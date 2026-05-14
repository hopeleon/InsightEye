"""
Primewords Chinese Corpus Set 1 (SLR47) 数据集加载器

数据集信息：
    - 规模：约 100 小时中文普通话语音
    - 说话人：296 人
    - 录制方式：智能手机
    - 下载：https://openslr.org/resources/47/primewords_md_2018_set1.tar.gz (9.0 GB)
    - 授权：CC BY-NC-ND 4.0（学术免费）

目录结构（解压后应如下）：

    data_primewords/                          ← PRIMEWORDS_DATA_DIR 指向此目录
    ├── set1/
    │   ├── 0000a4e8ef14b6bb48d200b00a42a0be/   ← speaker_id 文件夹（UUID 格式）
    │   │   ├── 0000a4e8ef14b6bb48d200b00a42a0be_001.mp3
    │   │   ├── 0000a4e8ef14b6bb48d200b00a42a0be_002.mp3
    │   │   └── ...
    │   ├── 0002ec1a0a7c9f2ce72b7a9afbf6b4fb/
    │   │   └── ...
    │   └── ...
    └── primewords_file_mapping_transcript.json

每个说话人目录下有该人录制的多段音频（MP3），JSON 中记录了每个音频对应的文本内容。
"""

from __future__ import annotations

import json
import os
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import numpy as np


# ==================== 音频读取工具 ====================


def read_mp3_as_wav_bytes(mp3_path: str) -> bytes:
    """将 MP3 文件解码为 WAV 格式字节串（16kHz 单声道）"""
    try:
        import soundfile as sf
        data, sr = sf.read(mp3_path, dtype="float32")
    except ImportError:
        try:
            import librosa
            data, sr = librosa.load(mp3_path, sr=16000, mono=True)
        except ImportError:
            import subprocess
            import sys
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "soundfile", "-q"],
                capture_output=True,
            )
            import soundfile as sf
            data, sr = sf.read(mp3_path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        try:
            import librosa
            data = librosa.resample(data, orig_sr=sr, target_sr=16000)
        except ImportError:
            from scipy import signal
            num = int(len(data) * 16000 / sr)
            data = signal.resample(data, num)
    data = np.clip(data, -1.0, 1.0)
    wav_bytes = _float32_to_wav(data, 16000)
    return wav_bytes


def read_audio_file(file_path: str) -> np.ndarray:
    """
    读取任意格式音频文件并转换为 16kHz float32 单声道 numpy 数组。

    支持格式：WAV (PCM / MP3), MP3, FLAC, OGG 等 soundfile / librosa 可加载的格式。
    返回 shape=(N,) 的 float32 数组，值域 [-1, 1]，单位为秒。
    """
    file_path = str(file_path)
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".mp3":
        return _decode_audio_to_float32(file_path)

    try:
        import soundfile as sf
        data, sr = sf.read(file_path, dtype="float32")
    except Exception:
        try:
            import librosa
            data, sr = librosa.load(file_path, sr=16000, mono=True)
        except ImportError:
            import subprocess, sys
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "soundfile", "-q"],
                capture_output=True,
            )
            import soundfile as sf
            data, sr = sf.read(file_path, dtype="float32")

    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        try:
            import librosa
            data = librosa.resample(data, orig_sr=sr, target_sr=16000)
        except ImportError:
            from scipy import signal
            num = int(len(data) * 16000 / sr)
            data = signal.resample(data, num)
    return np.clip(data, -1.0, 1.0).astype(np.float32)


def _decode_audio_to_float32(mp3_path: str) -> np.ndarray:
    """解码 MP3 文件为 16kHz float32 单声道数组"""
    try:
        import soundfile as sf
        data, sr = sf.read(mp3_path, dtype="float32")
    except Exception:
        import librosa
        data, sr = librosa.load(mp3_path, sr=16000, mono=True)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        import librosa
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)
    return np.clip(data, -1.0, 1.0).astype(np.float32)


def _float32_to_wav(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """将 float32 音频数据编码为 WAV 字节串"""
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    buffer = b""
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_int16.tobytes())
    return buffer


# ==================== 数据集加载器 ====================


@dataclass
class PrimewordsUtterance:
    """一条语音记录"""
    speaker_id: str          # 说话人 UUID（如 "0000a4e8ef14b6bb48d200b00a42a0be"）
    file_path: str          # 音频文件绝对路径
    file_id: str            # 文件唯一标识（JSON 中的 file_id）
    transcript: str         # 语音内容文本
    duration_sec: float     # 音频时长（秒）


@dataclass
class PrimewordsSpeaker:
    """一个说话人的统计信息"""
    speaker_id: str
    audio_dir: str          # 音频目录路径
    num_utterances: int     # 该说话人的音频段数
    total_duration_sec: float  # 总时长


