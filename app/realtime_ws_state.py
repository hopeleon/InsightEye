from __future__ import annotations

from typing import Any

from .realtime_analyzer import build_realtime_transcript
from .realtime_session import store as realtime_store


def _payload_text(event: dict[str, Any]) -> str:
    for key in ("transcript", "text", "delta"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    item = event.get("item")
    if isinstance(item, dict):
        for key in ("transcript", "text"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _payload_ms(event: dict[str, Any], key: str) -> int:
    raw = event.get(key)
    if raw is None:
        item = event.get("item")
        if isinstance(item, dict):
            raw = item.get(key)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        try:
            return int(round(float(raw or 0.0) * 1000))
        except (TypeError, ValueError):
            return 0


def consume_realtime_event(session_id: str, speaker_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = str(event.get("type") or "")
    session = realtime_store.get(session_id)
    if not session:
        return {"type": "error", "message": "Realtime session not found"}

    if event_type in {
        "conversation.item.input_audio_transcription.delta",
        "conversation.item.input_audio_transcription.text",
    }:
        delta = _payload_text(event)
        if not delta:
            return None
        return {
            "type": "transcript.delta",
            "speaker_id": speaker_id,
            "delta": delta,
        }

    if event_type in {
        "conversation.item.input_audio_transcription.completed",
        "conversation.item.input_audio_transcription.segment",
    }:
        text = _payload_text(event)
        if not text:
            return None
        session = realtime_store.append_segment(
            session_id,
            {
                "speaker_id": speaker_id,
                "text": text,
                "start_ms": _payload_ms(event, "start_ms") or _payload_ms(event, "start"),
                "end_ms": _payload_ms(event, "end_ms") or _payload_ms(event, "end"),
                "final": True,
            },
        )
        rolling = session.get("rolling_analysis") or {}
        return {
            "type": "session.update",
            "session": {
                "session_id": session_id,
                "status": session.get("status", "active"),
                "segment_count": len(session.get("segments") or []),
                "segments": session.get("segments") or [],
                "role_inference": session.get("role_inference") or {},
                "display_transcript": build_realtime_transcript(session.get("segments") or [], session.get("role_inference") or {}),
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
            },
        }

    if event_type == "input_audio_buffer.speech_started":
        return {"type": "speech.started", "speaker_id": speaker_id}

    if event_type == "input_audio_buffer.speech_stopped":
        return {"type": "speech.stopped", "speaker_id": speaker_id}

    if event_type == "error":
        error = event.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "Realtime API error")
        else:
            message = str(event.get("message") or "Realtime API error")
        return {"type": "error", "message": message}

    return None
