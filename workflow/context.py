from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowContext:
    transcript: str
    job_hint: str = ""
    knowledge: dict[str, Any] = field(default_factory=dict)
    segments: list[dict[str, Any]] = field(default_factory=list)
    detailed_turns: list[dict[str, Any]] = field(default_factory=list)
    job_inference: dict[str, Any] = field(default_factory=dict)
    parser_output: dict[str, Any] | None = None
    parser_error: str | None = None
    parse_source: str = "local_rules"
    turns_for_analysis: list[dict[str, Any]] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)
    local_disc_result: dict[str, Any] = field(default_factory=dict)
    disc_evidence: dict[str, Any] = field(default_factory=dict)
    masking_assessment: dict[str, Any] = field(default_factory=dict)
    decision_payload: dict[str, Any] = field(default_factory=dict)
    disc_analysis: dict[str, Any] = field(default_factory=dict)
    mbti_analysis: dict[str, Any] = field(default_factory=dict)
    mbti_knowledge: dict[str, Any] = field(default_factory=dict)
    mbti_result: dict[str, Any] = field(default_factory=dict)
    bigfive_result: dict[str, Any] = field(default_factory=dict)
    enneagram_result: dict[str, Any] = field(default_factory=dict)
    star_result: dict[str, Any] = field(default_factory=dict)
    personality_mapping_result: dict[str, Any] = field(default_factory=dict)
    llm_bigfive_output: dict[str, Any] = field(default_factory=dict)
    llm_enneagram_output: dict[str, Any] = field(default_factory=dict)
    analysis_output: dict[str, Any] | None = None
    analysis_error: str | None = None
    llm_called: bool = False
    stage_trace: list[dict[str, Any]] = field(default_factory=list)

    def mark_stage(self, name: str, status: str, detail: str = "") -> None:
        self.stage_trace.append({"stage": name, "status": status, "detail": detail})
