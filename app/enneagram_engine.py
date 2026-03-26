from __future__ import annotations

from collections import defaultdict


def _to_float(val) -> float:
    """安全将值转为 float，字符串非数字返回 0.0"""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val)
        except ValueError:
            return 0.0
    return 0.0


ALL_TYPES = (
    "type_1", "type_2", "type_3", "type_4", "type_5",
    "type_6", "type_7", "type_8", "type_9",
)

_TYPE_META = {
    "type_1": ("Type 1", "改革者", "1"),
    "type_2": ("Type 2", "助人者", "2"),
    "type_3": ("Type 3", "成就者", "3"),
    "type_4": ("Type 4", "自我型", "4"),
    "type_5": ("Type 5", "探索者", "5"),
    "type_6": ("Type 6", "忠诚者", "6"),
    "type_7": ("Type 7", "活跃者", "7"),
    "type_8": ("Type 8", "挑战者", "8"),
    "type_9": ("Type 9", "和平者", "9"),
}

_TYPE_FEATURE_RULES = {
    "type_1": [
        ("certainty_words_ratio",   ">=", 0.006,  16, "high"),
        ("process_words_ratio",     ">=", 0.012,  14, "high"),
        ("imperative_like_ratio",   ">=", 0.010,  12, "high"),
        ("qualifier_ratio",         ">=", 0.008,  10, "high"),
        ("logical_connector_ratio", ">=", 0.010,  10, "high"),
        ("hedge_words_ratio",       "<=", 0.006, -12, "low"),
        ("buzzword_density",        ">=", 0.010,  -8, "low"),
    ],
    "type_2": [
        ("social_words_ratio",            ">=", 0.012,  18, "high"),
        ("emotional_words_ratio",         ">=", 0.007,  14, "high"),
        ("first_person_plural_ratio",      ">=", 0.010,  14, "high"),
        ("first_person_singular_ratio",    ">=", 0.020,  -8, "low"),
        ("imperative_like_ratio",         ">=", 0.015, -10, "low"),
        ("achievement_words_ratio",        ">=", 0.015,  -6, "low"),
    ],
    "type_3": [
        ("achievement_words_ratio",     ">=", 0.015,  20, "high"),
        ("action_verbs_ratio",          ">=", 0.020,  16, "high"),
        ("star_structure_score",         ">=", 0.70,   14, "high"),
        ("first_person_singular_ratio", ">=", 0.018,  12, "high"),
        ("buzzword_density",            ">=", 0.008,  10, "high"),
        ("hedge_words_ratio",           "<=", 0.004, -12, "low"),
        ("question_ratio",              "<=", 0.06,   -8, "low"),
        ("first_person_plural_ratio",   ">=", 0.015,  -6, "low"),
    ],
    "type_4": [
        ("first_person_singular_ratio", ">=", 0.025,  20, "high"),
        ("emotional_words_ratio",        ">=", 0.010,  16, "high"),
        ("avg_sentence_length",          ">=", 20,     12, "high"),
        ("abstraction_level",            "==", "abstract", 14, "high"),
        ("first_person_plural_ratio",    "<=", 0.006, -14, "low"),
        ("social_words_ratio",           "<=", 0.008,  -8, "low"),
        ("process_words_ratio",          "<=", 0.008,  -8, "low"),
    ],
    "type_5": [
        ("detail_words_ratio",         ">=", 0.015,  18, "high"),
        ("logical_connector_ratio",    ">=", 0.012,  16, "high"),
        ("process_words_ratio",        ">=", 0.012,  14, "high"),
        ("qualifier_ratio",            ">=", 0.010,  12, "high"),
        ("risk_words_ratio",           ">=", 0.012,  12, "high"),
        ("avg_sentence_length",        ">=", 20,     10, "high"),
        ("social_words_ratio",         "<=", 0.008, -14, "low"),
        ("emotional_words_ratio",      "<=", 0.005, -10, "low"),
        ("first_person_plural_ratio",  "<=", 0.006, -10, "low"),
        ("imperative_like_ratio",      "<=", 0.006,  -8, "low"),
    ],
    "type_6": [
        ("risk_words_ratio",           ">=", 0.012,  20, "high"),
        ("hedge_words_ratio",          ">=", 0.008,  16, "high"),
        ("qualifier_ratio",            ">=", 0.012,  14, "high"),
        ("logical_connector_ratio",    ">=", 0.010,  12, "high"),
        ("first_person_plural_ratio",  ">=", 0.010,  12, "high"),
        ("certainty_words_ratio",      ">=", 0.010,  -8, "low"),
        ("imperative_like_ratio",      ">=", 0.015,  -8, "low"),
        ("hedge_words_ratio",          "<=", 0.003,  -6, "low"),
    ],
    "type_7": [
        ("emotional_words_ratio",        ">=", 0.010,  18, "high"),
        ("hedge_words_ratio",            ">=", 0.008,  16, "high"),
        ("avg_sentence_length",          ">=", 20,     14, "high"),
        ("story_richness_score",         ">=", 0.65,   12, "high"),
        ("first_person_singular_ratio",  ">=", 0.018,  10, "high"),
        ("topic_stability_score",        "<=", 0.65,   -8, "low"),
        ("detail_words_ratio",           "<=", 0.010,  -8, "low"),
        ("logical_connector_ratio",      "<=", 0.008,  -8, "low"),
        ("risk_words_ratio",             "<=", 0.006,  -8, "low"),
    ],
    "type_8": [
        ("imperative_like_ratio",     ">=", 0.015,  20, "high"),
        ("certainty_words_ratio",      ">=", 0.007,  16, "high"),
        ("first_person_singular_ratio",">=", 0.022,  18, "high"),
        ("contrast_connector_ratio",   ">=", 0.008,  14, "high"),
        ("action_verbs_ratio",         ">=", 0.020,  12, "high"),
        ("hedge_words_ratio",         "<=", 0.004, -16, "low"),
        ("first_person_plural_ratio",  ">=", 0.015,  -8, "low"),
        ("social_words_ratio",         "<=", 0.008,  -8, "low"),
        ("qualifier_ratio",           "<=", 0.005,  -6, "low"),
    ],
    "type_9": [
        ("first_person_plural_ratio",  ">=", 0.014,  20, "high"),
        ("social_words_ratio",         ">=", 0.014,  16, "high"),
        ("hedge_words_ratio",          ">=", 0.010,  14, "high"),
        ("contrast_connector_ratio",   "<=", 0.004, -14, "low"),
        ("imperative_like_ratio",      "<=", 0.005, -14, "low"),
        ("certainty_words_ratio",      "<=", 0.005, -12, "low"),
        ("first_person_singular_ratio",">=", 0.025,  -8, "low"),
        ("action_verbs_ratio",         ">=", 0.025,  -6, "low"),
    ],
}

