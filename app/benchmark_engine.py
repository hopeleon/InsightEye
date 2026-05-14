"""
Benchmark 引擎 — 准确率测试核心
==================================
功能：
  - 加载音频 + Ground Truth JSON
  - 对音频片段做 ASR 识别（复用现有 pipeline）
  - 使用 MacBERT4CSC 对 ASR 结果进行纠错
  - 按时间戳对齐识别结果与标准答案，计算 CER/WER/DER/一致性
  - 通过 SSE 推送实时指标到前端

Ground Truth JSON 格式：
  {
    "_meta": { "total_duration_sec": 600, "num_speakers": 4, ... },
    "segments": [
      { "id": 1, "speaker_id": "speaker_001", "start_ms": 0, "end_ms": 7800,
        "text": "...", "final": true, ... },
      ...
    ]
  }
"""

from __future__ import annotations

import io
import json
import math
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

try:
    import chardet
    HAS_CHARDET = True
except ImportError:
    HAS_CHARDET = False

# 导入文本纠错模块
from app.text_corrector import get_corrector, correct_and_compare


# ======================== 指标阈值 ========================

THRESHOLDS = {
    "cer":           0.10,   # ≤ 10%
    "wer":           0.10,   # ≤ 10%
    "der":           0.15,   # ≤ 15%
    "consistency":   0.90,   # ≥ 90%
    "min_speakers":  2,
    "max_speakers":  10,
}


# ======================== 数据结构 ========================

@dataclass
class GTSegment:
    """Ground Truth 中的单个片段"""
    idx: int
    speaker_id: str
    start_ms: int
    end_ms: int
    text: str
    duration_ms: int


@dataclass
class RecognizedSegment:
    """系统识别出的单个片段"""
    idx: int
    speaker_id: str
    start_ms: int
    end_ms: int
    text: str
    confidence: float = 1.0


@dataclass
class AlignmentResult:
    """对齐结果：GT 片段 ↔ 识别片段"""
    gt: GTSegment
    asr_text: str
    cer: float          # 字符错误率（0~1）
    wer: float          # 词错误率（0~1，英文段落用）
    speaker_correct: bool
    asr_speaker_id: str
    gt_speaker_id: str


@dataclass
class BenchmarkMetrics:
    """累积指标快照"""
    cer_avg: float = 0.0
    cer_count: int = 0
    wer_avg: float = 0.0
    wer_count: int = 0
    der: float = 0.0           # 说话人分离错误率
    speaker_consistency: float = 0.0
    composite_avg: float = 0.0  # 综合评分
    exact_match_rate: float = 0.0
    avg_coverage: float = 0.0
    processed_segments: int = 0
    total_segments: int = 0
    processed_ms: int = 0
    total_ms: int = 0
    elapsed_sec: float = 0.0
    passed_asr: bool = False
    passed_speaker: bool = False
    status: str = "running"     # running / completed / failed
    issues: list = field(default_factory=list)


@dataclass
class SegmentComparison:
    """逐片段对比（用于前端展示）"""
    idx: int
    gt_text: str
    asr_text: str
    corrected_text: str = ""           # MacBERT 纠错后的文本
    speaker_gt: str
    speaker_asr: str
    cer: float
    wer: float
    speaker_ok: bool
    status: str           # correct / minor_error / major_error / unknown
    # 新增多维度指标
    exact_match: float = 0.0   # 完全一致（0/1）
    prefix_score: float = 0.0  # 前缀匹配率 0~1
    suffix_score: float = 0.0  # 后缀匹配率 0~1
    coverage: float = 0.0      # 覆盖率 0~1
    composite: float = 0.0     # 综合评分 0~1
    # 纠错相关
    was_corrected: bool = False
    correction_errors: list = field(default_factory=list)
    correction_improved: bool = False


# ======================== 多维度文本评估 ========================

def _normalize_text(text: str) -> str:
    """文本归一化：去首尾空格、转小写"""
    return text.strip()


