"""
流式 VAD + ASR + 声纹识别管道
支持实时流式转录和异步推送，避免音频积压
"""

import asyncio
import queue
import threading
import time
from typing import Optional, Callable, Dict, Tuple, List
from dataclasses import dataclass
import numpy as np
import torch

# ============== 配置 ==============

@dataclass
class StreamingChangeDetectorConfig:
    """流式说话人切换检测配置（超高灵敏度版 - 极速响应）"""

    # Embedding 参数
    embedding_interval_ms: float = 100.0       # 进一步降低：从 160ms 降至 100ms，更快提取 embedding
    embedding_min_for_detection: int = 5      # 降低：至少累积 5 个 embedding（约0.5秒）就开始检测

    # 变化点检测参数 - 超高灵敏度
    change_distance_threshold: float = 0.10    # 进一步降低阈值：从 0.15 降至 0.10，极高敏感度
    change_confirm_count: int = 1              # 降至 1：只需 1 个 embedding 偏离基准就确认，极速响应
    min_change_interval_ms: float = 800.0     # 降低间隔：从 1500ms 降至 800ms，更快检测连续变化

    # 动态阈值：启用时用 mean + factor * std 自动调整阈值
    use_dynamic_threshold: bool = True
    dynamic_factor: float = 0.3               # 降低因子：从 0.5 降至 0.3，阈值更敏感

    # 滑动窗口基准参数
    use_sliding_window: bool = True           # 启用滑动窗口基准
    sliding_window_size: int = 4              # 窗口大小：缩小到 4 个 embedding（约0.4秒）作为局部基准
                                               # 更快的响应速度

    # 渐变检测参数
    detect_jump_only: bool = True            # 只检测"跳变"而非持续偏高
    jump_threshold: float = 0.08             # 跳变阈值：降低到 0.08，更容易触发
    jump_confirm_count: int = 1               # 跳变确认：降至 1 个 embedding 即可确认

    # 稳定性保护参数（调整以适应超高灵敏度）
    min_segment_duration_ms: float = 2000.0  # 提高：从 1200ms 增至 2000ms，避免过短片段
    warmup_duration_ms: float = 1500.0      # 降低：从 3000ms 降至 1500ms，快速响应

    # 后处理变点检测（离线 Binary Segmentation）
    offline_changepoint: bool = True          # 是否启用后处理变点检测
    cp_min_segment_ms: float = 800.0         # 提高：从 400ms 增至 800ms，避免过短片段
    cp_penalty: float = 0.2                  # 降低惩罚：从 0.4 降至 0.2，允许更多分段

    def __post_init__(self):
        assert self.change_confirm_count >= 1


# 全局实例（方便微调）
CHANGE_DETECTOR_CONFIG = StreamingChangeDetectorConfig()


# VAD 配置
VAD_SAMPLE_RATE = 16000
VAD_WINDOW_SIZE = 512  # samples（Silero VAD 要求）
VAD_THRESHOLD = 0.30  # VAD 检测阈值（进一步降低以检测更多语音片段）

# 语音片段检测参数
MIN_SPEECH_DURATION_MS = 600  # 最小语音持续时间（毫秒）；提高到 0.6s，减少过短片段
MIN_SILENCE_DURATION_MS = 500  # 静音超时（毫秒），0.5秒静音触发分段，配合说话人标签合并逻辑
MIN_SPEECH_ENERGY_THRESHOLD = 0.005  # 最小能量阈值

# 段间上下文重叠配置
SEGMENT_OVERLAP_TAIL_MS = 200  # 保留上一段末尾 200ms 音频作为下一段 ASR 的预热上下文，减少边界丢字

# 声纹识别参数
SPEAKER_SIMILARITY_THRESHOLD = 0.5  # 声纹匹配相似度阈值
MAX_SPEAKERS = 10  # 最大支持说话人数

# 声纹识别置信度参数
SPEAKER_TOP_GAP_THRESHOLD = 0.03  # top1 和 top2 分数差距阈值，低于此值认为置信度不足
SPEAKER_SHORT_AUDIO_THRESHOLD_MS = 2000  # 短音频阈值（毫秒），低于此值认为是短片段
SPEAKER_STRICT_GAP_THRESHOLD = 0.03  # 严格阈值：只有 gap < 0.03 才触发 uncertain（更保守）


# ============== 数据结构 ==============

@dataclass
class TranscriptDelta:
    """流式转录增量结果"""
    text: str              # 转录文本
    is_final: bool         # 是否是最终结果
    start_ms: int         # 开始时间
    end_ms: int           # 结束时间
    speaker_id: Optional[str] = None  # 说话人ID（top-1）
    speaker_name: Optional[str] = None  # 说话人姓名
    speaker_confidence: float = 0.0   # 说话人置信度
    segment_reason: Optional[str] = None  # 分段原因：silence_timeout / voice_change
    # 多说话人候选（top-k），用于 uncertain 场景展示给用户选择
    speaker_candidates: Optional[List[Tuple[str, str, float]]] = None  # [(speaker_id, name, confidence), ...]
    # 与各已注册说话人的相似度（兼容旧接口）
    registered_speaker_sims: Optional[Dict[str, float]] = None  # {speaker_id: similarity}
    recognized_role: Optional[str] = None  # 推断的角色
    # 兼容旧字段（模式一：interviewer/candidate）
    interviewer_sim: float = 0.0  # 兼容：与面试官的相似度
    candidate_sim: float = 0.0    # 兼容：与候选人的相似度
    # 多窗口投票结果（方向1）
    uncertain_speaker: bool = False  # 投票结果是否 uncertain
    speaker_uncertain_reason: Optional[str] = None  # uncertain 原因
    speaker_multi_window_stats: Optional[dict] = None  # 多窗口统计 {"n_windows": int, "n_valid": int, ...}
    # MacBERT 纠错相关字段
    corrected_text: Optional[str] = None  # 纠错后的文本
    was_corrected: bool = False  # 是否进行了纠错
    correction_errors: Optional[List] = None  # 纠错详情 [("错字", "正字", 位置), ...]


@dataclass
class SpeechSegment:
    """语音片段"""
    audio_data: np.ndarray   # float32, 16kHz
    start_ms: int            # 开始时间
    end_ms: int             # 结束时间
    segment_reason: str = "unknown"  # 分段原因：silence_timeout / voice_change
    overlap_tail: Optional[np.ndarray] = None  # 上一段末尾的音频片段（200ms），ASR 预热上下文
    # 说话人标签（用于合并决策，在 Pipeline 层通过声纹识别填充）
    speaker_id: Optional[str] = None
    speaker_label: Optional[str] = None  # 说话人标签字符串，用于合并决策
    speaker_uncertain: bool = False  # 声纹识别置信度是否不足（top1/top2 差距过小）
    speaker_uncertain_reason: Optional[str] = None  # uncertain 原因描述
    # 声纹相似度候选（用于合并决策时判断标签变化是否真实）
    # 格式: {speaker_id: cosine_similarity}，用于检测"同一人被误识为不同标签"的情况
    speaker_sims: Optional[Dict[str, float]] = None
    # 音频片段的声纹 embedding（用于直接比较两个片段是否来自同一人）
    embedding: Optional[np.ndarray] = None


# ============== 流式 VAD 处理器 ==============

