"""
流式 VAD + ASR + 声纹识别管道
支持实时流式转录和异步推送，避免音频积压
"""

import asyncio
import queue
import threading
from typing import Optional, Callable, Dict, Tuple
from dataclasses import dataclass
import numpy as np
import torch

# ============== 配置 ==============
VAD_SAMPLE_RATE = 16000
VAD_WINDOW_SIZE = 512  # samples（Silero VAD 要求）
VAD_THRESHOLD = 0.6  # VAD 检测阈值，0.6 更严格，减少杂音误判

# 语音片段检测参数
MIN_SPEECH_DURATION_MS = 1000  # 最小语音持续时间（毫秒），2秒可有效过滤杂音
MIN_SILENCE_DURATION_MS = 400# 静音超过此时间认为语音结束
MIN_SPEECH_ENERGY_THRESHOLD = 0.005  # 最小能量阈值，过滤低能量噪音

# 声纹识别参数
SPEAKER_SIMILARITY_THRESHOLD = 0.5  # 声纹匹配相似度阈值

# 语音特征变化检测参数
VOICE_CHANGE_THRESHOLD = 0.2  # 说话人变化检测阈值（0-1）
VOICE_CHANGE_WINDOW_MS = 1000  # 用于比较的窗口大小（毫秒）


# ============== 数据结构 ==============

@dataclass
class TranscriptDelta:
    """流式转录增量结果"""
    text: str              # 转录文本
    is_final: bool         # 是否是最终结果
    start_ms: int         # 开始时间
    end_ms: int           # 结束时间
    speaker_id: Optional[str] = None  # 说话人ID
    speaker_confidence: float = 0.0   # 说话人置信度
    segment_reason: Optional[str] = None  # 分段原因：silence_timeout / voice_change（用于声纹未注册时区分说话人切换）
    interviewer_sim: float = 0.0  # 与面试官声纹的相似度 [0, 1]
    candidate_sim: float = 0.0    # 与候选人声纹的相似度 [0, 1]
    recognized_role: Optional[str] = None  # 推断的角色：interviewer / candidate（基于相似度）