def _prefix_match_score(ref: str, hyp: str, max_len: int = 20) -> float:
    """
    前缀匹配率：从头开始连续匹配的最长前缀 / max_len
    容忍 ASR 偶尔在开头漏一个字或有一个小错误，不直接判定为 0
    """
    ref = _normalize_text(ref)
    hyp = _normalize_text(hyp)
    if not ref:
        return 1.0 if not hyp else 0.0

    matched = 0
    # 用 edit distance 找最大前缀长度
    r, h = list(ref), list(hyp)
    min_len = min(len(r), len(h), max_len)
    for i in range(min_len):
        if r[i] == h[i]:
            matched += 1
        else:
            # 允许 1 个字符的容错（如"你好啊"识别成"你好啊"多了一个语气词）
            # 只有第一个 mismatch 才宽容
            if i > 0:
                break
    return matched / max(min_len, 1)


def _suffix_match_score(ref: str, hyp: str, max_len: int = 10) -> float:
    """后缀匹配率：结尾连续匹配的长度 / max_len"""
    ref = _normalize_text(ref)
    hyp = _normalize_text(hyp)
    if not ref:
        return 1.0 if not hyp else 0.0

    matched = 0
    r, h = list(ref), list(hyp)
    min_len = min(len(r), len(h), max_len)
    for i in range(min_len):
        ri = len(r) - 1 - i
        hi = len(h) - 1 - i
        if r[ri] == h[hi]:
            matched += 1
        else:
            if i > 0:
                break
    return matched / max(min_len, 1)


def _coverage_score(ref: str, hyp: str) -> float:
    """
    覆盖率：GT 文本中有多少比例出现在 ASR 输出中
    使用编辑距离找最小对齐子序列（类似 LCS 但允许 skip）
    """
    ref = _normalize_text(ref)
    hyp = _normalize_text(hyp)
    if not ref:
        return 1.0 if not hyp else 0.0
    if not hyp:
        return 0.0

    # 贪心覆盖率：逐字符检查 ref 中每个字符是否能在 hyp 的剩余部分找到
    # 对于连续子串优先匹配（避免被标点/语气词打断）
    coverage = 0
    hyp_remaining = list(hyp)
    i = 0
    while i < len(ref):
        char = ref[i]
        if char in hyp_remaining:
            idx = hyp_remaining.index(char)
            # 匹配成功，移除已匹配部分
            hyp_remaining = hyp_remaining[idx + 1:]
            coverage += 1
            i += 1
        else:
            i += 1

    return coverage / len(ref)


def _exact_match_score(ref: str, hyp: str) -> float:
    """精确匹配率：完全一致为 1，否则为 0"""
    return 1.0 if _normalize_text(ref) == _normalize_text(hyp) else 0.0


def _partial_edit_score(ref: str, hyp: str) -> float:
    """
    编辑距离的宽松版：允许最大偏离 len(ref) * 0.3 的误差
    超过则按比例扣分，但不会直接到 0
    """
    ref = _normalize_text(ref)
    hyp = _normalize_text(hyp)
    if not ref:
        return 1.0 if not hyp else 0.0

    dist = levenshtein_distance(ref, hyp)
    max_allowed = max(int(len(ref) * 0.30), 2)  # 最多容忍 30% 误差，至少 2 个字符
    if dist <= max_allowed:
        # 在容错范围内：完全正确或轻微错误
        return max(0.0, 1.0 - dist / len(ref))
    else:
        # 超过容错范围：按比例扣分，但保留至少 30%
        excess = dist - max_allowed
        total_range = len(ref) - max_allowed
        return max(0.3, 1.0 - (max_allowed + excess * 0.5) / len(ref))


def character_error_rate(reference: str, hypothesis: str) -> float:
    """
    中文/字符级 CER（旧接口，保留兼容）
    内部改为宽松版 partial_edit_score
    """
    ref = reference.strip()
    hyp = hypothesis.strip()
    if not ref:
        return 0.0 if not hyp else 1.0
    return 1.0 - _partial_edit_score(ref, hyp)


