from __future__ import annotations

from workflow.context import WorkflowContext


def run_decision_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("decision_stage", "started", "Build final local decision payload")
    result = context.local_disc_result
    context.decision_payload = {
        "decision_summary": result.get("decision_summary", ""),
        "risk_summary": result.get("risk_summary", ""),
        "recommended_action": result.get("recommended_action", ""),
        "overall_style_summary": result.get("overall_style_summary", ""),
        "follow_up_questions": result.get("follow_up_questions", []),
    }
    context.disc_analysis = result
    context.mark_stage("decision_stage", "completed", "Local decision payload ready")
    return context
