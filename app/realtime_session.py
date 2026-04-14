from __future__ import annotations

import asyncio
import json
import time
import uuid
from threading import Lock
from typing import Any, Optional

from .realtime_analyzer import run_final_analysis, run_rolling_analysis, should_refresh_analysis


class RealtimeSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = Lock()
        self._analysis_tasks: dict[str, asyncio.Task] = {}
        self._analysis_task_lock = Lock()

    def create(self, job_hint: str = "") -> dict[str, Any]:
        session_id = f"rt_{uuid.uuid4().hex[:12]}"
        session = {
            "session_id": session_id,
            "job_hint": job_hint,
            "status": "active",
            "created_at": time.time(),
            "segments": [],
            "speaker_recognizer": None,
            "voice_registered": False,
            "voice_mapping": {},
            "rolling_analysis": None,
            "last_analysis_segment_count": 0,
            "last_analysis_candidate_chars": 0,
            "final_report": None,
            "ws_clients": [],
            "analysis_update_needed": False,
        }
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._sessions.get(session_id)

    def update_voice_mapping(self, session_id: str, voice_mapping: dict[str, str]) -> None:
        """更新声纹映射"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["voice_mapping"] = voice_mapping
                session["voice_registered"] = True

    def set_speaker_recognizer(self, session_id: str, recognizer) -> None:
        """设置说话人识别器"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["speaker_recognizer"] = recognizer

    def register_ws_client(self, session_id: str, websocket: Any) -> None:
        """注册实时 WS 客户端，用于后台分析完成后主动推送 session.update"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            clients = session.setdefault("ws_clients", [])
            if websocket not in clients:
                clients.append(websocket)

    def unregister_ws_client(self, session_id: str, websocket: Any) -> None:
        """注销实时 WS 客户端"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            clients = session.get("ws_clients") or []
            if websocket in clients:
                clients.remove(websocket)

    def mark_analysis_update_needed(self, session_id: str) -> None:
        """标记该 session 需要在分析完成后推送更新"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["analysis_update_needed"] = True

    def consume_analysis_update_needed(self, session_id: str) -> bool:
        """消费更新标记，避免重复推送"""
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return False
            needed = bool(session.get("analysis_update_needed"))
            session["analysis_update_needed"] = False
            return needed

    def append_segment(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        should_run_analysis = False
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(session_id)
            if session["status"] != "active":
                raise ValueError("Session is not active")

            segments = session["segments"]
            segment = {
                "id": len(segments) + 1,
                "speaker_id": str(payload.get("speaker_id") or "speaker_a").strip() or "speaker_a",
                "text": str(payload.get("text") or "").strip(),
                "start_ms": int(payload.get("start_ms") or 0),
                "end_ms": int(payload.get("end_ms") or 0),
                "final": bool(payload.get("final", True)),
                "recognized_role": payload.get("recognized_role"),
                "speaker_confidence": float(payload.get("speaker_confidence") or 0.0),
                "interviewer_sim": float(payload.get("interviewer_sim") or 0.0),
                "candidate_sim": float(payload.get("candidate_sim") or 0.0),
            }
            if not segment["text"]:
                raise ValueError("Segment text cannot be empty")
            segments.append(segment)
            should_run_analysis = should_refresh_analysis(session)
            if should_run_analysis:
                session["analysis_update_needed"] = True

        if should_run_analysis:
            self._schedule_rolling_analysis(session_id)
        return session

    def status(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        if not session:
            raise KeyError(session_id)
        if session["rolling_analysis"] is None and session["segments"]:
            self._schedule_rolling_analysis(session_id)
        return session

    def end(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(session_id)
            session["status"] = "finalizing"

        self._wait_for_analysis(session_id)
        if session["rolling_analysis"] is None and session["segments"]:
            run_rolling_analysis(session)
        session["final_report"] = run_final_analysis(session)
        session["status"] = "completed"
        return session

    def _schedule_rolling_analysis(self, session_id: str) -> None:
        with self._analysis_task_lock:
            task = self._analysis_tasks.get(session_id)
            if task and not task.done():
                return

            async def _run() -> None:
                try:
                    session = self.get(session_id)
                    if not session:
                        return
                    run_rolling_analysis(session)
                    await self._push_session_update(session_id)
                    self.consume_analysis_update_needed(session_id)
                finally:
                    with self._analysis_task_lock:
                        self._analysis_tasks.pop(session_id, None)

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return

            self._analysis_tasks[session_id] = loop.create_task(_run())

    async def _push_session_update(self, session_id: str) -> None:
        """后台分析完成后，主动向注册的 WS 客户端推送 session.update"""
        session = self.get(session_id)
        if not session:
            return

        ws_clients = list(session.get("ws_clients") or [])
        if not ws_clients:
            return

        from .realtime_ws_state import build_session_update_for_push

        update = build_session_update_for_push(session_id, session.get("segments", []), [])
        payload = json.dumps(update, ensure_ascii=False)

        for websocket in ws_clients:
            try:
                await websocket.send(payload)
            except Exception:
                continue

    def _wait_for_analysis(self, session_id: str) -> None:
        with self._analysis_task_lock:
            task = self._analysis_tasks.get(session_id)
        if task and not task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return
            if task.get_loop() is loop:
                return


store = RealtimeSessionStore()
