from __future__ import annotations

import time
import uuid
from threading import Lock
from typing import Any, Optional

from .realtime_analyzer import run_final_analysis, run_rolling_analysis, should_refresh_analysis


class RealtimeSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def create(self, job_hint: str = "") -> dict[str, Any]:
        session_id = f"rt_{uuid.uuid4().hex[:12]}"
        session = {
            "session_id": session_id,
            "job_hint": job_hint,
            "status": "active",
            "created_at": time.time(),
            "segments": [],
            "speaker_recognizer": None,  # CAM++ 说话人识别器
            "voice_registered": False,     # 声纹是否已注册
            "voice_mapping": {},
            "rolling_analysis": None,
            "last_analysis_segment_count": 0,
            "last_analysis_candidate_chars": 0,
            "final_report": None,
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

    def append_segment(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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
                "recognized_role": payload.get("recognized_role"),  # 声纹识别的角色
                "speaker_confidence": float(payload.get("speaker_confidence") or 0.0),  # 最佳相似度
                "interviewer_sim": float(payload.get("interviewer_sim") or 0.0),  # 与面试官的相似度
                "candidate_sim": float(payload.get("candidate_sim") or 0.0),  # 与候选人的相似度
            }
            if not segment["text"]:
                raise ValueError("Segment text cannot be empty")
            segments.append(segment)

        if should_refresh_analysis(session):
            run_rolling_analysis(session)
        return session

    def status(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        if not session:
            raise KeyError(session_id)
        if session["rolling_analysis"] is None and session["segments"]:
            run_rolling_analysis(session)
        return session

    def end(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(session_id)
            session["status"] = "finalizing"

        if session["rolling_analysis"] is None and session["segments"]:
            run_rolling_analysis(session)
        session["final_report"] = run_final_analysis(session)
        session["status"] = "completed"
        return session


store = RealtimeSessionStore()
