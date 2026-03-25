"""
MBTI 认知风格分析阶段
基于原子特征和 DISC 结果进行 MBTI 四维度推断
"""

from __future__ import annotations

from workflow.context import WorkflowContext


def run_mbti_stage(context: WorkflowContext) -> WorkflowContext:
    """
    执行 MBTI 本地规则分析
    
    依赖:
        - context.features: 原子特征
        - context.transcript: 面试文本
        - context.disc_evidence: DISC 分值（用于交叉验证）
        - context.mbti_knowledge: MBTI 知识库
    """
    context.mark_stage("mbti_stage", "started", "Analyze MBTI cognitive preferences")
    
    # 分析四维度
    dimensions = _analyze_all_dimensions(context)
    
    # 推断 MBTI 类型
    mbti_type = _infer_type(dimensions)
    
    # 交叉验证 DISC-MBTI 冲突
    conflicts = _detect_conflicts(dimensions, context.disc_evidence, context.mbti_knowledge)
    
    # 生成追问建议
    followup_questions = _generate_followups(dimensions, context.mbti_knowledge)
    
    # 计算置信度
    confidence = _calculate_confidence(dimensions, conflicts)
    
    # 保存结果
    context.mbti_analysis = {
        "type": mbti_type,
        "type_description": context.mbti_knowledge.get("output_mapping", {}).get("type_format", ""),
        "dimensions": dimensions,
        "conflicts": conflicts,
        "follow_up_questions": followup_questions,
        "meta": {
            "confidence": confidence,
            "source": "local_rules",
            "cross_validated_with_disc": bool(context.disc_evidence.get("scores")),
        },
    }
    
    context.mark_stage("mbti_stage", "completed", f"MBTI type inferred: {mbti_type}")
    return context


def _analyze_all_dimensions(context: WorkflowContext) -> dict:
    """分析 MBTI 四维度"""
    features = context.features
    transcript = context.transcript
    knowledge = context.mbti_knowledge
    
    dimensions = {}
    
    # E/I: 能量来源
    dimensions["E_I"] = _analyze_e_i(features, transcript, knowledge)
    
    # N/S: 信息获取
    dimensions["N_S"] = _analyze_n_s(features, transcript, knowledge)
    
    # T/F: 决策方式
    dimensions["T_F"] = _analyze_t_f(features, transcript, knowledge)
    
    # J/P: 生活方式
    dimensions["J_P"] = _analyze_j_p(features, transcript, knowledge)
    
    return dimensions