class StreamingVAD:
    """
    流式 VAD 检测器
    实时检测语音活动，支持变长片段
    """
    
    def __init__(self, vad_model, sample_rate: int = 16000):
        self.vad_model = vad_model
        self.sample_rate = sample_rate
        self.window_samples = VAD_WINDOW_SIZE
        
        # 状态
        self.reset()
        
        # 参数
        self.min_speech_samples = int(MIN_SPEECH_DURATION_MS * sample_rate / 1000)
        self.min_silence_samples = int(MIN_SILENCE_DURATION_MS * sample_rate / 1000)
        self.min_energy_threshold = MIN_SPEECH_ENERGY_THRESHOLD
        
        # 缓冲（累积到 512 samples）
        self._buffer = np.array([], dtype=np.float32)
        
        # 时间追踪
        self._total_samples_processed = 0
        
        # 说话人变化检测（滑动窗口 + 变化点检测）
        self._embedding_buffer: List[np.ndarray] = []   # 累积的 embedding
        self._embedding_timestamps_ms: List[int] = []   # 每个 embedding 对应的时间戳
        self._last_embedding_extract_ms = 0             # 上次提取时间
        self._embedding_extractor = None                # 由 pipeline 注入 SpeakerEmbeddingExtractor
        self._embedding_extraction_interval_samples = int(CHANGE_DETECTOR_CONFIG.embedding_interval_ms * sample_rate / 1000)
        self._pending_audio_lock = threading.Lock()
        self._embedding_lock = threading.Lock()          # 保护 _embedding_buffer / _embedding_timestamps_ms 的并发访问
        self._last_change_detected_ms = -999999        # 上次检测到换人的时间（ms）
        self._pending_audio_for_embedding: List[np.ndarray] = []  # 待提取的语音帧（仅VAD检测为speech时累积）
        self._prev_segment_tail: Optional[np.ndarray] = None  # 上一段末尾音频片段（200ms），ASR 预热上下文

    def reset(self):
        """重置状态"""
        self.state = "idle"  # idle, speech
        self.speech_buffer = []
        self.speech_start_sample = 0
        self.silence_samples = 0
        self._buffer = np.array([], dtype=np.float32)
        self._total_samples_processed = 0
        self._embedding_buffer = []
        self._embedding_timestamps_ms = []
        self._last_embedding_extract_ms = 0
        self._last_change_detected_ms = -999999
        self._pending_audio_for_embedding = []
        self._prev_segment_tail: Optional[np.ndarray] = None
    
    def feed(self, audio_chunk: np.ndarray) -> Optional[SpeechSegment]:
        """
        实时处理音频块
        
        Args:
            audio_chunk: 音频数据，float32，16kHz，可以是任意长度
        
        Returns:
            SpeechSegment 如果检测到完整语音片段，否则 None
        """
        # 累积到缓冲
        self._buffer = np.concatenate([self._buffer, audio_chunk])
        
        # 处理满 512 samples 的块
        while len(self._buffer) >= VAD_WINDOW_SIZE:
            chunk = self._buffer[:VAD_WINDOW_SIZE]
            self._buffer = self._buffer[VAD_WINDOW_SIZE:]
            
            # VAD 检测
            is_speech = self._detect_speech(chunk)
            
            # 仅在 VAD 检测为语音时，才累积音频用于 embedding 提取
            if is_speech and self._embedding_extractor is not None:
                self._pending_audio_for_embedding.append(chunk.copy())
            
            # 状态机
            result = self._update_state(is_speech, chunk)
            if result:
                return result
            
            self._total_samples_processed += VAD_WINDOW_SIZE
        
        return None
    
    def _detect_speech(self, chunk: np.ndarray) -> bool:
        """使用 Silero VAD + 能量检测"""
        # 能量检查：过滤低能量噪音
        energy = np.mean(chunk ** 2)
        if energy < self.min_energy_threshold:
            return False
        
        if self.vad_model is None:
            return True  # 无 VAD 模型时，用能量检测
        
        try:
            tensor = torch.from_numpy(chunk).float().unsqueeze(0)  # [1, 512]
            prob = self.vad_model(tensor, self.sample_rate).item()
            return prob > VAD_THRESHOLD
        except Exception as e:
            print(f"[VAD] 检测失败: {e}")
            return False
    
    def set_embedding_extractor(self, extractor):
        """注入 CAM++ embedding 提取器（由 StreamingPipeline 调用）"""
        self._embedding_extractor = extractor

    def extract_pending_embeddings(self) -> List[np.ndarray]:
        """
        从待处理音频中提取 embedding（每 EMBEDDING_EXTRACT_INTERVAL_MS 一次）。
        由 pipeline 的后台线程调用，返回提取到的 embedding 列表。
        只处理 VAD 检测为 speech 时的语音帧。
        """
        if self._embedding_extractor is None:
            return []

        with self._pending_audio_lock:
            if not self._pending_audio_for_embedding:
                return []

            # 把所有语音帧拼成一个连续数组
            audio = np.concatenate(self._pending_audio_for_embedding)
            self._pending_audio_for_embedding = []

            extracted = []
            interval = self._embedding_extraction_interval_samples
            while len(audio) >= interval:
                chunk = audio[:interval]
                audio = audio[interval:]

                try:
                    emb = self._embedding_extractor.extract(chunk)
                    if emb is not None and len(emb) > 0:
                        emb_norm = np.linalg.norm(emb)
                        # 过滤掉零向量和接近零的 embedding（通常是 CAM++ 对短/无效音频输出 NaN 后被替换的结果）
                        # 零向量与任何向量的余弦距离都是 1.0，会导致基准线失效，使整个变化检测崩溃
                        if emb_norm < 1e-6:
                            print(f"[VAD] 跳过零向量 embedding (norm={emb_norm:.2e})，避免破坏变化检测基准线")
                            continue
                        ts = int(self._total_samples_processed * 1000 / self.sample_rate)
                        with self._embedding_lock:
                            self._embedding_buffer.append(emb)
                            self._embedding_timestamps_ms.append(ts)
                        extracted.append(emb)
                        self._last_embedding_extract_ms = ts
                        # print(f"[DEBUG] Embedding 提取成功 #embedding={len(self._embedding_buffer)}, ts={ts}ms, norm={emb_norm:.4f}")
                except Exception as e:
                    print(f"[VAD] Embedding 提取失败: {e}")

            # 把还没处理完的剩余音频塞回去（下次继续）
            if len(audio) > 0:
                self._pending_audio_for_embedding.insert(0, audio)

            return extracted

    def _find_changepoint_offline(
        self,
        timestamps_ms: np.ndarray,
        distances: np.ndarray,
        start_ms: int,
        end_ms: int,
    ) -> Tuple[int, int]:
        """
        Binary Segmentation 变点检测（后处理）。

        在 distances 序列上用 Binary Segmentation 找出概率最大的变化点。
        用变化点对应的 embedding 时间戳，回溯计算 audio_data 中应该从哪个样本开始。

        Args:
            timestamps_ms: 每个 embedding 的时间戳（毫秒），和 distances 一一对应
            distances:     每个 embedding 到全局基准的余弦距离（标量）
            start_ms:      buffer 中 speech_start_sample 对应的毫秒时间
            end_ms:        buffer 中最后一个样本对应的毫秒时间

        Returns:
            (trim_start_ms, trim_end_ms):
                trim_start_ms: 修正后 segment 的起始时间（毫秒）
                trim_end_ms:   修正后 segment 的结束时间（毫秒）
                如果未检测到变化点，返回原始 (start_ms, end_ms)
        """
        cfg = CHANGE_DETECTOR_CONFIG
        if not cfg.offline_changepoint or len(distances) < 4:
            return start_ms, end_ms

        n = len(distances)
        # 每帧 ms 数（embedding_interval_ms）
        step_ms = cfg.embedding_interval_ms

        # ---- Binary Segmentation ----
        def binary_seg(data: np.ndarray, penalty: float) -> List[int]:
            """
            简化 Binary Segmentation（无 PELT 复杂代价函数，纯距离突变检测）。
            返回所有检测到的变化点索引列表。
            """
            n = len(data)
            if n < 4:
                return []

            def cost(seg: np.ndarray) -> float:
                # 段内方差 * 长度（类 SBC 代价）
                if len(seg) < 2:
                    return 0.0
                return float(np.var(seg)) * len(seg)

            def find_single_cp(seq: np.ndarray, start: int, stop: int) -> Tuple[float, int]:
                """在 seq[start:stop] 内找单个最优变化点，返回 (收益, cp_idx)。"""
                best_gain = 0.0
                best_cp = -1
                total_cost = cost(seq[start:stop])
                if total_cost <= 0:
                    return 0.0, -1
                for t in range(start + 2, stop - 2):
                    left = seq[start:t]
                    right = seq[t:stop]
                    gain = total_cost - cost(left) - cost(right) - penalty
                    if gain > best_gain:
                        best_gain = gain
                        best_cp = t
                return best_gain, best_cp

            cps = []
            stack = [(0, n)]
            while stack:
                start, stop = stack.pop()
                gain, cp = find_single_cp(data, start, stop)
                if cp < 0:
                    continue
                cps.append(cp)
                # 递归处理左右两段
                stack.append((start, cp))
                stack.append((cp, stop))
            cps.sort()
            return cps

        cps = binary_seg(distances, cfg.cp_penalty)
        if not cps:
            return start_ms, end_ms

        # ---- 取最后一个变化点（最接近当前时刻的那个）----
        # 变化点索引 → 时间戳
        cp_idx = cps[-1]
        cp_ms = int(timestamps_ms[cp_idx])

        # 变化点时间戳落在 buffer 的哪个位置
        cp_offset_from_start = cp_ms - start_ms
        if cp_offset_from_start < 0:
            cp_offset_from_start = 0

        # ms → 样本数
        trim_start_sample = int(cp_offset_from_start / 1000 * self.sample_rate)
        trim_start_ms = start_ms + trim_start_sample

        # 校验：修正后 segment 不能太短
        new_duration_ms = end_ms - trim_start_ms
        if new_duration_ms < cfg.cp_min_segment_ms:
            return start_ms, end_ms

        return trim_start_ms, end_ms

    def _detect_speaker_change_by_embedding(self) -> Tuple[bool, Optional[dict]]:
        """
        增强版说话人切换检测（提高灵敏度）。

        核心改进（方案一+二）：
        1. 滑动窗口基准：用最近 N 个 embedding 作为局部基准，而非全局基准
           - 优点：能适应说话人内部的自然波动，避免误检
           - 同时保留全局基准作为交叉验证

        2. 跳变检测：只检测"距离快速跳变"，而非"持续偏高"
           - 同一人说话：距离会在基准附近小幅波动
           - 换人时：距离会从低突然跳到高
           - 只在发生跳变时触发，降低误检

        3. 交叉验证：滑动窗口基准和全局基准都触发才确认
           - 避免单一基准误判

        Returns:
            (changed: bool, debug_info: dict or None)
        """
        cfg = CHANGE_DETECTOR_CONFIG

        # 在锁内一次性快照两个 list，防止与后台提取线程交错导致长度不一致
        with self._embedding_lock:
            emb_buffer = list(self._embedding_buffer)
            ts_list = list(self._embedding_timestamps_ms)

        # ---------- Warmup 检查（降低以提高灵敏度） ----------
        n = len(emb_buffer)
        if n < cfg.embedding_min_for_detection:
            return False, None

        timestamps_arr = np.array(ts_list)
        elapsed_ms = int(timestamps_arr[-1] - timestamps_arr[0])
        if elapsed_ms < cfg.warmup_duration_ms:
            return False, None

        # ---------- 过滤零向量 ----------
        norms = np.array([np.linalg.norm(e) for e in emb_buffer])
        valid_mask = norms > 1e-6
        embs_raw = np.array(emb_buffer)[valid_mask]
        embs_valid = np.array([
            e / (np.linalg.norm(e) + 1e-8) for e in embs_raw
        ])
        timestamps_valid = np.array(ts_list)[valid_mask]

        if len(embs_valid) < cfg.embedding_min_for_detection:
            return False, None

        # ---------- 最小段长检查 ----------
        segment_duration_ms = int(timestamps_arr[-1] - timestamps_arr[0])
        if segment_duration_ms < cfg.min_segment_duration_ms:
            return False, None

        # ---------- 最小间隔检查 ----------
        current_time_ms = int(timestamps_valid[-1])
        if current_time_ms - self._last_change_detected_ms < cfg.min_change_interval_ms:
            return False, None

        # ========== 新算法：滑动窗口基准 + 跳变检测 ==========

        n_v = len(embs_valid)

        # ---------- 1. 计算全局基准（交叉验证用） ----------
        global_reference = np.median(embs_valid, axis=0)
        global_reference = global_reference / (np.linalg.norm(global_reference) + 1e-8)

        global_distances = np.array([
            float(1.0 - np.clip(np.dot(emb, global_reference), -1.0, 1.0))
            for emb in embs_valid
        ])

        # ---------- 2. 计算滑动窗口基准（核心检测用） ----------
        if cfg.use_sliding_window and n_v >= cfg.sliding_window_size:
            window_size = cfg.sliding_window_size
            # 滑动窗口取最老的 N 个 embedding 作为基准（不包括最新的，避免滞后）
            window_start = max(0, n_v - window_size - cfg.change_confirm_count)
            window_embs = embs_valid[window_start:window_start + window_size]
            window_ref = np.median(window_embs, axis=0)
            window_ref = window_ref / (np.linalg.norm(window_ref) + 1e-8)

            window_distances = np.array([
                float(1.0 - np.clip(np.dot(emb, window_ref), -1.0, 1.0))
                for emb in embs_valid
            ])
        else:
            # 数据不足时用全局基准
            window_distances = global_distances
            window_ref = global_reference

        # ---------- 3. 计算两两距离（用于检测双簇结构） ----------
        pairwise_dists = []
        for i in range(n_v):
            for j in range(i + 1, n_v):
                d = float(1.0 - np.clip(np.dot(embs_valid[i], embs_valid[j]), -1.0, 1.0))
                pairwise_dists.append(d)
        pairwise_dists = np.array(pairwise_dists)
        max_pairwise = float(np.max(pairwise_dists)) if len(pairwise_dists) > 0 else 0.0

        # ---------- 4. 基准统计 ----------
        mean_d = float(np.mean(window_distances))
        std_d = float(np.std(window_distances)) + 1e-8

        # 动态阈值（降低以提高灵敏度）
        if cfg.use_dynamic_threshold:
            dynamic_threshold = mean_d + cfg.dynamic_factor * std_d
            threshold = max(cfg.change_distance_threshold, dynamic_threshold)
            threshold = min(threshold, 0.85)  # 从 0.95 降至 0.85，更敏感
        else:
            threshold = cfg.change_distance_threshold

        confirm_count = cfg.change_confirm_count
        if n_v < confirm_count + 2:
            return False, None

        recent_distances = window_distances[-confirm_count:]

        # ---------- 5. 跳变检测（核心改进 - 超高灵敏度） ----------
        # 计算最近 embedding 的变化趋势
        jump_detected = False
        if cfg.detect_jump_only and len(window_distances) >= 3:
            # 用滑动窗口基准的均值作为"正常"水平
            baseline = np.mean(window_distances[:-confirm_count]) if len(window_distances) > confirm_count + 1 else mean_d

            # 检查最近的 embedding 是否发生跳变
            # 跳变条件：最近的 embedding 比基准高出 jump_threshold
            recent_high = recent_distances - baseline
            jump_count = sum(1 for d in recent_high if d > cfg.jump_threshold)

            # 额外检查：最近 embedding 是否明显高于历史均值
            # 真正的跳变：最近几个 embedding 突然升高
            early_mean = np.mean(window_distances[:-confirm_count]) if len(window_distances) > confirm_count + 1 else mean_d
            recent_mean = np.mean(recent_distances)
            is_jump = (recent_mean - early_mean) > cfg.jump_threshold * 1.2  # 降低跳变幅度要求

            # 双簇证据：放宽条件，只要求最大两两距离超过较低的阈值
            cluster_evidence = max_pairwise > cfg.jump_threshold * 1.5  # 使用 jump_threshold 的 1.5 倍作为双簇证据阈值

            jump_detected = (jump_count >= confirm_count) and is_jump and cluster_evidence
        else:
            # 传统检测方式（fallback）
            all_exceed = all(d > threshold for d in recent_distances)
            recent_mean = float(np.mean(recent_distances))
            recent_exceeds_mean = recent_mean > mean_d + 0.03  # 放宽条件
            cluster_bimodal = max_pairwise > threshold * 0.8  # 放宽双簇要求
            jump_detected = all_exceed and recent_exceeds_mean and cluster_bimodal

        # ---------- 6. 全局基准交叉验证（放宽条件） ----------
        # 确保全局基准也显示异常（避免滑动窗口误判）
        global_recent = global_distances[-confirm_count:]
        global_mean = float(np.mean(global_distances))
        global_exceed = np.mean(global_recent) > global_mean + 0.05  # 从 0.08 降至 0.05
        global_threshold = global_mean + 0.4 * float(np.std(global_distances))  # 从 0.6 降至 0.4
        global_threshold = min(global_threshold, 0.70)  # 从 0.80 降至 0.70，更敏感
        global_confirmed = np.mean(global_recent) > global_threshold

        # 双重确认：只要滑动窗口基准触发 OR（全局基准强烈确认）即可
        change_confirmed = jump_detected and (global_exceed or global_confirmed)

        if change_confirmed:
            self._last_change_detected_ms = current_time_ms

            # ===== 详细调试日志 =====
            emb_distances = list(zip(
                [int(t) for t in timestamps_valid],
                [float(d) for d in window_distances]
            ))

            first_drift = None
            for ts, d in emb_distances:
                if d > threshold:
                    first_drift = (ts, d)
                    break

            # 计算跳变信息
            early_dist = np.mean(window_distances[:-confirm_count]) if len(window_distances) > confirm_count + 2 else mean_d
            jump_magnitude = float(np.mean(recent_distances) - early_dist)

            print(f"[VAD-DBG] *** SPEAKER CHANGE *** 检测时刻={current_time_ms}ms")
            print(f"[VAD-DBG]   跳变检测: recent_mean={np.mean(recent_distances):.3f}, "
                  f"baseline={early_dist:.3f}, jump_mag={jump_magnitude:.3f}, "
                  f"jump_threshold={cfg.jump_threshold:.3f}")
            print(f"[VAD-DBG]   阈值: window_thr={threshold:.3f}, global_thr={global_threshold:.3f}")
            print(f"[VAD-DBG]   双簇证据: pair_max={max_pairwise:.3f}, threshold={threshold:.3f}")
            print(f"[VAD-DBG]   embedding 分布: 共{len(embs_valid)}个, "
                  f"最早={int(timestamps_valid[0])}ms, 最新={int(timestamps_valid[-1])}ms, "
                  f"跨度={int(timestamps_valid[-1]-timestamps_valid[0])}ms")
            print(f"[VAD-DBG]   各embedding距离: {[(f'{t}ms:{d:.3f}') for t,d in emb_distances]}")
            print(f"[VAD-DBG]   首个显著偏离: {first_drift}")
            print(f"[VAD-DBG]   speech_buffer: 共{len(self.speech_buffer)}块, "
                  f"总样本={sum(len(x) for x in self.speech_buffer)}, "
                  f"起始={self.speech_start_sample}")

            debug_info = {
                "current_time_ms": current_time_ms,
                "segment_duration_ms": segment_duration_ms,
                "d": float(recent_distances[-1]),
                "mean_d": float(mean_d),
                "pair_max": float(max_pairwise),
                "threshold": float(threshold),
                "valid_count": len(embs_valid),
                "first_drift": first_drift,
                "emb_distances": emb_distances,
                "timestamps_first": int(timestamps_arr[0]),
                "timestamps_last": int(timestamps_arr[-1]),
                "total_samples_in_buffer": int(self._total_samples_processed - self.speech_start_sample),
                "speech_start_sample": int(self.speech_start_sample),
                "total_processed": int(self._total_samples_processed),
                "confirm_count": int(confirm_count),
                "jump_magnitude": jump_magnitude,
                "baseline": early_dist,
                "distances": window_distances.tolist(),
                "timestamps_ms_arr": timestamps_valid.tolist(),
                "global_distances": global_distances.tolist(),
                "global_threshold": float(global_threshold),
            }
            return True, debug_info

        return False, None

    def _update_state(self, is_speech: bool, chunk: np.ndarray) -> Optional[SpeechSegment]:
        """更新状态机：VAD 静音超时 + 聚类稳定性说话人切换检测"""
        if self.state == "idle":
            if is_speech:
                self.state = "speech"
                self.speech_start_sample = self._total_samples_processed
                self.speech_buffer = []
                self.silence_samples = 0
                self.speech_buffer.append(chunk)  # 保存音频
                print(f"[VAD] 语音开始 (样本={self.speech_start_sample})")
        
        elif self.state == "speech":
            self.speech_buffer.append(chunk)  # 保存所有帧

            # 说话人变化检测（基于聚类稳定性的 embedding 比对）
            voice_changed, change_info = self._detect_speaker_change_by_embedding()
            if voice_changed and len(self.speech_buffer) >= 3:
                total_samples = sum(len(x) for x in self.speech_buffer)
                audio_data = np.concatenate(self.speech_buffer)
                start_ms = int(self.speech_start_sample * 1000 / self.sample_rate)
                end_ms = int((self.speech_start_sample + total_samples) * 1000 / self.sample_rate)

                # 从 debug_info 取换人点数据
                info = change_info or {}
                change_det_ms = info.get("current_time_ms", 0)
                first_drift = info.get("first_drift")
                valid_count = info.get("valid_count", 0)
                d_val = info.get("d", 0)
                mean_d = info.get("mean_d", 0)
                pair_max = info.get("pair_max", 0)
                threshold = info.get("threshold", 0)
                emb_distances = info.get("emb_distances", [])
                distances = info.get("distances", [])
                timestamps_cp = info.get("timestamps_ms_arr", [])

                change_offset_from_start = change_det_ms - start_ms

                print(f"[VAD-DBG] >>> 强制分段详情 <<<")
                print(f"[VAD-DBG]   Buffer: {len(self.speech_buffer)}块/{total_samples}样本/{total_samples/self.sample_rate:.2f}s, ASR: [{start_ms}-{end_ms}ms]")
                print(f"[VAD-DBG]   首个偏离embedding: {first_drift[0] if first_drift else 'N/A'}ms, d={first_drift[1] if first_drift else 'N/A'}")
                print(f"[VAD-DBG]   检测参数: d={d_val:.3f}, mean={mean_d:.3f}, pair_max={pair_max:.3f}, thr={threshold:.3f}")
                # embedding 列表精简：首3个 + 最后1个
                _embs = [(f'{t}ms:{d:.3f}') for t, d in emb_distances]
                if valid_count <= 5:
                    _emb_str = _embs
                else:
                    _emb_str = _embs[:3] + [f"...({valid_count - 6}个)..."] + _embs[-3:]
                print(f"[VAD-DBG]   embeddings({valid_count}): {_emb_str}")
                print(f"[VAD-DBG] <<< 强制分段详情结束 >>>")

                # ===== 后处理变点检测：离线 Binary Segmentation 修正 audio_data =====
                _raw_start_ms = start_ms
                _raw_end_ms = end_ms
                _trimmed = False
                if CHANGE_DETECTOR_CONFIG.offline_changepoint and len(distances) >= 4 and len(timestamps_cp) == len(distances):
                    ts_arr = np.array(timestamps_cp, dtype=np.int64)
                    d_arr = np.array(distances, dtype=np.float64)
                    trim_start_ms, trim_end_ms = self._find_changepoint_offline(
                        ts_arr, d_arr, start_ms, end_ms
                    )
                    if trim_start_ms > start_ms:
                        # 找到了更优变化点，trim audio_data
                        trim_sample = int((trim_start_ms - start_ms) / 1000 * self.sample_rate)
                        audio_data_trimmed = audio_data[trim_sample:]
                        trim_ms = trim_start_ms - start_ms
                        _trimmed = True
                        start_ms = trim_start_ms
                        # end_ms 不变
                        overlap_samples = int(SEGMENT_OVERLAP_TAIL_MS * self.sample_rate / 1000)
                        overlap_tail = audio_data_trimmed[-overlap_samples:] if len(audio_data_trimmed) >= overlap_samples else audio_data_trimmed
                        self._prev_segment_tail = overlap_tail.copy()
                        print(f"[VAD-CP] ✅ 后处理变点修正: trim前=[{_raw_start_ms}-{_raw_end_ms}ms] "
                              f"→ trim后=[{start_ms}-{end_ms}ms] (丢弃{trim_ms:.0f}ms/{trim_sample}样本)")
                    else:
                        overlap_samples = int(SEGMENT_OVERLAP_TAIL_MS * self.sample_rate / 1000)
                        overlap_tail = audio_data[-overlap_samples:] if total_samples >= overlap_samples else audio_data
                        self._prev_segment_tail = overlap_tail.copy()
                        print(f"[VAD-CP] ⏭️  无更优变化点，保持原始分段")
                else:
                    overlap_samples = int(SEGMENT_OVERLAP_TAIL_MS * self.sample_rate / 1000)
                    overlap_tail = audio_data[-overlap_samples:] if total_samples >= overlap_samples else audio_data
                    self._prev_segment_tail = overlap_tail.copy()
                # ===== 后处理结束 =====

                # POLLUTION 日志用修正后的 start_ms
                first_emb_ts = emb_distances[0][0] if emb_distances else change_det_ms
                first_drift_d = first_drift[1] if first_drift else 0.0
                buffer_total_ms = total_samples / self.sample_rate * 1000
                pollution_ms = end_ms - change_det_ms
                pollution_pct = pollution_ms / buffer_total_ms * 100 if buffer_total_ms > 0 else 0
                _confirm = info.get("confirm_count", 0)
                if _trimmed:
                    print(f"[VAD-POLLUTION] ⚠️ 分段=[{start_ms}-{end_ms}ms](已修正) | "
                          f"Buffer原始={_raw_start_ms}-{_raw_end_ms}ms | "
                          f"实时检测={change_det_ms}ms | "
                          f"混入新说话人≈{pollution_ms:.0f}ms({pollution_pct:.0f}%)")
                else:
                    print(f"[VAD-POLLUTION] ⚠️ 分段=[{start_ms}-{end_ms}ms] | "
                          f"Buffer时长={buffer_total_ms:.0f}ms | "
                          f"VAD检测={change_det_ms}ms(偏{change_offset_from_start:.0f}ms) | "
                          f"混入新说话人≈{pollution_ms:.0f}ms({pollution_pct:.0f}%) | "
                          f"首个embedding@{first_emb_ts}ms,d={first_drift_d:.3f} | "
                          f"embedding确认需{_confirm}帧≈{_confirm * 320}ms滞后")

                print(f"[VAD] 检测到说话人变化，强制分段 ({start_ms}-{end_ms}ms, 原因=声纹变化)")
                self.speech_buffer = []
                self.speech_start_sample = self._total_samples_processed
                self.silence_samples = 0
                self._embedding_buffer.clear()
                self._embedding_timestamps_ms.clear()

                return SpeechSegment(
                    audio_data=audio_data_trimmed if _trimmed else audio_data,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    segment_reason="voice_change",
                    overlap_tail=self._prev_segment_tail,
                )
            
            # ---------- 静音超时检测（独立于声纹变化） ----------
            if is_speech:
                self.silence_samples = 0
            else:
                self.silence_samples += VAD_WINDOW_SIZE
                if self.silence_samples >= self.min_silence_samples:
                    total_samples = sum(len(x) for x in self.speech_buffer)
                    if total_samples >= self.min_speech_samples:
                        audio_data = np.concatenate(self.speech_buffer)
                        start_ms = int(self.speech_start_sample * 1000 / self.sample_rate)
                        end_ms = int((self.speech_start_sample + total_samples) * 1000 / self.sample_rate)
                        silence_dur = int(self.silence_samples * 1000 / self.sample_rate)
                        # 保存本段末尾 200ms 音频，作为下一段的 ASR 预热上下文
                        overlap_samples = int(SEGMENT_OVERLAP_TAIL_MS * self.sample_rate / 1000)
                        overlap_tail = audio_data[-overlap_samples:] if total_samples >= overlap_samples else audio_data
                        self._prev_segment_tail = overlap_tail.copy()

                        print(f"[VAD] 静音超时结束 ({start_ms}-{end_ms}ms, 静音={silence_dur}ms)")
                        self.state = "idle"
                        self.speech_buffer = []
                        self.speech_start_sample = 0
                        self.silence_samples = 0
                        self._embedding_buffer.clear()
                        self._embedding_timestamps_ms.clear()
                        return SpeechSegment(
                            audio_data=audio_data,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            segment_reason="silence_timeout",
                            overlap_tail=self._prev_segment_tail,
                        )
                    else:
                        print(f"[VAD] 语音太短，忽略 ({total_samples} samples)")
                        self.state = "idle"
                        self.speech_buffer = []
                        self.speech_start_sample = 0
                        self.silence_samples = 0
                        self._embedding_buffer.clear()
                        self._embedding_timestamps_ms.clear()
        
        return None


