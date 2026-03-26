from __future__ import annotations

from app.bigfive_engine import analyze_bigfive
from app.knowledge import load_bigfive_knowledge

from workflow.context import WorkflowContext


def run_bigfive_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("bigfive_stage", "started", "Run local Big Five analysis")
    knowledge = load_bigfive_knowledge()
    context.bigfive_result = analyze_bigfive(
        context.transcript,
        context.turns_for_analysis,
        context.features,
        knowledge,
    )
    context.mark_stage("bigfive_stage", "completed", "Big Five analysis ready")
    return context
