"""
模式三EX：批量声纹识别算法测试脚本
基于 test_speaker_batch.py 复制，用于测试说话人识别算法改进

功能：
1. 从 E:\primewords_md_2018_set1 随机抽取 200 条音频
2. 从已注册的 speaker_voiceprints.db 数据库加载声纹
3. 对每条音频进行识别
4. 支持切换不同的识别算法进行对比测试
"""

import sys
import os
import json
import random

# 使用系统级真随机数生成器（基于 os.urandom）
_system_random = random.SystemRandom()
import sqlite3
import wave
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Callable
from enum import Enum

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.model_manager import SpeakerEmbeddingExtractor, ModelManager
from app.enhanced_speaker_recognition import (
    MultiSpeakerRegistry,
    SpeakerProfile,
    SpeakerMatchResult,
    SpeakerMatch,
)
from app.speaker_database import SpeakerDatabase
import numpy as np


class AlgorithmMode(Enum):
    """支持的识别算法模式"""
    # 基础模式
    SINGLE_WINDOW = "single_window"           # 单窗口直接匹配
    MULTI_WINDOW_VOTE = "multi_window_vote"  # 多窗口投票融合
    CASCADE = "cascade"                      # 级联匹配

    # 实验性模式
    WEIGHTED_AVG = "weighted_avg"           # 加权平均融合
    MEDIAN_FUSION = "median_fusion"         # 中位数融合
    ADAPTIVE_WINDOW = "adaptive_window"      # 自适应窗口大小
    QUALITY_WEIGHTED = "quality_weighted"   # 按注册质量加权
    SIMILARITY_RANKING = "similarity_ranking"  # 相似度排名加权


@dataclass
class TestResult:
    """单个测试片段的识别结果"""
    segment_id: int
    audio_path: str
    ground_truth_speaker_id: str
    recognized_speaker_id: Optional[str]
    recognized_speaker_name: Optional[str]
    recognized_score: float
    is_correct: bool
    top3_includes_correct: bool
    duration_sec: float
    # 扩展统计
    algorithm_used: str = ""
    all_scores: Dict[str, float] = field(default_factory=dict)  # 所有候选人的得分


@dataclass
class TestSummary:
    """测试汇总结果"""
    total_segments: int
    top1_correct: int
    top1_accuracy: float
    top3_correct: int
    top3_accuracy: float
    uncertain_count: int
    results: List[TestResult]
    algorithm_name: str = ""


