# STAR 分析：有 STAR.yaml 知识库 vs 无 STAR.yaml 的对比

> 本文档记录 STAR 分析引擎在引入 `knowledge/STAR.yaml` 知识库前后的能力差异。

---

## 一、能力对比总表

| 评估维度 | 无 STAR.yaml（仅 features.py 关键词计数） | 有 STAR.yaml（完整 STAR 分析引擎） | 提升说明 |
|---|---|---|---|
| **S/T/A/R 独立评分** | ❌ 无。只有一个 0~1 的 `star_structure_score`，代表"覆盖了几个关键词桶" | ✅ 四维度各自分数（0~100），独立评分 | 从粗糙覆盖率到完整结构诊断 |
| **评分依据** | 固定 4 个桶 × 约 17 个词，无权重区分 | 强/弱关键词独立统计 + 句法加分 + 反线索惩罚 + YAML 命中加权 | 从"有没有"到"有多好" |
| **缺陷检测类型** | ❌ 无缺陷检测 | ✅ 检测 6 类：假 STAR、团队代答、情境缺失、结果归因、行动空洞、结果泛化 | 从 0 到完整的质量评估体系 |
| **缺陷严重度** | ❌ 无 | ✅ high / medium / low 三级，并按严重度排序 | 可区分风险优先级 |
| **缺陷交互规则** | ❌ 无 | ✅ 4 种高阶组合触发规则（如 fake_star + result_attribution_error → 高风险） | 发现单一缺陷无法捕捉的组合风险 |
| **追问生成** | ❌ 无 | ✅ 每种缺陷 5 条，按轮次轮换、去重 | 从无法追问到完整追问体系 |
| **真实性综合评分** | ❌ 无 | ✅ A 35% + R 35% + S 15% + T 15% 加权（与 STAR.yaml 一致） | 从无到有，可量化回答质量 |
| **置信度判定** | ⚠️ 借用 DISC 的 confidence_level，与 STAR 逻辑无关 | ✅ 独立 low/medium/high，与 STAR.yaml confidence_rules 一致 | 判定结果的可信程度 |
| **防过度声明** | ❌ 无 | ✅ 输出 `anti_overclaim_notes`（YAML原文），提示面试官避免误读 | 防止高分低能误判 |
| **STAR→DISC 辅助信号** | ❌ 无。STAR 仅作为 DISC 的辅助输入，但实际无辅助 | ✅ S/T/A/R 分数直接影响 DISC critical findings，降低高 STAR-R + 低 S 场景下 D 置信度等 | 从"名字叫辅助"到"真正辅助" |
| **特征覆盖率** | 仅 17 个词分 4 桶 | 9 个 STAR.yaml [待实现] 特征全部补全 + 6 个内部辅助特征 | 特征数量从 ~17 词到 ~120+ 词 + 多维度统计 |
| **量化指标检测** | ❌ 无 | ✅ `quantitative_words_ratio`、`vague_result_words_ratio` | 区分"提升了3倍"和"效果不错" |
| **时间/约束检测** | ⚠️ 简单包含"当时"等 | ✅ `temporal_words_ratio`、`constraint_words_ratio`、`context_marker_density` | 区分"有背景"和"背景具体" |
| **步骤结构检测** | ❌ 无 | ✅ `step_connector_ratio` | 判断回答是否有过程有步骤 |
| **工具/方法检测** | ❌ 无 | ✅ `tool_method_words_ratio` | 判断行动是否具体可验证 |
| **团队/个人区分** | ⚠️ 仅 `self_vs_team_orientation`（布尔值） | ✅ `_self_team_ratio`（数值比值）+ `team_result_attribution_ratio`（归因比例） | 从二元判断到比例评估 |
| **结果归因检测** | ❌ 无 | ✅ `result_attribution_self_ratio`、`team_result_attribution_ratio` | 区分"我的功劳"和"团队的功劳" |
| **知识库可维护性** | ❌ 无。关键词硬编码在 features.py | ✅ 知识库独立为 YAML，随时可增删关键词/规则/追问 | 从代码耦合到知识驱动 |
| **前端展示标签** | ⚠️ 只有 `star_structure_score` 一个数字 | ✅ 缺陷带中文标签（S/T/A/R 带 band 描述）、追问独立输出、风险信号列表 | 从数字到可读报告 |
| **CHANGELOG 记录** | ❌ 无 | ✅ `CHANGELOG_PERSONALITY.md` 完整记录实现过程和排查路径 | 可追溯、可维护 |

