# CHANGELOG — main 分支 vs 合并后版本

> 本文档记录当前本地 main 分支与合并 ywj 分支人格增强功能后的所有差异。
> 生成时间：2026-03-25

---

## 概述

本次合并不影响前端 UI 及原有 `/api/analyze` 接口，新增功能通过独立接口 `/api/analyze/full` 提供。整体系统现在支持两条并行的工作流：

- **DISC 工作流**（`POST /api/analyze`）— 原有行为风格分析，完全不变
- **完整人格工作流**（`POST /api/analyze/full`）— 新增 DISC + BigFive + 九型 + MBTI + 跨模型映射

---

## 一、修改的文件

### 1. `app/analysis.py`

**变更类型**：小幅扩展

```python
# 新增一行导入
from workflow.engine import run_disc_workflow, run_personality_workflow

# 新增一个函数
def analyze_interview_full(transcript: str, job_hint: str = "") -> dict:
    """完整人格分析：DISC + BigFive + 九型 + MBTI + 跨模型映射（ywj 分支新增）。"""
    return run_personality_workflow(transcript=transcript, job_hint=job_hint)
```

`analyze_interview()` 原有逻辑未改动。

---

### 2. `app/config.py`

**变更类型**：新增配置项

新增路径配置：
- `BIGFIVE_KNOWLEDGE_PATH` → `knowledge/BIGFIVE.yaml`
- `BIGFIVE_PROMPT_PATH` → `prompts/bigfive_system_prompt.txt`
- `ENNEAGRAM_KNOWLEDGE_PATH` → `knowledge/ENNEAGRAM.yaml`
- `ENNEAGRAM_PROMPT_PATH` → `prompts/enneagram_system_prompt.txt`
- `STAR_KNOWLEDGE_PATH` → `knowledge/STAR.yaml`

新增模型配置：
- `DEFAULT_OPENAI_PERSONALITY_MODEL = "gpt-5-mini"`
- `OPENAI_PERSONALITY_MODEL` — 支持 `local_settings.py` 或环境变量覆盖

---

### 3. `app/knowledge.py`

**变更类型**：新增知识库加载函数

```python
# 原有（保留）
load_disc_knowledge()     # knowledge/DISC.yaml
load_disc_prompt()       # prompts/disc_system_prompt.txt
load_mbti_knowledge()     # knowledge/MBTI.yaml（已提升为顶层导入，不再延迟导入）
load_mbti_prompt()

# 新增
load_bigfive_knowledge()      # knowledge/BIGFIVE.yaml
load_bigfive_prompt()         # prompts/bigfive_system_prompt.txt
load_enneagram_knowledge()   # knowledge/ENNEAGRAM.yaml
load_enneagram_prompt()      # prompts/enneagram_system_prompt.txt
load_star_knowledge()         # knowledge/STAR.yaml
```

---

### 4. `app/server.py`

**变更类型**：新增接口路由

```python
# 新增路由（与原有 /api/analyze 完全并行，互不影响）
POST /api/analyze/full
    → 调用 analyze_interview_full()
    → 返回完整人格分析结果（DISC + BigFive + 九型 + MBTI + 跨模型映射 + 图谱加速）

# 原有路由（完全不变）
POST /api/analyze
    → 调用 analyze_interview()
    → 返回 DISC 分析结果
```

同时提取了 `_parse_payload()` 和 `_run_analysis()` 公共辅助函数，简化了 `do_POST()` 的结构。

---

### 5. `workflow/context.py`

**变更类型**：新增数据字段

`WorkflowContext` dataclass 新增字段：

```python
# 新增人格分析结果
bigfive_result: dict           # BigFive 本地规则分析结果
enneagram_result: dict         # 九型人格本地规则分析结果
star_result: dict              # STAR 结构分析结果
mbti_result: dict             # MBTI 认知风格本地规则分析结果
llm_bigfive_output: dict       # LLM BigFive 分析结果（可选）
llm_enneagram_output: dict     # LLM 九型人格分析结果（可选）
personality_mapping_result: dict # 跨模型人格映射结果
```

原有字段（`mbti_analysis` / `mbti_knowledge` 等）保留，兼容两种命名。

---

### 6. `workflow/engine.py`

**变更类型**：新增工作流函数（改动最大）

#### 原有函数（`run_disc_workflow`）
- 保持 main 分支原逻辑不变
- 新增 `run_star_stage` 到 stage 链中（STAR 结构分析作为 DISC 辅助验证）
- 新增 `run_disc_stage`（DISC 维度综合评分）
- 移除原有的 `run_mbti_stage` 调用（MBTI 归入完整人格工作流）
- `build_response()` 新增 `apply_knowledge_graph` 参数

#### 新增函数

| 函数 | 说明 |
|------|------|
| `run_personality_workflow()` | 完整人格分析主入口 |
| `_run_disc_chain()` | DISC 分析链（parse → star → evidence → masking → disc → decision） |
| `_parallel_personality_stage()` | BigFive / Enneagram / MBTI 三个本地规则阶段并行执行（ThreadPoolExecutor） |
| `_run_llm_personality_stage()` | LLM BigFive + 九型并行分析（可选，依赖 OPENAI_API_KEY） |

#### 知识图谱加速层（新增）
- `workflow/knowledge_graph.py` 作为可选模块，在 `apply_knowledge_graph=True` 且模块可用时自动注入
- 功能：在响应层补充 MBTI 冲突检查和图谱加速效果报告
- 完全不侵入原有 stage 逻辑