def _analyze_e_i(features: dict, transcript: str, knowledge: dict) -> dict:
    """分析外向(E) vs 内向(I)"""
    dim_config = knowledge.get("dimensions", {}).get("E_I", {})
    
    e_score = 0
    i_score = 0
    e_evidence = []
    i_evidence = []
    
    # ========== E 型信号检测 ==========
    e_keywords = dim_config.get("E", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in e_keywords:
        count = transcript.count(keyword)
        if count > 0:
            e_score += count
            if len(e_evidence) < 3:
                e_evidence.append(f"使用外向词汇 '{keyword}'（{count}次）")
    
    # 检查特征规则
    social_ratio = features.get("social_words_ratio", 0)
    plural_ratio = features.get("first_person_plural_ratio", 0)
    team_orientation = features.get("self_vs_team_orientation", "")
    
    if social_ratio >= 0.015:
        e_score += 3
        e_evidence.append(f"社交词汇比例高（{social_ratio:.3f}）")
    
    if plural_ratio >= 0.012:
        e_score += 3
        e_evidence.append(f"'我们'使用频繁（{plural_ratio:.3f}）")
    
    if team_orientation == "team":
        e_score += 2
        e_evidence.append("团队导向明显")
    
    # ========== I 型信号检测 ==========
    i_keywords = dim_config.get("I", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in i_keywords:
        count = transcript.count(keyword)
        if count > 0:
            i_score += count
            if len(i_evidence) < 3:
                i_evidence.append(f"使用内向词汇 '{keyword}'（{count}次）")
    
    singular_ratio = features.get("first_person_singular_ratio", 0)
    
    if singular_ratio >= 0.018:
        i_score += 3
        i_evidence.append(f"'我'使用频繁（{singular_ratio:.3f}）")
    
    if social_ratio < 0.008:
        i_score += 2
        i_evidence.append(f"社交词汇稀少（{social_ratio:.3f}）")
    
    if team_orientation == "self":
        i_score += 2
        i_evidence.append("个人导向明显")
    
    # ========== 计算偏好 ==========
    total = e_score + i_score or 1
    e_percentage = int((e_score / total) * 100)
    i_percentage = int((i_score / total) * 100)
    
    if e_percentage > 55:
        preference = "E"
        strength = e_percentage
        confidence = "high" if e_percentage > 65 else "medium"
    elif i_percentage > 55:
        preference = "I"
        strength = i_percentage
        confidence = "high" if i_percentage > 65 else "medium"
    else:
        preference = "neutral"
        strength = 50
        confidence = "low"
    
    return {
        "preference": preference,
        "strength": strength,
        "confidence": confidence,
        "summary": f"倾向于{'外向表达' if preference == 'E' else '内向思考' if preference == 'I' else '中性（E/I 均衡）'}",
        "evidence": {
            "E": e_evidence[:3],
            "I": i_evidence[:3],
        },
        "scores": {
            "E": e_percentage,
            "I": i_percentage,
        },
    }


def _analyze_n_s(features: dict, transcript: str, knowledge: dict) -> dict:
    """分析直觉(N) vs 感觉(S)"""
    dim_config = knowledge.get("dimensions", {}).get("N_S", {})
    
    n_score = 0
    s_score = 0
    n_evidence = []
    s_evidence = []
    
    # ========== N 型信号检测 ==========
    n_keywords = dim_config.get("N", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in n_keywords:
        count = transcript.count(keyword)
        if count > 0:
            n_score += count
            if len(n_evidence) < 3:
                n_evidence.append(f"使用直觉词汇 '{keyword}'（{count}次）")
    
    abstraction = features.get("abstraction_level", "")
    abstract_ratio = features.get("abstract_words_ratio", 0)
    hedge_ratio = features.get("hedge_words_ratio", 0)
    
    if abstraction == "abstract":
        n_score += 3
        n_evidence.append("抽象思维倾向明显")
    
    if abstract_ratio >= 0.008:
        n_score += 2
        n_evidence.append(f"抽象词汇比例高（{abstract_ratio:.3f}）")
    
    if hedge_ratio >= 0.008:
        n_score += 2
        n_evidence.append(f"模糊限定词较多（{hedge_ratio:.3f}）")
    
    # ========== S 型信号检测 ==========
    s_keywords = dim_config.get("S", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in s_keywords:
        count = transcript.count(keyword)
        if count > 0:
            s_score += count
            if len(s_evidence) < 3:
                s_evidence.append(f"使用感觉词汇 '{keyword}'（{count}次）")
    
    detail_ratio = features.get("detail_words_ratio", 0)
    star_score = features.get("star_structure_score", 0)
    richness = features.get("story_richness_score", 0)
    
    if detail_ratio >= 0.015:
        s_score += 3
        s_evidence.append(f"细节词汇比例高（{detail_ratio:.3f}）")
    
    if abstraction == "grounded":
        s_score += 3
        s_evidence.append("具体化思维倾向明显")
    
    if star_score >= 0.75:
        s_score += 2
        s_evidence.append(f"STAR 结构完整（{star_score:.2f}）")
    
    if richness >= 0.70:
        s_score += 2
        s_evidence.append(f"细节丰富度高（{richness:.2f}）")
    
    # ========== 计算偏好 ==========
    total = n_score + s_score or 1
    n_percentage = int((n_score / total) * 100)
    s_percentage = int((s_score / total) * 100)
    
    if n_percentage > 55:
        preference = "N"
        strength = n_percentage
        confidence = "high" if n_percentage > 65 else "medium"
    elif s_percentage > 55:
        preference = "S"
        strength = s_percentage
        confidence = "high" if s_percentage > 65 else "medium"
    else:
        preference = "neutral"
        strength = 50
        confidence = "low"
    
    return {
        "preference": preference,
        "strength": strength,
        "confidence": confidence,
        "summary": f"倾向于{'直觉思维（关注可能性）' if preference == 'N' else '感觉思维（关注具体事实）' if preference == 'S' else '中性（N/S 均衡）'}",
        "evidence": {
            "N": n_evidence[:3],
            "S": s_evidence[:3],
        },
        "scores": {
            "N": n_percentage,
            "S": s_percentage,
        },
    }


def _analyze_t_f(features: dict, transcript: str, knowledge: dict) -> dict:
    """分析思考(T) vs 情感(F)"""
    dim_config = knowledge.get("dimensions", {}).get("T_F", {})
    
    t_score = 0
    f_score = 0
    t_evidence = []
    f_evidence = []
    
    # ========== T 型信号检测 ==========
    t_keywords = dim_config.get("T", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in t_keywords:
        count = transcript.count(keyword)
        if count > 0:
            t_score += count
            if len(t_evidence) < 3:
                t_evidence.append(f"使用理性词汇 '{keyword}'（{count}次）")
    
    logical_ratio = features.get("logical_connector_ratio", 0)
    problem_focus = features.get("problem_vs_people_focus", "")
    emotional_ratio = features.get("emotional_words_ratio", 0)
    
    if logical_ratio >= 0.015:
        t_score += 3
        t_evidence.append(f"逻辑连接词比例高（{logical_ratio:.3f}）")
    
    if problem_focus == "problem":
        t_score += 3
        t_evidence.append("问题导向明显")
    
    if emotional_ratio < 0.006:
        t_score += 2
        t_evidence.append(f"情感词汇稀少（{emotional_ratio:.3f}）")
    
    # ========== F 型信号检测 ==========
    f_keywords = dim_config.get("F", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in f_keywords:
        count = transcript.count(keyword)
        if count > 0:
            f_score += count
            if len(f_evidence) < 3:
                f_evidence.append(f"使用情感词汇 '{keyword}'（{count}次）")
    
    social_ratio = features.get("social_words_ratio", 0)
    
    if emotional_ratio >= 0.010:
        f_score += 3
        f_evidence.append(f"情感词汇比例高（{emotional_ratio:.3f}）")
    
    if problem_focus == "people":
        f_score += 3
        f_evidence.append("人际导向明显")
    
    if social_ratio >= 0.012:
        f_score += 2
        f_evidence.append(f"社交词汇比例高（{social_ratio:.3f}）")
    
    # ========== 计算偏好 ==========
    total = t_score + f_score or 1
    t_percentage = int((t_score / total) * 100)
    f_percentage = int((f_score / total) * 100)
    
    if t_percentage > 55:
        preference = "T"
        strength = t_percentage
        confidence = "high" if t_percentage > 65 else "medium"
    elif f_percentage > 55:
        preference = "F"
        strength = f_percentage
        confidence = "high" if f_percentage > 65 else "medium"
    else:
        preference = "neutral"
        strength = 50
        confidence = "low"
    
    return {
        "preference": preference,
        "strength": strength,
        "confidence": confidence,
        "summary": f"倾向于{'理性决策（基于逻辑）' if preference == 'T' else '情感决策（考虑人际）' if preference == 'F' else '中性（T/F 均衡）'}",
        "evidence": {
            "T": t_evidence[:3],
            "F": f_evidence[:3],
        },
        "scores": {
            "T": t_percentage,
            "F": f_percentage,
        },
    }


def _analyze_j_p(features: dict, transcript: str, knowledge: dict) -> dict:
    """分析判断(J) vs 知觉(P)"""
    dim_config = knowledge.get("dimensions", {}).get("J_P", {})
    
    j_score = 0
    p_score = 0
    j_evidence = []
    p_evidence = []
    
    # ========== J 型信号检测 ==========
    j_keywords = dim_config.get("J", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in j_keywords:
        count = transcript.count(keyword)
        if count > 0:
            j_score += count
            if len(j_evidence) < 3:
                j_evidence.append(f"使用计划词汇 '{keyword}'（{count}次）")
    
    star_score = features.get("star_structure_score", 0)
    action_ratio = features.get("action_verbs_ratio", 0)
    certainty_ratio = features.get("certainty_words_ratio", 0)
    topic_stability = features.get("topic_stability_score", 0)
    
    if star_score >= 0.75:
        j_score += 3
        j_evidence.append(f"STAR 结构完整（{star_score:.2f}）")
    
    if action_ratio >= 0.018:
        j_score += 2
        j_evidence.append(f"行动动词比例高（{action_ratio:.3f}）")
    
    if certainty_ratio >= 0.005:
        j_score += 2
        j_evidence.append(f"确定性词汇较多（{certainty_ratio:.3f}）")
    
    if topic_stability >= 0.70:
        j_score += 2
        j_evidence.append(f"话题稳定性高（{topic_stability:.2f}）")
    
    # ========== P 型信号检测 ==========
    p_keywords = dim_config.get("P", {}).get("interview_markers", {}).get("lexical", {}).get("keywords", [])
    for keyword in p_keywords:
        count = transcript.count(keyword)
        if count > 0:
            p_score += count
            if len(p_evidence) < 3:
                p_evidence.append(f"使用灵活词汇 '{keyword}'（{count}次）")
    
    hedge_ratio = features.get("hedge_words_ratio", 0)
    qualifier_ratio = features.get("qualifier_ratio", 0)
    question_ratio = features.get("question_ratio", 0)
    
    if hedge_ratio >= 0.010:
        p_score += 3
        p_evidence.append(f"模糊限定词比例高（{hedge_ratio:.3f}）")
    
    if qualifier_ratio >= 0.012:
        p_score += 2
        p_evidence.append(f"修饰语比例高（{qualifier_ratio:.3f}）")
    
    if question_ratio >= 0.08:
        p_score += 2
        p_evidence.append(f"提问比例高（{question_ratio:.2f}）")
    
    if topic_stability < 0.65:
        p_score += 2
        p_evidence.append(f"话题跳跃较多（{topic_stability:.2f}）")
    
    # ========== 计算偏好 ==========
    total = j_score + p_score or 1
    j_percentage = int((j_score / total) * 100)
    p_percentage = int((p_score / total) * 100)
    
    if j_percentage > 55:
        preference = "J"
        strength = j_percentage
        confidence = "high" if j_percentage > 65 else "medium"
    elif p_percentage > 55:
        preference = "P"
        strength = p_percentage
        confidence = "high" if p_percentage > 65 else "medium"
    else:
        preference = "neutral"
        strength = 50
        confidence = "low"
    
    return {
        "preference": preference,
        "strength": strength,
        "confidence": confidence,
        "summary": f"倾向于{'计划型（结构化）' if preference == 'J' else '灵活型（开放性）' if preference == 'P' else '中性（J/P 均衡）'}",
        "evidence": {
            "J": j_evidence[:3],
            "P": p_evidence[:3],
        },
        "scores": {
            "J": j_percentage,
            "P": p_percentage,
        },
    }


def _infer_type(dimensions: dict) -> str:
    """根据四维度推断 MBTI 类型"""
    type_str = ""
    
    for dim_key in ["E_I", "N_S", "T_F", "J_P"]:
        dim_data = dimensions.get(dim_key, {})
        pref = dim_data.get("preference", "X")
        
        if pref == "neutral":
            type_str += "X"
        else:
            type_str += pref
    
    return type_str


def _detect_conflicts(dimensions: dict, disc_evidence: dict, knowledge: dict) -> list[dict]:
    """检测 DISC-MBTI 冲突"""
    conflicts = []
    
    disc_scores = disc_evidence.get("scores", {})
    if not disc_scores:
        return conflicts
    
    # 获取 DISC 最高分维度
    disc_ranking = sorted(disc_scores.items(), key=lambda x: x[1], reverse=True)
    if not disc_ranking:
        return conflicts
    
    top_disc = disc_ranking[0][0]
    top_score = disc_ranking[0][1]
    
    if top_score < 60:
        return conflicts  # 分数不够高,不检测冲突
    
    mapping = knowledge.get("cross_validation", {}).get("disc_mbti_mapping", {})
    conflict_patterns = knowledge.get("cross_validation", {}).get("conflict_detection", [])
    
    # ========== 检测 D-MBTI 冲突 ==========
    if top_disc == "D":
        likely = mapping.get("D_high", {}).get("likely", [])
        unlikely = mapping.get("D_high", {}).get("unlikely", [])
        
        t_f = dimensions.get("T_F", {})
        j_p = dimensions.get("J_P", {})
        
        if t_f.get("preference") == "F" and t_f.get("confidence") in ["high", "medium"]:
            conflicts.append({
                "type": "DISC-MBTI 冲突",
                "severity": "medium",
                "description": "DISC 显示强 D 特质（结果导向、决断力强），但 MBTI 显示 F 型（情感决策），可能存在情境适应或包装",
                "recommendation": "追问：在团队冲突中，你如何平衡任务目标和成员感受？请举具体例子。",
            })
        
        if j_p.get("preference") == "P" and j_p.get("confidence") == "high":
            for pattern in conflict_patterns:
                if pattern.get("pattern") == "high_D + P":
                    conflicts.append({
                        "type": "DISC-MBTI 冲突",
                        "severity": "low",
                        "description": pattern.get("description", ""),
                        "recommendation": pattern.get("recommendation", ""),
                    })
    
    # ========== 检测 I-MBTI 冲突 ==========
    if top_disc == "I":
        e_i = dimensions.get("E_I", {})
        t_f = dimensions.get("T_F", {})
        
        if e_i.get("preference") == "I" and e_i.get("confidence") in ["high", "medium"]:
            for pattern in conflict_patterns:
                if pattern.get("pattern") == "high_I + I(introvert)":
                    conflicts.append({
                        "type": "DISC-MBTI 冲突",
                        "severity": "high",
                        "description": pattern.get("description", ""),
                        "recommendation": pattern.get("recommendation", ""),
                    })
        
        if t_f.get("preference") == "T" and t_f.get("confidence") in ["high", "medium"]:
            conflicts.append({
                "type": "DISC-MBTI 冲突",
                "severity": "medium",
                "description": "DISC 显示强 I 特质（关注人际影响），但 MBTI 显示理性决策为主，需进一步验证",
                "recommendation": "追问：你在说服他人时，更依赖数据逻辑还是情感共鸣？",
            })
    
    # ========== 检测 S-MBTI 冲突 ==========
    if top_disc == "S":
        e_i = dimensions.get("E_I", {})
        
        if e_i.get("preference") == "E" and e_i.get("confidence") == "high":
            conflicts.append({
                "type": "DISC-MBTI 冲突",
                "severity": "low",
                "description": "DISC 显示强 S 特质（稳定内敛），但 MBTI 显示强外向型，可能在不同场景下表现差异较大",
                "recommendation": "追问：你在陌生环境和熟悉团队中的表现有什么差异？",
            })
    
    # ========== 检测 C-MBTI 冲突 ==========
    if top_disc == "C":
        n_s = dimensions.get("N_S", {})
        j_p = dimensions.get("J_P", {})
        
        if n_s.get("preference") == "N" and n_s.get("confidence") in ["high", "medium"]:
            conflicts.append({
                "type": "DISC-MBTI 冲突",
                "severity": "medium",
                "description": "DISC 显示强 C 特质（注重细节和数据），但 MBTI 显示 N 型（偏好抽象概念），需确认真实倾向",
                "recommendation": "追问：在项目执行中，你更关注整体方向还是具体细节？请举例说明。",
            })
        
        if j_p.get("preference") == "P" and j_p.get("confidence") in ["high", "medium"]:
            for pattern in conflict_patterns:
                if pattern.get("pattern") == "high_C + P":
                    conflicts.append({
                        "type": "DISC-MBTI 冲突",
                        "severity": "medium",
                        "description": pattern.get("description", ""),
                        "recommendation": pattern.get("recommendation", ""),
                    })
    
    return conflicts


def _generate_followups(dimensions: dict, knowledge: dict) -> list[dict]:
    """生成 MBTI 追问建议"""
    questions = []
    
    # 为低置信度维度生成追问
    for dim_key, dim_data in dimensions.items():
        confidence = dim_data.get("confidence", "low")
        
        if confidence in ["low", "medium"]:
            dim_name_map = {
                "E_I": "能量来源",
                "N_S": "信息获取",
                "T_F": "决策方式",
                "J_P": "生活方式",
            }
            
            # 从 MBTI.yaml 获取追问模板（简化处理）
            if dim_key == "E_I":
                questions.append({
                    "dimension": dim_name_map[dim_key],
                    "question": "在团队项目中，你更喜欢主导讨论还是独立完成任务？",
                    "purpose": "验证能量来源偏好（E/I）",
                })
            elif dim_key == "N_S":
                questions.append({
                    "dimension": dim_name_map[dim_key],
                    "question": "你在做决策时，更依赖过往经验还是对未来的判断？",
                    "purpose": "验证信息获取方式（N/S）",
                })
            elif dim_key == "T_F":
                questions.append({
                    "dimension": dim_name_map[dim_key],
                    "question": "当团队意见不一致时，你会优先考虑效率还是成员感受？",
                    "purpose": "验证决策方式（T/F）",
                })
            elif dim_key == "J_P":
                questions.append({
                    "dimension": dim_name_map[dim_key],
                    "question": "你更喜欢提前规划好所有细节，还是边做边调整？",
                    "purpose": "验证生活方式偏好（J/P）",
                })
    
    return questions[:4]


def _calculate_confidence(dimensions: dict, conflicts: list[dict]) -> str:
    """计算整体置信度"""
    high_count = sum(1 for d in dimensions.values() if d.get("confidence") == "high")
    medium_count = sum(1 for d in dimensions.values() if d.get("confidence") == "medium")
    
    high_severity = sum(1 for c in conflicts if c.get("severity") == "high")
    
    if high_count >= 3 and high_severity == 0:
        return "high"
    elif high_count >= 2 or (high_count >= 1 and medium_count >= 2):
        return "medium"
    else:
        return "low"