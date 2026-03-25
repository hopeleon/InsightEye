from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Dict, Any
from urllib.parse import urlparse
import uuid

from .analysis import analyze_interview, analyze_interview_full
from .config import BASE_DIR, STATIC_DIR

SAMPLES_DIR = BASE_DIR / "samples"

<<<<<<< Updated upstream
=======
# ========== 异步任务存储 ==========
llm_tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = Lock()


def generate_task_id() -> str:
    return str(uuid.uuid4())


def run_full_analysis_async(task_id: str, transcript: str, job_hint: str, force_llm: bool):
    from workflow.engine import run_local_workflow, should_trigger_llm, run_disc_workflow

    try:
        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_running"
            llm_tasks[task_id]["progress"] = "正在执行本地规则分析..."

        local_result = run_local_workflow(transcript, job_hint)

        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_completed"
            llm_tasks[task_id]["local_result"] = local_result
            llm_tasks[task_id]["progress"] = "本地分析完成"

        need_llm, reason = should_trigger_llm(local_result)

        if force_llm:
            need_llm = True
            reason = "用户手动触发深度分析"

        with tasks_lock:
            llm_tasks[task_id]["llm_triggered"] = need_llm
            llm_tasks[task_id]["llm_reason"] = reason

        if not need_llm:
            with tasks_lock:
                llm_tasks[task_id]["status"] = "completed"
                llm_tasks[task_id]["progress"] = "分析完成（未调用 LLM）"
            return

        with tasks_lock:
            llm_tasks[task_id]["status"] = "llm_running"
            llm_tasks[task_id]["progress"] = "正在调用 LLM 深度分析..."

        llm_result = run_disc_workflow(transcript, job_hint)

        with tasks_lock:
            llm_tasks[task_id]["status"] = "completed"
            llm_tasks[task_id]["llm_result"] = llm_result
            llm_tasks[task_id]["progress"] = "LLM 分析完成"

    except Exception as e:
        with tasks_lock:
            llm_tasks[task_id]["status"] = "failed"
            llm_tasks[task_id]["error"] = str(e)
            llm_tasks[task_id]["progress"] = f"失败: {str(e)}"

>>>>>>> Stashed changes

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
<<<<<<< Updated upstream
    # 避免浏览器长期缓存 index.html / JS / CSS，否则 UI 更新后用户仍看到旧版页面
=======
>>>>>>> Stashed changes
    handler.send_header("Cache-Control", "no-store, max-age=0, must-revalidate")
    handler.send_header("Pragma", "no-cache")
    handler.end_headers()
    handler.wfile.write(data)


def _parse_payload(raw_body: bytes) -> dict | None:
    try:
        return json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return None


def _run_analysis(handler: BaseHTTPRequestHandler, payload: dict, full: bool = False) -> None:
    transcript = (payload.get("interview_transcript") or "").strip()
    if not transcript:
        _json_response(handler, {"error": "缺少 interview_transcript。"}, status=400)
        return

    job_hint = (payload.get("job_hint_optional") or "").strip()
<<<<<<< Updated upstream

    if full:
        report = analyze_interview_full(transcript, job_hint)
    else:
        report = analyze_interview(transcript, job_hint)
=======
    apply_kg = True
    if "use_knowledge_graph" in payload:
        raw_kg = payload["use_knowledge_graph"]
        if isinstance(raw_kg, str):
            apply_kg = raw_kg.strip().lower() not in ("0", "false", "no", "off")
        else:
            apply_kg = bool(raw_kg)

    if full:
        report = analyze_interview_full(transcript, job_hint, apply_knowledge_graph=apply_kg)
    else:
        report = analyze_interview(transcript, job_hint, apply_knowledge_graph=apply_kg)
>>>>>>> Stashed changes

    _json_response(handler, report)


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
<<<<<<< Updated upstream
=======

        # 异步任务状态查询
        if route.startswith("/api/llm_status/"):
            task_id = route.replace("/api/llm_status/", "")
            with tasks_lock:
                task = llm_tasks.get(task_id)
            if not task:
                _json_response(self, {"error": "任务不存在"}, status=404)
                return
            status = task["status"]
            response = {
                "task_id": task_id,
                "status": status,
                "progress": task["progress"],
            }
            if status in ["local_completed", "llm_running", "completed"]:
                response["local_result"] = task["local_result"]
                response["llm_triggered"] = task.get("llm_triggered", False)
                response["llm_reason"] = task.get("llm_reason", "")
            if status == "completed" and task.get("llm_result"):
                response["llm_result"] = task["llm_result"]
            if status == "failed":
                response["error"] = task["error"]
            _json_response(self, response)
            return

