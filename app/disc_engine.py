from __future__ import annotations

from collections import defaultdict

from .features import feature_highlights


DIMENSIONS = ("D", "I", "S", "C")


def _keyword_hits(text: str, words: list[str]) -> int:
    return sum(text.count(word) for word in words)


def _apply_feature_rules(dim: str, features: dict) -> tuple[float, list[str], list[str]]:
    positive: list[str] = []
    negative: list[str] = []
    score = 25.0

    if dim == "D":
        if features["action_verbs_ratio"] >= 0.02:
            score += 18
            positive.append("行动词密度较高，回答更偏推进和解决问题。")
        if features["achievement_words_ratio"] >= 0.015:
            score += 15
            positive.append("结果/指标词较多，体现较强结果导向。")
        if features["hedge_words_ratio"] <= 0.006:
            score += 8
            positive.append("保留性表达较少，措辞相对直接。")
        if features["problem_vs_people_focus"] == "problem":
            score += 8
            positive.append("叙述更偏问题拆解和决策，而非单纯关系维护。")
        if features["qualifier_ratio"] >= 0.015:
            score -= 10
            negative.append("限定条件较多，削弱了高支配型常见的直接决断感。")

    if dim == "I":
        if features["social_words_ratio"] >= 0.015:
            score += 18
            positive.append("人际/沟通相关词较多，体现明显关系取向。")
        if features["emotional_words_ratio"] >= 0.008:
            score += 15
            positive.append("情绪和氛围表达更丰富。")
        if features["first_person_plural_ratio"] >= 0.01:
            score += 10
            positive.append("“我们/大家”等集体表达较多。")
        if features["story_richness_score"] >= 0.65:
            score += 6
            positive.append("回答叙事感较强，较容易形成感染力。")
        if features["abstraction_level"] == "grounded" and features["social_words_ratio"] < 0.01:
            score -= 8
            negative.append("表达更偏事实和结构，社交感染线索不强。")

    if dim == "S":
        if features["topic_stability_score"] >= 0.72:
            score += 15
            positive.append("多轮回答主题稳定，整体节奏较平稳。")
        if features["self_vs_team_orientation"] == "team":
            score += 18
            positive.append("团队导向明显，更强调协作与支持。")
        if features["action_vs_reflection_balance"] == "balanced":
            score += 8
            positive.append("行动与反思较平衡，符合稳健型常见表达。")
        if 0.004 <= features["hedge_words_ratio"] <= 0.015:
            score += 6
            positive.append("存在适度缓和表达，语气更稳妥。")
        if features["imperative_like_ratio"] >= 0.012:
            score -= 10
            negative.append("强推动/强指令色彩偏高，不完全符合高 S 的温和风格。")

    if dim == "C":
        if features["logical_connector_ratio"] >= 0.015:
            score += 18
            positive.append("逻辑连接较清晰，说明表达偏结构化。")
        if features["detail_words_ratio"] >= 0.015:
            score += 15
            positive.append("细节、依据、风险等词汇较多，说明注意准确性。")
        if features["star_structure_score"] >= 0.75:
            score += 12
            positive.append("回答基本覆盖情境、任务、行动、结果，结构完整。")
        if features["qualifier_ratio"] >= 0.008:
            score += 8
            positive.append("会补充前提、条件或边界，体现谨慎与严谨。")
        if features["topic_stability_score"] < 0.55:
            score -= 10
            negative.append("回答跳跃度偏高，削弱了严谨一致的印象。")

    return max(0.0, min(100.0, score)), positive, negative


def _dimension_keywords(knowledge: dict, dim: str) -> list[str]:
    return knowledge["dimensions"][dim]["positive_language_cues"]["lexical"]["strong_keywords"]


def _dimension_probe(knowledge: dict, dim: str, probe_type: str) -> list[str]:
    return knowledge["dimensions"][dim]["probe_questions"][probe_type]


def _score_band(knowledge: dict, score: int) -> str:
    mapping = knowledge["output_mapping"]["score_bands"]
    if score <= 24:
        return mapping["0_24"]
    if score <= 49:
        return mapping["25_49"]
    if score <= 74:
        return mapping["50_74"]
    return mapping["75_100"]


def _sample_quality(knowledge: dict, word_count: int, turn_count: int) -> str:
    minimum = knowledge["global_rules"]["minimum_sample_words"]
    preferred = knowledge["global_rules"]["preferred_sample_words"]
    if word_count < minimum or turn_count <= 1:
        return "low"
    if word_count < preferred or turn_count <= 2:
        return "medium"
    return "high"


def _confidence_level(sample_quality: str, contradictions: int, features: dict) -> tuple[str, list[str]]:
    notes: list[str] = []
    level = "medium"
    if sample_quality == "low":
        level = "low"
        notes.append("样本长度或轮次偏少，结论只能视为初步倾向。")
    if contradictions > 2:
        level = "low"
        notes.append("不同回答中的风格信号不够稳定，降低置信度。")
    if sample_quality == "high" and contradictions == 0 and features["story_richness_score"] >= 0.7:
        level = "high"
        notes.append("跨多个回答出现较稳定的风格线索，且细节较充分。")
    return level, notes


