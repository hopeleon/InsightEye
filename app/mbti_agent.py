from __future__ import annotations

import logging
from collections import defaultdict


DIMENSIONS = ["E_I", "N_S", "T_F", "J_P"]
LETTERS = ["E", "I", "N", "S", "T", "F", "J", "P"]

logger = logging.getLogger("insighteye.mbti_agent")


def _keyword_hits(text: str, words: list[str]) -> int:
    """统计关键词出现次数"""
    return sum(text.count(word) for word in words)


def _score_dimension_side(side: str, features: dict, knowledge: dict, dimension: str) -> tuple[float, list[str]]:
    """
    为某个维度的某一侧打分（优化证据描述版）
    """
    dim_config = knowledge["dimensions"][dimension][side]
    rules = dim_config.get("feature_rules", {})
    evidence = []
    score = 0.0
    
    # ========== 证据翻译映射表 ==========
    EVIDENCE_TRANSLATION = {
        # E/I 维度
        "social_words_ratio >= 0.015": "高频使用「团队」「沟通」等社交词汇",
        "first_person_plural_ratio >= 0.012": "更多使用「我们」而非「我」",
        "self_vs_team_orientation == 'team'": "叙述重心偏向团队协作",
        "first_person_singular_ratio >= 0.018": "更多使用「我」进行独立叙述",
        "social_words_ratio < 0.008": "较少提及人际互动",
        "self_vs_team_orientation == 'self'": "叙述重心偏向个人行动",
        "avg_sentence_length >= 25": "句式偏长，表达更深思熟虑",
        "topic_stability_score >= 0.70": "回答主题稳定，逻辑连贯",
        "first_person_plural_ratio > 0.015": "频繁强调集体视角",
        "emotional_words_ratio > 0.012": "情绪化表达较多",
        
        # N/S 维度
        "abstraction_level == 'abstract'": "多用抽象概念和宏观视角",
        "abstract_words_ratio >= 0.008": "频繁使用「战略」「方向」等抽象词",
        "hedge_words_ratio >= 0.008": "使用较多「可能」「也许」等不确定词",
        "qualifier_ratio >= 0.010": "倾向加入条件和前提限定",
        "detail_words_ratio > 0.020": "非常关注具体细节和数据",
        "star_structure_score > 0.85": "回答过于按部就班",
        "detail_words_ratio >= 0.015": "高频提及「数据」「步骤」等具体词",
        "abstraction_level == 'grounded'": "表达聚焦具体事实和操作",
        "star_structure_score >= 0.75": "回答结构完整（情境-任务-行动-结果）",
        "story_richness_score >= 0.70": "案例细节丰富，证据充分",
        "certainty_words_ratio >= 0.005": "使用较多「明确」「一定」等确定性词汇",
        "abstract_words_ratio > 0.012": "过度抽象化",
        "hedge_words_ratio > 0.015": "过度不确定",
        
        # T/F 维度
        "logical_connector_ratio >= 0.015": "高频使用「因为」「所以」等逻辑连接词",
        "problem_vs_people_focus == 'problem'": "更关注问题本身而非人际关系",
        "emotional_words_ratio < 0.006": "较少使用情绪化表达",
        "certainty_words_ratio >= 0.006": "表达较为肯定和果断",
        "detail_words_ratio >= 0.012": "注重分析细节和依据",
        "emotional_words_ratio > 0.012": "情感表达过多",
        "problem_vs_people_focus == 'people'": "决策时更多考虑人的因素",
        "emotional_words_ratio >= 0.010": "频繁使用「关心」「信任」等情感词",
        "social_words_ratio >= 0.012": "强调人际和谐",
        "first_person_plural_ratio >= 0.010": "强调集体认同",
        "hedge_words_ratio >= 0.008": "表达较为委婉",
        "logical_connector_ratio > 0.020": "过度逻辑化",
        
        # J/P 维度
        "star_structure_score >= 0.75": "回答有明确的计划和执行结构",
        "action_verbs_ratio >= 0.018": "高频使用「完成」「达成」等行动词",
        "certainty_words_ratio >= 0.005": "决策果断，表达确定",
        "topic_stability_score >= 0.70": "思路稳定，按计划推进",
        "qualifier_ratio < 0.008": "较少使用条件限定",
        "hedge_words_ratio > 0.012": "频繁使用不确定表达",
        "qualifier_ratio > 0.015": "过多条件限定",
        "hedge_words_ratio >= 0.010": "倾向保留灵活性",
        "qualifier_ratio >= 0.012": "会考虑多种可能性和条件",
        "action_verbs_ratio < 0.015": "不急于行动，更多观察",
        "question_ratio >= 0.08": "倾向提出问题和探索",
        "topic_stability_score < 0.65": "思路较为跳跃，适应性强",
        "certainty_words_ratio > 0.008": "过于武断",
        "star_structure_score > 0.80": "过度依赖计划",
    }

    # 强正向规则
    for rule in rules.get("strong_positive", []):
        if _check_rule(rule, features):
            score += 25
            readable = EVIDENCE_TRANSLATION.get(rule, rule)
            evidence.append(f"✓ {readable}")

    # 软正向规则
    for rule in rules.get("soft_positive", []):
        if _check_rule(rule, features):
            score += 12
            readable = EVIDENCE_TRANSLATION.get(rule, rule)
            evidence.append(f"• {readable}")

    # 负向规则（减分）
    for rule in rules.get("negative", []):
        if _check_rule(rule, features):
            score -= 15
            readable = EVIDENCE_TRANSLATION.get(rule, rule)
            evidence.append(f"✗ {readable}")

    return max(0.0, score), evidence


