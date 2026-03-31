from __future__ import annotations

from app.audio_transcription import _normalize_segments


def test_normalize_segments() -> None:
    raw = {
        "segments": [
            {"speaker": "speaker_2", "text": "请先介绍一下最近项目。", "start": 0.0, "end": 1.5},
            {"speaker": "speaker_7", "text": "我最近主要负责订单系统重构。", "start": 1.7, "end": 4.1},
        ]
    }
    result = _normalize_segments(raw)
    assert len(result) == 2
    assert result[0]["speaker_id"] == "speaker_a"
    assert result[1]["speaker_id"] == "speaker_b"
    assert result[0]["start_ms"] == 0
    assert result[1]["end_ms"] == 4100


if __name__ == "__main__":
    test_normalize_segments()
    print("test_audio_transcription.py passed")
