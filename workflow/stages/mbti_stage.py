from __future__ import annotations

from app.knowledge import load_mbti_knowledge
from app.mbti_agent import analyze_mbti

from workflow.context import WorkflowContext


def run_mbti_stage(context: WorkflowContext) -> WorkflowContext:
    """运行 MBTI 本地规则分析阶段。"""
    context.mark_stage("mbti_stage", "started", "Run local MBTI analysis")
    knowledge = load_mbti_knowledge()
    disc_scores = context.disc_analysis.get("scores", {}) if isinstance(context.disc_analysis, dict) else {}
    context.mbti_result = analyze_mbti(
        context.transcript,
        context.turns_for_analysis,
        context.features,
        knowledge,
        disc_scores=disc_scores,
    )
    context.mark_stage("mbti_stage", "completed", "MBTI analysis ready")
    return context
