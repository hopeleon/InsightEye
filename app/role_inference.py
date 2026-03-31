from __future__ import annotations

from collections import defaultdict

from .transcript import classify_question_type


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _speaker_stats(segments: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = defaultdict(
        lambda: {
            "segment_count": 0,
            "question_count": 0,
            "question_type_count": 0,
            "char_count": 0,
            "avg_len": 0.0,
            "probe_hits": 0,
        }
    )
    question_types: dict[str, set[str]] = defaultdict(set)

    for segment in segments:
        speaker_id = str(segment.get("speaker_id") or "").strip()
        text = str(segment.get("text") or "").strip()
        if not speaker_id or not text:
            continue

        speaker_stats = stats[speaker_id]
        speaker_stats["segment_count"] += 1
        speaker_stats["char_count"] += len(text)

        if "?" in text or "？" in text:
            speaker_stats["question_count"] += 1
            question_types[speaker_id].add(classify_question_type(text))

        probe_hits = sum(text.count(token) for token in ("为什么", "怎么", "具体", "展开", "详细", "如何", "请介绍"))
        speaker_stats["probe_hits"] += probe_hits

    for speaker_id, speaker_stats in stats.items():
        segment_count = speaker_stats["segment_count"]
        speaker_stats["avg_len"] = _safe_ratio(speaker_stats["char_count"], segment_count)
        speaker_stats["question_type_count"] = len(question_types[speaker_id])
    return stats


def infer_roles(segments: list[dict]) -> dict:
    speaker_ids = sorted({str(item.get("speaker_id") or "").strip() for item in segments if item.get("speaker_id")})
    if len(speaker_ids) < 2:
        return {
            "ready": False,
            "state": "single_speaker",
            "mapping": {},
            "confidence": 0.0,
            "reasons": ["\u5f53\u524d\u4ec5\u68c0\u6d4b\u5230\u4e00\u8def\u6709\u6548\u8bf4\u8bdd\u4eba\uff0c\u6682\u4e0d\u8fdb\u884c\u89d2\u8272\u63a8\u65ad\u3002"],
        }

    stats = _speaker_stats(segments)
    speaker_a, speaker_b = speaker_ids[:2]
    a_stats = stats.get(speaker_a, {})
    b_stats = stats.get(speaker_b, {})

    if min(a_stats.get("segment_count", 0), b_stats.get("segment_count", 0)) < 2 or min(a_stats.get("char_count", 0), b_stats.get("char_count", 0)) < 12:
        return {
            "ready": False,
            "state": "warming_up",
            "mapping": {},
            "confidence": 0.0,
            "reasons": ["\u9700\u8981\u4e24\u8def\u8bf4\u8bdd\u4eba\u90fd\u79ef\u7d2f\u8db3\u591f\u7247\u6bb5\u540e\uff0c\u624d\u5f00\u59cb\u89d2\u8272\u63a8\u65ad\u3002"],
            "stats": {speaker_a: a_stats, speaker_b: b_stats},
        }

    a_score = 0.0
    b_score = 0.0
    reasons: list[str] = []

    a_question_ratio = _safe_ratio(a_stats.get("question_count", 0), a_stats.get("segment_count", 0))
    b_question_ratio = _safe_ratio(b_stats.get("question_count", 0), b_stats.get("segment_count", 0))
    if a_question_ratio > b_question_ratio:
        a_score += 2.0
        reasons.append(f"{speaker_a} has a higher question ratio.")
    elif b_question_ratio > a_question_ratio:
        b_score += 2.0
        reasons.append(f"{speaker_b} has a higher question ratio.")

    if a_stats.get("question_type_count", 0) > b_stats.get("question_type_count", 0):
        a_score += 1.0
        reasons.append(f"{speaker_a} covers more question types.")
    elif b_stats.get("question_type_count", 0) > a_stats.get("question_type_count", 0):
        b_score += 1.0
        reasons.append(f"{speaker_b} covers more question types.")

    if a_stats.get("probe_hits", 0) > b_stats.get("probe_hits", 0):
        a_score += 1.0
        reasons.append(f"{speaker_a} uses more probing language.")
    elif b_stats.get("probe_hits", 0) > a_stats.get("probe_hits", 0):
        b_score += 1.0
        reasons.append(f"{speaker_b} uses more probing language.")

    if a_stats.get("avg_len", 0.0) < b_stats.get("avg_len", 0.0):
        a_score += 1.0
        b_score += 0.5
        reasons.append(f"{speaker_b} tends to produce longer narrative responses.")
    elif b_stats.get("avg_len", 0.0) < a_stats.get("avg_len", 0.0):
        b_score += 1.0
        a_score += 0.5
        reasons.append(f"{speaker_a} tends to produce longer narrative responses.")

    total_score = max(a_score + b_score, 1.0)
    score_gap = abs(a_score - b_score)
    ready = score_gap >= 1.0

    if a_score >= b_score:
        mapping = {speaker_a: "interviewer", speaker_b: "candidate"}
    else:
        mapping = {speaker_a: "candidate", speaker_b: "interviewer"}

    return {
        "ready": ready,
        "state": "ready" if ready else "insufficient",
        "mapping": mapping if ready else {},
        "confidence": round(min(0.95, 0.5 + score_gap / total_score / 2), 2) if ready else 0.0,
        "reasons": reasons[:4],
        "stats": {speaker_a: a_stats, speaker_b: b_stats},
    }
