from __future__ import annotations

import re
from typing import Iterable


INTERVIEWER_PATTERNS = (
    "面试官",
    " interviewer",
    "interviewer",
    "面试老师",
    "hr",
    "hrbp",
)
INTERVIEWEE_PATTERNS = (
    "候选人",
    "应聘者",
    "求职者",
    "面试者",
    "candidate",
)


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


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

    segments: list[dict] = []
    current: dict | None = None

    for raw_line in normalized.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"^([^:：]{1,20})[:：]\s*(.+)$", line)
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
        "自我介绍": ("自我介绍", "介绍一下", "简单介绍", "简单说说你自己"),
        "项目经历": ("项目", "项目经历", "负责过", "做过", "案例"),
        "冲突处理": ("冲突", "分歧", "矛盾", "意见不一致"),
        "失败复盘": ("失败", "挫折", "复盘", "做错"),
        "团队协作": ("团队", "协作", "配合", "合作"),
        "压力应对": ("压力", "高压", "紧急", "deadline", "加班"),
        "职业动机": ("为什么", "动机", "加入", "选择我们", "职业规划"),
        "追问澄清": ("具体", "展开", "详细", "怎么做的", "为什么这样"),
    }
    for label, keywords in rules.items():
        if any(keyword in question for keyword in keywords):
            return label
    return "通用问题"


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
                    "question_type": classify_question_type(question_text) if question_text else "未标注",
                    "answer": segment["text"],
                }
            )
            pending_question = None
            turn_id += 1

    return turns
