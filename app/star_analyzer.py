"""
STAR 分析引擎 — 基于 STAR.yaml 知识库的本地规则评分引擎。

职责：
1. 基于 features.py 提取的原子特征，对 S/T/A/R 四维度独立评分（0-100）
2. 检测 6 类 STAR 缺陷（fake_star / team_substitution / situation_missing /
   result_attribution_error / action_vague / result_abstract）
3. 计算综合真实性评分（权重：A 35% + R 35% + S 15% + T 15%）
4. 判定置信度等级（low / medium / high）
5. 生成追问模板（按缺陷类型，从 STAR.yaml 轮换选取）
6. 缺陷交互高阶规则判定

使用方式：
    from app.star_analyzer import analyze_star
    result = analyze_star(transcript, turns, features, knowledge)
"""

from __future__ import annotations

from typing import Any

# 各维度在 YAML 中的键名
_DIM_LABELS = {"S": "situation", "T": "task", "A": "action", "R": "result"}

# 真实性综合权重（与 STAR.yaml global_rules.weight_overall 保持一致）
_WEIGHTS = {"S": 0.15, "T": 0.15, "A": 0.35, "R": 0.35}


# ─────────────────────────────────────────────────────────
# 1. 四维度独立评分
# ─────────────────────────────────────────────────────────

def _score_dimension(
    dim: str,
    features: dict,
    knowledge: dict,
    transcript: str,
) -> dict[str, Any]:
    """对单个 STAR 维度评分，返回 {score, band, interpretation, evidence_summary}。"""
    yaml_dim = knowledge.get("dimensions", {}).get(dim) or {}
    label = yaml_dim.get("label", dim)
    interp = yaml_dim.get("score_interpretation", {})

    # features.py 已提供 0~1 范围的分数，映射到 0~100
    raw = features.get(f"star_{dim.lower()}_score", 0.0)
    base = round(raw * 100, 1)

    # 关键词命中率加权（YAML strong_keywords 密度）
    strong_kws = yaml_dim.get("positive_language_cues", {}).get("lexical", {}).get("strong_keywords", [])
    kw_hits = sum(transcript.count(kw) for kw in strong_kws)
    kw_bonus = min(20.0, kw_hits * 4.0)

    # 反线索惩罚
    counter_kws = yaml_dim.get("negative_or_counter_cues", {}).get("lexical", [])
    counter_hits = sum(transcript.count(kw) for kw in counter_kws)
    counter_penalty = min(15.0, counter_hits * 5.0)

    # 句法加分（有步骤连接词 / 有宾语锚点）
    syntax_bonus = 0.0
    if dim == "S":
        if features.get("temporal_words_ratio", 0) > 0:
            syntax_bonus += 5.0
        if features.get("constraint_words_ratio", 0) > 0:
            syntax_bonus += 5.0
    elif dim == "T":
        if features.get("_self_team_ratio", 0) >= 0.8:
            syntax_bonus += 8.0
        elif features.get("self_vs_team_orientation") == "self":
            syntax_bonus += 4.0
    elif dim == "A":
        if features.get("step_connector_ratio", 0) > 0.005:
            syntax_bonus += 5.0
        if features.get("tool_method_words_ratio", 0) > 0:
            syntax_bonus += 5.0
    elif dim == "R":
        if features.get("quantitative_words_ratio", 0) > 0:
            syntax_bonus += 8.0
        if features.get("result_attribution_self_ratio", 0) > 0:
            syntax_bonus += 4.0
        if features.get("vague_result_words_ratio", 0) > features.get("quantitative_words_ratio", 0):
            counter_penalty += 10.0

    final_score = max(0.0, min(100.0, base + kw_bonus + syntax_bonus - counter_penalty))
    final_int = int(round(final_score))

    # band
    if final_int >= 75:
        band = "high"
    elif final_int >= 50:
        band = "medium"
    else:
        band = "low"

    interp_text = interp.get(band, "")
    return {
        "score": final_int,
        "band": band,
        "interpretation": interp_text,
        "evidence_summary": {
            "base_from_features": base,
            "keyword_hits": kw_hits,
            "counter_hits": counter_hits,
            "syntax_bonus": round(syntax_bonus, 1),
            "counter_penalty": round(counter_penalty, 1),
        },
    }