def _check_rule(rule: str, features: dict) -> bool:
    """
    检查特征是否满足规则（修复版，支持容错）
    """
    try:
        # 处理比较运算符
        if ">=" in rule:
            key, threshold = rule.split(">=")
            key = key.strip()
            threshold = float(threshold.strip())
            actual = features.get(key, 0)
            # 容错：允许 5% 的误差
            return actual >= threshold * 0.95
            
        elif "<=" in rule:
            key, threshold = rule.split("<=")
            key = key.strip()
            threshold = float(threshold.strip())
            actual = features.get(key, 0)
            return actual <= threshold * 1.05
            
        elif ">" in rule:
            key, threshold = rule.split(">")
            key = key.strip()
            threshold = float(threshold.strip())
            actual = features.get(key, 0)
            return actual > threshold * 0.95
            
        elif "<" in rule:
            key, threshold = rule.split("<")
            key = key.strip()
            threshold = float(threshold.strip())
            actual = features.get(key, 0)
            return actual < threshold * 1.05
            
        elif "==" in rule:
            key, value = rule.split("==")
            key = key.strip()
            value = value.strip().strip("'\"")
            return str(features.get(key, "")) == value
        else:
            return False
    except Exception:
        return False


def _get_dimension_keywords(knowledge: dict, dimension: str, side: str) -> list[str]:
    """提取某维度某侧的关键词"""
    try:
        return knowledge["dimensions"][dimension][side]["interview_markers"]["lexical"]["keywords"]
    except KeyError:
        return []


def _calculate_preference(score_a: float, score_b: float, side_a: str, side_b: str) -> dict:
    """
    计算偏好方向和强度（修复版）
    参数:
        score_a: 侧面A的得分
        score_b: 侧面B的得分
        side_a: 侧面A的字母（如 "E"）
        side_b: 侧面B的字母（如 "I"）
    """
    total = score_a + score_b
    if total < 5:  # 降低阈值
        return {
            "preference": "unclear",
            "strength": 50,
            "confidence": "low",
            "note": "证据不足",
            "score_a": round(score_a, 2),
            "score_b": round(score_b, 2),
        }

    percentage_a = (score_a / total) * 100
    
    # 确定偏好
    if percentage_a > 55:
        preference = side_a
        strength = int(percentage_a)
    elif percentage_a < 45:
        preference = side_b
        strength = int(100 - percentage_a)
    else:
        preference = "neutral"
        strength = 50

    # 确定置信度
    if strength >= 70:
        confidence = "clear"
    elif strength >= 60:
        confidence = "moderate"
    elif strength >= 55:
        confidence = "slight"
    else:
        confidence = "neutral"

    return {
        "preference": preference,
        "strength": strength,
        "confidence": confidence,
        "score_a": round(score_a, 2),
        "score_b": round(score_b, 2),
    }