class PrimewordsDataset:
    """
    Primewords Chinese Corpus Set 1 (SLR47) 数据集加载器

    使用方法：

        from tools.primewords_loader import PrimewordsDataset

        # 指向解压后的根目录（包含 set1/ 文件夹和 JSON 文件）
        dataset = PrimewordsDataset("D:/datasets/primewords_md_2018_set1")

        # 遍历所有说话人
        for speaker in dataset.iter_speakers():
            print(f"speaker={speaker.speaker_id}, utterances={speaker.num_utterances}")

        # 遍历指定说话人的所有音频
        for utt in dataset.iter_utterances("0000a4e8ef14b6bb48d200b00a42a0be"):
            audio = dataset.load_audio(utt)   # 返回 float32 numpy 数组
            print(f"  file={utt.file_path}, transcript={utt.transcript}, dur={utt.duration_sec:.1f}s")

        # 获取说话人列表（字典，key=speaker_id）
        speakers = dataset.get_speakers()
    """

    # Primewords 标准解压后的目录布局
    _DEFAULT_SET1_SUBFOLDER = "set1"
    _JSON_FILENAME = "primewords_file_mapping_transcript.json"

    def __init__(self, data_dir: Optional[str] = None):
        """
        Args:
            data_dir: Primewords 数据集根目录，即解压后包含 set1/ 和 JSON 文件的目录。
                     默认为 config.PRIMEWORDS_DATA_DIR。
        """
        if data_dir is None:
            from app.config import PRIMEWORDS_DATA_DIR
            data_dir = PRIMEWORDS_DATA_DIR

        self.data_dir = Path(data_dir).resolve()
        self._transcript_map: Dict[str, dict] = {}
        self._speaker_index: Dict[str, List[PrimewordsUtterance]] = {}
        self._speaker_dirs: Dict[str, str] = {}
        self._checked = False

    # ==================== 公开 API ====================

    def get_speakers(self) -> Dict[str, PrimewordsSpeaker]:
        """返回所有说话人的信息字典（key=speaker_id）"""
        self._ensure_loaded()
        return {
            sid: PrimewordsSpeaker(
                speaker_id=sid,
                audio_dir=self._speaker_dirs[sid],
                num_utterances=len(utts),
                total_duration_sec=sum(u.duration_sec for u in utts),
            )
            for sid, utts in self._speaker_index.items()
        }

    def iter_speakers(self) -> Iterator[PrimewordsSpeaker]:
        """遍历所有说话人（生成器）"""
        speakers = self.get_speakers()
        for sp in sorted(speakers.values(), key=lambda s: s.speaker_id):
            yield sp

    def iter_utterances(self, speaker_id: str) -> Iterator[PrimewordsUtterance]:
        """遍历指定说话人的所有音频段（按文件 ID 排序）"""
        self._ensure_loaded()
        for utt in sorted(self._speaker_index.get(speaker_id, []), key=lambda u: u.file_id):
            yield utt

    def get_speaker_audio(
        self,
        speaker_id: str,
        min_duration_sec: float = 1.0,
        max_utterances: Optional[int] = None,
    ) -> List[np.ndarray]:
        """
        获取指定说话人的所有音频数据（已加载为 numpy 数组）。

        Args:
            speaker_id: 说话人 ID
            min_duration_sec: 只保留时长 >= 此值的音频段（秒），默认 1.0s
            max_utterances: 最多加载多少条（用于快速测试），None=全部

        Returns:
            List[np.ndarray]，每项为 shape=(N,) 的 float32 数组（16kHz 单声道）
        """
        result = []
        for utt in self.iter_utterances(speaker_id):
            if utt.duration_sec < min_duration_sec:
                continue
            audio = self.load_audio(utt)
            result.append(audio)
            if max_utterances and len(result) >= max_utterances:
                break
        return result

    def load_audio(self, utterance: PrimewordsUtterance) -> np.ndarray:
        """
        加载单条语音记录对应的音频文件。

        内部会自动检测音频格式（MP3 / WAV / FLAC 等）并统一转换为
        16kHz float32 单声道 numpy 数组。

        Returns:
            np.ndarray，shape=(N,)，值域 [-1, 1]
        """
        path = utterance.file_path
        if not os.path.exists(path):
            raise FileNotFoundError(f"音频文件不存在: {path}")
        return read_audio_file(path)

    def summary(self) -> dict:
        """返回数据集摘要"""
        self._ensure_loaded()
        speakers = self.get_speakers()
        total_utts = sum(s.num_utterances for s in speakers.values())
        total_dur = sum(s.total_duration_sec for s in speakers.values())
        return {
            "data_dir": str(self.data_dir),
            "num_speakers": len(speakers),
            "total_utterances": total_utts,
            "total_duration_hours": round(total_dur / 3600, 2),
            "avg_utterances_per_speaker": round(total_utts / len(speakers), 1) if speakers else 0,
            "avg_duration_per_speaker_hours": round(total_dur / len(speakers) / 3600, 2) if speakers else 0,
        }

    # ==================== 内部实现 ====================

    def _ensure_loaded(self) -> None:
        """惰性加载（首次访问时才解析 JSON 和扫描目录）"""
        if self._checked:
            return
        self._checked = True
        self._discover_structure()
        self._load_transcript_json()
        self._build_speaker_index()

    def _discover_structure(self) -> None:
        """
        检测实际目录结构。

        支持以下解压布局：
        1. data_primewords/
               set1/{speaker_uuid}/xxx.mp3
               primewords_file_mapping_transcript.json
        2. primewords_md_2018_set1/
               set1/{speaker_uuid}/xxx.mp3
               primewords_file_mapping_transcript.json
        3. 直接在 data_dir 下找 {speaker_uuid}/xxx.mp3 和 JSON 文件
        """
        candidates = []

        # 候选 1：标准 set1/ 子目录
        set1_path = self.data_dir / self._DEFAULT_SET1_SUBFOLDER
        if set1_path.is_dir():
            candidates.append(set1_path)

        # 候选 2：直接在 data_dir 下找 speaker 文件夹（UUID 命名）
        for entry in self.data_dir.iterdir():
            if entry.is_dir() and len(entry.name) >= 32:
                candidates.append(self.data_dir)

        # 候选 3：data_dir 本身就是 set1 层（即 data_dir = .../set1）
        # 通过检查是否有 JSON 文件来判断
        json_candidate = self.data_dir / self._JSON_FILENAME
        if json_candidate.exists():
            candidates.insert(0, self.data_dir)

        if not candidates:
            raise FileNotFoundError(
                f"无法找到 Primewords 数据集目录。\n"
                f"请确认已解压 primewords_md_2018_set1.tar.gz，\n"
                f"并确保 PRIMEWORDS_DATA_DIR 指向包含 set1/ 文件夹和 JSON 文件的根目录。\n"
                f"当前路径: {self.data_dir}\n"
                f"可用目录: {[str(p) for p in self.data_dir.iterdir()]}"
            )

        # 选择第一个有效候选
        for cand in candidates:
            mp3_files = list(cand.rglob("*.mp3"))
            if mp3_files:
                self._audio_root = cand
                return

        raise FileNotFoundError(
            f"目录结构不符合 Primewords 格式（未找到 .mp3 文件）。\n"
            f"当前路径: {self.data_dir}"
        )

    def _load_transcript_json(self) -> None:
        """加载并解析 transcript JSON 文件"""
        json_paths = [
            self.data_dir / self._JSON_FILENAME,
            self.data_dir.parent / self._JSON_FILENAME,
        ]
        for jp in json_paths:
            if jp.exists():
                self._json_path = jp
                break
        else:
            raise FileNotFoundError(
                f"找不到 transcript JSON 文件: {self._JSON_FILENAME}\n"
                f"预期路径之一: {json_paths[0]}"
            )

        with open(self._json_path, encoding="utf-8") as f:
            raw = json.load(f)

        # JSON 结构：顶层是 dict，key=file_id，value={transcript, ...}
        # 也可能是 list，每个元素含 file_id 和 transcript
        if isinstance(raw, dict):
            self._transcript_map = raw
        elif isinstance(raw, list):
            self._transcript_map = {item["file_id"]: item for item in raw}
        else:
            raise ValueError(f"JSON 格式不支持：顶层应为 dict 或 list，实际为 {type(raw)}")

    def _build_speaker_index(self) -> None:
        """扫描音频目录，建立 speaker_id → [utterances] 索引"""
        audio_files = sorted(self._audio_root.rglob("*.mp3"))
        if not audio_files:
            raise RuntimeError(f"未在 {self._audio_root} 中找到 .mp3 文件")

        for mp3_path in audio_files:
            file_id = mp3_path.stem  # 文件名不含扩展名

            # 从 JSON 获取文本
            meta = self._transcript_map.get(file_id, {})
            transcript = meta.get("text", "") or meta.get("transcript", "")

            # 从父目录名获取 speaker_id（UUID 格式）
            speaker_id = mp3_path.parent.name

            # 估算时长（MP3 不可直接读，先记为 0，由 load_audio 填充）
            duration = 0.0

            utt = PrimewordsUtterance(
                speaker_id=speaker_id,
                file_path=str(mp3_path),
                file_id=file_id,
                transcript=transcript,
                duration_sec=duration,
            )

            self._speaker_index.setdefault(speaker_id, []).append(utt)
            self._speaker_dirs[speaker_id] = str(mp3_path.parent)
