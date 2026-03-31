from __future__ import annotations

import json
import mimetypes
import uuid
from pathlib import Path
from urllib import request

import app.config as config


class AudioTranscriptionError(RuntimeError):
    pass


def _multipart_body(fields: dict[str, str], file_field: str, filename: str, content: bytes, mime_type: str) -> tuple[bytes, str]:
    boundary = f"----InsightEye{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8"),
            f"Content-Type: {mime_type}\r\n\r\n".encode("utf-8"),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(chunks), boundary


def _first_present(item: dict, *keys: str):
    for key in keys:
        if key in item and item[key] is not None:
            return item[key]
    return None


def _normalize_segments(response_json: dict) -> list[dict]:
    raw_segments = response_json.get("segments") or response_json.get("speaker_segments") or []
    if not isinstance(raw_segments, list):
        raw_segments = []

    speaker_map: dict[str, str] = {}
    normalized: list[dict] = []
    next_id = 1
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        raw_speaker = str(item.get("speaker") or item.get("speaker_label") or item.get("speaker_id") or "speaker_0")
        if raw_speaker not in speaker_map:
            speaker_map[raw_speaker] = "speaker_a" if not speaker_map else "speaker_b"
        normalized.append(
            {
                "id": next_id,
                "speaker_id": speaker_map[raw_speaker],
                "raw_speaker": raw_speaker,
                "text": text,
                "start_ms": int(round(float(_first_present(item, "start_ms", "start") or 0) * (1 if _first_present(item, "start_ms") is not None else 1000))),
                "end_ms": int(round(float(_first_present(item, "end_ms", "end") or 0) * (1 if _first_present(item, "end_ms") is not None else 1000))),
                "final": True,
            }
        )
        next_id += 1

    if normalized:
        return normalized

    text = str(response_json.get("text") or "").strip()
    if not text:
        return []
    return [
        {
            "id": 1,
            "speaker_id": "speaker_a",
            "raw_speaker": "speaker_0",
            "text": text,
            "start_ms": 0,
            "end_ms": max(1000, len(text) * 120),
            "final": True,
        }
    ]


def transcribe_audio_bytes(audio_bytes: bytes, filename: str, mime_type: str | None = None, language: str = "zh") -> dict:
    if not config.OPENAI_API_KEY:
        print(f"[AudioTranscription] missing api key base_url={config.OPENAI_BASE_URL}")
        raise AudioTranscriptionError("OPENAI_API_KEY is not configured")
    if not audio_bytes:
        raise AudioTranscriptionError("Audio file is empty")

    detected_mime = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    fields = {
        "model": config.OPENAI_AUDIO_MODEL,
        "response_format": "diarized_json",
        "language": language,
    }
    body, boundary = _multipart_body(fields, "file", filename, audio_bytes, detected_mime)
    req = request.Request(
        f"{config.OPENAI_BASE_URL}/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=180) as resp:
            response_json = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise AudioTranscriptionError(f"Audio transcription failed: {exc}") from exc

    segments = _normalize_segments(response_json)
    if not segments:
        raise AudioTranscriptionError("Audio transcription returned no usable segments")

    return {
        "model": config.OPENAI_AUDIO_MODEL,
        "language": language,
        "segments": segments,
        "text": "\n".join(f"{item['speaker_id']}:{item['text']}" for item in segments),
        "raw": response_json,
    }


def transcribe_audio_file(path: str | Path, language: str = "zh") -> dict:
    audio_path = Path(path)
    return transcribe_audio_bytes(audio_path.read_bytes(), audio_path.name, mimetypes.guess_type(audio_path.name)[0], language=language)


def transcribe_audio_chunk_bytes(
    audio_bytes: bytes,
    filename: str,
    mime_type: str | None = None,
    language: str = "zh",
    speaker_id: str = "speaker_a",
    start_ms: int = 0,
    end_ms: int = 0,
) -> dict:
    if not config.OPENAI_API_KEY:
        print(f"[AudioTranscription] missing api key base_url={config.OPENAI_BASE_URL}")
        raise AudioTranscriptionError("OPENAI_API_KEY is not configured")
    if not audio_bytes:
        raise AudioTranscriptionError("Audio chunk is empty")

    detected_mime = mime_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    model = getattr(config, "OPENAI_REALTIME_TRANSCRIPTION_MODEL", "") or config.OPENAI_AUDIO_MODEL
    fields = {
        "model": model,
        "response_format": "json",
        "language": language,
    }
    body, boundary = _multipart_body(fields, "file", filename, audio_bytes, detected_mime)
    req = request.Request(
        f"{config.OPENAI_BASE_URL}/audio/transcriptions",
        data=body,
        headers={
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            response_json = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise AudioTranscriptionError(f"Chunk transcription failed: {exc}") from exc

    text = str(response_json.get("text") or "").strip()
    if not text:
        return {
            "model": model,
            "language": language,
            "text": "",
            "segment": None,
            "raw": response_json,
        }

    segment = {
        "speaker_id": speaker_id.strip() or "speaker_a",
        "text": text,
        "start_ms": int(start_ms or 0),
        "end_ms": int(end_ms or 0),
        "final": True,
    }
    return {
        "model": model,
        "language": language,
        "text": text,
        "segment": segment,
        "raw": response_json,
    }