# ─────────────────────────────────────────────────────────
# 2. 缺陷检测
# ─────────────────────────────────────────────────────────

def _detect_defects(
    features: dict,
    transcript: str,
    word_count: int,
    dim_scores: dict[str, int],
) -> list[dict[str, Any]]:
    """检测 6 类 STAR 缺陷，返回缺陷列表（按严重度降序）。"""
    defects: list[dict[str, Any]] = []

    # 辅助
    def add_defect(defect_id: str, severity: str, reason: str):
        defects.append({
            "defect_id": defect_id,
            "severity": severity,
            "reason": reason,
        })

    # ── fake_star ─────────────────────────────────────────
    dims_below_35 = sum(1 for d in "STAR" if dim_scores.get(d, 0) < 35)
    has_no_quant = features.get("quantitative_words_ratio", 0) == 0 and word_count > 100
    overall = (dim_scores.get("S", 0) + dim_scores.get("T", 0) +
               dim_scores.get("A", 0) + dim_scores.get("R", 0)) / 4
    if dims_below_35 >= 2 and has_no_quant and overall < 45:
        add_defect("fake_star", "high", "综合评分 < 45 且 R < 35 且全文字数 > 100 但无量化指标")
    elif dims_below_35 >= 2 or overall < 50:
        add_defect("fake_star", "medium", "多个维度 < 35 或综合评分 < 50，结构明显残缺")

    # ── team_substitution ─────────────────────────────────
    team_count = features.get("_team_count", 0)
    self_count = features.get("_self_count", 0)
    self_team_ratio = features.get("_self_team_ratio", 1.0)
    if team_count >= 5 and self_count <= 2:
        add_defect("team_substitution", "high", "'我们' >= 5 次 且 '我' <= 2 次，个人贡献被严重稀释")
    elif team_count >= 3 and self_team_ratio < 0.5:
        add_defect("team_substitution", "medium", "团队叙事占主导，'我'/'我们' 比值 < 0.5")
    elif features.get("self_vs_team_orientation") == "team" and self_team_ratio < 0.7:
        add_defect("team_substitution", "low", "以团队叙事为主，但偶有个人亮点")

    # ── situation_missing ─────────────────────────────────
    temporal_ratio = features.get("temporal_words_ratio", 0)
    context_density = features.get("context_marker_density", 0)
    constraint_ratio = features.get("constraint_words_ratio", 0)
    if temporal_ratio == 0 and word_count < 80:
        add_defect("situation_missing", "high", "全文无时间标记词 且 字数 < 80，直接跳步")
    elif temporal_ratio == 0 and context_density == 0:
        add_defect("situation_missing", "medium", "无时间词且无情境标记词，背景缺失")
    elif temporal_ratio > 0 and constraint_ratio == 0 and dim_scores.get("S", 0) < 50:
        add_defect("situation_missing", "low", "有简单时间背景但无约束条件")

    # ── result_attribution_error ───────────────────────────
    self_attr = features.get("result_attribution_self_ratio", 0)
    team_attr = features.get("team_result_attribution_ratio", 0)
    if self_attr > 0.5 and team_attr > 0.5:
        add_defect("result_attribution_error", "medium", "个人归因与团队归因词同时偏高，归因混淆")
    elif self_attr > 0.4 and dim_scores.get("R", 0) < 40:
        add_defect("result_attribution_error", "high", "自我归因偏高但结果得分偏低，可能夸大个人贡献")
    elif team_attr > 0.6 and dim_scores.get("R", 0) < 40:
        add_defect("result_attribution_error", "medium", "团队归因为主且结果得分低，结果归因存疑")

    # ── action_vague ───────────────────────────────────────
    step_ratio = features.get("step_connector_ratio", 0)
    tool_ratio = features.get("tool_method_words_ratio", 0)
    a_raw = features.get("_star_a_raw", {})
    strong_action = a_raw.get("strong", 0)
    if strong_action == 0 and step_ratio == 0 and tool_ratio == 0:
        add_defect("action_vague", "high", "强行动词为 0，无步骤连接词，无工具方法词，行动极度空洞")
    elif strong_action == 0:
        add_defect("action_vague", "medium", "强行动词缺失，行动描述多为抽象动词堆砌")
    elif step_ratio == 0 and dim_scores.get("A", 0) < 50:
        add_defect("action_vague", "low", "行动有内容但无步骤结构")

    # ── result_abstract ────────────────────────────────────
    quant_ratio = features.get("quantitative_words_ratio", 0)
    vague_ratio = features.get("vague_result_words_ratio", 0)
    r_raw = features.get("_star_r_raw", {})
    strong_result = r_raw.get("strong", 0)
    if quant_ratio == 0 and vague_ratio > 0 and word_count > 80:
        add_defect("result_abstract", "high", "全文无数字词但存在泛化结果词，结果无法量化验证")
    elif strong_result == 0 and vague_ratio > 0:
        add_defect("result_abstract", "medium", "无强量化结果词，结果描述停留在主观感受")

    # 按严重度降序 + 去重（同 defect_id 取最高严重度）
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for d in defects:
        if d["defect_id"] not in seen:
            seen.add(d["defect_id"])
            result.append(d)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    result.sort(key=lambda x: severity_order.get(x["severity"], 3))
    return result