_TYPE_KEYWORDS = {
    "type_1": [
        "应该", "必须", "正确", "标准", "原则", "规范", "对错", "责任",
        "良心", "正道", "公平", "公正", "底线", "合理", "该做", "不应该",
    ],
    "type_2": [
        "帮助", "支持", "照顾", "关心", "需要", "大家", "他们", "同事",
        "信任", "依赖", "付出", "温暖", "体贴", "善解人意", "主动",
    ],
    "type_3": [
        "成功", "完成", "目标", "业绩", "达成", "第一", "最好", "赢了",
        "突破", "成就", "价值", "证明", "高效", "最佳", "领先", "超额",
    ],
    "type_4": [
        "我", "真正", "感受", "内心", "独特", "真实", "不一样", "深刻",
        "意义", "个人", "自己", "情感", "自我", "别人眼中",
    ],
    "type_5": [
        "分析", "理解", "研究", "理论", "逻辑", "本质", "原理", "机制",
        "数据", "洞察", "假设", "深度", "底层", "为什么", "原因", "认知",
    ],
    "type_6": [
        "如果", "不确定", "担心", "风险", "安全", "可靠", "信任", "保证",
        "万一", "害怕", "后备方案", "应急预案", "稳妥", "保险", "确认",
    ],
    "type_7": [
        "有趣", "好玩", "新鲜", "体验", "可能", "探索", "尝试", "太好了",
        "太棒了", "开心", "快乐", "丰富", "多元", "机会", "各种", "兴奋",
    ],
    "type_8": [
        "我说了算", "按我的来", "控制", "主导", "强势", "保护", "不服",
        "直接", "不怕", "掌控", "拿主意", "决定", "权利", "底线", "界限", "拍板",
    ],
    "type_9": [
        "都可以", "无所谓", "没关系", "和谐", "和平", "配合", "稳定",
        "不冲突", "大家都好", "差不多", "没意见", "迁就", "让步", "和气",
    ],
}

