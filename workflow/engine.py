from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
<<<<<<< Updated upstream
<<<<<<< Updated upstream
from functools import lru_cache
=======
>>>>>>> Stashed changes
=======
from functools import lru_cache
>>>>>>> Stashed changes

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
<<<<<<< Updated upstream
<<<<<<< Updated upstream
=======
    load_mbti_knowledge,
>>>>>>> Stashed changes
=======
    load_mbti_knowledge,
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    star = context.star_result
=======
    star = getattr(context, "star_result", None)
>>>>>>> Stashed changes
=======
    star = getattr(context, "star_result", None)
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
<<<<<<< Updated upstream
        "bigfive_analysis": context.bigfive_result,
        "enneagram_analysis": context.enneagram_result,
        "mbti_analysis": context.mbti_result,
        "personality_mapping": context.personality_mapping_result,
        "llm_analysis": context.analysis_output,
        "llm_bigfive_analysis": context.llm_bigfive_output,
        "llm_enneagram_analysis": context.llm_enneagram_output,
=======
        "bigfive_analysis": getattr(context, "bigfive_result", None) or getattr(context, "bigfive_analysis", None),
        "enneagram_analysis": getattr(context, "enneagram_result", None) or getattr(context, "enneagram_analysis", None),
        "mbti_analysis": getattr(context, "mbti_result", None) or getattr(context, "mbti_analysis", None),
        "personality_mapping": getattr(context, "personality_mapping_result", None),
        "llm_analysis": context.analysis_output,
        "llm_bigfive_analysis": getattr(context, "llm_bigfive_output", None),
        "llm_enneagram_analysis": getattr(context, "llm_enneagram_output", None),
>>>>>>> Stashed changes
=======
        "bigfive_analysis": getattr(context, "bigfive_result", None) or getattr(context, "bigfive_analysis", None),
        "enneagram_analysis": getattr(context, "enneagram_result", None) or getattr(context, "enneagram_analysis", None),
        "mbti_analysis": getattr(context, "mbti_result", None) or getattr(context, "mbti_analysis", None),
        "personality_mapping": getattr(context, "personality_mapping_result", None),
        "llm_analysis": context.analysis_output,
        "llm_bigfive_analysis": getattr(context, "llm_bigfive_output", None),
        "llm_enneagram_analysis": getattr(context, "llm_enneagram_output", None),
