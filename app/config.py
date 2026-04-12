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

# 本地模型配置（FunASR + CAM++）
# 使用相对于项目根目录的路径
DEFAULT_LOCAL_MODEL_DIR = str(BASE_DIR / "models")
DEFAULT_FUNASR_MODEL = str(BASE_DIR / "models" / "funasr")
DEFAULT_CAMPPLUS_MODEL = str(BASE_DIR / "models" / "campplus" / "zh-cn")
DEFAULT_CAMPPLUS_EN_MODEL = str(BASE_DIR / "models" / "campplus" / "en")
DEFAULT_LOCAL_DEVICE = "cuda"  # "cuda" 或 "cpu"

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

# 本地模型配置（支持通过 local_settings.py 或环境变量覆盖）
# 空字符串表示使用默认值
def _get_config_path(local_val, env_var, default):
    val = local_val if local_val else os.getenv(env_var, default)
    return str(val).strip()

LOCAL_MODEL_DIR = _get_config_path(local_settings.get("LOCAL_MODEL_DIR"), "LOCAL_MODEL_DIR", DEFAULT_LOCAL_MODEL_DIR)
# FunASR 模型目录：支持从 local_settings.py 或环境变量覆盖，默认使用项目内置 models/funasr
FUNASR_MODEL_DIR = _get_config_path(local_settings.get("FUNASR_MODEL_DIR"), "FUNASR_MODEL_DIR", DEFAULT_FUNASR_MODEL)
# CAM++ 中文声纹模型目录
CAMPPLUS_MODEL_DIR = _get_config_path(local_settings.get("CAMPPLUS_MODEL_DIR"), "CAMPPLUS_MODEL_DIR", DEFAULT_CAMPPLUS_MODEL)
# CAM++ 英文声纹模型目录
CAMPPLUS_EN_MODEL_DIR = _get_config_path(local_settings.get("CAMPPLUS_EN_MODEL_DIR"), "CAMPPLUS_EN_MODEL_DIR", DEFAULT_CAMPPLUS_EN_MODEL)
# 推理设备
LOCAL_DEVICE = _get_config_path(local_settings.get("LOCAL_DEVICE"), "LOCAL_DEVICE", DEFAULT_LOCAL_DEVICE)