_WING_MAP = {
    "type_1":  ("type_2", "type_9"),
    "type_2":  ("type_1", "type_3"),
    "type_3":  ("type_2", "type_4"),
    "type_4":  ("type_3", "type_5"),
    "type_5":  ("type_4", "type_6"),
    "type_6":  ("type_5", "type_7"),
    "type_7":  ("type_6", "type_8"),
    "type_8":  ("type_7", "type_9"),
    "type_9":  ("type_8", "type_1"),
}

_WING_LABELS = {
    ("type_1", "type_2"):  "1w2 — 改革型+助人型：理想的利他主义者，有热情推动改变",
    ("type_1", "type_9"):  "1w9 — 改革型+和平型：内省型理想主义者，温和但有原则",
    ("type_2", "type_1"):  "2w1 — 助人型+改革型：服务型理想主义者，帮助建立在原则之上",
    ("type_2", "type_3"):  "2w3 — 助人型+成就型：社交型成就者，通过关系实现成功",
    ("type_3", "type_2"):  "3w2 — 成就型+助人型：魅力型成就者，善于人际影响力",
    ("type_3", "type_4"):  "3w4 — 成就型+自我型：独特型成就者，追求与众不同的成功",
    ("type_4", "type_3"):  "4w3 — 自我型+成就型：精英型创意者，追求独特的成就",
    ("type_4", "type_5"):  "4w5 — 自我型+探索型：内省型创意者，深入探索自我",
    ("type_5", "type_4"):  "5w4 — 探索型+自我型：反叛型思想家，独特的专业视角",
    ("type_5", "type_6"):  "5w6 — 探索型+忠诚型：问题解决者，忠诚于知识和系统",
    ("type_6", "type_5"):  "6w5 — 忠诚型+探索型：冷静型忠诚者，用知识保护自己",
    ("type_6", "type_7"):  "6w7 — 忠诚型+活跃型：乐观型忠诚者，用积极态度应对焦虑",
    ("type_7", "type_6"):  "7w6 — 活跃型+忠诚型：盟友型探索者，关注机会与安全",
    ("type_7", "type_8"):  "7w8 — 活跃型+挑战型：挑战型探索者，充满活力地追求多元",
    ("type_8", "type_7"):  "8w7 — 挑战型+活跃型：充满魅力的挑战者，强势且有感染力",
    ("type_8", "type_9"):  "8w9 — 挑战型+和平型：温和型挑战者，强势但包容",
    ("type_9", "type_8"):  "9w8 — 和平型+挑战型：仲裁者型，在和谐中保持立场",
    ("type_9", "type_1"):  "9w1 — 和平型+改革型：理想主义者型，在平静中追求正确",
}


