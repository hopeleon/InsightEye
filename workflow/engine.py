from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from app.config import (
    OPENAI_ANALYSIS_MODEL,
    OPENAI_API_KEY,
    OPENAI_PARSER_MODEL,
    OPENAI_PERSONALITY_MODEL,
)
from app.knowledge import (
    load_bigfive_knowledge,
    load_bigfive_prompt,
    load_disc_knowledge,
    load_disc_prompt,
    load_enneagram_knowledge,
    load_enneagram_prompt,
    load_star_knowledge,
)
from app.star_analyzer import analyze_star

from .context import WorkflowContext
from .helpers import (
    build_bigfive_messages,
    build_disc_messages,
    build_enneagram_messages,
    call_openai_compatible,
)
from .stages.bigfive_stage import run_bigfive_stage
from .stages.decision_stage import run_decision_stage
from .stages.disc_evidence_stage import run_disc_evidence_stage
from .stages.disc_stage import run_disc_stage
from .stages.feature_stage import run_feature_stage
from .stages.llm_stage import run_llm_stage
from .stages.masking_stage import run_masking_stage
from .stages.mbti_stage import run_mbti_stage
from .stages.parse_stage import run_parse_stage
from .stages.personality_mapping_stage import run_personality_mapping_stage
from .stages.enneagram_stage import run_enneagram_stage
from .stages.star_stage import run_star_stage

# ---- 知识图谱加速层（完全独立，不侵入原有 stage 逻辑）----
try:
    from .knowledge_graph import get_graph_accelerator, ENABLE_GRAPH_ACCEL
    _GRAPH_ACCEL_AVAILABLE = True
except Exception as e:
    print(f"[知识图谱] 模块未加载: {e}")
    _GRAPH_ACCEL_AVAILABLE = False
    ENABLE_GRAPH_ACCEL = False


def _star_dimension_scores_usable(ds: object) -> bool:
    if not isinstance(ds, dict) or not ds:
        return False
    return any(k in ds for k in ("S", "T", "A", "R"))


def _coalesce_star_analysis(context: WorkflowContext) -> dict | None:
    """确保 JSON 中 star_analysis 带有可展示的 dimension_scores（容错 / 旧缓存场景）。"""
    star = context.star_result
    if isinstance(star, dict) and _star_dimension_scores_usable(star.get("dimension_scores")):
        return star
    try:
        return analyze_star(
            context.transcript,
            context.detailed_turns,
            context.features,
            load_star_knowledge(),
        )
    except Exception:
        return star if isinstance(star, dict) else None


