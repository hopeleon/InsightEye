# -*- coding: utf-8 -*-
import sys

with open(r'D:/InsightEye/app/realtime_ws_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 方法1: 简单的字符串替换
old_str = '# 检查是否可以完成注册（每位说话人至少2个样本）\n            if len(auto_reg.interviewer_samples) >= 2 and len(auto_reg.candidate_samples) >= 2:'
new_str = '# 检查是否可以完成注册（每位说话人至少2个样本）\n            min_samples = 2\n            print(f"[AutoReg] 当前进度: 面试官={len(auto_reg.interviewer_samples)}/{min_samples}, 候选人={len(auto_reg.candidate_samples)}/{min_samples}")\n\n            if len(auto_reg.interviewer_samples) >= min_samples and len(auto_reg.candidate_samples) >= min_samples:'

if old_str in content:
    content = content.replace(old_str, new_str)
    print("替换成功")
else:
    print("未找到目标字符串")
    # 打印周围的字符用于调试
    idx = content.find('# 检查是否可以完成注册')
    if idx != -1:
        print("找到目标位置")
        print(repr(content[idx:idx+200]))
    else:
        print("连目标注释都没找到")
    sys.exit(1)

with open(r'D:/InsightEye/app/realtime_ws_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("保存成功")