def _impression_management_risk(features: dict, word_count: int) -> tuple[str, list[str]]:
    notes: list[str] = []
    risk = "low"
    if features["buzzword_density"] >= 0.01:
        risk = "medium"
        notes.append("高频业务化套话可能掩盖自然表达风格。")
    if features["story_richness_score"] < 0.45 and word_count >= 120:
        risk = "medium"
        notes.append("叙述较泛化，具体细节不足，存在包装回答风险。")
    if features["buzzword_density"] >= 0.015 and features["story_richness_score"] < 0.4:
        risk = "high"
        notes.append("套话较多且操作细节偏少，需警惕强准备痕迹。")
    return risk, notes


def _build_critical_findings(features: dict, scores: dict[str, int], word_count: int) -> tuple[list[dict], list[str], list[str]]:
    findings: list[dict] = []
    hire_risks: list[str] = []
    evidence_gaps: list[str] = []

    if word_count >= 120 and features["story_richness_score"] < 0.45:
        findings.append(
            {
                "finding": "Long answer but low information density.",
                "severity": "high",
                "basis": ["limited narrative detail", "few verifiable actions or mechanisms"],
                "impact": "It is hard to verify whether the candidate has real execution depth.",
            }
        )
        hire_risks.append("Long answer with limited high-value information")
        evidence_gaps.append("Missing detailed walk-through of key actions")

    if features["star_structure_score"] < 0.55:
        findings.append(
            {
                "finding": "The task-action-result chain is incomplete.",
                "severity": "medium",
                "basis": ["weak STAR structure", "the answer sounds like a summary rather than a replay"],
                "impact": "Confidence in ownership and execution depth should be lowered.",
            }
        )
        evidence_gaps.append("Missing a complete task-action-result loop")

    if features["achievement_words_ratio"] < 0.006:
        findings.append(
            {
                "finding": "Outcome evidence is weak and lacks measurable comparison.",
                "severity": "medium",
                "basis": ["few outcome terms", "no clear before-after proof"],
                "impact": "It is difficult to confirm whether the candidate created real value.",
            }
        )
        hire_risks.append("Insufficient evidence of results")
        evidence_gaps.append("Missing quantified results or before-after comparison")

    if features["action_verbs_ratio"] < 0.015:
        findings.append(
            {
                "finding": "Personal actions and decision details are thin.",
                "severity": "medium",
                "basis": ["low action-verb density", "the answer sounds more participatory than owner-led"],
                "impact": "A supporting role may be overstated as a leading role.",
            }
        )
        hire_risks.append("Ownership and personal contribution need validation")
        evidence_gaps.append("Missing evidence of specific personal decisions and actions")

    if features["buzzword_density"] >= 0.012 and features["story_richness_score"] < 0.5:
        findings.append(
            {
                "finding": "The answer sounds polished, but mechanism detail is thin.",
                "severity": "high" if features["buzzword_density"] >= 0.018 else "medium",
                "basis": ["high buzzword density", "abstract claims are not backed by detail"],
                "impact": "If follow-up questions still get abstract answers, authenticity risk rises.",
            }
        )
        hire_risks.append("Possible impression-management or rehearsed-answer risk")

    if scores.get("C", 0) >= 70 and features["detail_words_ratio"] < 0.012:
        evidence_gaps.append("The answer sounds structured, but the detail density is still not enough for a high-C read")

    unique_hire_risks = list(dict.fromkeys(hire_risks))
    unique_evidence_gaps = list(dict.fromkeys(evidence_gaps))
    return findings[:4], unique_hire_risks[:4], unique_evidence_gaps[:5]



def _build_decision_outputs(scores: dict[str, int], critical_findings: list[dict], evidence_gaps: list[str], confidence: str, impression_risk: str) -> tuple[str, str, str]:
    ranking = sorted(scores, key=scores.get, reverse=True)
    top, second = ranking[:2]
    top_label = f"{top}/{second}"
    high_finding = next((item for item in critical_findings if item["severity"] == "high"), None)
    medium_finding = next((item for item in critical_findings if item["severity"] == "medium"), None)

    if high_finding:
        decision_summary = f"The surface style looks {top_label}, but the stronger signal is: {high_finding['finding']}"
    elif evidence_gaps:
        decision_summary = f"The style leans toward {top_label}, but the main blocker is: {evidence_gaps[0]}"
    else:
        decision_summary = f"The candidate currently leans toward a {top_label} style mix with relatively stable signals."

    if high_finding:
        risk_summary = "High-priority weaknesses are present and should be verified before giving credit."
    elif impression_risk == "high":
        risk_summary = "Authenticity risk is elevated and should be validated first."
    elif medium_finding or impression_risk == "medium":
        risk_summary = "Medium-level risk is present; verify key details before trusting the story."
    else:
        risk_summary = "No major red flag yet, but spot-checking is still required."

    if high_finding:
        recommended_action = "Continue the interview, but challenge the top weakness before moving on."
    elif confidence == "low":
        recommended_action = "Collect more samples before making a continue / stop decision."
    else:
        recommended_action = "Continue, but verify ownership, key actions, and outcome evidence first."

    return decision_summary, risk_summary, recommended_action