def _detect_conflicts_with_disc(mbti_result: dict, disc_scores: dict, knowledge: dict) -> list[dict]:
    """
    检测 MBTI 与 DISC 的冲突
    """
    conflicts = []
    mapping = knowledge.get("cross_validation", {}).get("disc_mbti_mapping", {})
    
    # 找出 DISC 高分维度
    disc_high = [dim for dim, score in disc_scores.items() if score >= 70]
    
    # 提取 MBTI 类型
    mbti_type = mbti_result.get("type", "")
    
    for disc_dim in disc_high:
        key = f"{disc_dim}_high"
        if key in mapping:
            expected = mapping[key].get("likely", [])
            unexpected = mapping[key].get("unlikely", [])
            
            # 检查是否出现不应该出现的字母
            for letter in unexpected:
                if letter in mbti_type:
                    conflicts.append({
                        "type": f"{disc_dim}_vs_{letter}",
                        "description": f"DISC {disc_dim} 高分通常不对应 MBTI {letter}",
                        "severity": "medium",
                        "recommendation": f"需追问：{disc_dim} 维度的行为在日常中是否稳定？"
                    })
    
    # 检查预定义的冲突模式
    conflict_patterns = knowledge.get("cross_validation", {}).get("conflict_detection", [])
    for pattern_config in conflict_patterns:
        pattern = pattern_config["pattern"]
        
        # 解析模式（如 "high_D + P"）
        if "+" in pattern:
            parts = pattern.split("+")
            disc_part = parts[0].strip().replace("high_", "")
            mbti_part = parts[1].strip()
            
            if disc_scores.get(disc_part, 0) >= 70 and mbti_part in mbti_type:
                conflicts.append({
                    "type": pattern,
                    "description": pattern_config["description"],
                    "severity": "high",
                    "recommendation": pattern_config["recommendation"]
                })
    
    return conflicts


def analyze_mbti(transcript: str, turns: list[dict], features: dict, knowledge: dict, disc_scores: dict = None) -> dict:
    """
    MBTI 本地规则分析主函数（完全修复版）
    """
    word_count = len(transcript.replace("\n", ""))
    
    # 样本质量评估
    sample_quality = _assess_sample_quality(knowledge, word_count, len(turns))
    
    # 分析每个维度
    dimension_results = {}
    all_evidence = defaultdict(list)
    
    for dimension in DIMENSIONS:
        sides = dimension.split("_")
        side_a, side_b = sides[0], sides[1]
        
        # 计算两侧得分
        score_a, evidence_a = _score_dimension_side(side_a, features, knowledge, dimension)
        score_b, evidence_b = _score_dimension_side(side_b, features, knowledge, dimension)
        
        # 关键词加分（提高权重）
        keywords_a = _get_dimension_keywords(knowledge, dimension, side_a)
        keywords_b = _get_dimension_keywords(knowledge, dimension, side_b)
        
        keyword_score_a = min(30, _keyword_hits(transcript, keywords_a) * 5)
        keyword_score_b = min(30, _keyword_hits(transcript, keywords_b) * 5)
        
        score_a += keyword_score_a
        score_b += keyword_score_b
        
        if keyword_score_a > 0:
            evidence_a.append(f"出现了 {side_a} 相关高频词汇（+{keyword_score_a}分）")
        if keyword_score_b > 0:
            evidence_b.append(f"出现了 {side_b} 相关高频词汇（+{keyword_score_b}分）")
        
        # ========== 修复：正确调用 _calculate_preference ==========
        preference_result = _calculate_preference(score_a, score_b, side_a, side_b)
        
        all_evidence[side_a].extend(evidence_a)
        all_evidence[side_b].extend(evidence_b)
        
        dimension_results[dimension] = {
            "preference": preference_result["preference"],
            "strength": preference_result["strength"],
            "confidence": preference_result["confidence"],
            "scores": {
                side_a: preference_result["score_a"],
                side_b: preference_result["score_b"],
            },
            "evidence": {
                side_a: evidence_a[:3],
                side_b: evidence_b[:3],
            }
        }
    
    # 组装 MBTI 类型
    mbti_type = ""
    confidence_levels = []
    for dimension in DIMENSIONS:
        pref = dimension_results[dimension]["preference"]
        if pref == "neutral" or pref == "unclear":
            mbti_type += "X"
        else:
            mbti_type += pref
        confidence_levels.append(dimension_results[dimension]["confidence"])
    
    # 整体置信度
    overall_confidence = _calculate_overall_confidence(confidence_levels, sample_quality)
    
    # 生成描述
    type_description = _generate_type_description(mbti_type, dimension_results)
    
    # 交叉验证
    conflicts = []
    if disc_scores:
        conflicts = _detect_conflicts_with_disc(
            {"type": mbti_type},
            disc_scores,
            knowledge
        )
    
    # 生成追问建议
    follow_up_questions = _generate_follow_up_questions(dimension_results, mbti_type, knowledge)
    
    return {
        "meta": {
            "sample_quality": sample_quality,
            "confidence": overall_confidence,
            "word_count": word_count,
            "turn_count": len(turns),
        },
        "type": mbti_type,
        "type_description": type_description,
        "dimensions": dimension_results,
        "conflicts": conflicts,
        "follow_up_questions": follow_up_questions,
        "evidence_summary": {
            letter: all_evidence[letter][:2] for letter in LETTERS if all_evidence[letter]
        }
    }