# ─────────────────────────────────────────────────────────
# 3. 追问生成（轮换去重）
# ─────────────────────────────────────────────────────────

def _build_followups(
    defects: list[dict[str, Any]],
    knowledge: dict,
    max_per_defect: int = 2,
) -> list[dict[str, Any]]:
    """从 STAR.yaml 按缺陷类型选取追问模板。"""
    probes_raw: list[dict[str, Any]] = []
    used_questions: set[str] = set()

    for defect in defects:
        defect_id = defect["defect_id"]
        yaml_probes = knowledge.get("followup_probes", {}).get(defect_id, [])
        count = 0
        for probe in yaml_probes:
            q = probe.get("question", "")
            if q and q not in used_questions and count < max_per_defect:
                probes_raw.append({
                    "defect_id": defect_id,
                    "question": q,
                    "purpose": probe.get("purpose", ""),
                    "severity": defect["severity"],
                })
                used_questions.add(q)
                count += 1

    return probes_raw


# ─────────────────────────────────────────────────────────
# 4. 缺陷交互规则（高阶组合）
# ─────────────────────────────────────────────────────────

def _detect_defect_interactions(
    defects: list[dict[str, Any]],
    knowledge: dict,
) -> list[dict[str, Any]]:
    """根据 YAML defect_interactions 规则，检测高阶组合并返回结论。"""
    interactions: list[dict[str, Any]] = []
    defect_ids = {d["defect_id"] for d in defects}

    rules = knowledge.get("global_rules", {}).get("defect_interactions", [])
    for rule in rules:
        trigger_ids = set(rule.get("trigger", {}).get("defects", []))
        if trigger_ids <= defect_ids:
            interactions.append({
                "trigger_defects": list(trigger_ids),
                "conclusion": rule.get("conclusion", ""),
            })
    return interactions


# ─────────────────────────────────────────────────────────
# 5. 真实性综合评分 & 置信度
# ─────────────────────────────────────────────────────────

def _overall_score(dim_scores: dict[str, int]) -> float:
    return round(
        sum(_WEIGHTS[d] * dim_scores[d] for d in "STAR"),
        2,
    )


