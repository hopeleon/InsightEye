# CHANGELOG

## 2026-04-10

### Bug修复：流式管道的竞态条件导致候选人显示为面试官

**问题**：第二个人说话时，声纹自动注册（后台 `asyncio.create_task`）和 ASR 任务并发执行。ASR 在注册完成前就提交了 FunASR 任务，导致候选人片段被标记为上一个已注册说话人（面试官）。

**根因**：`feed_audio` 中 `on_speech_segment` 用 `asyncio.create_task` fire-and-forget 启动自动注册，随后立即提交 ASR 任务，两者无同步。

**修复**：引入 `asyncio.Event` 同步机制：
- `feed_audio` 在提交 ASR 前等待 `_reg_done_event`
- `_process_auto_registration` 注册完成时调用 `pipeline._reg_done_event.set()`
- 首次 VAD 段落注册未完成时等待超时后继续 ASR（使用顺序推断）

**修改文件**：
- `app/streaming_pipeline.py`：新增 `_reg_done_event: Optional[asyncio.Event]`；`feed_audio` 中等待事件后再提交 ASR
- `app/realtime_ws_server.py`：注册完成时设置 `pipeline._reg_done_event.set()`

---

## 2026-04-10

### 新增：前端显示双相似度（与面试官+候选人的相似度）

**显示效果**：每个转录片段的标签显示与两位已注册声纹的相似度：

```
面试官(面试官=0.92 候选人=0.31)    ← CAM++ 识别结果
候选人(面试官=0.28 候选人=0.85)    ← CAM++ 识别结果
面试官(顺序)                       ← 声纹未注册时，顺序推断
```

右侧角色状态面板也显示所有片段的平均相似度。

**修改文件**：
- `app/streaming_pipeline.py`：`extract_and_compare` 返回4元组 `(speaker_id, best_score, interviewer_sim, candidate_sim)`；`TranscriptDelta` 增加 `interviewer_sim`/`candidate_sim` 字段
- `app/realtime_ws_server.py`：事件传递双相似度
- `app/realtime_ws_state.py`：存储双相似度到片段
- `app/realtime_session.py`：片段存储双相似度
- `static/app.js`：`speakerDisplayLabel` 显示双相似度；右侧面板计算平均相似度

---

## 2026-04-10

### Bugfix：CAM++ 识别结果被 sequential fallback 覆盖

**问题根因**：`feed_audio` 中 CAM++ 结果写入共享状态 `_last_speaker`，ASR 通过 `asyncio.create_task` 异步提交，读取 `_last_speaker` 时可能早于 CAM++ 写入，产生竞态。且 `on_delta` 中没有根据相似度推断角色。

**修复**：
1. `feed_audio` 中 CAM++ 结果作为参数直接透传给 `_run_streaming_asr`，不经过共享状态
2. `on_delta` 中根据相似度推断 `recognized_role`：`candidate_sim > interviewer_sim → "candidate"`
3. `TranscriptDelta` 增加 `recognized_role` 字段
4. `_on_transcript_delta` 的 event 字典增加 `"recognized_role"` 字段传给 `consume_local_transcript_event`
5. `consume_local_transcript_event` 去掉 `voice_registered` 条件，始终使用 `recognized_role`

**修改文件**：
- `app/streaming_pipeline.py`：增加 `recognized_role` 字段；在 `on_delta` 中推断角色

**问题根因**：注册完成前，候选人说与面试官的 ASR 结果先后到达，候选人说被误判为面试官。fallback 逻辑缺失也导致部分 segment 被错误分类。

**修复方案**：
1. Sequential 逻辑加入兜底：不是 first_speaker → 候选人（而非无角色）
2. `second_speaker` 被设置时，自动回溯修正所有误判 segment
3. 后端推送 `segment.corrected` 事件，前端实时更新标签

**修改文件**：
- `app/realtime_ws_state.py`：`consume_local_transcript_event` 修正 sequential 逻辑 + 回溯修正
- `app/realtime_ws_server.py`：推送 `segment.corrected` 事件
- `static/app.js`：处理 `segment.corrected` 实时更新转录标签

**问题根因**：声纹未注册时，所有 segment 的 `speaker_id` 都相同（`speaker_a`），无法区分说话人。原有逻辑按 `speaker_id` 匹配 `sequential_roles`，导致静默超时分段的候选人说也被判为面试官。

**解决方案**：引入 `segment_reason`（VAD 分段原因）作为说话人切换信号：
- `segment_reason = "voice_change"`：VAD 检测到声纹变化（候选人说）
- `segment_reason = "silence_timeout"`：静默超时分段

**角色推断新逻辑**：
1. `voice_change` → 候选人（切换）
2. `speaker_id == second_speaker` → 候选人（延续）
3. `speaker_id == first_speaker` → 面试官（延续）
4. `first_speaker == None` → 面试官（首个）
5. `else` → 候选人（兜底）