def _assess_sample_quality(knowledge: dict, word_count: int, turn_count: int) -> str:
    """评估样本质量"""
    minimum = knowledge["global_rules"]["minimum_sample_words"]
    preferred = knowledge["global_rules"]["preferred_sample_words"]
    
    if word_count < minimum or turn_count <= 1:
        return "low"
    if word_count < preferred or turn_count <= 2:
        return "medium"
    return "high"


def _calculate_overall_confidence(confidence_levels: list[str], sample_quality: str) -> str:
    """计算整体置信度"""
    if sample_quality == "low":
        return "low"
    
    # 统计各置信度等级
    clear_count = confidence_levels.count("clear")
    neutral_count = confidence_levels.count("neutral")
    
    if clear_count >= 3 and sample_quality == "high":
        return "high"
    if neutral_count >= 2:
        return "low"
    return "medium"


def _generate_type_description(mbti_type: str, dimension_results: dict) -> str:
    """生成类型描述"""
    if "X" in mbti_type:
        return f"当前样本显示为 {mbti_type}（其中 X 表示该维度证据不足），建议增加样本后重新评估。"
    
    desc_parts = []
    
    # E/I
    ei_pref = dimension_results["E_I"]["preference"]
    if ei_pref == "E":
        desc_parts.append("偏外向型，能量来源于外部互动")
    elif ei_pref == "I":
        desc_parts.append("偏内向型，能量来源于内部思考")
    
    # N/S
    ns_pref = dimension_results["N_S"]["preference"]
    if ns_pref == "N":
        desc_parts.append("偏直觉型，关注可能性和抽象模式")
    elif ns_pref == "S":
        desc_parts.append("偏感觉型，关注具体事实和细节")
    
    # T/F
    tf_pref = dimension_results["T_F"]["preference"]
    if tf_pref == "T":
        desc_parts.append("偏思考型，决策基于逻辑分析")
    elif tf_pref == "F":
        desc_parts.append("偏情感型，决策考虑人际价值")
    
    # J/P
    jp_pref = dimension_results["J_P"]["preference"]
    if jp_pref == "J":
        desc_parts.append("偏判断型，喜欢结构和计划")
    elif jp_pref == "P":
        desc_parts.append("偏知觉型，喜欢灵活和开放")
    
    return f"类型 {mbti_type}：" + "；".join(desc_parts) + "。"


