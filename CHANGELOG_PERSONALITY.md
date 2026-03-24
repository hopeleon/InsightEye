# 人格分析模块变更记录

> 本文档记录 2026-03-24 本次会话中新增/修改的所有文件及其变更内容。
> 下次遇到问题时，可根据此文档还原或修复。

---

## 一、新增文件

### 1. 知识库文件

#### `knowledge/BIGFIVE.yaml`
- 大五人格（OCEAN）完整知识库，724 行
- 包含 5 个维度（O 开放性、C 尽责性、E 外向性、A 宜人性、N 神经质）
- 每个维度包含：核心动机、语言线索（强/弱关键词、语义模式、句法特征、话语特征）、反线索、常见误判来源、特征规则（强阳性/软阳性/阴性）、得分解读、追问问题
- 包含跨维度组合模式（8 种）、风险标记、内部置信度规则

#### `knowledge/ENNEAGRAM.yaml`
- 九型人格（Type 1-9）完整知识库，864 行
- 包含 9 种类型，每种类型定义：核心恐惧、核心欲望、核心动机、基本弱点、访谈语言签名、行为线索、区分标记、特征规则、追问问题
- 包含侧翼推断映射表（9 种主型 × 各 2 种侧翼，共 18 种组合）
- 包含 DISC→九型映射表
- 包含风险标记（Type3 过度包装、Type6 一致性不足、Type9 自我淡化等）

### 2. LLM 提示词文件

#### `prompts/bigfive_system_prompt.txt`
- Big Five LLM 分析 System Prompt
- 包含 Big Five 五维度简介、分析原则、置信度指南
- 指定 JSON 输出格式（scores、dominant_trait、trait_interpretations、cross_dimension_patterns、confidence_adjustments、internal_risk_flags、supplemental_probes）

#### `prompts/enneagram_system_prompt.txt`
- 九型人格 LLM 分析 System Prompt
- 包含九型类型速查表、分析原则、置信度指南
- 指定 JSON 输出格式（primary_type、secondary_type、wing、top_two_types、motivational_pattern、workplace_implications、risk_flags、supplemental_probes）

### 3. Python 引擎文件

#### `app/bigfive_engine.py`
- Big Five 本地规则评分引擎（无 LLM）
- 5 个维度（O/C/E/A/N），各维度独立的阈值评分规则 + 关键词命中加分
- 关键函数：`analyze_bigfive(transcript, turns, features, knowledge)`
- 包含 `_detect_cross_patterns()`：自动识别 8 种跨维度组合模式
- 包含 `_n_artifacts_detection()`：识别神经质维度的面试情境假象

#### `app/enneagram_engine.py`
- 九型人格本地规则评分引擎（无 LLM）
- 9 种类型，每种类型的 `_TYPE_FEATURE_RULES` 规则矩阵 + 关键词列表
- 输出 Top-2 类型、侧翼推断、置信度评估、风险标记
- 关键函数：`analyze_enneagram(transcript, turns, features, knowledge)`

#### `app/personality_mapping.py`
- 跨模型人格映射 Agent（纯 Python，无 LLM 调用）
- 三层映射矩阵：
  - `DISC_TO_BIGFIVE_MATRIX`：DISC→BigFive 映射（4×5=20 条规则）
  - `BIGFIVE_TO_ENNEAGRAM`：BigFive→九型映射（12 条组合条件规则）
  - `DISC_TO_ENNEAGRAM`：DISC→九型映射（12 条直接映射）
- 置信度影响规则：BigFive-N 高→STAR 真实性降权；Enneagram-Type3 高 + story_richness 低→面试伪装风险
- 关键函数：`map_personality(disc_result, bigfive_result, enneagram_result, features)`

### 4. Workflow Stage 文件

#### `workflow/stages/bigfive_stage.py`
- `run_bigfive_stage(context)`：调用 `bigfive_engine.analyze_bigfive()`

#### `workflow/stages/enneagram_stage.py`
- `run_enneagram_stage(context)`：调用 `enneagram_engine.analyze_enneagram()`

#### `workflow/stages/personality_mapping_stage.py`
- `run_personality_mapping_stage(context)`：调用 `personality_mapping.map_personality()`

---

## 二、修改文件

