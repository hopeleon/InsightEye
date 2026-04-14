from __future__ import annotations

import json
import logging
import time
from typing import Any

import app.config as config
from app.knowledge import load_realtime_disc_prompt
from workflow.engine import run_local_workflow
from workflow.helpers import call_openai_compatible

logger = logging.getLogger("insighteye.realtime_disc")

_STYLE_LABELS = {
    "D": "Dominance",
    "I": "Influence",
    "S": "Steadiness",
    "C": "Conscientiousness",
}

_LOCAL_ROLE_MAP = {
    "D": ["Sales Lead", "Business Development", "Project Lead", "Team Manager"],
    "I": ["Customer Success", "Sales Consultant", "Marketing", "Recruiting"],
    "S": ["Operations", "Delivery Manager", "Implementation", "Account Support"],
    "C": ["Data Analyst", "Solution Consultant", "Process Ops", "Quality Control"],
}

_DISC_KEYS = ("D", "I", "S", "C")


def _reverse_voice_map(session: dict[str, Any]) -> dict[str, str]:
    voice_mapping = session.get("voice_mapping") or {}
    return {v: k for k, v in voice_mapping.items()}


def _resolve_role(session: dict[str, Any], item: dict[str, Any]) -> str | None:
    role = item.get("recognized_role")
    if role:
        return str(role)
    return _reverse_voice_map(session).get(str(item.get("speaker_id") or ""))


def _partial_entries(session: dict[str, Any]) -> list[dict[str, Any]]:
    partials = session.get("partial_transcripts") or {}
    return sorted(partials.values(), key=lambda item: float(item.get("updated_at") or 0.0))


def _full_transcript(session: dict[str, Any], *, include_partials: bool = True) -> str:
    lines: list[str] = []
    for seg in session.get("segments") or []:
        text = str(seg.get("text") or "").strip()
        if not text:
            continue
        role = _resolve_role(session, seg)
        label = "Candidate" if role == "candidate" else "Interviewer" if role == "interviewer" else str(seg.get("speaker_id") or "Speaker")
        lines.append(f"{label}: {text}")
    if include_partials:
        for partial in _partial_entries(session):
            text = str(partial.get("text") or "").strip()
            if not text:
                continue
            role = _resolve_role(session, partial)
            label = "Candidate" if role == "candidate" else "Interviewer" if role == "interviewer" else str(partial.get("speaker_id") or "Speaker")
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


def _candidate_chars(session: dict[str, Any], *, include_partials: bool = True) -> int:
    total = 0
    for seg in session.get("segments") or []:
        if _resolve_role(session, seg) == "candidate":
            total += len(str(seg.get("text") or ""))
    if include_partials:
        for partial in _partial_entries(session):
            if _resolve_role(session, partial) == "candidate":
                total += len(str(partial.get("text") or ""))
    return total


def _has_candidate_partial(session: dict[str, Any]) -> bool:
    return any(_resolve_role(session, item) == "candidate" and str(item.get("text") or "").strip() for item in _partial_entries(session))


def _style_label(style: str) -> str:
    return _STYLE_LABELS.get(style or "", style or "Unknown")


def _local_roles(dominant: str, secondary: str) -> list[str]:
    merged: list[str] = []
    for style in (dominant, secondary):
        for role in _LOCAL_ROLE_MAP.get(style or "", []):
            if role not in merged:
                merged.append(role)
    return merged[:4]


def _local_summary(dominant: str, secondary: str, confidence: str, is_partial: bool) -> str:
    if not dominant:
        return "Not enough candidate content yet to form a stable realtime DISC trend."
    live_note = " Live window still in progress." if is_partial else ""
    if secondary:
        return f"Current realtime signal leans toward {_style_label(dominant)} first and {_style_label(secondary)} second, with {confidence} confidence.{live_note}"
    return f"Current realtime signal leans toward {_style_label(dominant)} with {confidence} confidence.{live_note}"


def _local_role_reason(dominant: str, secondary: str) -> str:
    if dominant and secondary:
        return f"The current {_style_label(dominant)} plus {_style_label(secondary)} pattern fits roles that value drive, communication, and structured execution."
    if dominant:
        return f"The current {_style_label(dominant)} trend fits roles that reward this style more directly."
    return "Recommended roles will stabilize after more candidate content arrives."


