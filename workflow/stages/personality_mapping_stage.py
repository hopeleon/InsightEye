from __future__ import annotations

from app.personality_mapping import map_personality

from workflow.context import WorkflowContext


<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
=======
>>>>>>> Stashed changes
# ─────────────────────────────────────────────────────────────────────────────
# 跨模型冲突检测
# ─────────────────────────────────────────────────────────────────────────────

def _norm_bf_score(raw) -> float:
    """统一 BigFive 分值格式：支持 0~100 也支持 0~1"""
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return v if v <= 1.0 else v / 100.0


def _rank_disc(scores: dict) -> list[tuple[str, float]]:
    if not scores:
        return []
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ── BigFive ↔ DISC 冲突检测 ────────────────────────────────────────────────

def _detect_bigfive_disc_conflicts(
    bf_scores: dict,
    disc_scores: dict,
    disc_ranking: list[tuple[str, float]],
) -> list[dict]:
    """
    基于 BigFive 五维度与 DISC 主维度之间的已知心理学关联规则，
    检测两者之间的异常矛盾，返回冲突列表。

    规则逻辑（置信度阈值 60%）：
      D  → C+  E+  A-  N-   (与 bigfive_scores 中的 C/E/A/N 对应)
      I  → E+  A+  O+  N-
      S  → A+  N+  C+  E-
      C  → C+  O+  N-  E-
    """
    conflicts: list[dict] = []

    if not bf_scores or not disc_scores or not disc_ranking:
        return conflicts

    top_disc, top_disc_score = disc_ranking[0]
    if top_disc_score < 60:
        return conflicts

    O = _norm_bf_score(bf_scores.get("openness", 0))
    C = _norm_bf_score(bf_scores.get("conscientiousness", 0))
    E = _norm_bf_score(bf_scores.get("extraversion", 0))
    A = _norm_bf_score(bf_scores.get("agreeableness", 0))
    N = _norm_bf_score(bf_scores.get("neuroticism", 0))

    def is_low(v: float) -> bool:
        return v < 0.40
    def is_high(v: float) -> bool:
        return v > 0.65
    def is_mid(v: float) -> bool:
        return 0.40 <= v <= 0.65

    # D vs BigFive
    if top_disc == "D":
        if is_high(C):
            pass  # 一致
        elif is_low(C) and not is_low(N):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "medium",
                "source": "bigfive_disc",
                "description": f"DISC 显示强 D 特质（主导、决断），但 BigFive 尽责性（C={int(C*100)}%）偏低，行动自律性存疑",
                "recommendation": "追问：你具体是如何保证项目按计划推进的？有哪些自我约束手段？",
            })
        if is_high(N):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "medium",
                "source": "bigfive_disc",
                "description": f"DISC 强 D（抗压决断），但 BigFive 神经质（N={int(N*100)}%）偏高，情绪稳定性值得关注",
                "recommendation": "追问：你在高压项目deadline前通常如何调节焦虑情绪？",
            })
        if is_high(A):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "low",
                "source": "bigfive_disc",
                "description": f"DISC 强 D（主导控制），但 BigFive 宜人性（A={int(A*100)}%）偏高，合作倾向与主导性存在张力",
                "recommendation": "追问：当你与团队成员意见分歧很大时，你会怎么做？",
            })
        if is_low(E) and is_high(C):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "low",
                "source": "bigfive_disc",
                "description": f"DISC 强 D（外向表达），但 BigFive 外向性（E={int(E*100)}%）偏低，在开放性上信号矛盾",
                "recommendation": "追问：你平时在团队讨论中是主动发起者还是倾向于独立思考后发言？",
            })

    # I vs BigFive
    elif top_disc == "I":
        if is_high(E):
            pass
        elif is_low(E):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "medium",
                "source": "bigfive_disc",
                "description": f"DISC 强 I（社交活跃），但 BigFive 外向性（E={int(E*100)}%）偏低，真实社交能量存疑",
                "recommendation": "追问：你最近一次主动组织团队活动是什么时候？平时社交活动频率如何？",
            })
        if is_low(A):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "medium",
                "source": "bigfive_disc",
                "description": f"DISC 强 I（人际影响），但 BigFive 宜人性（A={int(A*100)}%）偏低，影响力可能建立在竞争而非合作上",
                "recommendation": "追问：你更倾向于说服他人接受你的方案，还是先倾听再引导？",
            })
        if is_high(C) and is_low(E):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "low",
                "source": "bigfive_disc",
                "description": f"DISC 强 I（活泼影响），但 BigFive 显示高严谨（{int(C*100)}%）低外向（{int(E*100)}%），I 型可能为情境适应",
                "recommendation": "追问：在陌生人多的场合，你的表现和熟人团队中有多大差别？",
            })

    # S vs BigFive
    elif top_disc == "S":
        if is_high(A):
            pass
        elif is_low(A):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "medium",
                "source": "bigfive_disc",
                "description": f"DISC 强 S（稳定和谐），但 BigFive 宜人性（A={int(A*100)}%）偏低，合作意愿与 S 调性不一致",
                "recommendation": "追问：当你必须表达不同意见时，你通常会怎么处理？",
            })
        if is_low(N) and is_high(C):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "low",
                "source": "bigfive_disc",
                "description": f"DISC 强 S（平和稳定），但 BigFive 高严谨（{int(C*100)}%）低情绪波动（N={int(N*100)}%），高标准与 S 的随和可能存在自我包装",
                "recommendation": "追问：你认为自己的高标准和追求完美是天生的，还是工作后逐步养成的习惯？",
            })
        if is_high(O) and is_low(A):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "low",
                "source": "bigfive_disc",
                "description": f"DISC 强 S（偏好稳定流程），但 BigFive 开放性（O={int(O*100)}%）高，稳定性与开放性之间存在内在张力",
                "recommendation": "追问：你更喜欢有清晰SOP的稳定工作，还是经常变化、需要快速适应的环境？",
            })

    # C vs BigFive
    elif top_disc == "C":
        if is_high(C):
            pass
        elif is_low(C):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "medium",
                "source": "bigfive_disc",
                "description": f"DISC 强 C（结构严谨），但 BigFive 尽责性（C={int(C*100)}%）偏低，计划性和自律性存疑",
                "recommendation": "追问：你是怎么在没有明确流程约束的情况下保证交付质量的？",
            })
        if is_low(O):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "medium",
                "source": "bigfive_disc",
                "description": f"DISC 强 C（分析思维），但 BigFive 开放性（O={int(O*100)}%）偏低，抽象探索能力受限",
                "recommendation": "追问：你曾提出过哪些不在常规流程内的创新改进建议？",
            })
        if is_high(N):
            conflicts.append({
                "type": "BigFive ↔ DISC 冲突",
                "severity": "high",
                "source": "bigfive_disc",
                "description": f"DISC 强 C（冷静理性），但 BigFive 神经质（N={int(N*100)}%）偏高，情绪波动可能影响分析判断的客观性",
                "recommendation": "追问：你如何区分「合理担忧」和「不必要的焦虑」？过往有因为焦虑影响工作质量的经历吗？",
            })
        if is_low(E):
            pass

    return conflicts