def _confidence_level(
    dim_scores: dict[str, int],
    defects: list[dict[str, Any]],
    word_count: int,
    knowledge: dict,
) -> tuple[str, list[str]]:
    """根据 STAR.yaml confidence_rules 判定置信度。"""
    rules = knowledge.get("global_rules", {}).get("confidence_rules", {})
    overall = _overall_score(dim_scores)
    high_severity = sum(1 for d in defects if d["severity"] == "high")
    medium_severity = sum(1 for d in defects if d["severity"] == "medium")

    notes: list[str] = []

    # high 条件
    if (word_count >= 200 and
            dim_scores["S"] >= 50 and dim_scores["T"] >= 50 and
            dim_scores["A"] >= 60 and dim_scores["R"] >= 60 and
            high_severity == 0 and overall >= 55):
        return "high", ["多条回答各有特色且细节丰富，真实性信号强"]

    # low 条件
    if word_count < 60 or overall < 30 or high_severity >= 2:
        if word_count < 60:
            notes.append("样本总字数低于 60 字，结论不足以定论")
        if overall < 30:
            notes.append("STAR 综合评分极低，真实性信号不足")
        if high_severity >= 2:
            notes.append(f"存在 {high_severity} 个高严重度缺陷，风险较高")
        return "low", notes

    # medium（默认）
    if medium_severity > 0 or high_severity == 1:
        notes.append("缺陷与强信号并存，样本量尚不足以定论")
    else:
        notes.append("STAR 回答有一定结构，但信息量尚不足以得出强结论")
    return "medium", notes


# ─────────────────────────────────────────────────────────
# 6. 风险信号汇总
# ─────────────────────────────────────────────────────────

def _risk_signals(
    defects: list[dict[str, Any]],
    features: dict,
    dim_scores: dict[str, int],
) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    defect_ids = {d["defect_id"] for d in defects}

    if "fake_star" in defect_ids:
        signals.append({"type": "fake_star", "severity": "high", "message": "多个 STAR 维度结构残缺，整体真实性存疑"})
    if "team_substitution" in defect_ids:
        signals.append({"type": "team_substitution", "severity": "medium", "message": "团队叙事占主导，个人贡献难以评估"})
    if "action_vague" in defect_ids:
        signals.append({"type": "action_vague", "severity": "medium", "message": "行动描述多为抽象动词，缺乏可验证的具体步骤"})
    if "result_abstract" in defect_ids:
        signals.append({"type": "result_abstract", "severity": "medium", "message": "结果停留在主观感受层面，缺乏可量化指标"})
    if "situation_missing" in defect_ids:
        signals.append({"type": "situation_missing", "severity": "low", "message": "情境背景缺失或模糊，无法判断决策前提合理性"})
    if "result_attribution_error" in defect_ids:
        signals.append({"type": "result_attribution_error", "severity": "high", "message": "结果归因存疑，个人与团队贡献边界不清"})
    if features.get("buzzword_density", 0) >= 0.015 and features.get("story_richness_score", 0) < 0.45:
        signals.append({"type": "impression_management", "severity": "medium", "message": "套话较多且细节不足，疑似精心准备而非亲历"})

    return signals


# ─────────────────────────────────────────────────────────
# 7. DISC 辅助信号（STAR → DISC 交叉）
# ─────────────────────────────────────────────────────────

def _disc_auxiliary_signals(
    features: dict,
    dim_scores: dict[str, int],
) -> list[str]:
    """基于 STAR 分析结果，生成对 DISC 评分的辅助修正建议。"""
    signals: list[str] = []

    # C 维度：STAR 结构完整度高 → 加强 C 分
    star_total = sum(dim_scores.get(d, 0) for d in "STAR")
    if star_total >= 280 and dim_scores.get("R", 0) >= 65:
        signals.append("STAR 结构完整（R 维度强），高 C 特征置信度提升，建议在 DISC 分析中适当加强 C 权重")

    # D 维度：A 维度高但 S 维度低 → 警惕过度主导
    if dim_scores.get("A", 0) >= 70 and dim_scores.get("S", 0) < 40:
        signals.append("A 维度过高但 S 维度极低，行动丰富但情境缺失，D 特征置信度需下调")

    # I/S 维度：R 维度低但 team_substitution 存在 → 警惕社交面具
    if dim_scores.get("R", 0) < 40 and features.get("self_vs_team_orientation") == "team":
        signals.append("R 维度低且团队叙事主导，可能存在通过社交叙事掩盖结果空洞的倾向，I/S 置信度需谨慎")

    # 高 STAR 完整度但 A/R 偏弱 → C 或 S 高可能虚高
    if dim_scores.get("S", 0) >= 70 and dim_scores.get("A", 0) < 50 and dim_scores.get("R", 0) < 50:
        signals.append("S 维度偏高但 A/R 偏低，候选人描述背景能力强但执行结果弱，DISC-C 读数可能虚高")

    return signals