def analyze_disc(transcript: str, turns: list[dict], features: dict, knowledge: dict) -> dict:
    word_count = len(transcript.replace("\n", ""))
    sample_quality = _sample_quality(knowledge, word_count, len(turns))

    scores: dict[str, int] = {}
    dimension_analysis: dict[str, dict] = {}
    all_positive: dict[str, list[str]] = defaultdict(list)
    all_negative: dict[str, list[str]] = defaultdict(list)

    for dim in DIMENSIONS:
        base_score, positive, negative = _apply_feature_rules(dim, features)
        keyword_score = min(22, _keyword_hits(transcript, _dimension_keywords(knowledge, dim)) * 4)
        final_score = int(max(0, min(100, round(base_score + keyword_score))))
        scores[dim] = final_score
        if keyword_score > 0:
            positive.append(f"出现了与 {dim} 维度相关的高频语言指纹。")
        if not positive:
            positive.append("直接支持该维度的强证据有限。")
        if not negative:
            negative.append("未发现足以明显压低该维度的强反证，但样本仍有限。")
        all_positive[dim].extend(positive)
        all_negative[dim].extend(negative)
        dimension_analysis[dim] = {
            "score": final_score,
            "band": _score_band(knowledge, final_score),
            "evidence_for": positive[:4],
            "evidence_against": negative[:3],
            "summary": knowledge["dimensions"][dim]["score_interpretation"]["high" if final_score >= 75 else "medium" if final_score >= 50 else "low"],
        }

    ranking = sorted(scores, key=scores.get, reverse=True)
    contradictions = sum(1 for dim in DIMENSIONS if scores[dim] >= 60 and len(all_negative[dim]) >= 2)
    confidence, confidence_notes = _confidence_level(sample_quality, contradictions, features)
    impression_risk, risk_notes = _impression_management_risk(features, word_count)

    top_dimensions = ranking[:2]
    hypotheses = []
    for dim in top_dimensions:
        hypotheses.append(
            {
                "hypothesis": f"候选人呈现出偏 {knowledge['dimensions'][dim]['label']} 的表达风格。",
                "strength": "strong" if scores[dim] >= 75 else "medium" if scores[dim] >= 50 else "weak",
                "basis": dimension_analysis[dim]["evidence_for"][:3],
            }
        )

    if top_dimensions == ["D", "C"] or top_dimensions == ["C", "D"]:
        hypotheses.append(
            {
                "hypothesis": "整体可能呈现“强推动 + 重结构”的 D/C 复合风格。",
                "strength": "medium",
                "basis": ["同时出现结果导向和结构化表达线索。"],
            }
        )

    follow_up_questions = []
    for dim in top_dimensions:
        follow_up_questions.append(
            {
                "target_dimension": dim,
                "question": _dimension_probe(knowledge, dim, "confirm")[0],
                "purpose": f"验证当前对 {dim} 维度的初步判断是否成立。",
            }
        )
    for dim in ranking[-2:]:
        follow_up_questions.append(
            {
                "target_dimension": dim,
                "question": _dimension_probe(knowledge, dim, "challenge")[0],
                "purpose": f"Test the candidate's lower-bound behavior on {dim}.",
            }
        )

    critical_findings, hire_risks, evidence_gaps = _build_critical_findings(features, scores, word_count)
    decision_summary, risk_summary, recommended_action = _build_decision_outputs(
        scores, critical_findings, evidence_gaps, confidence, impression_risk
    )
    style_summary = f"Current sample leans toward a {ranking[0]}-{ranking[1]} mix, with {ranking[0]} highest and {ranking[-1]} relatively weaker."

    return {
        "meta": {
            "sample_quality": sample_quality,
            "confidence": confidence,
            "impression_management_risk": impression_risk,
            "notes": confidence_notes + risk_notes,
        },
        "critical_findings": critical_findings,
        "hire_risks": hire_risks,
        "evidence_gaps": evidence_gaps,
        "scores": scores,
        "ranking": ranking,
        "dimension_analysis": dimension_analysis,
        "decision_summary": decision_summary,
        "risk_summary": risk_summary,
        "recommended_action": recommended_action,
        "overall_style_summary": style_summary,
        "behavioral_hypotheses": hypotheses,
        "follow_up_questions": follow_up_questions,
        "feature_highlights": feature_highlights(features),
    }
