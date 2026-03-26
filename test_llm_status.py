# -*- coding: utf-8 -*-
import sys

sys.stdout.reconfigure(encoding="utf-8")

import app.config as config
from workflow.engine import run_local_workflow

transcript = "\u6d4b\u8bd5\u6587\u672c\u5185\u5bb9\uff0c\u7528\u4e8e\u9a8c\u8bc1 llm_status.enabled \u662f\u5426\u6b63\u786e\u53cd\u6620 LLM \u8c03\u7528\u72b6\u6001\u3002"
original_api_key = config.OPENAI_API_KEY
original_parser_model = config.OPENAI_PARSER_MODEL
original_analysis_model = config.OPENAI_ANALYSIS_MODEL

config.OPENAI_API_KEY = None
result = run_local_workflow(transcript, "")

print("=== run_local_workflow results ===")
llm_status = result.get("llm_status", {})
print(f'llm_status.enabled: {llm_status.get("enabled")}')
print(f'llm_analysis present: {result.get("llm_analysis") is not None}')
assert llm_status.get("enabled") is False
assert llm_status.get("api_enabled") is False
assert llm_status.get("parser_model") is None
assert llm_status.get("analysis_model") is None

config.OPENAI_API_KEY = None
from workflow.engine import run_disc_workflow

result2 = run_disc_workflow(transcript, "")
llm_status2 = result2.get("llm_status", {})
print()
print("=== run_disc_workflow results (API key = None) ===")
print(f'llm_status.enabled: {llm_status2.get("enabled")}')
print(f'llm_analysis present: {result2.get("llm_analysis") is not None}')
assert llm_status2.get("enabled") is False
assert llm_status2.get("api_enabled") is False

config.OPENAI_API_KEY = original_api_key
config.OPENAI_PARSER_MODEL = original_parser_model
config.OPENAI_ANALYSIS_MODEL = original_analysis_model
