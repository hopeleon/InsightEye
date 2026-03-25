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

def run_full_analysis_async(task_id: str, transcript: str, job_hint: str, force_llm: bool):
    """
    后台线程执行完整分析流程：
    1. 先执行本地分析并立即返回
    2. 判断是否需要 LLM
    3. 如果需要，执行 LLM 分析
    """
    from workflow.engine import run_local_workflow, should_trigger_llm, run_disc_workflow
    
    try:
        # ========== 阶段 1: 本地规则分析 ==========
        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_running"
            llm_tasks[task_id]["progress"] = "正在执行本地规则分析..."
        
        print(f"🚀 任务 {task_id[:8]}: 开始本地分析...")
        local_result = run_local_workflow(transcript, job_hint)
        
        # 保存本地结果（前端可以立即拿到）
        with tasks_lock:
            llm_tasks[task_id]["status"] = "local_completed"
            llm_tasks[task_id]["local_result"] = local_result
            llm_tasks[task_id]["progress"] = "本地分析完成"
        
        print(f"✅ 任务 {task_id[:8]}: 本地分析完成")
        
        # ========== 阶段 2: 判断是否需要 LLM ==========
        need_llm, reason = should_trigger_llm(local_result)
        
        if force_llm:
            need_llm = True
            reason = "用户手动触发深度分析"
        
        # 更新 LLM 触发状态
        with tasks_lock:
            llm_tasks[task_id]["llm_triggered"] = need_llm
            llm_tasks[task_id]["llm_reason"] = reason
        
        if not need_llm:
            # 不需要 LLM，任务完成
            with tasks_lock:
                llm_tasks[task_id]["status"] = "completed"
                llm_tasks[task_id]["progress"] = "分析完成（未调用 LLM）"
            print(f"✅ 任务 {task_id[:8]}: 无需 LLM，任务结束")
            return
        
        # ========== 阶段 3: 执行 LLM 分析 ==========
        with tasks_lock:
            llm_tasks[task_id]["status"] = "llm_running"
            llm_tasks[task_id]["progress"] = "正在调用 LLM 深度分析..."
        
        print(f"🔄 任务 {task_id[:8]}: 开始 LLM 分析（原因: {reason}）")
        llm_result = run_disc_workflow(transcript, job_hint)
        
        # 保存 LLM 结果
        with tasks_lock:
            llm_tasks[task_id]["status"] = "completed"
            llm_tasks[task_id]["llm_result"] = llm_result
            llm_tasks[task_id]["progress"] = "LLM 分析完成"
        
        print(f"✨ 任务 {task_id[:8]}: LLM 分析完成")
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 任务 {task_id[:8]} 失败: {error_msg}")
        import traceback
        traceback.print_exc()
        
        with tasks_lock:
            llm_tasks[task_id]["status"] = "failed"
            llm_tasks[task_id]["error"] = error_msg
            llm_tasks[task_id]["progress"] = f"失败: {error_msg}"


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
            
            status = task["status"]
            response = {
                "task_id": task_id,
                "status": status,
                "progress": task["progress"],
            }
            
            # 如果本地分析完成，返回本地结果
            if status in ["local_completed", "llm_running", "completed"]:
                response["local_result"] = task["local_result"]
                response["llm_triggered"] = task.get("llm_triggered", False)
                response["llm_reason"] = task.get("llm_reason", "")
            
            # 如果 LLM 分析完成，返回 LLM 结果
            if status == "completed" and task.get("llm_result"):
                response["llm_result"] = task["llm_result"]
            
            # 如果失败，返回错误
            if status == "failed":
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
            force_llm = payload.get("force_llm", False)

            if not transcript:
                _json_response(self, {"error": "缺少面试文本"}, status=400)
                return

            try:
                # ========== 立即生成任务 ID 并返回 ==========
                task_id = generate_task_id()

                # 初始化任务（状态为 "local_pending"）
                with tasks_lock:
                    llm_tasks[task_id] = {
                        "status": "local_pending",  # 新状态
                        "progress": "准备本地分析...",
                        "transcript": transcript,
                        "job_hint": job_hint,
                        "force_llm": force_llm,
                        "local_result": None,
                        "llm_result": None,
                        "error": None,
                    }

                # 启动后台线程执行完整流程
                thread = Thread(
                    target=run_full_analysis_async,
                    args=(task_id, transcript, job_hint, force_llm),
                    daemon=True,
                )
                thread.start()

                # 立即返回任务 ID（前端开始轮询）
                _json_response(self, {
                    "task_id": task_id,
                    "message": "分析任务已启动，请轮询状态"
                })

            except Exception as e:
                print(f"❌ 启动任务失败: {e}")
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
