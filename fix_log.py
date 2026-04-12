# 读取文件
with open(r'D:/InsightEye/app/realtime_ws_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 替换
content = content.replace(
    '''            # 检查是否可以完成注册（每位说话人至少2个样本）
            if len(auto_reg.interviewer_samples) >= 2 and len(auto_reg.candidate_samples) >= 2:
                print("[AutoReg] 样本数量已满足，开始注册声纹...")
                # 完成注册
                int_result = auto_reg.speaker_recognizer.register_speaker(
                    "interviewer", auto_reg.interviewer_samples, name="面试官", role="interviewer"
                )
                cand_result = auto_reg.speaker_recognizer.register_speaker(
                    "candidate", auto_reg.candidate_samples, name="候选人", role="candidate"
                )
                
                print(f"[AutoReg] 注册结果: 面试官={int_result.success}, 候选人={cand_result.success}")
                
                if int_result.success and cand_result.success:
                    auto_reg.auto_register_done = True
                    auto_reg.enabled = False
                    print(f"[AutoReg] ✅ 自动注册完成！面试官 {int_result.sample_count} 个样本，质量={int_result.embedding_quality:.2f}，候选人 {cand_result.sample_count} 个样本，质量={cand_result.embedding_quality:.2f}")
                    
                    # 同步声纹到所有源管道
                    for src in sources.values():
                        if src.pipeline:
                            src.pipeline.register_speaker("interviewer", auto_reg.interviewer_embedding)
                            src.pipeline.register_speaker("candidate", auto_reg.candidate_embedding)
                            print(f"[AutoReg] ✅ 已同步声纹到管道: {src.source_name}")
                    
                    await websocket.send(json.dumps({
                        "type": "auto_registration.completed",
                        "success": True,
                        "message": "声纹注册完成！面试官和候选人已自动识别"
                    }, ensure_ascii=False))
                else:
                    print(f"[AutoReg] ❌ 注册失败: 面试官={int_result.message}, 候选人={cand_result.message}")
                    await websocket.send(json.dumps({
                        "type": "auto_registration.failed",
                        "success": False,
                        "message": f"注册失败: {int_result.message}"
                    }, ensure_ascii=False))''',
    '''            # 检查是否可以完成注册（每位说话人至少2个样本）
            min_samples = 2
            print(f"[AutoReg] 当前进度: 面试官={len(auto_reg.interviewer_samples)}/{min_samples}, 候选人={len(auto_reg.candidate_samples)}/{min_samples}")
            
            if len(auto_reg.interviewer_samples) >= min_samples and len(auto_reg.candidate_samples) >= min_samples:
                print("[AutoReg] 样本数量已满足，开始注册声纹...")
                # 完成注册
                int_result = auto_reg.speaker_recognizer.register_speaker(
                    "interviewer", auto_reg.interviewer_samples, name="面试官", role="interviewer"
                )
                cand_result = auto_reg.speaker_recognizer.register_speaker(
                    "candidate", auto_reg.candidate_samples, name="候选人", role="candidate"
                )
                
                print(f"[AutoReg] 注册结果: 面试官={int_result.success}, 候选人={cand_result.success}")
                
                if int_result.success and cand_result.success:
                    auto_reg.auto_register_done = True
                    auto_reg.enabled = False
                    print(f"[AutoReg] ✅ 自动注册完成！面试官 {int_result.sample_count} 个样本，质量={int_result.embedding_quality:.2f}，候选人 {cand_result.sample_count} 个样本，质量={cand_result.embedding_quality:.2f}")
                    
                    # 同步声纹到所有源管道
                    for src in sources.values():
                        if src.pipeline:
                            src.pipeline.register_speaker("interviewer", auto_reg.interviewer_embedding)
                            src.pipeline.register_speaker("candidate", auto_reg.candidate_embedding)
                            print(f"[AutoReg] ✅ 已同步声纹到管道: {src.source_name}")
                    
                    await websocket.send(json.dumps({
                        "type": "auto_registration.completed",
                        "success": True,
                        "message": "声纹注册完成！面试官和候选人已自动识别"
                    }, ensure_ascii=False))
                else:
                    print(f"[AutoReg] ❌ 注册失败: 面试官={int_result.message}, 候选人={cand_result.message}")
                    await websocket.send(json.dumps({
                        "type": "auto_registration.failed",
                        "success": False,
                        "message": f"注册失败: {int_result.message}"
                    }, ensure_ascii=False))'''
)

# 保存
with open(r'D:/InsightEye/app/realtime_ws_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done 4')
