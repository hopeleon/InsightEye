from __future__ import annotations

import app.config  # ← 修改：导入模块
from app.transcript import build_turns, parse_transcript

from workflow.context import WorkflowContext
from workflow.helpers import build_parser_messages, call_openai_compatible, infer_job_type, normalize_turns


def run_parse_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("parse_stage", "started", "Split transcript into turns")
    context.segments = parse_transcript(context.transcript)
    turns = build_turns(context.segments)
    context.detailed_turns = normalize_turns(turns)
    context.job_inference = infer_job_type(context.transcript)

    if context.job_hint:
        context.job_inference = {
            "value": context.job_hint,
            "confidence": 0.95,
            "evidence": ["Used caller-provided job hint."],
        }

    # ← 修改：动态读取 config
    if app.config.OPENAI_API_KEY:
        try:
            parser_output = call_openai_compatible(
                app.config.OPENAI_PARSER_MODEL,  # ← 修改
                build_parser_messages(context.transcript)
            )
            context.parser_output = parser_output
            parsed_turns = normalize_turns(parser_output.get("turns", [])) if isinstance(parser_output, dict) else []
            if parsed_turns:
                context.detailed_turns = parsed_turns
                context.parse_source = "gpt-4o-mini"
            if isinstance(parser_output, dict) and not context.job_hint and parser_output.get("job_inference"):
                context.job_inference = parser_output["job_inference"]
        except Exception as exc:
            context.parser_error = str(exc)

    context.mark_stage("parse_stage", "completed", f"Parsed {len(context.detailed_turns)} turns")
    return context