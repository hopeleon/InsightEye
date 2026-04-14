"""
本地实时语音识别 WebSocket 服务
使用 FunASR 流式推理 + Silero VAD + CAM++ 实现流式实时识别
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional, Dict
from urllib.parse import parse_qs, urlparse

import numpy as np

from websockets.asyncio.server import serve

from . import config
from .realtime_analyzer import run_rolling_analysis, should_refresh_analysis
from .realtime_disc_analyzer import run_realtime_disc_analysis, should_refresh_realtime_disc
from .realtime_session import store as realtime_store
from .realtime_ws_state import build_session_update, consume_local_transcript_event
from .model_manager import ModelManager, get_model_manager
from .streaming_pipeline import (
    StreamingPipeline,
    create_streaming_pipeline,
    TranscriptDelta,
    SpeechSegment,
)
from .speaker_recognition import (
    SpeakerRecognizer,
    create_speaker_recognizer,
)

# 音频参数
AUDIO_SAMPLE_RATE = 16000

# 专用线程池：LLM/DISC 分析与 ASR 线程池隔离，互不阻塞
_ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="disc_llm")


@dataclass
class AudioSource:
    """音频源处理器"""
    source_name: str
    speaker_id: str
    session_id: str
    client_websocket: Any
    pipeline: Optional[StreamingPipeline] = None
    recognizer: Optional[SpeakerRecognizer] = None
    is_ready: bool = False
    _connection_closed: bool = False  # 连接断开标志，防止向死连接重复发送


@dataclass
class PendingSegment:
    audio_samples: np.ndarray
    text: str
    start_ms: int
    end_ms: int


@dataclass
class AutoRegistrationState:
    """自动声纹注册状态"""
    enabled: bool = True
    interviewer_embedding: Optional[np.ndarray] = None
    candidate_embedding: Optional[np.ndarray] = None
    speaker_recognizer: Optional[SpeakerRecognizer] = None
    auto_register_done: bool = False
    pending_segments: list = field(default_factory=list)  # 注册期间积累的音频片段
    interviewer_samples: list = field(default_factory=list)
    candidate_samples: list = field(default_factory=list)


def _build_disc_update_event(disc: dict, is_partial: bool) -> dict:
    """构建独立 disc.update 消息，供前端饼图动画使用"""
    return {
        "type": "disc.update",
        "dominant_style": disc.get("dominant_style", ""),
        "secondary_style": disc.get("secondary_style", ""),
        "scores": disc.get("scores", {"D": 0, "I": 0, "S": 0, "C": 0}),
        "score_deltas": disc.get("score_deltas", {"D": 0, "I": 0, "S": 0, "C": 0}),
        "confidence": disc.get("confidence", "low"),
        "summary": disc.get("summary", ""),
        "recommended_roles": disc.get("recommended_roles", []),
        "follow_up_hint": disc.get("follow_up_hint", ""),
        "source": disc.get("source", "local_rules"),
        "is_partial": is_partial,
        "updated_at": disc.get("updated_at", 0),
    }


class LocalRealtimeServer:
    """
    本地实时语音识别服务器
    使用流式 VAD + ASR + CAM++ 处理音频，无需外部 API
    """

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = threading.Event()
        self._server = None

        self._model_manager: Optional[ModelManager] = None
        self._initialized = False
        self._bind_error: Optional[Exception] = None

        self._active_sources: Dict[str, AudioSource] = {}

    async def _initialize_models(self) -> None:
        if self._initialized:
            return

        print("[LocalRealtimeServer] 正在初始化模型...")
        sys.stdout.flush()

        self._model_manager = get_model_manager()
        await self._model_manager.initialize()

        self._initialized = True
        print("[LocalRealtimeServer] 模型初始化完成")
        sys.stdout.flush()

    def start(self, host: str = "127.0.0.1", port: int | None = None) -> None:
        if self._thread and self._thread.is_alive():
            return

        target_port = port or config.REALTIME_WS_PORT
        self._bind_error = None
        self._started.clear()

        self._thread = threading.Thread(target=self._run, args=(host, target_port), daemon=True)
        self._thread.start()

        if not self._started.wait(timeout=10):
            if self._bind_error:
                print(f"[LocalRealtimeServer] 启动失败: {self._bind_error}")
            else:
                print("[LocalRealtimeServer] 启动超时，可能端口被占用或事件循环未正常启动")

    def _run(self, host: str, port: int) -> None:
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def init_and_serve():
                await self._initialize_models()
                await self._serve(host, port)

            self._loop.run_until_complete(init_and_serve())
            self._started.set()
            self._loop.run_forever()
        except OSError as exc:
            self._bind_error = exc
            self._started.set()
            print(f"[LocalRealtimeServer] WebSocket 服务启动失败: {exc}")
            sys.stdout.flush()
        except Exception as exc:
            self._bind_error = exc
            self._started.set()
            print(f"[LocalRealtimeServer] 运行异常: {exc}")
            sys.stdout.flush()

    async def _serve(self, host: str, port: int) -> None:
        if self._server is not None:
            print(f"[LocalRealtimeServer] WebSocket 服务器已存在，跳过重复启动 ws://{host}:{port}/realtime")
            return

        print("[LocalRealtimeServer] 开始启动 WebSocket 服务器...")
        self._server = await serve(self._handle_client, host, port, max_size=2**22)
        print(f"[LocalRealtimeServer] WebSocket 服务已启动 ws://{host}:{port}/realtime")
        sys.stdout.flush()

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

        await self._initialize_models()

        sources: Dict[str, AudioSource] = {}
        for source_name, speaker_id in SOURCE_TO_SPEAKER.items():
            sources[source_name] = AudioSource(
                source_name=source_name,
                speaker_id=speaker_id,
                session_id=session_id,
                client_websocket=websocket,
            )

        speaker_recognizer = create_speaker_recognizer(self._model_manager)

        auto_reg = AutoRegistrationState(
            enabled=True,
            speaker_recognizer=speaker_recognizer,
        )
        print("[Server] 自动声纹注册模式已默认开启，无需前端触发")

        with realtime_store._lock:
            raw = realtime_store._sessions.get(session_id, {})
            raw["speaker_recognizer"] = speaker_recognizer

        realtime_store.register_ws_client(session_id, websocket)

        try:
            await websocket.send(json.dumps({
                "type": "session.ready",
                "session_id": session_id,
                "message": "本地流式 FunASR + CAM++ 实时识别已就绪",
                "provider": "local",
                "supports_registration": True,
                "supports_auto_registration": True,
                "streaming": True,
            }, ensure_ascii=False))
            print(f"[WS发送] → 发送 session.ready (本地模式), session_id={session_id}")

            async for raw_message in websocket:
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue

                try:
                    message_type = str(message.get("type") or "")

                    if message_type == "audio_chunk":
                        await self._handle_audio_chunk(
                            sources, message, websocket, auto_reg, language
                        )

                    elif message_type == "start_registration":
                        auto_reg.enabled = False
                        auto_reg.interviewer_samples = []
                        auto_reg.candidate_samples = []
                        await websocket.send(json.dumps({
                            "type": "registration.started",
                            "mode": "manual",
                            "phase": "interviewer",
                            "message": "请面试官说话录音（至少2段）",
                        }, ensure_ascii=False))

                    elif message_type == "start_auto_registration":
                        auto_reg.enabled = True
                        auto_reg.interviewer_embedding = None
                        auto_reg.candidate_embedding = None
                        auto_reg.auto_register_done = False
                        print("[Server] 收到 start_auto_registration，重新开启自动声纹注册")
                        print("[Server] 等待音频片段开始注册流程...")
                        await websocket.send(json.dumps({
                            "type": "auto_registration.started",
                            "message": "请第一位说话人开始发言",
                        }, ensure_ascii=False))

                    elif message_type == "add_registration_sample":
                        phase = str(message.get("phase") or "interviewer")
                        audio_b64 = str(message.get("audio") or "")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            audio_float32 = self._bytes_to_audio(audio_bytes)
                            if phase == "interviewer":
                                if len(audio_float32) >= AUDIO_SAMPLE_RATE * 0.5:
                                    auto_reg.interviewer_samples.append(audio_float32)
                            else:
                                if len(audio_float32) >= AUDIO_SAMPLE_RATE * 0.5:
                                    auto_reg.candidate_samples.append(audio_float32)
                            await websocket.send(json.dumps({
                                "type": "registration.sample_added",
                                "phase": phase,
                                "interviewer_samples": len(auto_reg.interviewer_samples),
                                "candidate_samples": len(auto_reg.candidate_samples),
                                "samples_needed": 2,
                            }, ensure_ascii=False))

                    elif message_type == "finish_registration":
                        if len(auto_reg.interviewer_samples) < 2:
                            await websocket.send(json.dumps({
                                "type": "registration.finished",
                                "success": False,
                                "message": "面试官样本不足（需要至少2段）",
                            }, ensure_ascii=False))
                        elif len(auto_reg.candidate_samples) < 2:
                            await websocket.send(json.dumps({
                                "type": "registration.finished",
                                "success": False,
                                "message": "候选人样本不足（需要至少2段）",
                            }, ensure_ascii=False))
                        else:
                            int_result = speaker_recognizer.register_speaker(
                                "interviewer", auto_reg.interviewer_samples, name="面试官", role="interviewer"
                            )
                            cand_result = speaker_recognizer.register_speaker(
                                "candidate", auto_reg.candidate_samples, name="候选人", role="candidate"
                            )
                            if int_result.success and cand_result.success:
                                session["speaker_recognizer"] = speaker_recognizer
                                session["voice_registered"] = True
                                session["voice_mapping"] = {
                                    "interviewer": "interviewer",
                                    "candidate": "candidate",
                                }
                                print("[Server] 手动注册完成，session 状态已同步: voice_registered=True")
                                for source in sources.values():
                                    if source.pipeline:
                                        for sid, profile in speaker_recognizer.speakers.items():
                                            if profile.embedding is not None:
                                                source.pipeline.register_speaker(sid, profile.embedding)
                                print(f"[Server] 声纹注册完成，共 {len(speaker_recognizer.speakers)} 位说话人")
                            await websocket.send(json.dumps({
                                "type": "registration.finished",
                                "success": int_result.success and cand_result.success,
                                "voice_registered": int_result.success and cand_result.success,
                                "voice_mapping": {
                                    "interviewer": "interviewer",
                                    "candidate": "candidate",
                                } if int_result.success and cand_result.success else {},
                                "message": f"面试官: {int_result.message}, 候选人: {cand_result.message}",
                            }, ensure_ascii=False))
                            print(f"[WS发送] → 发送 registration.finished: success={int_result.success and cand_result.success}, "
                                  f"voice_registered={int_result.success and cand_result.success}")

                    elif message_type == "get_registration_status":
                        await websocket.send(json.dumps({
                            "type": "registration.status",
                            "interviewer_samples": len(auto_reg.interviewer_samples),
                            "candidate_samples": len(auto_reg.candidate_samples),
                            "samples_needed": 2,
                            "auto_mode": auto_reg.enabled,
                            "auto_done": auto_reg.auto_register_done,
                        }, ensure_ascii=False))

                    elif message_type == "close":
                        break

                    else:
                        print(f"[Server] 未知消息类型: {message_type}")

                except Exception as exc:
                    print(f"[Server] 处理消息错误: {exc}")
                    import traceback
                    traceback.print_exc()
                    try:
                        await websocket.send(json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False))
                    except Exception:
                        pass

        finally:
            realtime_store.unregister_ws_client(session_id, websocket)
            for source in sources.values():
                if source.pipeline:
                    asyncio.create_task(source.pipeline.stop())
                    source.pipeline.reset()
            with contextlib.suppress(Exception):
                await websocket.close()

    async def _handle_audio_chunk(
        self,
        sources: Dict[str, AudioSource],
        message: dict,
        websocket,
        auto_reg: AutoRegistrationState,
        language: str,
    ) -> None:
        source_name = str(message.get("source") or "system").strip()
        audio_b64 = str(message.get("audio") or "")

        if not audio_b64 or source_name not in sources:
            return

        source = sources[source_name]

        try:
            audio_bytes = base64.b64decode(audio_b64)
        except Exception as e:
            print(f"[LocalRealtimeServer] 音频解码失败: {e}")
            return

        audio_float32 = self._bytes_to_audio(audio_bytes)
        audio_duration = len(audio_float32) / 16000

        if not hasattr(self, "_audio_logged") or not self._audio_logged:
            is_init = self._model_manager.is_initialized() if self._model_manager else False
            vad_model = self._model_manager.get_vad_model() if self._model_manager else None
            print(f"[Server] 收到音频: source={source_name}, 时长={audio_duration:.2f}s, 模型已初始化={is_init}, VAD模型={'有' if vad_model else '无'}")
            self._audio_logged = True

        if source.pipeline is None:
            if not self._model_manager.is_initialized():
                return
            vad_model = self._model_manager.get_vad_model()
            if vad_model is None:
                return

            source.pipeline = create_streaming_pipeline(self._model_manager, language)

            source.pipeline.on_transcript = lambda delta: self._on_transcript_delta(delta, source, websocket)
            source.pipeline.on_speaker = lambda sid, score: self._on_speaker_identified(sid, score, source, websocket)
            source.pipeline.on_speech_segment = lambda seg: self._on_speech_segment_for_auto_reg(seg, sources, auto_reg)

            await source.pipeline.start()
            print("[Server] 管道已创建并启动")

        await source.pipeline.feed_audio(audio_float32)

    async def _on_speech_segment_for_auto_reg(
        self,
        segment,
        sources: Dict[str, AudioSource],
        auto_reg: AutoRegistrationState,
    ) -> None:
        if not auto_reg.enabled or auto_reg.auto_register_done:
            return

        duration = len(segment.audio_data) / 16000
        print(f"[AutoReg] VAD 段落触发，时长={duration:.2f}s")

        if not sources:
            return
        first_source = next(iter(sources.values()))
        websocket = first_source.client_websocket
        session_id = first_source.session_id

        with realtime_store._lock:
            raw = realtime_store._sessions.get(session_id, {})
            raw.setdefault("pending_audio", []).append({
                "audio_samples": segment.audio_data,
                "start_ms": getattr(segment, "start_ms", 0),
                "end_ms": getattr(segment, "end_ms", 0),
            })

        asyncio.create_task(
            self._process_auto_registration(
                segment.audio_data, sources, websocket, auto_reg, session_id=session_id
            )
        )

    async def _process_auto_registration(
        self,
        audio_float32: np.ndarray,
        sources: Dict[str, AudioSource],
        websocket,
        auto_reg: AutoRegistrationState,
        session_id: str | None = None,
    ) -> None:
        if auto_reg.auto_register_done:
            return

        try:
            extractor = auto_reg.speaker_recognizer.extractor
            new_embedding = extractor.extract(audio_float32)
            similarity_to_interviewer = extractor.compute_similarity(
                new_embedding, auto_reg.interviewer_embedding
            ) if auto_reg.interviewer_embedding is not None else 1.0

            if auto_reg.interviewer_embedding is None:
                auto_reg.interviewer_embedding = new_embedding
                print("[AutoReg] 第一位说话人（面试官）已记录")
                await websocket.send(json.dumps({
                    "type": "auto_registration.progress",
                    "phase": "interviewer",
                    "message": "面试官已识别，请让候选人说话...",
                }, ensure_ascii=False))
                return

            if similarity_to_interviewer < 0.75:
                if auto_reg.candidate_embedding is None:
                    auto_reg.candidate_embedding = new_embedding
                    print(f"[AutoReg] 第二位说话人（候选人）已记录，与面试官相似度={similarity_to_interviewer:.3f}")
                    await websocket.send(json.dumps({
                        "type": "auto_registration.candidate_found",
                        "message": "检测到第二位说话人，正在注册...",
                    }, ensure_ascii=False))
                else:
                    auto_reg.candidate_embedding = (
                        0.7 * auto_reg.candidate_embedding + 0.3 * new_embedding
                    )
                    auto_reg.candidate_embedding = auto_reg.candidate_embedding / (
                        np.linalg.norm(auto_reg.candidate_embedding) + 1e-8
                    )

                int_result = auto_reg.speaker_recognizer.register_embedding(
                    "interviewer", auto_reg.interviewer_embedding, name="面试官", role="interviewer"
                )
                cand_result = auto_reg.speaker_recognizer.register_embedding(
                    "candidate", auto_reg.candidate_embedding, name="候选人", role="candidate"
                )

                if int_result.success and cand_result.success:
                    auto_reg.auto_register_done = True
                    auto_reg.enabled = False
                    print(f"[AutoReg] ★ 声纹注册完成（面试官质量={int_result.embedding_quality:.2f}, 候选人质量={cand_result.embedding_quality:.2f}）")

                    for src in sources.values():
                        if src.pipeline:
                            src.pipeline.register_speaker("interviewer", auto_reg.interviewer_embedding)
                            src.pipeline.register_speaker("candidate", auto_reg.candidate_embedding)
                            print(f"[AutoReg] 已同步声纹到管道: {src.source_name}")

                    if session_id:
                        session = realtime_store.get(session_id)
                        if session:
                            session["voice_registered"] = True
                            session["voice_mapping"] = {
                                "interviewer": "interviewer",
                                "candidate": "candidate",
                            }
                            session["speaker_recognizer"] = auto_reg.speaker_recognizer
                            print("[AutoReg] session 状态已同步: voice_registered=True")

                            await websocket.send(json.dumps({
                                "type": "auto_registration.completed",
                                "success": True,
                                "message": "声纹注册成功！面试官和候选人已自动识别",
                                "voice_registered": True,
                                "voice_mapping": {
                                    "interviewer": "interviewer",
                                    "candidate": "candidate",
                                },
                            }, ensure_ascii=False))
                            print("[WS发送] → 发送 auto_registration.completed: voice_registered=True, voice_mapping={interviewer=interviewer, candidate=candidate}")
                else:
                    print(f"[AutoReg] 注册失败: 面试官={int_result.message}, 候选人={cand_result.message}")
            else:
                auto_reg.interviewer_embedding = (
                    0.8 * auto_reg.interviewer_embedding + 0.2 * new_embedding
                )
                auto_reg.interviewer_embedding = auto_reg.interviewer_embedding / (
                    np.linalg.norm(auto_reg.interviewer_embedding) + 1e-8
                )
                print(f"[AutoReg] 面试官新片段（相似度={similarity_to_interviewer:.3f}），等待候选人...")

        except Exception as e:
            print(f"[AutoReg] 处理失败: {e}")
            import traceback
            traceback.print_exc()

    async def _async_disc_refresh(
        self,
        session_id: str,
        websocket,
        source: AudioSource,
        is_partial: bool,
    ) -> None:
        """在线程池中异步执行 rolling analysis + DISC 分析，完成后推送结果，不阻塞事件循环"""
        if source._connection_closed:
            return
        session = realtime_store.get(session_id)
        if not session:
            return

        loop = asyncio.get_event_loop()

        try:
            if should_refresh_analysis(session):
                await loop.run_in_executor(_ANALYSIS_EXECUTOR, run_rolling_analysis, session)
                if source._connection_closed:
                    return
                rolling_update = build_session_update(session_id)
                if rolling_update:
                    await websocket.send(json.dumps(rolling_update, ensure_ascii=False))

            if not should_refresh_realtime_disc(session):
                return
            disc_result = await loop.run_in_executor(
                _ANALYSIS_EXECUTOR, run_realtime_disc_analysis, session
            )
            if source._connection_closed:
                return
            if not disc_result.get("ready"):
                return

            session_update = build_session_update(session_id)
            if session_update:
                rolling_disc = session_update.get("session", {}).get("rolling_disc_analysis", {})
                print(
                    f"[DISC] async refresh done, ready={rolling_disc.get('ready')}, "
                    f"partial={is_partial}, source={rolling_disc.get('source')}"
                )
                await websocket.send(json.dumps(session_update, ensure_ascii=False))

            disc_event = _build_disc_update_event(disc_result, is_partial=is_partial)
            await websocket.send(json.dumps(disc_event, ensure_ascii=False))

        except Exception as e:
            exc_type = type(e).__name__
            exc_mod = type(e).__module__
            if "ConnectionClosed" in exc_type or (exc_mod and "websockets" in exc_mod):
                source._connection_closed = True
                if source.pipeline:
                    asyncio.create_task(source.pipeline.stop())
            else:
                print(f"[LocalRealtimeServer] DISC 异步刷新错误: {e}")

    def _bytes_to_audio(self, audio_bytes: bytes) -> np.ndarray:
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        return audio_int16.astype(np.float32) / 32768.0

    async def _on_transcript_delta(
        self,
        delta: TranscriptDelta,
        source: AudioSource,
        websocket,
    ) -> None:
        if source._connection_closed:
            return
        try:
            if not delta.text.strip():
                return

            raw_speaker = delta.speaker_id or source.speaker_id

            speaker_display = raw_speaker
            if raw_speaker == "interviewer":
                speaker_display = "面试官"
            elif raw_speaker == "candidate":
                speaker_display = "候选人"
            elif raw_speaker == "speaker_unk":
                speaker_display = "未知说话人"

            int_sim_str = f" 面试官={delta.interviewer_sim:.2f}" if delta.interviewer_sim > 0 else ""
            cand_sim_str = f" 候选人={delta.candidate_sim:.2f}" if delta.candidate_sim > 0 else ""
            confidence_str = f" ({int_sim_str}{cand_sim_str})" if int_sim_str or cand_sim_str else ""
            reason_str = f" [{delta.segment_reason}]" if delta.segment_reason else ""
            print(f"[转录] 【{speaker_display}{confidence_str}{reason_str}】 {delta.text[:50]}{'...' if len(delta.text) > 50 else ''}")

            event = {
                "type": "transcript.delta" if not delta.is_final else "transcript.completed",
                "source": source.source_name,
                "speaker_id": raw_speaker,
                "text": delta.text,
                "is_final": delta.is_final,
                "start_ms": delta.start_ms,
                "end_ms": delta.end_ms,
                "speaker_confidence": float(delta.speaker_confidence),
                "segment_reason": delta.segment_reason,
                "interviewer_sim": float(delta.interviewer_sim),
                "candidate_sim": float(delta.candidate_sim),
                "recognized_role": getattr(delta, "recognized_role", None),
            }

            print(f"[WS发送] → 发送 {event['type']}: speaker_id={raw_speaker}, recognized_role={event.get('recognized_role')}, "
                  f"interviewer_sim={event['interviewer_sim']}, candidate_sim={event['candidate_sim']}, is_final={event['is_final']}, text={delta.text[:30]}")
            await websocket.send(json.dumps(event, ensure_ascii=False))

            recognized_speaker = delta.speaker_id or source.speaker_id

            if not delta.is_final and recognized_speaker:
                realtime_store.update_partial_transcript(
                    source.session_id,
                    recognized_speaker,
                    delta.text,
                    recognized_role=event.get("recognized_role"),
                    interviewer_sim=event["interviewer_sim"],
                    candidate_sim=event["candidate_sim"],
                )
                asyncio.create_task(
                    self._async_disc_refresh(source.session_id, websocket, source, is_partial=True)
                )

            if delta.is_final and recognized_speaker:
                session_update = consume_local_transcript_event(
                    source.session_id,
                    recognized_speaker,
                    event,
                )

                if session_update:
                    corrections = session_update.get("segment_corrections", [])
                    segments = session_update.get("session", {}).get("segments", [])
                    for i, seg in enumerate(segments):
                        print(f"[WS发送] segment[{i}]: speaker_id={seg.get('speaker_id')}, recognized_role={seg.get('recognized_role')}, "
                              f"interviewer_sim={seg.get('interviewer_sim')}, candidate_sim={seg.get('candidate_sim')}, "
                              f"text={str(seg.get('text') or '')[:30]}")
                    print(f"[WS发送] -> 发送 session.update 到前端，segments 共 {len(segments)} 条，corrections={corrections}")
                    await websocket.send(json.dumps(session_update, ensure_ascii=False))

                    if corrections:
                        for idx in corrections:
                            seg = session_update["session"]["segments"][idx]
                            await websocket.send(json.dumps({
                                "type": "segment.corrected",
                                "index": idx,
                                "old_role": "interviewer",
                                "new_role": "candidate",
                                "text": seg.get("text", ""),
                                "speaker_id": seg.get("speaker_id", ""),
                                "interviewer_sim": seg.get("interviewer_sim", 0),
                                "candidate_sim": seg.get("candidate_sim", 0),
                            }, ensure_ascii=False))
                            print(f"[修正] 片段 {idx} 角色已修正: 面试官 → 候选人（{seg.get('text', '')[:30]}...）")
                            print(f"[WS发送] → 发送 segment.corrected: index={idx}, new_role=candidate")

                    asyncio.create_task(
                        self._async_disc_refresh(source.session_id, websocket, source, is_partial=False)
                    )

        except (ConnectionError, OSError):
            source._connection_closed = True
            if source.pipeline:
                asyncio.create_task(source.pipeline.stop())
        except Exception as e:
            exc_type = type(e).__name__
            exc_mod = type(e).__module__
            if "ConnectionClosed" in exc_type or (exc_mod and "websockets" in exc_mod):
                print(f"[LocalRealtimeServer] 连接已断开，停止推送: {e}")
                source._connection_closed = True
                if source.pipeline:
                    asyncio.create_task(source.pipeline.stop())
            else:
                print(f"[LocalRealtimeServer] 转录回调错误: {e}")

    async def _on_speaker_identified(
        self,
        speaker_id: str,
        confidence: float,
        source: AudioSource,
        websocket,
    ) -> None:
        if source._connection_closed:
            return
        try:
            await websocket.send(json.dumps({
                "type": "speaker.identified",
                "source": source.source_name,
                "speaker_id": speaker_id,
                "confidence": confidence,
            }, ensure_ascii=False))
        except Exception as e:
            exc_type = type(e).__name__
            exc_mod = type(e).__module__
            if "ConnectionClosed" in exc_type or (exc_mod and "websockets" in exc_mod):
                print(f"[LocalRealtimeServer] 连接已断开（声纹回调）: {e}")
                source._connection_closed = True
                if source.pipeline:
                    asyncio.create_task(source.pipeline.stop())
            else:
                print(f"[LocalRealtimeServer] 声纹回调错误: {e}")


SOURCE_TO_SPEAKER = {
    "mic": "speaker_a",
    "system": "speaker_b",
}


_server_instance: Optional[LocalRealtimeServer] = None


def get_realtime_server() -> LocalRealtimeServer:
    """获取全局实时服务器实例"""
    global _server_instance
    if _server_instance is None:
        _server_instance = LocalRealtimeServer()
    return _server_instance


bridge_server = get_realtime_server()


async def start_realtime_server(host: str = "127.0.0.1", port: int | None = None) -> None:
    """启动实时服务器（协程版本）"""
    server = LocalRealtimeServer()
    await server._initialize_models()
    await server._serve(host, port or config.REALTIME_WS_PORT)