def _local_followup_hint(dominant: str) -> str:
    hints = {
        "D": "Ask how the candidate makes decisions under pressure and drives execution.",
        "I": "Ask how the candidate influences stakeholders and builds momentum.",
        "S": "Ask how the candidate sustains collaboration and delivery over time.",
        "C": "Ask how the candidate validates details, manages risk, and keeps standards.",
    }
    return hints.get(dominant or "", "Keep collecting examples to validate the current DISC trend.")


def _compute_score_deltas(current: dict[str, int], previous: dict[str, int]) -> dict[str, int]:
    """计算 DISC 各维度分数变化量，previous 为空时返回全零"""
    if not previous:
        return {k: 0 for k in _DISC_KEYS}
    return {k: current.get(k, 0) - previous.get(k, 0) for k in _DISC_KEYS}


def _smoothed_scores(current_scores: dict[str, Any], previous_scores: dict[str, Any]) -> dict[str, int]:
    smoothed: dict[str, int] = {}
    for key in _DISC_KEYS:
        current = float(current_scores.get(key) or 0)
        previous = float(previous_scores.get(key) or 0)
        base = current if not previous_scores else previous * 0.58 + current * 0.42
        smoothed[key] = int(round(base))
    return smoothed


def _rank_scores(scores: dict[str, int]) -> list[str]:
    return [key for key, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


def _should_call_llm(session: dict[str, Any], signature: str) -> bool:
    if not (config.OPENAI_API_KEY and config.OPENAI_REALTIME_DISC_MODEL):
        return False
    now = time.time()
    last_llm_at = float(session.get("last_disc_llm_at") or 0.0)
    last_signature = str(session.get("last_disc_llm_signature") or "")
    if signature != last_signature:
        return True
    return now - last_llm_at >= 10.0


def should_refresh_realtime_disc(
    session: dict[str, Any],
    *,
    min_new_segments: int = 1,
    min_new_candidate_chars: int = 20,
    min_interval_sec: int = 1,
) -> bool:
    segments = session.get("segments") or []
    if not segments and not session.get("partial_transcripts"):
        return False
    now = time.time()
    last_ts = float(session.get("last_disc_analysis_at") or 0.0)
    if last_ts and now - last_ts < min_interval_sec:
        return False
    last_count = int(session.get("last_disc_analysis_segment_count") or 0)
    current_chars = _candidate_chars(session, include_partials=True)
    last_chars = int(session.get("last_disc_analysis_candidate_chars") or 0)
    if len(segments) - last_count >= min_new_segments:
        return True
    if current_chars - last_chars >= min_new_candidate_chars:
        return True
    if _has_candidate_partial(session) and current_chars > last_chars:
        return True
    return False


def _build_llm_messages(transcript: str, disc_result: dict[str, Any], job_hint: str) -> list[dict[str, str]]:
    payload = {
        "job_hint": job_hint,
        "rolling_transcript": transcript[-4000:],
        "local_disc_analysis": {
            "scores": disc_result.get("scores") or {},
            "ranking": disc_result.get("ranking") or [],
            "confidence": ((disc_result.get("meta") or {}).get("confidence") or "medium"),
            "sample_quality": ((disc_result.get("meta") or {}).get("sample_quality") or "unknown"),
            "overall_style_summary": disc_result.get("overall_style_summary") or "",
            "evidence_gaps": list(disc_result.get("evidence_gaps") or [])[:3],
            "feature_highlights": list(disc_result.get("feature_highlights") or [])[:4],
        },
    }
    return [
        {"role": "system", "content": load_realtime_disc_prompt()},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def run_realtime_disc_analysis(session: dict[str, Any]) -> dict[str, Any]:
    transcript = _full_transcript(session, include_partials=True)
    candidate_chars = _candidate_chars(session, include_partials=True)
    segments = session.get("segments") or []
    is_partial_window = _has_candidate_partial(session)
    previous_disc = session.get("rolling_disc_analysis") or {}
    disc_output = {
        "ready": False,
        "status": "collecting",
        "updated_at": int(time.time() * 1000),
        "window_segment_count": len(segments),
        "window_candidate_chars": candidate_chars,
        "dominant_style": "",
        "secondary_style": "",
        "scores": {"D": 0, "I": 0, "S": 0, "C": 0},
        "confidence": "low",
        "summary": "Waiting for more candidate content before generating a realtime DISC trend.",
        "display_strengths": [],
        "watchouts": [],
        "recommended_roles": previous_disc.get("recommended_roles") or [],
        "role_reason": str(previous_disc.get("role_reason") or ""),
        "follow_up_hint": "Wait for more candidate content.",
        "source": "local_rules",
        "llm_model": str(previous_disc.get("llm_model") or ""),
        "is_partial_window": is_partial_window,
    }
    if candidate_chars < 20:
        session["rolling_disc_analysis"] = disc_output
        return disc_output

    local_result = run_local_workflow(transcript, session.get("job_hint", ""))
    disc_result = local_result.get("disc_analysis") or {}
    raw_scores = disc_result.get("scores") or {key: 0 for key in _DISC_KEYS}
    smooth_scores = _smoothed_scores(raw_scores, previous_disc.get("scores") or {})
    ranking = _rank_scores(smooth_scores)
    dominant = ranking[0] if ranking else ""
    secondary = ranking[1] if len(ranking) > 1 else ""
    signature = f"{dominant}:{secondary}"
    meta = disc_result.get("meta") or {}
    confidence = str(meta.get("confidence") or previous_disc.get("confidence") or "medium")
    strengths = []
    for dim in ranking[:2]:
        item = (disc_result.get("dimension_analysis") or {}).get(dim) or {}
        if item.get("summary"):
            strengths.append(str(item.get("summary")))

    previous_signature = f"{previous_disc.get('dominant_style') or ''}:{previous_disc.get('secondary_style') or ''}"
    if signature == previous_signature and previous_disc.get("recommended_roles"):
        recommended_roles = list(previous_disc.get("recommended_roles") or [])[:4]
        role_reason = str(previous_disc.get("role_reason") or "")
    else:
        recommended_roles = _local_roles(dominant, secondary)
        role_reason = _local_role_reason(dominant, secondary)

    disc_output.update({
        "ready": True,
        "status": "ready",
        "dominant_style": dominant,
        "secondary_style": secondary,
        "scores": smooth_scores,
        "score_deltas": _compute_score_deltas(smooth_scores, previous_disc.get("scores") or {}),
        "confidence": confidence,
        "summary": _local_summary(dominant, secondary, confidence, is_partial_window),
        "display_strengths": strengths[:2],
        "watchouts": list(disc_result.get("evidence_gaps") or [])[:2],
        "recommended_roles": recommended_roles,
        "role_reason": role_reason,
        "follow_up_hint": _local_followup_hint(dominant),
        "source": "local_rules",
        "is_partial_window": is_partial_window,
    })

    if _should_call_llm(session, signature):
        try:
            llm_result = call_openai_compatible(
                config.OPENAI_REALTIME_DISC_MODEL,
                _build_llm_messages(transcript, disc_result, session.get("job_hint", "")),
            ) or {}
            disc_output["summary"] = str(llm_result.get("summary") or disc_output["summary"])
            disc_output["confidence"] = str(llm_result.get("confidence") or disc_output["confidence"])
            disc_output["display_strengths"] = list(llm_result.get("display_strengths") or disc_output["display_strengths"])[:2]
            disc_output["watchouts"] = list(llm_result.get("watchouts") or disc_output["watchouts"])[:2]
            disc_output["recommended_roles"] = list(llm_result.get("recommended_roles") or disc_output["recommended_roles"])[:4]
            disc_output["role_reason"] = str(llm_result.get("role_reason") or disc_output["role_reason"])
            disc_output["follow_up_hint"] = str(llm_result.get("follow_up_hint") or disc_output["follow_up_hint"])
            disc_output["source"] = "local_plus_llm"
            disc_output["llm_model"] = config.OPENAI_REALTIME_DISC_MODEL
            session["last_disc_llm_at"] = time.time()
            session["last_disc_llm_signature"] = signature
        except Exception as exc:
            logger.warning("[realtime_disc] lightweight model failed: %s", exc)

    session["rolling_disc_analysis"] = disc_output
    session["last_disc_analysis_at"] = time.time()
    session["last_disc_analysis_segment_count"] = len(segments)
    session["last_disc_analysis_candidate_chars"] = candidate_chars
    return disc_output
