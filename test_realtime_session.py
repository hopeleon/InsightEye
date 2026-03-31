from __future__ import annotations

from app.realtime_session import RealtimeSessionStore


def test_realtime_session_flow() -> None:
    store = RealtimeSessionStore()
    session = store.create(job_hint="后端研发")
    session_id = session["session_id"]

    store.append_segment(
        session_id,
        {
            "speaker_id": "speaker_a",
            "text": "请你先介绍一下最近负责的项目？",
            "start_ms": 0,
            "end_ms": 1800,
            "final": True,
        },
    )
    store.append_segment(
        session_id,
        {
            "speaker_id": "speaker_b",
            "text": "我最近主要负责订单系统重构，重点解决高峰期延迟问题。",
            "start_ms": 1900,
            "end_ms": 4200,
            "final": True,
        },
    )

    current = store.status(session_id)
    assert current["rolling_analysis"] is not None
    assert current["rolling_analysis"]["transcript"]
    assert current["rolling_analysis"]["follow_up_questions"]
    assert any(item.get("source") for item in current["rolling_analysis"]["follow_up_questions"])

    final_session = store.end(session_id)
    final_report = final_session["final_report"]
    assert final_report is not None
    assert "interview_map" in final_report


if __name__ == "__main__":
    test_realtime_session_flow()
    print("test_realtime_session.py passed")