### `app/config.py`
**变更内容**：新增 7 个常量（路径常量 4 个 + 运行时变量 2 个 + 默认值 1 个）
```python
# 路径常量
BIGFIVE_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "BIGFIVE.yaml"
BIGFIVE_PROMPT_PATH = PROMPTS_DIR / "bigfive_system_prompt.txt"
ENNEAGRAM_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "ENNEAGRAM.yaml"
ENNEAGRAM_PROMPT_PATH = PROMPTS_DIR / "enneagram_system_prompt.txt"
# 默认值
DEFAULT_OPENAI_PERSONALITY_MODEL = "gpt-5.4"
# 运行时变量（支持 local_settings.py 和环境变量覆盖）
OPENAI_PERSONALITY_MODEL = str(local_settings.get(
    "OPENAI_PERSONALITY_MODEL",
    os.getenv("OPENAI_PERSONALITY_MODEL", DEFAULT_OPENAI_PERSONALITY_MODEL)
)).strip()
```

### `app/knowledge.py`
**变更内容**：新增 4 个函数（与 `load_disc_knowledge()` 结构完全一致）
```python
@lru_cache(maxsize=1)
def load_bigfive_knowledge() -> dict

@lru_cache(maxsize=1)
def load_bigfive_prompt() -> str

@lru_cache(maxsize=1)
def load_enneagram_knowledge() -> dict

@lru_cache(maxsize=1)
def load_enneagram_prompt() -> str
```

### `app/server.py`
**变更内容**：在 `do_POST()` 中新增路由分发，支持 `/api/analyze/full`
```python
if route == "/api/analyze/full":
    report = analyze_interview_full(transcript, job_hint)
else:
    report = analyze_interview(transcript, job_hint)
```
新增端点：`POST /api/analyze/full` → 完整人格分析（DISC + BigFive + 九型 + 跨模型映射）

### `app/analysis.py`
**变更内容**：新增 `analyze_interview_full()` 函数，暴露 `run_personality_workflow()`
```python
def analyze_interview_full(transcript: str, job_hint: str = "") -> dict:
    """完整人格分析：DISC + Big Five + 九型人格 + 跨模型映射。"""
    return run_personality_workflow(transcript=transcript, job_hint=job_hint)
```

### `workflow/context.py`
**变更内容**：在 `WorkflowContext` dataclass 中新增 5 个字段
```python
bigfive_result: dict[str, Any] | None = None
enneagram_result: dict[str, Any] | None = None
personality_mapping_result: dict[str, Any] | None = None
llm_bigfive_output: dict[str, Any] | None = None
llm_enneagram_output: dict[str, Any] | None = None
```

### `workflow/engine.py`
**变更内容**：
1. `build_response()` 新增 6 个字段：`bigfive_analysis`、`enneagram_analysis`、`personality_mapping`、`llm_bigfive_analysis`、`llm_enneagram_analysis`、`personality_model` in `llm_status`
2. `run_disc_workflow()` 保持不变
3. 新增 `run_personality_workflow()` 函数：完整人格分析管道（parse→feature→disc→bigfive→enneagram→mapping→llm）
4. 新增 `_run_llm_personality_stage()` 函数：可选的 LLM BigFive 和 Enneagram 分析

### `workflow/helpers.py`
**变更内容**：新增 3 个函数
```python
def build_personality_payload(...) -> dict      # 构建共享 payload
def build_bigfive_messages(...) -> list[dict]  # Big Five LLM prompt builder
def build_enneagram_messages(...) -> list[dict] # 九型 LLM prompt builder
```

---

## 三、API 端点说明

| 端点 | 方法 | 用途 |
|---|---|---|
| `POST /api/analyze` | 原有 | DISC 行为风格分析 |
| `POST /api/analyze/full` | 新增 | DISC + Big Five + 九型 + 跨模型映射 |

---

## 四、输出结构（`/api/analyze/full`）