---

## 二、关键差异示例

### 示例：同一段回答的评分对比

> 候选人回答："当时我们项目遇到了问题，我优化了一下，效果还不错。"

#### 无 STAR.yaml

| 输出字段 | 值 | 说明 |
|---|---|---|
| `star_structure_score` | `0.50` | 4 个桶中命中了 2 个（situation=1, result=1），50% |
| `star_hits` | `{"situation": 1, "task": 0, "action": 0, "result": 1}` | 勉强有情境和结果 |
| 缺陷 | 无 | 系统不知道这段回答质量差 |
| 追问 | 无 | 无法生成追问 |

#### 有 STAR.yaml

| 输出字段 | 值 | 说明 |
|---|---|---|
| `dimension_scores.S` | ~50 | 有"当时"，但无约束条件 |
| `dimension_scores.T` | ~20 | 全程无"我的职责/目标"，"我优化"也非角色声明 |
| `dimension_scores.A` | ~25 | "优化"是弱关键词，无宾语，step_connector=0 |
| `dimension_scores.R` | ~20 | "效果不错"是泛化词，无数字 |
| `overall_score` | ~30 | 综合质量差 |
| `defects` | `fake_star(high)`, `action_vague(high)`, `result_abstract(high)` | 三高缺陷，真实性极低 |
| `followup_questions` | "你说的「优化了」，具体优化了什么？原来是什么状态，推进后又是什么状态？" | 精准追问空洞行动 |
| `star_disc_auxiliary_signals` | "A 维度过高但 S 维度极低，D 特征置信度需下调" | 提示 DISC 不要过度相信这段回答 |

---

## 三、STAR 分析在 DISC 工作流中的位置

### 3.1 整体工作流（STAR 作为 DISC 的结构验证层）

```mermaid
flowchart TB
    subgraph INPUT["📥 输入层"]
        TRANSCRIPT["候选人逐字稿"]
    end

    subgraph EXTRACT["🔍 特征提取层  features.py"]
        ATOMIC["原子特征\n30+ 维度"]
        STAR_FEATURES["STAR 专用特征\n9 个新增特征"]
    end

    subgraph STAR_ENGINE["⭐ STAR 分析引擎  star_analyzer.py"]
        STAR_YAML["STAR.yaml\n知识库"]
        DIM_SCORE["S/T/A/R 独立评分\n0~100"]
        DEFECT_DETECT["6 类缺陷检测\nhigh/medium/low"]
        DEFECT_INTERACT["缺陷交互规则\n4 种高阶组合"]
        FOLLOWUP["追问生成\n按缺陷轮换"]
        AUTH["真实性综合评分\nA×35% R×35% S×15% T×15%"]
        CONF["置信度判定\nlow/medium/high"]
        DISC_SIGNALS["STAR→DISC 辅助信号"]
        ANTI_CLAIM["防过度声明"]
    end

    subgraph DISC_ENGINE["📊 DISC 分析引擎  disc_engine.py"]
        DISC_SCORE["四维度评分\nD/I/S/C"]
        CRITICAL["Critical Findings\n关键发现"]
        EVIDENCE_GAPS["Evidence Gaps\n证据缺口"]
        RECOMMEND["录用建议"]
    end

    subgraph OUTPUT["📤 输出层"]
        FINAL["综合报告\nDISC + STAR 融合结果"]
    end

    TRANSCRIPT --> ATOMIC
    TRANSCRIPT --> EXTRACT
    ATOMIC --> STAR_FEATURES
    STAR_FEATURES --> DIM_SCORE
    STAR_YAML --> DIM_SCORE
    STAR_YAML --> DEFECT_DETECT
    STAR_YAML --> DEFECT_INTERACT
    STAR_YAML --> FOLLOWUP
    STAR_YAML --> AUTH
    STAR_YAML --> CONF
    STAR_YAML --> ANTI_CLAIM

    DIM_SCORE --> DISC_SIGNALS
    DEFECT_DETECT --> DISC_SIGNALS
    AUTH --> DISC_SIGNALS
    DISC_SIGNALS --> CRITICAL

    ATOMIC --> DISC_SCORE
    DISC_SCORE --> CRITICAL
    CRITICAL --> EVIDENCE_GAPS
    EVIDENCE_GAPS --> RECOMMEND
    ANTI_CLAIM --> FINAL
    RECOMMEND --> FINAL
    DEFECT_DETECT --> FINAL
    FOLLOWUP --> FINAL

    style STAR_ENGINE fill:#1a3a5c,color:#fff,stroke:#4fc3f7,stroke-width:2px
    style STAR_YAML fill:#004d40,color:#fff,stroke:#4db6ac,stroke-width:2px
    style DISC_SIGNALS fill:#1a3a5c,color:#fff,stroke:#4fc3f7,stroke-width:2px
```

