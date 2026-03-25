from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PROMPTS_DIR = BASE_DIR / "prompts"
STATIC_DIR = BASE_DIR / "static"

DISC_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "DISC.yaml"
DISC_PROMPT_PATH = PROMPTS_DIR / "disc_system_prompt.txt"
# ========== MBTI 相关配置 ==========
MBTI_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "MBTI.yaml"
MBTI_PROMPT_PATH = PROMPTS_DIR / "mbti_system_prompt.txt"

DEFAULT_OPENAI_BASE_URL = "https://api.zhizengzeng.com/v1"
DEFAULT_OPENAI_PARSER_MODEL = "gpt-5-mini"
DEFAULT_OPENAI_ANALYSIS_MODEL = "gpt-5.4"

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
