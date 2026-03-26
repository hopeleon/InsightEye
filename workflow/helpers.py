from __future__ import annotations

import app.config as config
import json
import re
from urllib import request

from app.transcript import classify_question_type


JOB_HINTS = {
    "\u9500\u552e": ("\u5ba2\u6237", "\u6210\u4ea4", "\u7b7e\u5355", "\u4e1a\u7ee9", "\u62dc\u8bbf", "\u5546\u673a", "\u8f6c\u5316", "\u6e20\u9053"),
    "\u4ea7\u54c1\u7ecf\u7406": ("\u4ea7\u54c1", "\u7528\u6237", "\u9700\u6c42", "\u8fed\u4ee3", "\u57cb\u70b9", "\u7559\u5b58", "\u589e\u957f"),
    "\u540e\u7aef": ("\u63a5\u53e3", "\u670d\u52a1", "\u6570\u636e\u5e93", "\u7f13\u5b58", "\u5e76\u53d1", "\u65e5\u5fd7"),
    "\u8fd0\u8425": ("\u6d3b\u52a8", "\u8f6c\u5316", "\u793e\u7fa4", "\u5185\u5bb9", "\u6295\u653e", "GMV"),
    "\u7814\u53d1": ("\u67b6\u6784", "\u4ee3\u7801", "\u91cd\u6784", "\u6027\u80fd", "\u6d4b\u8bd5", "\u4e0a\u7ebf"),
}

PARSER_SYSTEM_PROMPT = """You are an interview transcript parser.
Your job is to convert a full interview transcript into structured JSON.
Return valid JSON only.
Do not infer beyond the text unless necessary.
If job type is uncertain, say \"\u672a\u77e5\" and lower confidence.
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
    best_job = max(counts, key=counts.get) if counts else "\u672a\u77e5"
    best_hits = counts.get(best_job, 0)
    if best_hits == 0:
        return {"value": "\u672a\u77e5", "confidence": 0.2, "evidence": ["\u672a\u547d\u4e2d\u660e\u663e\u5c97\u4f4d\u5173\u952e\u8bcd"]}
    evidence = [keyword for keyword in JOB_HINTS[best_job] if keyword in transcript][:4]
    confidence = min(0.9, 0.35 + best_hits * 0.1)
    return {"value": best_job, "confidence": round(confidence, 2), "evidence": evidence}


def summarize_turn(answer: str) -> str:
    trimmed = re.sub(r"\s+", "", answer)
    return trimmed[:80] + ("..." if len(trimmed) > 80 else "")


def normalize_turns(raw_turns: list[dict]) -> list[dict]:
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


def build_parser_messages(transcript: str) -> list[dict]:
    return [
        {"role": "system", "content": PARSER_SYSTEM_PROMPT},
        {"role": "user", "content": transcript},
    ]


def build_disc_messages(prompt: str, transcript: str, turns: list[dict], features: dict, knowledge: dict, job_inference: dict) -> list[dict]:
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


def call_openai_compatible(model: str, messages: list[dict]) -> dict | None:
    if not config.OPENAI_API_KEY:
        return None
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    req = request.Request(
        f"{config.OPENAI_BASE_URL}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=120) as resp:
        response_json = json.loads(resp.read().decode("utf-8"))
    content = response_json["choices"][0]["message"]["content"]
    return json.loads(content)


# Personality analysis prompt builders.


def build_personality_payload(
    transcript: str,
    turns: list[dict],
    features: dict,
    job_inference: dict,
    local_bigfive: dict | None,
    local_enneagram: dict | None,
) -> dict:
    return {
        "transcript": transcript,
        "parsed_interview": {
            "job_inference": job_inference,
            "turns": turns,
        },
        "atomic_features": features,
        "local_bigfive_result": local_bigfive,
        "local_enneagram_result": local_enneagram,
    }


def build_bigfive_messages(
    prompt: str,
    transcript: str,
    turns: list[dict],
    features: dict,
    job_inference: dict,
    local_bigfive: dict | None,
) -> list[dict]:
    payload = build_personality_payload(transcript, turns, features, job_inference, local_bigfive, None)
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def build_enneagram_messages(
    prompt: str,
    transcript: str,
    turns: list[dict],
    features: dict,
    job_inference: dict,
    local_enneagram: dict | None,
) -> list[dict]:
    payload = build_personality_payload(transcript, turns, features, job_inference, None, local_enneagram)
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
