from __future__ import annotations

import time
import uuid
from threading import Lock
from typing import Any, Optional

from .realtime_analyzer import run_final_analysis, run_rolling_analysis, should_refresh_analysis
from .realtime_disc_analyzer import run_realtime_disc_analysis, should_refresh_realtime_disc


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
            "partial_transcripts": {},
            "speaker_recognizer": None,
            "voice_registered": False,
            "voice_mapping": {},
            "rolling_analysis": None,
            "rolling_disc_analysis": None,
            "last_analysis_segment_count": 0,
            "last_analysis_candidate_chars": 0,
            "last_disc_analysis_segment_count": 0,
            "last_disc_analysis_candidate_chars": 0,
            "last_disc_analysis_at": 0.0,
            "last_disc_llm_at": 0.0,
            "last_disc_llm_signature": "",
            "final_report": None,
        }
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._sessions.get(session_id)

    def update_voice_mapping(self, session_id: str, voice_mapping: dict[str, str]) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["voice_mapping"] = voice_mapping
                session["voice_registered"] = True

    def set_speaker_recognizer(self, session_id: str, recognizer) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["speaker_recognizer"] = recognizer

    def update_partial_transcript(
        self,
        session_id: str,
        speaker_id: str,
        text: str,
        *,
        recognized_role: str | None = None,
        interviewer_sim: float = 0.0,
        candidate_sim: float = 0.0,
    ) -> tuple[dict[str, Any] | None, bool]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session or session["status"] != "active":
                return None, False
            partials = session.setdefault("partial_transcripts", {})
            clean_text = str(text or "").strip()
            if clean_text:
                partials[str(speaker_id or "speaker_a")] = {
                    "speaker_id": str(speaker_id or "speaker_a"),
                    "text": clean_text,
                    "recognized_role": recognized_role,
                    "interviewer_sim": float(interviewer_sim or 0.0),
                    "candidate_sim": float(candidate_sim or 0.0),
                    "updated_at": time.time(),
                }
            else:
                partials.pop(str(speaker_id or "speaker_a"), None)

        # 不在此处调用 DISC 分析——由调用方在线程池中异步触发，避免阻塞事件循环
        return session, False

    def clear_partial_transcript(self, session_id: str, speaker_id: str | None) -> None:
        if not speaker_id:
            return
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return
            partials = session.setdefault("partial_transcripts", {})
            partials.pop(str(speaker_id), None)

    def append_segment(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(session_id)
            if session["status"] != "active":
                raise ValueError("Session is not active")

            segments = session["segments"]
            speaker_id = str(payload.get("speaker_id") or "speaker_a").strip() or "speaker_a"
            segment = {
                "id": len(segments) + 1,
                "speaker_id": speaker_id,
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

            partials = session.setdefault("partial_transcripts", {})
            partials.pop(speaker_id, None)

        if should_refresh_analysis(session):
            run_rolling_analysis(session)
        # rolling_analysis 和 DISC 分析均不在此处同步调用
        # 由调用方（_async_disc_refresh）在线程池中异步触发，避免阻塞事件循环
        return session

    def status(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        if not session:
            raise KeyError(session_id)
        if session["rolling_analysis"] is None and session["segments"]:
            run_rolling_analysis(session)
        if session.get("rolling_disc_analysis") is None and (session["segments"] or session.get("partial_transcripts")):
            run_realtime_disc_analysis(session)
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
