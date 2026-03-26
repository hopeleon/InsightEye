from __future__ import annotations

import re
from typing import Iterable


INTERVIEWER_PATTERNS = (
    "\u9762\u8bd5\u5b98",
    " interviewer",
    "interviewer",
    "\u9762\u8bd5\u8001\u5e08",
    "hr",
    "hrbp",
)
INTERVIEWEE_PATTERNS = (
    "\u5019\u9009\u4eba",
    "\u5e94\u8058\u8005",
    "\u6c42\u804c\u8005",
    "\u9762\u8bd5\u8005",
    "candidate",
)


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _speaker_markers() -> tuple[str, ...]:
    labels = {pattern.strip() for pattern in (*INTERVIEWER_PATTERNS, *INTERVIEWEE_PATTERNS) if pattern.strip()}
    return tuple(sorted(labels, key=len, reverse=True))


def _insert_turn_breaks(text: str) -> str:
    markers = "|".join(re.escape(marker) for marker in _speaker_markers())
    if not markers:
        return text
    pattern = re.compile(rf"(?<!^)(?P<boundary>[\u3002\uff01\uff1f!?\uff1b;])\s*(?P<label>{markers})\s*[:\uff1a]", re.IGNORECASE)
    return pattern.sub(lambda match: f"{match.group('boundary')}\n{match.group('label')}\uff1a", text)


def _speaker_from_prefix(prefix: str) -> str | None:
    lowered = prefix.strip().lower()
    for pattern in INTERVIEWER_PATTERNS:
        if pattern.strip().lower() in lowered:
            return "interviewer"
    for pattern in INTERVIEWEE_PATTERNS:
        if pattern.strip().lower() in lowered:
            return "candidate"
    return None


def parse_transcript(transcript: str) -> list[dict]:
    normalized = normalize_text(transcript)
    if not normalized:
        return []
    normalized = _insert_turn_breaks(normalized)

    segments: list[dict] = []
    current: dict | None = None

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^:\uff1a]{1,20})[:\uff1a]\s*(.+)$", line)
        if match:
            speaker = _speaker_from_prefix(match.group(1))
            content = match.group(2).strip()
            if speaker:
                if current and current["speaker"] == speaker:
                    current["text"] += "\n" + content
                else:
                    current = {"speaker": speaker, "text": content}
                    segments.append(current)
                continue
        if current:
            current["text"] += "\n" + line
        else:
            current = {"speaker": "unknown", "text": line}
            segments.append(current)

    for index, segment in enumerate(segments, start=1):
        segment["id"] = index
        segment["text"] = segment["text"].strip()
    return segments


def classify_question_type(question: str) -> str:
    rules = {
        "\u81ea\u6211\u4ecb\u7ecd": ("\u81ea\u6211\u4ecb\u7ecd", "\u4ecb\u7ecd\u4e00\u4e0b", "\u7b80\u5355\u4ecb\u7ecd", "\u7b80\u5355\u8bf4\u8bf4\u4f60\u81ea\u5df1"),
        "\u9879\u76ee\u7ecf\u5386": ("\u9879\u76ee", "\u9879\u76ee\u7ecf\u5386", "\u8d1f\u8d23\u8fc7", "\u505a\u8fc7", "\u6848\u4f8b"),
        "\u51b2\u7a81\u5904\u7406": ("\u51b2\u7a81", "\u5206\u6b67", "\u77db\u76fe", "\u610f\u89c1\u4e0d\u4e00\u81f4"),
        "\u5931\u8d25\u590d\u76d8": ("\u5931\u8d25", "\u632b\u6298", "\u590d\u76d8", "\u505a\u9519"),
        "\u56e2\u961f\u534f\u4f5c": ("\u56e2\u961f", "\u534f\u4f5c", "\u914d\u5408", "\u5408\u4f5c"),
        "\u538b\u529b\u5e94\u5bf9": ("\u538b\u529b", "\u9ad8\u538b", "\u7d27\u6025", "deadline", "\u52a0\u73ed"),
        "\u804c\u4e1a\u52a8\u673a": ("\u4e3a\u4ec0\u4e48", "\u52a8\u673a", "\u52a0\u5165", "\u9009\u62e9\u6211\u4eec", "\u804c\u4e1a\u89c4\u5212"),
        "\u8ffd\u95ee\u6f84\u6e05": ("\u5177\u4f53", "\u5c55\u5f00", "\u8be6\u7ec6", "\u600e\u4e48\u505a\u7684", "\u4e3a\u4ec0\u4e48\u8fd9\u6837"),
    }
    for label, keywords in rules.items():
        if any(keyword in question for keyword in keywords):
            return label
    return "\u901a\u7528\u95ee\u9898"


def build_turns(segments: Iterable[dict]) -> list[dict]:
    segment_list = list(segments)
    turns: list[dict] = []
    pending_question: dict | None = None
    turn_id = 1

    for segment in segment_list:
        speaker = segment["speaker"]
        if speaker == "interviewer":
            pending_question = segment
            continue
        if speaker == "candidate":
            question_text = pending_question["text"] if pending_question else ""
            turns.append(
                {
                    "turn_id": turn_id,
                    "question": question_text,
                    "question_type": classify_question_type(question_text) if question_text else "\u672a\u6807\u6ce8",
                    "answer": segment["text"],
                }
            )
            pending_question = None
            turn_id += 1

    return turns
