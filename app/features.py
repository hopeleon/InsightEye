from __future__ import annotations

import re
from typing import Callable


LOGICAL_CONNECTORS = ("因为", "所以", "但是", "不过", "因此", "然后", "同时", "另外", "如果", "尽管", "首先", "其次")
CONTRAST_CONNECTORS = ("但是", "不过", "然而", "可是", "尽管")
HEDGE_WORDS = ("可能", "也许", "大概", "相对", "尽量", "通常", "有点", "某种程度")
CERTAINTY_WORDS = ("一定", "明确", "必须", "肯定", "绝对", "显著", "直接")
EMOTIONAL_WORDS = ("开心", "兴奋", "担心", "焦虑", "压力", "有趣", "热情", "失望", "满意", "成就感")
SOCIAL_WORDS = ("团队", "同事", "沟通", "协作", "客户", "大家", "伙伴", "配合", "关系", "反馈")
ACTION_WORDS = ("推进", "推动", "主导", "解决", "完成", "拿下", "落地", "达成", "执行", "拆解", "优化", "协调", "跟进", "交付")
ACHIEVEMENT_WORDS = ("结果", "目标", "提升", "增长", "突破", "完成", "指标", "达成", "产出", "收益")
PROCESS_WORDS = ("流程", "步骤", "方法", "机制", "规范", "复盘", "验证", "分析", "依据", "计划")
DETAIL_WORDS = ("细节", "数据", "指标", "依据", "具体", "风险", "假设", "边界", "步骤")
RISK_WORDS = ("风险", "问题", "异常", "bug", "隐患", "不确定", "边界", "代价", "错误", "失败")
REFLECTION_WORDS = ("复盘", "总结", "反思", "学习", "调整", "意识到", "判断", "思考")
STAR_WORDS = {
    "situation": ("当时", "背景", "情况", "场景", "遇到", "接手", "上线", "项目初期", "入职时", "deadline"),
    "task": ("目标", "任务", "负责", "要求", "我的职责", "KPI", "OKR", "我这边", "我被安排", "我主要"),
    "action": ("我做了", "我先", "推进", "协调", "分析", "拆解", "优化", "沟通", "我搭建", "我写了", "我改了", "我提了", "我选了"),
    "result": ("结果", "最后", "达成", "提升", "降低", "完成", "提升了", "降低了", "超额", "最终"),
}
PRONOUN_GROUPS = {
    "first_person_singular": ("我", "自己"),
    "first_person_plural": ("我们", "大家"),
    "second_person": ("你", "你们"),
    "third_person": ("他", "她", "他们", "她们"),
}
BUZZWORDS = ("赋能", "闭环", "抓手", "颗粒度", "协同", "体系化", "方法论", "全链路", "owner")
ABSTRACT_WORDS = ("价值", "战略", "方向", "认知", "抽象", "体系", "全局", "原则")
# ─── STAR 分析专用词表（对应 STAR.yaml input_features） ───
QUANTITATIVE_WORDS = (
    "提升了", "降低了", "增长", "减少", "完成了", "达成了", "超额", "倍", "%",
    "万元", "NPS", "DAU", "MAU", "转化率", "留存率", "增长到", "下降至",
    "从", "到", "共", "累计", "达到", "超过", "不足", "增加", "减少",
    "提高了", "扩大了", "缩减了",
)
TEMPORAL_WORDS = (
    "当时", "那段时间", "那一年", "接手时", "上线前", "入职时", "项目初期",
    "从零开始", "deadline", "截止", "年前", "年后", "周一", "周五",
    "后来", "最后", "最终", "首先", "其次", "第一步", "第二步", "第三步",
    "紧接着", "随后", "一周后", "一个月后", "半年后",
)
CONSTRAINT_WORDS = (
    "人手不够", "预算有限", "时间紧", "资源不足", "跨部门", "紧急",
    "压力下", "在没有", "缺乏", "预算紧张", "排期紧", "人少", "时间不够",
    "难度大", "复杂", "多方", "多部门", "多团队",
)
VAGUE_RESULT_WORDS = (
    "效果不错", "还不错", "挺满意的", "有提升", "有所改善", "完成得很好",
    "比较成功", "还可以", "挺好的", "还可以", "明显改善", "明显好转",
    "不错", "挺好", "很好", "满意", "改善", "提升", "改善了",
)
TOOL_METHOD_WORDS = (
    "系统", "工具", "文档", "平台", "APP", "数据库", "接口", "流程",
    "表格", "模板", "会议", "邮件", "需求文档", "设计文档", "PRD",
    "MRD", "方案", "原型", "架构", "代码", "SQL", "Python", "Excel",
    "PPT", "会议纪要", "周报", "日报", "OKR", "KPI",
)
STEP_CONNECTOR_WORDS = (
    "首先", "然后", "接着", "随后", "紧接着", "下一步", "第一步", "第二步",
    "第三步", "最后", "最终", "再", "之后", "于是", "接着我", "首先我",
    "于是我", "之后我",
)
CONTEXT_MARKER_WORDS = (
    "当时", "那时候", "那段时间", "接手时", "上线前", "项目初期", "入职时",
    "从零开始", "人手不够", "预算有限", "跨部门", "紧急", "deadline",
    "当时情况", "背景下", "业务", "数据", "团队规模", "部门", "公司",
)
RESULT_ATTRIBUTION_SELF_WORDS = (
    "我的", "我主导", "我带团队", "在我推动下", "我决定", "我拍板",
    "我推动", "我负责", "我的方案", "我的决策", "我坚持", "独立完成",
    "我任内", "我牵头",
)
TEAM_RESULT_WORDS = (
    "我们一起", "团队", "大家一起", "团队协作", "分工配合", "同事们",
    "我们决定", "我们讨论", "大家一起", "协作完成", "共同",
)


