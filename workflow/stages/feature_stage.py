from __future__ import annotations

from app.features import extract_features, extract_features_with_industry

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
    # 基础原子特征
    context.features = extract_features(context.turns_for_analysis)
    # 行业维度特征（行业知识库存在时生效）
    ind = context.industry_knowledge if hasattr(context, "industry_knowledge") else None
    if ind:
        context.features = extract_features_with_industry(context.turns_for_analysis, ind)
    context.mark_stage("feature_stage", "completed", "Atomic features ready")
    return context
