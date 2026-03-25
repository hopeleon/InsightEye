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


def _ratio(count: int, total: int) -> float:
    return round(count / total, 4) if total > 0 else 0.0


def _apply_feature_rules(dim: str, features: dict) -> tuple[float, list[str], list[str]]:
    positive: list[str] = []
    negative: list[str] = []
<<<<<<< Updated upstream
    score = 20.0

    if dim == "O":
        if features.get("abstraction_level") == "abstract":
            score += 18
            positive.append("表达偏抽象概念层，关注「为什么」多过「怎么做」，开放性信号强。")
        if features.get("hedge_words_ratio", 0) >= 0.008:
            score += 12
            positive.append("使用较多可能性表达（可能/也许），思维倾向开放探索。")
        if features.get("qualifier_ratio", 0) >= 0.010:
            score += 10
            positive.append("限定条件和假设性表达较多，体现多元思考倾向。")
        if features.get("process_words_ratio", 0) >= 0.010:
            score += 8
            positive.append("提及多种方法论，有探索不同路径的迹象。")
        if features.get("abstraction_level") == "grounded" and features.get("detail_words_ratio", 0) >= 0.012:
            score -= 10
            negative.append("表达更偏具体执行而非抽象思考，务实取向明显。")

    if dim == "C":
        if features.get("process_words_ratio", 0) >= 0.012:
            score += 18
            positive.append("过程和规范词汇丰富，体现较强的计划性和结构意识。")
        if features.get("detail_words_ratio", 0) >= 0.012:
            score += 15
            positive.append("细节关注度高，说明对质量和准确性的重视。")
        if features.get("star_structure_score", 0) >= 0.70:
            score += 12
            positive.append("STAR结构较完整，说明叙事有头有尾，责任感信号强。")
        if features.get("logical_connector_ratio", 0) >= 0.012:
            score += 10
            positive.append("逻辑连接较清晰，表达结构化倾向明显。")
        if features.get("qualifier_ratio", 0) >= 0.010:
            score += 6
            positive.append("有限定条件和边界意识，说明对标准的遵循。")
        if features.get("hedge_words_ratio", 0) >= 0.015:
            score -= 8
            negative.append("保留性表达过多，削弱了尽责性常见的确定感和自律感。")

    if dim == "E":
        if features.get("emotional_words_ratio", 0) >= 0.008:
            score += 18
            positive.append("情绪词丰富，表达具有感染力，外向信号明显。")
        if features.get("social_words_ratio", 0) >= 0.012:
            score += 15
            positive.append("人际相关词较多，对社交互动有较高关注。")
        if features.get("first_person_plural_ratio", 0) >= 0.010:
            score += 12
            positive.append("「我们/大家」等集体表达较多，社交导向明显。")
        if features.get("story_richness_score", 0) >= 0.65:
            score += 8
            positive.append("叙事丰富饱满，回答有感染力，符合外向者的表达特点。")
        if features.get("avg_sentence_length", 0) >= 18:
            score += 6
            positive.append("平均句长偏长，表达充分，符合外向者的表达习惯。")
        if features.get("social_words_ratio", 0) < 0.008 and features.get("process_words_ratio", 0) >= 0.012:
            score -= 12
            negative.append("表达以执行细节为主，人际互动词偏少，更偏向内向务实风格。")

    if dim == "A":
        if features.get("first_person_plural_ratio", 0) >= 0.012:
            score += 18
            positive.append("「我们/大家」等集体代词频率高，合作意识明显。")
        if features.get("social_words_ratio", 0) >= 0.012:
            score += 15
            positive.append("人际词汇丰富，关注他人需求和团队和谐。")
        if features.get("hedge_words_ratio", 0) >= 0.006:
            score += 10
            positive.append("缓和表达适中，语气温和有分寸，符合宜人特征。")
        if features.get("contrast_connector_ratio", 0) >= 0.010:
            score -= 12
            negative.append("对比转折词较多，可能表明对抗性或竞争性倾向。")
        if features.get("imperative_like_ratio", 0) >= 0.015:
            score -= 10
            negative.append("指令性表达偏多（必须/先/直接），直接强势倾向与高宜人性相悖。")

    if dim == "N":
        if features.get("emotional_words_ratio", 0) >= 0.010:
            score += 20
            positive.append("负面情绪词汇出现频率较高，焦虑和压力信号明显。")
        if features.get("risk_words_ratio", 0) >= 0.012:
            score += 15
            positive.append("风险和问题词汇多，对不确定性的关注度高。")
        if features.get("hedge_words_ratio", 0) >= 0.012:
            score += 10
            positive.append("保留表达多（「可能」「也许」），对确定性的信心不足。")
        if features.get("certainty_words_ratio", 0) >= 0.008:
            score -= 12
            positive.append("确定性词汇较多，情绪表达相对平稳。")
        if features.get("hedge_words_ratio", 0) < 0.004:
            score -= 8
