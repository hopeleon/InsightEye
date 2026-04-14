
## 开发日志

### Week1：项目初建与核心框架搭建

**主要工作**：
- 创建项目基础目录结构，建立分支管理规范
- 前端页面设计（`static/app.js`）
- 搭建后端服务框架（`app/server.py`）
- 初始化知识库体系（`knowledge/` 目录）
- 配置 DISC、MBTI 基础分析引擎
- 创建示例访谈样本库（`samples/` 目录）
- 优化测评结果的展示逻辑
- 调试九型人格（Enneagram）识别算法
- 优化九型人格的特征提取规则

**技术要点**：
- 采用模块化设计，分离业务逻辑与配置
- 建立 Workflow Pipeline 架构，支持 Stage 级联处理
- 设计统一的 LLM 调用接口（`app/analysis.py`）
- 将完整人格分析从原有主链路中拆分出来，新增 `analyze_interview_full()`，支持与基础分析并行存在
- 在 `app/server.py` 新增 `/api/analyze/full` 接口，避免破坏原有 `/api/analyze` 主链路
- 在 `workflow/engine.py` 组织 DISC、STAR、Big Five、九型、MBTI、映射与可选 LLM 阶段
- 在 `workflow/context.py` 扩展上下文字段，减少中间结果在单一 dict 中的堆叠
- 优化 STAR 分析逻辑，增强对回答质量的评判能力
- 调整分析流程的 Stage 执行顺序
- 补齐知识库路径、Prompt 路径和人格分析模型配置
- 在 `app/knowledge.py` 增加统一加载函数并使用缓存减少重复读取

**问题**：
- 完整分析速度较慢
- 完整人格映射与规则解析在早期落地时曾出现字符串闭合、条件分支不一致等问题，需要通过补测试和补文档逐步稳定

---

### Week2：实时面试系统开发

**主要工作**：
- 搭建实时面试工作空间（`app/realtime_session.py`）
- 集成阿里云 DashScope ASR 语音识别服务
- 实现 WebSocket 实时通信服务器（`app/realtime_ws_server.py`）
- 开发实时转录引擎（`app/realtime_transcriber.py`）
- 添加实时分析进度指示器
- 构建实时会话状态、转录回写与滚动建议分析的协同机制

**UI优化**：
- 工作流改进：缩短分析延迟至 2 秒以内，优化 LLM Prompt 提升建议质量，添加上下文滑动窗口机制
- 调整实时工作台布局为左中右三栏，分别承载状态与音源、中间转录、右侧建议，降低实时场景的信息噪音

**Bug修复记录**：
- 修复 WebSocket 异常断开后的状态恢复问题
- 解决 ASR 转录延迟累积导致的文本错位
- 修正 LLM 分析超时后的错误处理逻辑
- 优化内存占用，防止长时间会话的内存泄漏
- 由于原链路缺少真正的说话人识别，先采用 `speaker_a` / `speaker_b` 与文本推断组合的方式兜底，后续再向声纹识别重构

---

### Week3：本地语音链路重构与声纹识别接入

**主要工作**：
- 将原有云端语音链路重构为本地离线方案，改用 `FunASR + CAM++ + Silero VAD`
- 统一由 `app/model_manager.py` 管理本地模型资源
- 在 `app/streaming_pipeline.py` 中串联流式 VAD、ASR 与声纹识别
- 新增 `app/speaker_recognition.py`，支持说话人注册与识别
- 在 `app/realtime_session.py` 中扩展 `voice_mapping`、`voice_registered`、`sequential_roles` 等状态
- 移除旧的纯文本角色推断路径，降低链路歧义

**技术要点**：
- 从云端依赖转向本地推理，降低持续演示成本与网络波动影响
- 通过声纹识别前移角色判断，减少仅靠文本推断带来的不稳定性
- 保留顺序兜底与回溯修正机制，兼顾实时性与可解释性

**问题**：
- 当两个声纹阈值都未达到时，仍缺少强制二选一策略，低置信度相似度对决场景下还存在歧义

---

**最后更新**: 2026年4月14日

---