# ─────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────

def analyze_star(
    transcript: str,
    turns: list[dict],
    features: dict,
    knowledge: dict,
) -> dict[str, Any]:
    """
    STAR 完整分析。

    Returns:
        {
            "dimension_scores": {S/T/A/R: {"score": int, "band": str, "interpretation": str, ...}},
            "overall_score": float,           # 0~100 加权综合分
            "defects": [...],                  # 缺陷列表
            "authenticity_summary": {
                "overall": float,
                "confidence": str,             # low / medium / high
                "confidence_notes": [...],
                "risk_signals": [...],
                "anti_overclaim_notes": [...], # STAR.yaml anti_overclaim
            },
            "star_disc_auxiliary_signals": [...],  # DISC 辅助信号
            "followup_questions": [...],           # 追问模板
            "defect_interactions": [...],           # 高阶组合结论
            "meta": {
                "sample_words": int,
                "turn_count": int,
                "star_structure_score": float,      # features.py 原始覆盖率
                "feature_summary": {...},            # 关键特征快照
            },
        }
    """
    word_count = len(transcript.replace("\n", ""))
    turn_count = len(turns)

    # 1. 四维度独立评分
    dim_scores: dict[str, int] = {}
    dimension_results: dict[str, Any] = {}
    for dim in "STAR":
        result = _score_dimension(dim, features, knowledge, transcript)
        dim_scores[dim] = result["score"]
        dimension_results[dim] = result

    # 2. 缺陷检测
    defects = _detect_defects(features, transcript, word_count, dim_scores)

    # 3. 缺陷交互
    interactions = _detect_defect_interactions(defects, knowledge)

    # 4. 追问
    followups = _build_followups(defects, knowledge)

    # 5. 真实性 & 置信度
    overall = _overall_score(dim_scores)
    confidence, confidence_notes = _confidence_level(dim_scores, defects, word_count, knowledge)

    # 6. 风险信号
    risk_signals = _risk_signals(defects, features, dim_scores)

    # 7. DISC 辅助信号
    disc_aux = _disc_auxiliary_signals(features, dim_scores)

    # 8. 防过度声明（YAML anti_overclaim）
    anti_overclaim = knowledge.get("global_rules", {}).get("anti_overclaim", [])

    # 9. defect_labels（前端展示）
    defect_labels = knowledge.get("defect_labels", {})
    labeled_defects = [
        {**d, "label": defect_labels.get(d["defect_id"], d["defect_id"])}
        for d in defects
    ]

    return {
        "dimension_scores": dimension_results,
        "overall_score": overall,
        "defects": labeled_defects,
        "defect_interactions": interactions,
        "authenticity_summary": {
            "overall": overall,
            "confidence": confidence,
            "confidence_notes": confidence_notes,
            "risk_signals": risk_signals,
            "anti_overclaim_notes": anti_overclaim,
        },
        "star_disc_auxiliary_signals": disc_aux,
        "followup_questions": followups,
        "meta": {
            "sample_words": word_count,
            "turn_count": turn_count,
            "star_structure_score": features.get("star_structure_score", 0.0),
            "feature_summary": {
                "self_vs_team_orientation": features.get("self_vs_team_orientation"),
                "story_richness_score": features.get("story_richness_score"),
                "abstraction_level": features.get("abstraction_level"),
                "step_connector_ratio": features.get("step_connector_ratio"),
                "quantitative_words_ratio": features.get("quantitative_words_ratio"),
                "context_marker_density": features.get("context_marker_density"),
            },
        },
    }
