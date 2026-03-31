from __future__ import annotations

import time
import uuid
from threading import Lock
from typing import Any

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
            "role_inference": {"ready": False, "mapping": {}, "confidence": 0.0, "reasons": []},
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
