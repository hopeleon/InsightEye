from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from urllib.parse import quote

import websockets


BASE_DIR = Path(__file__).resolve().parent


def load_local_settings() -> dict:
    path = BASE_DIR / "local_settings.py"
    if not path.exists():
        return {}
    namespace: dict = {}
    content = path.read_text(encoding="utf-8").lstrip("\ufeff")
    exec(content, namespace)
    return namespace


async def main() -> int:
    settings = load_local_settings()

    api_key = str(settings.get("OPENAI_API_KEY", "")).strip()
    ws_base = str(settings.get("OPENAI_WEBSOCKET_BASE_URL", "")).strip()
    model = str(settings.get("OPENAI_REALTIME_TRANSCRIPTION_MODEL", "gpt-4o-transcribe")).strip()
    language = str(settings.get("REALTIME_TEST_LANGUAGE", "zh")).strip() or "zh"

    if not api_key:
        print("OPENAI_API_KEY is missing in local_settings.py")
        return 1

    if not ws_base:
        print("OPENAI_WEBSOCKET_BASE_URL is missing in local_settings.py")
        return 1

    url = f"{ws_base.rstrip('/')}/realtime?model={quote(model)}"
    headers = {"Authorization": f"Bearer {api_key}"}

    print(f"Connecting to: {url}")
    print("Sending auth header and session.update for transcription mode")

    try:
        async with websockets.connect(url, additional_headers=headers, max_size=2**22) as ws:
            print("WebSocket connected")

            await ws.send(
                json.dumps(
                    {
                        "type": "session.update",
                        "session": {
                            "type": "transcription",
                            "audio": {
                                "input": {
                                    "format": {"type": "audio/pcm", "rate": 24000},
                                    "noise_reduction": {"type": "near_field"},
                                    "transcription": {"model": model, "language": language},
                                    "turn_detection": {
                                        "type": "server_vad",
                                        "threshold": 0.45,
                                        "prefix_padding_ms": 300,
                                        "silence_duration_ms": 500,
                                    },
                                }
                            },
                        },
                    },
                    ensure_ascii=False,
                )
            )
            print("session.update sent")

            for index in range(5):
                try:
                    message = await asyncio.wait_for(ws.recv(), timeout=8)
                except asyncio.TimeoutError:
                    print("Timed out waiting for server event")
                    return 2

                print(f"Event #{index + 1}:")
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    print(message)
                    continue
                print(json.dumps(payload, ensure_ascii=False, indent=2))

            return 0
    except Exception as exc:
        print(f"Realtime WebSocket test failed: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
