from __future__ import annotations

import re


LOGICAL_CONNECTORS = ("因为", "所以", "但是", "不过", "因此", "然后", "同时", "另外", "如果", "尽管", "首先", "其次")
CONTRAST_CONNECTORS = ("但是", "不过", "然而", "可是", "尽管")
HEDGE_WORDS = ("可能", "也许", "大概", "相对", "尽量", "通常", "有点", "某种程度")
CERTAINTY_WORDS = ("一定", "明确", "必须", "肯定", "绝对", "显著", "直接")
EMOTIONAL_WORDS = ("开心", "兴奋", "担心", "焦虑", "压力", "有趣", "热情", "失望", "满意", "成就感")
SOCIAL_WORDS = ("团队", "同事", "沟通", "协作", "客户", "大家", "伙伴", "配合", "关系", "反馈")
ACTION_WORDS = ("推进", "推动", "主导", "解决", "完成", "拿下", "落地", "达成", "执行", "拆解", "优化", "协调", "跟进", "交付")
ACHIEVEMENT_WORDS = ("结果", "目标", "提升", "增长", "突破", "完成", "指标", "达成", "产出", "收益")
PROCESS_WORDS = ("流程", "步骤", "方法", "机制", "规范", "复盘", "验证", "分析", "依据", "计划")
DETAIL_WORDS = ("细节", "数据", "指标", "依据", "具体", "风险", "条件", "假设", "边界", "步骤")
RISK_WORDS = ("风险", "问题", "异常", "bug", "隐患", "不确定", "边界", "代价", "错误", "失败")
REFLECTION_WORDS = ("复盘", "总结", "反思", "学习", "调整", "意识到", "判断", "思考")
STAR_WORDS = {
    "situation": ("当时", "背景", "情况", "场景", "遇到"),
    "task": ("目标", "任务", "负责", "要求"),
    "action": ("我做了", "我先", "推进", "协调", "分析", "拆解", "优化", "沟通"),
    "result": ("结果", "最后", "达成", "提升", "降低", "完成"),
}
PRONOUN_GROUPS = {
    "first_person_singular": ("我", "自己"),
    "first_person_plural": ("我们", "大家"),
    "second_person": ("你", "你们"),
    "third_person": ("他", "她", "他们", "她们"),
}
BUZZWORDS = ("赋能", "闭环", "抓手", "颗粒度", "协同", "体系化", "方法论", "全链路", "owner")
ABSTRACT_WORDS = ("价值", "战略", "方向", "认知", "抽象", "体系", "全局", "原则")


def _count_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(text.count(keyword) for keyword in keywords)


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total > 0 else 0.0


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。！？!?；;\n]+", text) if part.strip()]


def _topic_stability(turns: list[dict]) -> float:
    if len(turns) <= 1:
        return 0.6
    question_types = [turn["question_type"] for turn in turns]
    diversity = len(set(question_types)) / max(len(question_types), 1)
    return round(min(1.0, 0.45 + diversity * 0.4), 4)


def _story_richness(text: str) -> float:
    evidence_count = _count_keywords(text, DETAIL_WORDS) + len(re.findall(r"\d+%|\d+个|\d+天|\d+周|\d+月", text))
    return round(min(1.0, 0.2 + evidence_count / 25), 4)