```json
{
  "bigfive_analysis": {
    "scores": { "O": int, "C": int, "E": int, "A": int, "N": int },
    "dominant_trait": "C",
    "secondary_traits": ["O", "E"],
    "cross_dimension_patterns": [...],
    "trait_interpretations": { ... },
    "evidence_summary": { ... },
    "supplemental_probes": [...]
  },
  "enneagram_analysis": {
    "primary_type": { "type_number": "3", "label": "成就者", ... },
    "secondary_type": { ... },
    "wing": "3w4 或 3w2",
    "top_two_types": [...],
    "motivational_pattern": { ... },
    "risk_flags": [...],
    "supplemental_probes": [...]
  },
  "personality_mapping": {
    "cross_mapping": {
      "disc_to_bigfive": [...],
      "bigfive_to_enneagram": [...],
      "disc_to_enneagram": [...]
    },
    "integrated_personality_profile": {
      "primary_style_label": "D/C 高效行动型",
      "primary_style_description": "兼具主导决策力和结构严谨性...",
      "bigfive_integration": { ... },
      "disc_integration": { ... }
    },
    "confidence_adjustments": [
      { "target": "STAR_authenticity", "direction": "down", "amount": "medium", "reason": "..." }
    ]
  },
  "llm_bigfive_analysis": { ... },   // LLM 分析结果（需 API Key）
  "llm_enneagram_analysis": { ... }  // LLM 分析结果（需 API Key）
}
```

---

## 五、已知注意事项

1. **N 维度（神经质）不对外展示**：仅作为内部风险参考，不出现在面向面试官的标签中
2. **九型侧翼推断需较多样本**：当 Top-2 类型得分差 < 8 分时，置信度自动降为 low
3. **YAML 字符串必须以双引号闭合**：撰写知识库 YAML 时，所有 `- "` 开头的行必须以 `"` 结尾，不能跨行
4. **personality_mapping 不依赖 LLM**：跨模型映射 Agent 是纯规则矩阵，无需 API Key 即可运行

---

## 六、下次遇到问题的排查路径

### 问题1：YAML 解析错误
- 检查 `knowledge/BIGFIVE.yaml` 和 `knowledge/ENNEAGRAM.yaml` 中是否有未闭合的字符串（以 `- "` 开头但不以 `"` 结尾的行）
- 运行：`python -c "import yaml; yaml.safe_load(open('knowledge/BIGFIVE.yaml'))"`

### 问题2：导入错误
- 确认 `app/config.py` 中 `BIGFIVE_KNOWLEDGE_PATH` 等常量已正确定义
- 确认 `workflow/context.py` 中新字段已添加到 `WorkflowContext` dataclass

### 问题3：集成测试失败
- 确认 `personality_mapping.py` 中 `DISC_TO_BIGFIVE_MATRIX` 的元组为 4 元素 `(sig, dim, weight, reason)`，而非 5 元素
- 确认 `enneagram_engine.py` 中 `abstraction_level` 字符串值（`"abstract"`/`"grounded"`）的转换逻辑正确

### 问题3：人格分析 API 报 404
- 确认 `app/server.py` 中 `do_POST()` 已更新路由分发逻辑，`/api/analyze/full` 路由已注册

### 问题4：服务启动时报 `ImportError: cannot import name 'OPENAI_PERSONALITY_MODEL'`
- **原因**：`workflow/engine.py` 导入 `OPENAI_PERSONALITY_MODEL`（运行时变量），但 `app/config.py` 只定义了默认值常量 `DEFAULT_OPENAI_PERSONALITY_MODEL`，漏掉了运行时变量
- **修复**：在 `app/config.py` 末尾添加：
  ```python
  OPENAI_PERSONALITY_MODEL = str(local_settings.get(
      "OPENAI_PERSONALITY_MODEL",
      os.getenv("OPENAI_PERSONALITY_MODEL", DEFAULT_OPENAI_PERSONALITY_MODEL)
  )).strip()
  ```

---

## 三、STAR 分析引擎实现（2026-03-24 补充）

### 新增文件

#### `app/star_analyzer.py`
- 基于 `STAR.yaml` 知识库的本地规则评分引擎（无需 LLM）
- 职责：S/T/A/R 四维度独立评分、6 类缺陷检测、真实性综合评分、置信度判定、追问生成、缺陷交互规则
- 关键函数：`analyze_star(transcript, turns, features, knowledge)`
- 核心逻辑：
  - `_score_dimension()`：从 features.py 提取的 `star_X_score` 出发，结合 YAML strong_keywords 命中数、counter_hits 惩罚、句法加分，最终输出 0~100 分
  - `_detect_defects()`：检测 6 类缺陷（fake_star / team_substitution / situation_missing / result_attribution_error / action_vague / result_abstract），按 high/medium/low 去重排序
  - `_detect_defect_interactions()`：读取 YAML `global_rules.defect_interactions`，检测高阶组合并输出结论
  - `_build_followups()`：从 YAML `followup_probes` 选取追问，按缺陷类型轮换去重
  - `_confidence_level()`：综合样本量、维度分、缺陷严重度，判定 low/medium/high
  - `_disc_auxiliary_signals()`：生成 STAR→DISC 交叉信号，影响 DISC 评分置信度

