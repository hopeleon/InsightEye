"""
VAD + ASR 异步处理管道
提供实时音频流的语音活动检测和语音转文字功能
"""

import asyncio
import io
import struct
from typing import Optional, Callable, Awaitable, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
import torch

# VAD 参数
VAD_SAMPLE_RATE = 16000
VAD_WINDOW_SIZE = 512  # 毫秒
VAD_THRESHOLD = 0.5
VAD_MIN_SPEECH_DURATION_MS = 250  # 最小语音持续时间
VAD_MIN_SILENCE_DURATION_MS = 300  # 最小静音持续时间（判断语音结束）


class VADState(Enum):
    """VAD 状态机"""
    IDLE = "idle"           # 等待语音开始
    SPEECH = "speech"       # 检测到语音
    ENDING = "ending"       # 语音可能结束，等待确认


@dataclass
class SpeechSegment:
    """识别出的语音片段"""
    audio_data: np.ndarray          # 音频数据（float32, 16kHz）
    start_ms: int                   # 开始时间（毫秒）
    end_ms: int                     # 结束时间（毫秒）
    transcript: Optional[str] = None  # 转录文本
    speaker_id: Optional[str] = None  # 说话人 ID（由声纹识别填充）


@dataclass
class TranscriptionResult:
    """转录结果"""
    text: str
    start_ms: int
    end_ms: int
    speaker_id: Optional[str] = None
    confidence: float = 1.0


class VADProcessor:
    """
    Silero VAD 语音活动检测处理器
    检测音频流中的语音边界
    """
    
    def __init__(self, vad_model, sample_rate: int = 16000):
        self.vad_model = vad_model
        self.sample_rate = sample_rate
        self.window_size_samples = int(VAD_WINDOW_SIZE * sample_rate / 1000)  # 512 samples
        
        # 状态
        self.state = VADState.IDLE
        self.speech_buffer: List[np.ndarray] = []
        self.speech_start_time: Optional[int] = None
        self.silence_frames = 0
        self.total_frames = 0
        
        # 参数
        self.min_speech_samples = int(VAD_MIN_SPEECH_DURATION_MS * sample_rate / 1000)
        self.min_silence_samples = int(VAD_MIN_SILENCE_DURATION_MS * sample_rate / 1000)
    
    def reset(self):
        """重置状态"""
        self.state = VADState.IDLE
        self.speech_buffer = []
        self.speech_start_time = None
        self.silence_frames = 0
        self.total_frames = 0
    
    def process_chunk(self, audio_chunk: np.ndarray) -> Optional[SpeechSegment]:
        """
        处理一个音频块，返回检测到的语音片段（如果有）
        
        Args:
            audio_chunk: 音频数据，float32，范围 [-1, 1]，16kHz
        
        Returns:
            SpeechSegment 如果检测到完整语音片段，否则 None
        """
        self.total_frames += 1
        
        # 使用 Silero VAD 检测（需要 torch.Tensor）
        try:
            audio_tensor = torch.from_numpy(audio_chunk).float()
            vad_prob = self.vad_model(audio_tensor, VAD_SAMPLE_RATE).item()
            
            # 每 500 帧打印一次诊断
            if self.total_frames % 500 == 1:
                audio_rms = float(np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2)))
                print(f"[VAD] 帧={self.total_frames} 能量={audio_rms:.4f} VAD概率={vad_prob:.3f} 状态={self.state.name}")
                
        except Exception as e:
            print(f"[VAD] *** VAD 模型调用失败: {e} ***")
            vad_prob = 0.8
        
        is_speech = vad_prob > VAD_THRESHOLD
        
        # 状态机处理
        if self.state == VADState.IDLE:
            if is_speech:
                self.state = VADState.SPEECH
                self.speech_buffer.append(audio_chunk)
                self.speech_start_time = (self.total_frames - 1) * VAD_WINDOW_SIZE
                self.silence_frames = 0
                print(f"[VAD] *** 状态转换 IDLE -> SPEECH (帧={self.total_frames}) ***")
        
        elif self.state == VADState.SPEECH:
            if is_speech:
                self.speech_buffer.append(audio_chunk)
                self.silence_frames = 0
            else:
                self.speech_buffer.append(audio_chunk)
                self.silence_frames += len(audio_chunk)
                
                # 每 10 个静音块打印进度
                if self.total_frames % 10 == 0:
                    print(f"[VAD] 静音累积: {self.silence_frames}/{self.min_silence_samples} ({self.silence_frames * 100 // self.min_silence_samples}%)")
                
                if self.silence_frames >= self.min_silence_samples:
                    print(f"[VAD] *** 状态转换 SPEECH -> ENDING (静音 {self.silence_frames} samples) ***")
                    self.state = VADState.ENDING
        
        elif self.state == VADState.ENDING:
            if is_speech:
                print(f"[VAD] *** 状态转换 ENDING -> SPEECH (语音恢复) ***")
                self.state = VADState.SPEECH
                self.speech_buffer.append(audio_chunk)
                self.silence_frames = 0
            else:
                print(f"[VAD] *** 状态转换 ENDING -> IDLE (语音结束) ***")
                segment = self._create_segment()
                self.reset()
                return segment
        
        return None
    
    def _create_segment(self) -> Optional[SpeechSegment]:
        """从缓冲区创建语音片段"""
        if not self.speech_buffer:
            return None
        
        # 合并音频数据
        audio_data = np.concatenate(self.speech_buffer)
        
        # 检查最小语音长度
        if len(audio_data) < self.min_speech_samples:
            return None
        
        # 计算时间戳
        start_ms = int(self.speech_start_time or 0)
        end_ms = start_ms + int(len(audio_data) * 1000 / self.sample_rate)
        
        return SpeechSegment(
            audio_data=audio_data,
            start_ms=start_ms,
            end_ms=end_ms
        )


