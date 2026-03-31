from __future__ import annotations

from email.parser import BytesParser
import contextlib
from email.policy import default
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
from .audio_transcription import AudioTranscriptionError, transcribe_audio_bytes, transcribe_audio_chunk_bytes
from .config import BASE_DIR, STATIC_DIR, REALTIME_WS_PORT
from .realtime_analyzer import build_realtime_transcript
from .realtime_session import store as realtime_store
from .realtime_ws_server import bridge_server

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
    with contextlib.suppress((BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
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

def _parse_multipart_form(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    content_length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(content_length)
    raw = b"Content-Type: " + handler.headers.get("Content-Type", "").encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    message = BytesParser(policy=default).parsebytes(raw)

    fields: dict[str, str] = {}
    files: dict[str, dict[str, Any]] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files[name] = {
                "filename": filename,
                "content": payload,
                "content_type": part.get_content_type(),
            }
        else:
            fields[name] = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return fields, files


def _run_audio_transcription(handler: BaseHTTPRequestHandler, fields: dict[str, str], files: dict[str, dict[str, Any]]) -> None:
    file_item = files.get("audio")
    if not file_item:
        _json_response(handler, {"error": "Missing audio file"}, status=400)
        return

    audio_bytes = file_item["content"]
    filename = file_item.get("filename") or "interview_audio.wav"
    mime_type = file_item.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    language = str(fields.get("language", "zh") or "zh").strip() or "zh"

    try:
        result = transcribe_audio_bytes(audio_bytes, filename=filename, mime_type=mime_type, language=language)
    except AudioTranscriptionError as exc:
        _json_response(handler, {"error": str(exc)}, status=400)
        return

    _json_response(
        handler,
        {
            "model": result["model"],
            "language": result["language"],
            "segment_count": len(result["segments"]),
            "segments": result["segments"],
            "transcript_preview": build_realtime_transcript(result["segments"], {}),
        },
    )


def _run_realtime_chunk_transcription(handler: BaseHTTPRequestHandler, session_id: str, fields: dict[str, str], files: dict[str, dict[str, Any]]) -> None:
    file_item = files.get("audio")
    if not file_item:
        _json_response(handler, {"error": "Missing audio file"}, status=400)
        return

    audio_bytes = file_item["content"]
    filename = file_item.get("filename") or "live_chunk.webm"
    mime_type = file_item.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    language = str(fields.get("language", "zh") or "zh").strip() or "zh"
    speaker_id = str(fields.get("speaker_id", "speaker_a") or "speaker_a").strip() or "speaker_a"
    start_ms = int(str(fields.get("start_ms", "0") or "0"))
    end_ms = int(str(fields.get("end_ms", "0") or "0"))

    print(f"[ChunkTranscribe] session={session_id} speaker={speaker_id} bytes={len(audio_bytes)} start_ms={start_ms} end_ms={end_ms}")
    try:
        result = transcribe_audio_chunk_bytes(
            audio_bytes,
            filename=filename,
            mime_type=mime_type,
            language=language,
            speaker_id=speaker_id,
            start_ms=start_ms,
            end_ms=end_ms,
        )
    except AudioTranscriptionError as exc:
        print(f"[ChunkTranscribe] failed session={session_id} speaker={speaker_id} error={exc}")
        _json_response(handler, {"error": str(exc)}, status=400)
        return

    session = realtime_store.status(session_id)
    segment = result.get("segment")
    if segment:
        session = realtime_store.append_segment(session_id, segment)

    _json_response(
        handler,
        {
            "session": _realtime_session_response(session),
            "transcribed": bool(segment),
            "text": result.get("text", ""),
            "speaker_id": speaker_id,
            "model": result.get("model"),
        },
    )


def _run_full_mode_analysis(handler: BaseHTTPRequestHandler, payload: dict) -> None:
    transcript = (payload.get("interview_transcript") or "").strip()
    if not transcript:
        _json_response(handler, {"error": "Missing interview_transcript"}, status=400)
        return
    job_hint = (payload.get("job_hint_optional") or "").strip()
    report = analyze_interview_full(transcript, job_hint)
    _json_response(handler, report)


def _realtime_session_response(session: dict[str, Any]) -> dict[str, Any]:
    rolling = session.get("rolling_analysis") or {}
    role_state = session.get("role_inference") or {}
    return {
        "session_id": session["session_id"],
        "status": session["status"],
        "job_hint_optional": session.get("job_hint", ""),
        "segment_count": len(session.get("segments") or []),
        "segments": session.get("segments") or [],
        "role_inference": role_state,
        "display_transcript": build_realtime_transcript(session.get("segments") or [], role_state),
        "rolling_analysis": {
            "summary": rolling.get("summary", ""),
            "risk_summary": rolling.get("risk_summary", ""),
            "evidence_gaps": rolling.get("evidence_gaps", []),
            "follow_up_questions": rolling.get("follow_up_questions", []),
            "recommended_action": rolling.get("recommended_action", ""),
            "mbti_type": rolling.get("mbti_type", ""),
            "mbti_summary": rolling.get("mbti_summary", ""),
            "local_result": rolling.get("local_result"),
        },
        "final_report": session.get("final_report"),
    }


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

        if route.startswith("/api/realtime/session/") and route.endswith("/status"):
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/status", "", 1).strip("/")
            try:
                session = realtime_store.status(session_id)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            _json_response(self, _realtime_session_response(session))
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
        content_type = self.headers.get("Content-Type", "")

        if route == "/api/audio/transcribe":
            if "multipart/form-data" not in content_type:
                _json_response(self, {"error": "Content-Type must be multipart/form-data"}, status=400)
                return
            fields, files = _parse_multipart_form(self)
            _run_audio_transcription(self, fields, files)
            return

        if route.startswith("/api/realtime/session/") and route.endswith("/transcribe_chunk"):
            if "multipart/form-data" not in content_type:
                _json_response(self, {"error": "Content-Type must be multipart/form-data"}, status=400)
                return
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/transcribe_chunk", "", 1).strip("/")
            try:
                realtime_store.status(session_id)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            fields, files = _parse_multipart_form(self)
            _run_realtime_chunk_transcription(self, session_id, fields, files)
            return

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

        if route == "/api/realtime/session/start":
            job_hint = (payload.get("job_hint_optional") or "").strip()
            session = realtime_store.create(job_hint=job_hint)
            _json_response(
                self,
                {
                    "session_id": session["session_id"],
                    "status": session["status"],
                    "message": "Realtime session started",
                    "append_path": f"/api/realtime/session/{session['session_id']}/append",
                    "status_path": f"/api/realtime/session/{session['session_id']}/status",
                    "end_path": f"/api/realtime/session/{session['session_id']}/end",
                    "ws_url": f"ws://127.0.0.1:{REALTIME_WS_PORT}/realtime?session_id={session['session_id']}",
                },
            )
            return

        if route.startswith("/api/realtime/session/") and route.endswith("/append"):
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/append", "", 1).strip("/")
            try:
                session = realtime_store.append_segment(session_id, payload)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            except ValueError as exc:
                _json_response(self, {"error": str(exc)}, status=400)
                return
            _json_response(self, _realtime_session_response(session))
            return

        if route.startswith("/api/realtime/session/") and route.endswith("/end"):
            session_id = route.replace("/api/realtime/session/", "", 1).replace("/end", "", 1).strip("/")
            try:
                session = realtime_store.end(session_id)
            except KeyError:
                _json_response(self, {"error": "Realtime session not found"}, status=404)
                return
            _json_response(self, _realtime_session_response(session))
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    bridge_server.start(host=host, port=REALTIME_WS_PORT)
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InsightEye demo running at http://{host}:{port}")
    print(f"InsightEye realtime websocket running at ws://{host}:{REALTIME_WS_PORT}/realtime")
    server.serve_forever()