def extract_features(turns: list[dict]) -> dict:
    candidate_text = "\n".join(turn["answer"] for turn in turns if turn["answer"]).strip()
    sentences = _split_sentences(candidate_text)
    total_chars = max(len(re.sub(r"\s+", "", candidate_text)), 1)
    sentence_lengths = [len(sentence) for sentence in sentences]

    pronoun_counts = {key: _count_keywords(candidate_text, value) for key, value in PRONOUN_GROUPS.items()}
    keyword_counts = {
        "action": _count_keywords(candidate_text, ACTION_WORDS),
        "emotional": _count_keywords(candidate_text, EMOTIONAL_WORDS),
        "social": _count_keywords(candidate_text, SOCIAL_WORDS),
        "certainty": _count_keywords(candidate_text, CERTAINTY_WORDS),
        "hedge": _count_keywords(candidate_text, HEDGE_WORDS),
        "achievement": _count_keywords(candidate_text, ACHIEVEMENT_WORDS),
        "process": _count_keywords(candidate_text, PROCESS_WORDS),
        "detail": _count_keywords(candidate_text, DETAIL_WORDS),
        "risk": _count_keywords(candidate_text, RISK_WORDS),
        "logical": _count_keywords(candidate_text, LOGICAL_CONNECTORS),
        "contrast": _count_keywords(candidate_text, CONTRAST_CONNECTORS),
        "reflection": _count_keywords(candidate_text, REFLECTION_WORDS),
        "abstract": _count_keywords(candidate_text, ABSTRACT_WORDS),
        "buzzword": _count_keywords(candidate_text, BUZZWORDS),
    }

    star_hits = {key: _count_keywords(candidate_text, words) for key, words in STAR_WORDS.items()}
    star_structure_score = round(sum(1 for count in star_hits.values() if count > 0) / len(STAR_WORDS), 4)
    team_count = pronoun_counts["first_person_plural"] + _count_keywords(candidate_text, ("团队", "同事", "大家"))
    self_count = pronoun_counts["first_person_singular"]
    people_focus = keyword_counts["social"]
    problem_focus = keyword_counts["process"] + keyword_counts["detail"] + keyword_counts["risk"]
    action_bias = keyword_counts["action"] - keyword_counts["reflection"]

    return {
        "text_length": total_chars,
        "sentence_count": len(sentences),
        "avg_sentence_length": round(sum(sentence_lengths) / max(len(sentence_lengths), 1), 2),
        "action_verbs_ratio": _ratio(keyword_counts["action"], total_chars),
        "adjective_ratio": _ratio(len(re.findall(r"[非常很挺太真特别]", candidate_text)), total_chars),
        "emotional_words_ratio": _ratio(keyword_counts["emotional"], total_chars),
        "social_words_ratio": _ratio(keyword_counts["social"], total_chars),
        "certainty_words_ratio": _ratio(keyword_counts["certainty"], total_chars),
        "hedge_words_ratio": _ratio(keyword_counts["hedge"], total_chars),
        "achievement_words_ratio": _ratio(keyword_counts["achievement"], total_chars),
        "process_words_ratio": _ratio(keyword_counts["process"], total_chars),
        "detail_words_ratio": _ratio(keyword_counts["detail"], total_chars),
        "risk_words_ratio": _ratio(keyword_counts["risk"], total_chars),
        "first_person_singular_ratio": _ratio(pronoun_counts["first_person_singular"], total_chars),
        "first_person_plural_ratio": _ratio(pronoun_counts["first_person_plural"], total_chars),
        "second_person_ratio": _ratio(pronoun_counts["second_person"], total_chars),
        "third_person_ratio": _ratio(pronoun_counts["third_person"], total_chars),
        "imperative_like_ratio": _ratio(_count_keywords(candidate_text, ("必须", "先", "直接", "马上", "尽快")), total_chars),
        "question_ratio": _ratio(candidate_text.count("？") + candidate_text.count("?"), max(len(sentences), 1)),
        "qualifier_ratio": _ratio(_count_keywords(candidate_text, ("如果", "取决于", "前提", "通常", "在这种情况下")), total_chars),
        "logical_connector_ratio": _ratio(keyword_counts["logical"], total_chars),
        "contrast_connector_ratio": _ratio(keyword_counts["contrast"], total_chars),
        "modal_verb_ratio": _ratio(_count_keywords(candidate_text, ("会", "可以", "应该", "需要")), total_chars),
        "star_structure_score": star_structure_score,
        "topic_stability_score": _topic_stability(turns),
        "self_vs_team_orientation": "team" if team_count > self_count else "self",
        "problem_vs_people_focus": "problem" if problem_focus >= people_focus else "people",
        "action_vs_reflection_balance": "action" if action_bias > 1 else ("reflection" if action_bias < -1 else "balanced"),
        "abstraction_level": "abstract" if keyword_counts["abstract"] > keyword_counts["detail"] else "grounded",
        "story_richness_score": _story_richness(candidate_text),
        "buzzword_density": _ratio(keyword_counts["buzzword"], total_chars),
        "star_hits": star_hits,
    }


def feature_highlights(features: dict) -> list[dict]:
    return [
        {"label": "STAR 完整度", "value": f"{int(features['star_structure_score'] * 100)}%"},
        {"label": "逻辑连接词密度", "value": f"{features['logical_connector_ratio']:.4f}"},
        {"label": "行动词密度", "value": f"{features['action_verbs_ratio']:.4f}"},
        {"label": "团队导向", "value": features["self_vs_team_orientation"]},
        {"label": "问题/人际焦点", "value": features["problem_vs_people_focus"]},
        {"label": "行动/反思平衡", "value": features["action_vs_reflection_balance"]},
        {"label": "故事细节丰富度", "value": f"{int(features['story_richness_score'] * 100)}%"},
    ]
