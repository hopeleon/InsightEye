from __future__ import annotations

import json
import re
from urllib import request

from .config import (
    OPENAI_ANALYSIS_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_PARSER_MODEL,
)
from .disc_engine import analyze_disc
from .features import extract_features
from .knowledge import load_disc_knowledge, load_disc_prompt
from .transcript import build_turns, classify_question_type, parse_transcript


JOB_HINTS = {
    "研发": ("代码", "系统", "架构", "后端", "前端", "算法", "测试", "上线"),
    "产品经理": ("需求", "用户", "增长", "策略", "产品", "埋点", "转化"),
    "销售": ("客户", "成交", "签单", "业绩", "线索", "转介绍"),
    "运营": ("活动", "内容", "拉新", "留存", "社群", "渠道"),
    "设计": ("设计", "视觉", "交互", "体验", "稿", "组件"),
}


PARSER_SYSTEM_PROMPT = """You are an interview transcript parser.
Your job is to convert a full interview transcript into structured JSON.
Return valid JSON only.
Do not infer beyond the text unless necessary.
If job type is uncertain, say \"未知\" and lower confidence.
Schema:
{
  \"job_inference\": {\"value\": \"string\", \"confidence\": 0.0, \"evidence\": [\"...\"]},
  \"turns\": [
    {
      \"turn_id\": 1,
      \"question\": \"string\",
      \"question_type\": \"string\",
      \"answer\": \"string\",
      \"answer_summary\": \"string\"
    }
  ]
}
"""


def infer_job_type(transcript: str) -> dict:
    counts = {}
    for job, keywords in JOB_HINTS.items():
        hits = sum(transcript.count(keyword) for keyword in keywords)
        counts[job] = hits
    best_job = max(counts, key=counts.get) if counts else "未知"
    best_hits = counts.get(best_job, 0)
    if best_hits == 0:
        return {"value": "未知", "confidence": 0.2, "evidence": ["未出现足够明确的岗位词汇。"]}
    evidence = [keyword for keyword in JOB_HINTS[best_job] if keyword in transcript][:4]
    confidence = min(0.9, 0.35 + best_hits * 0.1)
    return {"value": best_job, "confidence": round(confidence, 2), "evidence": evidence}


def summarize_turn(answer: str) -> str:
    trimmed = re.sub(r"\s+", "", answer)
    return trimmed[:80] + ("..." if len(trimmed) > 80 else "")


def _build_disc_messages(transcript: str, turns: list[dict], features: dict, knowledge: dict, job_inference: dict) -> list[dict]:
    prompt = load_disc_prompt()
    payload = {
        "transcript": transcript,
        "parsed_interview": {
            "job_inference": job_inference,
            "turns": turns,
        },
        "atomic_features": features,
        "disc_knowledge": knowledge,
    }
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _build_parser_messages(transcript: str) -> list[dict]:
    return [
        {"role": "system", "content": PARSER_SYSTEM_PROMPT},
        {"role": "user", "content": transcript},
    ]


def _call_openai_compatible(model: str, messages: list[dict]) -> dict | None:
    if not OPENAI_API_KEY:
        return None
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        f"{OPENAI_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
        method="POST",
    )
    with request.urlopen(req) as resp:
        response_json = json.loads(resp.read().decode("utf-8"))
    content = response_json["choices"][0]["message"]["content"]
    return json.loads(content)


def _normalize_turns(raw_turns: list[dict]) -> list[dict]:
    normalized = []
    for index, item in enumerate(raw_turns, start=1):
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not answer:
            continue
        normalized.append(
            {
                "turn_id": index,
                "question": question,
                "question_type": str(item.get("question_type", "")).strip() or classify_question_type(question),
                "answer": answer,
                "answer_summary": str(item.get("answer_summary", "")).strip() or summarize_turn(answer),
                "answer_length": len(answer),
            }
        )
    return normalized


def _local_parse(transcript: str, job_hint: str) -> tuple[list[dict], list[dict], dict]:
    segments = parse_transcript(transcript)
    turns = build_turns(segments)
    detailed_turns = _normalize_turns(turns)
    job_inference = infer_job_type(transcript)
    if job_hint:
        job_inference = {
            "value": job_hint,
            "confidence": 0.95,
            "evidence": ["使用了用户提供的岗位提示。"],
        }
    return segments, detailed_turns, job_inference


def analyze_interview(transcript: str, job_hint: str = "") -> dict:
    knowledge = load_disc_knowledge()
    segments, detailed_turns, job_inference = _local_parse(transcript, job_hint)

    parser_output = None
    parser_error = None
    analysis_output = None
    analysis_error = None
    parse_source = "local_rules"

    if OPENAI_API_KEY:
        try:
            parser_output = _call_openai_compatible(OPENAI_PARSER_MODEL, _build_parser_messages(transcript))
            parsed_turns = _normalize_turns(parser_output.get("turns", [])) if isinstance(parser_output, dict) else []
            if parsed_turns:
                detailed_turns = parsed_turns
                parse_source = "gpt-5-mini"
            if isinstance(parser_output, dict) and not job_hint and parser_output.get("job_inference"):
                job_inference = parser_output["job_inference"]
        except Exception as exc:
            parser_error = str(exc)

    turns_for_analysis = [
        {
            "turn_id": turn["turn_id"],
            "question": turn["question"],
            "question_type": turn["question_type"],
            "answer": turn["answer"],
        }
        for turn in detailed_turns
    ]
    features = extract_features(turns_for_analysis)
    disc_analysis = analyze_disc(transcript, turns_for_analysis, features, knowledge)

    if OPENAI_API_KEY:
        try:
            analysis_output = _call_openai_compatible(
                OPENAI_ANALYSIS_MODEL,
                _build_disc_messages(transcript, detailed_turns, features, knowledge, job_inference),
            )
        except Exception as exc:
            analysis_error = str(exc)

    return {
        "input_overview": {
            "segment_count": len(segments),
            "turn_count": len(detailed_turns),
            "candidate_char_count": features["text_length"],
        },
        "interview_map": {
            "job_inference": job_inference,
            "segments": segments,
            "turns": detailed_turns,
            "parse_source": parse_source,
        },
        "atomic_features": features,
        "disc_analysis": disc_analysis,
        "llm_analysis": analysis_output,
        "llm_status": {
            "enabled": bool(OPENAI_API_KEY),
            "parser_model": OPENAI_PARSER_MODEL,
            "analysis_model": OPENAI_ANALYSIS_MODEL,
            "parser_error": parser_error,
            "analysis_error": analysis_error,
            "parser_output_available": parser_output is not None,
        },
    }
