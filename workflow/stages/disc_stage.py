from __future__ import annotations

from workflow.context import WorkflowContext


def run_disc_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("disc_stage", "started", "Run local DISC analysis")
    # 直接复用 disc_evidence_stage 的结果，避免重复调用 analyze_disc
    context.disc_analysis = context.local_disc_result
    context.mark_stage("disc_stage", "completed", "Local DISC analysis ready")
    return context
