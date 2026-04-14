from __future__ import annotations

from typing import Any, Optional

from .realtime_analyzer import build_realtime_transcript
from .realtime_session import store as realtime_store


def build_session_update(session_id: str, corrections: list | None = None) -> dict[str, Any] | None:
    session = realtime_store.get(session_id)
    if not session:
        return None
    return _build_session_update(session_id, session.get("segments", []), corrections or [])


def consume_local_transcript_event(session_id: str, vad_speaker_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
    """
    处理本地 FunASR 转录完成事件，更新会话状态。

    策略：注册前用 enrollment_source 标签存储 segment；注册后用 CAM++ 识别结果。
    注册完成后通过 _retroactive_identify 批量修正之前存储的 segment 角色。
    """
    event_type = str(event.get("type") or "")

    if event_type != "transcript.completed":
        return None

    session = realtime_store.get(session_id)
    if not session:
        return {"type": "error", "message": "Realtime session not found"}

    text = str(event.get("text") or "").strip()
    if not text:
        return None

    voice_registered = session.get("voice_registered", False)
    recognized_role = event.get("recognized_role")  # CAM++ 声纹识别结果
    campp_speaker_id = event.get("speaker_id")  # CAM++ 识别的 speaker_id
    interviewer_sim = float(event.get("interviewer_sim") or 0.0)
    candidate_sim = float(event.get("candidate_sim") or 0.0)

    # pending_audio 存在说明还在注册期间，用 enrollment_source 标签存储
    if not voice_registered or not recognized_role:
        # 注册期间：存储为 enrollment_source，立即用对应音频做声纹比对修正
        pending_audio: list = session.get("pending_audio", [])

        try:
            session = realtime_store.append_segment(
                session_id,
                {
                    "speaker_id": "enrollment_source",
                    "text": text,
                    "start_ms": int(event.get("start_ms") or 0),
                    "end_ms": int(event.get("end_ms") or 0),
                    "final": True,
                    "recognized_role": "enrollment_source",
                    "speaker_confidence": float(event.get("speaker_confidence") or 0.0),
                    "interviewer_sim": interviewer_sim,
                    "candidate_sim": candidate_sim,
                },
            )
        except ValueError:
            return None

        # 用对应音频做声纹比对，修正刚存的 segment
        recognizer: Optional[Any] = session.get("speaker_recognizer")
        if recognizer and pending_audio:
            audio = pending_audio[0]["audio_samples"]
            match = recognizer.identify_speaker(audio)
            if match:
                role = match.role or match.speaker_id
                int_sim = match.similarity if role == "interviewer" else 0.0
                cand_sim = match.similarity if role == "candidate" else 0.0
            else:
                role = "interviewer"
                int_sim = 0.0
                cand_sim = 0.0

            segments = session.get("segments", [])
            if segments:
                seg = segments[-1]
                seg["speaker_id"] = role
                seg["recognized_role"] = role
                seg["interviewer_sim"] = float(int_sim)
                seg["candidate_sim"] = float(cand_sim)
                print(f"[AutoReg] fixed enrollment_source segment[{len(segments)-1}] -> {role}")
            pending_audio.pop(0)

        realtime_store.mark_analysis_update_needed(session_id)
        return build_session_update(session_id, [])

    # 注册后：CAM++ 直接给角色，用识别结果存储
    try:
        realtime_store.clear_partial_transcript(session_id, campp_speaker_id or recognized_role)
        session = realtime_store.append_segment(
            session_id,
            {
                "speaker_id": campp_speaker_id or recognized_role,
                "text": text,
                "start_ms": int(event.get("start_ms") or 0),
                "end_ms": int(event.get("end_ms") or 0),
                "final": True,
                "recognized_role": recognized_role,
                "speaker_confidence": float(event.get("speaker_confidence") or 0.0),
                "interviewer_sim": interviewer_sim,
                "candidate_sim": candidate_sim,
            },
        )
    except ValueError:
        return None

    realtime_store.mark_analysis_update_needed(session_id)
    return _build_session_update(session_id, session.get("segments", []), [])


def _build_session_update(session_id: str, segments: list, corrections: list) -> dict[str, Any]:
    """构建 session.update 响应"""
    session = realtime_store.get(session_id)
    rolling = (session or {}).get("rolling_analysis") or {}
    rolling_disc = (session or {}).get("rolling_disc_analysis") or {}

    return {
        "type": "session.update",
        "segment_corrections": corrections,
        "session": {
            "session_id": session_id,
            "status": (session or {}).get("status", "active"),
            "segment_count": len(segments),
            "segments": segments,
            "voice_registered": (session or {}).get("voice_registered", False),
            "voice_mapping": (session or {}).get("voice_mapping", {}),
            "display_transcript": build_realtime_transcript(
                segments,
                (session or {}).get("voice_mapping", {}),
            ),
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
            "rolling_disc_analysis": rolling_disc,
        },
    }


def build_session_update_for_push(session_id: str, segments: list, corrections: list) -> dict[str, Any]:
    """后台分析完成后主动推送 session.update 的统一入口"""
    return _build_session_update(session_id, segments, corrections)


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
    """
    处理 DashScope 实时事件（原有模式）
    """
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
        realtime_store.update_partial_transcript(session_id, speaker_id, delta)
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
        realtime_store.clear_partial_transcript(session_id, speaker_id)
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
        return _build_session_update(session_id, session.get("segments") or [], [])

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
