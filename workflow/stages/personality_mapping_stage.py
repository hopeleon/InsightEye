from __future__ import annotations

from app.personality_mapping import map_personality

from workflow.context import WorkflowContext


def run_personality_mapping_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("personality_mapping_stage", "started", "Run cross-model personality mapping")
    context.personality_mapping_result = map_personality(
        disc_result=context.local_disc_result,
        bigfive_result=getattr(context, "bigfive_result", None),
        enneagram_result=getattr(context, "enneagram_result", None),
        features=context.features,
    )
    context.mark_stage("personality_mapping_stage", "completed", "Cross-model personality mapping ready")
    return context