**流程说明：**
- `star_stage` 必须在 `disc_evidence_stage` 之前执行，因为 DISC 引擎需要读取 `star_result`
- STAR 输出的 **STAR→DISC 辅助信号** 会修改 `critical_findings` 的严重度和 `evidence_gaps` 的内容
- 防过度声明（`anti_claim_notes`）直接透传到最终报告，提醒面试官避免误读

---

### 3.2 STAR→DISC 辅助信号的交叉影响

```mermaid
flowchart LR
    subgraph STAR_RESULT["STAR 分析结论"]
        S_LOW["S 情境 < 40\n→ 情境缺失"]
        T_LOW["T 任务 < 40\n→ 角色模糊"]
        A_LOW["A 行动 < 40\n→ 行动空洞"]
        R_LOW["R 结果 < 40\n→ 结果泛化"]
        AUTH_LOW["authenticity\nconfidence = low"]
        DEFECT_FAKESTAR["假 STAR\n高严重度"]
        DEFECT_TEAM["团队代答\n中严重度"]
        DEFECT_ATTR["归因存疑\n高严重度"]
    end

    subgraph DISC_IMPACT["对 DISC 评分的影响"]
        direction TB
        C_UP["C 高置信度 ↑\nS 强 → C 分可信"]
        C_DOWN["C 下调风险\nS 缺失 → 结构性可疑"]
        D_DOWN["D 下调风险\nA 高但 S 低 → 冒进冲动"]
        IS_UP["I/S 下调风险\nteam_substitution + R 低\n→ 社交叙事掩盖空洞"]
        BUY_RISK["整体录用风险 ↑\nhigh severity defects ≥ 2\n→ 需重点追问"]
    end

    subgraph OUTPUT["输出修改"]
        ADD_FINDING["新增/升级\ncritical_findings"]
        ADD_GAP["追加\nevidence_gaps"]
        ADD_RISK["追加\nhire_risks"]
        REDUCE_DISC["DISC 置信度\n降级处理"]
    end

    S_LOW --> C_UP
    S_LOW --> C_DOWN
    A_LOW --> D_DOWN
    R_LOW --> IS_UP
    AUTH_LOW --> BUY_RISK
    DEFECT_FAKESTAR --> BUY_RISK
    DEFECT_TEAM --> IS_UP
    DEFECT_ATTR --> BUY_RISK

    C_DOWN --> ADD_FINDING
    D_DOWN --> ADD_FINDING
    IS_UP --> ADD_FINDING
    BUY_RISK --> ADD_RISK
    BUY_RISK --> REDUCE_DISC

    style STAR_RESULT fill:#1a3a5c,color:#fff,stroke:#4fc3f7
    style DISC_IMPACT fill:#1b2e47,color:#fff,stroke:#81d4fa
    style OUTPUT fill:#2c1810,color:#fff,stroke:#ff8a65
    style BUY_RISK fill:#7b0000,color:#fff,stroke:#ef5350
```

---

### 3.3 STAR 引擎内部评分流程

