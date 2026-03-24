from __future__ import annotations

from app.knowledge import load_star_knowledge
from app.star_analyzer import analyze_star

from workflow.context import WorkflowContext


def run_star_stage(context: WorkflowContext) -> WorkflowContext:
    """运行 STAR 结构分析阶段（作为 DISC 的辅助验证）。"""
    context.mark_stage("star_stage", "started", "Run STAR structure analysis")
    knowledge = load_star_knowledge()
    context.star_result = analyze_star(
        context.transcript,
        context.detailed_turns,
        context.features,
        knowledge,
    )
    context.mark_stage("star_stage", "completed", "STAR analysis ready")
    return context
