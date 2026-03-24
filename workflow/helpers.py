from __future__ import annotations

import json
import re
from urllib import request

from app.config import OPENAI_API_KEY, OPENAI_BASE_URL
from app.transcript import classify_question_type


JOB_HINTS = {
    "??": ("??", "??", "??", "??", "??", "??", "??", "??"),
    "????": ("??", "??", "??", "??", "??", "??", "??"),
    "??": ("??", "??", "??", "??", "??", "???"),
    "??": ("??", "??", "??", "??", "??", "??"),
    "??": ("??", "??", "??", "??", "?", "??"),
}

PARSER_SYSTEM_PROMPT = """You are an interview transcript parser.
Your job is to convert a full interview transcript into structured JSON.
Return valid JSON only.
Do not infer beyond the text unless necessary.
If job type is uncertain, say \"??\" and lower confidence.
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
    best_job = max(counts, key=counts.get) if counts else "??"
    best_hits = counts.get(best_job, 0)
    if best_hits == 0:
        return {"value": "??", "confidence": 0.2, "evidence": ["?????????????"]}
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