@dataclass
class SpeechSegment:
    """语音片段"""
    audio_data: np.ndarray   # float32, 16kHz
    start_ms: int            # 开始时间
    end_ms: int             # 结束时间
    segment_reason: str = "unknown"  # 分段原因：silence_timeout / voice_change


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
        
        # 说话人变化检测
        self._voice_change_window = int(VOICE_CHANGE_WINDOW_MS * sample_rate / 1000)
        self._recent_features: list = []  # 最近几帧的声纹特征
        self._feature_history_size = 5  # 保留最近5帧的特征用于比较
    
    def reset(self):
        """重置状态"""
        self.state = "idle"  # idle, speech
        self.speech_buffer = []
        self.speech_start_sample = 0
        self.silence_samples = 0
        self._buffer = np.array([], dtype=np.float32)
        self._total_samples_processed = 0
        self._recent_features = []  # 重置特征历史
    
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
    
    def _extract_voice_features(self, chunk: np.ndarray) -> np.ndarray:
        """
        提取简化的语音特征用于说话人变化检测
        使用短时能量和频谱质心作为特征
        """
        # 短时能量
        energy = np.mean(chunk ** 2)
        
        # 频谱质心（简化版）
        fft = np.abs(np.fft.rfft(chunk))
        freqs = np.arange(len(fft)) * self.sample_rate / len(chunk) / 2
        if np.sum(fft) > 0:
            spectral_centroid = np.sum(freqs * fft) / np.sum(fft)
        else:
            spectral_centroid = 0
        
        # 基频估计（简化）
        autocorr = np.correlate(chunk, chunk, mode='full')
        autocorr = autocorr[len(autocorr)//2:]
        peaks = []
        min_lag = int(0.002 * self.sample_rate)  # 最小周期 2ms
        max_lag = int(0.02 * self.sample_rate)   # 最大周期 20ms
        for i in range(min_lag + 1, min(max_lag, len(autocorr))):
            if autocorr[i] > autocorr[i-1] and autocorr[i] > autocorr[i+1]:
                peaks.append(i)
        pitch = peaks[0] / self.sample_rate if peaks else 0
        
        return np.array([energy, spectral_centroid / 4000, pitch * 100])
    
    def _detect_voice_change(self, new_features: np.ndarray) -> bool:
        """
        检测语音特征是否发生显著变化（说话人切换）
        
        Returns:
            True 如果检测到说话人变化
        """
        if len(self._recent_features) < 2:
            return False
        
        # 与最近的特征比较
        last_features = self._recent_features[-1]
        
        # 计算特征差异
        diff = np.abs(new_features - last_features)
        max_diff = np.max(diff)
        
        # 能量归一化
        if last_features[0] > 0:
            energy_ratio = new_features[0] / last_features[0]
            energy_change = abs(1 - energy_ratio)
        else:
            energy_change = 0
        
        # 检测明显变化
        if max_diff > VOICE_CHANGE_THRESHOLD or energy_change > 0.5:
            # 再与更早的特征比较，确保不是噪音
            if len(self._recent_features) >= 3:
                earlier_features = self._recent_features[-3]
                older_diff = np.mean(np.abs(new_features - earlier_features))
                if older_diff > VOICE_CHANGE_THRESHOLD * 0.7:
                    return True
            elif max_diff > VOICE_CHANGE_THRESHOLD * 1.5:
                return True
        
        return False
    
    def _update_state(self, is_speech: bool, chunk: np.ndarray) -> Optional[SpeechSegment]:
        """更新状态机"""
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
            
            # 说话人变化检测
            new_features = self._extract_voice_features(chunk)
            self._recent_features.append(new_features)
            if len(self._recent_features) > self._feature_history_size:
                self._recent_features.pop(0)
            
            # 检测说话人变化
            voice_changed = self._detect_voice_change(new_features)
            if voice_changed and len(self.speech_buffer) >= 3:
                # 计算差异信息用于日志
                last_features = self._recent_features[-1]
                diff = np.abs(new_features - last_features)
                max_diff = np.max(diff)
                print(f"[VAD] 检测到说话人变化，强制分段 (特征差异={max_diff:.3f}, 原因=声纹变化)")
                total_samples = sum(len(x) for x in self.speech_buffer)
                audio_data = np.concatenate(self.speech_buffer)
                start_ms = int(self.speech_start_sample * 1000 / self.sample_rate)
                end_ms = int((self.speech_start_sample + total_samples) * 1000 / self.sample_rate)
                
                # 重置，但保留最后几帧用于下一段（重叠处理）
                overlap_frames = 2
                self.speech_buffer = []
                self.speech_start_sample = self._total_samples_processed
                self.silence_samples = 0
                self._recent_features = []
                
                return SpeechSegment(
                    audio_data=audio_data,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    segment_reason="voice_change"
                )
            
            if is_speech:
                self.silence_samples = 0
            else:
                self.silence_samples += VAD_WINDOW_SIZE
                
                if self.silence_samples >= self.min_silence_samples:
                    # 确认语音结束
                    total_samples = sum(len(x) for x in self.speech_buffer)
                    
                    # 检查最小语音时长
                    if total_samples >= self.min_speech_samples:
                        audio_data = np.concatenate(self.speech_buffer)
                        start_ms = int(self.speech_start_sample * 1000 / self.sample_rate)
                        end_ms = int((self.speech_start_sample + total_samples) * 1000 / self.sample_rate)
                        silence_duration_ms = int(self.silence_samples * 1000 / self.sample_rate)
                        
                        print(f"[VAD] 语音结束 (样本数={total_samples}, {start_ms}-{end_ms}ms, 原因=静音超时 {silence_duration_ms}ms)")
                        
                        # 重置到 idle 等待下一句
                        self.state = "idle"
                        self.speech_buffer = []
                        self.speech_start_sample = 0
                        
                        return SpeechSegment(
                            audio_data=audio_data,
                            start_ms=start_ms,
                            end_ms=end_ms,
                            segment_reason="silence_timeout"
                        )
                    else:
                        # 语音太短，忽略
                        print(f"[VAD] 语音太短，忽略")
                        self.state = "idle"
                        self.speech_buffer = []
                        self.speech_start_sample = 0
        
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
        识别音频数据
        
        Args:
            audio_data: 音频数据，float32，16kHz
            on_delta: 回调函数，实时推送转录结果
            language: 语言，zh 或 en
        """
        try:
            # FunASR 推理（Paraformer 模型）
            result = self.asr_model.generate(
                input=audio_data,
                batch_size_s=300,       # 批量大小（秒）
                return_raw_text=True,   # 返回原始文本
                language=language,
            )
            
            # 处理结果
            if result:
                for item in result:
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        if text:
                            print(f"[ASR] 转录结果: {text}")
                            on_delta(TranscriptDelta(
                                text=text,
                                is_final=True,  # 非流式，单次调用即为最终结果
                                start_ms=0,
                                end_ms=0
                            ))
                    elif isinstance(item, str) and item.strip():
                        print(f"[ASR] 转录结果: {item}")
                        on_delta(TranscriptDelta(
                            text=item.strip(),
                            is_final=True,
                            start_ms=0,
                            end_ms=0
                        ))
            else:
                print("[ASR] 无转录结果")
        
        except Exception as e:
            print(f"[ASR] 识别失败: {e}")
            import traceback
            traceback.print_exc()


# ============== 流式声纹识别器 ==============

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
        threshold: float = 0.75  # [0, 1] 范围，0.75 约等于余弦相似度 0.5
    ) -> Optional[Tuple[str, float, float, float]]:
        """
        提取声纹并比对
        
        Args:
            audio_data: 音频数据，float32，16kHz
            registered_embeddings: 已注册的声纹 {speaker_id: embedding}
            threshold: 相似度阈值
        
        Returns:
            (speaker_id, best_score, interviewer_sim, candidate_sim) 如果匹配，否则 None
        """
        try:
            if not registered_embeddings:
                print("[声纹] ⚠️ 没有已注册的说话人，无法进行声纹识别")
                return None
            
            print(f"[声纹] 开始识别，音频长度={len(audio_data)/16000:.2f}秒，已注册说话人: {list(registered_embeddings.keys())}")
            
            # 使用 SpeakerEmbeddingExtractor 提取声纹
            embedding = self.extractor.extract(audio_data)
            
            # 打印声纹特征参数
            emb_norm = np.linalg.norm(embedding)
            emb_mean = np.mean(embedding)
            emb_std = np.std(embedding)
            emb_min = np.min(embedding)
            emb_max = np.max(embedding)
            print(f"[声纹] 声纹特征参数: 维度={len(embedding)}, L2范数={emb_norm:.4f}, 均值={emb_mean:.4f}, 标准差={emb_std:.4f}, 范围=[{emb_min:.4f}, {emb_max:.4f}]")
            
            # 比对
            best_match = None
            best_score = 0
            interviewer_sim = 0.0
            candidate_sim = 0.0
            
            for speaker_id, registered_emb in registered_embeddings.items():
                # 余弦相似度（归一化到 [0, 1]）
                cos_sim = np.dot(embedding, registered_emb) / (
                    np.linalg.norm(embedding) * np.linalg.norm(registered_emb)
                )
                score = (cos_sim + 1.0) / 2.0  # 映射到 [0, 1]

                print(f"[声纹] 与 {speaker_id} 相似度: cos_sim={cos_sim:.3f}, score={score:.3f}, threshold={threshold}")

                # 记录两个角色的相似度
                if speaker_id == "interviewer":
                    interviewer_sim = score
                elif speaker_id == "candidate":
                    candidate_sim = score

                if score > best_score:
                    best_score = score
                    best_match = speaker_id

            # 始终返回最高相似度的说话人（不硬卡阈值）
            if best_match:
                print(f"[声纹] 识别结果: {best_match} (score={best_score:.3f})")
                return (best_match, best_score, interviewer_sim, candidate_sim)
            return None
        
        except Exception as e:
            print(f"[声纹] ❌ 声纹识别异常: {e}")
            import traceback
            traceback.print_exc()
            return None


# ============== 流式处理管道 ==============

class StreamingPipeline:
    """
    流式 VAD + ASR + 声纹识别管道
    
    特性：
    - 实时流式处理，无需等待完整音频
    - ASR 支持实时输出中间结果
    - 声纹识别异步比对
    - 异步回调，不会阻塞音频接收
    """
    
    def __init__(
        self,
        vad_model,
        asr_model,
        camp_model=None,
        language: str = "zh",
        device: str = "cuda"
    ):
        self.vad = StreamingVAD(vad_model)
        self.asr = StreamingASR(asr_model)
        self.speaker = StreamingSpeakerRecognition(camp_model, device=device) if camp_model else None
        self.language = language
        
        # 回调（可以是普通函数或协程）
        self.on_transcript: Optional[Callable] = None
        self.on_speaker: Optional[Callable] = None
        self.on_speech_segment: Optional[Callable] = None
        
        # 注册的声纹
        self._registered_speakers: Dict[str, np.ndarray] = {}
        
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
    
    def register_speaker(self, speaker_id: str, embedding: np.ndarray):
        """注册说话人声纹"""
        self._registered_speakers[speaker_id] = embedding
        print(f"[管道] 已注册说话人: {speaker_id}, 当前共 {len(self._registered_speakers)} 位")
        if self.speaker:
            print(f"[管道] StreamingSpeakerRecognition 已配置")
        else:
            print(f"[管道] 警告: StreamingSpeakerRecognition 未配置（camp_model=None）")
    
    async def start(self):
        """启动管道（启动后台处理任务）"""
        if self._process_task is None or self._process_task.done():
            self._loop = asyncio.get_event_loop()
            self._process_task = asyncio.create_task(self._process_loop())
            print("[管道] 流式管道已启动")
    
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
                    if delta.text.strip() and self.on_transcript:
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
        
        # VAD 检测（同步，在当前线程执行）
        try:
            segment = self.vad.feed(audio_data)
        except Exception as e:
            print(f"[管道] VAD 检测异常: {e}")
            import traceback
            traceback.print_exc()
            return
        
        if segment:
            print(f"[管道] 检测到语音片段，样本数={len(segment.audio_data)}, 时长={len(segment.audio_data)/16000:.2f}s, 分段原因={segment.segment_reason}")
            
            # 先同步执行声纹识别（确保在转录之前完成）
            speaker_info = None  # 本次片段的声纹信息，直接传给 ASR
            if self.speaker is None:
                print("[管道] ⚠️ 声纹模型未加载，跳过声纹识别")
            elif not self._registered_speakers:
                print("[管道] ⚠️ 没有已注册的说话人，跳过声纹识别")
            else:
                print(f"[管道] 执行声纹识别，已注册: {list(self._registered_speakers.keys())}")
                loop = asyncio.get_event_loop()
                speaker_result = await loop.run_in_executor(
                    None,
                    self.speaker.extract_and_compare,
                    segment.audio_data,
                    self._registered_speakers
                )
                if speaker_result:
                    sid, confidence, interviewer_sim, candidate_sim = speaker_result
                    # 存储：说话人ID, 最佳置信度, 面试官相似度, 候选人相似度
                    speaker_info = (sid, confidence, interviewer_sim, candidate_sim)
                    print(f"[管道] 声纹识别成功: {sid} (置信度={confidence:.3f}, 面试官={interviewer_sim:.3f}, 候选人={candidate_sim:.3f})")
            
            # 触发语音段落回调（自动注册在回调中同步等待完成）
            # 关键：这里 await，确保自动注册完成后才执行 ASR，避免 ASR 先于注册完成
            if self.on_speech_segment:
                result = self.on_speech_segment(segment)
                if asyncio.iscoroutine(result):
                    await result
            
            # 提交 ASR 任务，将声纹信息作为参数传入（不依赖共享状态，避免竞态）
            print(f"[管道] 提交 ASR 任务...")
            asyncio.create_task(
                self._run_streaming_asr_locked(segment.audio_data, segment.segment_reason, speaker_info)
            )
            print(f"[管道] ASR 任务已提交（非阻塞）")
    
    async def _run_streaming_asr_locked(self, audio_data: np.ndarray, segment_reason: str = None, speaker_info: tuple = None):
        """带锁的 ASR 执行，确保串行"""
        async with self._asr_lock:
            await self._loop.run_in_executor(
                None,
                self._run_streaming_asr,
                audio_data,
                segment_reason,
                speaker_info
            )
    
    def _run_streaming_asr(self, audio_data: np.ndarray, segment_reason: str = None, speaker_info: tuple = None):
        """在线程池中运行流式 ASR"""
        print(f"[ASR-Thread] 开始识别，样本数={len(audio_data)}")
        
        def on_delta(delta: TranscriptDelta):
            print(f"[ASR-Thread] on_delta called: {delta.text[:50]}...")
            
            # 声纹信息已由 feed_audio 同步执行后直接传入，不依赖共享状态
            if speaker_info:
                delta.speaker_id = speaker_info[0]
                delta.speaker_confidence = speaker_info[1]
                delta.interviewer_sim = speaker_info[2]
                delta.candidate_sim = speaker_info[3]
                print(f"[ASR-Thread] 转录结果已标记说话人: {speaker_info[0]}, 面试官={speaker_info[2]:.3f}, 候选人={speaker_info[3]:.3f}")
                # 根据相似度推断角色（用于声纹未注册时的 sequential fallback）
                if speaker_info[3] > speaker_info[2]:
                    delta.recognized_role = "candidate"
                elif speaker_info[2] > speaker_info[3]:
                    delta.recognized_role = "interviewer"
                else:
                    delta.recognized_role = "interviewer"  # 相同按面试官
            
            # 传递分段原因（用于声纹未注册时区分说话人切换）
            if segment_reason:
                delta.segment_reason = segment_reason
            
            try:
                self._transcript_queue.put_nowait(("delta", delta))
            except Exception as e:
                print(f"[ASR-Thread] 放入队列失败: {e}")
        
        try:
            self.asr.recognize(audio_data, on_delta, self.language)
        except Exception as e:
            print(f"[ASR-Thread] 识别异常: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[ASR-Thread] 识别完成")
    
    async def _run_speaker_recognition(self, audio_data: np.ndarray):
        """异步声纹识别"""
        if not self.speaker or not self._registered_speakers:
            print(f"[声纹] 跳过：speaker={self.speaker is not None}, registered={bool(self._registered_speakers)}")
            return
        
        print(f"[声纹] 开始识别，registered={list(self._registered_speakers.keys())}")
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self.speaker.extract_and_compare,
            audio_data,
            self._registered_speakers
        )
        
        if result:
            speaker_id, confidence, interviewer_sim, candidate_sim = result
            print(f"[声纹] 识别结果: {speaker_id}")
            await self._transcript_queue.put(("speaker_result", (speaker_id, confidence, interviewer_sim, candidate_sim)))
        else:
            print("[声纹] 未匹配到任何说话人")
    
    async def stop(self) -> None:
        """停止管道"""
        if self._process_task:
            await self._transcript_queue.put(None)  # 发送停止信号
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass
            self._process_task = None
            print("[管道] 流式管道已停止")
    
    def reset(self):
        """重置管道状态"""
        self.vad.reset()


# ============== 便捷创建函数 ==============

def create_streaming_pipeline(
    model_manager,
    language: str = "zh"
) -> StreamingPipeline:
    """
    从 ModelManager 创建流式管道
    """
    return StreamingPipeline(
        vad_model=model_manager.get_vad_model(),
        asr_model=model_manager.get_asr_model(),
        camp_model=model_manager.get_camp_model(),
        language=language,
        device=model_manager.device
    )
