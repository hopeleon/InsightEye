# -*- coding: utf-8 -*-
with open(r'D:/InsightEye/app/realtime_ws_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_str = '# 检查是否可以完成注册（每位说话人至少2个样本）\n            if len(auto_reg.interviewer_samples) >= 2 and len(auto_reg.candidate_samples) >= 2:'
new_str = '# 检查是否可以完成注册（每位说话人至少2个样本）\n            min_samples = 2\n            print(f"[AutoReg] 当前进度: 面试官={len(auto_reg.interviewer_samples)}/{min_samples}, 候选人={len(auto_reg.candidate_samples)}/{min_samples}")\n\n            if len(auto_reg.interviewer_samples) >= min_samples and len(auto_reg.candidate_samples) >= min_samples:'

if old_str in content:
    content = content.replace(old_str, new_str)
    result = "替换成功"
else:
    result = "未找到目标"

with open(r'D:/InsightEye/fix_result.txt', 'w', encoding='utf-8') as f:
    f.write(result)