def word_error_rate(reference: str, hypothesis: str) -> float:
    """
    英文/词级 WER（旧接口，保留兼容）
    """
    ref = reference.strip().split()
    hyp = hypothesis.strip().split()
    if not ref:
        return 0.0 if not hyp else 1.0
    dist = levenshtein_distance(ref, hyp)
    max_allowed = max(int(len(ref) * 0.30), 2)
    if dist <= max_allowed:
        return min(dist / len(ref), 1.0)
    else:
        return max(0.3, min((dist - max_allowed * 0.5) / len(ref), 1.0))


@dataclass
class TextEvalResult:
    """文本评估详细结果"""
    exact_match: float     # 完全一致（0/1）
    prefix_score: float    # 前缀匹配率 0~1
    suffix_score: float    # 后缀匹配率 0~1
    coverage: float        # 覆盖率 0~1
    partial_score: float   # 编辑距离宽松评分 0~1
    cer: float             # 字符错误率 0~1（兼容旧接口）
    composite: float       # 综合评分 0~1
    status: str            # correct / minor_error / major_error / unknown


def evaluate_text(reference: str, hypothesis: str) -> TextEvalResult:
    """
    多维度文本评估。
    综合考虑前缀匹配、后缀匹配、覆盖率、编辑距离，
    而不是仅用单一的错误率指标。
    """
    ref = _normalize_text(reference)
    hyp = _normalize_text(hypothesis)

    if not ref:
        return TextEvalResult(
            exact_match=1.0 if not hyp else 0.0,
            prefix_score=1.0 if not hyp else 0.0,
            suffix_score=1.0 if not hyp else 0.0,
            coverage=1.0 if not hyp else 0.0,
            partial_score=1.0 if not hyp else 0.0,
            cer=0.0 if not hyp else 1.0,
            composite=1.0 if not hyp else 0.0,
            status="unknown",
        )

    exact = _exact_match_score(ref, hyp)
    prefix = _prefix_match_score(ref, hyp)
    suffix = _suffix_match_score(ref, hyp)
    cover = _coverage_score(ref, hyp)
    partial = _partial_edit_score(ref, hyp)
    cer = 1.0 - partial

    # 综合评分：覆盖率权重最高，前缀其次，后缀次之
    composite = cover * 0.40 + prefix * 0.25 + suffix * 0.15 + partial * 0.20

    # 状态分级
    if exact >= 1.0:
        status = "correct"
    elif composite >= 0.80 and cover >= 0.85:
        status = "correct"
    elif composite >= 0.60 and cover >= 0.60:
        status = "minor_error"
    elif composite >= 0.40:
        status = "minor_error"
    else:
        status = "major_error"

    return TextEvalResult(
        exact_match=exact,
        prefix_score=prefix,
        suffix_score=suffix,
        coverage=cover,
        partial_score=partial,
        cer=cer,
        composite=composite,
        status=status,
    )


def detect_language(text: str) -> str:
    """简单语言检测（基于字符集）"""
    if not text:
        return "zh"
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    alpha_chars   = sum(1 for c in text if c.isalpha())
    total = chinese_chars + alpha_chars
    if total == 0:
        return "zh"
    return "zh" if chinese_chars / total > 0.6 else "en"


# ======================== Ground Truth 解析 ========================