#### `build_response()` 更新
新增返回字段：
```json
{
  "star_analysis": { ... },              // STAR 结构分析
  "bigfive_analysis": { ... },            // BigFive 大五人格
  "enneagram_analysis": { ... },         // 九型人格
  "personality_mapping": { ... },         // 跨模型映射
  "llm_bigfive_analysis": { ... },        // LLM 大五（可选）
  "llm_enneagram_analysis": { ... },     // LLM 九型（可选）
  "llm_status.personality_model": "...", // 新增
  "workflow.mode": "disc_with_personality",
  "workflow.version": "v0.4",
  "graph_boost": { ... }                  // 图谱加速报告（可选）
}
```

---

### 7. `workflow/helpers.py`

**变更类型**：追加新函数

```python
# ─── Personality analysis prompt builders ────────────────────────────────────

build_personality_payload()   # 构建 BigFive / Enneagram LLM 分析的统一 payload
build_bigfive_messages()      # 构建 BigFive LLM 调用消息
build_enneagram_messages()    # 构建九型人格 LLM 调用消息
```

---

## 二、新增的文件

### 新增分析引擎（`app/`）

| 文件 | 说明 | 行数 |
|------|------|------|
| `app/bigfive_engine.py` | BigFive 大五人格本地规则分析引擎 | ~320 |
| `app/enneagram_engine.py` | 九型人格本地规则分析引擎 | ~410 |
| `app/star_analyzer.py` | STAR 结构分析器（Situation/Task/Action/Result） | ~475 |
| `app/personality_mapping.py` | 跨模型人格映射（DISC ↔ BigFive ↔ 九型 ↔ MBTI） | ~425 |

### 新增知识库（`knowledge/`）

| 文件 | 说明 | 行数 |
|------|------|------|
| `knowledge/BIGFIVE.yaml` | BigFive 知识库：五维度（开放/尽责/外向/宜人/神经质）行为指标 | ~720 |
| `knowledge/ENNEAGRAM.yaml` | 九型人格知识库：九种类型的行为特征与面试信号 | ~860 |
| `knowledge/STAR.yaml` | STAR 行为面试知识库：结构完整度评分标准 | ~740 |
| `knowledge/STAR_IMPROVEMENTS.md` | STAR 知识库改进文档 | ~270 |

### 新增系统提示词（`prompts/`）

| 文件 | 说明 |
|------|------|
| `prompts/bigfive_system_prompt.txt` | BigFive LLM 分析系统提示词 |
| `prompts/enneagram_system_prompt.txt` | 九型人格 LLM 分析系统提示词 |

### 新增工作流 Stage（`workflow/stages/`）

| 文件 | 说明 |
|------|------|
| `workflow/stages/bigfive_stage.py` | BigFive 本地规则分析 Stage |
| `workflow/stages/enneagram_stage.py` | 九型人格本地规则分析 Stage |
| `workflow/stages/star_stage.py` | STAR 结构分析 Stage |
| `workflow/stages/personality_mapping_stage.py` | 跨模型人格映射 Stage |

### 新增知识图谱（`workflow/`）

| 文件 | 说明 |
|------|------|
| `workflow/knowledge_graph.py` | 知识图谱加速层（可选，提供冲突检测与加速效果报告） |

### 新增样式资源（`static/`）

| 文件 | 说明 |
|------|------|
| `static/knowledge_graph_timer.css` | 知识图谱计时器 CSS |
| `static/knowledge_graph_timer.js` | 知识图谱计时器 JS（可选 UI 增强） |

### 文档

| 文件 | 说明 |
|------|------|
| `CHANGELOG_PERSONALITY.md` | ywj 分支人格功能开发变更记录 |

---

## 三、接口变更总结

| 接口 | 变更 | 影响 |
|------|------|------|
| `POST /api/analyze` | **无变化** | 前端无需修改 |
| `POST /api/analyze/full` | **新增** | 需专门调用，触发完整人格分析 |

调用示例（`/api/analyze/full`）：
```json
POST /api/analyze/full
{
  "interview_transcript": "面试官：讲一个技术项目...",
  "job_hint_optional": "后端研发"
}
```

返回结构额外包含：
- `star_analysis` — STAR 结构评分与缺陷
- `bigfive_analysis` — BigFive 五维度评分
- `enneagram_analysis` — 九型人格类型及分数
- `personality_mapping` — 跨模型一致性映射
- `graph_boost` — 知识图谱加速效果（如启用）

---

## 四、前端兼容性

**完全兼容，前端无需任何修改。**

- `static/app.js` — 保持 main 分支版本不变 ✅
- `static/index.html` — 保持 main 分支版本不变 ✅
- `static/styles.css` — 保持 main 分支版本不变 ✅

---

## 五、版本信息

| 项目 | 原值 | 新值 |
|------|------|------|
| `workflow.version` | `v0.3` | `v0.4` |
| `workflow.mode` | `disc+mbti` | `disc_with_personality` |
| `llm_status.personality_model` | 无 | 有（`gpt-5-mini`） |

---

## 六、依赖新增

新增 Python 依赖（标准库，无需额外安装）：
- `concurrent.futures.ThreadPoolExecutor` — 并行阶段执行

如启用知识图谱加速，需确保 `workflow/knowledge_graph.py` 可导入。