class EnhancedSpeakerRecognitionTester:
    """
    增强版声纹识别测试器
    支持多种识别算法对比测试
    """

    def __init__(self):
        self.test_data_dir = Path(r"E:\primewords_md_2018_set1\primewords_md_2018_set1")
        self.audio_files_dir = self.test_data_dir / "audio_files"
        self.transcript_file = self.test_data_dir / "set1_transcript.json"
        self.db_path = Path(__file__).parent / "data" / "speaker_voiceprints.db"

        # 初始化
        self.registry: Optional[MultiSpeakerRegistry] = None
        self.speaker_db: Optional[SpeakerDatabase] = None
        self.transcripts: List[Dict] = []
        self.speaker_id_set: set = set()
        self.speaker_id_to_name: Dict[str, str] = {}
        self.speaker_profiles: Dict[str, SpeakerProfile] = {}  # 保存所有说话人profile用于自定义算法

        # 算法统计
        self.algorithm_stats: Dict[str, Dict] = {}

    def load_resources(self):
        """加载测试资源和初始化模型"""
        print("=" * 60)
        print("模式三EX：批量声纹识别算法测试")
        print("=" * 60)

        # 加载音频转录文件
        print("\n[1/5] 加载音频转录文件...")
        with open(self.transcript_file, "r", encoding="utf-8") as f:
            self.transcripts = json.load(f)
        print(f"  总共有 {len(self.transcripts)} 条音频记录")

        # 加载已注册的说话人数据库
        print("\n[2/5] 加载声纹数据库...")
        self.speaker_db = SpeakerDatabase(db_path=str(self.db_path))

        all_speakers = self.speaker_db.load_all(active_only=True)
        print(f"  数据库中有 {len(all_speakers)} 个已注册的说话人")

        self.speaker_id_set = set()
        self.speaker_id_to_name = {}
        for speaker in all_speakers:
            sid = speaker["speaker_id"]
            self.speaker_id_set.add(sid)
            self.speaker_id_to_name[sid] = speaker.get("name", sid)

        self.valid_test_samples = [
            t for t in self.transcripts
            if t["user_id"] in self.speaker_id_set
        ]
        print(f"  其中 {len(self.valid_test_samples)} 条音频属于已注册说话人")

        # 初始化声纹识别系统
        print("\n[3/5] 初始化声纹识别模型（CAM++）...")
        import asyncio
        model_mgr = ModelManager()
        asyncio.run(model_mgr.initialize())

        camp_model = model_mgr.get_camp_model()
        if camp_model is None:
            raise RuntimeError("CAM++ 模型加载失败")

        self.model_mgr = model_mgr
        self.extractor = SpeakerEmbeddingExtractor(camp_model=camp_model, device=model_mgr.device)

        # 创建 MultiSpeakerRegistry
        self.registry = MultiSpeakerRegistry(model_manager=model_mgr)

        # 从数据库加载已注册的说话人声纹
        print("\n[4/5] 从数据库加载已注册说话人的声纹...")
        self._load_registered_speakers_from_db()
        print(f"  已加载 {len(self.registry.speakers)} 个说话人的声纹到内存")

    def _load_registered_speakers_from_db(self):
        """从数据库加载已注册的说话人声纹"""
        all_speakers = self.speaker_db.load_all(active_only=True)

        loaded_count = 0
        for speaker in all_speakers:
            speaker_id = speaker["speaker_id"]

            embedding_bytes = speaker.get("embedding")
            if embedding_bytes is None:
                continue

            try:
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
            except Exception as e:
                print(f"    反序列化 embedding 失败 for {speaker_id}: {e}")
                continue

            # 保存原始profile用于自定义算法
            profile = SpeakerProfile(
                speaker_id=speaker_id,
                name=speaker.get("name"),
                embedding=embedding,
                embedding_mean=embedding,
                sample_count=speaker.get("sample_count", 1),
                individual_embeddings=[embedding],
                registration_quality=speaker.get("quality", 0.8),
            )
            self.speaker_profiles[speaker_id] = profile

            # 注册到 registry
            self.registry.speakers[speaker_id] = profile
            self.registry.matching_engine.register_speaker(
                speaker_id=speaker_id,
                embedding=embedding,
            )

            loaded_count += 1

            if loaded_count % 50 == 0:
                print(f"    已加载 {loaded_count} 个说话人...")

    def _find_audio_file(self, file_name: str) -> Optional[str]:
        """根据文件名查找音频文件路径"""
        base_name = file_name.replace(".wav", "")
        prefix = base_name[:2]
        first_dir = prefix[0]
        second_dir = prefix[:2]

        possible_path = self.audio_files_dir / first_dir / second_dir / file_name
        if possible_path.exists():
            return str(possible_path)

        for root, dirs, files in os.walk(self.audio_files_dir):
            if file_name in files:
                return os.path.join(root, file_name)

        return None

    def _load_wav_audio(self, filepath: str) -> Optional[Tuple[np.ndarray, int]]:
        """加载 WAV 音频文件"""
        try:
            with wave.open(filepath, "rb") as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                frames = wf.readframes(n_frames)

                if sample_width == 2:
                    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                else:
                    audio = np.frombuffer(frames, dtype=np.float32)

                if n_channels > 1:
                    audio = audio.reshape(-1, n_channels).mean(axis=1)

                if framerate != 16000:
                    import scipy.signal as signal
                    num_samples = int(len(audio) * 16000 / framerate)
                    audio = signal.resample(audio, num_samples)

                return audio.astype(np.float32), 16000
        except Exception as e:
            print(f"    加载音频失败 {filepath}: {e}")
            return None

    # ==================== 核心识别算法 ====================

    def _compute_single_window(self, audio: np.ndarray) -> Dict[str, float]:
        """单窗口直接匹配"""
        try:
            embedding = self.extractor.extract(audio)
            scores = {}

            for speaker_id, profile in self.speaker_profiles.items():
                cos_sim = float(np.dot(embedding, profile.embedding) /
                               (np.linalg.norm(embedding) * np.linalg.norm(profile.embedding) + 1e-8))
                scores[speaker_id] = (cos_sim + 1.0) / 2.0

            return scores
        except Exception as e:
            print(f"      [single_window] 错误: {e}")
            return {}

    def _compute_multi_window(self, audio: np.ndarray, n_windows: int = 3,
                              step_ratio: float = 0.25) -> Dict[str, float]:
        """多窗口提取 + 简单平均"""
        try:
            windows = self.extractor.extract_multi_window(audio, n_windows, step_ratio)
            valid = [(emb, ts) for emb, ts, ok in windows if ok]

            if not valid:
                return self._compute_single_window(audio)

            # 平均所有窗口的embedding
            embeddings = [emb for emb, _ in valid]
            fused_emb = np.mean(embeddings, axis=0)
            fused_emb = fused_emb / (np.linalg.norm(fused_emb) + 1e-8)

            scores = {}
            for speaker_id, profile in self.speaker_profiles.items():
                cos_sim = float(np.dot(fused_emb, profile.embedding) /
                               (np.linalg.norm(profile.embedding) + 1e-8))
                scores[speaker_id] = (cos_sim + 1.0) / 2.0

            return scores
        except Exception as e:
            print(f"      [multi_window] 错误: {e}")
            return self._compute_single_window(audio)

    def _compute_weighted_avg(self, audio: np.ndarray, n_windows: int = 3,
                             step_ratio: float = 0.25) -> Dict[str, float]:
        """加权平均融合：按窗口间一致性加权"""
        try:
            windows = self.extractor.extract_multi_window(audio, n_windows, step_ratio)
            valid = [(emb, ts, ok) for emb, ts, ok in windows if ok]

            if not valid:
                return self._compute_single_window(audio)

            embeddings = [emb for emb, _, _ in valid]
            fused_emb = np.mean(embeddings, axis=0)
            fused_emb = fused_emb / (np.linalg.norm(fused_emb) + 1e-8)

            # 计算每个窗口与融合向量的相似度作为权重
            weights = []
            for emb in embeddings:
                emb_norm = emb / (np.linalg.norm(emb) + 1e-8)
                sim = float(np.dot(emb_norm, fused_emb))
                weights.append(max(sim, 0.5))  # 保证最小权重

            # 加权融合
            weighted_emb = np.zeros_like(embeddings[0])
            total_weight = sum(weights)
            for emb, w in zip(embeddings, weights):
                weighted_emb += emb * (w / total_weight)

            weighted_emb = weighted_emb / (np.linalg.norm(weighted_emb) + 1e-8)

            scores = {}
            for speaker_id, profile in self.speaker_profiles.items():
                cos_sim = float(np.dot(weighted_emb, profile.embedding) /
                               (np.linalg.norm(profile.embedding) + 1e-8))
                scores[speaker_id] = (cos_sim + 1.0) / 2.0

            return scores
        except Exception as e:
            print(f"      [weighted_avg] 错误: {e}")
            return self._compute_single_window(audio)

    def _compute_median_fusion(self, audio: np.ndarray, n_windows: int = 3,
                               step_ratio: float = 0.25) -> Dict[str, float]:
        """中位数融合：对每个维度取中位数"""
        try:
            windows = self.extractor.extract_multi_window(audio, n_windows, step_ratio)
            valid = [(emb, ts, ok) for emb, ts, ok in windows if ok]

            if not valid:
                return self._compute_single_window(audio)

            embeddings = [emb for emb, _, _ in valid]

            if len(embeddings) == 1:
                fused_emb = embeddings[0]
            else:
                stacked = np.array(embeddings)
                fused_emb = np.median(stacked, axis=0)

            fused_emb = fused_emb / (np.linalg.norm(fused_emb) + 1e-8)

            scores = {}
            for speaker_id, profile in self.speaker_profiles.items():
                cos_sim = float(np.dot(fused_emb, profile.embedding) /
                               (np.linalg.norm(profile.embedding) + 1e-8))
                scores[speaker_id] = (cos_sim + 1.0) / 2.0

            return scores
        except Exception as e:
            print(f"      [median_fusion] 错误: {e}")
            return self._compute_single_window(audio)

    def _compute_quality_weighted(self, audio: np.ndarray, n_windows: int = 3,
                                  step_ratio: float = 0.25) -> Dict[str, float]:
        """按注册质量加权：注册质量高的说话人匹配时权重更高"""
        try:
            windows = self.extractor.extract_multi_window(audio, n_windows, step_ratio)
            valid = [(emb, ts, ok) for emb, ts, ok in windows if ok]

            if not valid:
                return self._compute_single_window(audio)

            embeddings = [emb for emb, _, _ in valid]
            fused_emb = np.mean(embeddings, axis=0)
            fused_emb = fused_emb / (np.linalg.norm(fused_emb) + 1e-8)

            scores = {}
            for speaker_id, profile in self.speaker_profiles.items():
                cos_sim = float(np.dot(fused_emb, profile.embedding) /
                               (np.linalg.norm(profile.embedding) + 1e-8))
                base_score = (cos_sim + 1.0) / 2.0

                # 乘以注册质量的平方根（温和加权）
                quality = profile.registration_quality
                weighted_score = base_score * (0.7 + 0.3 * quality)

                scores[speaker_id] = weighted_score

            return scores
        except Exception as e:
            print(f"      [quality_weighted] 错误: {e}")
            return self._compute_single_window(audio)

    def _compute_similarity_ranking(self, audio: np.ndarray, n_windows: int = 3,
                                    step_ratio: float = 0.25) -> Dict[str, float]:
        """相似度排名加权：结合绝对相似度和相对排名"""
        try:
            windows = self.extractor.extract_multi_window(audio, n_windows, step_ratio)
            valid = [(emb, ts, ok) for emb, ts, ok in windows if ok]

            if not valid:
                return self._compute_single_window(audio)

            embeddings = [emb for emb, _, _ in valid]
            fused_emb = np.mean(embeddings, axis=0)
            fused_emb = fused_emb / (np.linalg.norm(fused_emb) + 1e-8)

            # 先计算所有候选的基础分数
            raw_scores = {}
            for speaker_id, profile in self.speaker_profiles.items():
                cos_sim = float(np.dot(fused_emb, profile.embedding) /
                               (np.linalg.norm(profile.embedding) + 1e-8))
                raw_scores[speaker_id] = (cos_sim + 1.0) / 2.0

            if not raw_scores:
                return {}

            # 按分数排序
            sorted_speakers = sorted(raw_scores.items(), key=lambda x: x[1], reverse=True)
            n_speakers = len(sorted_speakers)

            # 计算排名分数（top1=1, top2=0.9, ..., topN=1-N*0.05）
            scores = {}
            for rank, (speaker_id, base_score) in enumerate(sorted_speakers):
                rank_score = max(1.0 - rank * 0.05, 0.5)
                # 结合绝对分数和相对排名
                combined = 0.6 * base_score + 0.4 * rank_score
                scores[speaker_id] = combined

            return scores
        except Exception as e:
            print(f"      [similarity_ranking] 错误: {e}")
            return self._compute_single_window(audio)

    def _compute_cascade(self, audio: np.ndarray) -> Dict[str, float]:
        """级联匹配：先用粗筛再用精匹配"""
        try:
            # 第一步：单窗口快速匹配，取top-10候选
            embedding = self.extractor.extract(audio)

            all_scores = []
            for speaker_id, profile in self.speaker_profiles.items():
                cos_sim = float(np.dot(embedding, profile.embedding) /
                               (np.linalg.norm(embedding) * np.linalg.norm(profile.embedding) + 1e-8))
                all_scores.append((speaker_id, cos_sim))

            # 取top-10
            all_scores.sort(key=lambda x: x[1], reverse=True)
            top_candidates = [s[0] for s in all_scores[:10]]

            # 第二步：对top候选进行多窗口验证
            windows = self.extractor.extract_multi_window(audio, n_windows=3, window_step_ratio=0.25)
            valid = [(emb, ts) for emb, ts, ok in windows if ok]

            if not valid:
                # 回退到单窗口结果
                return {s[0]: (s[1] + 1.0) / 2.0 for s in all_scores[:10]}

            fused_emb = np.mean([emb for emb, _ in valid], axis=0)
            fused_emb = fused_emb / (np.linalg.norm(fused_emb) + 1e-8)

            final_scores = {}
            for speaker_id in top_candidates:
                profile = self.speaker_profiles.get(speaker_id)
                if profile:
                    cos_sim = float(np.dot(fused_emb, profile.embedding) /
                                   (np.linalg.norm(profile.embedding) + 1e-8))
                    final_scores[speaker_id] = (cos_sim + 1.0) / 2.0

            return final_scores
        except Exception as e:
            print(f"      [cascade] 错误: {e}")
            return self._compute_single_window(audio)

    def _get_algorithm_func(self, mode: AlgorithmMode) -> Callable:
        """获取算法对应的函数"""
        algorithm_map = {
            AlgorithmMode.SINGLE_WINDOW: self._compute_single_window,
            AlgorithmMode.MULTI_WINDOW_VOTE: self._compute_multi_window,
            AlgorithmMode.CASCADE: self._compute_cascade,
            AlgorithmMode.WEIGHTED_AVG: self._compute_weighted_avg,
            AlgorithmMode.MEDIAN_FUSION: self._compute_median_fusion,
            AlgorithmMode.QUALITY_WEIGHTED: self._compute_quality_weighted,
            AlgorithmMode.SIMILARITY_RANKING: self._compute_similarity_ranking,
        }
        return algorithm_map.get(mode, self._compute_multi_window)

    def run_test(self, n_samples: int = 200, mode: AlgorithmMode = AlgorithmMode.MULTI_WINDOW_VOTE,
                 **kwargs) -> TestSummary:
        """
        运行批量测试

        Args:
            n_samples: 测试样本数量
            mode: 算法模式
            **kwargs: 传递给算法的额外参数（如 n_windows）
        """
        print(f"\n[5/5] 运行声纹识别测试（随机 {n_samples} 条）...")
        print(f"       算法模式: {mode.value}")
        print("-" * 60)

        if len(self.valid_test_samples) < n_samples:
            print(f"  警告: 只有 {len(self.valid_test_samples)} 条有效样本，使用全部")
            test_samples = self.valid_test_samples
        else:
            test_samples = _system_random.sample(self.valid_test_samples, n_samples)

        results: List[TestResult] = []
        uncertain_count = 0

        # 获取算法函数
        algorithm_func = self._get_algorithm_func(mode)
        algorithm_name = mode.value

        for idx, sample in enumerate(test_samples):
            file_name = sample["file"]
            user_id = sample["user_id"]
            duration = float(sample.get("length", 0))

            print(f"\n  [{idx+1}/{len(test_samples)}] 处理: {file_name}")

            audio_path = self._find_audio_file(file_name)
            if audio_path is None:
                print(f"    警告: 找不到音频文件，跳过")
                continue

            audio_data = self._load_wav_audio(audio_path)
            if audio_data is None:
                print(f"    警告: 加载音频失败，跳过")
                continue

            audio, _ = audio_data

            if len(audio) < 16000:
                print(f"    警告: 音频过短（{len(audio)/16000:.1f}s），跳过")
                continue

            # 调用识别算法
            try:
                scores = algorithm_func(audio, **kwargs)

                if not scores:
                    result = TestResult(
                        segment_id=idx + 1,
                        audio_path=file_name,
                        ground_truth_speaker_id=user_id,
                        recognized_speaker_id=None,
                        recognized_speaker_name=None,
                        recognized_score=0.0,
                        is_correct=False,
                        top3_includes_correct=False,
                        duration_sec=duration,
                        algorithm_used=algorithm_name,
                    )
                    results.append(result)
                    gt_name = self.speaker_id_to_name.get(user_id, user_id)
                    print(f"    ❌ 无识别结果 | GT: {user_id} ({gt_name})")
                    continue

                # 排序取top-k
                sorted_matches = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                top1_id, top1_score = sorted_matches[0]
                top3_ids = [s[0] for s in sorted_matches[:3]]

                is_correct = (top1_id == user_id)
                top3_includes_correct = user_id in top3_ids

                result = TestResult(
                    segment_id=idx + 1,
                    audio_path=file_name,
                    ground_truth_speaker_id=user_id,
                    recognized_speaker_id=top1_id,
                    recognized_speaker_name=self.speaker_id_to_name.get(top1_id, top1_id),
                    recognized_score=top1_score,
                    is_correct=is_correct,
                    top3_includes_correct=top3_includes_correct,
                    duration_sec=duration,
                    algorithm_used=algorithm_name,
                    all_scores=dict(sorted_matches[:10]),
                )
                results.append(result)

                status = "✓" if is_correct else "✗"
                top3_marker = "" if is_correct else ("*" if top3_includes_correct else "")
                gt_name = self.speaker_id_to_name.get(user_id, user_id)
                print(f"    {status} Top-1: {self.speaker_id_to_name.get(top1_id, top1_id)} | GT: {user_id} ({gt_name}) {top3_marker}")
                print(f"       得分: {top1_score:.4f} | 时长: {duration:.1f}s")

            except Exception as e:
                print(f"    ❌ 识别错误: {e}")
                result = TestResult(
                    segment_id=idx + 1,
                    audio_path=file_name,
                    ground_truth_speaker_id=user_id,
                    recognized_speaker_id=None,
                    recognized_speaker_name=None,
                    recognized_score=0.0,
                    is_correct=False,
                    top3_includes_correct=False,
                    duration_sec=duration,
                    algorithm_used=algorithm_name,
                )
                results.append(result)

        # 计算统计
        total = len(results)
        top1_correct = sum(1 for r in results if r.is_correct)
        top3_correct = sum(1 for r in results if r.top3_includes_correct)

        summary = TestSummary(
            total_segments=total,
            top1_correct=top1_correct,
            top1_accuracy=top1_correct / total if total > 0 else 0,
            top3_correct=top3_correct,
            top3_accuracy=top3_correct / total if total > 0 else 0,
            uncertain_count=uncertain_count,
            results=results,
            algorithm_name=algorithm_name,
        )

        return summary

    def run_comparison(self, n_samples: int = 100) -> Dict[str, TestSummary]:
        """
        运行多算法对比测试

        Args:
            n_samples: 每个算法的测试样本数

        Returns:
            各算法的测试结果
        """
        print("\n" + "=" * 60)
        print("算法对比测试")
        print("=" * 60)

        # 使用固定的随机样本
        if len(self.valid_test_samples) < n_samples:
            test_samples = self.valid_test_samples
        else:
            test_samples = _system_random.sample(self.valid_test_samples, n_samples)

        results = {}

        # 测试各算法
        algorithms = [
            AlgorithmMode.SINGLE_WINDOW,
            AlgorithmMode.MULTI_WINDOW_VOTE,
            AlgorithmMode.CASCADE,
            AlgorithmMode.WEIGHTED_AVG,
            AlgorithmMode.MEDIAN_FUSION,
            AlgorithmMode.QUALITY_WEIGHTED,
            AlgorithmMode.SIMILARITY_RANKING,
        ]

        for algo in algorithms:
            print(f"\n{'='*40}")
            print(f"测试算法: {algo.value}")
            print(f"{'='*40}")

            summary = self._run_test_for_samples(test_samples, algo)
            results[algo.value] = summary

            print(f"\n  Top-1 准确率: {summary.top1_accuracy * 100:.2f}%")
            print(f"  Top-3 准确率: {summary.top3_accuracy * 100:.2f}%")

        return results

    def _run_test_for_samples(self, test_samples: List, mode: AlgorithmMode) -> TestSummary:
        """对指定样本运行测试"""
        results = []
        algorithm_func = self._get_algorithm_func(mode)
        algorithm_name = mode.value

        for idx, sample in enumerate(test_samples):
            file_name = sample["file"]
            user_id = sample["user_id"]
            duration = float(sample.get("length", 0))

            if idx % 20 == 0:
                print(f"  进度: {idx+1}/{len(test_samples)}")

            audio_path = self._find_audio_file(file_name)
            if audio_path is None:
                continue

            audio_data = self._load_wav_audio(audio_path)
            if audio_data is None:
                continue

            audio, _ = audio_data

            if len(audio) < 16000:
                continue

            try:
                scores = algorithm_func(audio)

                if not scores:
                    continue

                sorted_matches = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                top1_id, top1_score = sorted_matches[0]
                top3_ids = [s[0] for s in sorted_matches[:3]]

                result = TestResult(
                    segment_id=idx + 1,
                    audio_path=file_name,
                    ground_truth_speaker_id=user_id,
                    recognized_speaker_id=top1_id,
                    recognized_speaker_name=self.speaker_id_to_name.get(top1_id, top1_id),
                    recognized_score=top1_score,
                    is_correct=(top1_id == user_id),
                    top3_includes_correct=(user_id in top3_ids),
                    duration_sec=duration,
                    algorithm_used=algorithm_name,
                )
                results.append(result)

            except Exception:
                continue

        total = len(results)
        top1_correct = sum(1 for r in results if r.is_correct)
        top3_correct = sum(1 for r in results if r.top3_includes_correct)

        return TestSummary(
            total_segments=total,
            top1_correct=top1_correct,
            top1_accuracy=top1_correct / total if total > 0 else 0,
            top3_correct=top3_correct,
            top3_accuracy=top3_correct / total if total > 0 else 0,
            uncertain_count=0,
            results=results,
            algorithm_name=algorithm_name,
        )

    def print_summary(self, summary: TestSummary):
        """打印测试结果汇总"""
        print("\n" + "=" * 60)
        print(f"测试结果汇总 - 算法: {summary.algorithm_name}")
        print("=" * 60)
        print(f"总测试样本数: {summary.total_segments}")
        print(f"Top-1 准确率: {summary.top1_correct}/{summary.total_segments} = {summary.top1_accuracy * 100:.2f}%")
        print(f"Top-3 准确率: {summary.top3_correct}/{summary.total_segments} = {summary.top3_accuracy * 100:.2f}%")

        # 按音频时长分组统计
        print("\n--- 按音频时长统计 ---")
        duration_buckets = [
            (0, 5, "0-5s"),
            (5, 10, "5-10s"),
            (10, 15, "10-15s"),
            (15, float("inf"), "15s+"),
        ]

        for low, high, label in duration_buckets:
            bucket_results = [r for r in summary.results if low <= r.duration_sec < high]
            if bucket_results:
                bucket_correct = sum(1 for r in bucket_results if r.is_correct)
                bucket_total = len(bucket_results)
                bucket_acc = bucket_correct / bucket_total * 100 if bucket_total > 0 else 0
                print(f"  {label}: {bucket_acc:.1f}% ({bucket_correct}/{bucket_total})")

        # 错误分析
        print("\n--- Top-1 错误样本分析（前10个）---")
        errors = [r for r in summary.results if not r.is_correct]
        if not errors:
            print("  无错误样本！")
        else:
            for r in errors[:10]:
                recognized_name = r.recognized_speaker_name or "无结果"
                gt_name = self.speaker_id_to_name.get(r.ground_truth_speaker_id, r.ground_truth_speaker_id)
                top3_marker = "*" if r.top3_includes_correct else ""
                print(f"  [{r.segment_id}] GT={r.ground_truth_speaker_id} ({gt_name}) | 识别={recognized_name} | 得分={r.recognized_score:.4f} | 时长={r.duration_sec:.1f}s {top3_marker}")

        print("=" * 60)

    def print_comparison(self, results: Dict[str, TestSummary]):
        """打印算法对比结果"""
        print("\n" + "=" * 60)
        print("算法对比结果")
        print("=" * 60)
        print(f"{'算法':<25} {'Top-1':<12} {'Top-3':<12} {'样本数':<8}")
        print("-" * 60)

        sorted_results = sorted(results.items(), key=lambda x: x[1].top1_accuracy, reverse=True)

        for algo_name, summary in sorted_results:
            print(f"{algo_name:<25} {summary.top1_accuracy*100:>6.2f}%     {summary.top3_accuracy*100:>6.2f}%     {summary.total_segments:>6}")

        print("=" * 60)

        # 最佳算法
        best = sorted_results[0]
        print(f"\n最佳算法: {best[0]} (Top-1: {best[1].top1_accuracy*100:.2f}%)")

    def save_results(self, summary: TestSummary, output_file: str = None):
        """保存测试结果到 JSON 文件"""
        if output_file is None:
            output_file = Path(__file__).parent / "data" / "speaker_test_results_ex.json"

        output_data = {
            "algorithm": summary.algorithm_name,
            "summary": {
                "total_segments": summary.total_segments,
                "top1_correct": summary.top1_correct,
                "top1_accuracy": summary.top1_accuracy,
                "top3_correct": summary.top3_correct,
                "top3_accuracy": summary.top3_accuracy,
            },
            "results": [
                {
                    "segment_id": r.segment_id,
                    "audio_file": r.audio_path,
                    "ground_truth_id": r.ground_truth_speaker_id,
                    "recognized": {
                        "speaker_id": r.recognized_speaker_id,
                        "speaker_name": r.recognized_speaker_name,
                        "score": r.recognized_score,
                    },
                    "is_correct": r.is_correct,
                    "top3_includes_correct": r.top3_includes_correct,
                    "duration_sec": r.duration_sec,
                    "all_scores": r.all_scores,
                }
                for r in summary.results
            ],
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        print(f"\n结果已保存到: {output_file}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="模式三EX：批量声纹识别算法测试")
    parser.add_argument("--n-samples", "-n", type=int, default=200,
                        help="测试样本数量（默认 200）")
    parser.add_argument("--mode", "-m", type=str, default="multi_window_vote",
                        choices=["single_window", "multi_window_vote", "cascade",
                                "weighted_avg", "median_fusion", "quality_weighted",
                                "similarity_ranking", "compare"],
                        help="算法模式（默认 multi_window_vote）")
    parser.add_argument("--compare", "-c", action="store_true",
                        help="运行多算法对比测试")
    parser.add_argument("--save", "-s", action="store_true",
                        help="保存结果到 JSON 文件")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（用于复现结果）")

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        print(f"随机种子设置为: {args.seed}")
    else:
        import time
        seed = int(time.time() * 1000) % (2**32)
        random.seed(seed)
        print(f"使用时间随机种子: {seed}")

    tester = EnhancedSpeakerRecognitionTester()
    tester.load_resources()

    if args.compare or args.mode == "compare":
        # 运行对比测试
        results = tester.run_comparison(n_samples=args.n_samples)
        tester.print_comparison(results)
    else:
        # 运行单个算法测试
        mode = AlgorithmMode(args.mode)
        summary = tester.run_test(n_samples=args.n_samples, mode=mode)
        tester.print_summary(summary)

        if args.save:
            tester.save_results(summary)


if __name__ == "__main__":
    main()