def build_response(context: WorkflowContext, *, apply_knowledge_graph: bool = True) -> dict:
    response = {
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
        "star_analysis": _coalesce_star_analysis(context),
        "bigfive_analysis": context.bigfive_result,
        "enneagram_analysis": context.enneagram_result,
        "mbti_analysis": context.mbti_result,
        "personality_mapping": context.personality_mapping_result,
        "llm_analysis": context.analysis_output,
        "llm_bigfive_analysis": context.llm_bigfive_output,
        "llm_enneagram_analysis": context.llm_enneagram_output,
        "llm_status": {
            "enabled": bool(OPENAI_API_KEY),
            "parser_model": OPENAI_PARSER_MODEL,
            "analysis_model": OPENAI_ANALYSIS_MODEL,
            "personality_model": OPENAI_PERSONALITY_MODEL if OPENAI_API_KEY else None,
            "parser_error": getattr(context, "parser_error", None),
            "analysis_error": getattr(context, "analysis_error", None),
            "parser_output_available": context.parser_output is not None,
        },
        "workflow": {
            "version": "v0.4",
            "mode": "disc_with_personality",
            "stage_trace": context.stage_trace,
            "disc_evidence": context.disc_evidence,
            "masking_assessment": context.masking_assessment,
            "decision_payload": context.decision_payload,
        },
    }

    # ============================================================
    # 知识图谱加速层（完全不修改原有 stage，仅在响应层注入）
    # ============================================================
    if not apply_knowledge_graph:
        response["graph_boost"] = {
            "enabled": False,
            "suppressed_by_client": True,
            "skipped_stages": [],
            "speedup_ratio": 0.0,
            "conflict_hit_rate": 0.0,
        }
    elif _GRAPH_ACCEL_AVAILABLE and ENABLE_GRAPH_ACCEL:
        try:
            graph = get_graph_accelerator()

            # ① MBTI 冲突检查：用图谱预计算补充 stage 分析结果
            if context.mbti_result and isinstance(context.mbti_result, dict):
                disc_scores: dict[str, float] = {}
                if context.disc_analysis and isinstance(context.disc_analysis, dict):
                    raw = context.disc_analysis.get("scores", {})
                    disc_scores = {k: float(v or 0) for k, v in raw.items()}

                bigfive_scores: dict[str, float] | None = None
                if context.bigfive_result and isinstance(context.bigfive_result, dict):
                    bf_raw = context.bigfive_result.get("scores", {})
                    bigfive_scores = {k: float(v or 0) for k, v in bf_raw.items()}

                mbti_dims = context.mbti_result.get("dimensions") or {}
                graph_conflicts = graph.get_conflicts(
                    disc_scores, mbti_dims, bigfive_scores
                )
                if graph_conflicts:
                    existing = response["mbti_analysis"].get("conflicts") or []
                    # 图谱冲突去重合并
                    seen_keys = {c["type"] + c["description"][:20] for c in existing}
                    for c in graph_conflicts:
                        key = c["type"] + c["description"][:20]
                        if key not in seen_keys:
                            existing.append(c)
                    response["mbti_analysis"]["conflicts"] = existing[:6]

            # ② 图谱加速效果报告（供前端计时器旁的图谱指示器）
            report = graph.get_speedup_report()
            response["graph_boost"] = {
                "enabled": report["enabled"],
                "skipped_stages": report["skipped"],
                "speedup_ratio": report["speedup_ratio"],
                "conflict_hit_rate": report["conflict_hit_rate"],
            }
        except Exception:
            response["graph_boost"] = {"enabled": False, "skipped_stages": [], "speedup_ratio": 0.0}
    else:
        response["graph_boost"] = {"enabled": False, "skipped_stages": [], "speedup_ratio": 0.0}

    return response


def run_disc_workflow(transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True) -> dict:
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=load_disc_knowledge(),
    )
    disc_prompt = load_disc_prompt()

    for stage in (
        run_parse_stage,
        run_feature_stage,
        run_star_stage,
        run_disc_evidence_stage,
        run_masking_stage,
        run_disc_stage,
        run_decision_stage,
    ):
        context = stage(context)

    context = run_llm_stage(context, disc_prompt=disc_prompt)
    return build_response(context, apply_knowledge_graph=apply_knowledge_graph)


# ─── 并行人格分析工作流 ───────────────────────────────────────────


def _run_disc_chain(context: WorkflowContext, disc_knowledge, disc_prompt: str) -> WorkflowContext:
    """DISC 分析链（必须顺序）。"""
    context.knowledge = disc_knowledge
    context.disc_evidence = {}
    try:
        context = run_star_stage(context)
    except Exception:
        context.star_result = None
    for stage in (
        run_disc_evidence_stage,
        run_masking_stage,
        run_disc_stage,
        run_decision_stage,
    ):
        context = stage(context)
    return context


