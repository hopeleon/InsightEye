# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

from workflow.engine import run_local_workflow, should_trigger_llm
import app.config as config

transcript = """
面试官：请介绍一下你自己，以及你最近做的一个项目。
候选人：大家好，我是张三，目前在一家互联网公司担任产品经理。最近半年我主导了一个用户增长项目，通过优化分享机制和Push策略，使日活提升了15%。
面试官：能具体说说你是怎么做的吗？
候选人：好的，我当时首先分析了数据，发现分享的转化率比较低，只有3%左右。我和团队讨论后决定从两个方向入手：一是优化分享卡片的设计，二是增加激励机制。结果分享率提升到了8%，带动日活增加了5000人。
面试官：你在这个过程中遇到的最大挑战是什么？
候选人：最大的挑战是资源有限。开发和设计的资源都很紧张，我需要和多个团队协调优先级。我采用了敏捷迭代的方式，每周一个小版本，快速验证效果。最终在两个月内完成了全部优化。
面试官：如果让你重新做一次，有什么会做得不一样？
候选人：我觉得前期调研可以更充分一些，当时数据埋点不够完善，导致后期花了不少时间补数据。如果重来，我会先把埋点方案做得更完整。
"""

original = config.OPENAI_API_KEY
config.OPENAI_API_KEY = None

result = run_local_workflow(transcript, "产品经理")
need_llm, reason = should_trigger_llm(result)

config.OPENAI_API_KEY = original

disc = result.get("disc_analysis", {})
mbti = result.get("mbti_analysis", {})
overview = result.get("input_overview", {})

print("=== should_trigger_llm results ===")
print(f"Need LLM: {need_llm}")
print(f"Reason: {reason}")
print()
print("=== Key data ===")
print(f"Char count: {overview.get('candidate_char_count', 0)}")
print(f"Turn count: {overview.get('turn_count', 0)}")
disc_max = max(disc.get("scores", {}).values()) if disc.get("scores") else 0
print(f"DISC max score: {disc_max}")
print(f"MBTI type: {mbti.get('type')}")
mbti_neutral = sum(1 for d in mbti.get("dimensions", {}).values() if d.get("preference") == "neutral")
print(f"MBTI neutral count: {mbti_neutral}")
high_conflicts = sum(1 for c in mbti.get("conflicts", []) if c.get("severity") == "high")
print(f"High severity conflicts: {high_conflicts}")
print()
print("=== MBTI dimensions ===")
for key, val in mbti.get("dimensions", {}).items():
    print(f"  {key}: preference={val.get('preference')}, confidence={val.get('confidence')}, strength={val.get('strength')}")
