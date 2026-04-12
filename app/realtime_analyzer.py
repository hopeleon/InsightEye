from __future__ import annotations

import logging
import time
from typing import Any

import app.config as config
from .analysis import analyze_interview_full
from workflow.engine import run_local_workflow
from workflow.helpers import build_llm_followup_messages, call_openai_compatible

logger = logging.getLogger("insighteye.realtime_analyzer")


def build_realtime_transcript(segments: list[dict], voice_mapping: dict | None = None) -> str:
    """
    构建实时转录文本

    Args:
        segments: 片段列表
        voice_mapping: 声纹映射 {"interviewer": "speaker_a", "candidate": "speaker_b"}

    Returns:
        格式化后的转录文本
    """
    # voice_mapping: {"interviewer": "speaker_a", "candidate": "speaker_b"}
    # 需要反向映射: {"speaker_a": "interviewer", "speaker_b": "candidate"}
    reverse_voice: dict[str, str] = {}
    if voice_mapping:
        reverse_voice = {v: k for k, v in voice_mapping.items()}

    lines: list[str] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        speaker_id = str(segment.get("speaker_id") or "").strip() or "speaker_a"

        # 角色分配优先级：recognized_role > voice_mapping > speaker_a/speaker_b
        role = segment.get("recognized_role")
        if not role:
            role = reverse_voice.get(speaker_id)

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

    # 从声纹映射推导 candidate speaker_id
    voice_mapping = session.get("voice_mapping") or {}
    reverse_map = {v: k for k, v in voice_mapping.items()}  # {"speaker_a": "interviewer", "speaker_b": "candidate"}
    last_chars = int(session.get("last_analysis_candidate_chars", 0))
    current_chars = 0
    for segment in current_segments:
        if reverse_map.get(segment.get("speaker_id")) == "candidate":
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


def generate_llm_followups(
    transcript: str,
    disc_result: dict,
    mbti_result: dict,
    star_result: dict,
    job_hint: str,
) -> list[dict]:
    """
    Call LLM to generate high-quality follow-up questions targeting evidence gaps
    and ambiguous dimensions identified by local rules.
    Returns a list of normalized follow-up dicts, or empty list on failure.
    """
    _llm_start = time.perf_counter()
    logger.info("[实时分析] 开始调用 LLM 生成追问...")
    try:
        messages = build_llm_followup_messages(
            transcript=transcript,
            disc_result=disc_result,
            mbti_result=mbti_result,
            star_result=star_result,
            job_hint=job_hint,
        )
        _build_elapsed = (time.perf_counter() - _llm_start) * 1000
        logger.info(f"[实时分析] LLM prompt 构建完成，耗时 {_build_elapsed:.2f}ms，消息数: {len(messages)}")

        if not config.OPENAI_API_KEY:
            logger.warning("[实时分析] OPENAI_API_KEY 未配置，无法调用 LLM")
            return []

        result = call_openai_compatible(config.OPENAI_ANALYSIS_MODEL, messages)
        if not result:
            logger.warning("[实时分析] LLM 调用返回空结果")
            return []

        questions = result.get("follow_up_questions") or result.get("questions") or []
        followups = []
        for q in questions:
            normalized = _normalize_realtime_followup(
                q,
                source="llm",
                source_label="LLM追问",
                default_priority="high",
                default_purpose="基于当前面试内容深度分析生成",
            )
            if normalized:
                followups.append(normalized)
                logger.info(f"[实时分析] LLM 追问: [{normalized['source_label']}] {normalized['question'][:60]}")

        _elapsed = time.perf_counter() - _llm_start
        logger.info(f"[实时分析] LLM 追问生成完成，共 {len(followups)} 条，耗时 {_elapsed * 1000:.2f}ms")
        return followups
    except Exception as exc:
        _elapsed = time.perf_counter() - _llm_start
        logger.warning(f"[实时分析] LLM 追问生成失败，耗时 {_elapsed * 1000:.2f}ms: {exc}")
        return []


def run_rolling_analysis(session: dict) -> dict:
    logger.info("[实时分析] ===== 开始滚动分析 =====")
    _total_start = time.perf_counter()

    segments = session.get("segments") or []
    _seg_count = len(segments)
    logger.info(f"[实时分析] 当前片段数量: {_seg_count}")

    # 获取声纹映射和发言顺序角色推断
    voice_mapping = session.get("voice_mapping", {})
    transcript = build_realtime_transcript(segments, voice_mapping)
    logger.info(f"[实时分析] 转录文本构建完成，长度: {len(transcript)} 字符")

    _local_start = time.perf_counter()
    local_result = run_local_workflow(transcript, session.get("job_hint", ""))
    _local_elapsed = (time.perf_counter() - _local_start) * 1000
    logger.info(f"[实时分析] 本地规则分析完成，耗时 {_local_elapsed:.2f}ms")

    disc_analysis = local_result.get("disc_analysis") or {}
    mbti_analysis = local_result.get("mbti_analysis") or {}
    star_analysis = local_result.get("star_analysis") or {}

    disc_type = disc_analysis.get("ranking", [""])[0] + disc_analysis.get("ranking", ["", ""])[1]
    mbti_type = mbti_analysis.get("type", "unknown")
    logger.info(f"[实时分析] 本地分析结果 - DISC: {disc_type}, MBTI: {mbti_type}")
    logger.info(
        f"[实时分析] API Key 状态: {'已配置' if config.OPENAI_API_KEY else '未配置'}, "
        f"模型: {config.OPENAI_ANALYSIS_MODEL}"
    )

    _llm_fuq_start = time.perf_counter()
    followups = generate_llm_followups(
        transcript=transcript,
        disc_result=disc_analysis,
        mbti_result=mbti_analysis,
        star_result=star_analysis,
        job_hint=session.get("job_hint", ""),
    )
    _llm_fuq_elapsed = (time.perf_counter() - _llm_fuq_start) * 1000
    logger.info(
        f"[实时分析] LLM 追问生成完成: {len(followups)} 条, 耗时 {_llm_fuq_elapsed:.2f}ms"
    )

    # 从声纹映射推导 candidate 字符数
    reverse_map = {v: k for k, v in voice_mapping.items()}
    candidate_chars = sum(
        len(str(segment.get("text") or ""))
        for segment in segments
        if reverse_map.get(segment.get("speaker_id")) == "candidate"
    )

    snapshot = {
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
    session["rolling_analysis"] = snapshot
    session["last_analysis_segment_count"] = len(segments)
    session["last_analysis_candidate_chars"] = candidate_chars

    _total_elapsed = (time.perf_counter() - _total_start) * 1000
    logger.info(f"[实时分析] ===== 滚动分析完成 ===== 总耗时 {_total_elapsed:.2f}ms, 候选字符数: {candidate_chars}")
    return snapshot


def run_final_analysis(session: dict) -> dict:
    logger.info("[实时分析] ===== 开始最终分析 =====")
    _final_start = time.perf_counter()
    
    voice_mapping = session.get("voice_mapping", {})

    transcript = build_realtime_transcript(
        session.get("segments") or [],
        voice_mapping
    )
    result = analyze_interview_full(transcript, session.get("job_hint", ""))
    _final_elapsed = time.perf_counter() - _final_start
    logger.info(f"[实时分析] ===== 最终分析完成 ===== 耗时 {_final_elapsed * 1000:.2f}ms")
    return result
