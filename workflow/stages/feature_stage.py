from __future__ import annotations

from app.features import extract_features

from workflow.context import WorkflowContext


def run_feature_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("feature_stage", "started", "Extract atomic features")
    context.turns_for_analysis = [
        {
            "turn_id": turn["turn_id"],
            "question": turn["question"],
            "question_type": turn["question_type"],
            "answer": turn["answer"],
        }
        for turn in context.detailed_turns
    ]
    context.features = extract_features(context.turns_for_analysis)
    context.mark_stage("feature_stage", "completed", "Atomic features ready")
    return context
