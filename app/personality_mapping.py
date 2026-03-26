from __future__ import annotations

"""
personality_mapping.py — 跨模型人格映射 Agent

功能：
  1. DISC ↔ Big Five 映射
  2. Big Five ↔ 九型人格映射
  3. DISC ↔ 九型人格映射
  4. 综合三模型输出统一的人格画像
  5. 输出跨模型置信度调整（人格结果影响 DISC/STAR 置信度）

调用方式：
  result = map_personality(disc_result, bigfive_result, enneagram_result, features)
"""


# ─────────────────────────────────────────────────────────────────────────────
# 映射矩阵
# ─────────────────────────────────────────────────────────────────────────────

# DISC → BigFive 映射表
# 格式: (disc_rank_signature, bigfive_dim, direction, weight)
# direction: +1=正相关, -1=负相关, +0.5=弱正相关, -0.5=弱负相关
DISC_TO_BIGFIVE_MATRIX = [
    # DISC D 与 BigFive 的关系
    ("D_dominant", "C",  +1.0, "D的高行动力和成就导向强烈预示高尽责性"),
    ("D_dominant", "E",  +0.8, "D的社交自信预示较高外向性"),
    ("D_dominant", "A",  -0.8, "D的主导性与宜人性呈负相关"),
    ("D_dominant", "N",  -0.6, "D的决断力预示较低神经质"),
    ("D_dominant", "O",  +0.3, "D的行动导向有时伴随开放性"),
    # DISC I 与 BigFive 的关系
    ("I_dominant", "E",  +1.0, "I的社交活跃度直接对应外向性"),
    ("I_dominant", "A",  +0.9, "I的人际影响导向预示高宜人性"),
    ("I_dominant", "O",  +0.5, "I的表达欲与开放性相关"),
    ("I_dominant", "N",  -0.4, "I的社交能量可能缓冲焦虑"),
    ("I_dominant", "C",  -0.3, "I的灵活性有时与高C冲突"),
    # DISC S 与 BigFive 的关系
    ("S_dominant", "A",  +1.0, "S的稳定支持导向强烈预示高宜人性"),
    ("S_dominant", "N",  +0.6, "S对稳定的追求有时伴随对不确定性的焦虑"),
    ("S_dominant", "C",  +0.5, "S的可靠性与尽责性相关"),
    ("S_dominant", "E",  -0.7, "S的内敛与外向性呈负相关"),
    ("S_dominant", "O",  -0.3, "S的稳定性与开放性呈弱负相关"),
    # DISC C 与 BigFive 的关系
    ("C_dominant", "C",  +1.0, "C的结构导向强烈预示高尽责性"),
    ("C_dominant", "O",  +0.7, "C的分析性思维与开放性相关"),
    ("C_dominant", "N",  -0.5, "C的谨慎有时表现为高标准而非焦虑"),
    ("C_dominant", "A",  +0.4, "C的结构化有时促进合作"),
    ("C_dominant", "E",  -0.5, "C的内省倾向与外向性负相关"),
]

# BigFive → 九型映射表（基于核心动机相似性）
BIGFIVE_TO_ENNEAGRAM = [
    # 高C + 高N → Type1（完美主义）
    (("C", ">=", 65), ("N", ">=", 55),  "type_1", 0.85, "高标准+高自我批评 = Type1改革者"),
    # 高C + 低N → Type3（高效成就）
    (("C", ">=", 65), ("N", "<=", 45),  "type_3", 0.80, "高自律+情绪稳定 = Type3成就者"),
    # 高A + 高N → Type2（助人+敏感）
    (("A", ">=", 65), ("N", ">=", 55),  "type_2", 0.75, "高同理+情绪敏感 = Type2助人者"),
    # 高A + 低N + 低E → Type9（和平）
    (("A", ">=", 65), ("N", "<=", 45), ("E", "<=", 50), "type_9", 0.80, "高宜人+内敛+稳定 = Type9和平者"),
    # 高A + 高E → Type2（热情助人）
    (("A", ">=", 60), ("E", ">=", 65),  "type_2", 0.80, "温暖+外向 = Type2助人者"),
    # 高O + 高E → Type7（活跃探索）
    (("O", ">=", 65), ("E", ">=", 65),  "type_7", 0.80, "高开放+外向 = Type7活跃者"),
    # 高O + 低E → Type4（内省独特）
    (("O", ">=", 65), ("E", "<=", 45),  "type_4", 0.80, "高开放+内敛 = Type4自我型"),
    # 高O + 高C → Type5（深度分析）
    (("O", ">=", 60), ("C", ">=", 60),  "type_5", 0.75, "高开放+高严谨 = Type5探索者"),
    # 高N + 低E + 高O → Type4（敏感内省）
    (("N", ">=", 65), ("E", "<=", 50), ("O", ">=", 55), "type_4", 0.70, "高神经质+内省 = Type4自我型"),
    # 高N + 高C → Type6（谨慎忠诚）
    (("N", ">=", 60), ("C", ">=", 60),  "type_6", 0.75, "高谨慎+高标准 = Type6忠诚者"),
    # 高E + 高C + 高N → Type3（外显成就）
    (("E", ">=", 65), ("C", ">=", 60), ("N", ">=", 50), "type_3", 0.70, "高外向+成就导向 = Type3成就者"),
    # 高D（大五中无D，用E+C模拟）→ Type8
    # 高O + 低C → Type7
    (("O", ">=", 65), ("C", "<=", 45),  "type_7", 0.70, "高开放+低自律 = Type7活跃者"),
]