```mermaid
flowchart TB
    subgraph IN["输入"]
        TEXT["候选人回答文本"]
        TURNS["轮次列表\nquestion_type"]
        FEATURES["features.py 原子特征"]
        YAML["STAR.yaml 知识库"]
    end

    subgraph DIM["四维度独立评分  _score_dimension()"]
        S_SCORER["S 情境评分\ntemporal_ratio + constraint_ratio + YAML关键词命中"]
        T_SCORER["T 任务评分\nself_team_ratio + YAML关键词命中"]
        A_SCORER["A 行动评分\nstep_connector + tool_method + 强/弱动词对比"]
        R_SCORER["R 结果评分\nquantitative_ratio + 归因比例 + 泛化词惩罚"]
    end

    subgraph DEFECT["缺陷检测  _detect_defects()"]
        FAKE["假 STAR\n综合分 & R 分双低"]
        TEAM["团队代答\n'我们'≥5 且 '我'≤2"]
        SIT["情境缺失\n无时间词 且 字数<80"]
        ATTR["结果归因\nteam_attr & self_attr 同时偏高"]
        ACT["行动空洞\n强行动词=0 且 无步骤连接词"]
        RES["结果泛化\n无数字词 且 有泛化词"]
    end

    subgraph HIGH["高阶处理"]
        INTERACT["缺陷交互\n触发组合规则 → 输出结论"]
        FOLLOWUP["追问生成\n按缺陷类型 + 去重轮换"]
        CONF["置信度判定\nlow/medium/high"]
        ANTI["防过度声明\nanti_overclaim_notes"]
    end

    subgraph OUT["输出"]
        DIM_OUT["dimension_scores\n{S: {...}, T: {...}, A: {...}, R: {...}}"]
        AUTH["authenticity_summary\noverall + confidence + risk_signals"]
        DISC_SIG["star_disc_auxiliary_signals"]
        DEFECTS["defects\n含 severity + label + reason"]
        FOLLOW["followup_questions\n含 defect_id + purpose"]
        INTER["defect_interactions\n触发组合 + 结论"]
    end

    IN --> DIM
    YAML --> DIM
    YAML --> DEFECT
    YAML --> HIGH
    DIM --> DEFECT
    DIM --> HIGH
    DEFECT --> INTERACT
    DEFECT --> FOLLOWUP
    HIGH --> OUT

    style IN fill:#1a3a5c,color:#fff,stroke:#4fc3f7
    style DIM fill:#004d40,color:#fff,stroke:#4db6ac
    style DEFECT fill:#4a148c,color:#fff,stroke:#ce93d8
    style HIGH fill:#1b2e47,color:#fff,stroke:#81d4fa
    style OUT fill:#1a3a5c,color:#fff,stroke:#4fc3f7
```

---

### 3.4 关键文件对应关系

| 步骤 | 源文件 | 输出字段 | 消费方 |
|---|---|---|---|
| 特征提取 | `app/features.py` | `star_s_score` / `temporal_words_ratio` 等 | `app/star_analyzer.py` |
| STAR 评分 | `app/star_analyzer.py` | `dimension_scores.S/T/A/R` | `app/disc_engine.py` |
| STAR 缺陷 | `app/star_analyzer.py` | `defects` / `authenticity_summary` | `app/disc_engine.py` |
| STAR→DISC | `app/star_analyzer.py` | `star_disc_auxiliary_signals` | `app/disc_engine.py` |
| DISC 融合 | `app/disc_engine.py` | `critical_findings` / `evidence_gaps` | `workflow/engine.py` |
| 最终输出 | `workflow/engine.py` | `star_analysis` + `disc_analysis` | API / 前端 |

---

## 四、知识点睛

- **无 STAR.yaml 的 STAR 分析**：本质是一个"关键词有没有出现"的覆盖率指标，与真正的行为面试 STAR 评分体系（情境→任务→行动→结果 四个独立维度）完全不同。
- **有 STAR.yaml 的 STAR 分析**：完全基于 STAR.yaml 知识库驱动，代码只是执行规则引擎，关键词、追问模板、缺陷定义、置信度规则全部由 YAML 维护，无需改代码即可迭代。
