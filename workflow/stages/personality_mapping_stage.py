from __future__ import annotations

from app.personality_mapping import map_personality

from workflow.context import WorkflowContext


def _conflict_key(item: dict) -> str:
    return f"{item.get('type', '')}:{(item.get('description') or '')[:40]}"


def run_personality_mapping_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("personality_mapping_stage", "started", "Run cross-model personality mapping")
    context.personality_mapping_result = map_personality(
        disc_result=context.local_disc_result,
        bigfive_result=context.bigfive_result,
        enneagram_result=context.enneagram_result,
        features=context.features,
    )

    combined_conflicts: list[dict] = []
    combined_conflicts.extend(context.bigfive_result.get("risk_flags", []) if isinstance(context.bigfive_result, dict) else [])
    combined_conflicts.extend(context.enneagram_result.get("risk_flags", []) if isinstance(context.enneagram_result, dict) else [])

    if combined_conflicts and context.mbti_analysis:
        existing = list(context.mbti_analysis.get("conflicts") or [])
        seen = {_conflict_key(item) for item in existing}
        for item in combined_conflicts:
            if not isinstance(item, dict):
                continue
            normalized = {
                "type": item.get("risk_type") or item.get("type") or "Cross-model signal",
                "severity": item.get("severity", "medium"),
                "description": item.get("description") or item.get("message") or "",
                "recommendation": item.get("mitigation") or item.get("recommendation") or "",
            }
            key = _conflict_key(normalized)
            if key not in seen:
                existing.append(normalized)
                seen.add(key)
        context.mbti_analysis["conflicts"] = existing[:8]

    context.mark_stage("personality_mapping_stage", "completed", "Cross-model personality mapping ready")
    return context
