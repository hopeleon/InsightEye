from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PROMPTS_DIR = BASE_DIR / "prompts"
STATIC_DIR = BASE_DIR / "static"

DISC_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "DISC.yaml"
DISC_PROMPT_PATH = PROMPTS_DIR / "disc_system_prompt.txt"

BIGFIVE_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "BIGFIVE.yaml"
BIGFIVE_PROMPT_PATH = PROMPTS_DIR / "bigfive_system_prompt.txt"

ENNEAGRAM_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "ENNEAGRAM.yaml"
ENNEAGRAM_PROMPT_PATH = PROMPTS_DIR / "enneagram_system_prompt.txt"

MBTI_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "MBTI.yaml"
MBTI_PROMPT_PATH = PROMPTS_DIR / "mbti_system_prompt.txt"
# ========== BigFive / Enneagram / STAR ==========
BIGFIVE_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "BIGFIVE.yaml"
BIGFIVE_PROMPT_PATH = PROMPTS_DIR / "bigfive_system_prompt.txt"
ENNEAGRAM_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "ENNEAGRAM.yaml"
ENNEAGRAM_PROMPT_PATH = PROMPTS_DIR / "enneagram_system_prompt.txt"
STAR_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "STAR.yaml"
<<<<<<< Updated upstream

STAR_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "STAR.yaml"
=======
>>>>>>> Stashed changes

DEFAULT_OPENAI_BASE_URL = "https://api.zhizengzeng.com/v1"
DEFAULT_OPENAI_PARSER_MODEL = "gpt-5-mini"
DEFAULT_OPENAI_ANALYSIS_MODEL = "gpt-5.4"
<<<<<<< Updated upstream
<<<<<<< Updated upstream
DEFAULT_OPENAI_PERSONALITY_MODEL = "gpt-5.4"
=======
DEFAULT_OPENAI_PERSONALITY_MODEL = "gpt-5-mini"
>>>>>>> Stashed changes
=======
DEFAULT_OPENAI_PERSONALITY_MODEL = "gpt-5-mini"
>>>>>>> Stashed changes

local_settings = {}
local_settings_path = BASE_DIR / "local_settings.py"
if local_settings_path.exists():
    namespace = {}
    content = local_settings_path.read_text(encoding="utf-8").lstrip("\ufeff")
    exec(content, namespace)
    local_settings = namespace

OPENAI_API_KEY = str(local_settings.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))).strip()
OPENAI_BASE_URL = str(local_settings.get("OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL))).rstrip("/")
OPENAI_PARSER_MODEL = str(local_settings.get("OPENAI_PARSER_MODEL", os.getenv("OPENAI_PARSER_MODEL", DEFAULT_OPENAI_PARSER_MODEL))).strip()
OPENAI_ANALYSIS_MODEL = str(local_settings.get("OPENAI_ANALYSIS_MODEL", os.getenv("OPENAI_ANALYSIS_MODEL", DEFAULT_OPENAI_ANALYSIS_MODEL))).strip()
OPENAI_PERSONALITY_MODEL = str(local_settings.get("OPENAI_PERSONALITY_MODEL", os.getenv("OPENAI_PERSONALITY_MODEL", DEFAULT_OPENAI_PERSONALITY_MODEL))).strip()