# ============== 流式 ASR 处理器 ==============

class StreamingASR:
    """
    流式 ASR 处理器
    使用 FunASR 推理，支持实时输出
    """
    
    def __init__(self, asr_model):
        self.asr_model = asr_model
    
    def recognize(
        self, 
        audio_data: np.ndarray,
        on_delta: Callable[[TranscriptDelta], None],
        language: str = "zh"
    ):
        """
        识别音频数据（流式增量模式）

        Args:
            audio_data: 音频数据，float32，16kHz
            on_delta: 回调函数，实时推送转录结果
            language: 语言，zh 或 en

        FunASR 的 `is_streaming=True` 会在识别过程中实时回调中间结果，
        每来一个新字符就通过 on_delta 推送，不用等整句说完。
        """
        try:
            result = self.asr_model.generate(
                input=audio_data,
                batch_size_s=300,
                is_streaming=True,
                language=language,
            )

            for item in result:
                is_final = True
                text = None
                if isinstance(item, dict):
                    text = item.get("text", "")
                elif isinstance(item, str):
                    text = item.strip()

                if text:
                    print(f"[ASR] 转录增量: {text}")
                    on_delta(TranscriptDelta(
                        text=text,
                        is_final=is_final,
                        start_ms=0,
                        end_ms=0
                    ))

        except Exception as e:
            print(f"[ASR] 识别失败: {e}")
            import traceback
            traceback.print_exc()