**修改文件**：
- `app/streaming_pipeline.py`：`TranscriptDelta` 增加 `segment_reason` 字段；`_run_streaming_asr` 传递分段原因
- `app/realtime_ws_server.py`：事件传递 `segment_reason`；日志标签改为中文
- `app/realtime_ws_state.py`：`consume_local_transcript_event` 用 `segment_reason` 区分说话人切换
- `static/app.js`：`speakerDisplayLabel` 简化；`buildRealtimeTranscriptRows` 从 segment 读取 `recognized_role`

**显示效果**：
- 声纹注册后：`面试官(0.85)` `候选人(0.72)`（括号内为与已注册声纹的平均相似度）
- 声纹未注册时：`面试官(顺序)` `候选人(顺序)`（括号内标注顺序推断来源）
- 右侧角色状态面板同步显示各角色的平均相似度

**修改文件**：

| 文件 | 变更 |
|------|------|
| `app/realtime_session.py` | `append_segment` 增加 `speaker_confidence` 字段存储 |
| `app/realtime_ws_state.py` | `consume_local_transcript_event` 传递 `speaker_confidence` 到片段 |
| `static/app.js` | `speakerDisplayLabel` 重写，支持 `recognized_role + confidence` 参数；`buildRealtimeTranscriptRows` 传入片段级 `recognized_role` 和 `speaker_confidence`；`renderRealtimeSessionPanel` 计算并显示各角色平均相似度 |

**问题**：在 CAM++ 声纹注册完成前，系统无法区分说话人，所有未识别片段的 `speaker_id` 为 `speaker_unk`，前端显示为"未知说话人"。

**解决方案**：新增"发言顺序角色推断"机制，在声纹未注册时自动按发言顺序分配角色：

| 发言顺序 | 分配角色 | 显示 |
|---------|---------|------|
| 第1个不同说话人 | interviewer | 面试官 |
| 第2个不同说话人 | candidate | 候选人 |
| 同一说话人再次发言 | 保持已有角色 | 同上 |

**角色推断优先级**：`recognized_role`（CAM++） > `sequential_roles`（发言顺序）

**修改文件**：

| 文件 | 变更 |
|------|------|
| `app/realtime_session.py` | 新增 `session["sequential_roles"]` 字段 `{"first_speaker": None, "second_speaker": None}` |
| `app/realtime_ws_state.py` | `consume_local_transcript_event` 增加发言顺序推断逻辑；修复原有的 `elif` NameError 问题；响应中增加 `sequential_roles` 字段 |
| `app/realtime_analyzer.py` | `build_realtime_transcript` 增加第3参数 `sequential_roles`；角色分配优先级改为 `recognized_role > voice_mapping > sequential_roles` |
| `app/server.py` | `_realtime_session_response` 增加 `sequential_roles` 传递 |
| `app/realtime_ws_server.py` | `SOURCE_TO_SPEAKER` 默认值从 `"speaker_unk"` 改为 `"speaker_a"`；注释说明 `recognized_role` 由后端推断填充 |
| `static/app.js` | `speakerDisplayLabel` 增加 `sequentialRoles` 参数；`buildRealtimeTranscriptRows` 增加 `sequentialRoles` 参数；`renderRealtimeSessionPanel` 声纹未注册时显示"发言顺序推断"和对应角色标签 |

**行为说明**：
- CAM++ 声纹注册成功后 `voice_registered=True`，`sequential_roles` 不再生效，完全由 `voice_mapping` 决定角色
- 发言顺序推断具有"记忆"：同一说话人的后续片段会保持首次推断的角色

---

## 2026-04-10

### 代码清理：移除 role_inference 残留逻辑

**问题背景**：项目中曾存在 `role_inference.py`（基于文本推断说话人角色的模块），该文件已删除，但其数据载体 `session["role_inference"]` 及相关传递逻辑仍残留在多个文件中。经过排查确认，这些残留代码从未被任何算法实际填充数据，纯粹是冗余的状态传递。

**清理内容**：

| 文件 | 变更 |
|------|------|
| `app/realtime_session.py` | 移除 session 初始化中的 `"role_inference"` 字段 |
| `app/realtime_analyzer.py` | 移除 `role_state` 变量及所有相关条件分支；`build_realtime_transcript` 参数从 3 个减为 2 个（移除 `role_state`）；`should_refresh_analysis` 改用 `voice_mapping` 直接推导 candidate |
| `app/realtime_ws_state.py` | 移除所有 `role_inference` 字段传递 |
| `app/server.py` | 移除 `_realtime_session_response` 中的 `role_state` 和 `role_inference` 传递；修正 `build_realtime_transcript` 调用签名 |

**替代逻辑**：所有原本依赖 `role_state["mapping"]` 的地方，现在统一使用 `voice_mapping` 的反向映射（`{v: k for k, v in voice_mapping.items()}`）。

**注意事项**：
- 前端如果曾依赖 `role_inference` 字段，需要改为使用 `voice_mapping`
- `job_inference`（职位类型推断）与本次清理无关，已确认保留

---

## 2026-04-10

### Bug 修复：CAM++ 英文声纹模型配置解析

**问题**：`app/model_manager.py` 中使用 `json.safe_load()` 导致报错 `module 'json' has no attribute 'safe_load'`。

**修复**：将 `json.safe_load(f)` 改为 `json.load(f)`。
