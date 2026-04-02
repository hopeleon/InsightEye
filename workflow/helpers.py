from __future__ import annotations

import app.config as config
import json
import logging
import re
import time
from urllib import request

from app.transcript import classify_question_type

logger = logging.getLogger("insighteye.llm_call")


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
        logger.warning(f"[LLM调用] API Key 未配置，跳过 LLM 调用")
        return None

    _call_start = time.perf_counter()
    _msg_count = len(messages)
    _input_tokens_est = sum(len(str(m.get("content", ""))) // 4 for m in messages)
    logger.info(f"[LLM调用] 开始调用模型: {model}, 消息数: {_msg_count}, 预估输入token: {_input_tokens_est}")

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
    try:
        with request.urlopen(req, timeout=120) as resp:
            _http_elapsed = (time.perf_counter() - _call_start) * 1000
            response_json = json.loads(resp.read().decode("utf-8"))
        content = response_json["choices"][0]["message"]["content"]

        usage = response_json.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        _total_elapsed = (time.perf_counter() - _call_start) * 1000
        logger.info(
            f"[LLM调用] 调用完成 | 模型: {model} | "
            f"耗时: {_total_elapsed:.0f}ms (HTTP: {_http_elapsed:.0f}ms) | "
            f"Token: 输入≈{prompt_tokens}, 生成≈{completion_tokens}, 总计≈{total_tokens}"
        )
        return json.loads(content)
    except Exception as exc:
        _error_elapsed = (time.perf_counter() - _call_start) * 1000
        logger.error(f"[LLM调用] 调用失败 | 模型: {model} | 耗时: {_error_elapsed:.0f}ms | 错误: {exc}")
        raise


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


LLM_FOLLOWUP_SYSTEM_PROMPT = """You are an expert behavioral interviewer. Based on the interview transcript and local analysis results, generate 3-5 high-quality follow-up questions to probe unresolved evidence gaps.

## Your task
Given:
1. An interview transcript
2. Local rule-based analysis (DISC, MBTI, STAR) with existing follow-up questions
3. Evidence gaps and risk signals identified by the local engine

Generate follow-up questions that:
- Target specific evidence gaps the local engine flagged as uncertain
- Probe ambiguous personality dimensions that need deeper verification
- Challenge any authenticity risk signals (rehearsed answers, vague actions, missing outcomes)
- Are specific to this candidate's actual answers, NOT generic templates
- Help the interviewer verify or refute the current local hypotheses

## Output rules
Return valid JSON only. Do not include reasoning or chain-of-thought.
Each question must be a direct follow-up to something the candidate actually said.
Prioritize questions that would be most diagnostic given the local engine's uncertainty."""

LLM_FOLLOWUP_USER_TEMPLATE = """## Interview Transcript
{transcript}

## Local DISC Analysis
- Ranking: {disc_ranking}
- Scores: {disc_scores}
- Existing follow-ups: {disc_fuq}
- Evidence gaps: {disc_gaps}
- Risk: {disc_risk}

## Local MBTI Analysis
- Type: {mbti_type}
- Ambiguous dimensions: {mbti_ambiguous}
- Existing follow-ups: {mbti_fuq}

## Local STAR Analysis
- Defects: {star_defects}
- Existing follow-ups: {star_fuq}

## Job Context
{job_hint}

Generate follow-up questions targeting the most critical unresolved gaps."""


def build_llm_followup_messages(
    transcript: str,
    disc_result: dict,
    mbti_result: dict,
    star_result: dict,
    job_hint: str,
) -> list[dict]:
    disc_scores = disc_result.get("scores") or {}
    disc_ranking = " / ".join(disc_result.get("ranking") or [])
    disc_gaps = (disc_result.get("evidence_gaps") or [])[:4]
    disc_risk = (disc_result.get("meta") or {}).get("impression_management_risk", "N/A")

    disc_fuq = [
        {"dimension": q.get("target_dimension", ""), "question": q.get("question", "")}
        for q in (disc_result.get("follow_up_questions") or [])[:4]
    ]
    mbti_fuq = [
        {"dimension": q.get("dimension", ""), "question": q.get("question", "")}
        for q in (mbti_result.get("follow_up_questions") or [])[:4]
    ]
    star_fuq = [
        {"defect": q.get("defect_id", ""), "question": q.get("question", "")}
        for q in (star_result.get("followup_questions") or [])[:4]
    ]

    mbti_dims = mbti_result.get("dimensions") or {}
    mbti_ambiguous = [
        dim for dim, val in mbti_dims.items()
        if isinstance(val, dict) and val.get("preference") in {"neutral", "unclear"}
    ]

    star_defects = [
        {"severity": d.get("severity"), "defect": d.get("defect_id"), "description": d.get("description", "")}
        for d in (star_result.get("defects") or [])
        if isinstance(d, dict) and d.get("severity") == "high"
    ]

    user_content = LLM_FOLLOWUP_USER_TEMPLATE.format(
        transcript=transcript,
        disc_ranking=disc_ranking,
        disc_scores=json.dumps(disc_scores, ensure_ascii=False),
        disc_fuq=json.dumps(disc_fuq, ensure_ascii=False),
        disc_gaps=json.dumps(disc_gaps, ensure_ascii=False),
        disc_risk=disc_risk,
        mbti_type=mbti_result.get("type", "unknown"),
        mbti_ambiguous=json.dumps(mbti_ambiguous, ensure_ascii=False),
        mbti_fuq=json.dumps(mbti_fuq, ensure_ascii=False),
        star_defects=json.dumps(star_defects, ensure_ascii=False),
        star_fuq=json.dumps(star_fuq, ensure_ascii=False),
        job_hint=job_hint or "未提供岗位信息",
    )

    return [
        {"role": "system", "content": LLM_FOLLOWUP_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