class ASRProcessor:
    """
    FunASR 语音识别处理器
    将语音片段转换为文字
    """
    
    def __init__(self, asr_model):
        self.asr_model = asr_model
        self.sample_rate = 16000
    
    def transcribe(self, audio_data: np.ndarray) -> TranscriptionResult:
        """
        转录音频数据
        
        Args:
            audio_data: 音频数据，float32，16kHz
        
        Returns:
            TranscriptionResult 转录结果
        """
        try:
            # FunASR 可以直接接收 numpy array
            result = self.asr_model.generate(
                input=audio_data,
                batch_size_s=300,
                return_raw_text=True,
                is_streaming=False,
            )
            
            # 解析结果
            if isinstance(result, list) and len(result) > 0:
                item = result[0]
                if isinstance(item, dict):
                    text = item.get("text", "")
                    print(f"[ASR] 转录: '{text}'")
                    return TranscriptionResult(
                        text=text,
                        start_ms=0,
                        end_ms=0,
                        confidence=1.0
                    )
            
            return TranscriptionResult(text="", start_ms=0, end_ms=0)
            
        except Exception as e:
            print(f"[ASR] 转录失败: {e}")
            return TranscriptionResult(text="", start_ms=0, end_ms=0)


class VADASRPipeline:
    """
    VAD + ASR 异步处理管道
    接收音频流，检测语音边界，转录为文字
    """
    
    def __init__(
        self,
        vad_processor: VADProcessor,
        asr_processor: ASRProcessor,
        audio_buffer_size: int = 50
    ):
        """
        Args:
            vad_processor: VAD 处理器
            asr_processor: ASR 处理器
            audio_buffer_size: 音频队列最大长度
        """
        self.vad = vad_processor
        self.asr = asr_processor
        self.audio_queue: asyncio.Queue = asyncio.Queue(maxsize=audio_buffer_size)
        
        # 样本缓冲（用于累积到精确的 512 samples）
        self._sample_buffer: np.ndarray = np.array([], dtype=np.float32)
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._pending_result_callback: Optional[Callable[[TranscriptionResult], Awaitable[None]]] = None
        self._pending_audio_callback: Optional[Callable[[SpeechSegment], Awaitable[None]]] = None
    
    async def start(
        self,
        result_callback: Optional[Callable[[TranscriptionResult], Awaitable[None]]] = None,
        audio_callback: Optional[Callable[[SpeechSegment], Awaitable[None]]] = None
    ) -> None:
        """
        启动处理管道
        
        Args:
            result_callback: 转录结果回调（异步）
            audio_callback: 语音片段回调（用于声纹识别）
        """
        self._pending_result_callback = result_callback
        self._pending_audio_callback = audio_callback
        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        print("[VADASRPipeline] 管道已启动")
    
    async def stop(self) -> None:
        """停止处理管道"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[VADASRPipeline] 管道已停止")
    
    async def feed_audio(self, audio_data: np.ndarray) -> bool:
        """
        接收音频数据并累积，累积满 512 samples 后放入队列
        
        Args:
            audio_data: 音频数据，float32，16kHz
        
        Returns:
            True 如果成功，False 如果队列满
        """
        # 追加到缓冲
        self._sample_buffer = np.concatenate([self._sample_buffer, audio_data])
        
        # 累积到精确的 512 samples 后，放入队列
        while len(self._sample_buffer) >= 512:
            chunk = self._sample_buffer[:512]
            self._sample_buffer = self._sample_buffer[512:]
            try:
                self.audio_queue.put_nowait(chunk)
            except asyncio.QueueFull:
                # 队列满了，丢弃最旧的块
                try:
                    self.audio_queue.get_nowait()
                    self.audio_queue.put_nowait(chunk)
                except asyncio.QueueEmpty:
                    pass
                return False
        return True
    
    async def feed_audio_from_pcm(self, pcm_bytes: bytes) -> bool:
        """
        从 PCM 字节喂入音频
        
        Args:
            pcm_bytes: PCM 数据（16bit, 16kHz, mono）
        
        Returns:
            True 如果成功入队，False 如果队列满
        """
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        return await self.feed_audio(audio_float32)
    
    async def _process_loop(self) -> None:
        """异步处理循环"""
        loop = asyncio.get_event_loop()
        processed_chunks = 0
        
        while self._running:
            try:
                # 异步获取音频数据
                try:
                    audio_chunk = await asyncio.wait_for(
                        self.audio_queue.get(),
                        timeout=0.05
                    )
                except asyncio.TimeoutError:
                    continue
                
                processed_chunks += 1
                
                # 在线程池中执行 VAD 处理（CPU 密集型）
                segment = await loop.run_in_executor(
                    None,
                    self.vad.process_chunk,
                    audio_chunk
                )
                
                # 如果检测到完整语音片段
                if segment is not None:
                    print(f"[VADASRPipeline] 检测到语音片段: {segment.start_ms}-{segment.end_ms}ms")
                    
                    # 回调音频片段（用于声纹识别）
                    if self._pending_audio_callback:
                        await self._pending_audio_callback(segment)
                    
                    # 在线程池中执行 ASR 转录（CPU 密集型）
                    result = await loop.run_in_executor(
                        None,
                        self.asr.transcribe,
                        segment.audio_data
                    )
                    
                    # 更新时间戳
                    result.start_ms = segment.start_ms
                    result.end_ms = segment.end_ms
                    
                    # 回调转录结果
                    if self._pending_result_callback and result.text.strip():
                        print(f"[VADASRPipeline] 转录结果: {result.text}")
                        await self._pending_result_callback(result)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[VADASRPipeline] 处理循环错误: {e}")
    
    def get_queue_size(self) -> int:
        """获取当前队列大小"""
        return self.audio_queue.qsize()


async def create_pipeline_from_manager(
    model_manager,
    audio_buffer_size: int = 50
) -> VADASRPipeline:
    """
    从 ModelManager 创建 VAD + ASR 管道
    
    Args:
        model_manager: 模型管理器实例
        audio_buffer_size: 音频队列大小
    
    Returns:
        配置好的 VADASRPipeline
    """
    vad_processor = VADProcessor(
        model_manager.get_vad_model(),
        sample_rate=16000
    )
    
    asr_processor = ASRProcessor(
        model_manager.get_asr_model()
    )
    
    return VADASRPipeline(
        vad_processor=vad_processor,
        asr_processor=asr_processor,
        audio_buffer_size=audio_buffer_size
    )
