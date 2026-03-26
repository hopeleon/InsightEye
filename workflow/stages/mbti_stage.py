from __future__ import annotations

from app.knowledge import load_mbti_knowledge
from app.mbti_agent import analyze_mbti

from workflow.context import WorkflowContext


def run_mbti_stage(context: WorkflowContext) -> WorkflowContext:
    """Run MBTI local-rule analysis while keeping the main branch MBTI flow."""
    context.mark_stage("mbti_stage", "started", "Run local MBTI analysis")
    knowledge = context.mbti_knowledge or load_mbti_knowledge()

    disc_scores = {}
    if isinstance(context.local_disc_result, dict):
        disc_scores = context.local_disc_result.get("scores", {}) or {}
    elif isinstance(context.disc_analysis, dict):
        disc_scores = context.disc_analysis.get("scores", {}) or {}

    result = analyze_mbti(
        context.transcript,
        context.turns_for_analysis,
        context.features,
        knowledge,
        disc_scores=disc_scores,
    )
    context.mbti_knowledge = knowledge
    context.mbti_result = result
    context.mbti_analysis = result
    context.mark_stage("mbti_stage", "completed", "MBTI analysis ready")
    return context
