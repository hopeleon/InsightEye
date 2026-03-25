#!/usr/bin/env python
import sys, os
sys.path.insert(0, os.getcwd())

def try_import(m):
    try:
        __import__(m)
        print(f"  [OK] {m}")
        return True
    except Exception as e:
        print(f"  [FAIL] {m}: {e}")
        return False

print("=" * 60)
print("TEST: Import all Python modules")
print("=" * 60)
for m in ["app.config","app.knowledge","app.analysis","app.star_analyzer","app.bigfive_engine","app.enneagram_engine","app.personality_mapping","workflow.engine","workflow.helpers","workflow.knowledge_graph"]:
    try_import(m)

print()
print("=" * 60)
print("TEST: Workflow stages")
print("=" * 60)
sdir = os.path.join("workflow", "stages")
for s in ["parse_stage","feature_stage","disc_evidence_stage","disc_stage","masking_stage","decision_stage","llm_stage","mbti_stage","star_stage","bigfive_stage","enneagram_stage","personality_mapping_stage"]:
    p = os.path.join(sdir, f"{s}.py")
    print(f"  {'[OK]' if os.path.exists(p) else '[MISS]'} {s}")

print()
print("=" * 60)
print("TEST: Knowledge files")
print("=" * 60)
kdir = "knowledge"
for kf in ["DISC.yaml","MBTI.yaml","BIGFIVE.yaml","ENNEAGRAM.yaml","STAR.yaml"]:
    p = os.path.join(kdir, kf)
    sz = os.path.getsize(p) if os.path.exists(p) else 0
    print(f"  {'[OK]' if os.path.exists(p) else '[MISS]'} {kf} ({sz} bytes)")

print()
print("=" * 60)
print("TEST: Quick local workflow")
print("=" * 60)
try:
    from workflow.engine import run_local_workflow
    txt = ("面试官：讲一个你做过的技术项目。"
           "候选人：我之前参与过一个订单系统优化项目，高峰期响应时间不太稳定。"
           "面试官：你具体是怎么定位问题的？"
           "候选人：我主要先看日志和响应时间，再看哪些接口比较慢。")
    result = run_local_workflow(txt, "后端研发")
    print(f"  [OK] Workflow completed")
    print(f"      turn_count: {result.get('input_overview', {}).get('turn_count', 'N/A')}")
    print(f"      disc keys: {list(result.get('disc_analysis', {}).keys())}")
    print(f"      star keys: {list(result.get('star_analysis', {}).keys())}")
    print(f"      mbti type: {result.get('mbti_analysis', {}).get('type', 'N/A')}")
    print(f"      bigfive: {'present' if result.get('bigfive_analysis') else 'MISSING'}")
    print(f"      enneagram: {'present' if result.get('enneagram_analysis') else 'MISSING'}")
    print(f"      mapping: {'present' if result.get('personality_mapping') else 'MISSING'}")
    print(f"      graph_boost enabled: {result.get('graph_boost', {}).get('enabled', 'N/A')}")
except Exception as e:
    import traceback
    print(f"  [FAIL] {e}")
    traceback.print_exc()

print()
print("=" * 60)
print("All tests done!")
print("=" * 60)
