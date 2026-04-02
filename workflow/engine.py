from __future__ import annotations

import logging
import time

import app.config as config

from app.knowledge import (
    load_bigfive_knowledge,
    load_bigfive_prompt,
    load_disc_knowledge,
    load_disc_prompt,
    load_enneagram_knowledge,
    load_enneagram_prompt,
    load_mbti_knowledge,
)

from .context import WorkflowContext
from .helpers import build_bigfive_messages, build_enneagram_messages, call_openai_compatible
from .stages.bigfive_stage import run_bigfive_stage
from .stages.decision_stage import run_decision_stage
from .stages.disc_evidence_stage import run_disc_evidence_stage
from .stages.disc_stage import run_disc_stage
from .stages.enneagram_stage import run_enneagram_stage
from .stages.feature_stage import run_feature_stage
from .stages.llm_stage import run_llm_stage
from .stages.masking_stage import run_masking_stage
from .stages.mbti_stage import run_mbti_stage
from .stages.parse_stage import run_parse_stage
from .stages.personality_mapping_stage import run_personality_mapping_stage
from .stages.star_stage import run_star_stage

logger = logging.getLogger("insighteye.workflow")


def _current_mbti(context: WorkflowContext) -> dict:
    return context.mbti_result or context.mbti_analysis or {}


def _print_followups(context: WorkflowContext) -> None:
    pass  # 实时追问已迁移至 LLM 生成，此处不再打印本地规则追问


def build_response(context: WorkflowContext, *, mode: str) -> dict:
    _print_followups(context)
    return {
        "input_overview": {
            "segment_count": len(context.segments),
            "turn_count": len(context.detailed_turns),
            "candidate_char_count": context.features.get("text_length", 0),
        },
        "interview_map": {
            "job_inference": context.job_inference,
            "segments": context.segments,
            "turns": context.detailed_turns,
            "parse_source": context.parse_source,
        },
        "atomic_features": context.features,
        "disc_analysis": context.disc_analysis,
        "mbti_analysis": _current_mbti(context),
        "star_analysis": context.star_result,
        "bigfive_analysis": context.bigfive_result,
        "enneagram_analysis": context.enneagram_result,
        "personality_mapping": context.personality_mapping_result,
        "llm_analysis": context.analysis_output,
        "llm_bigfive_analysis": context.llm_bigfive_output,
        "llm_enneagram_analysis": context.llm_enneagram_output,
        "llm_status": {
            "enabled": context.llm_called,
            "api_enabled": bool(config.OPENAI_API_KEY),
            "parser_model": config.OPENAI_PARSER_MODEL or None,
            "analysis_model": config.OPENAI_ANALYSIS_MODEL or None,
            "personality_model": config.OPENAI_PERSONALITY_MODEL if config.OPENAI_API_KEY else None,
            "parser_error": context.parser_error,
            "analysis_error": context.analysis_error,
            "parser_output_available": context.parser_output is not None,
        },
        "workflow": {
            "version": "v0.5",
            "mode": mode,
            "stage_trace": context.stage_trace,
            "disc_evidence": context.disc_evidence,
            "masking_assessment": context.masking_assessment,
            "decision_payload": context.decision_payload,
        },
    }


def _base_context(transcript: str, job_hint: str = "") -> WorkflowContext:
    return WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=load_disc_knowledge(),
        mbti_knowledge=load_mbti_knowledge(),
    )


def _run_core_local_stages(context: WorkflowContext) -> WorkflowContext:
    for stage in (
        run_parse_stage,
        run_feature_stage,
        run_star_stage,
        run_disc_evidence_stage,
        run_mbti_stage,
        run_masking_stage,
        run_disc_stage,
        run_decision_stage,
    ):
        context = stage(context)
    return context


