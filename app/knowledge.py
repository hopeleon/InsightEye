from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import DISC_KNOWLEDGE_PATH, DISC_PROMPT_PATH


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def load_disc_knowledge() -> dict:
    return yaml.safe_load(_read_text(DISC_KNOWLEDGE_PATH))


@lru_cache(maxsize=1)
def load_disc_prompt() -> str:
    return _read_text(DISC_PROMPT_PATH)
