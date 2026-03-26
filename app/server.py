from __future__ import annotations

import json
import mimetypes
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from urllib.parse import urlparse

from .analysis import analyze_interview_full
from .config import BASE_DIR, STATIC_DIR

SAMPLES_DIR = BASE_DIR / "samples"
llm_tasks: dict[str, dict[str, Any]] = {}
tasks_lock = Lock()


def generate_task_id() -> str:
    return str(uuid.uuid4())


def run_full_analysis_async(task_id: str, transcript: str, job_hint: str, force_llm: bool) -> None:
    from workflow.engine import run_disc_workflow, run_local_workflow, should_trigger_llm

    try:
        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_running"
            llm_tasks[task_id]["progress"] = "Running local rule analysis..."

        local_result = run_local_workflow(transcript, job_hint)
        need_llm, reason = should_trigger_llm(local_result)
        if force_llm:
            need_llm = True
            reason = "LLM analysis forced by user"

        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_completed"
            llm_tasks[task_id]["local_result"] = local_result
            llm_tasks[task_id]["llm_triggered"] = need_llm
            llm_tasks[task_id]["llm_reason"] = reason
            llm_tasks[task_id]["progress"] = "Local analysis completed"

        if not need_llm:
            with tasks_lock:
                llm_tasks[task_id]["status"] = "completed"
                llm_tasks[task_id]["progress"] = "Completed without LLM"
            return

        with tasks_lock:
            llm_tasks[task_id]["status"] = "llm_running"
            llm_tasks[task_id]["progress"] = "Running LLM analysis..."

        llm_result = run_disc_workflow(transcript, job_hint)
        with tasks_lock:
            llm_tasks[task_id]["status"] = "completed"
            llm_tasks[task_id]["llm_result"] = llm_result
            llm_tasks[task_id]["progress"] = "LLM analysis completed"
    except Exception as exc:
        with tasks_lock:
            llm_tasks[task_id]["status"] = "failed"
            llm_tasks[task_id]["error"] = str(exc)
            llm_tasks[task_id]["progress"] = f"Failed: {exc}"


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


def _serve_file(handler: BaseHTTPRequestHandler, path: Path) -> None:
    if not path.exists() or not path.is_file():
        handler.send_error(HTTPStatus.NOT_FOUND, "File not found")
        return
    mime_type, _ = mimetypes.guess_type(str(path))
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", f"{mime_type or 'application/octet-stream'}; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.end_headers()
    handler.wfile.write(data)


def _parse_payload(raw_body: bytes) -> dict | None:
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _run_full_mode_analysis(handler: BaseHTTPRequestHandler, payload: dict) -> None:
    transcript = (payload.get("interview_transcript") or "").strip()
    if not transcript:
        _json_response(handler, {"error": "Missing interview_transcript"}, status=400)
        return
    job_hint = (payload.get("job_hint_optional") or "").strip()
    report = analyze_interview_full(transcript, job_hint)
    _json_response(handler, report)


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        route = urlparse(self.path).path

        if route.startswith("/api/llm_status/"):
            task_id = route.replace("/api/llm_status/", "")
            with tasks_lock:
                task = llm_tasks.get(task_id)
            if not task:
                _json_response(self, {"error": "Task not found"}, status=404)
                return

            response = {
                "task_id": task_id,
                "status": task["status"],
                "progress": task.get("progress", ""),
            }
            if task["status"] in {"local_completed", "llm_running", "completed"}:
                response["local_result"] = task.get("local_result")
                response["llm_triggered"] = task.get("llm_triggered", False)
                response["llm_reason"] = task.get("llm_reason", "")
            if task["status"] == "completed" and task.get("llm_result"):
                response["llm_result"] = task.get("llm_result")
            if task["status"] == "failed":
                response["error"] = task.get("error", "Unknown error")
            _json_response(self, response)
            return

        if route == "/":
            _serve_file(self, STATIC_DIR / "index.html")
            return
        if route.startswith("/static/"):
            _serve_file(self, STATIC_DIR / route.replace("/static/", "", 1))
            return
        if route.startswith("/samples/"):
            _serve_file(self, SAMPLES_DIR / route.replace("/samples/", "", 1))
            return
        if route == "/api/health":
            _json_response(self, {"ok": True})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = _parse_payload(self.rfile.read(content_length))
        if payload is None:
            _json_response(self, {"error": "Body must be valid JSON"}, status=400)
            return

        if route == "/api/analyze/full":
            _run_full_mode_analysis(self, payload)
            return

        if route == "/api/analyze":
            transcript = (payload.get("interview_transcript") or "").strip()
            job_hint = (payload.get("job_hint_optional") or "").strip()
            force_llm = bool(payload.get("force_llm", False))
            if not transcript:
                _json_response(self, {"error": "Missing interview transcript"}, status=400)
                return

            task_id = generate_task_id()
            with tasks_lock:
                llm_tasks[task_id] = {
                    "status": "local_pending",
                    "progress": "Preparing local analysis...",
                    "transcript": transcript,
                    "job_hint": job_hint,
                    "force_llm": force_llm,
                    "local_result": None,
                    "llm_result": None,
                    "error": None,
                    "llm_triggered": False,
                    "llm_reason": "",
                }

            Thread(
                target=run_full_analysis_async,
                args=(task_id, transcript, job_hint, force_llm),
                daemon=True,
            ).start()
            _json_response(self, {"task_id": task_id, "message": "Task started"})
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InsightEye demo running at http://{host}:{port}")
    server.serve_forever()
