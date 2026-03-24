from __future__ import annotations

from workflow.engine import run_disc_workflow


def analyze_interview(transcript: str, job_hint: str = "") -> dict:
    return run_disc_workflow(transcript=transcript, job_hint=job_hint)