# ── Enneagram ↔ DISC 冲突检测 ────────────────────────────────────────────

# 九型核心动机标签 → 对应 DISC 预期风格
_ENNG_TO_DISC_EXPECTED = {
    "type_1": "C",   # 完美主义者 → C 蓝色
    "type_2": "I",   # 助人者     → I 黄色
    "type_3": "D",   # 成就者     → D 红色
    "type_4": "I",   # 浪漫者     → I/S（情绪敏感）
    "type_5": "C",   # 探索者     → C 蓝色（内省分析）
    "type_6": "S",   # 忠诚者     → S 绿色（寻求安全）
    "type_7": "I",   # 活跃者     → I 黄色（外向乐观）
    "type_8": "D",   # 保护者     → D 红色（掌控）
    "type_9": "S",   # 和平者     → S 绿色（和谐）
}

# Enneagram 过度包装风险类型（关注表面成就、回避深层反思）
_ENNG_PACKING_RISK = {"type_3", "type_7", "type_1"}

# Enneagram 高焦虑风险类型
_ENNG_ANXIETY_RISK = {"type_6", "type_4", "type_1"}


def _detect_enneagram_disc_conflicts(
    enneagram_result: dict,
    disc_scores: dict,
    disc_ranking: list[tuple[str, float]],
    features: dict | None = None,
) -> list[dict]:
    """
    基于九型人格类型与 DISC 主维度之间的预期关系，
    检测两者之间的异常矛盾，并识别过度包装风险。
    """
    conflicts: list[dict] = []

    if not enneagram_result or not disc_scores or not disc_ranking:
        return conflicts

    top_disc, top_disc_score = disc_ranking[0]
    if top_disc_score < 60:
        return conflicts

    # 提取九型类型
    top_types = enneagram_result.get("top_two_types", [])
    if not top_types:
        top_two = enneagram_result.get("top_two_types", [])
    else:
        top_two = top_types

    if not top_two:
        return conflicts

    primary = top_two[0]
    primary_type = str(primary.get("type_number") or primary.get("type") or "").strip()
    if not primary_type:
        return conflicts

    expected_disc = _ENNG_TO_DISC_EXPECTED.get(f"type_{primary_type}")
    primary_score = primary.get("raw_score") or primary.get("score") or 50

    # 核心冲突检测
    if expected_disc and expected_disc != top_disc:
        # 仅当九型类型置信度高时才报告
        if primary_score >= 55:
            severity = "high" if abs(primary_score - top_disc_score) > 30 else "medium"
            enng_meta = {
                "type_1": ("Type 1 改革者", "追求完美与标准"),
                "type_2": ("Type 2 助人者", "渴望被需要与认可"),
                "type_3": ("Type 3 成就者", "目标导向、追求成功"),
                "type_4": ("Type 4 自我型", "渴望独特与深度连接"),
                "type_5": ("Type 5 探索者", "渴望知识与独立"),
                "type_6": ("Type 6 忠诚者", "寻求安全与支持"),
                "type_7": ("Type 7 活跃者", "追求自由与多元体验"),
                "type_8": ("Type 8 保护者", "渴望掌控与保护"),
                "type_9": ("Type 9 和平者", "渴望和谐与内在平静"),
            }
            enng_label, enng_core = enng_meta.get(f"type_{primary_type}", (f"Type {primary_type}", ""))
            DISC_META = {"D": "D 型（主导决断）", "I": "I 型（人际影响）", "S": "S 型（稳定支持）", "C": "C 型（结构分析）"}
            DISC_DOMINANT = {"D": "主导决断", "I": "人际影响", "S": "稳定支持", "C": "结构分析"}

            conflicts.append({
                "type": "Enneagram ↔ DISC 冲突",
                "severity": severity,
                "source": "enneagram_disc",
                "description": f"九型核心动机为 {enng_label}（{enng_core}），预期对应 {DISC_META.get(expected_disc, '')}，"
                               f"但 DISC 显示 {DISC_DOMINANT.get(top_disc, top_disc)}（得分 {top_disc_score}），两者存在明显偏差",
                "recommendation": f"追问：{_enneagram_followup_question(primary_type, top_disc)}",
            })

    # Type 3 高风险：成就导向过强，STAR 叙事可能过度包装
    if primary_type in _ENNG_PACKING_RISK and primary_score >= 60:
        star_score = 0.0
        if features:
            star_score = float(features.get("star_structure_score") or 0)
        achievement_ratio = float(features.get("achievement_words_ratio") or 0) if features else 0
        if star_score < 0.60 and achievement_ratio > 0.010:
            conflicts.append({
                "type": "Enneagram ↔ STAR 包装风险",
                "severity": "high",
                "source": "enneagram_disc",
                "description": f"Enneagram Type {primary_type} 高分（{primary_score}），成就词密度高但 STAR 结构弱（{int(star_score*100)}%），"
                               "叙事可能以成就自我标榜为主，缺乏真实行为锚点",
                "recommendation": "追问：请描述你在这个项目中具体负责了哪几步？最终可量化的结果是什么，数字是你统计的还是上级告知的？",
            })

    # Type 6 高焦虑：与高神经质或低自信信号结合时
    if primary_type == "6" and primary_score >= 60:
        N = 0.0
        if features:
            N = float(features.get("social_words_ratio") or 0)  # 粗略替代焦虑信号
        if N < 0.005:  # 低社交词汇可能暗示回避
            conflicts.append({
                "type": "Enneagram ↔ DISC 风险信号",
                "severity": "medium",
                "source": "enneagram_disc",
                "description": "Type 6 忠诚者（寻求安全）但 DISC 为 S 型（稳定内敛），可能存在过度谨慎或回避冲突的倾向",
                "recommendation": "追问：当你发现团队方向可能有风险时，你会直接指出还是会先观察一段时间？",
            })

    return conflicts


