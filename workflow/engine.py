from __future__ import annotations

from app.config import OPENAI_ANALYSIS_MODEL, OPENAI_API_KEY, OPENAI_PARSER_MODEL
from app.knowledge import load_disc_knowledge, load_disc_prompt, load_mbti_knowledge  # 新增

from .context import WorkflowContext
from .stages.decision_stage import run_decision_stage
from .stages.disc_evidence_stage import run_disc_evidence_stage
from .stages.feature_stage import run_feature_stage
from .stages.llm_stage import run_llm_stage
from .stages.masking_stage import run_masking_stage
from .stages.parse_stage import run_parse_stage
from .stages.mbti_stage import run_mbti_stage  # 新增


def build_response(context: WorkflowContext) -> dict:
    return {
        "input_overview": {
            "segment_count": len(context.segments),
            "turn_count": len(context.detailed_turns),
            "candidate_char_count": context.features.get("text_length", 0),
        },
        "interview_map": {
            "job_inference": context.job_inference,
            "segments": context.segments,
            "turns": context.detailed_turns,
            "parse_source": context.parse_source,
        },
        "atomic_features": context.features,
        "disc_analysis": context.disc_analysis,
        "mbti_analysis": context.mbti_analysis,  # 新增
        "llm_analysis": context.analysis_output,
        "llm_status": {
            "enabled": bool(OPENAI_API_KEY),
            "parser_model": OPENAI_PARSER_MODEL,
            "analysis_model": OPENAI_ANALYSIS_MODEL,
            "parser_error": context.parser_error,
            "analysis_error": context.analysis_error,
            "parser_output_available": context.parser_output is not None,
        },
        "workflow": {
            "version": "v0.3",  # 版本号升级
            "mode": "disc+mbti",  # 模式更新
            "stage_trace": context.stage_trace,
            "disc_evidence": context.disc_evidence,
            "masking_assessment": context.masking_assessment,
            "decision_payload": context.decision_payload,
        },
    }


def run_disc_workflow(transcript: str, job_hint: str = "") -> dict:
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=load_disc_knowledge(),
        mbti_knowledge=load_mbti_knowledge(),  # 新增
    )
    disc_prompt = load_disc_prompt()

    for stage in (
        run_parse_stage,
        run_feature_stage,
        run_disc_evidence_stage,
        run_mbti_stage,  # 新增：在 masking 之前运行
        run_masking_stage,
        run_decision_stage,
    ):
        context = stage(context)

    context = run_llm_stage(context, disc_prompt=disc_prompt)
    return build_response(context)

def run_local_workflow(transcript: str, job_hint: str = "") -> dict:
    """
    仅运行本地规则分析（不调用 LLM）
    用于快速返回初步结果
    """
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=load_disc_knowledge(),
        mbti_knowledge=load_mbti_knowledge(),
    )

    # 只运行本地阶段
    for stage in (
        run_parse_stage,
        run_feature_stage,
        run_disc_evidence_stage,
        run_mbti_stage,
        run_masking_stage,
        run_decision_stage,
    ):
        context = stage(context)

    # 不调用 LLM
    return build_response(context)


def should_trigger_llm(local_result: dict) -> tuple[bool, str]:
    """
    判断是否需要调用 LLM 深度分析
    
    返回: (是否触发, 触发原因)
    """
    if not local_result:
        return True, "本地分析结果为空"
    
    reasons = []
    
    # 1. 样本质量检查
    input_overview = local_result.get("input_overview") or {}
    char_count = input_overview.get("candidate_char_count", 0)
    if char_count < 200:
        reasons.append(f"样本字数不足（{char_count} < 200字）")
    
    # 2. DISC 主导维度不明显
    disc_analysis = local_result.get("disc_analysis") or {}
    disc_scores = disc_analysis.get("scores") or {}
    if disc_scores:
        try:
            max_score = max(disc_scores.values()) if disc_scores.values() else 0
            if max_score < 60:
                reasons.append(f"DISC 无明显主导维度（最高分 {max_score}）")
        except (ValueError, TypeError):
            pass
    
    # 3. MBTI 多维度中性（修复点）
    mbti_analysis = local_result.get("mbti_analysis") or {}
    mbti_dims = mbti_analysis.get("dimensions") or {}
    neutral_count = 0
    if isinstance(mbti_dims, dict):
        for dim_data in mbti_dims.values():
            if isinstance(dim_data, dict) and dim_data.get("preference") == "neutral":
                neutral_count += 1
    
    if neutral_count >= 2:
        reasons.append(f"MBTI 有 {neutral_count} 个维度为中性，信号不足")
    
    # 4. 检测到高严重度冲突
    conflicts = mbti_analysis.get("conflicts") or []
    high_conflicts = []
    if isinstance(conflicts, list):
        high_conflicts = [
            c for c in conflicts 
            if isinstance(c, dict) and c.get("severity") == "high"
        ]
    
    if high_conflicts:
        reasons.append(f"检测到 {len(high_conflicts)} 个高严重度冲突，需深度验证")
    
    # 5. 包装风险高
    disc_meta = disc_analysis.get("meta") or {}
    risk = disc_meta.get("impression_management_risk", "")
    risk_str = str(risk).lower()
    if "高" in risk_str or "high" in risk_str:
        reasons.append("包装风险高，需 LLM 深度解析")
    
    # 6. 样本质量标记为低
    quality = disc_meta.get("sample_quality", "")
    quality_str = str(quality).lower()
    if any(keyword in quality_str for keyword in ["低", "差", "不足", "薄弱"]):
        reasons.append(f"样本质量评估为: {quality}")
    
    # 7. 问答轮次过少
    turn_count = input_overview.get("turn_count", 0)
    if turn_count < 3:
        reasons.append(f"问答轮次过少（{turn_count} < 3轮）")
    
    # 如果有任一条件触发
    if reasons:
        return True, " | ".join(reasons)
    else:
        return False, "本地规则置信度充足，无需 LLM 深度分析"

def run_llm_only(context: WorkflowContext, disc_prompt: str) -> WorkflowContext:
    """
    仅运行 LLM 阶段（基于已有的 context）
    """
    from workflow.stages.llm_stage import run_llm_stage
    
    context = run_llm_stage(context, disc_prompt=disc_prompt)
    return context