def _count_keywords(text: str, keywords: tuple[str, ...]) -> int:
    return sum(text.count(keyword) for keyword in keywords)


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total > 0 else 0.0


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[。！？!?；;\n]+", text) if part.strip()]


def _star_feature(
    text: str,
    total_chars: int,
    strong_kw: tuple[str, ...],
    weak_kw: tuple[str, ...],
    required_syntax: list[str] | None = None,
) -> dict[str, float | int]:
    strong = _count_keywords(text, strong_kw)
    weak = _count_keywords(text, weak_kw)
    score = 0.0
    if strong > 0 and weak == 0:
        score = min(1.0, 0.3 + strong * 0.15)
    elif strong > 0 and weak > 0:
        score = min(1.0, 0.2 + (strong - weak * 0.5) * 0.15)
    else:
        score = 0.1
    syntax_bonus = 0.0
    if required_syntax:
        for pattern in required_syntax:
            if re.search(pattern, text):
                syntax_bonus = 0.1
                break
    return {
        "score": round(min(1.0, score + syntax_bonus), 4),
        "strong_hits": strong,
        "weak_hits": weak,
    }


def _topic_stability(turns: list[dict]) -> float:
    if len(turns) <= 1:
        return 0.6
    question_types = [turn["question_type"] for turn in turns]
    diversity = len(set(question_types)) / max(len(question_types), 1)
    return round(min(1.0, 0.45 + diversity * 0.4), 4)