>>>>>>> Stashed changes
        "llm_status": {
            "enabled": context.llm_called,  # 真实反映 LLM 是否被调用，而非仅检查 API key 是否配置
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
<<<<<<< Updated upstream
<<<<<<< Updated upstream
            if context.mbti_result and isinstance(context.mbti_result, dict):
=======
            mbti_result = response["mbti_analysis"]
            if mbti_result and isinstance(mbti_result, dict):
>>>>>>> Stashed changes
=======
            mbti_result = response["mbti_analysis"]
            if mbti_result and isinstance(mbti_result, dict):
>>>>>>> Stashed changes
                disc_scores: dict[str, float] = {}
                if context.disc_analysis and isinstance(context.disc_analysis, dict):
                    raw = context.disc_analysis.get("scores", {})
                    disc_scores = {k: float(v or 0) for k, v in raw.items()}

                bigfive_scores: dict[str, float] | None = None
<<<<<<< Updated upstream
<<<<<<< Updated upstream
                if context.bigfive_result and isinstance(context.bigfive_result, dict):
                    bf_raw = context.bigfive_result.get("scores", {})
                    bigfive_scores = {k: float(v or 0) for k, v in bf_raw.items()}

                mbti_dims = context.mbti_result.get("dimensions") or {}
=======
=======
>>>>>>> Stashed changes
                bf_result = response.get("bigfive_analysis")
                if bf_result and isinstance(bf_result, dict):
                    bf_raw = bf_result.get("scores", {})
                    bigfive_scores = {k: float(v or 0) for k, v in bf_raw.items()}

                mbti_dims = mbti_result.get("dimensions") or {}
<<<<<<< Updated upstream
>>>>>>> Stashed changes
=======
>>>>>>> Stashed changes
                graph_conflicts = graph.get_conflicts(
                    disc_scores, mbti_dims, bigfive_scores
                )
                if graph_conflicts:
<<<<<<< Updated upstream
<<<<<<< Updated upstream
                    existing = response["mbti_analysis"].get("conflicts") or []
=======
                    existing = mbti_result.get("conflicts") or []
>>>>>>> Stashed changes
                    # 图谱冲突去重合并
=======
                    existing = mbti_result.get("conflicts") or []
>>>>>>> Stashed changes
                    seen_keys = {c["type"] + c["description"][:20] for c in existing}
                    for c in graph_conflicts:
                        key = c["type"] + c["description"][:20]
                        if key not in seen_keys:
                            existing.append(c)
<<<<<<< Updated upstream
<<<<<<< Updated upstream
                    response["mbti_analysis"]["conflicts"] = existing[:6]

            # ② 图谱加速效果报告（供前端计时器旁的图谱指示器）
=======
                    mbti_result["conflicts"] = existing[:6]

            # ② 图谱加速效果报告
>>>>>>> Stashed changes
=======
                    mbti_result["conflicts"] = existing[:6]

            # ② 图谱加速效果报告
>>>>>>> Stashed changes
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


<<<<<<< Updated upstream
<<<<<<< Updated upstream
def run_disc_workflow(transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True) -> dict:
=======
# ─── 原有 DISC 工作流（main 分支逻辑，保持完全不变）──────────────────────────
=======
# ─── 原有 DISC 工作流（快速模式）──────────────────────────────
>>>>>>> Stashed changes


def run_disc_workflow(transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True) -> dict:
    """
<<<<<<< Updated upstream
    原有 DISC 分析工作流（main 分支逻辑）。
    与 run_personality_workflow 完全独立，互不影响。
    """
>>>>>>> Stashed changes
=======
    快速 DISC 分析工作流（原有逻辑）。
    与 run_personality_workflow 完全独立，互不影响。
    """
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
=======

>>>>>>> Stashed changes


<<<<<<< Updated upstream
# ─── 并行人格分析工作流 ───────────────────────────────────────────
=======
# ─── 并行人格分析工作流（ywj 分支新增）───────────────────────────────────────
>>>>>>> Stashed changes


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
<<<<<<< Updated upstream
=======
    context.local_disc_result = context.disc_analysis
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
            local_bigfive=context.bigfive_result,
=======
            local_bigfive=getattr(context, "bigfive_result", None),
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
            local_enneagram=context.enneagram_result,
=======
            local_enneagram=getattr(context, "enneagram_result", None),
>>>>>>> Stashed changes
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
<<<<<<< Updated upstream
<<<<<<< Updated upstream
    # 闭包捕获 context 引用，分别提交到线程池
=======
>>>>>>> Stashed changes
    def do_bigfive() -> None:
        context.knowledge = bigfive_knowledge
        run_bigfive_stage(context)

    def do_enneagram() -> None:
        context.knowledge = enneagram_knowledge
        run_enneagram_stage(context)

    def do_mbti() -> None:
        try:
<<<<<<< Updated upstream
=======
            context.mbti_knowledge = load_mbti_knowledge()
>>>>>>> Stashed changes
            run_mbti_stage(context)
        except Exception as e:
            print(f"[MBTI] 阶段异常: {e}")
            context.mbti_result = None
            context.mark_stage("mbti_stage", "failed", str(e))

    with ThreadPoolExecutor(max_workers=3) as pool:
        pool.submit(do_bigfive)
        pool.submit(do_enneagram)
        pool.submit(do_mbti)
<<<<<<< Updated upstream
        # result() 等待所有线程完成后再继续
=======
>>>>>>> Stashed changes
        pool.shutdown(wait=True)

    return context


def run_personality_workflow(
    transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True
) -> dict:
    """
<<<<<<< Updated upstream
    完整人格分析工作流：DISC + BigFive + 九型 + 跨模型映射。

    性能优化（v0.4）：
    - BigFive / Enneagram / MBTI 三个本地规则阶段并行运行
    - llm_stage / llm_personality_stage 两个 LLM 阶段并行运行
    - 约节省 10-15 秒（取决于网络延迟）
=======
    完整人格分析工作流：DISC + BigFive + 九型 + MBTI + 跨模型映射。
    新增功能入口，不影响原有 run_disc_workflow。
>>>>>>> Stashed changes
    """
    disc_knowledge = load_disc_knowledge()
    bigfive_knowledge = load_bigfive_knowledge()
    enneagram_knowledge = load_enneagram_knowledge()
    disc_prompt = load_disc_prompt()
    bigfive_prompt = load_bigfive_prompt()
    enneagram_prompt = load_enneagram_prompt()

<<<<<<< Updated upstream
    # ── 阶段一：必须顺序（parse → feature） ─────────────────────
=======
    # ── 阶段一：必须顺序（parse → feature）
>>>>>>> Stashed changes
=======
    import app.config as config
    import time

>>>>>>> Stashed changes
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=disc_knowledge,
    )
    for stage in (run_parse_stage, run_feature_stage):
        context = stage(context)

<<<<<<< Updated upstream
<<<<<<< Updated upstream
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
=======
    # ── 阶段二：DISC 分析链（必须顺序）
    context = _run_disc_chain(context, disc_knowledge, disc_prompt)

    # ── 阶段三：三个本地人格阶段并行
    context = _parallel_personality_stage(context, bigfive_knowledge, enneagram_knowledge)

    # ── 阶段四：跨模型人格映射（需要三个本地结果）
    context = run_personality_mapping_stage(context)

    # ── 阶段五：两个 LLM 阶段并行
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_disc = pool.submit(run_llm_stage, context, disc_prompt)
        f_llm = pool.submit(_run_llm_personality_stage, context, bigfive_prompt, enneagram_prompt)
>>>>>>> Stashed changes
        context = f_disc.result()
        context = f_llm.result()

    return build_response(context, apply_knowledge_graph=apply_knowledge_graph)
=======
    # 临时禁用所有 LLM 调用
    original_api_key = config.OPENAI_API_KEY
    original_parser_model = config.OPENAI_PARSER_MODEL
    original_analysis_model = config.OPENAI_ANALYSIS_MODEL

    try:
        config.OPENAI_API_KEY = None
        config.OPENAI_PARSER_MODEL = None
        config.OPENAI_ANALYSIS_MODEL = None

        stages = [
            ("parse", run_parse_stage),
            ("feature", run_feature_stage),
            ("star", run_star_stage),
            ("disc_evidence", run_disc_evidence_stage),
            ("mbti", run_mbti_stage),
            ("masking", run_masking_stage),
            ("decision", run_decision_stage),
        ]

        for stage_name, stage_func in stages:
            start = time.time()
            context = stage_func(context)
            elapsed = time.time() - start
            print(f"  {stage_name}_stage: {elapsed:.2f}s")

    finally:
        config.OPENAI_API_KEY = original_api_key
        config.OPENAI_PARSER_MODEL = original_parser_model
        config.OPENAI_ANALYSIS_MODEL = original_analysis_model

    return build_response(context)


# ─── 并行人格分析工作流（完整模式）──────────────────────────────


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
    context.local_disc_result = context.disc_analysis
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
            local_bigfive=getattr(context, "bigfive_result", None),
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
            local_enneagram=getattr(context, "enneagram_result", None),
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
    def do_bigfive() -> None:
        context.knowledge = bigfive_knowledge
        run_bigfive_stage(context)

    def do_enneagram() -> None:
        context.knowledge = enneagram_knowledge
        run_enneagram_stage(context)

    def do_mbti() -> None:
        try:
            context.mbti_knowledge = load_mbti_knowledge()
            run_mbti_stage(context)
        except Exception as e:
            print(f"[MBTI] 阶段异常: {e}")
            context.mbti_result = None
            context.mark_stage("mbti_stage", "failed", str(e))

    with ThreadPoolExecutor(max_workers=3) as pool:
        pool.submit(do_bigfive)
        pool.submit(do_enneagram)
        pool.submit(do_mbti)
        pool.shutdown(wait=True)

    return context


def run_personality_workflow(
    transcript: str, job_hint: str = "", *, apply_knowledge_graph: bool = True
) -> dict:
    """
    完整人格分析工作流：DISC + BigFive + 九型 + MBTI + 跨模型映射。

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

    # ── 阶段一：必须顺序（parse → feature）
    context = WorkflowContext(
        transcript=transcript,
        job_hint=job_hint,
        knowledge=disc_knowledge,
    )
    for stage in (run_parse_stage, run_feature_stage):
        context = stage(context)

    # ── 阶段二：DISC 分析链（必须顺序）
    context = _run_disc_chain(context, disc_knowledge, disc_prompt)

    # ── 阶段三：三个本地人格阶段并行
    context = _parallel_personality_stage(context, bigfive_knowledge, enneagram_knowledge)

    # ── 阶段四：跨模型人格映射（需要三个本地结果）
    context = run_personality_mapping_stage(context)

    # ── 阶段五：两个 LLM 阶段并行
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_disc = pool.submit(run_llm_stage, context, disc_prompt)
        f_llm = pool.submit(_run_llm_personality_stage, context, bigfive_prompt, enneagram_prompt)
        context = f_disc.result()
        context = f_llm.result()

    return build_response(context, apply_knowledge_graph=apply_knowledge_graph)


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
    if char_count < 500:
        reasons.append(f"样本字数不足（{char_count} < 500字）")

    # 2. DISC 主导维度不明显（阈值从 60 降至 55）
    disc_analysis = local_result.get("disc_analysis") or {}
    disc_scores = disc_analysis.get("scores") or {}
    if disc_scores:
        try:
            max_score = max(disc_scores.values()) if disc_scores.values() else 0
            if max_score < 55:
                reasons.append(f"DISC 无明显主导维度（最高分 {max_score}）")
        except (ValueError, TypeError):
            pass

    # 3. MBTI 维度为中性（任意一个即触发，降低门槛）
    mbti_analysis = local_result.get("mbti_analysis") or {}
    mbti_dims = mbti_analysis.get("dimensions") or {}
    neutral_count = 0
    if isinstance(mbti_dims, dict):
        for dim_data in mbti_dims.values():
            if isinstance(dim_data, dict) and dim_data.get("preference") == "neutral":
                neutral_count += 1

    if neutral_count >= 1:
        reasons.append(f"MBTI 有 {neutral_count} 个维度为中性，信号不足")

    # 4. 检测到中/高严重度冲突（从 high 降至 medium）
    conflicts = mbti_analysis.get("conflicts") or []
    significant_conflicts = []
    if isinstance(conflicts, list):
        significant_conflicts = [
            c for c in conflicts
            if isinstance(c, dict) and c.get("severity") in ("high", "medium")
        ]

    if significant_conflicts:
        reasons.append(f"检测到 {len(significant_conflicts)} 个维度冲突，需深度验证")

    # 5. 包装风险为中/高（从仅"高"扩展至"中"）
    disc_meta = disc_analysis.get("meta") or {}
    risk = disc_meta.get("impression_management_risk", "")
    risk_str = str(risk).lower()
    if any(kw in risk_str for kw in ["高", "中", "high", "medium"]):
        reasons.append(f"包装风险 {risk}，需 LLM 深度解析")

    # 6. DISC 置信度低（meta 中置信度不足）
    disc_confidence = disc_meta.get("confidence", "medium").lower()
    if disc_confidence in ("low", "medium"):
        reasons.append(f"DISC 分析置信度为 {disc_confidence}，建议深度验证")

    # 7. STAR 存在缺陷
    star_analysis = local_result.get("star_analysis") or {}
    star_defects = star_analysis.get("defects") or []
    if star_defects:
        reasons.append(f"STAR 存在 {len(star_defects)} 项缺陷，真实性存疑")

    # 8. 问答轮次过少
    turn_count = input_overview.get("turn_count", 0)
    if turn_count < 5:
        reasons.append(f"问答轮次偏少（{turn_count} < 5轮）")

    if reasons:
        return True, " | ".join(reasons)
    else:
        return False, "本地规则置信度充足，无需 LLM 深度分析"


def run_llm_only(context: WorkflowContext, disc_prompt: str) -> WorkflowContext:
    """仅运行 LLM 阶段（基于已有的 context）"""
    context = run_llm_stage(context, disc_prompt=disc_prompt)
    return context
>>>>>>> Stashed changes
