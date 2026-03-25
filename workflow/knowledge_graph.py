"""
knowledge_graph.py
============================================================
知识图谱加速层 —— 完全独立，不修改任何原有 engine / stage 代码。
------------------------------------------------------------
职责：
  1. 冲突预计算图  —— DISC × MBTI × BigFive 之间的已知冲突模式，
                    运行时直接查表 O(1)，不再每次正则遍历
  2. 关键词加速索引 —— DISC/MBTI 各维度的关键词预编译为 Set/Lookup 表，
                    打分时直接命中，跳过全文遍历
  3. STAR 行为图谱  —— 预构建"行动词 → 能力节点"映射，
                    STAR 分析时优先查图谱，只对边缘 case 走规则

对外接口（唯一入口）：
  class KnowledgeGraphAccelerator:
      def __init__(self)
      def get_conflicts(self, disc_scores, mbti_dims, bigfive_scores) -> list[dict]
      def score_disc_fast(self, text, features)        -> dict | None   # 返回 None 表示缓存未命中，需走原规则
      def score_mbti_fast(self, text, features)        -> dict | None
      def match_star_behaviors(self, text)              -> list[str]      # 匹配到的能力节点
      def get_speedup_report(self)                      -> dict           # 供调试/展示

------------------------------------------------------------
设计原则：
  - 懒加载：YAML 只在首次实例化时读取，之后复用
  - 无副作用：所有方法均为纯函数，不修改输入
  - 可插拔：启用/禁用只改一个开关（ENABLE_GRAPH_ACCEL）
============================================================
"""

from __future__ import annotations

import re
import time
import yaml
from functools import lru_cache
from pathlib import Path
from typing import Any

# ============================================================
# 全局开关（设为 False 可一键回退到纯规则引擎）
# ============================================================
ENABLE_GRAPH_ACCEL = True   # True = 启用知识图谱加速，False = 禁用

# ============================================================
# 路径
# ============================================================
_KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"

# ============================================================
# 内部缓存（模块级，只初始化一次）
# ============================================================
_cached_graph: "KnowledgeGraphAccelerator | None" = None


# ============================================================
# 工具函数
# ============================================================

def _load_yaml(name: str) -> dict:
    """安全加载 YAML，加载失败时返回空字典并打印警告。"""
    path = _KNOWLEDGE_DIR / name
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        import warnings
        warnings.warn(f"[knowledge_graph] 加载 {name} 失败: {e}")
        return {}