def run_local_workflow(transcript: str, job_hint: str = "") -> dict:
    context = _base_context(transcript, job_hint)
    original_api_key = config.OPENAI_API_KEY
    original_parser_model = config.OPENAI_PARSER_MODEL
    original_analysis_model = config.OPENAI_ANALYSIS_MODEL
    try:
        config.OPENAI_API_KEY = None
        config.OPENAI_PARSER_MODEL = None
        config.OPENAI_ANALYSIS_MODEL = None
        context = _run_core_local_stages(context)
        return build_response(context, mode="quick_local")
    finally:
        config.OPENAI_API_KEY = original_api_key
        config.OPENAI_PARSER_MODEL = original_parser_model
        config.OPENAI_ANALYSIS_MODEL = original_analysis_model


def run_disc_workflow(transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True) -> dict:
    del apply_knowledge_graph
    context = _base_context(transcript, job_hint)
    context = _run_core_local_stages(context)
    context = run_llm_stage(context, disc_prompt=load_disc_prompt())
    return build_response(context, mode="disc_mbti")


def _run_llm_personality_stage(context: WorkflowContext) -> WorkflowContext:
    logger.info("[人格LLM阶段] ===== 开始 LLM 人格分析 (BigFive + Enneagram) =====")
    _personality_start = time.perf_counter()

    if not config.OPENAI_API_KEY:
        logger.warning("[人格LLM阶段] OPENAI_API_KEY 未配置，跳过人格 LLM 分析")
        context.mark_stage("llm_personality_stage", "skipped", "OPENAI_API_KEY not configured")
        return context

    context.mark_stage("llm_personality_stage", "started", "Run optional LLM Big Five and Enneagram analysis")

    try:
        _bf_start = time.perf_counter()
        context.llm_bigfive_output = call_openai_compatible(
            config.OPENAI_PERSONALITY_MODEL,
            build_bigfive_messages(
                prompt=load_bigfive_prompt(),
                transcript=context.transcript,
                turns=context.detailed_turns,
                features=context.features,
                job_inference=context.job_inference,
                local_bigfive=context.bigfive_result,
            ),
        ) or {}
        _bf_elapsed = (time.perf_counter() - _bf_start) * 1000
        context.llm_called = True
        logger.info(f"[人格LLM阶段] BigFive LLM 调用完成 | 耗时: {_bf_elapsed:.0f}ms")
    except Exception as exc:
        _bf_elapsed = (time.perf_counter() - _bf_start) * 1000
        context.mark_stage("llm_personality_stage", "failed", f"BigFive LLM failed: {exc}")
        logger.error(f"[人格LLM阶段] BigFive LLM 调用失败 | 耗时: {_bf_elapsed:.0f}ms | 错误: {exc}")

    try:
        _en_start = time.perf_counter()
        context.llm_enneagram_output = call_openai_compatible(
            config.OPENAI_PERSONALITY_MODEL,
            build_enneagram_messages(
                prompt=load_enneagram_prompt(),
                transcript=context.transcript,
                turns=context.detailed_turns,
                features=context.features,
                job_inference=context.job_inference,
                local_enneagram=context.enneagram_result,
            ),
        ) or {}
        _en_elapsed = (time.perf_counter() - _en_start) * 1000
        context.llm_called = True
        logger.info(f"[人格LLM阶段] Enneagram LLM 调用完成 | 耗时: {_en_elapsed:.0f}ms")
    except Exception as exc:
        _en_elapsed = (time.perf_counter() - _en_start) * 1000
        context.mark_stage("llm_personality_stage", "failed", f"Enneagram LLM failed: {exc}")
        logger.error(f"[人格LLM阶段] Enneagram LLM 调用失败 | 耗时: {_en_elapsed:.0f}ms | 错误: {exc}")

    _personality_total = (time.perf_counter() - _personality_start) * 1000
    if context.llm_bigfive_output or context.llm_enneagram_output:
        context.mark_stage("llm_personality_stage", "completed", "LLM personality analysis ready")
        logger.info(f"[人格LLM阶段] ===== LLM 人格分析完成 ===== 总耗时: {_personality_total:.0f}ms")
    return context


