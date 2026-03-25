# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from workflow.engine import run_local_workflow
import app.config as config

transcript = "测试文本内容，用于验证 llm_status.enabled 是否正确反映 LLM 调用状态。"

# 本地工作流（禁用 LLM）
config.OPENAI_API_KEY = None
result = run_local_workflow(transcript, "")

print("=== run_local_workflow 结果 ===")
llm_status = result.get("llm_status", {})
print(f'llm_status.enabled: {llm_status.get("enabled")}')
print(f'llm_analysis 存在: {result.get("llm_analysis") is not None}')
print(f'llm_analysis 值: {result.get("llm_analysis")}')

# 正常流程（启用 LLM，但 API key 为 None 所以不会真正调用）
config.OPENAI_API_KEY = None
from workflow.engine import run_disc_workflow
result2 = run_disc_workflow(transcript, "")
llm_status2 = result2.get("llm_status", {})
print()
print("=== run_disc_workflow 结果（API key = None）===")
print(f'llm_status.enabled: {llm_status2.get("enabled")}')
print(f'llm_analysis 存在: {result2.get("llm_analysis") is not None}')