def _enneagram_followup_question(enng_type: str, disc_type: str) -> str:
    q_map = {
        ("type_1", "D"): "你追求的高标准和底线，最初是怎么形成的？有人质疑过你的标准吗？",
        ("type_1", "I"): "你是如何让团队成员接受你的高要求的？有没有引起过反弹？",
        ("type_1", "S"): "你对完美的追求，会让同事感到压力吗？你是怎么处理的？",
        ("type_1", "C"): "你在追求完美的过程中，最常在哪类事情上纠结？为什么？",
        ("type_2", "D"): "你的助人行为，是发自内心还是因为觉得「我必须有用才能被认可」？",
        ("type_2", "I"): "当你的帮助被对方拒绝时，你通常会有什么感受？你是怎么应对的？",
        ("type_2", "S"): "你会不会因为过度关注他人需求而忽略自己的优先事项？请举例。",
        ("type_2", "C"): "你如何在「帮助他人」和「按计划完成任务」之间平衡？",
        ("type_3", "D"): "你描述的这些成就，哪些是你主导的，哪些是团队协作的成果？你具体负责了什么？",
        ("type_3", "I"): "你最自豪的一次「成功」经历，身边人是怎么评价你的？他们知道你背后的付出吗？",
        ("type_3", "S"): "如果你发现用一种更保守的方式能达到 80% 的效果，你会选择那条路吗？",
        ("type_3", "C"): "在追求目标的过程中，你是否有过「说了大话但最后没做到」的经历？",
        ("type_4", "D"): "你曾说「与众不同很重要」，在团队合作中你是如何平衡个人独特性和协作需求的？",
        ("type_4", "I"): "你内心深处的目标和外在表现出来的形象，差距有多大？有没有被人误解的经历？",
        ("type_4", "S"): "当你的想法不被认同时，你通常会选择坚持还是妥协？",
        ("type_4", "C"): "你认为「做自己」和「遵守团队规则」能同时做到吗？",
        ("type_5", "D"): "你通常观察多久才会出手干预一个正在偏离轨道的问题？",
        ("type_5", "I"): "你是主动分享你的分析和发现，还是等人来问？哪种方式更舒服？",
        ("type_5", "S"): "当你对某件事有深入见解但团队不需要时，你会怎么做？",
        ("type_5", "C"): "你更享受「提出深刻洞察」还是「自己动手执行到位」？",
        ("type_6", "D"): "你对规则的信任程度如何？当你发现规定可能有漏洞时会怎么做？",
        ("type_6", "I"): "你更依赖规则还是直觉来做判断？有没有两者产生矛盾的经历？",
        ("type_6", "S"): "你对「安全」的定义是什么？什么样的信号会让你决定退出或坚持？",
        ("type_6", "C"): "当权威人士告诉你「按我说的做」但你直觉判断有问题时，你会怎么做？",
        ("type_7", "D"): "你说「有很多想法」，其中有多少是你真正深入研究过的？",
        ("type_7", "I"): "你是如何在多线程任务中保持专注的？有没有因为分散精力导致失误的经历？",
        ("type_7", "S"): "你描述的乐观目标，有没有遭遇过被团队成员质疑「不现实」的情况？",
        ("type_7", "C"): "你会不会有时因为追求刺激和新鲜感，而低估了任务的风险？请举例。",
        ("type_8", "D"): "你如何区分「推动事情前进」和「控制欲过强」？有人说你强势吗？",
        ("type_8", "I"): "当你的强势引起团队反感时，你是如何调整的？",
        ("type_8", "S"): "你有没有经历过「保护他人反而伤害了关系」的情况？",
        ("type_8", "C"): "你如何让自己「果断但不冲动」？有没有冲动决策后后悔的经历？",
        ("type_9", "D"): "当团队决定和你内心偏好完全相反时，你会怎么应对？",
        ("type_9", "I"): "你会不会因为「不想破坏和谐」而隐瞒自己的真实想法？请举例。",
        ("type_9", "S"): "你如何在「满足他人期望」和「坚持自己的原则」之间取舍？",
        ("type_9", "C"): "当你对某件事有强烈意见但决定已经做出，你会怎么做？",
    }
    return q_map.get((enng_type, disc_type), f"请结合你九型核心动机和DISC主导风格，谈谈你在压力下的真实反应。")


