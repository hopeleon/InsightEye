from __future__ import annotations

from workflow.context import WorkflowContext


def run_masking_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("masking_stage", "started", "Extract masking and risk signals")
    result = context.local_disc_result
    context.masking_assessment = {
        "meta": result.get("meta", {}),
        "critical_findings": result.get("critical_findings", []),
        "hire_risks": result.get("hire_risks", []),
        "evidence_gaps": result.get("evidence_gaps", []),
    }
    detail = f"{len(context.masking_assessment.get('critical_findings', []))} critical findings"
    context.mark_stage("masking_stage", "completed", detail)
    return context
