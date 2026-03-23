from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .analysis import analyze_interview
from .config import BASE_DIR, STATIC_DIR

SAMPLES_DIR = BASE_DIR / "samples"


def _json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
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
    handler.end_headers()
    handler.wfile.write(data)


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
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
        if parsed.path != "/api/analyze":
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            _json_response(self, {"error": "请求体必须是合法 JSON。"}, status=400)
            return

        transcript = (payload.get("interview_transcript") or "").strip()
        if not transcript:
            _json_response(self, {"error": "缺少 interview_transcript。"}, status=400)
            return

        job_hint = (payload.get("job_hint_optional") or "").strip()
        report = analyze_interview(transcript, job_hint)
        _json_response(self, report)

    def log_message(self, format: str, *args) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InsightEye demo running at http://{host}:{port}")
    server.serve_forever()
