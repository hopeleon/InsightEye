from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .analysis import analyze_interview
from .config import BASE_DIR, STATIC_DIR

import uuid
from threading import Thread, Lock
from typing import Dict, Any
from urllib.parse import urlparse, parse_qs

# 全局任务存储
llm_tasks: Dict[str, Dict[str, Any]] = {}
tasks_lock = Lock()


def generate_task_id() -> str:
    """生成唯一任务 ID"""
    return str(uuid.uuid4())


def run_llm_task_async(task_id: str, transcript: str, job_hint: str):
    """
    后台线程执行 LLM 分析
    """
    from workflow.engine import run_disc_workflow
    from app.knowledge import load_disc_prompt
    
    try:
        # 更新任务状态
        with tasks_lock:
            llm_tasks[task_id]["status"] = "running"
            llm_tasks[task_id]["progress"] = "正在调用 LLM..."
        
        # 执行完整工作流（包含 LLM）
        result = run_disc_workflow(transcript, job_hint)
        
        # 保存结果
        with tasks_lock:
            llm_tasks[task_id]["status"] = "completed"
            llm_tasks[task_id]["result"] = result
            llm_tasks[task_id]["progress"] = "分析完成"
            
    except Exception as e:
        with tasks_lock:
            llm_tasks[task_id]["status"] = "failed"
            llm_tasks[task_id]["error"] = str(e)
            llm_tasks[task_id]["progress"] = f"失败: {str(e)}"

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
        
        # ========== 新增: LLM 任务状态查询 ==========
        if route.startswith("/api/llm_status/"):
            task_id = route.replace("/api/llm_status/", "")
            
            with tasks_lock:
                task = llm_tasks.get(task_id)
            
            if not task:
                _json_response(self, {"error": "任务不存在"}, status=404)
                return
            
            response = {
                "task_id": task_id,
                "status": task["status"],  # pending/running/completed/failed
                "progress": task["progress"],
            }
            
            if task["status"] == "completed":
                response["result"] = task["result"]
            elif task["status"] == "failed":
                response["error"] = task["error"]
            
            _json_response(self, response)
            return
        
        # ========== 原有路由保持不变 ==========
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

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/analyze":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            payload = json.loads(body)

            transcript = payload.get("interview_transcript", "").strip()
            job_hint = payload.get("job_hint_optional", "").strip()
            force_llm = payload.get("force_llm", False)  # 用户手动触发

            if not transcript:
                _json_response(self, {"error": "缺少面试文本"}, status=400)
                return

            try:
                from workflow.engine import run_local_workflow, should_trigger_llm

                # ========== 1. 立即执行本地规则分析 ==========
                print("🚀 开始本地规则分析...")
                local_result = run_local_workflow(transcript, job_hint)
                print("✅ 本地规则分析完成")

                # ========== 2. 判断是否需要 LLM ==========
                need_llm, reason = should_trigger_llm(local_result)

                if force_llm:
                    need_llm = True
                    reason = "用户手动触发深度分析"

                response = {
                    "local_result": local_result,
                    "llm_status": {
                        "triggered": need_llm,
                        "reason": reason,
                        "task_id": None,
                        "manual": force_llm,
                    }
                }

                # ========== 3. 如果需要 LLM，启动异步任务 ==========
                if need_llm:
                    task_id = generate_task_id()

                    # 初始化任务
                    with tasks_lock:
                        llm_tasks[task_id] = {
                            "status": "pending",
                            "progress": "等待启动...",
                            "transcript": transcript,
                            "job_hint": job_hint,
                            "result": None,
                            "error": None,
                        }

                    response["llm_status"]["task_id"] = task_id

                    # 启动后台线程
                    thread = Thread(
                        target=run_llm_task_async,
                        args=(task_id, transcript, job_hint),
                        daemon=True,
                    )
                    thread.start()

                    print(f"🔄 已启动 LLM 异步任务: {task_id}")

                _json_response(self, response)

            except Exception as e:
                print(f"❌ 分析失败: {e}")
                import traceback
                traceback.print_exc()
                _json_response(self, {"error": str(e)}, status=500)
    
        else:
            self.send_error(404)

    def log_message(self, format: str, *args) -> None:
        return


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InsightEye demo running at http://{host}:{port}")
    server.serve_forever()
