from __future__ import annotations

from app.config import OPENAI_ANALYSIS_MODEL, OPENAI_API_KEY, OPENAI_PARSER_MODEL
from app.knowledge import load_disc_knowledge, load_disc_prompt

from .context import WorkflowContext
from .stages.decision_stage import run_decision_stage
from .stages.disc_evidence_stage import run_disc_evidence_stage
from .stages.feature_stage import run_feature_stage
from .stages.llm_stage import run_llm_stage
from .stages.masking_stage import run_masking_stage
from .stages.parse_stage import run_parse_stage


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
            "version": "v0.2",
            "mode": "disc",
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
    )
    disc_prompt = load_disc_prompt()

    for stage in (
        run_parse_stage,
        run_feature_stage,
        run_disc_evidence_stage,
        run_masking_stage,
        run_decision_stage,
    ):
        context = stage(context)

    context = run_llm_stage(context, disc_prompt=disc_prompt)
    return build_response(context)
