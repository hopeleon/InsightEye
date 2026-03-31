# InsightEye

[English Version](./README_EN.md)

InsightEye 是一个面向面试辅助场景的候选人分析原型系统。它的目标不是替代面试官做判断，而是在面试过程中提供更结构化的辅助信息，包括实时转录、滚动分析、行为风格判断、风险提示和后续追问建议，并在面试结束后输出完整分析报告。

当前版本已经具备两条可运行主链路：一条是基于 transcript 的本地/LLM 分析链路，适合直接输入面试文本做结构化分析；另一条是基于浏览器音频采集的实时工作台链路，支持系统音频/麦克风输入、实时转录、滚动展示与结束后完整分析。整个系统的设计原则是先保证链路可运行、可回退、可解释，再逐步提升实时体验和识别精度。

---

## 核心能力

当前项目重点提供四类能力。第一类是 transcript 解析与面试结构化，包括角色切分、问答轮次组织、岗位语境粗判断和原子语言特征抽取。第二类是候选人风格与风险分析，包括 DISC、MBTI、STAR、Big Five、Enneagram 以及综合人格映射能力，其中本地规则链路可以在没有外部模型时独立运行。第三类是实时工作台能力，支持进入独立的实时界面，展示当前会话状态、音量监控、实时转录内容和推荐提问区域。第四类是结束后完整报告，能够在面试结束时返回整段 transcript 对应的完整分析结果。

需要明确的是，InsightEye 是“面试决策支持层”，不是临床人格测量工具，也不是自动淘汰系统。系统输出属于启发式与概率性判断，最终决策仍应由面试官结合岗位要求、上下文和实际面试表现综合判断。

---

## 当前实现状态

目前项目已经跑通以下关键能力：HTTP Demo 服务启动、本地静态页面访问、`/api/analyze` 异步分析、`/api/analyze/full` 同步全量分析、实时 session 管理、浏览器音频采集、本地 WebSocket 桥接、阿里 DashScope `qwen3-asr-flash-realtime` 实时 ASR 接入，以及实时会话结束后的完整分析报告生成。

在实时模式下，页面进入一个单独的工作台，只保留三个核心区域：左侧用于展示会话状态、音源开关和音量监控，中间用于展示实时转录内容，右侧用于展示滚动建议与推荐提问。完整分析区默认不在实时工作台中展开，而是在实时会话结束后通过按钮进入查看。

---

## 系统架构概览

从结构上看，InsightEye 可以理解为三层。最底层是输入层，既支持直接输入 transcript，也支持浏览器采集系统音频和麦克风音频。中间层是处理与编排层，包括 transcript 解析、实时 session 管理、实时 ASR 桥接、角色推断和滚动分析调度。最上层是结果层，分别对应实时工作台展示和结束后完整报告展示。

在实时链路中，浏览器会把音频流送到本地 WebSocket 桥接服务，由桥接服务把音频转发到阿里 DashScope Realtime ASR；ASR 返回的事件会被转换成项目内部统一的实时 session 结构，然后驱动前端工作台刷新。结束会话后，系统会把实时积累的 transcript 输入到现有分析链路中，生成完整报告。

---

## 目录结构

```text
InsightEye/
├─ app/
│  ├─ analysis.py
│  ├─ audio_transcription.py
│  ├─ config.py
│  ├─ disc_engine.py
│  ├─ star_analyzer.py
│  ├─ mbti_agent.py
│  ├─ bigfive_engine.py
│  ├─ enneagram_engine.py
│  ├─ personality_mapping.py
│  ├─ realtime_analyzer.py
│  ├─ realtime_session.py
│  ├─ realtime_ws_server.py
│  ├─ realtime_ws_state.py
│  ├─ role_inference.py
│  ├─ server.py
│  └─ transcript.py
├─ knowledge/
├─ prompts/
├─ static/
├─ samples/
├─ run_demo.py
├─ local_settings.py.example
└─ README.md
```

其中，`app/server.py` 是 HTTP Demo 服务入口，`app/realtime_ws_server.py` 是本地实时桥接服务入口，`app/realtime_session.py` 管理实时会话状态，`app/realtime_analyzer.py` 负责滚动分析与最终分析衔接，`static/` 目录包含当前前端工作台页面。

---

## 运行前准备

推荐使用 Python 3.11+。如果你要运行实时语音能力，还需要保证浏览器允许麦克风或系统音频采集，并且本机网络能够访问阿里 DashScope 实时接口。

项目配置通过 `local_settings.py` 或环境变量读取。最基本的做法是复制 `local_settings.py.example` 为 `local_settings.py`，然后按需填写配置项。对于 transcript 分析链路，你可以只配置 OpenAI 相关模型，也可以完全不配置 API Key，先跑本地规则链路。对于实时 ASR 链路，当前主配置是阿里 DashScope 的 `DASHSCOPE_API_KEY`。

一个典型的配置示例如下：

```python
OPENAI_API_KEY = ""
OPENAI_BASE_URL = "https://api.zhizengzeng.com/v1"
OPENAI_PARSER_MODEL = "gpt-5-mini"
OPENAI_ANALYSIS_MODEL = "gpt-5.4"
OPENAI_PERSONALITY_MODEL = "gpt-5-mini"

DASHSCOPE_API_KEY = ""
DASHSCOPE_REALTIME_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
DASHSCOPE_REALTIME_ASR_MODEL = "qwen3-asr-flash-realtime"
```