# DISC → 九型直接映射（简化版）
DISC_TO_ENNEAGRAM = [
    ("D", "type_3", 0.80, "D的结果导向+行动力 = Type3成就者"),
    ("D", "type_8", 0.60, "D的主导性有时体现为Type8挑战型"),
    ("D", "type_1", 0.45, "D的高标准可对应Type1改革型"),
    ("I", "type_2", 0.85, "I的人际影响 = Type2助人者"),
    ("I", "type_7", 0.60, "I的社交活力 = Type7活跃者"),
    ("I", "type_3", 0.50, "I的表达欲 = Type3成就型"),
    ("S", "type_9", 0.80, "S的稳定和谐 = Type9和平者"),
    ("S", "type_2", 0.65, "S的支持导向 = Type2助人者"),
    ("S", "type_6", 0.50, "S的可靠性 = Type6忠诚者"),
    ("C", "type_1", 0.80, "C的结构化+标准 = Type1改革者"),
    ("C", "type_5", 0.65, "C的分析性 = Type5探索者"),
    ("C", "type_6", 0.55, "C的谨慎 = Type6忠诚者"),
]


# ─────────────────────────────────────────────────────────────────────────────
# 置信度影响规则
# ─────────────────────────────────────────────────────────────────────────────

# BigFive/Enneagram 置信度 → DISC 置信度调整
# 如果九型/大五置信度高，且与 DISC 结论一致 → DISC 置信度升权
# 如果 BigFive-N 高 → STAR 真实性降权（情绪波动可能影响叙事真实性）
# 如果 Enneagram-Type3 高且 star_richness 低 → 面试伪装风险 → 降权


def _get_disc_signature(disc_scores: dict, disc_ranking: list) -> str:
    """生成分 DISC 排名签名，用于查表。"""
    if not disc_ranking:
        return "unknown"
    top = disc_ranking[0]
    if len(disc_ranking) >= 2 and disc_scores.get(disc_ranking[1], 0) >= disc_scores.get(top, 0) * 0.85:
        return f"{top}_plus_{disc_ranking[1]}"
    return f"{top}_dominant"


def _check_bigfive_condition(value: float, op: str, threshold: float) -> bool:
    if op == ">=": return value >= threshold
    if op == "<=": return value <= threshold
    if op == "==": return value == threshold
    if op == ">":  return value > threshold
    if op == "<":  return value < threshold
    return False


def _eval_bigfive_conditions(conditions: tuple, bigfive_scores: dict) -> bool:
    """???? BigFive ???AND ????"""
    for cond in conditions:
        dim, op, threshold = cond
        val = bigfive_scores.get(dim, 0)
        if not _check_bigfive_condition(val, op, threshold):
            return False
    return True


def _split_bigfive_enneagram_rule(rule: tuple) -> tuple[tuple[tuple[str, str, float], ...], str, float, str]:
    """?? BigFive???????? 2 ??? 3 ?????"""
    conditions: list[tuple[str, str, float]] = []
    index = 0
    while index < len(rule):
        item = rule[index]
        if (
            isinstance(item, tuple)
            and len(item) == 3
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        ):
            conditions.append(item)
            index += 1
            continue
        break

    if not conditions or index + 2 >= len(rule):
        raise ValueError(f"Invalid BigFive?Enneagram rule: {rule!r}")

    type_key = rule[index]
    confidence = rule[index + 1]
    reason = rule[index + 2] if index + 2 < len(rule) else ""
    return tuple(conditions), str(type_key), float(confidence), str(reason)


