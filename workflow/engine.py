from __future__ import annotations

from app.config import OPENAI_ANALYSIS_MODEL, OPENAI_API_KEY, OPENAI_PARSER_MODEL
from app.knowledge import load_disc_knowledge, load_disc_prompt, load_mbti_knowledge  # 新增

from .context import WorkflowContext
from .stages.decision_stage import run_decision_stage
from .stages.disc_evidence_stage import run_disc_evidence_stage
from .stages.feature_stage import run_feature_stage
from .stages.llm_stage import run_llm_stage
from .stages.masking_stage import run_masking_stage
from .stages.parse_stage import run_parse_stage
from .stages.mbti_stage import run_mbti_stage  # 新增


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
        "mbti_analysis": context.mbti_analysis,  # 新增
        "llm_analysis": context.analysis_output,
        "llm_status": {
            "enabled": bool(OPENAI_API_KEY),
            "parser_model": OPENAI_PARSER_MODEL,
            "analysis_model": OPENAI_ANALYSIS_MODEL,
            "parser_error": context.parser_error,
            "analysis_error": context.analysis_error,
            "parser_output_available": context.parser_output is not None,
        },
        "workflow": {
            "version": "v0.3",  # 版本号升级
            "mode": "disc+mbti",  # 模式更新
            "stage_trace": context.stage_trace,
            "disc_evidence": context.disc_evidence,
            "masking_assessment": context.masking_assessment,
            "decision_payload": context.decision_payload,
        },
    }


def run_disc_workflow(transcript: str, job_hint: str = "") -> dict:
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=load_disc_knowledge(),
        mbti_knowledge=load_mbti_knowledge(),  # 新增
    )
    disc_prompt = load_disc_prompt()

    for stage in (
        run_parse_stage,
        run_feature_stage,
        run_disc_evidence_stage,
        run_mbti_stage,  # 新增：在 masking 之前运行
        run_masking_stage,
        run_decision_stage,
    ):
        context = stage(context)

    context = run_llm_stage(context, disc_prompt=disc_prompt)
    return build_response(context)