#### `workflow/stages/star_stage.py`
- `run_star_stage(context)`：调用 `star_analyzer.analyze_star()`，结果存入 `context.star_result`

### 修改文件

#### `app/features.py`
**变更内容**：大幅扩展，核心新增：
- 9 个 STAR.yaml `[待实现]` 特征全部补全：`quantitative_words_ratio`、`temporal_words_ratio`、`constraint_words_ratio`、`vague_result_words_ratio`、`tool_method_words_ratio`、`step_connector_ratio`、`context_marker_density`、`result_attribution_self_ratio`、`team_result_attribution_ratio`
- STAR 四维度独立评分函数 `_star_feature()`：对 S/T/A/R 各维度的 strong/weak 关键词命中数分别统计并输出 0~1 分数
- 新增 9 个词表：`QUANTITATIVE_WORDS`、`TEMPORAL_WORDS`、`CONSTRAINT_WORDS`、`VAGUE_RESULT_WORDS`、`TOOL_METHOD_WORDS`、`STEP_CONNECTOR_WORDS`、`CONTEXT_MARKER_WORDS`、`RESULT_ATTRIBUTION_SELF_WORDS`、`TEAM_RESULT_WORDS`
- 新增内部字段（`_` 前缀）：`_star_s_raw`、`_star_t_raw`、`_star_a_raw`、`_star_r_raw`、`_self_count`、`_team_count`、`_self_team_ratio`、`_pronoun_counts`、`_keyword_counts`
- `feature_highlights()` 输出增强：新增 S/T/A/R 独立分和步骤连接词密度

#### `app/disc_engine.py`
**变更内容**：
- `analyze_disc()` 新增 `star_result` 参数（可选）
- `_build_critical_findings()` 新增 `star_result` 参数，STAR 分析结果融入 DISC 关键发现：
  - STAR 置信度 low → 降低整体可信度
  - STAR-S < 40 → 情境缺失，提升 critical finding
  - STAR-R < 40 → 结果空洞，高严重度
  - `star_disc_auxiliary_signals` → 加入 evidence_gaps

#### `workflow/engine.py`
**变更内容**：
- `run_disc_workflow()` stage 顺序：`run_feature_stage` → `run_star_stage` → `run_disc_evidence_stage`（STAR 在 DISC 证据之前）
- `run_personality_workflow()` 同理
- `build_response()` 输出新增 `star_analysis` 字段

#### `workflow/context.py`
**变更内容**：`WorkflowContext` 新增字段 `star_result: dict[str, Any] | None = None`

#### `app/config.py`
**变更内容**：新增 `STAR_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "STAR.yaml"`

#### `app/knowledge.py`
**变更内容**：新增 `load_star_knowledge()` 函数（`@lru_cache` 装饰）

#### `workflow/stages/disc_evidence_stage.py`
**变更内容**：`analyze_disc()` 调用传入 `star_result=context.star_result`

### 重要修复

#### `knowledge/STAR.yaml` 语法修复
- **问题**：第 158-160 行 `negative_or_counter_cues.lexical` 列表项 `"后来"（直接跳到结果，跳过背景）` 的引号在内部中文括号处提前闭合
- **修复**：将 3 个条目改为转义写法 `"\u201c后来\u201d（直接跳到结果，跳过背景）"`

### API 输出结构（STAR 部分）

```json
{
  "star_analysis": {
    "dimension_scores": {
      "S": {"score": 79, "band": "high", "interpretation": "...", "evidence_summary": {...}},
      "T": {"score": 18, "band": "low", "interpretation": "..."},
      "A": {"score": 30, "band": "low", "interpretation": "..."},
      "R": {"score": 84, "band": "high", "interpretation": "..."}
    },
    "overall_score": 54.45,
    "defects": [
      {"defect_id": "fake_star", "severity": "medium", "label": "假 STAR（结构残缺）", "reason": "..."},
      {"defect_id": "action_vague", "severity": "medium", "label": "行动空洞", "reason": "..."}
    ],
    "authenticity_summary": {
      "overall": 54.45,
      "confidence": "medium",
      "confidence_notes": ["缺陷与强信号并存..."],
      "risk_signals": [...],
      "anti_overclaim_notes": [...]
    },
    "star_disc_auxiliary_signals": ["[STAR→DISC] ..."],
    "followup_questions": [...],
    "defect_interactions": [...],
    "meta": {...}
  }
}
```