def run_personality_workflow(transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True) -> dict:
    del apply_knowledge_graph
    context = _base_context(transcript, job_hint)
    context = _run_core_local_stages(context)

    context.knowledge = load_bigfive_knowledge()
    context = run_bigfive_stage(context)
    context.knowledge = load_enneagram_knowledge()
    context = run_enneagram_stage(context)
    context.knowledge = load_disc_knowledge()
    context = run_personality_mapping_stage(context)
    context = run_llm_stage(context, disc_prompt=load_disc_prompt())
    context = _run_llm_personality_stage(context)
    return build_response(context, mode="full_personality")


def should_trigger_llm(local_result: dict) -> tuple[bool, str]:
    logger.info("[LLM触发决策] ===== 开始判断是否触发 LLM =====")
    if not local_result:
        logger.info("[LLM触发决策] 本地分析结果为空，决定触发 LLM")
        return True, "Local analysis result is empty"

    reasons: list[str] = []
    input_overview = local_result.get("input_overview") or {}
    candidate_chars = input_overview.get("candidate_char_count", 0)
    turn_count = input_overview.get("turn_count", 0)
    logger.info(f"[LLM触发决策] 候选字符数: {candidate_chars}, 轮次数: {turn_count}")

    if candidate_chars < 300:
        reasons.append("Candidate sample is too short")
        logger.info(f"[LLM触发决策] 样本过短: {candidate_chars} < 300")
    if turn_count < 3:
        reasons.append("Too few interview turns")
        logger.info(f"[LLM触发决策] 轮次过少: {turn_count} < 3")

    disc_analysis = local_result.get("disc_analysis") or {}
    disc_scores = disc_analysis.get("scores") or {}
    if disc_scores:
        try:
            max_disc = max(disc_scores.values())
            logger.info(f"[LLM触发决策] DISC 最高分: {max_disc}")
            if max_disc < 60:
                reasons.append("DISC dominant style is not clear enough")
                logger.info(f"[LLM触发决策] DISC 主风格不清晰: 最高分 {max_disc} < 60")
        except (TypeError, ValueError):
            reasons.append("DISC scores are malformed")

    mbti_analysis = local_result.get("mbti_analysis") or {}
    dimensions = mbti_analysis.get("dimensions") or {}
    neutral_count = sum(
        1
        for item in dimensions.values()
        if isinstance(item, dict) and item.get("preference") in {"neutral", "unclear"}
    ) if isinstance(dimensions, dict) else 0
    if neutral_count >= 2:
        reasons.append("MBTI evidence is still ambiguous")
        logger.info(f"[LLM触发决策] MBTI 不确定维度数: {neutral_count} >= 2")
    if any(isinstance(item, dict) and item.get("severity") == "high" for item in (mbti_analysis.get("conflicts") or [])):
        reasons.append("High-severity personality conflict detected")
        logger.info(f"[LLM触发决策] 检测到高严重度人格冲突")

    star_analysis = local_result.get("star_analysis") or {}
    high_star_defects = [
        item
        for item in (star_analysis.get("defects") or [])
        if isinstance(item, dict) and item.get("severity") == "high"
    ]
    if high_star_defects:
        reasons.append("STAR authenticity has high-severity defects")
        logger.info(f"[LLM触发决策] STAR 高严重度缺陷数: {len(high_star_defects)}")

    risk = str((disc_analysis.get("meta") or {}).get("impression_management_risk", "")).lower()
    if any(token in risk for token in ("high", "?")):
        reasons.append("Impression-management risk is high")
        logger.info(f"[LLM触发决策] 印象管理风险: {risk}")

    if reasons:
        reason_str = " | ".join(reasons)
        logger.info(f"[LLM触发决策] 决定触发 LLM | 原因: {reason_str}")
        return True, reason_str
    logger.info(f"[LLM触发决策] 本地证据已足够稳定，跳过 LLM")
    return False, "Local evidence is already stable enough"


def run_llm_only(context: WorkflowContext, disc_prompt: str) -> WorkflowContext:
    return run_llm_stage(context, disc_prompt=disc_prompt)