def _generate_follow_up_questions(dimension_results: dict, mbti_type: str, knowledge: dict) -> list[dict]:
    """生成追问建议（人话版）"""
    questions = []
    
    # ========== 维度描述映射 ==========
    DIMENSION_LABELS = {
        "E_I": {
            "name": "能量来源",
            "E": "外向型（从外部互动获取能量）",
            "I": "内向型（从独处思考获取能量）"
        },
        "N_S": {
            "name": "信息处理方式",
            "N": "直觉型（关注可能性和抽象模式）",
            "S": "感觉型（关注具体事实和细节）"
        },
        "T_F": {
            "name": "决策方式",
            "T": "思考型（基于逻辑和客观标准）",
            "F": "情感型（考虑人际和价值观）"
        },
        "J_P": {
            "name": "生活方式",
            "J": "判断型（喜欢计划和确定性）",
            "P": "知觉型（喜欢灵活和开放性）"
        }
    }
    
    # ========== 追问模板库 ==========
    QUESTION_TEMPLATES = {
        "E_I": {
            "neutral": "在一个需要独立深思和团队协作并存的项目中，你更倾向于先做哪个？为什么？",
            "E": "你在独处时如何保持工作效率？有什么具体方法？",
            "I": "当需要在短时间内影响或说服一群不熟悉的人时，你通常怎么做？"
        },
        "N_S": {
            "neutral": "描述一次你需要在「快速试错」和「充分验证」之间做选择的经历，你是怎么权衡的？",
            "N": "当需要落地执行一个抽象想法时，你如何确保细节不出错？",
            "S": "面对一个完全陌生的领域，你如何快速建立框架性认知？"
        },
        "T_F": {
            "neutral": "讲一个你的决策会明显影响他人感受的案例，你是如何平衡逻辑和人际的？",
            "T": "当团队成员情绪化反对你的方案时，你通常如何处理？",
            "F": "如果你的人际判断与数据结论冲突，你会怎么做？"
        },
        "J_P": {
            "neutral": "在一个高度不确定的环境中，你如何平衡「按计划推进」和「灵活调整」？",
            "J": "当外部环境突变，原计划失效时，你的典型反应是什么？",
            "P": "如果必须在有限时间内完成一个有明确 deadline 的任务，你如何确保按时交付？"
        }
    }
    
    # 1. 对中性或低置信度的维度追问
    for dimension, result in dimension_results.items():
        if result["confidence"] in ["neutral", "slight"]:
            dim_info = DIMENSION_LABELS.get(dimension, {})
            dim_name = dim_info.get("name", dimension)
            question_text = QUESTION_TEMPLATES.get(dimension, {}).get("neutral", "")
            
            if question_text:
                questions.append({
                    "dimension": f"{dim_name}",
                    "question": question_text,
                    "purpose": f"当前在该维度证据不足，需要进一步确认真实偏好",
                    "priority": "high"
                })

    # 2. 对高置信度维度验证（测反向能力）
    for dimension, result in dimension_results.items():
        if result["confidence"] == "clear":
            pref = result["preference"]
            if pref in ["neutral", "unclear"]:
                continue

            dim_info = DIMENSION_LABELS.get(dimension, {})
            dim_name = dim_info.get("name", dimension)
            pref_label = dim_info.get(pref, pref)
            question_text = QUESTION_TEMPLATES.get(dimension, {}).get(pref, "")

            if question_text:
                questions.append({
                    "dimension": f"{dim_name}",
                    "question": question_text,
                    "purpose": f"验证 {pref_label} 的边界和反向适应能力",
                    "priority": "medium"
                })

    # 按优先级排序，high 优先
    questions.sort(key=lambda x: 0 if x.get("priority") == "high" else 1)

    return questions[:4]  # 最多返回4个


def mbti_feature_highlights(mbti_result: dict) -> list[dict]:
    """生成 MBTI 关键指标摘要（用于前端展示）"""
    highlights = []
    
    for dimension, result in mbti_result["dimensions"].items():
        pref = result["preference"]
        strength = result["strength"]
        confidence = result["confidence"]
        
        highlights.append({
            "label": dimension.replace("_", "/"),
            "value": f"{pref} ({strength}%)",
            "confidence": confidence
        })
    
    return highlights