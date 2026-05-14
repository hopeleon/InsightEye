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
from typing import Any, Optional, Dict, List
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
from .enhanced_speaker_recognition import (
    MultiSpeakerRegistry,
    create_multi_speaker_registry,
)

# 音频参数
AUDIO_SAMPLE_RATE = 16000

# 专用线程池：LLM/DISC 分析与 ASM 线程池隔离，互不阻塞
_ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="disc_llm")

# pending_audio 队列最大长度（FIFO，超过则丢弃最旧的）
_MAX_PENDING_AUDIO = 20


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


# ==================== 模式一：双人自动注册状态 ====================

@dataclass
class PendingSegment:
    audio_samples: np.ndarray
    text: str
    start_ms: int
    end_ms: int

@dataclass
class AutoRegistrationState:
    """自动声纹注册状态（模式一：双人）"""
    enabled: bool = True
    interviewer_embedding: Optional[np.ndarray] = None
    candidate_embedding: Optional[np.ndarray] = None
    speaker_recognizer: Optional[SpeakerRecognizer] = None
    auto_register_done: bool = False
    pending_segments: list = field(default_factory=list)
    interviewer_samples: list = field(default_factory=list)
    candidate_samples: list = field(default_factory=list)


# ==================== 模式二：多人自动识别状态（无需手动注册） ====================

@dataclass
class AutoMultiState:
    """
    自动声纹识别状态（模式二：多人）
    每次会议开始时，自动从公司声纹数据库加载所有在职员工的声纹，
    对进入会议室的人进行实时识别，无需手动注册。
    """
    enabled: bool = False
    # SpeakerDatabase 实例（通过 session["speaker_database"] 访问）
    # MultiSpeakerRegistry 实例（识别引擎）
    registry: Optional[MultiSpeakerRegistry] = None
    # 入会时从 DB 加载的说话人数量
    db_speaker_count: int = 0
    # 入会时从 DB 加载的说话人信息 [{speaker_id, name, role, department}, ...]
    db_speakers: List[dict] = field(default_factory=list)
    # 是否已尝试过初始化（避免重复发送 VAD 未就绪错误）
    initialized: bool = False


# ==================== Benchmark 模式状态 ====================

@dataclass
class BenchmarkState:
    """
    Benchmark 测试模式状态。
    当开启时，系统正常转录，但会与预置答案比对并计算准确率。
    """
    enabled: bool = False
    # 预置答案文本，格式: [{"text": "答案1", "speaker_id": "speaker1"}, ...]
    reference_texts: List[dict] = field(default_factory=list)
    # 当前正在等待比对的转录结果队列
    pending_hypotheses: List[dict] = field(default_factory=list)
    # 最终评估结果
    final_results: dict = field(default_factory=dict)
    # 是否已完成评估
    evaluation_done: bool = False
    # DB 中的说话人列表，用于姓名映射
    db_speakers: List[dict] = field(default_factory=list)


def _levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串之间的 Levenshtein 编辑距离"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _compute_wer(reference: str, hypothesis: str) -> float:
    """
    计算 Word Error Rate (WER)。
    WER = 编辑距离 / 参考词数，值越小越好，0 表示完全一致。
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0
    dist = _levenshtein_distance(ref_words, hyp_words)
    return dist / len(ref_words)


def _compute_cer(reference: str, hypothesis: str) -> float:
    """
    计算 Character Error Rate (CER)。
    CER = 编辑距离 / 参考字符数，值越小越好，0 表示完全一致。
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0
    dist = _levenshtein_distance(reference, hypothesis)
    return dist / len(reference)