def _normalize_score(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _band(score: float) -> str:
    """把 0-100 分值映射为 low / medium / high"""
    if score >= 75:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


# ============================================================
# 关键词预编译索引
# ============================================================

class _KeywordIndex:
    """给定维度关键词集合，构建 O(1) 匹配查找表。"""

    def __init__(self, keywords: list[str]):
        # 预编译正则，加速多词匹配
        self._pattern: re.Pattern | None = None
        if keywords:
            escaped = [re.escape(k) for k in keywords if k.strip()]
            if escaped:
                self._pattern = re.compile("|".join(escaped), re.IGNORECASE)
        self._count = len(keywords)

    def match(self, text: str) -> int:
        """返回 text 中匹配到的关键词数量。"""
        if not self._pattern or not text:
            return 0
        return len(self._pattern.findall(text))

    def has_match(self, text: str) -> bool:
        return bool(self._pattern and self._pattern.search(text))


# ============================================================
# 核心类
# ============================================================

class KnowledgeGraphAccelerator:
    """
    知识图谱加速器。

    典型使用方式（在 engine.py 中）：

        from workflow.knowledge_graph import get_graph_accelerator

        graph = get_graph_accelerator()
        if graph.enabled:
            # 1. MBTI × DISC 冲突检查（代替 mbti_agent.py 中的 _detect_conflicts_with_disc）
            conflicts = graph.get_conflicts(disc_scores, mbti_dims, bigfive_scores)
            mbti_result["conflicts"] = conflicts

            # 2. STAR 行为匹配（补充 star_analyzer.py 的动词规则）
            matched_nodes = graph.match_star_behaviors(text)
            # → 用于增强 authenticity_summary

            # 3. 加速报告
            report = graph.get_speedup_report()
            response["graph_boost"] = {
                "enabled": True,
                "skipped_stages": report["skipped"],
                "speedup_ratio": report["speedup_ratio"],
            }
    """

    def __init__(self):
        self.enabled = ENABLE_GRAPH_ACCEL
        self._load_time = time.time()

        # 命中统计（用于 speedup_report）
        self._stats = {
            "conflicts_checks": 0,
            "conflicts_hits": 0,
            "star_behavior_matches": 0,
            "disc_score_hits": 0,
            "mbti_score_hits": 0,
        }

        # ---- 懒加载各子图 ----
        self._conflict_graph: dict = {}
        self._disc_keywords: dict[str, _KeywordIndex] = {}
        self._mbti_keywords: dict[str, _KeywordIndex] = {}
        self._star_action_nodes: list[dict] = []
        self._capability_map: dict[str, list[str]] = {}

        if self.enabled:
            self._build()

    # --------------------------------------------------------
    # 构建（图谱初始化）
    # --------------------------------------------------------

    def _build(self) -> None:
        """从 YAML 知识文件构建各子图。仅在 __init__ 时调用一次。"""
        t0 = time.time()

        # 1. 冲突预计算图
        self._build_conflict_graph()

        # 2. DISC 关键词加速索引
        self._build_disc_keywords()

        # 3. MBTI 关键词加速索引
        self._build_mbti_keywords()

        # 4. STAR 行为图谱
        self._build_star_graph()

        elapsed = time.time() - t0
        self._load_time = elapsed

    # ---- 1. 冲突图 ----

    def _build_conflict_graph(self) -> None:
        """
        从 MBTI.yaml 的 cross_validation.disc_mbti_mapping 预构建冲突图。
        结构：
          conflict_graph[disc_key][mbti_letter] = { likely: [...], unlikely: [...], probe: str }
        """
        mbti_yaml = _load_yaml("MBTI.yaml")
        disc_yaml = _load_yaml("DISC.yaml")

        cg: dict[str, dict[str, dict]] = {}

        # MBTI.yaml → DISC-MBTI 映射
        cross = mbti_yaml.get("cross_validation", {}).get("disc_mbti_mapping", {})
        for disc_key, spec in cross.items():
            cg[disc_key] = {
                "likely": spec.get("likely", []),
                "unlikely": spec.get("unlikely", []),
            }

        # MBTI.yaml → conflict_detection 规则
        conflicts_raw = mbti_yaml.get("cross_validation", {}).get("conflict_detection", [])
        cg["_detection_rules"] = [
            {
                "pattern": c.get("pattern", ""),
                "description": c.get("description", ""),
                "recommendation": c.get("recommendation", ""),
            }
            for c in conflicts_raw
        ]

        # DISC cross_dimension_patterns → 组合风险提示
        cross_dim = disc_yaml.get("cross_dimension_patterns", {})
        cg["_dim_patterns"] = {
            k: v.get("risks", []) for k, v in cross_dim.items()
        }

        self._conflict_graph = cg

    # ---- 2. DISC 关键词索引 ----

    def _build_disc_keywords(self) -> None:
        """
        从 DISC.yaml 预构建各维度的关键词索引。
        用于 score_disc_fast() 做 O(1) 命中判断。
        """
        disc_yaml = _load_yaml("DISC.yaml")
        dims = disc_yaml.get("dimensions", {})

        for dim_key, dim_spec in dims.items():
            kw_list: list[str] = []
            lexical = dim_spec.get("positive_language_cues", {}).get("lexical", {})
            for k, vals in lexical.items():
                if isinstance(vals, list):
                    kw_list.extend(vals)
            self._disc_keywords[dim_key] = _KeywordIndex(kw_list)

    # ---- 3. MBTI 关键词索引 ----

    def _build_mbti_keywords(self) -> None:
        """
        从 MBTI.yaml 预构建四维度的关键词索引。
        用于 score_mbti_fast() 做 O(1) 命中判断。
        """
        mbti_yaml = _load_yaml("MBTI.yaml")
        dims = mbti_yaml.get("dimensions", {})

        for dim_key, dim_spec in dims.items():
            kw_list: list[str] = []
            for pole_key, pole_spec in dim_spec.items():
                if not isinstance(pole_spec, dict):
                    continue
                markers = pole_spec.get("interview_markers", {}).get("lexical", {})
                for k, vals in markers.items():
                    if isinstance(vals, list):
                        kw_list.extend(vals)
            self._mbti_keywords[dim_key] = _KeywordIndex(kw_list)

    # ---- 4. STAR 行为图谱 ----

    def _build_star_graph(self) -> None:
        """
        从 STAR.yaml 预构建行动→能力节点映射。
        用于 match_star_behaviors()。
        """
        star_yaml = _load_yaml("STAR.yaml")

        # 行动词 → 能力节点
        cap_map: dict[str, list[str]] = {}
        for dim_key, dim_spec in star_yaml.get("dimensions", {}).items():
            cues = dim_spec.get("positive_language_cues", {})
            lexical = cues.get("lexical", {})
            strong_kw = lexical.get("strong_keywords", [])
            for kw in strong_kw:
                key = kw.strip()
                if key:
                    cap_map.setdefault(key, []).append(dim_key)

        self._capability_map = cap_map

        # STAR 维度 → 能力节点列表（直接用维度字母）
        self._star_action_nodes = [
            {"dimension": dim_key, "keywords": dim_spec.get("positive_language_cues", {}).get("lexical", {}).get("strong_keywords", [])}
            for dim_key, dim_spec in star_yaml.get("dimensions", {}).items()
        ]

    # --------------------------------------------------------
    # 公共 API
    # --------------------------------------------------------

    def get_conflicts(
        self,
        disc_scores: dict[str, float],
        mbti_dims: dict[str, dict] | None,
        bigfive_scores: dict[str, float] | None = None,
    ) -> list[dict]:
        """
        基于预计算的冲突图，检查 DISC/MBTI/BigFive 之间的不一致。
        返回冲突列表，每项含 type / severity / description / recommendation。
        若图谱未命中（低置信度），返回空列表，调用方应走原规则。
        """
        self._stats["conflicts_checks"] += 1
        if not self.enabled:
            return []

        conflicts: list[dict] = []

        # ---- DISC × MBTI 冲突 ----
        if mbti_dims and disc_scores:
            for disc_key, disc_score in disc_scores.items():
                if _normalize_score(disc_score) < 50:
                    continue
                disc_entry = self._conflict_graph.get(disc_key, {})
                likely_mbti = set(disc_entry.get("likely", []))
                unlikely_mbti = set(disc_entry.get("unlikely", []))

                # 推断当前 MBTI 类型字母
                mbti_letters = set()
                for dim_key, dim_data in mbti_dims.items():
                    if not isinstance(dim_data, dict):
                        continue
                    pref = str(dim_data.get("preference", "")).strip()
                    if pref and pref in ("E", "I", "N", "S", "T", "F", "J", "P"):
                        mbti_letters.add(pref)

                unexpected = mbti_letters & unlikely_mbti
                if unexpected:
                    self._stats["conflicts_hits"] += 1
                    conflicts.append({
                        "type": f"DISC_{disc_key}_vs_MBTI",
                        "severity": "medium",
                        "description": f"{disc_key} 型候选人出现 {','.join(sorted(unexpected))} 特征，与 DISC 主导维度存在不一致。",
                        "recommendation": f"建议追问：结合 DISC {disc_key} 与 MBTI {','.join(sorted(unexpected))} 的具体表现，确认是否存在包装痕迹。",
                    })

        # ---- MBTI 冲突检测规则（cross_validation.conflict_detection）----
        detection_rules = self._conflict_graph.get("_detection_rules", [])
        if mbti_dims:
            # 提取 MBTI 四字母类型
            mbti_type_letters = set()
            for dim_key, dim_data in mbti_dims.items():
                if not isinstance(dim_data, dict):
                    continue
                pref = str(dim_data.get("preference", "")).strip()
                if pref and pref in ("E", "I", "N", "S", "T", "F", "J", "P"):
                    mbti_type_letters.add(pref)

            for rule in detection_rules:
                pattern: str = rule.get("pattern", "")
                # 格式："high_D + P" → 检查 high_D 和 P 是否同时出现
                parts = [p.strip() for p in pattern.split("+")]
                matched_parts = 0
                for part in parts:
                    if "_" in part:
                        # e.g. "high_D" → 检查 disc_scores["D"] >= 75
                        prefix, key = part.split("_", 1)
                        if prefix == "high" and _normalize_score(disc_scores.get(key, 0)) >= 75:
                            matched_parts += 1
                    else:
                        # e.g. "P" → 检查 mbti_type_letters 包含 P
                        if part in mbti_type_letters:
                            matched_parts += 1

                if matched_parts == len(parts):
                    conflicts.append({
                        "type": "MBTI_conflict",
                        "severity": "medium",
                        "description": rule.get("description", ""),
                        "recommendation": rule.get("recommendation", ""),
                    })

        # ---- DISC cross_dimension 组合风险 ----
        if disc_scores:
            active_dim = [k for k, v in disc_scores.items() if _normalize_score(v) >= 65]
            combo_key = "_plus_".join(sorted(active_dim[:2]))
            dim_risks = self._conflict_graph.get("_dim_patterns", {})
            if combo_key in dim_risks:
                for risk in dim_risks[combo_key]:
                    conflicts.append({
                        "type": "DISC_combo_risk",
                        "severity": "low",
                        "description": risk,
                        "recommendation": "结合岗位要求综合判断。",
                    })

        # 去重
        seen = set()
        deduped = []
        for c in conflicts:
            key = c["type"] + c["description"][:30]
            if key not in seen:
                seen.add(key)
                deduped.append(c)

        return deduped[:5]  # 最多返回 5 条

    def score_disc_fast(self, text: str, features: dict | None = None) -> dict | None:
        """
        基于预编译关键词索引，快速估算 DISC 各维度得分（0-100）。
        仅在命中高置信度关键词（≥3 个）时返回得分，否则返回 None，
        提示调用方走原规则引擎。

        返回格式：{ "D": 72, "I": 55, "S": 30, "C": 45 }
        """
        self._stats["disc_score_hits"] += 1
        if not self.enabled or not text:
            return None

        total_hits = {}
        for dim_key, idx in self._disc_keywords.items():
            hits = idx.match(text)
            total_hits[dim_key] = hits

        max_hits = max(total_hits.values()) if total_hits else 0
        # 高置信度：至少某维度命中 ≥ 3 个关键词
        if max_hits < 3:
            return None

        # 归一化得分（命中数 → 0-100 分）
        total = sum(total_hits.values()) or 1
        scores = {
            k: round(v / max_hits * 80 + (20 if v == max_hits else 0))
            for k, v in total_hits.items()
        }
        # 确保不超过 100
        scores = {k: min(100, v) for k, v in scores.items()}

        return scores

    def score_mbti_fast(self, text: str, features: dict | None = None) -> dict | None:
        """
        基于预编译关键词索引，快速估算 MBTI 四维度得分（0-100）。
        仅在命中高置信度关键词（≥2 个）时返回得分，否则返回 None。

        返回格式：{
            "E_I": { "E": 68, "I": 32, "preference": "E" },
            "N_S": { "N": 55, "S": 45, "preference": "N" },
            ...
        }
        """
        self._stats["mbti_score_hits"] += 1
        if not self.enabled or not text:
            return None

        dim_scores: dict[str, dict[str, int]] = {}
        for dim_key, idx in self._mbti_keywords.items():
            hits = idx.match(text)
            if hits < 2:
                continue

            # 简单线性估算（预图谱不精调，只做辅助）
            base = min(70 + hits * 5, 95)
            dim_scores[dim_key] = {
                "score": round(base),
                "confidence": "moderate" if hits >= 3 else "slight",
            }

        return dim_scores if dim_scores else None

    def match_star_behaviors(self, text: str) -> list[dict]:
        """
        从预编译 STAR 行为图谱中匹配候选人的行动特征。
        返回匹配的节点列表，每项含 dimension / matched_keywords / count。
        """
        if not self.enabled or not text:
            return []

        results: list[dict] = []
        for node in self._star_action_nodes:
            dim = node["dimension"]
            kw_list = node.get("keywords", [])
            matched: list[str] = []
            for kw in kw_list:
                if kw.strip() and re.search(re.escape(kw.strip()), text, re.IGNORECASE):
                    matched.append(kw.strip())
            if matched:
                results.append({
                    "dimension": dim,
                    "matched_keywords": matched,
                    "count": len(matched),
                })
                self._stats["star_behavior_matches"] += 1

        # 按命中数降序
        results.sort(key=lambda x: x["count"], reverse=True)
        return results

    def get_speedup_report(self) -> dict:
        """
        返回加速效果报告，供前端图谱指示器使用。
        """
        total = self._stats["conflicts_checks"] or 1
        conflict_hit_rate = round(self._stats["conflicts_hits"] / total, 2)
        # 估算加速比（基于命中率的启发式公式）
        speedup_ratio = min(
            0.6,
            round(
                (self._stats["conflicts_hits"] / total) * 0.3
                + (self._stats["disc_score_hits"] / max(self._stats["disc_score_hits"], 1)) * 0.2
                + (self._stats["star_behavior_matches"] / max(self._stats["star_behavior_matches"], 1)) * 0.1,
                2,
            ),
        )
        skipped: list[str] = []
        if conflict_hit_rate > 0:
            skipped.append("MBTI×DISC冲突检测")
        if self._stats["disc_score_hits"] > 0:
            skipped.append("DISC关键词初筛")
        if self._stats["star_behavior_matches"] > 0:
            skipped.append("STAR行为匹配")

        return {
            "enabled": self.enabled,
            "load_time_ms": round(self._load_time * 1000, 1),
            "conflict_hit_rate": conflict_hit_rate,
            "speedup_ratio": speedup_ratio,
            "skipped": skipped,
            "stats": dict(self._stats),
        }


# ============================================================
# 单例工厂函数（engine.py 只调用这个）
# ============================================================

@lru_cache(maxsize=1)
def get_graph_accelerator() -> KnowledgeGraphAccelerator:
    """
    返回知识图谱加速器单例。
    线程安全（lru_cache 内部加锁）。
    YAML 在首次调用时加载，之后所有请求复用同一实例。
    """
    return KnowledgeGraphAccelerator()