def _resolve_enng_from_bigfive(bigfive_scores: dict) -> list[dict]:
    """?? BigFive ??????????"""
    candidates = []
    for rule in BIGFIVE_TO_ENNEAGRAM:
        conditions, type_key, confidence, reason = _split_bigfive_enneagram_rule(rule)
        if _eval_bigfive_conditions(conditions, bigfive_scores):
            candidates.append({"type": type_key, "confidence": confidence, "source": "bigfive", "reason": reason})
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates[:3]


def _resolve_enng_from_disc(disc_scores: dict, disc_ranking: list) -> list[dict]:
    """基于 DISC 推断可能的九型类型。"""
    candidates = []
    top_disc = disc_ranking[0] if disc_ranking else "D"
    for row in DISC_TO_ENNEAGRAM:
        disc_dim, type_key, confidence, reason = row
        if disc_dim == top_disc:
            candidates.append({"type": type_key, "confidence": confidence, "source": "disc", "reason": reason})
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates[:3]


def _resolve_bigfive_from_disc(disc_scores: dict, disc_ranking: list) -> list[dict]:
    """基于 DISC 推断 BigFive 各维度得分调整。"""
    disc_sig = _get_disc_signature(disc_scores, disc_ranking)
    adjustments = {dim: 0.0 for dim in ("O", "C", "E", "A", "N")}

    for row in DISC_TO_BIGFIVE_MATRIX:
        sig, dim, weight = row[:3]
        if sig == disc_sig or sig.startswith(disc_ranking[0] if disc_ranking else "D"):
            adjustments[dim] += weight

    result = []
    for dim, adj in adjustments.items():
        if abs(adj) >= 0.3:
            result.append({"dimension": dim, "adjustment": round(adj, 2), "direction": "up" if adj > 0 else "down"})
    result.sort(key=lambda x: abs(x["adjustment"]), reverse=True)
    return result


