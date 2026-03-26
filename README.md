# InsightEye

[English Version](./README_EN.md)

**InsightEye** 是一个面向面试辅助场景的候选人分析原型系统。它把原始 transcript 转成更适合面试官快速判断的结果界面，重点输出候选人的行为风格、风险信号和下一步追问建议。

当前版本的中心目标不是“分析得更花”，而是先保证 **核心链路可运行、可回退、可验证**。

---

## 当前可跑通的重点功能

当前版本已经验证可用的核心链路有：

- 本地 Demo 服务可正常启动
- `GET /api/health` 可用
- `POST /api/analyze` 可用，返回异步任务并可轮询结果
- `GET /api/llm_status/{task_id}` 可用
- `POST /api/analyze/full` 可用
- 单行 transcript 与多行 transcript 都可以正常切分轮次
- 未启用 LLM 时，系统可退回本地分析，不会因为模型不可用而完全失效

本次本地冒烟实际验证的是：

- `http://127.0.0.1:8011/api/health`
- `http://127.0.0.1:8011/api/analyze`
- `http://127.0.0.1:8011/api/analyze/full`

验证时关闭了外部 LLM，结果如下：

- 服务启动成功
- `/api/analyze` 成功返回任务并完成轮询
- `/api/analyze/full` 成功返回完整结果
- 本地全量模式下可得到 `DISC / STAR / MBTI / Big Five / Enneagram / personality mapping`

---

## 系统定位

InsightEye 是一个 **面试决策支持层**，不是人格诊断工具。

它重点辅助的是：

- 候选人的行为风格判断
- 证据质量和真实性风险识别
- 面试官下一步追问方向

它不应该被理解为：

- 自动淘汰系统
- 临床人格评估
- 对面试官判断的替代

---

## 当前能力范围

### 本地模式

本地模式是当前最稳定、最推荐的运行方式，也是保证核心功能可行的基础模式。

本地模式当前可提供：

- transcript 角色识别与问答切分
- 岗位语境粗判断
- 原子语言特征抽取
- DISC 分析
- STAR 真实性 / 缺陷分析
- MBTI 分析
- Big Five 分析
- Enneagram 分析
- 人格映射汇总
- 决策层结果组织

### LLM 增强模式

当 `local_settings.py` 中配置有效 API Key 时，系统可以启用 LLM 增强链路。

当前约定是：

- `gpt-5-mini` 用于 transcript 结构化解析
- `gpt-5.4` 用于 DISC 主分析
- 可选人格分析模型用于补充更高阶的人格维度输出

但从工程优先级上，当前版本首先保证的是：

- 没有 LLM 时核心功能依然能跑
- LLM 状态字段尽量反映真实运行状态
- 本地结果始终可作为 fallback

---

## 关键接口

### 1. 健康检查

```http
GET /api/health
```

返回：

```json
{"ok": true}
```

### 2. 异步分析

```http
POST /api/analyze
```

请求体：

```json
{
  "interview_transcript": "面试官：...\n候选人：...",
  "job_hint_optional": "后端研发",
  "force_llm": false
}
```

返回：

```json
{
  "task_id": "...",
  "message": "Task started"
}
```

然后轮询：

```http
GET /api/llm_status/{task_id}
```

### 3. 同步全量分析

```http
POST /api/analyze/full
```

请求体：

```json
{
  "interview_transcript": "面试官：...\n候选人：...",
  "job_hint_optional": "后端研发"
}
```

该接口会直接返回完整分析结果，更适合本地直连验证。

---

## 输入要求

推荐输入格式：

```text
面试官：请介绍一个你最近负责的项目。
候选人：……
面试官：你怎么判断问题出在哪里？
候选人：……
```

当前版本支持：

- 多行 transcript
- 单行连续 transcript
- 常见中文角色前缀，如 `面试官：`、`候选人：`

建议仍然优先使用结构清晰的 transcript，因为这会直接影响分析质量。

---

## 项目结构

```text
InsightEye/
├─ app/
│  ├─ analysis.py
│  ├─ config.py
│  ├─ server.py
│  ├─ transcript.py
│  ├─ features.py
│  ├─ disc_engine.py
│  ├─ star_analyzer.py
│  ├─ bigfive_engine.py
│  ├─ enneagram_engine.py
│  └─ personality_mapping.py
├─ workflow/
│  ├─ engine.py
│  ├─ helpers.py
│  └─ stages/
├─ knowledge/
├─ prompts/
├─ static/
├─ samples/
├─ run_demo.py
└─ README.md
```

---

## 本地运行

### 1. 配置

参考 `local_settings.py.example` 创建 `local_settings.py`。

如果你只想保证重点功能可跑，最简单的方式是：

- 不配置 API Key，直接走本地模式
- 或者保留 API 配置，但先把本地模式跑通再接 LLM

示例：

```python
OPENAI_API_KEY = ""
OPENAI_BASE_URL = "https://api.zhizengzeng.com/v1"
OPENAI_PARSER_MODEL = "gpt-5-mini"
OPENAI_ANALYSIS_MODEL = "gpt-5.4"
OPENAI_PERSONALITY_MODEL = "gpt-5-mini"
```

### 2. 启动

```powershell
python run_demo.py
```

默认地址：

```text
http://127.0.0.1:8000
```

### 3. 自检

建议至少跑下面三个脚本：

```powershell
python test_merge.py
python test_llm_status.py
python test_llm_trigger.py
```

这些检查当前覆盖了：

- 关键模块能否导入
- 单行 / 多行 transcript 是否都能正确切分
- 本地模式下 `llm_status` 是否正确
- `should_trigger_llm` 的基本行为是否正常

---

## 当前设计原则

当前版本的工程原则很明确：

- 先保证本地核心链路稳定
- LLM 是增强层，不是唯一依赖
- 输出优先服务面试官决策，不追求展示型堆料
- 出现不确定性时，优先保留 fallback 和可解释结果

---

## 已知限制

当前仍需明确的限制有：

- 分析结果是启发式和概率性的，不是诊断性结论
- transcript 质量会直接影响结果质量
- 岗位推断只是辅助信息，不应当作真值
- LLM 输出依赖外部接口可用性
- 当前测试更偏核心回归检查，还不是完整 benchmark 体系

---

## 安全说明

不要提交以下内容：

- `local_settings.py`
- API Key
- 真实且未脱敏的面试数据

---

## 总结

当前版本已经具备一个可运行的核心闭环：

- 启动服务
- 提交 transcript
- 获得本地可回退的分析结果
- 在需要时再接入 LLM 增强

如果目标是“先保证重点功能能跑”，当前建议就是：**优先用本地模式验证，再逐步打开 LLM 能力。**