def _keyword_hits(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def _eval_condition(value: float, op: str, threshold: float) -> bool:
    if op == ">=":  return value >= threshold
    if op == "<=":  return value <= threshold
    if op == "==":  return str(value) == str(threshold)
    if op == ">":   return value > threshold
    if op == "<":   return value < threshold
    return False


def _score_band(score: float) -> str:
    if score <= 24:  return "极弱信号"
    if score <= 49:  return "较弱信号"
    if score <= 74:  return "中等信号"
    return "强信号"


def _apply_type_feature_rules(type_key: str, features: dict) -> tuple[float, list[str], list[str]]:
    score = 15.0
    positive: list[str] = []
    negative: list[str] = []
    rules = _TYPE_FEATURE_RULES.get(type_key, [])
    for feat_name, op, threshold, delta, direction in rules:
        val: float = 0.0
        raw = features.get(feat_name, 0)
        if isinstance(raw, (int, float)):
            val = float(raw)
        elif raw in ("abstract", "grounded"):
            val = 1.0 if raw == "abstract" else 0.0
        if _eval_condition(val, op, threshold):
            if direction == "high":
                score += delta
                positive.append(f"命中 {feat_name}={val} 规则 → +{delta}")
            else:
                score += delta
                negative.append(f"命中反向规则 {feat_name}={val} → {delta}")
    return max(0.0, min(100.0, score)), positive, negative


def _risk_flags_for_type(raw_scores: dict, features: dict) -> list[dict]:
    flags: list[dict] = []
    if raw_scores.get("type_3", 0) >= 72 and features.get("star_structure_score", 0) >= 0.75 and features.get("story_richness_score", 0) < 0.50:
        flags.append({
            "risk_type": "Type3过度包装",
            "severity": "high",
            "description": "成就导向词极高、STAR结构完整但细节贫乏，可能是精心包装的成功叙事而非真实经历。",
            "mitigation": "追问具体执行细节、决策权衡和失败案例来核验。"
        })
    if raw_scores.get("type_6", 0) >= 65 and features.get("hedge_words_ratio", 0) >= 0.010:
        flags.append({
            "risk_type": "Type6一致性不足",
            "severity": "medium",
            "description": "忠诚型特征明显但同时有大量不确定性表达，可能反映内在矛盾，需进一步观察。",
            "mitigation": "用压力问题测试其在不确定情境下的决策稳定性。"
        })
    if raw_scores.get("type_9", 0) >= 65 and features.get("first_person_singular_ratio", 0) < 0.010:
        flags.append({
            "risk_type": "Type9自我表述淡化",
            "severity": "medium",
            "description": "自我主张极度弱化，可能是真实类型特征，也可能是伪装成Type9的防御策略。",
            "mitigation": "用决策类问题追问其真实立场和偏好。"
        })
    return flags


def analyze_enneagram(transcript: str, turns: list[dict], features: dict, knowledge: dict) -> dict:
    word_count = max(len(transcript.replace("\n", "")), 1)

    raw_scores: dict[str, float] = {}
    positive_map: dict[str, list[str]] = defaultdict(list)
    negative_map: dict[str, list[str]] = defaultdict(list)

    for type_key in ALL_TYPES:
        base_score, positive, negative = _apply_type_feature_rules(type_key, features)
        kw_score = min(28, _keyword_hits(transcript, _TYPE_KEYWORDS.get(type_key, [])) * 3)
        final = max(0.0, min(100.0, round(base_score + kw_score)))
        raw_scores[type_key] = final
        if kw_score > 0:
            positive.append(f"关键词命中 → +{kw_score:.0f}")
        positive_map[type_key] = positive[:4]
        negative_map[type_key] = negative[:3]

    ranked = sorted(raw_scores, key=raw_scores.get, reverse=True)
    top_type = ranked[0]
    second_type = ranked[1] if len(ranked) >= 2 else None
    top_score = raw_scores[top_type]
    second_score = raw_scores.get(second_type, 0) if second_type else 0

    confidence_notes: list[str] = []
    confidence = "medium"
    if word_count < 150 or len(turns) <= 1:
        confidence = "low"
        confidence_notes.append("样本量偏少，九型判断置信度有限。")
    if second_type and abs(top_score - second_score) <= 8:
        confidence = "low"
        confidence_notes.append(f"前两名类型得分接近（{top_score} vs {second_score}），主型不确定。")
    elif top_score >= 68 and second_type and (top_score - second_score) >= 20:
        confidence = "high"
        confidence_notes.append("主型信号清晰，且与次型有显著差距。")

    top_meta = _TYPE_META[top_type]
    second_meta = _TYPE_META[second_type] if second_type else None

    wing_key = None
    wing_label: str | None = None
    if second_type and second_type in _WING_MAP.get(top_type, ()):
        wing_key = second_type
        wing_label = _WING_LABELS.get((top_type, second_type), "")
    elif second_type:
        wing_label = f"{top_meta[1]}+?（侧翼不确定）"

    top_two_types = []
    for rank, type_key in enumerate(ranked[:2], start=1):
        meta = _TYPE_META[type_key]
        raw_s = raw_scores[type_key]
        kw_count = _keyword_hits(transcript, _TYPE_KEYWORDS[type_key])
        rules_hit = sum(
            1 for fn, op, th, d, direction in _TYPE_FEATURE_RULES.get(type_key, [])
            if _eval_condition(_to_float(features.get(fn, 0.0)), op, th)
        )
        key_evidence: list[str] = []
        if kw_count >= 5:
            key_evidence.append(f"关键词命中{kw_count}次，语言模式与{meta[1]}高度一致。")
        if rules_hit >= 3:
            key_evidence.append(f"命中{rules_hit}条特征规则，具备{meta[1]}的核心行为模式。")
        if not key_evidence:
            key_evidence.append("信号较弱，需结合追问进一步验证。")

        top_two_types.append({
            "rank": rank,
            "type_number": meta[2],
            "label": meta[1],
            "raw_score": int(raw_s),
            "confidence_level": "high" if raw_s >= 65 else "medium" if raw_s >= 50 else "low",
            "key_evidence": key_evidence,
        })

    risk_flags = _risk_flags_for_type(raw_scores, features)

    supplemental_probes: list[dict] = []
    if top_two_types:
        primary_key = f"type_{top_two_types[0]['type_number']}"
        type_probes = knowledge.get("types", {}).get(primary_key, {}).get("probe_questions", {})
        confirm_qs = type_probes.get("confirm", [])
        if confirm_qs:
            supplemental_probes.append({
                "target_type": top_two_types[0]["type_number"],
                "question": confirm_qs[0],
                "purpose": f"进一步验证 {top_two_types[0]['label']} 的类型判断。"
            })

    primary_data = knowledge.get("types", {}).get(top_type, {})
    if top_score >= 70:
        interp_source = primary_data.get("behavioral_cues", {}).get("positive", [""])[0]
        primary_interpretation = interp_source or f"强烈呈现{top_meta[1]}特征。"
    elif top_score >= 50:
        primary_interpretation = f"呈现一定{top_meta[1]}倾向，但证据尚不够充分。"
    else:
        primary_interpretation = f"轻微{top_meta[1]}倾向，整体类型特征不够突出。"

    motivational_pattern = {
        "dominant_motive":  primary_data.get("core_motivation", ""),
        "core_fear":        primary_data.get("core_fear", ""),
        "core_desire":      primary_data.get("core_desire", ""),
    }

    return {
        "meta": {
            "sample_words": word_count,
            "turn_count": len(turns),
            "confidence": confidence,
            "confidence_basis": " ".join(confidence_notes) or "样本量适中，有一定推断依据。",
        },
        "primary_type": {
            "type_number":            top_meta[2],
            "label":                  top_meta[1],
            "core_motivation_confidence": "high" if top_score >= 65 else "medium" if top_score >= 50 else "low",
            "interpretation":        primary_interpretation,
        },
        "secondary_type": {
            "type_number":            second_meta[2] if second_meta else None,
            "label":                  second_meta[1] if second_meta else None,
            "interpretation":         f"次要类型{second_meta[1] if second_meta else '不确定'}。" if second_meta else "次要类型信号不够清晰。"
        },
        "wing":  wing_label or f"{top_meta[1]}+?（需更多样本推断侧翼）",
        "top_two_types": top_two_types,
        "motivational_pattern": motivational_pattern,
        "risk_flags": risk_flags,
        "evidence_summary": {
            type_key: {
                "score":           int(raw_scores[type_key]),
                "band":            _score_band(raw_scores[type_key]),
                "keyword_hits":    _keyword_hits(transcript, _TYPE_KEYWORDS[type_key]),
                "feature_hits":    sum(
                    1 for fn, op, th, d, direction in _TYPE_FEATURE_RULES.get(type_key, [])
                    if _eval_condition(
                        float(features.get(fn, 0)) if not isinstance(features.get(fn), str) else (1.0 if features.get(fn) == "abstract" else 0.0),
                        op, th
                    )
                ),
                "evidence_for":    positive_map[type_key],
                "evidence_against": negative_map[type_key],
            }
            for type_key in ranked[:4]
        },
        "supplemental_probes": supplemental_probes,
    }
