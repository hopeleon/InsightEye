from __future__ import annotations

from .analysis import analyze_interview_full
from .role_inference import infer_roles
from workflow.engine import run_local_workflow


def build_realtime_transcript(segments: list[dict], role_state: dict | None = None) -> str:
    mapping = (role_state or {}).get("mapping") or {}
    lines: list[str] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        speaker_id = str(segment.get("speaker_id") or "").strip() or "speaker_a"
        role = mapping.get(speaker_id)
        if role == "interviewer":
            label = "面试官"
        elif role == "candidate":
            label = "候选人"
        elif speaker_id == "speaker_a":
            label = "说话人A"
        elif speaker_id == "speaker_b":
            label = "说话人B"
        else:
            label = speaker_id
        lines.append(f"{label}：{text}")
    return "\n".join(lines)


def should_refresh_analysis(session: dict, *, min_new_segments: int = 2, min_new_candidate_chars: int = 80) -> bool:
    last_count = int(session.get("last_analysis_segment_count", 0))
    current_segments = session.get("segments") or []
    if len(current_segments) - last_count >= min_new_segments:
        return True

    role_map = ((session.get("role_inference") or {}).get("mapping") or {})
    last_chars = int(session.get("last_analysis_candidate_chars", 0))
    current_chars = 0
    for segment in current_segments:
        if role_map.get(segment.get("speaker_id")) == "candidate":
            current_chars += len(str(segment.get("text") or ""))
    return current_chars - last_chars >= min_new_candidate_chars


def run_rolling_analysis(session: dict) -> dict:
    segments = session.get("segments") or []
    role_state = infer_roles(segments)
    transcript = build_realtime_transcript(segments, role_state)
    local_result = run_local_workflow(transcript, session.get("job_hint", ""))

    disc_analysis = local_result.get("disc_analysis") or {}
    star_analysis = local_result.get("star_analysis") or {}
    followups = list(disc_analysis.get("follow_up_questions") or [])
    for item in star_analysis.get("followup_questions") or []:
        if len(followups) >= 4:
            break
        followups.append(item)

    candidate_chars = sum(
        len(str(segment.get("text") or ""))
        for segment in segments
        if (role_state.get("mapping") or {}).get(segment.get("speaker_id")) == "candidate"
    )

    snapshot = {
        "role_inference": role_state,
        "transcript": transcript,
        "summary": disc_analysis.get("decision_summary", ""),
        "risk_summary": disc_analysis.get("risk_summary", ""),
        "evidence_gaps": list(disc_analysis.get("evidence_gaps") or [])[:4],
        "follow_up_questions": followups[:4],
        "recommended_action": disc_analysis.get("recommended_action", ""),
        "local_result": local_result,
        "segment_count": len(segments),
        "candidate_char_count": candidate_chars,
    }
    session["role_inference"] = role_state
    session["rolling_analysis"] = snapshot
    session["last_analysis_segment_count"] = len(segments)
    session["last_analysis_candidate_chars"] = candidate_chars
    return snapshot


def run_final_analysis(session: dict) -> dict:
    transcript = build_realtime_transcript(session.get("segments") or [], session.get("role_inference") or {})
    return analyze_interview_full(transcript, session.get("job_hint", ""))