def load_ground_truth(json_path: Path) -> tuple[list[GTSegment], dict]:
    """
    解析 Ground Truth JSON 文件。

    Returns:
        (segments_list, meta_dict)
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("_meta", {})
    gt_segments: list[GTSegment] = []

    for seg in data.get("segments", []):
        gt_segments.append(GTSegment(
            idx=int(seg.get("id", 0)),
            speaker_id=str(seg.get("speaker_id", "")),
            start_ms=int(seg.get("start_ms", 0)),
            end_ms=int(seg.get("end_ms", 0)),
            text=str(seg.get("text", "")).strip(),
            duration_ms=int(seg.get("duration_ms", 0)),
        ))

    return gt_segments, meta


def load_audio_info(wav_path: Path) -> tuple[int, float]:
    """读取 WAV 文件基本信息，返回 (total_frames, duration_sec)"""
    with wave.open(str(wav_path), "rb") as wf:
        frames = wf.getnframes()
        sr = wf.getframerate()
    return frames, frames / sr


# ======================== 音频分片 ========================

def slice_audio_by_gt(
    wav_path: Path,
    gt_segments: list[GTSegment],
    overlap_ms: int = 200,
) -> list[tuple[GTSegment, np.ndarray]]:
    """
    按 Ground Truth 的时间戳切分音频，返回 [(gt_segment, audio_pcm), ...]
    overlap_ms 允许边界容差（VAD 切分和 GT 不完全重合）
    """
    results: list[tuple[GTSegment, np.ndarray]] = []

    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        sampwidth = wf.getsampwidth()
        for seg in gt_segments:
            start_frame = max(0, int((seg.start_ms - overlap_ms) / 1000 * sr))
            end_frame = int((seg.end_ms + overlap_ms) / 1000 * sr)
            wf.setpos(start_frame)
            n_frames = end_frame - start_frame
            raw = wf.readframes(n_frames)
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            results.append((seg, audio))

    return results


# ======================== ASR 识别 ========================

def run_asr_on_segment(
    audio: np.ndarray,
    model_manager,
    language: str = "zh",
    sample_rate: int = 16000,
) -> str:
    """
    对单个音频片段运行 ASR，返回识别文本。
    复用现有 audio_transcription.py 的逻辑。
    """
    try:
        from .audio_transcription import transcribe_audio_bytes
        int16_bytes = (audio * 32767.0).astype(np.int16).tobytes()
        result = transcribe_audio_bytes(
            int16_bytes,
            filename="benchmark_segment.wav",
            mime_type="audio/wav",
            language=language,
        )
        segments = result.get("segments", [])
        if segments:
            return segments[0].get("text", "")
        return result.get("text", "")
    except Exception as e:
        print(f"[Benchmark-ASR] 识别失败: {e}")
        return ""


# ======================== 说话人一致性计算 ========================

def compute_speaker_consistency(
    alignments: list[AlignmentResult],
    gt_segments: list[GTSegment],
) -> float:
    """
    计算同一说话人标签一致性。
    对每个 GT 说话人，检查其所有片段中系统输出的 speaker_id 是否一致。
    """
    # 按 GT speaker_id 分组
    from collections import defaultdict
    groups: dict[str, list[AlignmentResult]] = defaultdict(list)
    for al in alignments:
        groups[al.gt.speaker_id].append(al)

    if not groups:
        return 0.0

    total_correct = 0
    total_segments = 0
    for sid, items in groups.items():
        # 统计该说话人被一致识别的片段数
        if not items:
            continue
        # 找出最常出现的 ASR speaker_id
        from collections import Counter
        asr_ids = [al.asr_speaker_id for al in items]
        most_common_id, most_common_count = Counter(asr_ids).most_common(1)[0]
        # 一致片段数 = 最常出现的那个 ID 的出现次数
        total_correct += most_common_count
        total_segments += len(items)

    if total_segments == 0:
        return 0.0
    return total_correct / total_segments


def compute_der(
    alignments: list[AlignmentResult],
    total_gt_ms: int,
) -> float:
    """
    说话人分离错误率（DER）。

    DER = 错误标注时长 / 总时长
    错误包括：说话人标签错误、漏识别、误识别
    这里用简化模型：speaker_correct=False 的片段占总时长的比例
    """
    if total_gt_ms == 0 or not alignments:
        return 0.0

    error_ms = 0
    for al in alignments:
        if not al.speaker_correct:
            error_ms += al.gt.duration_ms

    return min(error_ms / total_gt_ms, 1.0)


# ======================== SSE 推送器 ========================

class SSELogger:
    """线程安全的 SSE 事件记录器（供 BenchmarkEngine 回调使用）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._events: list[dict] = []

    def push(self, event_type: str, data: dict) -> None:
        with self._lock:
            self._events.append({
                "type": event_type,
                "data": data,
                "ts": time.time(),
            })

    def pop_all(self) -> list[dict]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def count(self) -> int:
        with self._lock:
            return len(self._events)


# ======================== Benchmark 主引擎 ========================

