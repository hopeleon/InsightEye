from __future__ import annotations

from workflow.engine import run_disc_workflow, run_personality_workflow


def analyze_interview(
    transcript: str,
    job_hint: str = "",
    *,
    apply_knowledge_graph: bool = True,
) -> dict:
    return run_disc_workflow(
        transcript=transcript,
        job_hint=job_hint,
        apply_knowledge_graph=apply_knowledge_graph,
    )


def analyze_interview_full(
    transcript: str,
    job_hint: str = "",
    *,
    apply_knowledge_graph: bool = True,
) -> dict:
    """完整人格分析：DISC + Big Five + 九型人格 + 跨模型映射。"""
    return run_personality_workflow(
        transcript=transcript,
        job_hint=job_hint,
        apply_knowledge_graph=apply_knowledge_graph,
    )
