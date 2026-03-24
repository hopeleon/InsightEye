from __future__ import annotations

from app.enneagram_engine import analyze_enneagram
from app.knowledge import load_enneagram_knowledge

from workflow.context import WorkflowContext


def run_enneagram_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("enneagram_stage", "started", "Run local Enneagram analysis")
    knowledge = load_enneagram_knowledge()
    context.enneagram_result = analyze_enneagram(
        context.transcript,
        context.turns_for_analysis,
        context.features,
        knowledge,
    )
    context.mark_stage("enneagram_stage", "completed", "Enneagram analysis ready")
    return context
