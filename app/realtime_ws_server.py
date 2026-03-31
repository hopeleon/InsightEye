from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from . import config
from .realtime_session import store as realtime_store
from .realtime_ws_state import consume_realtime_event

SOURCE_TO_SPEAKER = {"mic": "speaker_a", "system": "speaker_b"}


def _event_id(prefix: str) -> str:
    return f"{prefix}_{int(asyncio.get_running_loop().time() * 1000)}"


@dataclass
class SourceBridge:
    source_name: str
    speaker_id: str
    session_id: str
    language: str
    client_websocket: Any
    upstream_websocket: Any | None = None
    reader_task: asyncio.Task | None = None

    async def ensure_connected(self) -> None:
        if self.upstream_websocket is not None:
            return
        model = quote(config.DASHSCOPE_REALTIME_ASR_MODEL, safe="")
        url = f"{config.DASHSCOPE_REALTIME_WS_URL}?model={model}"
        headers = {
            "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
            "OpenAI-Beta": "realtime=v1",
        }
        print(f"[DashScopeRealtime] connect source={self.source_name} url={config.DASHSCOPE_REALTIME_WS_URL} model={config.DASHSCOPE_REALTIME_ASR_MODEL}")
        self.upstream_websocket = await connect(url, additional_headers=headers, max_size=2**22)
        self.reader_task = asyncio.create_task(self._read_loop())
        await self.upstream_websocket.send(
            json.dumps(
                {
                    "event_id": _event_id("event"),
                    "type": "session.update",
                    "session": {
                        "modalities": ["text"],
                        "input_audio_format": "pcm",
                        "sample_rate": 16000,
                        "input_audio_transcription": {
                            "language": self.language,
                        },
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": 0.0,
                            "silence_duration_ms": 400,
                        },
                    },
                },
                ensure_ascii=False,
            )
        )
        await self.client_websocket.send(
            json.dumps(
                {
                    "type": "source.ready",
                    "source": self.source_name,
                    "speaker_id": self.speaker_id,
                    "model": config.DASHSCOPE_REALTIME_ASR_MODEL,
                },
                ensure_ascii=False,
            )
        )

    async def append(self, audio: str) -> None:
        await self.ensure_connected()
        await self.upstream_websocket.send(
            json.dumps(
                {
                    "event_id": _event_id("event"),
                    "type": "input_audio_buffer.append",
                    "audio": audio,
                }
            )
        )

    async def commit(self) -> None:
        if self.upstream_websocket is None:
            return
        await self.upstream_websocket.send(json.dumps({"event_id": _event_id("event"), "type": "input_audio_buffer.commit"}))

    async def finish(self) -> None:
        if self.upstream_websocket is None:
            return
        with contextlib.suppress(Exception):
            await self.commit()
        with contextlib.suppress(Exception):
            await self.upstream_websocket.send(json.dumps({"event_id": _event_id("event"), "type": "session.finish"}))

    async def close(self) -> None:
        if self.upstream_websocket is None:
            return
        await self.finish()
        with contextlib.suppress(Exception):
            await self.upstream_websocket.close()
        if self.reader_task is not None:
            self.reader_task.cancel()
            with contextlib.suppress(Exception):
                await self.reader_task
        self.reader_task = None
        self.upstream_websocket = None

    async def _read_loop(self) -> None:
        assert self.upstream_websocket is not None
        try:
            async for raw_message in self.upstream_websocket:
                try:
                    event = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                payload = consume_realtime_event(self.session_id, self.speaker_id, event)
                if payload is not None:
                    payload.setdefault("source", self.source_name)
                    await self.client_websocket.send(json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            await self.client_websocket.send(
                json.dumps(
                    {
                        "type": "error",
                        "source": self.source_name,
                        "message": str(exc),
                        "hint": "DashScope realtime upstream closed unexpectedly.",
                    },
                    ensure_ascii=False,
                )
            )


class RealtimeBridgeServer:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()
        self._server = None

    def start(self, host: str = "127.0.0.1", port: int | None = None) -> None:
        if self._thread and self._thread.is_alive():
            return
        target_port = port or config.REALTIME_WS_PORT
        self._thread = threading.Thread(target=self._run, args=(host, target_port), daemon=True)
        self._thread.start()
        self._started.wait(timeout=5)

    def _run(self, host: str, port: int) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve(host, port))
        self._started.set()
        self._loop.run_forever()

    async def _serve(self, host: str, port: int) -> None:
        self._server = await serve(self._handle_client, host, port, max_size=2**22)

    async def _handle_client(self, websocket) -> None:
        request = getattr(websocket, "request", None)
        path = getattr(request, "path", "/")
        parsed = urlparse(path)
        if parsed.path != "/realtime":
            await websocket.send(json.dumps({"type": "error", "message": "Invalid websocket path"}))
            await websocket.close()
            return

        query = parse_qs(parsed.query)
        session_id = (query.get("session_id") or [""])[0].strip()
        language = (query.get("language") or ["zh"])[0].strip() or "zh"
        if not session_id:
            await websocket.send(json.dumps({"type": "error", "message": "Missing session_id"}))
            await websocket.close()
            return

        session = realtime_store.get(session_id)
        if not session:
            await websocket.send(json.dumps({"type": "error", "message": "Realtime session not found"}))
            await websocket.close()
            return

        if not config.DASHSCOPE_API_KEY:
            await websocket.send(json.dumps({"type": "error", "message": "DASHSCOPE_API_KEY is not configured"}, ensure_ascii=False))
            await websocket.close()
            return

        bridges = {
            source_name: SourceBridge(source_name, speaker_id, session_id, language, websocket)
            for source_name, speaker_id in SOURCE_TO_SPEAKER.items()
        }

        try:
            await websocket.send(
                json.dumps(
                    {
                        "type": "session.ready",
                        "session_id": session_id,
                        "message": "DashScope realtime bridge connected",
                        "model": config.DASHSCOPE_REALTIME_ASR_MODEL,
                        "provider": "dashscope",
                    },
                    ensure_ascii=False,
                )
            )
            async for raw_message in websocket:
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid client JSON"}))
                    continue

                message_type = str(message.get("type") or "")
                source_name = str(message.get("source") or "").strip() or "system"
                bridge = bridges.get(source_name)
                if bridge is None:
                    await websocket.send(json.dumps({"type": "error", "message": f"Unknown source: {source_name}"}))
                    continue

                if message_type == "audio_chunk":
                    audio = str(message.get("audio") or "")
                    if audio:
                        await bridge.append(audio)
                elif message_type == "commit":
                    await bridge.commit()
                elif message_type == "close":
                    break
        except Exception as exc:
            print(f"[DashScopeRealtime] {exc}")
            with contextlib.suppress(Exception):
                await websocket.send(json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False))
        finally:
            for bridge in bridges.values():
                with contextlib.suppress(Exception):
                    await bridge.close()
            with contextlib.suppress(Exception):
                await websocket.close()


bridge_server = RealtimeBridgeServer()