# ============== 流式声纹识别器（兼容旧接口） ==============

from app.model_manager import SpeakerEmbeddingExtractor


class StreamingSpeakerRecognition:
    """
    流式声纹识别
    实时比对说话人身份
    """
    
    def __init__(self, camp_model, device="cuda"):
        self.camp_model = camp_model
        self.extractor = SpeakerEmbeddingExtractor(camp_model, device=device)
    
    def extract_and_compare(
        self,
        audio_data: np.ndarray,
        registered_embeddings: dict,
        threshold: float = 0.75
    ) -> Optional[Tuple[str, float, Dict[str, float]]]:
        """
        提取声纹并比对（多人版本）

        Args:
            audio_data: 音频数据，float32，16kHz
            registered_embeddings: 已注册的声纹 {speaker_id: embedding}
            threshold: 相似度阈值

        Returns:
            (best_speaker_id, best_score, all_sims_dict) 如果匹配，否则 None
            all_sims_dict: {speaker_id: normalized_score}
        """
        try:
            if not registered_embeddings:
                print("[声纹] 没有已注册的说话人，无法进行声纹识别")
                return None

            print(f"[声纹] 开始识别，音频长度={len(audio_data)/16000:.2f}秒，已注册: {list(registered_embeddings.keys())}")

            embedding = self.extractor.extract(audio_data)

            emb_norm = np.linalg.norm(embedding)
            print(f"[声纹] 声纹特征: L2={emb_norm:.4f}, 维度={len(embedding)}")

            # 检测零向量 embedding（通常是 CAM++ 对短/无效音频输出 NaN 后被替换的结果）
            # 零向量与任何向量的余弦相似度都接近 0.5（归一化后），导致识别结果完全不可靠
            if emb_norm < 1e-6:
                print(f"[声纹] 警告: 检测到零向量 embedding (norm={emb_norm:.2e})，识别结果不可靠，返回空匹配")
                return ("__unknown__", 0.0, {})

            best_match = None
            best_score = 0
            all_sims = {}

            for speaker_id, registered_emb in registered_embeddings.items():
                cos_sim = np.dot(embedding, registered_emb) / (
                    np.linalg.norm(embedding) * np.linalg.norm(registered_emb)
                )
                score = (cos_sim + 1.0) / 2.0

                all_sims[speaker_id] = float(score)
                print(f"[声纹] 与 {speaker_id} 相似度: cos={cos_sim:.3f}, score={score:.3f}")

                if score > best_score:
                    best_score = score
                    best_match = speaker_id

            if best_match:
                print(f"[声纹] 识别结果: {best_match} (score={best_score:.3f})")
                return (best_match, float(best_score), all_sims)
            return None

        except Exception as e:
            print(f"[声纹] 声纹识别异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    def extract_topk_and_compare(
        self,
        audio_data: np.ndarray,
        registered_embeddings: dict,
        top_k: int = 3,
        threshold: float = 0.60
    ) -> Optional[Tuple[List[Tuple[str, float]], Dict[str, float]]]:
        """
        提取声纹并返回 top-k 比对结果（多说话人高精度版本）

        Args:
            audio_data: 音频数据，float32，16kHz
            registered_embeddings: 已注册的声纹 {speaker_id: embedding}
            top_k: 返回的候选数量
            threshold: 最低分数阈值

        Returns:
            (topk_matches, all_sims_dict) 匹配列表 [(speaker_id, score), ...] + 所有相似度
        """
        try:
            if not registered_embeddings:
                print("[声纹] 没有已注册的说话人")
                return None

            embedding = self.extractor.extract(audio_data)

            emb_norm = np.linalg.norm(embedding)
            if emb_norm < 1e-6:
                print(f"[声纹-topk] 警告: 零向量 embedding，topk 结果不可靠，返回空")
                return ([], {})

            all_sims = {}
            for speaker_id, registered_emb in registered_embeddings.items():
                cos_sim = np.dot(embedding, registered_emb) / (
                    np.linalg.norm(embedding) * np.linalg.norm(registered_emb)
                )
                score = (cos_sim + 1.0) / 2.0
                all_sims[speaker_id] = float(score)

            # 排序取 top-k
            sorted_speakers = sorted(all_sims.items(), key=lambda x: x[1], reverse=True)
            topk = [(sid, score) for sid, score in sorted_speakers[:top_k]
                    if score >= threshold]

            print(f"[声纹-topk] 音频长度={len(audio_data)/16000:.2f}秒，top-{len(topk)}: {topk}")
            return (topk, all_sims)

        except Exception as e:
            print(f"[声纹-topk] 识别异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    def extract_multi_window(
        self,
        audio_data: np.ndarray,
        n_windows: int = 3,
        window_step_ratio: float = 0.25,
    ) -> list[tuple[np.ndarray, float, bool]]:
        """从音频中提取多个滑动窗口的 embedding。"""
        return self.extractor.extract_multi_window(audio_data, n_windows, window_step_ratio)

    def extract_fused(
        self,
        audio_data: np.ndarray,
        n_windows: int = 3,
        window_step_ratio: float = 0.25,
        fusion_method: str = "mean",
    ) -> tuple[np.ndarray, dict]:
        """提取并融合多窗口 embedding。"""
        return self.extractor.extract_fused(
            audio_data, n_windows, window_step_ratio, fusion_method
        )


# ============== 流式处理管道 ==============

