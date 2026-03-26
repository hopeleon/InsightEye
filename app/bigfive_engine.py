from __future__ import annotations

from collections import defaultdict

DIMENSIONS = ("O", "C", "E", "A", "N")

_TYPE_KEYWORDS = {
    "O": [
        "探索", "尝试", "创新", "好奇", "设计", "抽象", "概念", "思维",
        "模型", "框架", "假设", "可能", "多元", "跨界", "视角",
        "另一个角度", "不一样", "有意思", "新颖", "独特",
    ],
    "C": [
        "计划", "目标", "标准", "规范", "流程", "步骤", "检查", "确保",
        "完成", "交付", "承诺", "跟进", "负责", "任务", "阶段", "优先",
        "分三步", "拆解", "自律", "按时", "质量", "底线",
    ],
    "E": [
        "大家", "一起", "聊天", "交流", "聚会", "热闹", "开心", "兴奋",
        "激动", "有意思", "和人", "社交", "外向", "活跃", "朋友", "氛围",
        "人一多", "带劲", "链接", "认识", "朋友们",
    ],
    "A": [
        "帮助", "支持", "配合", "理解", "信任", "合作", "和气", "照顾",
        "让步", "包容", "体谅", "共识", "协调", "退让", "倾听",
        "对方", "大家都不容易", "各退一步", "和谐",
    ],
    "N": [
        "担心", "焦虑", "压力", "害怕", "紧张", "不安", "失控",
        "崩溃", "纠结", "恐惧", "忧虑", "失眠", "睡不着", "怎么办",
    ],
}

_NEGATIVE_KEYWORDS = {
    "O": ["稳定", "传统", "按部就班", "标准做法", "不需要创新"],
    "C": ["差不多就行", "到时候再说", "灵活应变", "先做再说"],
    "E": ["自己", "独立", "安静", "内向", "独处", "一个人"],
    "A": ["直接说", "我不认同", "必须按我的来", "竞争", "据理力争"],
    "N": ["冷静", "稳住", "没什么", "照常", "淡定", "平静"],
}



