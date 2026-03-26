#!/usr/bin/env python
import os
import sys

sys.path.insert(0, os.getcwd())


def try_import(module_name):
    try:
        __import__(module_name)
        print(f"  [OK] {module_name}")
        return True
    except Exception as exc:
        print(f"  [FAIL] {module_name}: {exc}")
        return False


print("=" * 60)
print("TEST: Import all Python modules")
print("=" * 60)
for module_name in [
    "app.config",
    "app.knowledge",
    "app.analysis",
    "app.star_analyzer",
    "app.bigfive_engine",
    "app.enneagram_engine",
    "app.personality_mapping",
    "workflow.engine",
    "workflow.helpers",
    "workflow.knowledge_graph",
]:
    try_import(module_name)

print()
print("=" * 60)
print("TEST: Workflow stages")
print("=" * 60)
stage_dir = os.path.join("workflow", "stages")
for stage_name in [
    "parse_stage",
    "feature_stage",
    "disc_evidence_stage",
    "disc_stage",
    "masking_stage",
    "decision_stage",
    "llm_stage",
    "mbti_stage",
    "star_stage",
    "bigfive_stage",
    "enneagram_stage",
    "personality_mapping_stage",
]:
    path = os.path.join(stage_dir, f"{stage_name}.py")
    print(f"  {'[OK]' if os.path.exists(path) else '[MISS]'} {stage_name}")

print()
print("=" * 60)
print("TEST: Knowledge files")
print("=" * 60)
knowledge_dir = "knowledge"
for knowledge_file in ["DISC.yaml", "MBTI.yaml", "BIGFIVE.yaml", "ENNEAGRAM.yaml", "STAR.yaml"]:
    path = os.path.join(knowledge_dir, knowledge_file)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    print(f"  {'[OK]' if os.path.exists(path) else '[MISS]'} {knowledge_file} ({size} bytes)")

print()
print("=" * 60)
print("TEST: Quick local workflow")
print("=" * 60)
try:
    from workflow.engine import run_local_workflow

    cases = {
        "single_line": (
            "\u9762\u8bd5\u5b98\uff1a\u8bb2\u4e00\u4e2a\u4f60\u505a\u8fc7\u7684\u6280\u672f\u9879\u76ee\u3002"
            "\u5019\u9009\u4eba\uff1a\u6211\u4e4b\u524d\u53c2\u4e0e\u8fc7\u4e00\u4e2a\u8ba2\u5355\u7cfb\u7edf\u4f18\u5316\u9879\u76ee\uff0c\u9ad8\u5cf0\u671f\u54cd\u5e94\u65f6\u95f4\u4e0d\u592a\u7a33\u5b9a\u3002"
            "\u9762\u8bd5\u5b98\uff1a\u4f60\u5177\u4f53\u662f\u600e\u4e48\u5b9a\u4f4d\u95ee\u9898\u7684\uff1f"
            "\u5019\u9009\u4eba\uff1a\u6211\u4e3b\u8981\u5148\u770b\u65e5\u5fd7\u548c\u54cd\u5e94\u65f6\u95f4\uff0c\u518d\u770b\u54ea\u4e9b\u63a5\u53e3\u6bd4\u8f83\u6162\u3002"
        ),
        "multi_line": (
            "\u9762\u8bd5\u5b98\uff1a\u8bb2\u4e00\u4e2a\u4f60\u505a\u8fc7\u7684\u6280\u672f\u9879\u76ee\u3002\n"
            "\u5019\u9009\u4eba\uff1a\u6211\u4e4b\u524d\u53c2\u4e0e\u8fc7\u4e00\u4e2a\u8ba2\u5355\u7cfb\u7edf\u4f18\u5316\u9879\u76ee\uff0c\u9ad8\u5cf0\u671f\u54cd\u5e94\u65f6\u95f4\u4e0d\u592a\u7a33\u5b9a\u3002\n"
            "\u9762\u8bd5\u5b98\uff1a\u4f60\u5177\u4f53\u662f\u600e\u4e48\u5b9a\u4f4d\u95ee\u9898\u7684\uff1f\n"
            "\u5019\u9009\u4eba\uff1a\u6211\u4e3b\u8981\u5148\u770b\u65e5\u5fd7\u548c\u54cd\u5e94\u65f6\u95f4\uff0c\u518d\u770b\u54ea\u4e9b\u63a5\u53e3\u6bd4\u8f83\u6162\u3002"
        ),
    }
    result = None
    for label, transcript in cases.items():
        result = run_local_workflow(transcript, "\u540e\u7aef\u7814\u53d1")
        overview = result.get("input_overview", {})
        if overview.get("turn_count", 0) < 2:
            raise AssertionError(f"{label} transcript parsed into too few turns: {overview}")
        if overview.get("candidate_char_count", 0) <= 20:
            raise AssertionError(f"{label} transcript produced invalid candidate_char_count: {overview}")
        print(f"  [OK] {label} workflow completed: {overview}")
    print(f"      disc keys: {list(result.get('disc_analysis', {}).keys())}")
    print(f"      star keys: {list(result.get('star_analysis', {}).keys())}")
    print(f"      mbti type: {result.get('mbti_analysis', {}).get('type', 'N/A')}")
    print(f"      bigfive: {'present' if result.get('bigfive_analysis') else 'MISSING'}")
    print(f"      enneagram: {'present' if result.get('enneagram_analysis') else 'MISSING'}")
    print(f"      mapping: {'present' if result.get('personality_mapping') else 'MISSING'}")

    from workflow.engine import run_personality_workflow
    full_report = run_personality_workflow(cases["multi_line"], "????")
    if full_report.get("workflow", {}).get("mode") != "full_personality":
        raise AssertionError(f"full workflow mode mismatch: {full_report.get('workflow')}")
    if not full_report.get("personality_mapping"):
        raise AssertionError("full workflow missing personality_mapping")
    print(f"  [OK] full personality workflow completed: {full_report.get('workflow', {}).get('mode')}")
except Exception as exc:
    import traceback

    print(f"  [FAIL] {exc}")
    traceback.print_exc()
    raise

print()
print("=" * 60)
print("All tests done!")
print("=" * 60)
