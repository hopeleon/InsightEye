from __future__ import annotations

import logging
import time

import app.config as config

from workflow.context import WorkflowContext
from workflow.helpers import build_disc_messages, call_openai_compatible

logger = logging.getLogger("insighteye.llm_stage")


def run_llm_stage(context: WorkflowContext, disc_prompt: str) -> WorkflowContext:
    logger.info("[LLM阶段] ===== 开始 LLM 分析 =====")
    _llm_start = time.perf_counter()

    context.mark_stage("llm_stage", "started", "Optional LLM analysis")
    if not config.OPENAI_API_KEY:
        logger.warning("[LLM阶段] OPENAI_API_KEY 未配置，跳过 LLM 分析")
        context.mark_stage("llm_stage", "skipped", "OPENAI_API_KEY not configured")
        return context

    try:
        _call_start = time.perf_counter()
        context.analysis_output = call_openai_compatible(
            config.OPENAI_ANALYSIS_MODEL,
            build_disc_messages(
                prompt=disc_prompt,
                transcript=context.transcript,
                turns=context.detailed_turns,
                features=context.features,
                knowledge=context.knowledge,
                job_inference=context.job_inference,
            ),
        )
        _call_elapsed = (time.perf_counter() - _call_start) * 1000
        _total_elapsed = (time.perf_counter() - _llm_start) * 1000

        context.mark_stage("llm_stage", "completed", f"LLM analysis returned in {_call_elapsed:.0f}ms")
        context.llm_called = True
        logger.info(f"[LLM阶段] LLM 分析完成 | 模型: {config.OPENAI_ANALYSIS_MODEL} | 调用耗时: {_call_elapsed:.0f}ms | 总耗时: {_total_elapsed:.0f}ms")
    except Exception as exc:
        _error_elapsed = (time.perf_counter() - _llm_start) * 1000
        context.analysis_error = str(exc)
        context.mark_stage("llm_stage", "failed", context.analysis_error)
        logger.error(f"[LLM阶段] LLM 分析失败 | 耗时: {_error_elapsed:.0f}ms | 错误: {exc}")

    logger.info(f"[LLM阶段] ===== LLM 分析阶段结束 =====")
    return context
