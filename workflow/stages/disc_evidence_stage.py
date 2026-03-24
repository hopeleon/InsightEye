from __future__ import annotations

from app.disc_engine import analyze_disc

from workflow.context import WorkflowContext


def run_disc_evidence_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("disc_evidence_stage", "started", "Build DISC evidence bundle")
    context.local_disc_result = analyze_disc(
        context.transcript,
        context.turns_for_analysis,
        context.features,
        context.knowledge,
    )
    context.disc_evidence = {
        "scores": context.local_disc_result.get("scores", {}),
        "ranking": context.local_disc_result.get("ranking", []),
        "dimension_analysis": context.local_disc_result.get("dimension_analysis", {}),
        "behavioral_hypotheses": context.local_disc_result.get("behavioral_hypotheses", []),
        "feature_highlights": context.local_disc_result.get("feature_highlights", []),
    }
    context.mark_stage("disc_evidence_stage", "completed", "DISC evidence extracted")
    return context
