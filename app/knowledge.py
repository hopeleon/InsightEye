from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import (
    BIGFIVE_KNOWLEDGE_PATH,
    BIGFIVE_PROMPT_PATH,
    DISC_KNOWLEDGE_PATH,
    DISC_PROMPT_PATH,
    ENNEAGRAM_KNOWLEDGE_PATH,
    ENNEAGRAM_PROMPT_PATH,
    MBTI_KNOWLEDGE_PATH,
    MBTI_PROMPT_PATH,
    STAR_KNOWLEDGE_PATH,
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_disc_knowledge() -> dict:
    return yaml.safe_load(_read_text(DISC_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_disc_prompt() -> str:
    return _read_text(DISC_PROMPT_PATH)


<<<<<<< Updated upstream
<<<<<<< Updated upstream
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


=======
>>>>>>> Stashed changes
@lru_cache(maxsize=1)
def load_mbti_knowledge() -> dict:
=======
@lru_cache(maxsize=1)
def load_mbti_knowledge() -> dict:
    """加载 MBTI 知识库"""
    from .config import MBTI_KNOWLEDGE_PATH
>>>>>>> Stashed changes
    return yaml.safe_load(_read_text(MBTI_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_mbti_prompt() -> str:
<<<<<<< Updated upstream
=======
    """加载 MBTI 提示词"""
    from .config import MBTI_PROMPT_PATH
>>>>>>> Stashed changes
    return _read_text(MBTI_PROMPT_PATH)


@lru_cache(maxsize=1)
<<<<<<< Updated upstream
<<<<<<< Updated upstream
def load_star_knowledge() -> dict:
    return yaml.safe_load(_read_text(STAR_KNOWLEDGE_PATH))
=======
def load_bigfive_knowledge() -> dict:
=======
def load_bigfive_knowledge() -> dict:
    """加载 Big Five 知识库"""
    from .config import BIGFIVE_KNOWLEDGE_PATH
>>>>>>> Stashed changes
    return yaml.safe_load(_read_text(BIGFIVE_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_bigfive_prompt() -> str:
<<<<<<< Updated upstream
=======
    """加载 Big Five 提示词"""
    from .config import BIGFIVE_PROMPT_PATH
>>>>>>> Stashed changes
    return _read_text(BIGFIVE_PROMPT_PATH)


@lru_cache(maxsize=1)
def load_enneagram_knowledge() -> dict:
<<<<<<< Updated upstream
=======
    """加载九型人格知识库"""
    from .config import ENNEAGRAM_KNOWLEDGE_PATH
>>>>>>> Stashed changes
    return yaml.safe_load(_read_text(ENNEAGRAM_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_enneagram_prompt() -> str:
<<<<<<< Updated upstream
=======
    """加载九型人格提示词"""
    from .config import ENNEAGRAM_PROMPT_PATH
>>>>>>> Stashed changes
    return _read_text(ENNEAGRAM_PROMPT_PATH)


@lru_cache(maxsize=1)
def load_star_knowledge() -> dict:
<<<<<<< Updated upstream
    return yaml.safe_load(_read_text(STAR_KNOWLEDGE_PATH))
>>>>>>> Stashed changes
=======
    """加载 STAR 知识库"""
    from .config import STAR_KNOWLEDGE_PATH
    return yaml.safe_load(_read_text(STAR_KNOWLEDGE_PATH))
>>>>>>> Stashed changes