def _merge_hypotheses_by_speaker(hypotheses: List[dict], reference_texts: List[dict]) -> List[dict]:
    """
    将 pending_hypotheses 按说话人合并，再与 reference_texts 逐一对应。
    同一个人说的多个小段 → 合并成完整句子 → 再和对应的参考文本对比。
    """
    merged_by_speaker: dict = {}
    for h in hypotheses:
        sid = h.get("speaker_id", "") or ""
        if sid not in merged_by_speaker:
            merged_by_speaker[sid] = {"text": "", "speaker_id": sid, "segments": []}
        text = h.get("text", "").strip()
        if text:
            merged_by_speaker[sid]["text"] += text + " "
            merged_by_speaker[sid]["segments"].append(text)

    for sid in merged_by_speaker:
        merged_by_speaker[sid]["text"] = merged_by_speaker[sid]["text"].strip()

    results = []
    for ref in reference_texts:
        ref_sid = ref.get("speaker_id", "") or ""
        ref_text = ref.get("text", "").strip()
        ref_name = ref.get("speaker_name", "") or ""
        hyp = merged_by_speaker.get(ref_sid, {"text": "", "speaker_id": ref_sid, "segments": []})
        results.append({
            "reference": ref_text,
            "hypothesis": hyp["text"],
            "reference_speaker": ref_sid,
            "recognized_speaker": hyp["speaker_id"],
            "reference_speaker_name": ref_name or ref_sid,
            "_segments": hyp["segments"],
        })
    return results


def _evaluate_merged(results: List[dict], db_speakers: List[dict] = None) -> dict:
    """对合并后的 results 计算各项指标。"""
    # 建立 speaker_id → 姓名的映射
    speaker_name_map = {}
    if db_speakers:
        for sp in db_speakers:
            sid = sp.get("speaker_id", "")
            name = sp.get("name", "")
            if sid and name:
                speaker_name_map[str(sid)] = name

    for r in results:
        ref = r["reference"]
        hyp = r["hypothesis"]
        r["wer"] = round(_compute_wer(ref, hyp), 4)
        r["cer"] = round(_compute_cer(ref, hyp), 4)
        r["accuracy"] = round(_compute_accuracy(ref, hyp), 4)
        r["speaker_correct"] = 1 if r["recognized_speaker"] == r["reference_speaker"] else 0

        # 解析姓名
        r["reference_speaker_name"] = speaker_name_map.get(
            str(r["reference_speaker"]), r["reference_speaker"]
        )
        r["recognized_speaker_name"] = speaker_name_map.get(
            str(r["recognized_speaker"]), r["recognized_speaker"]
        )

    total_wer = sum(r["wer"] for r in results) / len(results) if results else 1.0
    total_cer = sum(r["cer"] for r in results) / len(results) if results else 1.0
    total_acc = sum(r["accuracy"] for r in results) / len(results) if results else 0.0
    speaker_acc = sum(r["speaker_correct"] for r in results) / len(results) if results else 0.0

    for i, r in enumerate(results):
        r["index"] = i
        r.pop("_segments", None)

    # 收集标准答案中涉及的所有说话人姓名（去重，保持顺序）
    seen = set()
    involved = []
    for r in results:
        name = r["reference_speaker_name"]
        if name and name not in seen:
            seen.add(name)
            involved.append(name)

    return {
        "results": results,
        "involved_speakers": involved,
        "total_wer": round(total_wer, 4),
        "total_cer": round(total_cer, 4),
        "total_accuracy": round(total_acc, 4),
        "speaker_accuracy": round(speaker_acc, 4),
        "total_samples": len(results),
    }