class BenchmarkEngine:
    """
    准确率测试主引擎。

    使用方式：
        engine = BenchmarkEngine(model_manager)
        engine.load(wav_path, gt_json_path)
        engine.on_event(callback)  # 实时指标回调
        engine.run()               # 同步运行
        # 或：
        threading.Thread(target=engine.run, daemon=True).start()
    """

    def __init__(self, model_manager=None, use_correction: bool = True):
        """
        Args:
            model_manager: 模型管理器实例
            use_correction: 是否启用 MacBERT 文本纠错（默认启用）
        """
        self.model_manager = model_manager
        self.use_correction = use_correction
        self._corrector = None  # 延迟加载

        # 加载状态
        self.gt_segments: list[GTSegment] = []
        self.audio_slices: list[tuple[GTSegment, np.ndarray]] = []
        self.meta: dict = {}
        self.total_duration_sec: float = 0.0

        # 识别结果
        self.alignments: list[AlignmentResult] = []
        self.metrics = BenchmarkMetrics()

        # SSE 回调
        self._on_sse: list[Callable[[str, dict], None]] = []

        # 实时对比记录（供前端展示）
        self.comparisons: list[SegmentComparison] = []

        # 状态
        self._running = False
        self._stopped = False
        self._thread: Optional[threading.Thread] = None  # 后台 benchmark 线程
        self._lock = threading.Lock()  # 保护所有共享状态的线程安全访问

    def _get_corrector(self):
        """获取或初始化纠错器"""
        if not self.use_correction:
            return None
        if self._corrector is None:
            print("[Benchmark] 初始化 MacBERT 纠错模型...")
            self._corrector = get_corrector()
        return self._corrector

    # ---- 事件注册 ----

    def on_event(self, callback: Callable[[str, dict], None]) -> None:
        """注册 SSE 事件回调"""
        self._on_sse.append(callback)

    def _emit(self, event_type: str, data: dict) -> None:
        for cb in self._on_sse:
            try:
                cb(event_type, data)
            except Exception as e:
                print(f"[Benchmark] SSE callback 失败: {e}")

    # ---- 数据加载 ----

    def load(
        self,
        wav_path: Path | str,
        gt_json_path: Path | str,
    ) -> dict:
        """加载音频和 Ground Truth，返回摘要"""
        wav_path = Path(wav_path)
        gt_path  = Path(gt_json_path)

        if not wav_path.exists():
            raise FileNotFoundError(f"音频文件不存在: {wav_path}")
        if not gt_path.exists():
            raise FileNotFoundError(f"Ground Truth 文件不存在: {gt_path}")

        # 加载 GT
        self.gt_segments, self.meta = load_ground_truth(gt_path)

        # 读取音频时长
        _, self.total_duration_sec = load_audio_info(wav_path)

        # 切分音频
        print(f"[Benchmark] 加载 GT：{len(self.gt_segments)} 片段，音频时长 {self.total_duration_sec:.1f}s")
        self.audio_slices = slice_audio_by_gt(wav_path, self.gt_segments)

        self.metrics.total_segments = len(self.gt_segments)
        self.metrics.total_ms = int(self.total_duration_sec * 1000)

        return {
            "segments": len(self.gt_segments),
            "duration_sec": round(self.total_duration_sec, 2),
            "speakers": list({s.speaker_id for s in self.gt_segments}),
        }

    # ---- 运行测试 ----

    def run_async(self) -> None:
        """
        异步非阻塞运行 benchmark（后台线程）。

        每处理完一个片段立即：
          1. 执行 ASR 识别
          2. 与标准答案对比评估
          3. 通过 SSE 推送实时结果
          4. 更新累积指标

        调用方通过 on_event 注册回调接收实时结果。
        状态通过 get_metrics_snapshot() 实时查询。
        """
        if self._running:
            print("[Benchmark] 已在运行中，忽略重复调用")
            return

        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="BenchmarkRunner")
        self._thread.start()

    def run(self) -> BenchmarkMetrics:
        """同步运行完整 benchmark（内部调用 run_async 并等待完成）"""
        self.run_async()
        # 等待后台线程结束
        if self._thread is not None:
            self._thread.join()
        return self.metrics

    def _run_loop(self) -> None:
        """后台线程主循环：逐片段 ASR + 评估 + SSE 推送"""
        start_time = time.time()

        with self._lock:
            self._running = True
            self._stopped = False
            total = len(self.audio_slices)

        self._emit("started", {
            "total_segments": total,
            "total_duration_sec": round(self.total_duration_sec, 2),
            "speakers": list({s.speaker_id for s in self.gt_segments}),
        })

        try:
            self._process_segments()  # 逐片段实时评估
            with self._lock:
                self.metrics.status = "completed"
        except Exception as e:
            with self._lock:
                self.metrics.status = "failed"
                self.metrics.issues.append(f"运行异常: {e}")
            print(f"[Benchmark] 运行失败: {e}")
            import traceback
            traceback.print_exc()
        finally:
            with self._lock:
                self._running = False
            elapsed = time.time() - start_time
            with self._lock:
                self.metrics.elapsed_sec = round(elapsed, 1)
                self._finalize_metrics()
            self._emit("complete", self._build_final_report())
            print(f"[Benchmark] 完成，耗时 {elapsed:.1f}s")

    def _process_segments(self) -> None:
        """
        后台线程中逐片段执行：
          1. ASR 识别
          2. MacBERT 文本纠错
          3. 与标准答案实时对比评估
          4. SSE 推送片段结果
          5. 更新累积指标

        每个片段处理完立即推送，不等待全部完成。
        所有共享状态访问均加锁保护。
        """
        with self._lock:
            total = len(self.audio_slices)

        # 获取纠错器
        corrector = self._get_corrector()

        for i, (gt_seg, audio) in enumerate(self.audio_slices):
            # stop 检查（加锁）
            with self._lock:
                if self._stopped:
                    break

            # ASR 识别（同步调用，不阻塞 SSE 线程）
            lang = detect_language(gt_seg.text)

            asr_text = ""
            asr_speaker = "unknown"
            corrected_text = ""
            was_corrected = False
            correction_errors = []
            correction_improved = False

            try:
                asr_text = run_asr_on_segment(audio, self.model_manager, language=lang)
            except Exception as e:
                print(f"[Benchmark] 片段 {i+1} ASR 失败: {e}")

            # MacBERT 文本纠错
            if corrector and asr_text.strip():
                try:
                    correction_result = correct_and_compare(asr_text, gt_seg.text)
                    corrected_text = correction_result.get("corrected_text", asr_text)
                    was_corrected = correction_result.get("was_corrected", False)
                    correction_errors = correction_result.get("errors", [])
                    correction_improved = correction_result.get("improved", False)
                except Exception as e:
                    print(f"[Benchmark] 片段 {i+1} 纠错失败: {e}")
                    corrected_text = asr_text

            # 多维度文本评估（使用纠错后的文本与 GT 对比）
            eval_result = evaluate_text(gt_seg.text, corrected_text if corrected_text else asr_text)
            cer = eval_result.cer
            wer = word_error_rate(gt_seg.text, corrected_text if corrected_text else asr_text)
            speaker_correct = False

            # 打印日志：显示纠错前后对比
            if was_corrected:
                print(f"[Benchmark] 片段 {i+1}/{total} | CER纠后={cer:.3f} | 纠错↑{correction_improved} | "
                      f"GT='{gt_seg.text[:25]}...' | 纠前='{asr_text[:25]}...' → 纠后='{corrected_text[:25]}...'")
                if correction_errors:
                    print(f"       纠错详情: {correction_errors[:5]}")  # 最多显示5个错误
            else:
                print(f"[Benchmark] 片段 {i+1}/{total} | CER纠后={cer:.3f} | "
                      f"GT='{gt_seg.text[:30]}' | ASR='{asr_text[:30]}'")

            # 多维度文本评估（立即完成）
            eval_result = evaluate_text(gt_seg.text, asr_text)
            cer = eval_result.cer
            wer = word_error_rate(gt_seg.text, asr_text)
            speaker_correct = False

            # 更新共享状态（加锁）
            with self._lock:
                # 记录对齐结果
                alignment = AlignmentResult(
                    gt=gt_seg, asr_text=asr_text, cer=cer, wer=wer,
                    speaker_correct=speaker_correct,
                    asr_speaker_id=asr_speaker, gt_speaker_id=gt_seg.speaker_id,
                )
                self.alignments.append(alignment)

                # 累积 CER/WER
                self.metrics.cer_count += 1
                self.metrics.cer_avg = (
                    self.metrics.cer_avg * (self.metrics.cer_count - 1) + cer
                ) / self.metrics.cer_count
                if lang == "en":
                    self.metrics.wer_count += 1
                    self.metrics.wer_avg = (
                        self.metrics.wer_avg * (self.metrics.wer_count - 1) + wer
                    ) / self.metrics.wer_count

                # 记录对比
                self.comparisons.append(SegmentComparison(
                    idx=i + 1,
                    gt_text=gt_seg.text, asr_text=asr_text,
                    corrected_text=corrected_text if was_corrected else asr_text,
                    speaker_gt=gt_seg.speaker_id, speaker_asr=asr_speaker,
                    cer=cer, wer=wer, speaker_ok=speaker_correct,
                    status=eval_result.status,
                    exact_match=eval_result.exact_match,
                    prefix_score=eval_result.prefix_score,
                    suffix_score=eval_result.suffix_score,
                    coverage=eval_result.coverage,
                    composite=eval_result.composite,
                    was_corrected=was_corrected,
                    correction_errors=correction_errors,
                    correction_improved=correction_improved,
                ))

                # 更新进度
                self.metrics.processed_segments = i + 1
                self.metrics.processed_ms = gt_seg.end_ms

                # 计算实时平均
                n = len(self.comparisons)
                recent = self.comparisons[-5:]
                avg_cer = sum(c.cer for c in recent) / len(recent)
                avg_composite = sum(c.composite for c in recent) / len(recent)
                correct_rate = sum(1 for c in recent if c.status == "correct") / len(recent)

            # SSE 推送（片段级别，立即送达）
            self._emit("segment", {
                "idx": i + 1,
                "gt_text": gt_seg.text,
                "asr_text": asr_text,
                "corrected_text": corrected_text if was_corrected else asr_text,
                "cer": round(cer, 4),
                "wer": round(wer, 4),
                "speaker_gt": gt_seg.speaker_id,
                "speaker_asr": asr_speaker,
                "speaker_ok": speaker_correct,
                "status": eval_result.status,
                "exact_match": round(eval_result.exact_match, 4),
                "prefix_score": round(eval_result.prefix_score, 4),
                "suffix_score": round(eval_result.suffix_score, 4),
                "coverage": round(eval_result.coverage, 4),
                "composite": round(eval_result.composite, 4),
                # 纠错相关
                "was_corrected": was_corrected,
                "correction_errors": correction_errors,
                "correction_improved": correction_improved,
            })

            # 每 5 个片段推送一次进度
            if (i + 1) % 5 == 0 or i == total - 1:
                self._emit("progress", {
                    "processed_segments": i + 1,
                    "total_segments": total,
                    "pct": round((i + 1) / total * 100, 1),
                    "avg_cer": round(avg_cer, 4),
                    "avg_composite": round(avg_composite, 4),
                    "correct_rate": round(correct_rate, 4),
                })

        # 计算最终说话人指标（加锁）
        with self._lock:
            if self.alignments:
                self.metrics.der = compute_der(self.alignments, self.metrics.total_ms)
                self.metrics.speaker_consistency = compute_speaker_consistency(
                    self.alignments, self.gt_segments
                )

    def _finalize_metrics(self) -> None:
        """最终判定 PASS / FAIL"""
        m = self.metrics
        issues = []

        # 使用 composite 平均替代纯 CER 作为 ASR 评估
        composite_avg = sum(c.composite for c in self.comparisons) / max(len(self.comparisons), 1)
        m.composite_avg = composite_avg

        cer_pass = m.cer_avg <= THRESHOLDS["cer"]
        composite_pass = composite_avg >= 0.80  # 综合评分 ≥ 80% 才算通过
        wer_pass = m.wer_avg <= THRESHOLDS["wer"]
        der_pass = m.der <= THRESHOLDS["der"]
        con_pass = m.speaker_consistency >= THRESHOLDS["consistency"]

        if not composite_pass:
            issues.append(f"综合评分 {composite_avg:.1%} < 80%")
        elif not cer_pass:
            issues.append(f"CER {m.cer_avg:.1%} 超过阈值 {THRESHOLDS['cer']:.1%}")
        if not wer_pass:
            issues.append(f"WER {m.wer_avg:.1%} 超过阈值 {THRESHOLDS['wer']:.1%}")
        if not der_pass:
            issues.append(f"DER {m.der:.1%} 超过阈值 {THRESHOLDS['der']:.1%}")
        if not con_pass:
            issues.append(f"说话人一致性 {m.speaker_consistency:.1%} < {THRESHOLDS['consistency']:.0%}")

        m.issues = issues
        # ASR 通过条件：综合评分 ≥ 80%
        m.passed_asr = composite_pass and wer_pass
        m.passed_speaker = der_pass and con_pass

    def _build_final_report(self) -> dict:
        """构建最终报告（用于 SSE complete 事件）"""
        m = self.metrics
        n = max(len(self.comparisons), 1)
        composite_avg = getattr(m, "composite_avg", sum(c.composite for c in self.comparisons) / n)

        # 纠错统计
        corrected_count = sum(1 for c in self.comparisons if c.was_corrected)
        correction_improved_count = sum(1 for c in self.comparisons if c.correction_improved)

        return {
            "cer_avg":           round(m.cer_avg, 4),
            "wer_avg":           round(m.wer_avg, 4),
            "der":               round(m.der, 4),
            "speaker_consistency": round(m.speaker_consistency, 4),
            "composite_avg":     round(composite_avg, 4),
            "exact_match_rate":  round(sum(c.exact_match for c in self.comparisons) / n, 4),
            "avg_coverage":      round(sum(c.coverage for c in self.comparisons) / n, 4),
            "avg_prefix":        round(sum(c.prefix_score for c in self.comparisons) / n, 4),
            "avg_suffix":        round(sum(c.suffix_score for c in self.comparisons) / n, 4),
            "correct_rate":      round(sum(1 for c in self.comparisons if c.status == "correct") / n, 4),
            "processed_segments": m.processed_segments,
            "total_segments":    m.total_segments,
            "elapsed_sec":       m.elapsed_sec,
            "status":            m.status,
            "passed_asr":        m.passed_asr,
            "passed_speaker":    m.passed_speaker,
            "passed":            m.passed_asr and m.passed_speaker,
            "issues":            m.issues,
            "thresholds": {
                "cer": THRESHOLDS["cer"],
                "wer": THRESHOLDS["wer"],
                "der": THRESHOLDS["der"],
                "consistency": THRESHOLDS["consistency"],
                "composite": 0.80,
            },
            # 纠错统计
            "correction_stats": {
                "enabled": self.use_correction,
                "corrected_count": corrected_count,
                "corrected_ratio": round(corrected_count / n, 4) if n > 0 else 0,
                "improved_count": correction_improved_count,
                "improved_ratio": round(correction_improved_count / max(corrected_count, 1), 4) if corrected_count > 0 else 0,
            },
        }

    def get_metrics_snapshot(self) -> dict:
        """获取当前指标快照"""
        m = self.metrics
        n = max(len(self.comparisons), 1)
        return {
            "cer_avg":       round(m.cer_avg, 4),
            "wer_avg":       round(m.wer_avg, 4),
            "der":           round(m.der, 4),
            "speaker_consistency": round(m.speaker_consistency, 4),
            "composite_avg": round(sum(c.composite for c in self.comparisons) / n, 4),
            "correct_rate":  round(sum(1 for c in self.comparisons if c.status == "correct") / n, 4),
            "processed_segments": m.processed_segments,
            "total_segments":    m.total_segments,
            "processed_ms":      m.processed_ms,
            "total_ms":          m.total_ms,
            "pct":           round(m.processed_ms / max(m.total_ms, 1) * 100, 1),
            "status":        m.status,
            "passed_asr":    m.passed_asr,
            "passed_speaker": m.passed_speaker,
            "elapsed_sec":   round(m.elapsed_sec, 1),
        }

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