如果你只想先验证本地文本分析，可以先不配置 `DASHSCOPE_API_KEY`。如果你要验证实时 ASR，则必须配置阿里 API Key。

---

## 启动方式

启动 Demo 服务的方式很直接：

```powershell
python run_demo.py
```

默认会启动两个本地服务：HTTP Demo 服务运行在 `http://127.0.0.1:8000`，本地实时桥接 WebSocket 服务运行在 `ws://127.0.0.1:8765/realtime`。浏览器打开首页后，可以直接使用静态页面中的样例 transcript，也可以进入实时工作台模式。

---

## 使用方式

### 1. Transcript 分析

如果你当前更关注文本分析能力，可以直接在输入页粘贴 transcript，然后选择快速分析或完整分析模式。推荐输入格式为带有角色前缀的多轮对话，例如：

```text
面试官：请介绍一个你最近负责的项目。
候选人：……
面试官：你怎么判断问题出在哪里？
候选人：……
```

系统当前支持多行 transcript、单行连续 transcript，以及常见中文角色前缀，如 `面试官：`、`候选人：`。但从结果稳定性上看，结构越清晰的 transcript，分析结果通常越可靠。

### 2. 实时工作台

如果你要使用实时模式，前端会进入一个独立的实时工作台。左侧区域展示会话状态、音量监控和当前音源状态，中间区域展示实时转录内容，右侧区域展示滚动建议和推荐提问。实时模式支持麦克风和系统音频开关控制，适合演示“边听边转录、边看边分析”的工作流。

当前实时角色识别在双路输入条件下更可靠。如果只有单路系统音频，系统会退化为基于句子内容的启发式角色推断，因此不应把这部分结果当作严格意义上的说话人分离结论。

---

## API 概览

InsightEye 当前主要开放以下接口。

`GET /api/health` 用于健康检查，返回 `{ "ok": true }`。`POST /api/analyze` 用于触发异步分析任务，请求体中需要提供 `interview_transcript`，可选提供 `job_hint_optional` 和 `force_llm`，返回 `task_id` 后再通过 `GET /api/llm_status/{task_id}` 轮询结果。`POST /api/analyze/full` 用于直接获取完整分析结果，更适合本地联调和快速验证。

对于音频链路，`POST /api/audio/transcribe` 支持上传音频文件并返回分段转写结果；`POST /api/realtime/session/start` 用于创建一个实时会话；`GET /api/realtime/session/{session_id}/status` 返回当前实时会话状态；`POST /api/realtime/session/{session_id}/append` 用于追加文本片段；`POST /api/realtime/session/{session_id}/end` 用于结束实时会话并生成最终报告。前端在实时模式下不会直接访问 DashScope，而是通过本地桥接服务和这些会话接口进行协作。

---

## 测试与自检

当前仓库已经包含若干可直接运行的自检脚本。`test_merge.py` 主要覆盖 transcript 合并与切分逻辑，`test_llm_status.py` 和 `test_llm_trigger.py` 主要覆盖异步分析状态和是否触发 LLM 的判定逻辑，`test_realtime_session.py` 覆盖实时 session 相关行为，`test_audio_transcription.py` 覆盖音频转写结果归一化，`test_realtime_ws.py` 用于独立排查 realtime WebSocket 接口行为。

如果你在修改服务端逻辑或前端实时工作台后，建议至少执行：

```powershell
python test_merge.py
python test_llm_status.py
python test_llm_trigger.py
python test_realtime_session.py
python test_audio_transcription.py
```

如果你改动了前端脚本，还建议额外执行：

```powershell
node --check static/app.js
```

---

## 当前限制

当前版本仍然存在一些明确限制。首先，角色识别在单路音频场景下仍然是启发式推断，不是真正的声纹或说话人分离。其次，实时转录的输出时机和会议软件级别的极低延迟仍有差距，尤其在长回答场景下，用户感知延迟仍有继续优化空间。再次，推荐提问区域虽然已经有容器和基本数据通路，但在策略质量和稳定性上仍然处于继续迭代阶段。另外，本项目当前是原型系统，测试覆盖的是核心链路可运行性，而不是完整 benchmark、性能压测或生产级容错体系。

因此，当前更适合把 InsightEye 理解为“可运行、可演示、可继续开发的原型底座”，而不是已经具备生产级鲁棒性的面试系统。

---

## 安全与数据说明

不要提交 `local_settings.py`、真实 API Key 和未脱敏的真实面试数据。项目中的 transcript、样例音频和测试数据应始终保持可公开或已脱敏状态。实时模式涉及浏览器音频采集，使用时也应明确区分测试音频、公开音频和真实业务场景数据，避免未经授权采集或上传敏感内容。

---

## 当前建议

如果你的目标是先验证项目是否能跑，建议优先从 transcript 分析链路入手，确认本地分析、本地页面和完整报告都正常；然后再配置 DashScope 实时 ASR，进入实时工作台验证音频采集、转录和会话收尾流程。这样更容易把问题隔离清楚，也更符合当前项目的成熟度。