def _integrate_cross_model(
    disc_result: dict | None,
    bigfive_result: dict | None,
    enneagram_result: dict | None,
) -> dict:
    """整合三个模型，输出统一的人格画像。"""

    disc_scores = disc_result.get("scores", {}) if disc_result else {}
    disc_ranking = disc_result.get("ranking", []) if disc_result else []
    bigfive_scores = bigfive_result.get("scores", {}) if bigfive_result else {}
    enneagram_top = None
    if enneagram_result:
        top_types = enneagram_result.get("top_two_types", [])
        if top_types:
            enneagram_top = top_types[0].get("label", "")

    integrated_styles: list[dict] = []

    # 从 BigFive 到九型
    enng_from_bf = _resolve_enng_from_bigfive(bigfive_scores)
    # 从 DISC 到九型
    enng_from_disc = _resolve_enng_from_disc(disc_scores, disc_ranking)

    # 综合九型来源
    enng_combined: dict[str, float] = {}
    enng_sources: dict[str, list[str]] = {}
    for item in enng_from_bf:
        t = item["type"]
        enng_combined[t] = enng_combined.get(t, 0) + item["confidence"]
        enng_sources.setdefault(t, []).append(f"BigFive→{item['reason']}")
    for item in enng_from_disc:
        t = item["type"]
        enng_combined[t] = enng_combined.get(t, 0) + item["confidence"]
        enng_sources.setdefault(t, []).append(f"DISC→{item['reason']}")

    # 直接九型分析结果加权
    if enneagram_top:
        for item in (enneagram_result.get("top_two_types") or []):
            type_num = item.get("type_number")
            type_key = f"type_{type_num}" if type_num else ""
            if type_key:
                enng_combined[type_key] = enng_combined.get(type_key, 0) + (item.get("raw_score", 0) / 100.0)
                enng_sources.setdefault(type_key, []).append(f"九型直接分析")

    # 取 Top 综合九型
    TYPE_META = {
        "type_1": "Type 1 改革者", "type_2": "Type 2 助人者", "type_3": "Type 3 成就者",
        "type_4": "Type 4 自我型", "type_5": "Type 5 探索者", "type_6": "Type 6 忠诚者",
        "type_7": "Type 7 活跃者", "type_8": "Type 8 挑战者", "type_9": "Type 9 和平者",
    }
    sorted_enng = sorted(enng_combined.items(), key=lambda x: x[1], reverse=True)[:3]
    integrated_styles.append({
        "synthesis_type": "综合九型人格",
        "top_inferred": [{"type": k, "label": TYPE_META.get(k, k), "combined_score": round(v, 2), "sources": enng_sources.get(k, [])} for k, v in sorted_enng],
    })

    # BigFive 综合解读
    bf_dom = bigfive_result.get("dominant_trait", "") if bigfive_result else ""
    bf_second = bigfive_result.get("secondary_traits", []) if bigfive_result else []
    bf_cross = bigfive_result.get("cross_dimension_patterns", []) if bigfive_result else []
    disc_top = disc_ranking[0] if disc_ranking else ""

    integrated_styles.append({
        "synthesis_type": "综合人格画像",
        "primary_style": f"{disc_top or ''} + BigFive-{bf_dom}" if disc_top and bf_dom else (disc_top or bf_dom or ""),
        "bigfive_dominant": bf_dom,
        "bigfive_secondary": bf_second,
        "disc_dominant": disc_top,
        "cross_patterns": [p.get("pattern_name", "") for p in bf_cross[:3]],
    })

    # 综合置信度调整
    confidence_adjustments: list[dict] = []

    if bigfive_result:
        n_score = bigfive_scores.get("N", 0)
        e_score = bigfive_scores.get("E", 0)
        c_score = bigfive_scores.get("C", 0)
        if n_score >= 70 and e_score <= 45:
            confidence_adjustments.append({
                "target": "STAR_authenticity",
                "direction": "down",
                "amount": "medium",
                "reason": f"BigFive-N={n_score}高且E={e_score}低，情绪稳定性存疑，STAR叙事真实性降权。"
            })
        if n_score >= 65 and c_score >= 65:
            confidence_adjustments.append({
                "target": "STAR_authenticity",
                "direction": "up",
                "amount": "small",
                "reason": f"BigFive-N={n_score}高但C={c_score}也高，自律可部分抵消情绪波动影响。"
            })
        if c_score >= 70 and bigfive_result.get("meta", {}).get("confidence") == "high":
            confidence_adjustments.append({
                "target": "DISC_C_confidence",
                "direction": "up",
                "amount": "small",
                "reason": "BigFive-C高且置信度高，DISC的C维度置信度升权。"
            })

    if enneagram_result:
        enng_meta = enneagram_result.get("meta", {})
        top_types = enneagram_result.get("top_two_types") or []
        type3_risk = next((t for t in top_types if t.get("type_number") == "3"), None)
        if type3_risk and bigfive_result and bigfive_result.get("scores", {}).get("achievement_words_ratio", 0) > 0:
            confidence_adjustments.append({
                "target": "STAR_action_vague_risk",
                "direction": "up",
                "amount": "medium",
                "reason": "Enneagram-Type3高且成就词密度高，存在过度包装风险，需追问行动细节。"
            })

    return {
        "integrated_styles": integrated_styles,
        "confidence_adjustments": confidence_adjustments,
        "model_cross_validations": {
            "bigfive_to_enneagram": [
                {"type": item["type"], "label": TYPE_META.get(item["type"], item["type"]),
                 "confidence": item["confidence"], "basis": item["reason"]}
                for item in enng_from_bf
            ],
            "disc_to_enneagram": [
                {"type": item["type"], "label": TYPE_META.get(item["type"], item["type"]),
                 "confidence": item["confidence"], "basis": item["reason"]}
                for item in enng_from_disc
            ],
            "disc_to_bigfive": _resolve_bigfive_from_disc(disc_scores, disc_ranking),
        },
    }