=======
    score = 40.0   # 基础分提高，让短文本也能有基础分

    if dim == "O":
        if features.get("abstraction_level") == "abstract":
            score += 15
            positive.append("表达偏抽象概念层，关注「为什么」多过「怎么做」，开放性信号强。")
        if features.get("hedge_words_ratio", 0) >= 0.005:
            score += 10
            positive.append("使用较多可能性表达（可能/也许），思维倾向开放探索。")
        if features.get("qualifier_ratio", 0) >= 0.006:
            score += 8
            positive.append("限定条件和假设性表达较多，体现多元思考倾向。")
        if features.get("process_words_ratio", 0) >= 0.006:
            score += 6
            positive.append("提及多种方法论，有探索不同路径的迹象。")
        if features.get("abstraction_level") == "grounded" and features.get("detail_words_ratio", 0) >= 0.010:
            score -= 8
            negative.append("表达更偏具体执行而非抽象思考，务实取向明显。")

    if dim == "C":
        if features.get("process_words_ratio", 0) >= 0.008:
            score += 15
            positive.append("过程和规范词汇丰富，体现较强的计划性和结构意识。")
        if features.get("detail_words_ratio", 0) >= 0.008:
            score += 12
            positive.append("细节关注度高，说明对质量和准确性的重视。")
        if features.get("star_structure_score", 0) >= 0.60:
            score += 10
            positive.append("STAR结构较完整，说明叙事有头有尾，责任感信号强。")
        if features.get("logical_connector_ratio", 0) >= 0.008:
            score += 8
            positive.append("逻辑连接较清晰，表达结构化倾向明显。")
        if features.get("qualifier_ratio", 0) >= 0.006:
            score += 5
            positive.append("有限定条件和边界意识，说明对标准的遵循。")
        if features.get("hedge_words_ratio", 0) >= 0.010:
            score -= 6
            negative.append("保留性表达过多，削弱了尽责性常见的确定感和自律感。")

    if dim == "E":
        if features.get("emotional_words_ratio", 0) >= 0.005:
            score += 15
            positive.append("情绪词丰富，表达具有感染力，外向信号明显。")
        if features.get("social_words_ratio", 0) >= 0.006:
            score += 12
            positive.append("人际相关词较多，对社交互动有较高关注。")
        if features.get("first_person_plural_ratio", 0) >= 0.006:
            score += 10
            positive.append("「我们/大家」等集体表达较多，社交导向明显。")
        if features.get("story_richness_score", 0) >= 0.55:
            score += 7
            positive.append("叙事丰富饱满，回答有感染力，符合外向者的表达特点。")
        if features.get("avg_sentence_length", 0) >= 15:
            score += 5
            positive.append("平均句长偏长，表达充分，符合外向者的表达习惯。")
        if features.get("social_words_ratio", 0) < 0.005 and features.get("process_words_ratio", 0) >= 0.008:
            score -= 10
            negative.append("表达以执行细节为主，人际互动词偏少，更偏向内向务实风格。")

    if dim == "A":
        if features.get("first_person_plural_ratio", 0) >= 0.008:
            score += 15
            positive.append("「我们/大家」等集体代词频率高，合作意识明显。")
        if features.get("social_words_ratio", 0) >= 0.006:
            score += 12
            positive.append("人际词汇丰富，关注他人需求和团队和谐。")
        if features.get("hedge_words_ratio", 0) >= 0.004:
            score += 8
            positive.append("缓和表达适中，语气温和有分寸，符合宜人特征。")
        if features.get("contrast_connector_ratio", 0) >= 0.006:
            score -= 10
            negative.append("对比转折词较多，可能表明对抗性或竞争性倾向。")
        if features.get("imperative_like_ratio", 0) >= 0.010:
            score -= 8
            negative.append("指令性表达偏多（必须/先/直接），直接强势倾向与高宜人性相悖。")

    if dim == "N":
        if features.get("emotional_words_ratio", 0) >= 0.007:
            score += 18
            positive.append("负面情绪词汇出现频率较高，焦虑和压力信号明显。")
        if features.get("risk_words_ratio", 0) >= 0.006:
            score += 12
            positive.append("风险和问题词汇多，对不确定性的关注度高。")
        if features.get("hedge_words_ratio", 0) >= 0.008:
            score += 8
            positive.append("保留表达多（「可能」「也许」），对确定性的信心不足。")
        if features.get("certainty_words_ratio", 0) >= 0.006:
            score -= 10
            positive.append("确定性词汇较多，情绪表达相对平稳。")
        if features.get("hedge_words_ratio", 0) < 0.003:
            score -= 6
