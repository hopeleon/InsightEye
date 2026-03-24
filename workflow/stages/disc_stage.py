from __future__ import annotations

from app.disc_engine import analyze_disc

from workflow.context import WorkflowContext


def run_disc_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("disc_stage", "started", "Run local DISC analysis")
    context.disc_analysis = analyze_disc(
        context.transcript,
        context.turns_for_analysis,
        context.features,
        context.knowledge,
    )
    context.mark_stage("disc_stage", "completed", "Local DISC analysis ready")
    return context