def map_personality(
    disc_result: dict | None = None,
    bigfive_result: dict | None = None,
    enneagram_result: dict | None = None,
    features: dict | None = None,
) -> dict:
    """
    跨模型人格映射入口函数。

    Args:
        disc_result:     DISC 分析结果（来自 disc_engine 或 LLM）
        bigfive_result:  BigFive 分析结果（来自 bigfive_engine 或 LLM）
        enneagram_result: 九型分析结果（来自 enneagram_engine 或 LLM）
        features:        原子特征（用于置信度调整）

    Returns:
        包含三部分内容的字典：
        - cross_mapping: 三个方向的跨模型映射结果
        - integrated_personality_profile: 综合人格画像
        - confidence_adjustments: 置信度调整建议
    """
    cross_mapping = _integrate_cross_model(disc_result, bigfive_result, enneagram_result)

    # 综合画像合成
    disc_scores = disc_result.get("scores", {}) if disc_result else {}
    disc_ranking = disc_result.get("ranking", []) if disc_result else []
    bigfive_scores = bigfive_result.get("scores", {}) if bigfive_result else {}
    bigfive_meta = bigfive_result.get("meta", {}) if bigfive_result else {}
    enneagram_meta = enneagram_result.get("meta", {}) if enneagram_result else {}

    disc_top = disc_ranking[0] if disc_ranking else ""
    bf_dom = bigfive_result.get("dominant_trait", "") if bigfive_result else ""
    bf_cross = bigfive_result.get("cross_dimension_patterns", []) if bigfive_result else []

    # 主导风格合成
    if disc_top and bf_dom:
        if disc_top == "D" and bf_dom == "C":
            primary_label = "D/C 高效行动型"
            primary_desc = "兼具主导决策力和结构严谨性，适合推动型和高标准岗位。"
        elif disc_top == "D" and bf_dom == "E":
            primary_label = "D/E 领袖影响型"
            primary_desc = "强势且有感染力，适合需要快速决策和带领团队的岗位。"
        elif disc_top == "I" and bf_dom == "A":
            primary_label = "I/A 温暖连接型"
            primary_desc = "善于人际影响且合作性强，适合客户关系和团队文化建设。"
        elif disc_top == "I" and bf_dom == "E":
            primary_label = "I/E 活力影响型"
            primary_desc = "社交活跃且表达力强，适合市场和销售类岗位。"
        elif disc_top == "S" and bf_dom == "A":
            primary_label = "S/A 稳定支持型"
            primary_desc = "稳健可靠、合作导向，适合需要长期维护和稳定输出的岗位。"
        elif disc_top == "C" and bf_dom == "C":
            primary_label = "C/C 精密严谨型"
            primary_desc = "分析严谨、标准导向，适合质量控制和风险把控类岗位。"
        elif disc_top == "C" and bf_dom == "O":
            primary_label = "C/O 深度专家型"
            primary_desc = "兼具分析深度和创新意识，适合技术专家或策略类岗位。"
        elif disc_top == "D" and bf_dom == "N":
            primary_label = "D/N 强势焦虑型"
            primary_desc = "主导性强但情绪波动明显，适合高压推动岗位但需关注稳定性。"
        else:
            primary_label = f"{disc_top} + BigFive-{bf_dom}"
            primary_desc = f"DISC风格偏向{disc_top}，BigFive特质以{bf_dom}为主导。"
    elif disc_top:
        primary_label = f"DISC-{disc_top}"
        primary_desc = f"主导DISC风格为{disc_top}型，整体人格轮廓清晰。"
    elif bf_dom:
        primary_label = f"BigFive-{bf_dom}"
        primary_desc = f"BigFive主导特质为{bf_dom}，整体人格轮廓以该特质为核心。"
    else:
        primary_label = "待评估"
        primary_desc = "样本量不足，暂无法形成明确的人格画像。"

    # 整合九型标签
    enneagram_top_label = ""
    enneagram_wing = ""
    if enneagram_result:
        top_types = enneagram_result.get("top_two_types") or []
        if top_types:
            t = top_types[0]
            enneagram_top_label = t.get("label", "")
        enneagram_wing = enneagram_result.get("wing", "")

    # 整合交叉维度
    integration_notes: list[str] = []
    for p in bf_cross[:2]:
        integration_notes.append(p.get("interpretation", ""))

    integrated_profile = {
        "primary_style_label": primary_label,
        "primary_style_description": primary_desc,
        "enneagram_integration": {
            "dominant_type": enneagram_top_label,
            "wing": enneagram_wing,
            "confidence": enneagram_meta.get("confidence", "unknown"),
        },
        "bigfive_integration": {
            "dominant_trait": bf_dom,
            "secondary_traits": bigfive_result.get("secondary_traits", []) if bigfive_result else [],
            "confidence": bigfive_meta.get("confidence", "unknown"),
            "n_artifact_flag": bigfive_meta.get("n_artifact_flag", False) if bigfive_result else False,
        },
        "disc_integration": {
            "dominant_style": disc_top,
            "secondary_style": disc_ranking[1] if len(disc_ranking) >= 2 else None,
        },
        "integration_notes": integration_notes,
    }

    return {
        "cross_mapping": cross_mapping,
        "integrated_personality_profile": integrated_profile,
        "confidence_adjustments": cross_mapping.get("confidence_adjustments", []),
    }