def _keyword_hits(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def _apply_feature_rules(dim: str, features: dict) -> tuple[float, list[str], list[str]]:
    positive: list[str] = []
    negative: list[str] = []
    score = 40.0

    if dim == "O":
        if features.get("abstraction_level") == "abstract":
            score += 15
            positive.append("Abstract framing is stronger than pure execution detail.")
        if features.get("hedge_words_ratio", 0) >= 0.005:
            score += 10
            positive.append("The answer keeps multiple possibilities open.")
        if features.get("qualifier_ratio", 0) >= 0.006:
            score += 8
            positive.append("The speaker uses conditions and caveats, showing exploratory thinking.")
        if features.get("process_words_ratio", 0) >= 0.006:
            score += 6
            positive.append("Multiple methods or paths are mentioned.")
        if features.get("abstraction_level") == "grounded" and features.get("detail_words_ratio", 0) >= 0.010:
            score -= 8
            negative.append("The answer stays mostly concrete and execution-oriented.")

    if dim == "C":
        if features.get("process_words_ratio", 0) >= 0.008:
            score += 15
            positive.append("Process and standards language is frequent.")
        if features.get("detail_words_ratio", 0) >= 0.008:
            score += 12
            positive.append("Detail density suggests accuracy and quality awareness.")
        if features.get("star_structure_score", 0) >= 0.60:
            score += 10
            positive.append("The story has a relatively complete STAR structure.")
        if features.get("logical_connector_ratio", 0) >= 0.008:
            score += 8
            positive.append("Logical connectors indicate structured expression.")
        if features.get("qualifier_ratio", 0) >= 0.006:
            score += 5
            positive.append("Boundary and condition awareness is visible.")
        if features.get("hedge_words_ratio", 0) >= 0.010:
            score -= 6
            negative.append("Too much hesitation weakens conscientiousness signals.")

    if dim == "E":
        if features.get("emotional_words_ratio", 0) >= 0.005:
            score += 15
            positive.append("Emotional language adds outward expressive energy.")
        if features.get("social_words_ratio", 0) >= 0.006:
            score += 12
            positive.append("The answer pays visible attention to people and interaction.")
        if features.get("first_person_plural_ratio", 0) >= 0.006:
            score += 10
            positive.append("Collective framing appears often.")
        if features.get("story_richness_score", 0) >= 0.55:
            score += 7
            positive.append("The story is vivid and outward-facing.")
        if features.get("avg_sentence_length", 0) >= 15:
            score += 5
            positive.append("Longer sentences support fuller outward expression.")
        if features.get("social_words_ratio", 0) < 0.005 and features.get("process_words_ratio", 0) >= 0.008:
            score -= 10
            negative.append("The answer leans more toward execution than interaction.")

    if dim == "A":
        if features.get("first_person_plural_ratio", 0) >= 0.008:
            score += 15
            positive.append("Collective pronouns suggest cooperation and shared framing.")
        if features.get("social_words_ratio", 0) >= 0.006:
            score += 12
            positive.append("People-oriented words suggest empathy and coordination.")
        if features.get("hedge_words_ratio", 0) >= 0.004:
            score += 8
            positive.append("The tone is moderated rather than confrontational.")
        if features.get("contrast_connector_ratio", 0) >= 0.006:
            score -= 10
            negative.append("Frequent contrast markers can indicate friction or challenge posture.")
        if features.get("imperative_like_ratio", 0) >= 0.010:
            score -= 8
            negative.append("Directive language weakens agreeableness.")

    if dim == "N":
        if features.get("emotional_words_ratio", 0) >= 0.007:
            score += 18
            positive.append("Emotional intensity points to pressure sensitivity.")
        if features.get("risk_words_ratio", 0) >= 0.006:
            score += 12
            positive.append("Risk and uncertainty are salient in the answer.")
        if features.get("hedge_words_ratio", 0) >= 0.008:
            score += 8
            positive.append("Frequent hedging suggests lower certainty under ambiguity.")
        if features.get("certainty_words_ratio", 0) >= 0.006:
            score -= 10
            negative.append("Direct certainty reduces neuroticism cues.")
        if features.get("hedge_words_ratio", 0) < 0.003:
            score -= 6
            negative.append("Low hedging suggests steadier emotional baseline.")

    return max(0.0, min(100.0, score)), positive, negative


def _score_band(score: float) -> str:
    if score <= 24:
        return "weak"
    if score <= 49:
        return "light"
    if score <= 74:
        return "moderate"
    return "strong"


def _confidence_level(word_count: int, turn_count: int, scores: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    if word_count < 60 or turn_count <= 1:
        level = "low"
        notes.append("Sample size is small, so the result is directional only.")
    elif word_count >= 300 and turn_count >= 3:
        level = "high"
        notes.append("The sample is large enough to support a stable reading.")
    else:
        level = "medium"

    extreme_count = sum(1 for value in scores.values() if value > 90 or value < 12)
    if extreme_count >= 3:
        level = "low"
        notes.append("Several dimensions are extreme, so presentation bias is possible.")
    return level, notes


def _n_artifacts_detection(features: dict, scores: dict, turn_count: int) -> tuple[bool, str]:
    neuroticism = scores.get("N", 0)
    extraversion = scores.get("E", 0)
    if neuroticism >= 65 and extraversion >= 70:
        return True, "High N with high E may reflect interview activation rather than baseline trait."
    if neuroticism >= 60 and turn_count >= 2:
        return False, "N signals appear across more than one turn, so they may be stable."
    if neuroticism >= 60:
        return True, "N signals appear in limited context and still need validation."
    return False, "N signal is not especially prominent in this sample."


def _detect_cross_patterns(scores: dict, features: dict) -> list[dict]:
    patterns = []
    openness = scores.get("O", 0)
    conscientiousness = scores.get("C", 0)
    extraversion = scores.get("E", 0)
    agreeableness = scores.get("A", 0)
    neuroticism = scores.get("N", 0)

    if openness >= 65 and conscientiousness >= 65:
        patterns.append({
            "pattern_name": "creative_operator",
            "interpretation": "Curiosity and execution discipline appear together.",
            "workplace_implications": "Useful where experimentation still needs strong delivery discipline.",
        })
    if extraversion >= 65 and agreeableness >= 65:
        patterns.append({
            "pattern_name": "warm_connector",
            "interpretation": "The person looks socially active and cooperative.",
            "workplace_implications": "Useful in roles with heavy cross-functional communication.",
        })
    if conscientiousness >= 65 and neuroticism >= 60:
        patterns.append({
            "pattern_name": "anxious_achiever",
            "interpretation": "High standards may coexist with elevated pressure sensitivity.",
            "workplace_implications": "Delivery quality can be high, but pressure tolerance should be checked.",
        })
    if conscientiousness >= 65 and neuroticism <= 40:
        patterns.append({
            "pattern_name": "steady_executor",
            "interpretation": "The person looks disciplined and emotionally steady.",
            "workplace_implications": "Useful in high-pressure or high-standard roles.",
        })
    if openness >= 65 and conscientiousness <= 45:
        patterns.append({
            "pattern_name": "free_explorer",
            "interpretation": "Ideas may outpace follow-through.",
            "workplace_implications": "Needs delivery support in execution-heavy environments.",
        })
    if extraversion >= 65 and agreeableness <= 45:
        patterns.append({
            "pattern_name": "forceful_influencer",
            "interpretation": "The person may combine social energy with a stronger challenge posture.",
            "workplace_implications": "Can drive fast decisions but may create interpersonal friction.",
        })
    if agreeableness >= 65 and neuroticism <= 40:
        patterns.append({
            "pattern_name": "stable_supporter",
            "interpretation": "The person looks emotionally steady and cooperative.",
            "workplace_implications": "Useful in roles requiring stable collaboration and service mindset.",
        })
    if features.get("story_richness_score", 0) >= 0.7 and openness >= 55 and conscientiousness >= 55:
        patterns.append({
            "pattern_name": "clear_story_specialist",
            "interpretation": "The story is detailed while still showing both exploration and structure.",
            "workplace_implications": "Useful in roles that require both technical depth and communication clarity.",
        })
    return patterns


def analyze_bigfive(transcript: str, turns: list[dict], features: dict, knowledge: dict) -> dict:
    word_count = max(len(transcript.replace("\n", "")), 1)
    scores: dict[str, int] = {}
    positive_map: dict[str, list[str]] = defaultdict(list)
    negative_map: dict[str, list[str]] = defaultdict(list)

    for dim in DIMENSIONS:
        base_score, positive, negative = _apply_feature_rules(dim, features)
        keyword_score = min(22, _keyword_hits(transcript, _TYPE_KEYWORDS[dim]) * 3)
        negative_keyword_penalty = min(10, _keyword_hits(transcript, _NEGATIVE_KEYWORDS[dim]) * 4)
        final_score = int(max(0, min(100, round(base_score + keyword_score - negative_keyword_penalty))))
        scores[dim] = final_score
        if keyword_score > 0:
            positive.append(f"Language cues for {dim} are present.")
        if not positive:
            positive.append("Direct supporting evidence for this dimension is limited.")
        positive_map[dim] = positive[:4]
        negative_map[dim] = negative[:3]

    confidence, confidence_notes = _confidence_level(word_count, len(turns), scores)
    n_artifact_flag, n_artifact_notes = _n_artifacts_detection(features, scores, len(turns))
    ranking = sorted(scores, key=scores.get, reverse=True)
    dominant_trait = ranking[0]
    secondary_traits = [dim for dim in ranking[1:3] if scores[dim] >= scores[dominant_trait] * 0.7]

    trait_interpretations = {}
    for dim in DIMENSIONS:
        score = scores[dim]
        interpretation_key = "high" if score >= 75 else "medium" if score >= 50 else "low"
        trait_interpretations[dim] = knowledge["dimensions"].get(dim, {}).get("score_interpretation", {}).get(interpretation_key, "")

    supplemental_probes = []
    for dim in ranking[:2]:
        probes = knowledge["dimensions"].get(dim, {}).get("probe_questions", {})
        confirm_questions = probes.get("confirm", [])
        if confirm_questions:
            supplemental_probes.append({
                "target_dimension": dim,
                "question": confirm_questions[0],
                "purpose": f"Validate the current reading for {dim}.",
            })

    return {
        "meta": {
            "sample_words": word_count,
            "turn_count": len(turns),
            "confidence": confidence,
            "confidence_notes": confidence_notes,
            "n_artifact_flag": n_artifact_flag,
            "n_artifact_notes": n_artifact_notes,
        },
        "scores": scores,
        "ranking": ranking,
        "dominant_trait": dominant_trait,
        "secondary_traits": secondary_traits,
        "trait_interpretations": trait_interpretations,
        "cross_dimension_patterns": _detect_cross_patterns(scores, features),
        "evidence_summary": {
            dim: {
                "score": scores[dim],
                "band": _score_band(scores[dim]),
                "evidence_for": positive_map[dim],
                "evidence_against": negative_map[dim],
            }
            for dim in DIMENSIONS
        },
        "supplemental_probes": supplemental_probes,
    }