def _compute_accuracy(reference: str, hypothesis: str) -> float:
    """
    计算词级准确率 = 1 - WER。
    """
    return max(0.0, 1.0 - _compute_wer(reference, hypothesis))


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
        self._auto_multi: Optional[AutoMultiState] = None  # 模式二：多人识别状态（会话共享）

    async def _initialize_models(self) -> None:
        if self._initialized:
            return

        print("[LocalRealtimeServer] 正在初始化模型...", flush=True)
        sys.stdout.flush()

        self._model_manager = get_model_manager()
        await self._model_manager.initialize()

        self._initialized = True
        print("[LocalRealtimeServer] 模型初始化完成", flush=True)
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
        multi_registry = create_multi_speaker_registry(self._model_manager)

        auto_reg = AutoRegistrationState(
            enabled=True,
            speaker_recognizer=speaker_recognizer,
        )
        self._auto_multi = AutoMultiState(
            enabled=False,
            registry=multi_registry,
        )
        print("[Server] 模式一（双人自动注册）默认开启")

        with realtime_store._lock:
            raw = realtime_store._sessions.get(session_id, {})
            raw["speaker_recognizer"] = speaker_recognizer
            raw["multi_speaker_registry"] = multi_registry

        realtime_store.register_ws_client(session_id, websocket)

        try:
            await websocket.send(json.dumps({
                "type": "session.ready",
                "session_id": session_id,
                "message": "本地流式 FunASR + CAM++ 实时识别已就绪",
                "provider": "local",
                "supports_registration": True,
                "supports_auto_registration": True,
                "supports_multi_speaker": True,
                "streaming": True,
            }, ensure_ascii=False))
            print(f"[WS发送] → 发送 session.ready (本地模式), session_id={session_id}")

            # 预创建管道并启动，避免第一句话因模型初始化而丢失
            await self._preinitialize_pipelines(sources, language)

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

                    # ==================== Benchmark 测试模式 ====================

                    elif message_type == "benchmark.start":
                        # 开启 Benchmark 模式：接收预置答案
                        bench = BenchmarkState()
                        refs_raw = message.get("reference_texts", [])
                        if isinstance(refs_raw, list):
                            bench.reference_texts = [
                                {
                                    "text": str(r.get("text", "")).strip(),
                                    "speaker_id": str(r.get("speaker_id", "")),
                                    "speaker_name": str(r.get("speaker_name", "")),
                                }
                                for r in refs_raw
                                if isinstance(r, dict) and str(r.get("text", "")).strip()
                            ]
                        bench.enabled = True
                        bench.db_speakers = self._auto_multi.db_speakers
                        session["_benchmark"] = bench
                        print(f"[Benchmark] 已开启，预置答案数量={len(bench.reference_texts)}")
                        for idx, r in enumerate(bench.reference_texts):
                            print(f"  [{idx}] speaker={r['speaker_id']}({r.get('speaker_name', '')}): {r['text'][:40]}...")
                        await websocket.send(json.dumps({
                            "type": "benchmark.started",
                            "reference_count": len(bench.reference_texts),
                            "message": f"Benchmark 模式已开启，准备 {len(bench.reference_texts)} 条预置答案",
                        }, ensure_ascii=False))

                    elif message_type == "benchmark.stop":
                        # 关闭 Benchmark 模式
                        bench: Optional[BenchmarkState] = session.get("_benchmark")
                        if bench:
                            bench.enabled = False
                            print("[Benchmark] 已关闭")
                        await websocket.send(json.dumps({
                            "type": "benchmark.stopped",
                            "message": "Benchmark 模式已关闭",
                        }, ensure_ascii=False))

                    elif message_type == "benchmark.evaluate":
                        # 手动触发最终评估
                        bench: Optional[BenchmarkState] = session.get("_benchmark")
                        if not bench or not bench.enabled:
                            await websocket.send(json.dumps({
                                "type": "benchmark.error",
                                "message": "Benchmark 模式未开启",
                            }, ensure_ascii=False))
                        else:
                            # 按说话人合并 hypotheses 后再与 reference_texts 比对
                            if bench.pending_hypotheses and bench.reference_texts:
                                merged = _merge_hypotheses_by_speaker(
                                    bench.pending_hypotheses, bench.reference_texts
                                )
                                bench.final_results = _evaluate_merged(merged, bench.db_speakers)
                                bench.evaluation_done = True
                                print(f"[Benchmark] 评估完成: WER={bench.final_results['total_wer']:.4f}, "
                                      f"CER={bench.final_results['total_cer']:.4f}, "
                                      f"Accuracy={bench.final_results['total_accuracy']:.4f}, "
                                      f"SpeakerAcc={bench.final_results['speaker_accuracy']:.4f}, "
                                      f"样本数={len(merged)}")
                                await websocket.send(json.dumps({
                                    "type": "benchmark.results",
                                    **bench.final_results,
                                }, ensure_ascii=False))
                            else:
                                await websocket.send(json.dumps({
                                    "type": "benchmark.results",
                                    "results": [],
                                    "total_wer": 0.0,
                                    "total_cer": 0.0,
                                    "total_accuracy": 0.0,
                                    "speaker_accuracy": 0.0,
                                    "total_samples": 0,
                                    "message": "没有足够的转录结果进行评估",
                                }, ensure_ascii=False))

                    # ==================== 模式切换 ====================

                    elif message_type == "choose_speaker_mode":
                        mode = str(message.get("mode") or "auto")
                        if mode == "auto_multi":
                            # 切换到模式二：多人自动识别（从公司 DB 加载声纹）
                            auto_reg.enabled = False
                            auto_reg.auto_register_done = False
                            self._auto_multi.enabled = True
                            # 加载公司声纹数据库到识别引擎
                            db = session.get("speaker_database")
                            if db:
                                all_speakers = db.load_all()
                                db_speakers = [s for s in all_speakers if s.get("is_active", 1) == 1]
                                if db_speakers:
                                    # 将 DB 中的声纹向量注入 registry
                                    from app.speaker_database import bytes_to_ndarray
                                    for sp in db_speakers:
                                        emb = bytes_to_ndarray(sp.get("embedding"))
                                        if emb is not None:
                                            self._auto_multi.registry.register_embedding(
                                                sp["speaker_id"],
                                                emb,
                                                name=sp.get("name", ""),
                                                role=sp.get("role", ""),
                                            )
                                    print(f"[Server] 模式二：从 DB 加载 {len(db_speakers)} 位说话人到识别引擎")
                                    await websocket.send(json.dumps({
                                        "type": "mode.switched",
                                        "mode": "auto_multi",
                                        "message": f"已切换到模式二，正在识别...（已加载 {len(db_speakers)} 位员工声纹）",
                                        "db_speaker_count": len(db_speakers),
                                        "db_speakers": [
                                            {"speaker_id": s["speaker_id"], "name": s.get("name", ""),
                                             "role": s.get("role", ""), "department": s.get("department", "")}
                                            for s in db_speakers
                                        ],
                                    }, ensure_ascii=False))
                                    self._auto_multi.db_speaker_count = len(db_speakers)
                                    self._auto_multi.db_speakers = [
                                        {"speaker_id": s["speaker_id"], "name": s.get("name", ""),
                                         "role": s.get("role", ""), "department": s.get("department", "")}
                                        for s in db_speakers
                                    ]
                                else:
                                    print("[Server] 模式二：公司声纹数据库为空，请先在「声纹数据库」页面注册员工")
                                    await websocket.send(json.dumps({
                                        "type": "mode.switched",
                                        "mode": "auto_multi",
                                        "message": "公司声纹数据库为空，请在「声纹数据库」页面注册员工后再使用此模式",
                                        "db_speaker_count": 0,
                                        "db_speakers": [],
                                    }, ensure_ascii=False))
                                    self._auto_multi.db_speaker_count = 0
                                    self._auto_multi.db_speakers = []
                            else:
                                print("[Server] 模式二：speaker_database 未初始化")
                                await websocket.send(json.dumps({
                                    "type": "mode.switched",
                                    "mode": "auto_multi",
                                    "message": "声纹数据库未初始化，请检查配置",
                                    "db_speaker_count": 0,
                                    "db_speakers": [],
                                }, ensure_ascii=False))
                                self._auto_multi.db_speaker_count = 0
                                self._auto_multi.db_speakers = []
                        else:
                            # 切换到模式一：双人自动注册
                            auto_reg.enabled = True
                            auto_reg.auto_register_done = False
                            self._auto_multi.enabled = False
                            print("[Server] 已切换到模式一：双人自动注册")
                            await websocket.send(json.dumps({
                                "type": "mode.switched",
                                "mode": "auto",
                                "message": "已切换到模式一，请第一位说话人开始发言",
                            }, ensure_ascii=False))

                    # ==================== 模式一：原有的注册消息（保留兼容） ====================

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
            # 清理注册状态中的大对象引用（float32 音频数组）
            auto_reg.interviewer_samples.clear()
            auto_reg.candidate_samples.clear()
            auto_reg.pending_segments.clear()
            auto_reg.interviewer_embedding = None
            auto_reg.candidate_embedding = None

            # 关闭并清理会话（从 _sessions 字典移除，释放大对象）
            realtime_store.close_session(session_id)

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
            print(f"[Server] 收到音频: source={source_name}, 时长={audio_duration:.2f}s, 模型已初始化={is_init}, VAD模型={'有' if vad_model else '无'}", flush=True)
            self._audio_logged = True

        # ---------- 模式二：多人自动识别 ----------
        if self._auto_multi.enabled:
            if source.pipeline is None:
                await self._init_pipeline(source, language)
            if source.pipeline:
                # 清空旧注册人，设置为增强引擎
                source.pipeline._registered_speakers = {}
                if self._auto_multi.registry:
                    source.pipeline.set_enhanced_registry(self._auto_multi.registry)
                await source.pipeline.feed_audio(audio_float32)
            elif not self._auto_multi.initialized:
                # 管道初始化失败且未通知过客户端（VAD 未就绪或模型加载错误）
                self._auto_multi.initialized = True
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "VAD 模型未就绪，音频暂不处理，请等待模型加载完成后重试。",
                }, ensure_ascii=False))
            return

        # ---------- 模式一：自动注册模式 ----------
        if source.pipeline is None:
            if not self._model_manager.is_initialized():
                return
            vad_model = self._model_manager.get_vad_model()
            if vad_model is None:
                # 即使 VAD 模型为空，仍尝试创建 pipeline（StreamingVAD 会回退到能量检测）
                print("[Server] VAD 模型未就绪，使用能量检测模式创建管道")
                try:
                    source.pipeline = create_streaming_pipeline(self._model_manager, language)
                except Exception as e:
                    print(f"[Server] 创建管道失败（VAD 缺失）: {e}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": f"模型加载失败: {e}",
                    }, ensure_ascii=False))
                    return

            source.pipeline.on_transcript = lambda delta: self._on_transcript_delta(delta, source, websocket)
            source.pipeline.on_speaker = lambda sid, score: self._on_speaker_identified(sid, score, source, websocket)
            source.pipeline.on_speech_segment = lambda seg: self._on_speech_segment_for_auto_reg(seg, sources, auto_reg)

            await source.pipeline.start()
            print("[Server] 管道已创建并启动")

        if auto_reg.enabled:
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
            queue = raw.setdefault("pending_audio", [])
            queue.append({
                "audio_samples": segment.audio_data,
                "start_ms": getattr(segment, "start_ms", 0),
                "end_ms": getattr(segment, "end_ms", 0),
            })
            # FIFO 上限，超过则丢弃最旧的（防止 ASR 慢于 VAD 时内存无限增长）
            if len(queue) > _MAX_PENDING_AUDIO:
                evicted = queue.pop(0)
                print(f"[AutoReg] pending_audio 队列已满，丢弃最旧片段 "
                      f"({len(evicted['audio_samples'])/16000:.1f}s)")

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

    async def _preinitialize_pipelines(self, sources: Dict[str, AudioSource], language: str) -> None:
        """
        预先初始化所有管道的音频处理部分。
        
        关键：在 WebSocket 连接建立后、开始接收音频前，
        预先创建好管道并启动，等待音频到来。
        这样可以避免第一句话因为模型还在初始化而被丢弃。
        """
        if not sources:
            return
        
        # 如果模型已就绪，立即初始化
        if self._model_manager and self._model_manager.is_initialized():
            for source in sources.values():
                if source.pipeline is None:
                    await self._init_pipeline(source, language)
            print(f"[Server] 预初始化完成：{len(sources)} 个管道已就绪，等待音频...")
            return
        
        # 模型未就绪时，启动后台初始化任务
        async def _init_task():
            # 等待模型初始化（最多等 60 秒）
            for _ in range(60):
                await asyncio.sleep(1)
                if self._model_manager and self._model_manager.is_initialized():
                    break
            
            # 模型就绪后，初始化所有管道
            if self._model_manager and self._model_manager.is_initialized():
                for source in sources.values():
                    if source.pipeline is None:
                        await self._init_pipeline(source, language)
                print(f"[Server] 延迟预初始化完成：{len(sources)} 个管道已就绪，等待音频...")
            else:
                print("[Server] 警告：模型初始化超时，管道未能在音频到来前就绪")
        
        asyncio.create_task(_init_task())

    async def _init_pipeline(self, source: AudioSource, language: str) -> None:
        """初始化管道的辅助方法"""
        if source.pipeline is None and self._model_manager and self._model_manager.is_initialized():
            vad_model = self._model_manager.get_vad_model()
            if vad_model:
                source.pipeline = create_streaming_pipeline(self._model_manager, language)
                source.pipeline.on_transcript = lambda delta: self._on_transcript_delta(delta, source, source.client_websocket)
                source.pipeline.on_speaker = lambda sid, score: self._on_speaker_identified(sid, score, source, source.client_websocket)
                await source.pipeline.start()
                print(f"[Server] 管道已初始化: {source.source_name}")
            else:
                # 即使无 VAD 模型，仍尝试创建（回退到能量检测）
                print("[Server] VAD 模型缺失，使用能量检测模式初始化管道")
                try:
                    source.pipeline = create_streaming_pipeline(self._model_manager, language)
                    source.pipeline.on_transcript = lambda delta: self._on_transcript_delta(delta, source, source.client_websocket)
                    source.pipeline.on_speaker = lambda sid, score: self._on_speaker_identified(sid, score, source, source.client_websocket)
                    await source.pipeline.start()
                    print(f"[Server] 管道已初始化（能量模式）: {source.source_name}")
                except Exception as e:
                    print(f"[Server] 管道初始化失败: {e}")

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
            session = realtime_store.get(source.session_id)
            if not delta.text.strip():
                return

            raw_speaker = delta.speaker_id or source.speaker_id

            speaker_display = raw_speaker
            # Mode 2: 优先显示 DB 中的姓名
            if hasattr(delta, "speaker_name") and delta.speaker_name:
                speaker_display = delta.speaker_name
            elif raw_speaker == "interviewer":
                speaker_display = "面试官"
            elif raw_speaker == "candidate":
                speaker_display = "候选人"
            elif raw_speaker == "speaker_unk" or raw_speaker == "unknown":
                speaker_display = "未知"

            int_sim_str = f" 面试官={delta.interviewer_sim:.2f}" if delta.interviewer_sim > 0 else ""
            cand_sim_str = f" 候选人={delta.candidate_sim:.2f}" if delta.candidate_sim > 0 else ""
            confidence_str = f" ({int_sim_str}{cand_sim_str})" if int_sim_str or cand_sim_str else ""
            reason_str = f" [{delta.segment_reason}]" if delta.segment_reason else ""
            print(f"[转录] 【{speaker_display}{confidence_str}{reason_str}】 {delta.text[:50]}{'...' if len(delta.text) > 50 else ''}")

            # 转换 numpy 类型为 Python 原生类型（避免 json 序列化失败）
            def _to_native(obj):
                if isinstance(obj, np.floating):
                    return float(obj)
                if isinstance(obj, np.integer):
                    return int(obj)
                if isinstance(obj, np.ndarray):
                    return _to_native(obj.tolist())
                if isinstance(obj, dict):
                    return {k: _to_native(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [_to_native(x) for x in obj]
                return obj

            candidates_raw = getattr(delta, "speaker_candidates", None)
            registered_sims_raw = getattr(delta, "registered_speaker_sims", None)

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
                # Mode 2 扩展字段
                "speaker_name": getattr(delta, "speaker_name", None),
                "speaker_candidates": _to_native(candidates_raw),
                "registered_speaker_sims": _to_native(registered_sims_raw),
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
                # 模式二（多人识别）禁用 DISC 分析
                if not self._auto_multi.enabled:
                    asyncio.create_task(
                        self._async_disc_refresh(source.session_id, websocket, source, is_partial=True)
                    )

            if delta.is_final and recognized_speaker:
                session_update = consume_local_transcript_event(
                    source.session_id,
                    recognized_speaker,
                    event,
                    )

                # 注册期间：异步声纹识别已完成，发送修正后的更新
                # 注意：consume_local_transcript_event 已经提交了异步识别任务
                # 这里等待一小段时间后发送修正后的 session.update
                _session = realtime_store.get(source.session_id)
                if _session and not _session.get("voice_registered"):

                    async def _send_correction():
                        try:
                            await asyncio.sleep(0.1)  # 等待后台识别完成
                            if source._connection_closed:
                                return
                            update = build_session_update(source.session_id)
                            if update:
                                await websocket.send(json.dumps(update, ensure_ascii=False))
                                print(f"[WS发送] → 注册期间发送 session.update（带声纹修正）")
                        except Exception as e:
                            print(f"[AutoReg] 发送修正失败: {e}")

                    asyncio.create_task(_send_correction())

                # Benchmark 模式：记录 hypothesis 并自动评估
                bench: Optional[BenchmarkState] = session.get("_benchmark")
                if bench and bench.enabled and delta.text.strip():
                    hyp_entry = {
                        "text": delta.text.strip(),
                        "speaker_id": recognized_speaker,
                        "is_final": True,
                    }
                    bench.pending_hypotheses.append(hyp_entry)
                    print(f"[Benchmark] 记录 hypothesis[{len(bench.pending_hypotheses)-1}]: "
                          f"speaker={recognized_speaker}, text={delta.text[:40]}...")

                    # 当 hypotheses 数量达到 reference_texts 数量时，自动触发评估（按说话人合并后）
                    if (not bench.evaluation_done
                            and bench.reference_texts
                            and len(bench.pending_hypotheses) >= len(bench.reference_texts)):
                        merged = _merge_hypotheses_by_speaker(
                            bench.pending_hypotheses, bench.reference_texts
                        )
                        bench.final_results = _evaluate_merged(merged, bench.db_speakers)
                        bench.evaluation_done = True
                        print(f"[Benchmark] 自动评估完成: WER={bench.final_results['total_wer']:.4f}, "
                              f"CER={bench.final_results['total_cer']:.4f}, "
                              f"Accuracy={bench.final_results['total_accuracy']:.4f}, "
                              f"SpeakerAcc={bench.final_results['speaker_accuracy']:.4f}")
                        await websocket.send(json.dumps({
                            "type": "benchmark.results",
                            **bench.final_results,
                        }, ensure_ascii=False))

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

                    # 模式二（多人识别）禁用 DISC 分析
                    if not self._auto_multi.enabled:
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
    "system": "interviewer",
    "mic": "interviewer",   # mic 和 system 都是候选人端，合并为同一说话人
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
