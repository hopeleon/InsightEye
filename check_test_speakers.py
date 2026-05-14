"""从测试结果JSON中分析说话人分布"""
import json
import re

with open(r"d:\InsightEye\data\speaker_test_results_v2.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# 获取测试结果中的所有说话人ID
test_speakers = set()
for r in data["results"]:
    test_speakers.add(r["ground_truth_id"])

print(f"测试结果中出现的不同说话人数量: {len(test_speakers)}")

# 排序并显示
sorted_speakers = sorted(test_speakers, key=lambda x: int(x))
print(f"说话人ID列表 (共{len(sorted_speakers)}个):")
for i, sid in enumerate(sorted_speakers):
    if i % 10 == 0:
        print()
    print(f"{sid}", end=" ")
print()

# 分析ID范围
ids_int = [int(s) for s in test_speakers]
print(f"\nID范围: {min(ids_int)} - {max(ids_int)}")