class StreamingPipeline:
    """
    流式 VAD + ASR + 声纹识别管道 + MacBERT 文本纠错

    特性：
    - 实时流式处理，无需等待完整音频
    - ASR 支持实时输出中间结果
    - 声纹识别异步比对
    - MacBERT 文本纠错后处理
    - 异步回调，不会阻塞音频接收
    """

    # MacBERT 纠错器单例
    _corrector = None

    def __init__(
        self,
        vad_model,
        asr_model,
        punc_model=None,
        camp_model=None,
        language: str = "zh",
        device: str = "cuda",
        use_correction: bool = True
    ):
        self.vad = StreamingVAD(vad_model)
        self.asr = StreamingASR(asr_model)
        self.punc_model = punc_model  # 标点模型独立持有，在 _process_loop 中异步调用
        self.speaker = StreamingSpeakerRecognition(camp_model, device=device) if camp_model else None
        self.language = language
        self.use_correction = use_correction  # 是否启用 MacBERT 纠错

        # MacBERT 纠错器延迟加载
        self._corrector_initialized = False

        # CAM++ embedding 提取器（用于 VAD 说话人边界检测）
        if camp_model is not None:
            from app.model_manager import SpeakerEmbeddingExtractor
            self._embedding_extractor = SpeakerEmbeddingExtractor(camp_model, device=device)
            self.vad.set_embedding_extractor(self._embedding_extractor)
        else:
            self._embedding_extractor = None

        # 后台 embedding 提取线程
        self._embedding_thread_running = False
        self._embedding_thread: Optional[threading.Thread] = None

        # 回调（可以是普通函数或协程）
        self.on_transcript: Optional[Callable] = None
        self.on_speaker: Optional[Callable] = None
        self.on_speech_segment: Optional[Callable] = None
        
        # 注册的声纹（改为 dict，支持多说话人）
        self._registered_speakers: Dict[str, np.ndarray] = {}

        # 是否使用增强版声纹引擎（MultiSpeakerRegistry）
        self._use_enhanced_engine = False
        self._enhanced_registry = None  # MultiSpeakerRegistry 实例

        # 事件循环引用（从 feed_audio 调用时自动获取）
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # 转录结果队列（使用 queue.Queue 保证线程安全）
        self._transcript_queue: queue.Queue = queue.Queue(maxsize=100)

        # 后台处理任务
        self._process_task: Optional[asyncio.Task] = None

        # ASR 互斥锁（FunASR 不支持并行调用）
        self._asr_lock = asyncio.Lock()

        # 默认说话人标签（当没有声纹注册时使用）
        self._speaker_counter = 0
        self._use_default_speaker = True  # 是否使用默认说话人标签

        # 多窗口投票融合参数
        self._multi_window_enabled = True   # 是否启用多窗口投票
        self._multi_window_n: int = 3     # 窗口数量
        self._multi_window_step: float = 0.25  # 步长比例（0.25=重叠75%）
        self._multi_window_vote: str = "score_weighted"  # 投票方法

        # ===== 说话人标签合并逻辑 =====
        # 片段缓冲区：暂存待确认的片段，等待下一个片段的说话人标签
        self._pending_segments: List[SpeechSegment] = []
        self._pending_lock = threading.Lock()  # 保护 pending_segments 的并发访问

        # 合并策略配置
        self._merge_enabled: bool = True  # 是否启用合并
        self._merge_max_wait_ms: float = 10000.0  # 最大等待时间（毫秒），超过此时间强制提交
        self._merge_min_same_label: int = 2  # 至少需要多少个相同标签的片段才合并
        self._merge_min_duration_ms: float = 500.0  # 最小合并长度（毫秒），防止过短片段

        # 上一段的说话人标签（用于与下一段比较）
        self._last_speaker_label: Optional[str] = None

        # 全局片段追踪计数器（用于关联同一片段的完整处理流程）
        self._track_counter = 0
        self._track_lock = threading.Lock()

        # ===== 分割统计 =====
        self._segment_stats = {
            "silence_timeout": 0,   # 静音超时分割数
            "voice_change": 0,       # 声纹突变分割数
            "merged_submit": 0,      # 合并后提交数
            "timeout_submit": 0,     # 超时强制提交数
            "total_segments": 0,     # 总VAD片段数
            "total_merged": 0,       # 总合并片段数（送去ASR的）
        }

        print("[管道] 说话人标签合并逻辑已启用")

    def register_speaker(self, speaker_id: str, embedding: np.ndarray,
                          name: Optional[str] = None, role: Optional[str] = None):
        """
        注册说话人声纹（支持多说话人）

        Args:
            speaker_id: 说话人唯一标识
            embedding: 192 维声纹向量
            name: 说话人姓名
            role: 角色标签
        """
        self._registered_speakers[speaker_id] = embedding
        print(f"[管道] 已注册说话人: {speaker_id}({name or 'unknown'}), "
              f"当前共 {len(self._registered_speakers)} 位: {list(self._registered_speakers.keys())}")
        if self.speaker:
            print(f"[管道] StreamingSpeakerRecognition 已配置")
        else:
            print(f"[管道] 警告: StreamingSpeakerRecognition 未配置（camp_model=None）")

    def unregister_speaker(self, speaker_id: str) -> bool:
        """注销说话人"""
        if speaker_id in self._registered_speakers:
            del self._registered_speakers[speaker_id]
            print(f"[管道] 已注销说话人: {speaker_id}, 剩余 {len(self._registered_speakers)} 位")
            return True
        return False

    def set_enhanced_registry(self, registry):
        """
        接入增强版声纹引擎（MultiSpeakerRegistry）
        接入后，所有声纹比对优先走 cascade matching 引擎
        """
        if not hasattr(self, '_enhanced_registry') or self._enhanced_registry is None:
            self._use_enhanced_engine = True
            print("[管道] 已接入增强版声纹引擎（cascade matching + dynamic threshold）")
        self._enhanced_registry = registry

    def set_multi_window(self, enabled: bool = True, n_windows: int = 3,
                         window_step_ratio: float = 0.25, vote_method: str = "score_weighted"):
        """
        配置多窗口投票融合参数。

        Args:
            enabled: 是否启用多窗口投票（默认 True）
            n_windows: 滑动窗口数量，建议 3~5
            window_step_ratio: 步长占窗口长度比例，0.25 = 重叠 75%，值越小重叠越多
            vote_method: 投票方法，"hard"（多数票）/ "score_weighted"（分数加权）/ "rank_weighted"（排名加权）
        """
        self._multi_window_enabled = enabled
        self._multi_window_n = n_windows
        self._multi_window_step = window_step_ratio
        self._multi_window_vote = vote_method
        mode_str = "enabled" if enabled else "disabled"
        print(f"[管道] 多窗口投票: {mode_str}, n={n_windows}, step_ratio={window_step_ratio}, method={vote_method}")

    def set_merge_strategy(self, enabled: bool = True, max_wait_ms: float = 5000.0,
                           min_same_label: int = 2, min_duration_ms: float = 500.0):
        """
        配置说话人标签合并策略。

        Args:
            enabled: 是否启用合并（默认 True）
            max_wait_ms: 最大等待时间（毫秒），超过此时间强制提交当前缓冲区的片段（默认 2000ms）
            min_same_label: 至少需要多少个相同标签的片段才合并（默认 2）
            min_duration_ms: 最小合并长度（毫秒），防止过短片段（默认 500ms）
        """
        self._merge_enabled = enabled
        self._merge_max_wait_ms = max_wait_ms
        self._merge_min_same_label = min_same_label
        self._merge_min_duration_ms = min_duration_ms
        print(f"[管道] 合并策略: enabled={enabled}, max_wait={max_wait_ms}ms, "
              f"min_same_label={min_same_label}, min_duration={min_duration_ms}ms")

    def _labels_match(self, label1: Optional[str], label2: Optional[str]) -> bool:
        """
        判断两个说话人标签是否匹配。

        匹配规则：
        1. 两个标签都不为 None 且相等 → 匹配
        2. 两个标签都为 None → 匹配（都未识别，视为同一人）
        3. 一个为 None 一个不为 None → 不匹配
        4. 标签不相等 → 不匹配
        """
        if label1 is None and label2 is None:
            return True
        if label1 is None or label2 is None:
            return False
        return label1 == label2

    # 声纹相似度回退阈值：用于检测"同一人被误识为不同标签"
    # 如果新片段与旧片段的 embedding 余弦相似度 >= 此阈值，认为是同一人
    _SPEAKER_EMB_SIM_THRESHOLD: float = 0.65  # embedding 直接比较的余弦相似度阈值，低于此值判定为换人

    def _check_speaker_similarity_for_merge(
        self, segment: SpeechSegment, last_pending_label: str
    ) -> bool:
        """
        检查新片段是否可能与缓冲区中最后一个片段是同一人（尽管被识别为不同标签）。

        核心思想：当声纹识别器将同一个人的两段语音识别为不同标签时，
        通过直接比较两个片段的音频 embedding 来判断是否应该继续合并。

        判定条件：新片段与缓冲区最后一个片段的 embedding 余弦相似度 >= 阈值

        Args:
            segment: 新来的片段（已带有 speaker_label 和 embedding）
            last_pending_label: 缓冲区中最后一个片段的标签

        Returns:
            True 如果应该继续合并（判定为同一人），False 如果应该提交（判定为换人）
        """
        # 获取缓冲区中最后一个片段的 embedding
        last_segment = self._pending_segments[-1] if self._pending_segments else None
        if not last_segment or last_segment.embedding is None:
            print(f"[管道-合并] 🔍 声纹相似度回退检查: 缓冲区无 embedding，无法比较，判定为换人")
            return False

        if segment.embedding is None:
            print(f"[管道-合并] 🔍 声纹相似度回退检查: 新片段无 embedding，无法比较，判定为换人")
            return False

        # 直接计算两个片段 embedding 的余弦相似度
        emb_a = segment.embedding
        emb_b = last_segment.embedding

        # 归一化
        norm_a = np.linalg.norm(emb_a)
        norm_b = np.linalg.norm(emb_b)
        if norm_a < 1e-6 or norm_b < 1e-6:
            print(f"[管道-合并] 🔍 声纹相似度回退检查: embedding 范数过小，无法比较，判定为换人")
            return False

        cos_sim = float(np.dot(emb_a, emb_b) / (norm_a * norm_b))
        print(f"[管道-合并] 🔍 声纹相似度回退检查: 片段 embedding 直接比较 "
              f"(speaker: {last_pending_label} vs {segment.speaker_label}), "
              f"余弦相似度={cos_sim:.4f}, 阈值={self._SPEAKER_EMB_SIM_THRESHOLD}")

        if cos_sim >= self._SPEAKER_EMB_SIM_THRESHOLD:
            print(f"[管道-合并] 🔍 判定为同一人（相似度 {cos_sim:.4f} >= {self._SPEAKER_EMB_SIM_THRESHOLD}），继续合并")
            return True
        else:
            print(f"[管道-合并] 🔍 判定为换人（相似度 {cos_sim:.4f} < {self._SPEAKER_EMB_SIM_THRESHOLD}）")
            return False

    def _merge_segments(self, segments: List[SpeechSegment], speaker_label: Optional[str] = None) -> SpeechSegment:
        """
        合并多个片段为一个片段。

        Args:
            segments: 待合并的片段列表（按时间顺序）
            speaker_label: 合并后片段的说话人标签

        Returns:
            合并后的 SpeechSegment
        """
        if not segments:
            raise ValueError("无法合并空片段列表")

        if len(segments) == 1:
            # 单个片段，直接返回
            seg = segments[0]
            seg.speaker_label = speaker_label
            return seg

        # 合并音频数据
        merged_audio = np.concatenate([s.audio_data for s in segments])

        # 计算时间范围
        start_ms = segments[0].start_ms
        end_ms = segments[-1].end_ms

        # 使用最后一个片段的 overlap_tail
        overlap_tail = segments[-1].overlap_tail

        # 合并分段原因
        reasons = set(s.segment_reason for s in segments)
        merged_reason = "/".join(sorted(reasons))

        # 说话人标签
        final_label = speaker_label or segments[-1].speaker_label or segments[-1].speaker_id

        # 说话人ID
        speaker_id = segments[-1].speaker_id

        # 保留最后一个片段的 track_id（用于日志关联）
        merged_segment = SpeechSegment(
            audio_data=merged_audio,
            start_ms=start_ms,
            end_ms=end_ms,
            segment_reason=merged_reason,
            overlap_tail=overlap_tail,
            speaker_id=speaker_id,
            speaker_label=final_label,
        )
        # 继承最后一个片段的追踪ID
        merged_segment._track_id = getattr(segments[-1], '_track_id', None)

        print(f"[管道-合并] 合并 {len(segments)} 个片段: "
              f"[{start_ms}-{end_ms}ms], 时长={(end_ms - start_ms)/1000:.2f}s, "
              f"标签={final_label}, 原因={merged_reason}")

        return merged_segment

    def _should_commit_segments(self, current_label: Optional[str]) -> Tuple[bool, List[SpeechSegment]]:
        """
        判断是否应该提交当前缓冲区的片段。

        提交条件（满足任一即可）：
        1. 连续 min_same_label 个片段的标签相同
        2. 等待时间超过 max_wait_ms
        3. 当前片段标签与缓冲区最后一个片段的标签不同

        Args:
            current_label: 当前新片段的说话人标签

        Returns:
            (should_commit, segments_to_commit): 是否提交，以及待提交的片段列表
        """
        if not self._pending_segments:
            return False, []

        # 条件1：等待时间超时 → 强制提交
        if self._pending_segments:
            first_seg = self._pending_segments[0]
            last_seg = self._pending_segments[-1]
            wait_duration_ms = last_seg.end_ms - first_seg.start_ms
            if wait_duration_ms >= self._merge_max_wait_ms:
                print(f"[管道-合并] ⏰ 等待超时 ({wait_duration_ms:.0f}ms >= {self._merge_max_wait_ms}ms)，强制提交")
                return True, list(self._pending_segments)

        # 条件2：当前标签与最后一个待处理片段标签不同 → 提交前一个
        last_pending_label = self._pending_segments[-1].speaker_label if self._pending_segments else None
        if current_label is not None and last_pending_label is not None and current_label != last_pending_label:
            # 标签发生变化，提交之前的片段
            print(f"[管道-合并] 🔄 标签变化: {last_pending_label} → {current_label}，提交之前的片段")
            return True, list(self._pending_segments)

        # 条件3：连续相同标签片段数量达标 → 提交
        if len(self._pending_segments) >= self._merge_min_same_label:
            # 检查是否所有待处理片段的标签都相同
            labels = [s.speaker_label for s in self._pending_segments if s.speaker_label is not None]
            if labels and all(l == labels[0] for l in labels):
                print(f"[管道-合并] ✅ 连续 {len(labels)} 个相同标签片段达标，提交")
                return True, list(self._pending_segments)

        return False, []

    def _add_segment_to_buffer(self, segment: SpeechSegment) -> Optional[List[SpeechSegment]]:
        """
        将片段添加到缓冲区，并根据合并策略决定是否提交。

        核心逻辑：等待下一个片段来确认当前片段的标签。
        - 如果下一个片段标签相同 → 继续等待
        - 如果下一个片段标签不同 → 确认前一段是谁，提交转录
        - uncertain 片段处理（严格策略）：
          1. 同一时间只允许一个 uncertain
          2. 如果缓冲区已有 uncertain，新片段不标记为 uncertain
          3. 如果新片段标签与 uncertain 的 top2 匹配，修正 uncertain 为 top2 并提交

        Args:
            segment: 新片段（已带有 speaker_label）

        Returns:
            如果有片段需要提交，返回待提交的片段列表；否则返回 None
        """
        with self._pending_lock:
            # 标记是否超时提交（用于统计）
            _is_timeout_submit = False

            # 获取缓冲区最后一个片段的标签
            last_pending_label = self._pending_segments[-1].speaker_label if self._pending_segments else None
            
            # 查找缓冲区中的 uncertain 片段
            uncertain_idx = None
            uncertain_seg = None
            for i, seg in enumerate(self._pending_segments):
                if seg.speaker_uncertain:
                    uncertain_idx = i
                    uncertain_seg = seg
                    break
            
            # 如果缓冲区中已有 uncertain，新片段强制不标记为 uncertain
            if uncertain_seg is not None and segment.speaker_uncertain:
                segment.speaker_uncertain = False
                segment.speaker_uncertain_reason = None
                print(f"[管道-合并] 🔒 缓冲区已有uncertain，新片段不标记uncertain，继续正常处理")

            # 如果缓冲区为空，直接加入并等待下一个片段确认
            if not self._pending_segments:
                self._pending_segments.append(segment)
                self._last_speaker_label = segment.speaker_label
                track_id = getattr(segment, '_track_id', 0)
                print(f"\n[📦合并][#{track_id:04d}] 🆕 缓冲区为空 → 等待确认")
                print(f"[📦合并][#{track_id:04d}]    新片段: #{track_id:04d}, speaker={segment.speaker_label}")
                return None

            # 如果有缓冲区，检查是否应该提交
            should_commit = False

            # 获取当前片段的追踪ID
            track_id = getattr(segment, '_track_id', 0)

            # 打印当前状态
            print(f"\n[📦合并][#{track_id:04d}] ═══ 合并决策 ═══")
            pending_ids = [f"#{getattr(s, '_track_id', '?'):04d}" for s in self._pending_segments]
            print(f"[📦合并][#{track_id:04d}] 缓冲区: {len(self._pending_segments)} 个 {pending_ids} | 新片段: speaker={segment.speaker_label}")

            # 检查是否可以用 uncertain 的 top2 来修正并提交
            if uncertain_seg is not None:
                # 获取 uncertain 片段的 top2（第二候选说话人）
                uncertain_top2_id = None
                uncertain_top2_score = None
                if uncertain_seg.speaker_sims:
                    sorted_sims = sorted(uncertain_seg.speaker_sims.items(), key=lambda x: x[1], reverse=True)
                    if len(sorted_sims) >= 2:
                        uncertain_top2_id = sorted_sims[1][0]
                        uncertain_top2_score = sorted_sims[1][1]

                # 如果新片段标签与 uncertain 的 top2 匹配，说明 uncertain 是被误识别的
                if uncertain_top2_id and segment.speaker_label == uncertain_top2_id:
                    uncertain_track_id = getattr(uncertain_seg, '_track_id', '?')
                    print(f"[📦合并][#{track_id:04d}] 🔧 发现 uncertain 片段 #[{uncertain_track_id}] 需要修正:")
                    print(f"       当前识别: {uncertain_seg.speaker_label}, top2 候选: {uncertain_top2_id}({uncertain_top2_score:.3f})")
                    print(f"       新片段识别: {segment.speaker_label} 与 top2 匹配！")
                    print(f"       → 修正: {uncertain_seg.speaker_label} → {uncertain_top2_id}")

                    # 修正 uncertain 片段的标签
                    uncertain_seg.speaker_label = uncertain_top2_id
                    uncertain_seg.speaker_id = uncertain_top2_id
                    uncertain_seg.speaker_uncertain = False
                    uncertain_seg.speaker_uncertain_reason = f"已修正为top2({uncertain_top2_id})"

                    # 提交所有片段（包括修正后的 uncertain 和当前片段）
                    segments_to_commit = list(self._pending_segments)
                    segments_to_commit.append(segment)

                    # 清空缓冲区
                    self._pending_segments.clear()

                    # 把当前片段加入缓冲区（开始新的等待周期）
                    self._pending_segments.append(segment)
                    self._last_speaker_label = segment.speaker_label
                    print(f"[📦合并][#{track_id:04d}] ✅ 修正后提交 {len(segments_to_commit)} 个片段")
                    print(f"[📦合并][#{track_id:04d}] ← 提交片段IDs: {[getattr(s, '_track_id', '?') for s in segments_to_commit]}")
                    print(f"{'='*70}\n")
                    return segments_to_commit

                # 如果新片段标签与 uncertain 不匹配，检查是否标签变化需要提交
                # 此时 uncertain 需要等待更长时间或超时后提交
                pass  # 继续下面的逻辑

            # 条件1：等待时间超时 → 强制提交（包含 uncertain）
            first_seg = self._pending_segments[0]
            last_seg = self._pending_segments[-1]
            wait_duration_ms = last_seg.end_ms - first_seg.start_ms
            if wait_duration_ms >= self._merge_max_wait_ms:
                _is_timeout_submit = True
                print(f"[📦合并][#{track_id:04d}] ⏰ 超时提交 ({wait_duration_ms:.0f}ms >= {self._merge_max_wait_ms}ms)")

                # 超时时，将 uncertain 修正为 top1（假设 top1 是正确的）
                if uncertain_seg is not None:
                    uncertain_top2_id = None
                    uncertain_top2_score = None
                    if uncertain_seg.speaker_sims:
                        sorted_sims = sorted(uncertain_seg.speaker_sims.items(), key=lambda x: x[1], reverse=True)
                        if len(sorted_sims) >= 2:
                            uncertain_top2_id = sorted_sims[1][0]
                            uncertain_top2_score = sorted_sims[1][1]

                    # 如果前后片段都与 top2 一致，修正为 top2；否则修正为 top1
                    prev_label = None
                    next_label = segment.speaker_label if segment.speaker_label else None

                    # 查找 uncertain 前后的标签
                    if uncertain_idx > 0:
                        prev_label = self._pending_segments[uncertain_idx - 1].speaker_label
                    if uncertain_idx < len(self._pending_segments) - 1:
                        next_label = self._pending_segments[uncertain_idx + 1].speaker_label

                    # 如果前后一致且与 top2 匹配，修正为 top2；否则修正为 top1
                    final_label = uncertain_seg.speaker_label  # 默认 top1
                    if uncertain_top2_id and prev_label == uncertain_top2_id and next_label == uncertain_top2_id:
                        final_label = uncertain_top2_id

                    if final_label != uncertain_seg.speaker_label:
                        uncertain_track_id = getattr(uncertain_seg, '_track_id', '?')
                        print(f"[📦合并][#{track_id:04d}]    超时修正 uncertain #[{uncertain_track_id}]: {uncertain_seg.speaker_label} → {final_label}")
                        uncertain_seg.speaker_label = final_label
                        uncertain_seg.speaker_id = final_label
                        uncertain_seg.speaker_uncertain = False

                print(f"[📦合并][#{track_id:04d}] → 强制提交 {len(self._pending_segments)} 个片段")
                should_commit = True

            # 条件2：新片段标签与缓冲区最后一个片段标签不同 → 检查是否声纹相似
            elif segment.speaker_label != last_pending_label:
                print(f"[📦合并][#{track_id:04d}] 🔄 标签变化检测: {last_pending_label} → {segment.speaker_label}")

                # 检查是否"同一人被误识为不同标签"的情况
                # 如果新片段的相似度候选中包含 last_pending_label 且相似度较高，说明是同一人
                should_continue_buffering = self._check_speaker_similarity_for_merge(
                    segment, last_pending_label
                )
                if should_continue_buffering:
                    print(f"[📦合并][#{track_id:04d}]    ← 声纹相似度回退检查通过，继续合并（不提交）")
                    # 继续缓冲，不提交
                    self._pending_segments.append(segment)
                    self._last_speaker_label = segment.speaker_label
                    print(f"[📦合并][#{track_id:04d}]    → 继续等待")
                    return None
                else:
                    print(f"[📦合并][#{track_id:04d}]    ← 声纹相似度回退检查失败，确认换人")
                    should_commit = True

            # 不再限制合并数量，只要标签相同就一直合并，直到换人或超时
            # 只有以下情况才提交：
            # 1. 超时（条件1）
            # 2. 声纹相似度检查失败，确认换人（条件2）

            if should_commit:
                # 保存待提交的片段
                segments_to_commit = list(self._pending_segments)
                committed_ids = [f"#{getattr(s, '_track_id', '?'):04d}" for s in segments_to_commit]

                # 统计提交原因
                if _is_timeout_submit:
                    self._segment_stats["timeout_submit"] += 1
                else:
                    self._segment_stats["merged_submit"] += 1
                self._segment_stats["total_merged"] += 1

                # 清空缓冲区
                self._pending_segments.clear()

                # 把当前片段加入缓冲区（开始新的等待周期）
                self._pending_segments.append(segment)
                self._last_speaker_label = segment.speaker_label
                final_label = segments_to_commit[0].speaker_label if segments_to_commit else 'unknown'
                print(f"[📦合并][#{track_id:04d}] ✅ 提交: {committed_ids} → speaker={final_label}")
                print(f"{'='*70}\n")

                # 返回待提交的片段
                return segments_to_commit
            else:
                # 标签相同且未达标，继续等待
                self._pending_segments.append(segment)
                self._last_speaker_label = segment.speaker_label
                print(f"[📦合并][#{track_id:04d}] 🔄 继续等待 (缓冲区: {len(self._pending_segments)} 个)")
                return None

    def _flush_pending_segments(self) -> List[SpeechSegment]:
        """
        强制提交所有待处理的片段（通常在管道停止时调用）。

        Returns:
            所有待提交的片段列表
        """
        with self._pending_lock:
            if not self._pending_segments:
                return []
            segments = list(self._pending_segments)
            self._pending_segments.clear()
            # 统计管道结束时剩余片段的提交
            self._segment_stats["timeout_submit"] += 1
            self._segment_stats["total_merged"] += 1
            print(f"[管道-合并] 🔚 管道结束时提交 {len(segments)} 个待处理片段")
            return segments

    def list_registered_speakers(self) -> List[str]:
        """列出已注册的说话人 ID"""
        return list(self._registered_speakers.keys())
    
    async def start(self):
        """启动管道（启动后台处理任务）"""
        if self._process_task is None or self._process_task.done():
            self._loop = asyncio.get_event_loop()
            self._process_task = asyncio.create_task(self._process_loop())
            print("[管道] 流式管道已启动")

    def _apply_punctuation_sync(self, delta: TranscriptDelta) -> TranscriptDelta:
        """
        同步调用标点恢复模型（在 _process_loop 的线程池中执行，不阻塞 ASR 锁）。
        标点模型计算极快（纯 CPU 推理），直接在线程池执行即可。
        """
        if not self.punc_model or not delta.text or not delta.text.strip():
            return delta

        try:
            result = self.punc_model.generate(input=delta.text)
            if result and len(result) > 0:
                punc_text = result[0].get("text", delta.text) if isinstance(result[0], dict) else str(result[0])
                if punc_text and punc_text != delta.text:
                    print(f"[ASR] 标点后处理: '{delta.text}' → '{punc_text}'")
                    delta.text = punc_text
        except Exception as e:
            print(f"[ASR] 标点后处理失败（使用原文）: {e}")

        return delta

    def _init_corrector(self):
        """初始化 MacBERT 纠错器"""
        if not self.use_correction:
            return

        if self._corrector_initialized:
            return

        try:
            from app.text_corrector import get_corrector
            self._corrector = get_corrector()
            self._corrector_initialized = True
            print("[MacBERT纠错] 纠错器已初始化")
        except Exception as e:
            print(f"[MacBERT纠错] 纠错器初始化失败: {e}")
            self._corrector_initialized = True  # 只初始化一次，避免重复报错
            self._corrector = None

    def _apply_macbert_correction(self, delta: TranscriptDelta) -> TranscriptDelta:
        """
        应用 MacBERT 文本纠错。

        Args:
            delta: 转录结果

        Returns:
            添加纠错字段的 delta
        """
        if not self.use_correction or not delta.text or not delta.text.strip():
            return delta

        # 延迟初始化
        if not self._corrector_initialized:
            self._init_corrector()

        if self._corrector is None:
            return delta

        try:
            original_text = delta.text
            result = self._corrector.correct(original_text)

            if result.get("corrected", False):
                delta.corrected_text = result.get("target", original_text)
                delta.was_corrected = True
                delta.correction_errors = result.get("errors", [])

                # 日志输出纠错前后对比
                errors = result.get("errors", [])
                if errors:
                    error_str = ", ".join([f"'{e[0]}'→'{e[1]}'" for e in errors[:3]])
                    print(f"[MacBERT纠错] '{original_text[:40]}...' → '{delta.corrected_text[:40]}...' | 纠错: {error_str}")
                else:
                    print(f"[MacBERT纠错] '{original_text[:40]}...' → '{delta.corrected_text[:40]}...'")
        except Exception as e:
            print(f"[MacBERT纠错] 纠错失败: {e}")

        return delta
    
    async def _process_loop(self) -> None:
        """后台处理循环：处理转录结果和声纹识别"""
        while True:
            try:
                # 使用 run_in_executor 让 queue.get() 不阻塞事件循环
                loop = asyncio.get_event_loop()
                item = await loop.run_in_executor(None, self._transcript_queue.get)

                if item is None:
                    break

                item_type, data = item

                if item_type == "delta":
                    delta = data
                    if delta.text.strip():
                        # 标点后处理在队列处理线程中异步执行，不阻塞 ASR 锁
                        delta = await loop.run_in_executor(
                            None, self._apply_punctuation_sync, delta
                        )

                        # MacBERT 文本纠错
                        delta = await loop.run_in_executor(
                            None, self._apply_macbert_correction, delta
                        )

                        # 获取本次提交对应的原始片段IDs
                        committed_ids = getattr(delta, '_committed_ids', [])
                        committed_labels = getattr(delta, '_committed_labels', [])
                        final_label = getattr(delta, 'speaker_id', 'unknown')
                        text_preview = delta.text[:30] + "..." if len(delta.text) > 30 else delta.text

                        # 如果有纠错，显示纠错前后对比
                        if delta.was_corrected and delta.corrected_text:
                            corrected_preview = delta.corrected_text[:30] + "..." if len(delta.corrected_text) > 30 else delta.corrected_text
                            print(f"[📤WS] ← ASR结果 (片段{committed_ids}, speaker={final_label})")
                            print(f"       纠前: '{text_preview}'")
                            print(f"       纠后: '{corrected_preview}'")
                        else:
                            print(f"[📤WS] ← ASR结果 (片段{committed_ids}, speaker={final_label}): '{text_preview}'")

                        if self.on_transcript:
                            result = self.on_transcript(delta)
                            if asyncio.iscoroutine(result):
                                await result

                elif item_type == "speaker_result":
                    # data 是 (speaker_id, confidence, interviewer_sim, candidate_sim)
                    if isinstance(data, tuple) and len(data) == 4:
                        speaker_id, confidence, interviewer_sim, candidate_sim = data
                    elif isinstance(data, tuple) and len(data) == 2:
                        speaker_id, confidence = data
                        interviewer_sim = candidate_sim = 0.0
                    else:
                        print(f"[管道] ⚠️ speaker_result 数据格式异常: {type(data)}, 跳过")
                        continue
                    if self.on_speaker:
                        result = self.on_speaker(speaker_id, confidence)
                        if asyncio.iscoroutine(result):
                            await result

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[管道] 处理循环错误: {e}")
                import traceback
                traceback.print_exc()
    
    async def feed_audio(self, audio_data: np.ndarray):
        """
        异步接收音频数据

        Args:
            audio_data: float32, 16kHz
        """
        # 获取事件循环
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.get_event_loop()

        # 启动后台任务
        if self._process_task is None:
            self._process_task = asyncio.create_task(self._process_loop())

        # 启动后台 embedding 提取线程
        if self._embedding_extractor is not None and not self._embedding_thread_running:
            self._embedding_thread_running = True
            self._embedding_thread = threading.Thread(target=self._embedding_extraction_loop, daemon=True)
            self._embedding_thread.start()

        # 同步路径：VAD 检测（VAD 内部会同步累积语音帧用于 embedding）
        try:
            segment = self.vad.feed(audio_data)
        except Exception as e:
            print(f"[管道] VAD 检测异常: {e}")
            import traceback
            traceback.print_exc()
            return

        if segment:
            # 统计分段原因
            self._segment_stats["total_segments"] += 1
            if segment.segment_reason == "silence_timeout":
                self._segment_stats["silence_timeout"] += 1
            elif segment.segment_reason == "voice_change":
                self._segment_stats["voice_change"] += 1

            duration_s = len(segment.audio_data) / 16000.0
            print(f"[管道] 检测到语音片段，样本数={len(segment.audio_data)}, 时长={duration_s:.2f}s, 分段原因={segment.segment_reason}")

            # 过滤过短片段：小于 0.5 秒的片段不送 ASR，直接跳过
            # 这些通常是填充词（如"嗯"、"啊"）或噪声
            MIN_SEGMENT_DURATION_S = 0.5
            if duration_s < MIN_SEGMENT_DURATION_S:
                print(f"[管道] ⏭️ 跳过过短片段 ({duration_s:.2f}s < {MIN_SEGMENT_DURATION_S}s)")
                return

            if self.on_speech_segment:
                result = self.on_speech_segment(segment)
                if asyncio.iscoroutine(result):
                    await result

            # ===== 说话人标签合并逻辑 =====
            # 新流程：先识别说话人标签 → 决定是否合并 → 再送 ASR
            if self._merge_enabled:
                # 1. 声纹识别：获取说话人标签 + 相似度候选
                speaker_label, speaker_sims = self._recognize_speaker_label(segment)
                segment.speaker_label = speaker_label
                segment.speaker_id = speaker_label  # 统一使用 speaker_label 作为标识
                segment.speaker_sims = speaker_sims  # 保存相似度候选用于合并决策

                track_id = getattr(segment, '_track_id', 0)

                # 2. 检查缓冲区：是否需要提交已缓冲的片段
                segments_to_commit = self._add_segment_to_buffer(segment)

                if segments_to_commit:
                    # 有片段需要提交，合并后送 ASR
                    committed_ids = [f"#{getattr(s, '_track_id', '?'):04d}" for s in segments_to_commit]
                    committed_labels = [s.speaker_label for s in segments_to_commit]
                    final_label = committed_labels[0] if committed_labels else 'unknown'

                    # 使用缓冲区内片段的共同标签
                    confirmed_label = final_label
                    merged_segment = self._merge_segments(segments_to_commit, confirmed_label)
                    # 从缓冲区移除已提交的片段
                    with self._pending_lock:
                        # 保留当前片段（它已经在缓冲区里了，但我们要确保不重复）
                        pass

                    # 记录本次提交对应的原始片段IDs（用于WS发送时对应Match日志）
                    self._pending_lock.acquire()
                    try:
                        # 临时存储，等待ASR完成后使用
                        merged_segment._committed_ids = committed_ids
                        merged_segment._committed_labels = committed_labels
                    finally:
                        self._pending_lock.release()

                    track_id_merged = getattr(merged_segment, '_track_id', 0)
                    print(f"[📤WS] → 提交片段{committed_ids}，speaker={final_label}")
                    asyncio.create_task(
                        self._run_streaming_asr_locked(
                            merged_segment.audio_data,
                            merged_segment.segment_reason,
                            merged_segment.overlap_tail,
                            merged_segment.start_ms,
                            merged_segment.end_ms,
                            merged_segment.speaker_label,
                            merged_segment,  # 传递追踪ID
                        )
                    )
                else:
                    # 片段已加入缓冲区，等待下一个片段确认
                    print(f"\n[⏳缓冲][#{track_id:04d}] 片段等待确认: speaker={segment.speaker_label}, 缓冲区还有 {len(self._pending_segments)} 个")
            else:
                # 合并未启用，直接提交 ASR 任务
                track_id = getattr(segment, '_track_id', 0)
                print(f"[📤WS][#{track_id:04d}] 提交非合并 ASR 任务 (start_ms={segment.start_ms}, speaker={segment.speaker_label})")
                asyncio.create_task(
                    self._run_streaming_asr_locked(
                        segment.audio_data,
                        segment.segment_reason,
                        segment.overlap_tail,
                        segment.start_ms,
                        segment.end_ms,
                        segment.speaker_label,
                        segment,  # 传递追踪ID
                    )
                )
                print(f"[📤WS][#{track_id:04d}] ASR 任务已提交（非阻塞）")

    def _recognize_speaker_label(self, segment: SpeechSegment) -> Tuple[Optional[str], Dict[str, float]]:
        """
        识别片段的说话人标签。

        Args:
            segment: 语音片段

        Returns:
            (speaker_label, speaker_sims): 说话人标签字符串，以及所有候选相似度 {speaker_id: similarity}
            如果无法识别则返回 (None, {})

        Note:
            会同时设置 segment.speaker_uncertain 和 segment.speaker_uncertain_reason
            当 top1/top2 分数差距过小时，标记为 uncertain
        """
        audio_len = len(segment.audio_data) if segment.audio_data is not None else 0
        if audio_len == 0:
            return None, {}

        # 生成片段追踪ID（关联整个处理流程）
        with self._track_lock:
            self._track_counter += 1
            track_id = self._track_counter
        segment._track_id = track_id
        audio_ms = audio_len / 16.0  # 16kHz

        print(f"\n[🎯#{track_id:04d}] 音频{audio_ms:.0f}ms ═══")

        try:
            if self._use_enhanced_engine and self._enhanced_registry:
                # 使用增强版声纹引擎
                result = self._enhanced_registry.identify(segment.audio_data, track_id=track_id)
                if result and result.matches:
                    top = result.matches[0]
                    # 提取所有候选相似度
                    speaker_sims = {}
                    for m in result.matches:
                        speaker_sims[m.speaker_id] = m.cosine_score
                    segment.speaker_sims = speaker_sims
                    # 保存 embedding 用于后续比较
                    if hasattr(self._enhanced_registry, 'extractor') and self._enhanced_registry.extractor:
                        try:
                            emb = self._enhanced_registry.extractor.extract(segment.audio_data)
                            if emb is not None and np.linalg.norm(emb) > 1e-6:
                                segment.embedding = emb
                        except Exception:
                            pass

                    # 检查置信度差距
                    self._check_speaker_uncertainty(segment, speaker_sims)

                    print(f"[🎯#{track_id:04d}] 识别结果: speaker={top.speaker_id}, cos={top.cosine_score:.4f}")
                    return top.speaker_id, speaker_sims
                print(f"[🎯#{track_id:04d}] 无匹配结果")
                return None, {}
            elif self._registered_speakers and self.speaker:
                # 使用普通声纹识别
                result = self.speaker.extract_and_compare(
                    segment.audio_data,
                    self._registered_speakers,
                    threshold=SPEAKER_SIMILARITY_THRESHOLD
                )
                if result:
                    speaker_id, score, all_sims = result
                    if speaker_id != "__unknown__":
                        segment.speaker_sims = all_sims
                        # 保存 embedding
                        if self.speaker and hasattr(self.speaker, 'extractor') and self.speaker.extractor:
                            try:
                                emb = self.speaker.extractor.extract(segment.audio_data)
                                if emb is not None and np.linalg.norm(emb) > 1e-6:
                                    segment.embedding = emb
                            except Exception:
                                pass

                        # 检查置信度差距
                        self._check_speaker_uncertainty(segment, all_sims)

                        print(f"[🎯#{track_id:04d}] 识别结果: speaker={speaker_id}, score={score:.3f}")
                        return speaker_id, all_sims
                print(f"[🎯#{track_id:04d}] 无匹配结果")
                return None, {}
            else:
                # 无声纹注册，使用默认标签
                self._speaker_counter += 1
                default_label = f"speaker_{self._speaker_counter}"
                print(f"[🎯#{track_id:04d}] 无已注册说话人，使用: {default_label}")
                return default_label, {}
        except Exception as e:
            print(f"[🎯#{track_id:04d}] 识别异常: {e}")
            import traceback
            traceback.print_exc()
            return None, {}

    def _check_speaker_uncertainty(self, segment: SpeechSegment, speaker_sims: Dict[str, float]) -> None:
        """
        检查声纹识别的置信度是否不足（保守策略）。
        
        只有当以下条件同时满足时才标记为 uncertain：
        1. top1 和 top2 分数差距非常小（gap < 0.03）
        2. 音频时长较短（< SPEAKER_SHORT_AUDIO_THRESHOLD_MS）
        
        这样可以避免 uncertain 成为拖油瓶，只有真正难以区分的情况才触发。
        
        Args:
            segment: 语音片段
            speaker_sims: 所有候选相似度 {speaker_id: similarity}
        """
        if not speaker_sims or len(speaker_sims) < 2:
            return
        
        # 按分数排序
        sorted_speakers = sorted(speaker_sims.items(), key=lambda x: x[1], reverse=True)
        top1_id, top1_score = sorted_speakers[0]
        top2_id, top2_score = sorted_speakers[1]
        
        # 如果只有一个已注册说话人，无法比较
        if len(sorted_speakers) < 2:
            return
        
        gap = top1_score - top2_score
        
        # 计算音频时长
        audio_len = len(segment.audio_data) if segment.audio_data is not None else 0
        audio_duration_ms = audio_len / 16.0  # 16kHz 采样率
        
        # 只有同时满足以下条件才标记为 uncertain：
        # 1. gap < 0.03（top1 与 top2 非常接近）
        # 2. 音频时长较短（< 800ms）
        if gap < SPEAKER_STRICT_GAP_THRESHOLD and audio_duration_ms < SPEAKER_SHORT_AUDIO_THRESHOLD_MS:
            segment.speaker_uncertain = True
            segment.speaker_uncertain_reason = (
                f"top1({top1_id}:{top1_score:.3f}) vs top2({top2_id}:{top2_score:.3f}) "
                f"gap={gap:.3f} < {SPEAKER_STRICT_GAP_THRESHOLD}, duration={audio_duration_ms:.0f}ms < {SPEAKER_SHORT_AUDIO_THRESHOLD_MS}ms"
            )
            print(f"[管道-声纹] ⚠️ 置信度不足(严格): {segment.speaker_uncertain_reason}")
        else:
            segment.speaker_uncertain = False
            segment.speaker_uncertain_reason = None
            if gap < 0.1:
                print(f"[管道-声纹] ✅ 置信度充足: top1({top1_id}:{top1_score:.3f}) vs top2({top2_id}:{top2_score:.3f}) gap={gap:.3f}")
            # gap 较大时不需要打印

    def _embedding_extraction_loop(self) -> None:
        """后台线程：定期从待处理音频中提取 embedding"""
        import time
        interval_s = CHANGE_DETECTOR_CONFIG.embedding_interval_ms / 1000.0
        while self._embedding_thread_running:
            try:
                self.vad.extract_pending_embeddings()
                time.sleep(interval_s)
            except Exception as e:
                print(f"[管道] 后台 embedding 提取异常: {e}")
    
    async def _run_streaming_asr_locked(self, audio_data: np.ndarray, segment_reason: str = None, overlap_tail: np.ndarray = None, segment_start_ms: int = 0, segment_end_ms: int = 0, speaker_label: str = None, merged_segment=None):
        """带锁的 ASR 执行

        speaker_label: 如果已通过合并逻辑确认说话人标签，则传入以跳过内部重识别。
        merged_segment: 合并后的片段对象（用于传递追踪ID）
        """
        loop = asyncio.get_event_loop()
        speaker_result_holder = {}

        # ---------- Prepend 尾音上下文 ----------
        if overlap_tail is not None and len(overlap_tail) > 0:
            prepend_samples = len(overlap_tail)
            prepend_ms = int(prepend_samples / self.vad.sample_rate * 1000)
            audio_data_original_samples = len(audio_data)
            audio_data_original_ms = int(audio_data_original_samples / self.vad.sample_rate * 1000)
            audio_data = np.concatenate([overlap_tail, audio_data])
            # prepend 前的原始 segment 时间范围
            orig_start_ms = segment_start_ms
            orig_end_ms = segment_end_ms
            # prepend 后实际送 ASR 的时间范围（往前延伸了 prepend_ms）
            actual_start_ms = segment_start_ms - prepend_ms
            actual_end_ms = segment_end_ms
            print(f"[ASR-DBG] ================================================")
            print(f"[ASR-DBG] ASR 接收详情:")
            print(f"[ASR-DBG]   分段原因: {segment_reason}")
            print(f"[ASR-DBG]   prepend overlap tail: {prepend_samples}样本 = {prepend_ms}ms")
            print(f"[ASR-DBG]   原始 segment:  [{orig_start_ms}-{orig_end_ms}ms], {audio_data_original_samples}样本, {audio_data_original_ms}ms")
            print(f"[ASR-DBG]   prepend 后实际:  [{actual_start_ms}-{actual_end_ms}ms], {len(audio_data)}样本, {len(audio_data)/self.vad.sample_rate*1000:.0f}ms")
            print(f"[ASR-DBG]   prepend 向前延伸了: {prepend_ms}ms (来自上一段的末尾)")
            print(f"[ASR-DBG]   音频能量: min={float(audio_data.min()):.4f}, max={float(audio_data.max()):.4f}, mean={float(audio_data.mean()):.4f}")
            print(f"[ASR-DBG] ================================================")
        else:
            print(f"[ASR-DBG] ASR 接收: [{segment_start_ms}-{segment_end_ms}ms], "
                  f"{len(audio_data)}样本, {len(audio_data)/self.vad.sample_rate*1000:.0f}ms, "
                  f"reason={segment_reason}")

        def _do_speaker_recognition() -> None:
            """在 ASR 线程内同步执行声纹识别，确保 ASR 开始时结果已就绪"""
            if not self._registered_speakers and not self._use_enhanced_engine:
                return
            # 获取片段追踪ID用于日志关联
            track_id = getattr(merged_segment, '_track_id', None)
            try:
                if self._use_enhanced_engine and self._enhanced_registry:
                    # 多窗口投票融合识别
                    if self._multi_window_enabled:
                        result, stats = self._enhanced_registry.identify_with_voting(
                            audio_data,
                            n_windows=self._multi_window_n,
                            window_step_ratio=self._multi_window_step,
                            vote_method=self._multi_window_vote,
                            track_id=track_id,
                        )
                        if result and result.matches:
                            top = result.matches[0]
                            all_sims = {m.speaker_id: m.final_score for m in result.matches}
                            speaker_result_holder["data"] = ("enhanced_vote", ({
                                "matches": [
                                    (m.speaker_id, m.name or m.speaker_id, m.final_score)
                                    for m in result.matches
                                ],
                                "all_sims": all_sims,
                                "uncertain": result.uncertain,
                                "uncertain_reason": result.uncertainty_reason or "",
                                "stats": stats,
                            }, all_sims))
                        else:
                            speaker_result_holder["data"] = ("enhanced_vote", ([], {}))
                    # 单窗口级联匹配（默认）
                    else:
                        result = self._enhanced_registry.identify(audio_data, track_id=track_id)
                        if result and result.matches:
                            top = result.matches[0]
                            all_sims = {m.speaker_id: m.final_score for m in result.matches}
                            speaker_result_holder["data"] = ("enhanced", ([
                                (m.speaker_id, m.name or m.speaker_id, m.final_score)
                                for m in result.matches
                            ], all_sims))
                        else:
                            speaker_result_holder["data"] = ("enhanced", ([], {}))
                else:
                    # 多窗口投票 + StreamingSpeakerRecognition（未接入 MultiSpeakerRegistry）
                    if self._multi_window_enabled and self.speaker is not None:
                        window_results = self.speaker.extract_multi_window(
                            audio_data,
                            n_windows=self._multi_window_n,
                            window_step_ratio=self._multi_window_step,
                        )
                        valid = [(emb, ts, ok) for emb, ts, ok in window_results if ok]
                        if valid:
                            embeddings = [emb for emb, _, _ in valid]
                            timestamps = [ts for _, ts, _ in valid]
                            # 向量融合
                            fused_emb, fuse_stats = self.speaker.extractor.extract_fused(
                                audio_data, self._multi_window_n,
                                self._multi_window_step, fusion_method="mean"
                            )
                            result = self.speaker.extract_and_compare(
                                fused_emb, self._registered_speakers
                            )
                            if result:
                                sid, confidence, all_sims = result
                                speaker_result_holder["data"] = ("legacy_vote", (
                                    sid, confidence, all_sims,
                                    {"n_valid": len(valid), "timestamps": timestamps, "stats": fuse_stats}
                                ))
                        else:
                            speaker_result_holder["data"] = ("legacy_vote", (None, 0.0, {}, {}))
                    else:
                        result = self.speaker.extract_and_compare(
                            audio_data, self._registered_speakers
                        )
                        if result:
                            sid, confidence, all_sims = result
                            speaker_result_holder["data"] = ("legacy", (sid, confidence, all_sims))
            except Exception as e:
                print(f"[管道] 声纹识别异常: {e}")
                import traceback
                traceback.print_exc()

        def on_delta(delta: TranscriptDelta):
            # 传递追踪ID和提交片段IDs（来自合并后的segment）
            track_id = getattr(merged_segment, '_track_id', 0) if merged_segment else 0
            delta._track_id = track_id
            delta._committed_ids = getattr(merged_segment, '_committed_ids', []) if merged_segment else []
            delta._committed_labels = getattr(merged_segment, '_committed_labels', []) if merged_segment else []

            # 如果已有确认的说话人标签，直接使用，跳过重识别
            if speaker_label:
                delta.speaker_id = speaker_label
                delta.speaker_confidence = 1.0
                # 设置 speaker_candidates 以便 consume_local_transcript_event 识别为 Mode2
                delta.speaker_candidates = [(speaker_label, None, 1.0)]
            else:
                speaker_info = speaker_result_holder.get("data")
                if speaker_info:
                    info_type, info_data = speaker_info
                    if info_type in ("enhanced", "enhanced_vote"):
                        # enhanced_vote: info_data = ({matches, all_sims, uncertain, stats}, all_sims)
                        # enhanced:      info_data = ([(sid, name, score), ...], all_sims)
                        if info_type == "enhanced_vote" and isinstance(info_data, tuple):
                            vote_data, all_sims = info_data
                            if isinstance(vote_data, dict):
                                top_candidates = vote_data.get("matches", [])
                                delta.uncertain_speaker = vote_data.get("uncertain", False)
                                delta.speaker_uncertain_reason = vote_data.get("uncertain_reason", "")
                                delta.speaker_multi_window_stats = vote_data.get("stats", {})
                            else:
                                top_candidates = []
                                all_sims = {}
                        else:
                            top_candidates, all_sims = info_data
                        if top_candidates:
                            top_sid, top_name, top_score = top_candidates[0]
                            delta.speaker_id = top_sid
                            delta.speaker_name = top_name if top_name != top_sid else None
                            delta.speaker_confidence = top_score
                            delta.speaker_candidates = top_candidates
                            delta.registered_speaker_sims = all_sims
                        else:
                            delta.speaker_id = "unknown"
                            delta.speaker_confidence = 0.0
                            delta.registered_speaker_sims = all_sims
                    else:
                        if info_type == "legacy_vote":
                            sid, confidence, all_sims, vote_stats = info_data
                        else:
                            sid, confidence, all_sims = info_data
                            vote_stats = {}
                        # "__unknown__" 表示零向量 embedding（CAM++ 对无效音频输出 NaN），不分配说话人 ID
                        if sid == "__unknown__" or sid is None:
                            delta.speaker_id = "unknown"
                            delta.speaker_confidence = 0.0
                            delta.registered_speaker_sims = {}
                        else:
                            delta.speaker_id = sid
                            delta.speaker_confidence = confidence
                            delta.registered_speaker_sims = all_sims
                            if "interviewer" in all_sims and "candidate" in all_sims:
                                delta.recognized_role = (
                                    "candidate" if all_sims.get("candidate", 0) > all_sims.get("interviewer", 0)
                                    else "interviewer"
                                )
                            if vote_stats:
                                delta.speaker_multi_window_stats = vote_stats
                else:
                    # 既没有传入 speaker_label，也没有声纹识别结果，设置为 unknown
                    delta.speaker_id = "unknown"
                    delta.speaker_confidence = 0.0
            if segment_reason:
                delta.segment_reason = segment_reason
            try:
                self._transcript_queue.put_nowait(("delta", delta))
            except Exception as e:
                print(f"[ASR-Thread] 放入队列失败: {e}")

        def _run():
            # 如果已有确认的说话人标签，跳过重识别
            if not speaker_label:
                _do_speaker_recognition()
            self.asr.recognize(audio_data, on_delta, self.language)

        async with self._asr_lock:
            await self._loop.run_in_executor(None, _run)

    async def stop(self) -> None:
        """停止管道"""
        # 先提交所有待处理的片段
        if self._merge_enabled:
            pending_segments = self._flush_pending_segments()
            if pending_segments:
                # 合并并送 ASR
                confirmed_label = pending_segments[0].speaker_label if pending_segments else None
                merged_segment = self._merge_segments(pending_segments, confirmed_label)
                track_id = getattr(merged_segment, '_track_id', 0)
                print(f"[📤WS][#{track_id:04d}] 停止前提交最后一批合并片段 [{merged_segment.start_ms}-{merged_segment.end_ms}ms]")
                asyncio.create_task(
                    self._run_streaming_asr_locked(
                        merged_segment.audio_data,
                        merged_segment.segment_reason,
                        merged_segment.overlap_tail,
                        merged_segment.start_ms,
                        merged_segment.end_ms,
                        merged_segment.speaker_label,
                        merged_segment,  # 传递追踪ID
                    )
                )

        if self._process_task:
            self._transcript_queue.put_nowait(None)  # 发送停止信号（queue.Queue 不是 asyncio.Queue，不能 await put）
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None
            print("[管道] 流式管道已停止")
            # 打印分割统计汇总
            self.print_segment_stats()

    def get_segment_stats(self) -> dict:
        """获取分割统计结果"""
        return self._segment_stats.copy()

    def print_segment_stats(self) -> None:
        """打印分割统计汇总"""
        stats = self._segment_stats
        total = stats["total_segments"]
        silence = stats["silence_timeout"]
        voice = stats["voice_change"]
        merged = stats["merged_submit"]
        timeout = stats["timeout_submit"]
        total_merged = stats["total_merged"]

        print("\n" + "=" * 60)
        print("【分割统计汇总】")
        print("-" * 60)
        print(f"  总VAD片段数:        {total}")
        print(f"  静音超时分割:       {silence} ({silence/total*100:.1f}% of total)" if total else "  静音超时分割:       0")
        print(f"  声纹突变分割:       {voice} ({voice/total*100:.1f}% of total)" if total else "  声纹突变分割:       0")
        print("-" * 60)
        print(f"  合并提交数:         {merged}")
        print(f"  超时强制提交数:     {timeout}")
        print(f"  总合并提交数:       {total_merged}")
        print("=" * 60 + "\n")

    def reset(self):
        """重置管道状态"""
        self.vad.reset()


# ============== 便捷创建函数 ==============

def create_streaming_pipeline(
    model_manager,
    language: str = "zh",
    use_correction: bool = None
) -> StreamingPipeline:
    """
    从 ModelManager 创建流式管道

    Args:
        model_manager: 模型管理器
        language: 语言
        use_correction: 是否启用 MacBERT 纠错（默认从配置读取）
    """
    from app import config

    if use_correction is None:
        use_correction = getattr(config, 'ENABLE_MACBERT_CORRECTION', True)

    return StreamingPipeline(
        vad_model=model_manager.get_vad_model(),
        asr_model=model_manager.get_asr_model(),
        punc_model=model_manager.get_punc_model(),
        camp_model=model_manager.get_camp_model(),
        language=language,
        device=model_manager.device,
        use_correction=use_correction
    )