# ─────────────────────────────────────────────────────────────────────────────
# Stage 入口
# ─────────────────────────────────────────────────────────────────────────────

<<<<<<< Updated upstream
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
def run_personality_mapping_stage(context: WorkflowContext) -> WorkflowContext:
    context.mark_stage("personality_mapping_stage", "started", "Run cross-model personality mapping")
    context.personality_mapping_result = map_personality(
        disc_result=context.local_disc_result,
        bigfive_result=getattr(context, "bigfive_result", None),
        enneagram_result=getattr(context, "enneagram_result", None),
        features=context.features,
    )
<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
=======
>>>>>>> Stashed changes

    # ── 冲突检测并注入 mbti_analysis.conflicts ────────────────────────────
    disc_scores = context.local_disc_result.get("scores", {}) if context.local_disc_result else {}
    disc_ranking = _rank_disc(disc_scores)
    bf_scores = (getattr(context, "bigfive_result", None) or {}).get("scores", {})
    enneagram_result = getattr(context, "enneagram_result", None)

    bf_conflicts = _detect_bigfive_disc_conflicts(bf_scores, disc_scores, disc_ranking)
    enng_conflicts = _detect_enneagram_disc_conflicts(
        enneagram_result, disc_scores, disc_ranking, context.features
    )

    all_conflicts = bf_conflicts + enng_conflicts

    if all_conflicts and context.mbti_analysis:
        existing = context.mbti_analysis.get("conflicts") or []
        # 去重（按 type + description[:30] 判重）
        seen_keys = {c["type"] + (c.get("description") or "")[:30] for c in existing}
        for c in all_conflicts:
            key = c["type"] + (c.get("description") or "")[:30]
            if key not in seen_keys:
                existing.append(c)
        context.mbti_analysis["conflicts"] = existing[:8]

<<<<<<< Updated upstream
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
    context.mark_stage("personality_mapping_stage", "completed", "Cross-model personality mapping ready")
    return context
