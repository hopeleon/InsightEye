from __future__ import annotations

from app.config import (
    OPENAI_ANALYSIS_MODEL,
    OPENAI_API_KEY,
    OPENAI_PARSER_MODEL,
    OPENAI_PERSONALITY_MODEL,
)
from app.knowledge import (
    load_bigfive_knowledge,
    load_bigfive_prompt,
    load_disc_knowledge,
    load_disc_prompt,
    load_enneagram_knowledge,
    load_enneagram_prompt,
    load_industry_knowledge,
    load_star_knowledge,
)
from app.star_analyzer import analyze_star

from .context import WorkflowContext
from .helpers import (
    build_bigfive_messages,
    build_disc_messages,
    build_enneagram_messages,
    call_openai_compatible,
)
from .stages.bigfive_stage import run_bigfive_stage
from .stages.decision_stage import run_decision_stage
from .stages.disc_evidence_stage import run_disc_evidence_stage
from .stages.disc_stage import run_disc_stage
from .stages.feature_stage import run_feature_stage
from .stages.llm_stage import run_llm_stage
from .stages.masking_stage import run_masking_stage
from .stages.parse_stage import run_parse_stage
from .stages.personality_mapping_stage import run_personality_mapping_stage
from .stages.enneagram_stage import run_enneagram_stage
from .stages.star_stage import run_star_stage


def _star_dimension_scores_usable(ds: object) -> bool:
    if not isinstance(ds, dict) or not ds:
        return False
    return any(k in ds for k in ("S", "T", "A", "R"))


def _coalesce_star_analysis(context: WorkflowContext) -> dict | None:
    """\u786e\u4fdd JSON \u4e2d star_analysis \u5e26\u6709\u53ef\u5c55\u793a\u7684 dimension_scores\uff08\u5bb9\u9519 / \u65e7\u7f13\u5b58\u573a\u666f\uff09\u3002"""
    star = context.star_result
    if isinstance(star, dict) and _star_dimension_scores_usable(star.get("dimension_scores")):
        return star
    try:
        return analyze_star(
            context.transcript,
            context.detailed_turns,
            context.features,
            load_star_knowledge(),
        )
    except Exception:
        return star if isinstance(star, dict) else None


def build_response(context: WorkflowContext) -> dict:
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
        "star_analysis": _coalesce_star_analysis(context),
        "bigfive_analysis": context.bigfive_result,
        "enneagram_analysis": context.enneagram_result,
        "personality_mapping": context.personality_mapping_result,
        "llm_analysis": context.analysis_output,
        "llm_bigfive_analysis": context.llm_bigfive_output,
        "llm_enneagram_analysis": context.llm_enneagram_output,
        "llm_status": {
            "enabled": bool(OPENAI_API_KEY),
            "parser_model": OPENAI_PARSER_MODEL,
            "analysis_model": OPENAI_ANALYSIS_MODEL,
            "personality_model": OPENAI_PERSONALITY_MODEL if OPENAI_API_KEY else None,
            "parser_error": getattr(context, "parser_error", None),
            "analysis_error": getattr(context, "analysis_error", None),
            "parser_output_available": context.parser_output is not None,
        },
        "workflow": {
            "version": "v0.3",
            "mode": "disc_with_personality",
            "stage_trace": context.stage_trace,
            "disc_evidence": context.disc_evidence,
            "masking_assessment": context.masking_assessment,
            "decision_payload": context.decision_payload,
        },
    }


def _inject_industry_context(context: WorkflowContext) -> WorkflowContext:
    """在工作流早期注入行业上下文（供特征提取和分析引擎使用）。"""
    from app.knowledge import detect_industry, detect_job_family, load_job_competencies
    industry = detect_industry(context.job_hint, context.transcript)
    ind_knowledge = load_industry_knowledge(industry) if industry else None
    job_family = detect_job_family(context.job_hint)
    jc = load_job_competencies()
    family_info = jc.get("job_families", {}).get(job_family) or jc.get("job_families", {}).get("default") or {}
    context.industry_context = {
        "industry": industry,
        "job_family": job_family,
        "job_family_label": family_info.get("label", "通用岗位"),
        "disc_to_competency": jc.get("disc_to_competency", {}),
        "industry_benchmarks": (ind_knowledge or {}).get("job_benchmarks", {}),
        "analysis_priorities": (ind_knowledge or {}).get("analysis_priorities", {}),
    }
    context.industry_knowledge = ind_knowledge or {}
    return context


def run_disc_workflow(transcript: str, job_hint: str = "") -> dict:
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=load_disc_knowledge(),
    )
    context = _inject_industry_context(context)
    disc_prompt = load_disc_prompt()

    for stage in (
        run_parse_stage,
        run_feature_stage,
        run_star_stage,
        run_disc_evidence_stage,
        run_masking_stage,
        run_disc_stage,
        run_decision_stage,
    ):
        context = stage(context)

    context = run_llm_stage(context, disc_prompt=disc_prompt)
    return build_response(context)


def run_personality_workflow(transcript: str, job_hint: str = "") -> dict:
    """完整人格分析工作流：DISC + BigFive + 九型 + 跨模型映射。"""
    disc_knowledge = load_disc_knowledge()
    bigfive_knowledge = load_bigfive_knowledge()
    enneagram_knowledge = load_enneagram_knowledge()
    disc_prompt = load_disc_prompt()
    bigfive_prompt = load_bigfive_prompt()
    enneagram_prompt = load_enneagram_prompt()

    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=disc_knowledge,
    )
    context = _inject_industry_context(context)

    for stage in (run_parse_stage, run_feature_stage):
        context = stage(context)

    context.disc_evidence = {}
    for stage in (
        run_star_stage,
        run_disc_evidence_stage,
        run_masking_stage,
        run_disc_stage,
        run_decision_stage,
    ):
        context = stage(context)

    context.knowledge = bigfive_knowledge
    context = run_bigfive_stage(context)

    context.knowledge = enneagram_knowledge
    context = run_enneagram_stage(context)

    context = run_personality_mapping_stage(context)
    context = run_llm_stage(context, disc_prompt=disc_prompt)

    if OPENAI_API_KEY:
        context = _run_llm_personality_stage(context, bigfive_prompt, enneagram_prompt)

    return build_response(context)


def _run_llm_personality_stage(context: WorkflowContext, bigfive_prompt: str, enneagram_prompt: str) -> WorkflowContext:
    context.mark_stage("llm_personality_stage", "started", "Run optional LLM Big Five and Enneagram analysis")
    try:
        bf_msgs = build_bigfive_messages(
            prompt=bigfive_prompt,
            transcript=context.transcript,
            turns=context.detailed_turns,
            features=context.features,
            job_inference=context.job_inference,
            local_bigfive=context.bigfive_result,
        )
        context.llm_bigfive_output = call_openai_compatible(OPENAI_PERSONALITY_MODEL, bf_msgs)
        context.mark_stage("llm_personality_stage", "completed", "LLM Big Five analysis done")
    except Exception as exc:
        context.mark_stage("llm_personality_stage", "failed", str(exc))

    try:
        en_msgs = build_enneagram_messages(
            prompt=enneagram_prompt,
            transcript=context.transcript,
            turns=context.detailed_turns,
            features=context.features,
            job_inference=context.job_inference,
            local_enneagram=context.enneagram_result,
        )
        context.llm_enneagram_output = call_openai_compatible(OPENAI_PERSONALITY_MODEL, en_msgs)
        context.mark_stage("llm_personality_stage", "completed", "LLM Enneagram analysis done")
    except Exception as exc:
        context.mark_stage("llm_personality_stage", "failed", str(exc))

    return context