def _story_richness(text: str) -> float:
    evidence_count = _count_keywords(text, DETAIL_WORDS) + len(re.findall(r"\d+%|\d+个|\d+天|\d+周|\d+月|\d+年|\d+人", text))
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
        # STAR 专用
        "quantitative": _count_keywords(candidate_text, QUANTITATIVE_WORDS),
        "temporal": _count_keywords(candidate_text, TEMPORAL_WORDS),
        "constraint": _count_keywords(candidate_text, CONSTRAINT_WORDS),
        "vague_result": _count_keywords(candidate_text, VAGUE_RESULT_WORDS),
        "tool_method": _count_keywords(candidate_text, TOOL_METHOD_WORDS),
        "step_connector": _count_keywords(candidate_text, STEP_CONNECTOR_WORDS),
        "context_marker": _count_keywords(candidate_text, CONTEXT_MARKER_WORDS),
        "result_attribution_self": _count_keywords(candidate_text, RESULT_ATTRIBUTION_SELF_WORDS),
        "team_result": _count_keywords(candidate_text, TEAM_RESULT_WORDS),
    }

    star_hits = {key: _count_keywords(candidate_text, words) for key, words in STAR_WORDS.items()}
    star_structure_score = round(sum(1 for count in star_hits.values() if count > 0) / len(STAR_WORDS), 4)
    team_count = pronoun_counts["first_person_plural"] + _count_keywords(candidate_text, ("团队", "同事", "大家"))
    self_count = pronoun_counts["first_person_singular"]
    people_focus = keyword_counts["social"]
    problem_focus = keyword_counts["process"] + keyword_counts["detail"] + keyword_counts["risk"]
    action_bias = keyword_counts["action"] - keyword_counts["reflection"]

    # ─── STAR 四维度独立评分（S/T/A/R，各 0~1） ───
    s_feature = _star_feature(
        candidate_text, total_chars,
        strong_kw=STAR_WORDS["situation"],
        weak_kw=("后来", "有一次"),
        required_syntax=[r"当时", r"那(个|段|时)", r"背景"],
    )
    t_feature = _star_feature(
        candidate_text, total_chars,
        strong_kw=STAR_WORDS["task"],
        weak_kw=STAR_WORDS["task"][4:],  # 弱化"团队"叙事
    )
    a_feature = _star_feature(
        candidate_text, total_chars,
        strong_kw=(
            "我搭建了", "我写了", "我改了", "我提了", "我选了", "我谈了", "我拒了",
            "我删了", "我重做了", "我拍板", "我分配了", "我顶着压力", "我独自",
            "我先", "我最后", "我独自", "我先斩后奏",
        ),
        weak_kw=("推进了", "完善了", "优化了", "改进了", "加强了", "协调了"),
        required_syntax=[r"我.{0,8}(了|的)", r"第一步", r"首先"],
    )
    r_feature = _star_feature(
        candidate_text, total_chars,
        strong_kw=QUANTITATIVE_WORDS + RESULT_ATTRIBUTION_SELF_WORDS,
        weak_kw=VAGUE_RESULT_WORDS,
        required_syntax=[r"\d+", r"%", r"提升了", r"降低了", r"从.{0,10}到"],
    )

    # step_connector_ratio（步骤连接词）
    step_connector_ratio = _ratio(keyword_counts["step_connector"], total_chars)
    # contrast_connector_ratio 已在上方 keyword_counts 中

    # self_vs_team_orientation 数值版（供 star_analyzer 使用）
    self_team_ratio = round(self_count / max(team_count, 1), 4)

    # 团队结果归因比例
    team_result_ratio = _ratio(keyword_counts["team_result"], max(keyword_counts["team_result"] + keyword_counts["result_attribution_self"], 1))

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
        "abstract_words_ratio": _ratio(keyword_counts["abstract"], total_chars),
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
        # ─── STAR 四维度独立分数（features.py 层） ───
        "star_s_score": s_feature["score"],
        "star_t_score": t_feature["score"],
        "star_a_score": a_feature["score"],
        "star_r_score": r_feature["score"],
        # ─── STAR.yaml [待实现] 特征 ───
        "quantitative_words_ratio": _ratio(keyword_counts["quantitative"], total_chars),
        "temporal_words_ratio": _ratio(keyword_counts["temporal"], total_chars),
        "constraint_words_ratio": _ratio(keyword_counts["constraint"], total_chars),
        "vague_result_words_ratio": _ratio(keyword_counts["vague_result"], total_chars),
        "tool_method_words_ratio": _ratio(keyword_counts["tool_method"], total_chars),
        "step_connector_ratio": step_connector_ratio,
        "context_marker_density": _ratio(keyword_counts["context_marker"], total_chars),
        "result_attribution_self_ratio": _ratio(keyword_counts["result_attribution_self"], total_chars),
        "team_result_attribution_ratio": team_result_ratio,
        # ─── 供 star_analyzer 使用的原始计数 ───
        "_star_s_raw": {"strong": s_feature["strong_hits"], "weak": s_feature["weak_hits"]},
        "_star_t_raw": {"strong": t_feature["strong_hits"], "weak": t_feature["weak_hits"]},
        "_star_a_raw": {"strong": a_feature["strong_hits"], "weak": a_feature["weak_hits"]},
        "_star_r_raw": {"strong": r_feature["strong_hits"], "weak": r_feature["weak_hits"]},
        "_self_count": self_count,
        "_team_count": team_count,
        "_self_team_ratio": self_team_ratio,
        "_pronoun_counts": pronoun_counts,
        "_keyword_counts": keyword_counts,
    }


def feature_highlights(features: dict) -> list[dict]:
    return [
        {"label": "STAR 完整度", "value": f"{int(features['star_structure_score'] * 100)}%"},
        {"label": "S/T/A/R 独立分", "value": f"S={int(features['star_s_score']*100)} T={int(features['star_t_score']*100)} A={int(features['star_a_score']*100)} R={int(features['star_r_score']*100)}"},
        {"label": "逻辑连接词密度", "value": f"{features['logical_connector_ratio']:.4f}"},
        {"label": "行动词密度", "value": f"{features['action_verbs_ratio']:.4f}"},
        {"label": "团队导向", "value": features["self_vs_team_orientation"]},
        {"label": "问题/人际焦点", "value": features["problem_vs_people_focus"]},
        {"label": "行动/反思平衡", "value": features["action_vs_reflection_balance"]},
        {"label": "故事细节丰富度", "value": f"{int(features['story_richness_score'] * 100)}%"},
        {"label": "步骤连接词密度", "value": f"{features['step_connector_ratio']:.4f}"},
        {"label": "量化词密度", "value": f"{features['quantitative_words_ratio']:.4f}"},
    ]