>>>>>>> Stashed changes
            positive.append("保留性表达极少，表达直接确定，情绪稳定性信号较强。")

    return max(0.0, min(100.0, score)), positive, negative


def _score_band(score: float) -> str:
    if score <= 24:
        return "弱信号"
    if score <= 49:
        return "轻度倾向"
    if score <= 74:
        return "中度倾向"
    return "强倾向"


def _confidence_level(word_count: int, turn_count: int, scores: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    level = "medium"
<<<<<<< Updated upstream
    if word_count < 120 or turn_count <= 1:
        level = "low"
        notes.append("样本量偏少，结论仅作为初步倾向参考。")
    if word_count >= 300 and turn_count >= 3:
        level = "high"
        notes.append("样本充分，多个回答维度有较一致的信号。")
    extreme_count = sum(1 for s in scores.values() if s > 88 or s < 18)
    if extreme_count >= 2:
        level = "low"
        notes.append("多个维度出现极端分数，可能存在面试呈现偏差，置信度降权。")
=======
    if word_count < 60 or turn_count <= 1:
        level = "low"
        notes.append("样本量偏少，结论仅作为初步倾向参考。")
    elif word_count >= 300 and turn_count >= 3:
        level = "high"
        notes.append("样本充分，多个回答维度有较一致的信号。")
    extreme_count = sum(1 for s in scores.values() if s > 90 or s < 12)
    if extreme_count >= 3:
        level = "low"
        notes.append("多个维度出现极端分数，可能存在面试呈现偏差，置信度降权。")
    elif extreme_count == 2 and level == "low":
        notes.append("部分极端维度存在，需扩大样本验证。")
>>>>>>> Stashed changes
    return level, notes


def _n_artifacts_detection(features: dict, scores: dict, turn_count: int) -> tuple[bool, str]:
    n_score = scores.get("N", 0)
    e_score = scores.get("E", 0)
    if n_score >= 65 and e_score >= 70:
        return True, "N高且E也高，N信号可能是面试焦虑激活而非基线特质，建议在非压力话题中验证。"

    if n_score >= 60 and turn_count >= 2:
        return False, "N信号在多个问题中出现，有一定稳定性，但面试场景仍是干扰因素。"
    if n_score >= 60:
        return True, "N信号仅在单一问题中出现，情境激活可能性较大，需扩大样本验证。"
    return False, "N信号不明显，或处于合理范围内，面试压力干扰较小。"


def analyze_bigfive(transcript: str, turns: list[dict], features: dict, knowledge: dict) -> dict:
    word_count = max(len(transcript.replace("\n", "")), 1)

    scores: dict[str, int] = {}
    all_positive: dict[str, list[str]] = defaultdict(list)
    all_negative: dict[str, list[str]] = defaultdict(list)

    for dim in DIMENSIONS:
        base_score, positive, negative = _apply_feature_rules(dim, features)
        kw_score = min(22, _keyword_hits(transcript, _TYPE_KEYWORDS[dim]) * 3)
        neg_kw = min(10, _keyword_hits(transcript, _NEGATIVE_KEYWORDS[dim]) * 4)
        final_score = int(max(0, min(100, round(base_score + kw_score - neg_kw))))
        scores[dim] = final_score
        if kw_score > 0:
            positive.append(f"出现了与 {dim} 维度相关的语言特征。")
        if not positive:
            positive.append("该维度的正向证据有限。")
        all_positive[dim] = positive
        all_negative[dim] = negative

    confidence, conf_notes = _confidence_level(word_count, len(turns), scores)
    n_artifact, n_notes = _n_artifacts_detection(features, scores, len(turns))

    sorted_dims = sorted(scores, key=scores.get, reverse=True)
    dominant = sorted_dims[0]
    secondary = [d for d in sorted_dims[1:3] if scores[d] >= scores[dominant] * 0.7]

    trait_interpretations = {}
    for dim in DIMENSIONS:
        score = scores[dim]
        interp_key = "high" if score >= 75 else "medium" if score >= 50 else "low"
        interp_raw = knowledge["dimensions"].get(dim, {}).get("score_interpretation", {}).get(interp_key, "")
        trait_interpretations[dim] = interp_raw

    cross_patterns = _detect_cross_patterns(scores, features)

    supplemental_probes = []
    top_dims = sorted_dims[:2]
    for dim in top_dims:
        probes = knowledge["dimensions"].get(dim, {}).get("probe_questions", {})
        confirm_qs = probes.get("confirm", [])
        if confirm_qs:
            supplemental_probes.append({
                "target_dimension": dim,
                "question": confirm_qs[0],
                "purpose": f"进一步验证 {dim} 维度的初步判断。"
            })

    return {
        "meta": {
            "sample_words": word_count,
            "turn_count": len(turns),
            "confidence": confidence,
            "confidence_notes": conf_notes,
            "n_artifact_flag": n_artifact,
            "n_artifact_notes": n_notes,
        },
        "scores": scores,
        "ranking": sorted_dims,
        "dominant_trait": dominant,
        "secondary_traits": secondary,
        "trait_interpretations": trait_interpretations,
        "cross_dimension_patterns": cross_patterns,
        "evidence_summary": {
            dim: {
                "score": scores[dim],
                "band": _score_band(scores[dim]),
                "evidence_for": all_positive[dim][:4],
                "evidence_against": all_negative[dim][:3],
            }
            for dim in DIMENSIONS
        },
        "supplemental_probes": supplemental_probes,
    }


def _detect_cross_patterns(scores: dict, features: dict) -> list[dict]:
    patterns = []
    O, C, E, A, N = scores.get("O", 0), scores.get("C", 0), scores.get("E", 0), scores.get("A", 0), scores.get("N", 0)

    if O >= 65 and C >= 65:
        patterns.append({
            "pattern_name": "有原则的创新者",
            "interpretation": "兼具好奇心和自律性，既能发散思维又能严谨落地。",
            "workplace_implications": "适合需要创造性与规范性并重的工作，但需注意不要过度分析导致行动偏慢。"
        })
    if E >= 65 and A >= 65:
        patterns.append({
            "pattern_name": "温暖的支持者",
            "interpretation": "人际连接能力强，团队氛围带动者，合作导向明显。",
            "workplace_implications": "适合需要大量人际协作的岗位，但需注意在关键冲突场景中可能回避问题。"
        })
    if C >= 65 and N >= 60:
        patterns.append({
            "pattern_name": "高焦虑型自律者",
            "interpretation": "自律性强但情绪波动也较高，可能是通过高标准来管理焦虑。",
            "workplace_implications": "工作质量有保障，但在高压环境下可能出现稳定性下降，需关注心理健康。"
        })
    if C >= 65 and N <= 40:
        patterns.append({
            "pattern_name": "高效自律型",
            "interpretation": "情绪稳定且高度自律，目标导向明确，在压力下反而表现更好。",
            "workplace_implications": "适合高压高标准的岗位，可能是优秀的项目负责人，但需注意对他人可能要求过高。"
        })
    if O >= 65 and C <= 45:
        patterns.append({
            "pattern_name": "自由探索者",
            "interpretation": "想法多但落地能力不确定，享受探索过程超过追求结果。",
            "workplace_implications": "适合早期创新项目，但需要强执行者配合以确保项目收尾。"
        })
    if E >= 65 and A <= 45:
        patterns.append({
            "pattern_name": "主导型影响者",
            "interpretation": "社交活跃且强势，领导力明显，决策快速直接。",
            "workplace_implications": "适合需要快速决策和强势推动的岗位，但需注意可能忽视他人意见。"
        })
    if N >= 70 and E <= 45:
        patterns.append({
            "pattern_name": "内省焦虑型",
            "interpretation": "内向且情绪波动较大，对压力敏感，但倾向于内化处理而非外放表达。",
            "workplace_implications": "适合独立工作的深度岗位，高压人际场景可能不是最佳环境。"
        })
    if A >= 65 and N <= 40:
        patterns.append({
            "pattern_name": "稳定磐石型",
            "interpretation": "情绪稳定且合作性强，是团队的稳定力量，人际风险低。",
            "workplace_implications": "适合需要长期维护和稳定输出的协作型岗位，但可能缺乏推动变革的动力。"
        })

    return patterns