def _run_llm_personality_stage(
    context: WorkflowContext, bigfive_prompt: str, enneagram_prompt: str
) -> WorkflowContext:
    context.mark_stage("llm_personality_stage", "started", "Run optional LLM Big Five and Enneagram analysis")
    try:
        bf_msgs = build_bigfive_messages(
            prompt=bigfive_prompt,
            transcript=context.transcript,
            turns=context.detailed_turns,
            features=context.features,
            job_inference=context.job_inference,
            local_bigfive=context.bigfive_result,
        )
        context.llm_bigfive_output = call_openai_compatible(OPENAI_PERSONALITY_MODEL, bf_msgs)
        context.mark_stage("llm_personality_stage", "completed", "LLM Big Five analysis done")
    except Exception as exc:
        context.mark_stage("llm_personality_stage", "failed", str(exc))

    try:
        en_msgs = build_enneagram_messages(
            prompt=enneagram_prompt,
            transcript=context.transcript,
            turns=context.detailed_turns,
            features=context.features,
            job_inference=context.job_inference,
            local_enneagram=context.enneagram_result,
        )
        context.llm_enneagram_output = call_openai_compatible(OPENAI_PERSONALITY_MODEL, en_msgs)
        context.mark_stage("llm_personality_stage", "completed", "LLM Enneagram analysis done")
    except Exception as exc:
        context.mark_stage("llm_personality_stage", "failed", str(exc))

    return context


def _parallel_personality_stage(context: WorkflowContext, bigfive_knowledge, enneagram_knowledge) -> WorkflowContext:
    """
    并行运行 BigFive、Enneagram、MBTI 三个本地规则阶段。
    三个阶段互相独立（只依赖 feature_stage 的输出），
    并行执行可节省约 2/3 的规则阶段时间。
    """
    # 闭包捕获 context 引用，分别提交到线程池
    def do_bigfive() -> None:
        context.knowledge = bigfive_knowledge
        run_bigfive_stage(context)

    def do_enneagram() -> None:
        context.knowledge = enneagram_knowledge
        run_enneagram_stage(context)

    def do_mbti() -> None:
        try:
            run_mbti_stage(context)
        except Exception as e:
            print(f"[MBTI] 阶段异常: {e}")
            context.mbti_result = None
            context.mark_stage("mbti_stage", "failed", str(e))

    with ThreadPoolExecutor(max_workers=3) as pool:
        pool.submit(do_bigfive)
        pool.submit(do_enneagram)
        pool.submit(do_mbti)
        # result() 等待所有线程完成后再继续
        pool.shutdown(wait=True)

    return context


def run_personality_workflow(
    transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True
) -> dict:
    """
    完整人格分析工作流：DISC + BigFive + 九型 + 跨模型映射。

    性能优化（v0.4）：
    - BigFive / Enneagram / MBTI 三个本地规则阶段并行运行
    - llm_stage / llm_personality_stage 两个 LLM 阶段并行运行
    - 约节省 10-15 秒（取决于网络延迟）
    """
    disc_knowledge = load_disc_knowledge()
    bigfive_knowledge = load_bigfive_knowledge()
    enneagram_knowledge = load_enneagram_knowledge()
    disc_prompt = load_disc_prompt()
    bigfive_prompt = load_bigfive_prompt()
    enneagram_prompt = load_enneagram_prompt()

    # ── 阶段一：必须顺序（parse → feature） ─────────────────────
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=disc_knowledge,
    )
    for stage in (run_parse_stage, run_feature_stage):
        context = stage(context)

    # ── 阶段二：DISC 分析链（必须顺序）─────────────────────────
    context = _run_disc_chain(context, disc_knowledge, disc_prompt)

    # ── 阶段三：三个本地人格阶段并行 ───────────────────────────
    context = _parallel_personality_stage(context, bigfive_knowledge, enneagram_knowledge)

    # ── 阶段四：跨模型人格映射（需要三个本地结果）──────────────
    context = run_personality_mapping_stage(context)

    # ── 阶段五：两个 LLM 阶段并行 ──────────────────────────────
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_disc = pool.submit(run_llm_stage, context, disc_prompt)
        f_llm = pool.submit(_run_llm_personality_stage, context, bigfive_prompt, enneagram_prompt)
        # 等待两个都完成后再返回
        context = f_disc.result()
        context = f_llm.result()

    return build_response(context, apply_knowledge_graph=apply_knowledge_graph)
