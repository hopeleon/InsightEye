from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import (
    BASE_DIR,
    BIGFIVE_KNOWLEDGE_PATH,
    BIGFIVE_PROMPT_PATH,
    DISC_KNOWLEDGE_PATH,
    DISC_PROMPT_PATH,
    ENNEAGRAM_KNOWLEDGE_PATH,
    ENNEAGRAM_PROMPT_PATH,
    KNOWLEDGE_DIR,
    STAR_KNOWLEDGE_PATH,
)

INDUSTRIES_DIR = KNOWLEDGE_DIR / "industries"
JOB_COMPETENCIES_PATH = KNOWLEDGE_DIR / "job_competencies.yaml"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────
# 通用知识库（已有）
# ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_disc_knowledge() -> dict:
    return yaml.safe_load(_read_text(DISC_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_disc_prompt() -> str:
    return _read_text(DISC_PROMPT_PATH)


@lru_cache(maxsize=1)
def load_bigfive_knowledge() -> dict:
    return yaml.safe_load(_read_text(BIGFIVE_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_bigfive_prompt() -> str:
    return _read_text(BIGFIVE_PROMPT_PATH)


@lru_cache(maxsize=1)
def load_enneagram_knowledge() -> dict:
    return yaml.safe_load(_read_text(ENNEAGRAM_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_enneagram_prompt() -> str:
    return _read_text(ENNEAGRAM_PROMPT_PATH)


@lru_cache(maxsize=1)
def load_star_knowledge() -> dict:
    return yaml.safe_load(_read_text(STAR_KNOWLEDGE_PATH))


# ─────────────────────────────────────────────────────────────────
# 行业知识库
# ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_industry_knowledge(industry: str) -> dict | None:
    """
    加载指定行业的行为知识库。
    例如: load_industry_knowledge("tech") → knowledge/industries/tech.yaml
    """
    path = INDUSTRIES_DIR / f"{industry}.yaml"
    if not path.exists():
        return None
    return yaml.safe_load(_read_text(path))


@lru_cache(maxsize=1)
def load_all_industries() -> dict[str, dict]:
    """加载所有行业知识库，返回 {行业名: 知识内容}。"""
    result = {}
    if not INDUSTRIES_DIR.exists():
        return result
    for path in sorted(INDUSTRIES_DIR.glob("*.yaml")):
        key = path.stem
        result[key] = yaml.safe_load(_read_text(path))
    return result


# ─────────────────────────────────────────────────────────────────
# 岗位胜任力知识库
# ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def load_job_competencies() -> dict:
    """加载岗位胜任力映射（DISC → 胜任力 → 岗位基准）。"""
    if not JOB_COMPETENCIES_PATH.exists():
        return {}
    return yaml.safe_load(_read_text(JOB_COMPETENCIES_PATH))


# ─────────────────────────────────────────────────────────────────
# 行业 & 岗位自动识别
# ─────────────────────────────────────────────────────────────────

def detect_industry(job_hint: str, transcript: str = "") -> str | None:
    """
    从岗位提示推断行业。
    当前只支持 tech（互联网），后续可扩展 finance / manufacturing 等。
    """
    text = (job_hint + " " + transcript).lower()
    tech_keywords = [
        "互联网", "软件", "it", "tech", "产品", "运营", "开发", "前端", "后端",
        "算法", "数据", "devops", "sre", "测试", "qa", "架构", "cto",
        "pm", "项目经理", "增长", "电商",
    ]
    score = sum(1 for kw in tech_keywords if kw in text)
    if score >= 1:
        return "tech"
    return None


def detect_job_family(job_hint: str) -> str:
    """
    从岗位提示词推断岗位族（与 job_competencies.yaml 的 key 对应）。
    返回最匹配的 job_family key，未匹配时返回 "default"。
    """
    hint = job_hint.lower().strip()
    if not hint:
        return "default"

    competencies = load_job_competencies()
    families = competencies.get("job_families", {})

    best_match: tuple[str, int] = ("default", 0)
    for key, family in families.items():
        if key == "default":
            continue
        score = 0
        for alias in (family.get("alias") or []):
            if alias.lower() in hint:
                score += len(alias)  # 更长的别名优先
        if score > best_match[1]:
            best_match = (key, score)

    return best_match[0]


def get_industry_context(job_hint: str, transcript: str = "") -> dict:
    """
    获取完整的行业上下文，供分析引擎使用。
    返回 {"industry", "industry_knowledge", "job_family", "job_competencies"}
    """
    industry = detect_industry(job_hint, transcript)
    ind_knowledge = load_industry_knowledge(industry) if industry else None
    job_family = detect_job_family(job_hint)
    jc = load_job_competencies()
    family_info = jc.get("job_families", {}).get(job_family, jc.get("job_families", {}).get("default", {}))

    return {
        "industry": industry,
        "industry_knowledge": ind_knowledge,
        "job_family": job_family,
        "job_family_info": family_info,
        "job_competencies": jc,
        "disc_to_competency": jc.get("disc_to_competency", {}),
    }

