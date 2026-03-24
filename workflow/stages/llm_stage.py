from __future__ import annotations

from app.config import OPENAI_ANALYSIS_MODEL, OPENAI_API_KEY

from workflow.context import WorkflowContext
from workflow.helpers import build_disc_messages, call_openai_compatible


def run_llm_stage(context: WorkflowContext, disc_prompt: str) -> WorkflowContext:
    context.mark_stage("llm_stage", "started", "Optional LLM analysis")
    if not OPENAI_API_KEY:
        context.mark_stage("llm_stage", "skipped", "OPENAI_API_KEY not configured")
        return context

    try:
        context.analysis_output = call_openai_compatible(
            OPENAI_ANALYSIS_MODEL,
            build_disc_messages(
                prompt=disc_prompt,
                transcript=context.transcript,
                turns=context.detailed_turns,
                features=context.features,
                knowledge=context.knowledge,
                job_inference=context.job_inference,
            ),
        )
        context.mark_stage("llm_stage", "completed", "LLM analysis returned")
    except Exception as exc:
        context.analysis_error = str(exc)
        context.mark_stage("llm_stage", "failed", context.analysis_error)
    return context