---

## 四、已知注意事项

1. **STAR 必须在 DISC 之前运行**：因为 `analyze_disc()` 需要 `star_result`，stage 顺序固定为 parse→feature→star→disc_evidence→masking→disc→decision
2. **STAR 不对外展示 N 维度**（大五神经质）：仅内部风险参考，不出现在面向面试官的标签中
3. **STAR.yaml 字符串闭合规范**：所有 `- "` 开头的行必须以 `"` 结尾，字符串内部的中文括号 `（）` 不影响，但中文引号 `""` 会导致提前闭合，需转义

---

## 四、次要人格映射前端展示（2026-03-24 补充）

### 修改文件

#### `static/index.html`
- 在 `.workflow-row` 之后、`<details class="detail-panel">` 之前插入 `<div class="personality-row">` 行
- 包含 3 个面板：`大五人格`、`九型人格`、`STAR 结构分析`
- 每个面板各自对应一个 DOM id（`bigfiveCards`、`enneagramCards`、`starCards`）

#### `static/app.js`
**变更内容**：
- 新增 `BIGFIVE_LABELS` 常量映射：大五 5 个维度的中文标签与描述
- 新增 `ENNEAGRAM_LABELS` 常量映射：九型 9 个类型的编号、名称与描述
- 新增 `renderPersonalitySecondary(report)` 函数：
  - 渲染 `bigfiveCards`：5 个维度的百分比条 + band 标签 + 行为假设（取前 2 条）
  - 渲染 `enneagramCards`：九型主类型（高亮展示） + 次要类型列表 + 跨模型笔记
  - 渲染 `starCards`：S/T/A/R 四维度得分条（高/中/低分别对应红/橙/绿）+ 前 3 条缺陷 + 真实性置信度
- `renderReport()` 中新增调用：`renderPersonalitySecondary(report)`，位于 `renderWorkflow(report)` 之前
- `DEFAULT_REPORT` 新增模拟数据：
  - `star_analysis`：四维度模拟评分、缺陷列表、真实性摘要
  - `bigfive_analysis`：5 维度百分比、排名、行为假设
  - `enneagram_analysis`：九型 top3 类型描述、跨模型笔记
- `workflow.stage_trace` 新增 `star_stage` 节点

#### `static/styles.css`
**变更内容**：
- `.personality-row`：三列等宽 grid 布局（`1fr 1fr 1fr`），与 `.metric-row` 并列
- `.personality-cards`：内嵌 grid 子布局
- `.personality-dim`：每行含标签 + 分值 + 进度条 + band 徽章
- `.personality-dim-bar`：4px 高进度条，蓝色
- `.personality-star-item`：带左侧彩色边框区分严重度（红/橙/绿）
- `.personality-row` 加入全局 grid display 声明

### 渲染顺序

```
renderDecisionLayer  →  renderMetricsLayer
       ↓
renderPersonalitySecondary  →  ⭐ 大五 / 九型 / STAR 次要映射（新增）
       ↓
renderWorkflow  →  工作流阶段 / DISC证据 / 伪装扫描 / 决策载荷
       ↓
renderInterviewOverview  →  面试结构速览
       ↓
renderDetailedLayer  →  维度详情 / 关键缺陷 / 证据缺口 / 行为假设 / 原子特征 / 追问 / 模型状态与原始返回
```

---

## 五、下次遇到问题的排查路径（补充）

### 问题5：STAR 分析结果为空
- 确认 `workflow/engine.py` 中 `run_star_stage` 已加入 stage 列表
- 确认 `run_disc_workflow` 顺序：STAR stage 必须在 `run_disc_evidence_stage` 之前

### 问题6：`star_result is None` 导致 DISC critical findings 崩溃
- `analyze_disc()` 中访问 `star_result` 使用 `star_result.get(...)` 而非直接下标访问，`star_result` 可为 None

### 问题7：STAR.yaml YAML 解析错误
- 运行 `python -c "import yaml; yaml.safe_load(open('knowledge/STAR.yaml', encoding='utf-8'))"`
- 检查所有 `- "` 开头的行是否正确闭合，内部是否有未转义的 `"` 字符
