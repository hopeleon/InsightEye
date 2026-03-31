# InsightEye Realtime Interview Architecture

## Goal

Build a realtime interview mode that can:

1. Stream audio during the interview.
2. Transcribe speech into text incrementally.
3. Separate the dialogue into `speaker_a` and `speaker_b` at first.
4. Infer `interviewer` and `candidate` after enough evidence accumulates.
5. Continuously suggest follow-up questions during the interview.
6. Produce a final full analysis after the interview ends.

This design keeps the existing text-analysis core and adds a realtime session layer in front of it.

## Current Reusable Pieces

The current repository already provides the text analysis core:

- `app/transcript.py`
  - transcript normalization
  - speaker parsing
  - turn construction
  - question-type classification
- `app/analysis.py`
  - `analyze_interview`
  - `analyze_interview_full`
- `workflow/engine.py`
  - local workflow
  - LLM-enhanced workflow
  - full personality workflow
- `app/disc_engine.py`
  - follow-up questions
  - recommended action
- `app/star_analyzer.py`
  - STAR defects
  - probe question generation

The realtime mode should reuse these modules instead of rewriting them.

## Target Workflow

### Realtime phase

1. Client starts a realtime interview session.
2. Client sends audio chunks to backend over WebSocket.
3. Backend forwards audio to a streaming ASR provider.
4. Backend receives incremental transcript events.
5. Backend groups transcript into speaker segments:
   - early stage: `speaker_a` / `speaker_b`
   - later stage: `interviewer (inferred)` / `candidate (inferred)`
6. Backend maintains a rolling transcript buffer.
7. Every completed turn or analysis window, backend runs a lightweight rolling analysis.
8. Backend sends transcript updates and suggested follow-up questions back to the UI.

### Final phase

1. User clicks `End Interview`.
2. Backend freezes the transcript.
3. Backend runs the existing full workflow on the final transcript.
4. Backend returns a final structured report.

## Recommended Tooling

### Streaming ASR

Recommended first choice:

- OpenAI Realtime Transcription

Why:

- low-latency streaming
- incremental transcript events
- easier server integration than building ASR from scratch

### Speaker separation

Recommended strategy for V1:

- do not try to identify real-world identity
- maintain online speaker clustering for two active speakers
- assign transcript segments to `speaker_a` and `speaker_b`

V1 does not need perfect diarization. It needs stable enough segmentation to support turn-based interview analysis.

### Final transcript correction

Optional second-stage correction:

- pyannote-audio
- WhisperX

Use this only after the interview or on delayed background jobs. Do not make the first realtime loop depend on it.

## New Backend Modules

### `app/realtime_server.py`

Responsibilities:

- expose HTTP session endpoints
- expose WebSocket endpoint for audio streaming
- push transcript and analysis updates to the client

Recommended endpoints:

- `POST /api/realtime/session/start`
- `WS /api/realtime/session/{session_id}`
- `POST /api/realtime/session/{session_id}/end`
- `GET /api/realtime/session/{session_id}/status`

### `app/realtime_session.py`

Responsibilities:

- hold all in-memory state for one interview
- track transcript segments
- track speaker mapping confidence
- track rolling analysis snapshots

Suggested fields:

- `session_id`
- `started_at`
- `job_hint`
- `audio_offset_ms`
- `segments`
- `speaker_map`
- `role_inference`
- `rolling_summary`
- `rolling_followups`
- `status`

### `app/realtime_transcriber.py`

Responsibilities:

- manage streaming ASR connection
- accept binary or base64 audio chunks
- emit incremental transcript events

Suggested output event shape:

```json
{
  "type": "transcript.partial",
  "text": "我最近主要负责",
  "start_ms": 1200,
  "end_ms": 1900
}
```

and:

```json
{
  "type": "transcript.final",
  "text": "我最近主要负责推荐系统重构。",
  "start_ms": 1200,
  "end_ms": 2600
}
```

### `app/realtime_speaker.py`

Responsibilities:

- maintain online two-speaker clustering
- assign each finalized speech segment to `speaker_a` or `speaker_b`
- expose confidence

Suggested output:

```json
{
  "speaker_id": "speaker_a",
  "confidence": 0.82
}
```

### `app/role_inference.py`

Responsibilities:

- infer `interviewer` vs `candidate` from transcript behavior
- keep role mapping stable unless new evidence is clearly stronger

Rules for V1:

- speaker with more question-like utterances tends to be interviewer
- speaker with higher question diversity tends to be interviewer
- speaker with longer narrative responses tends to be candidate
- speaker with more probing patterns tends to be interviewer

Suggested output:

```json
{
  "speaker_a": "interviewer",
  "speaker_b": "candidate",
  "confidence": 0.77,
  "reasons": [
    "speaker_a has a much higher question ratio",
    "speaker_b has longer answer spans"
  ]
}
```

