# -*- coding: utf-8 -*-
# 读取文件
with open(r'D:/InsightEye/app/realtime_ws_server.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 找到目标行并修改
for i, line in enumerate(lines):
    if '# 检查是否可以完成注册' in line and i > 0:
        # 检查下一行
        if i + 1 < len(lines) and 'if len(auto_reg.interviewer_samples) >= 2' in lines[i + 1]:
            # 在注释行后插入新代码
            lines.insert(i + 1, '            min_samples = 2\n')
            lines.insert(i + 2, '            print(f"[AutoReg] 当前进度: 面试官={len(auto_reg.interviewer_samples)}/{min_samples}, 候选人={len(auto_reg.candidate_samples)}/{min_samples}")\n')
            lines.insert(i + 3, '            \n')
            break

# 保存
with open(r'D:/InsightEye/app/realtime_ws_server.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done')
