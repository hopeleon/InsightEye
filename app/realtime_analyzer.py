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


def _normalize_realtime_followup(
    item: dict | str,
    *,
    source: str,
    source_label: str,
    default_priority: str,
    default_purpose: str,
) -> dict | None:
    if isinstance(item, str):
        question = item.strip()
        raw: dict = {}
    elif isinstance(item, dict):
        question = str(item.get("question") or "").strip()
        raw = item
    else:
        return None

    if not question:
        return None

    purpose = str(raw.get("purpose") or default_purpose).strip() or default_purpose
    dimension = str(
        raw.get("target_dimension")
        or raw.get("dimension")
        or raw.get("defect_id")
        or raw.get("label")
        or ""
    ).strip()
    priority = str(raw.get("priority") or default_priority).strip().lower() or default_priority
    if priority not in {"high", "medium", "low"}:
        priority = default_priority

    return {
        "source": source,
        "source_label": source_label,
        "priority": priority,
        "dimension": dimension,
        "question": question,
        "purpose": purpose,
    }


def _collect_realtime_followups(local_result: dict) -> list[dict]:
    disc_analysis = local_result.get("disc_analysis") or {}
    mbti_analysis = local_result.get("mbti_analysis") or {}
    star_analysis = local_result.get("star_analysis") or {}

    candidates: list[dict] = []
    for item in disc_analysis.get("follow_up_questions") or []:
        normalized = _normalize_realtime_followup(
            item,
            source="disc",
            source_label="DISC",
            default_priority="high",
            default_purpose="验证当前 DISC 判断是否成立。",
        )
        if normalized:
            candidates.append(normalized)

    for item in mbti_analysis.get("follow_up_questions") or []:
        normalized = _normalize_realtime_followup(
            item,
            source="mbti",
            source_label="MBTI",
            default_priority="medium",
            default_purpose="确认当前 MBTI 维度偏好是否稳定。",
        )
        if normalized:
            candidates.append(normalized)

    for item in star_analysis.get("followup_questions") or []:
        normalized = _normalize_realtime_followup(
            item,
            source="star",
            source_label="STAR",
            default_priority="high",
            default_purpose="补足 STAR 结构证据，验证经历真实性。",
        )
        if normalized:
            candidates.append(normalized)

    priority_rank = {"high": 0, "medium": 1, "low": 2}
    source_rank = {"disc": 0, "star": 1, "mbti": 2}
    deduped: list[dict] = []
    seen_questions: set[str] = set()
    for item in sorted(
        candidates,
        key=lambda current: (
            priority_rank.get(current["priority"], 9),
            source_rank.get(current["source"], 9),
        ),
    ):
        dedupe_key = item["question"].strip().lower()
        if dedupe_key in seen_questions:
            continue
        seen_questions.add(dedupe_key)
        deduped.append(item)
        if len(deduped) >= 5:
            break
    return deduped


def run_rolling_analysis(session: dict) -> dict:
    segments = session.get("segments") or []
    role_state = infer_roles(segments)
    transcript = build_realtime_transcript(segments, role_state)
    local_result = run_local_workflow(transcript, session.get("job_hint", ""))

    disc_analysis = local_result.get("disc_analysis") or {}
    mbti_analysis = local_result.get("mbti_analysis") or {}
    followups = _collect_realtime_followups(local_result)

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
        "follow_up_questions": followups,
        "recommended_action": disc_analysis.get("recommended_action", ""),
        "mbti_type": mbti_analysis.get("type", ""),
        "mbti_summary": mbti_analysis.get("type_description", ""),
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