### `app/realtime_analyzer.py`

Responsibilities:

- transform rolling transcript into partial interview turns
- call existing local analysis on small windows
- generate follow-up suggestions without waiting for full interview completion

V1 should focus on:

- current answer summary
- evidence gaps
- STAR defects
- ownership clarity
- suggested follow-up questions

V1 should avoid frequent full-personality analysis.

## Transcript State Model

Suggested canonical segment format:

```json
{
  "id": 12,
  "speaker_id": "speaker_a",
  "role": "candidate",
  "role_confidence": 0.77,
  "text": "我当时负责把线上延迟从 280ms 降到 110ms。",
  "start_ms": 18200,
  "end_ms": 21400,
  "final": true
}
```

The display layer can show:

- before role inference stabilizes: `说话人 A / 说话人 B`
- after enough evidence: `面试官（推断） / 候选人（推断）`

## Realtime Analysis Triggers

Do not run a full analysis on every transcript update.

Recommended trigger conditions:

- one new complete Q/A turn
- or 20 to 40 seconds of additional dialogue
- or 150 to 300 new candidate characters

When triggered:

1. build a normalized transcript from current segments
2. build partial turns
3. run lightweight local analysis
4. extract:
   - current observations
   - evidence gaps
   - follow-up questions
   - recommended next move

## Client-Server Protocol

### Start session

Request:

```json
{
  "job_hint_optional": "后端研发"
}
```

Response:

```json
{
  "session_id": "rt_xxx",
  "ws_path": "/api/realtime/session/rt_xxx"
}
```

### WebSocket message types from client

Audio chunk:

```json
{
  "type": "audio.append",
  "seq": 15,
  "audio_format": "pcm16",
  "sample_rate": 16000,
  "data": "<base64>"
}
```

End stream:

```json
{
  "type": "audio.commit"
}
```

### WebSocket message types from server

Transcript update:

```json
{
  "type": "transcript.update",
  "segment": {
    "speaker_id": "speaker_a",
    "role": null,
    "text": "请先介绍一下最近负责的项目",
    "final": true
  }
}
```

Role update:

```json
{
  "type": "role.update",
  "mapping": {
    "speaker_a": "interviewer",
    "speaker_b": "candidate"
  },
  "confidence": 0.77
}
```

Analysis update:

```json
{
  "type": "analysis.update",
  "summary": "候选人强调执行推进，但个人贡献边界仍不够清晰。",
  "evidence_gaps": [
    "缺少可量化结果",
    "个人决策权边界不清"
  ],
  "follow_up_questions": [
    "这个项目中你独立拍板的关键决策是什么？",
    "结果提升具体是多少，验证口径是什么？"
  ],
  "recommended_action": "继续追问具体动作和结果证据。"
}
```

## Integration With Existing Workflow

### Realtime path

Use the realtime session layer to periodically build a text transcript like:

```text
面试官：请先介绍一下最近负责的项目。
候选人：我最近主要负责推荐系统重构。
面试官：你个人做了哪些关键决策？
候选人：我主要主导了召回链路的重建。
```

Then feed the rolling transcript into the existing local workflow functions.

### Final path

At session end:

1. finalize the transcript
2. convert `speaker_a / speaker_b` to inferred roles
3. run `analyze_interview_full`
4. return the final full report

## Recommended V1 Scope

V1 should include:

- WebSocket realtime session
- streaming ASR integration
- two-speaker online separation
- role inference from text behavior
- rolling transcript
- rolling follow-up suggestion
- final full analysis on session end

V1 should not include:

- multi-party interview support
- stable real-name speaker identification
- heavy full-personality reruns on every update
- perfect overlap resolution

## Suggested Implementation Order

1. Add session lifecycle endpoints and in-memory session store.
2. Add WebSocket streaming endpoint.
3. Add realtime ASR adapter.
4. Add segment buffer and transcript builder.
5. Add `speaker_a / speaker_b` assignment.
6. Add role inference.
7. Add rolling analysis updates.
8. Add end-of-session final report generation.

## Practical Notes

- Keep V1 in memory. Do not add a database unless session persistence becomes necessary.
- Keep realtime analysis local-first. Use LLM only where it clearly adds value.
- Use stable hysteresis for role mapping. Do not flip `speaker_a` and `speaker_b` too easily.
- Treat low-confidence windows as provisional and show that in the UI.

## What Changes First In This Repository

The first code changes should be:

- add new realtime modules under `app/`
- add a new server entry for realtime mode
- keep existing `app/server.py` endpoints intact
- add a transcript-to-realtime adapter that reuses `app/transcript.py`

This keeps the current demo usable while a new realtime path is introduced alongside it.