>>>>>>> Stashed changes
        if route == "/":
            _serve_file(self, STATIC_DIR / "index.html")
            return
        if route.startswith("/static/"):
            relative = route.replace("/static/", "", 1)
            _serve_file(self, STATIC_DIR / relative)
            return
        if route.startswith("/samples/"):
            relative = route.replace("/samples/", "", 1)
            _serve_file(self, SAMPLES_DIR / relative)
            return
        if route == "/api/health":
            _json_response(self, {"ok": True})
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
<<<<<<< Updated upstream
<<<<<<< Updated upstream
        if route not in ("/api/analyze", "/api/analyze/full"):
=======

        # ywj 新增：完整人格分析接口（/api/analyze/full）
        if route == "/api/analyze/full":
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length)
            payload = _parse_payload(raw_body)
            if payload is None:
                _json_response(self, {"error": "请求体必须是合法 JSON。"}, status=400)
=======

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        payload = _parse_payload(raw_body)
        if payload is None:
            _json_response(self, {"error": "请求体必须是合法 JSON。"}, status=400)
            return

        # 完整人格分析接口（ywj 分支新增）
        if route == "/api/analyze/full":
            _run_analysis(self, payload, full=True)
            return

        # 原有 DISC 分析接口（异步模式）
        if route == "/api/analyze":
            transcript = (payload.get("interview_transcript") or "").strip()
            job_hint = (payload.get("job_hint_optional") or "").strip()
            force_llm = payload.get("force_llm", False)

            if not transcript:
                _json_response(self, {"error": "缺少面试文本"}, status=400)
>>>>>>> Stashed changes
                return
            _run_analysis(self, payload, full=True)
            return

<<<<<<< Updated upstream
        # 原有 DISC 分析接口（完全不变）
        if route != "/api/analyze":
>>>>>>> Stashed changes
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        payload = _parse_payload(raw_body)
        if payload is None:
            _json_response(self, {"error": "请求体必须是合法 JSON。"}, status=400)
            return
<<<<<<< Updated upstream

        transcript = (payload.get("interview_transcript") or "").strip()
        if not transcript:
            _json_response(self, {"error": "缺少 interview_transcript。"}, status=400)
            return

        job_hint = (payload.get("job_hint_optional") or "").strip()
        raw_kg = payload.get("use_knowledge_graph", True)
        if isinstance(raw_kg, str):
            use_knowledge_graph = raw_kg.strip().lower() not in ("0", "false", "no", "off")
        else:
            use_knowledge_graph = bool(raw_kg)
        if route == "/api/analyze/full":
            report = analyze_interview_full(
                transcript,
                job_hint,
                apply_knowledge_graph=use_knowledge_graph,
            )
        else:
            report = analyze_interview(
                transcript,
                job_hint,
                apply_knowledge_graph=use_knowledge_graph,
            )
        _json_response(self, report)
=======
        _run_analysis(self, payload, full=False)
>>>>>>> Stashed changes
=======
            task_id = generate_task_id()
            with tasks_lock:
                llm_tasks[task_id] = {
                    "status": "local_pending",
                    "progress": "准备本地分析...",
                    "transcript": transcript,
                    "job_hint": job_hint,
                    "force_llm": force_llm,
                    "local_result": None,
                    "llm_result": None,
                    "error": None,
                }

            thread = Thread(
                target=run_full_analysis_async,
                args=(task_id, transcript, job_hint, force_llm),
                daemon=True,
            )
            thread.start()

            _json_response(self, {
                "task_id": task_id,
                "message": "分析任务已启动，请轮询状态"
            })
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")
>>>>>>> Stashed changes

    def log_message(self, format: str, *args) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InsightEye demo running at http://{host}:{port}")
    server.serve_forever()
