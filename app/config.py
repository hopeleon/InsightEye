from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
PROMPTS_DIR = BASE_DIR / "prompts"
STATIC_DIR = BASE_DIR / "static"

DISC_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "DISC.yaml"
DISC_PROMPT_PATH = PROMPTS_DIR / "disc_system_prompt.txt"
MBTI_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "MBTI.yaml"
MBTI_PROMPT_PATH = PROMPTS_DIR / "mbti_system_prompt.txt"
BIGFIVE_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "BIGFIVE.yaml"
BIGFIVE_PROMPT_PATH = PROMPTS_DIR / "bigfive_system_prompt.txt"
ENNEAGRAM_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "ENNEAGRAM.yaml"
ENNEAGRAM_PROMPT_PATH = PROMPTS_DIR / "enneagram_system_prompt.txt"
STAR_KNOWLEDGE_PATH = KNOWLEDGE_DIR / "STAR.yaml"

DEFAULT_OPENAI_BASE_URL = "https://api.zhizengzeng.com/v1"
DEFAULT_OPENAI_PARSER_MODEL = "gpt-5-mini"
DEFAULT_OPENAI_ANALYSIS_MODEL = "gpt-5.4"
DEFAULT_OPENAI_PERSONALITY_MODEL = "gpt-5-mini"
DEFAULT_OPENAI_AUDIO_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_OPENAI_REALTIME_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
DEFAULT_REALTIME_WS_PORT = 8765
DEFAULT_DASHSCOPE_REALTIME_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
DEFAULT_DASHSCOPE_REALTIME_ASR_MODEL = "qwen3-asr-flash-realtime"

local_settings = {}
local_settings_path = BASE_DIR / "local_settings.py"
if local_settings_path.exists():
    namespace = {}
    content = local_settings_path.read_text(encoding="utf-8").lstrip("﻿")
    exec(content, namespace)
    local_settings = namespace

OPENAI_API_KEY = str(local_settings.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))).strip()
OPENAI_BASE_URL = str(local_settings.get("OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL))).rstrip("/")
OPENAI_PARSER_MODEL = str(local_settings.get("OPENAI_PARSER_MODEL", os.getenv("OPENAI_PARSER_MODEL", DEFAULT_OPENAI_PARSER_MODEL))).strip()
OPENAI_ANALYSIS_MODEL = str(local_settings.get("OPENAI_ANALYSIS_MODEL", os.getenv("OPENAI_ANALYSIS_MODEL", DEFAULT_OPENAI_ANALYSIS_MODEL))).strip()
OPENAI_PERSONALITY_MODEL = str(local_settings.get("OPENAI_PERSONALITY_MODEL", os.getenv("OPENAI_PERSONALITY_MODEL", DEFAULT_OPENAI_PERSONALITY_MODEL))).strip()
OPENAI_AUDIO_MODEL = str(local_settings.get("OPENAI_AUDIO_MODEL", os.getenv("OPENAI_AUDIO_MODEL", DEFAULT_OPENAI_AUDIO_MODEL))).strip()
OPENAI_REALTIME_TRANSCRIPTION_MODEL = str(local_settings.get("OPENAI_REALTIME_TRANSCRIPTION_MODEL", os.getenv("OPENAI_REALTIME_TRANSCRIPTION_MODEL", DEFAULT_OPENAI_REALTIME_TRANSCRIPTION_MODEL))).strip()
OPENAI_WEBSOCKET_BASE_URL = str(local_settings.get("OPENAI_WEBSOCKET_BASE_URL", os.getenv("OPENAI_WEBSOCKET_BASE_URL", ""))).strip() or None
REALTIME_WS_PORT = int(local_settings.get("REALTIME_WS_PORT", os.getenv("REALTIME_WS_PORT", DEFAULT_REALTIME_WS_PORT)))
DASHSCOPE_API_KEY = str(local_settings.get("DASHSCOPE_API_KEY", os.getenv("DASHSCOPE_API_KEY", ""))).strip()
DASHSCOPE_REALTIME_WS_URL = str(
    local_settings.get("DASHSCOPE_REALTIME_WS_URL", os.getenv("DASHSCOPE_REALTIME_WS_URL", DEFAULT_DASHSCOPE_REALTIME_WS_URL))
).strip().rstrip("/")
DASHSCOPE_REALTIME_ASR_MODEL = str(
    local_settings.get("DASHSCOPE_REALTIME_ASR_MODEL", os.getenv("DASHSCOPE_REALTIME_ASR_MODEL", DEFAULT_DASHSCOPE_REALTIME_ASR_MODEL))
).strip()
