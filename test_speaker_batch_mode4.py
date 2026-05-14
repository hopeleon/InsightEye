"""
模式四：批量声纹识别算法测试脚本
基于 test_speaker_batch.py 复制，用于测试说话人识别算法改进

功能：
1. 从 E:\primewords_md_2018_set1 随机抽取 N 条音频
2. 从已注册的 speaker_voiceprints.db 数据库加载声纹
3. 对每条音频进行识别，支持多种识别算法对比
4. 输出准确率统计

注意：本脚本只优化识别侧（不修改注册端逻辑）
"""

import sys
import os
import json
import random
import copy

# 使用系统级真随机数生成器（基于 os.urandom）
_system_random = random.SystemRandom()
import sqlite3
import wave
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Callable, Any
from enum import Enum

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.model_manager import SpeakerEmbeddingExtractor, ModelManager
from app.enhanced_speaker_recognition import (
    MultiSpeakerRegistry,
    SpeakerProfile,
    SpeakerMatch,
    SpeakerState,
)
from app.speaker_database import SpeakerDatabase
import numpy as np


class RecognitionMode(Enum):
    """支持的识别算法模式（识别侧优化）"""

    # ===== 基础对比基准 =====
    BASELINE_COSINE = "baseline_cosine"          # 基线：余弦相似度
    BASELINE_L2 = "baseline_l2"                # 基线：L2距离（归一化后）

    # ===== Embedding 预处理 =====
    PCA_WHITENING = "pca_whitening"             # PCA 白化变换
    CENTER_SUBTRACT = "center_subtract"          # 中心化（减去全局均值）
    NORMALIZE_BEFORE = "normalize_before"       # 提前做 L2 归一化
    DIMENSION_WEIGHTED = "dimension_weighted"   # 维度加权（高区分度维度权重高）

    # ===== 相似度度量 =====
    COSINE_PLUS_L2 = "cosine_plus_l2"          # 余弦 + L2 组合
    ANGLE_MAGNITUDE = "angle_magnitude"         # 角度 + 幅度分离
    MAHALANOBIS = "mahalanobis"                # 马氏距离（需校准）
    SOFTMAX_SCORE = "softmax_score"            # Softmax 归一化分数

    # ===== 匹配策略 =====
    TOPK_VERIFY = "topk_verify"                # Top-K 验证
    DIFF_THRESHOLD = "diff_threshold"          # 差异阈值拒绝
    CONFIDENCE_CALIBRATE = "confidence_calibrate"  # 置信度校准
    BAYESIAN_POSTERIOR = "bayesian_posterior"  # 贝叶斯后验

    # ===== 融合方法 =====
    MEDIAN_FUSION = "median_fusion"             # 中位数融合
    WEIGHTED_WINDOW = "weighted_window"         # 窗口一致性加权
    TRIMMED_MEAN = "trimmed_mean"               # 截断均值（去离群）
    GEOMETRIC_MEAN = "geometric_mean"           # 几何平均

    # ===== 多算法集成 =====
    ENSEMBLE_VOTE = "ensemble_vote"             # 多算法投票集成
    ENSEMBLE_WEIGHTED = "ensemble_weighted"     # 多算法加权集成


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
    algorithm_used: str = ""
    all_scores: Dict[str, float] = field(default_factory=dict)
    uncertainty_flag: bool = False  # 是否标记为不确定


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


@dataclass
class GlobalStats:
    """全局统计信息（用于 PCA 等算法）"""
    embeddings: List[np.ndarray] = field(default_factory=list)
    mean_embedding: Optional[np.ndarray] = None
    pca_matrix: Optional[np.ndarray] = None
    pca_fitted: bool = False
    dim_variance: Optional[np.ndarray] = None  # 各维度方差（用于维度加权）
    speaker_embedding_means: Dict[str, np.ndarray] = field(default_factory=dict)  # 各说话人的质心


class EnhancedSpeakerRecognitionTester:
    """
    增强版声纹识别测试器
    支持多种识别算法对比测试（识别侧优化）
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
        self.speaker_profiles: Dict[str, SpeakerProfile] = {}
        self.model_mgr = None
        self.extractor = None

        # 全局统计（用于 PCA、中心化等）
        self.global_stats = GlobalStats()

        # 预计算的说话人质心
        self._speaker_centroids: Dict[str, np.ndarray] = {}

    def load_resources(self):
        """加载测试资源和初始化模型"""
        print("=" * 60)
        print("模式四：批量声纹识别算法测试（识别侧优化）")
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

        # 预计算说话人质心（用于某些算法）
        self._compute_speaker_centroids()

        # 收集全局 embedding 用于 PCA 等
        self._collect_global_embeddings()

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
            self.registry.speakers[speaker_id] = profile
            self.registry.matching_engine.register_speaker(
                speaker_id=speaker_id,
                embedding=embedding,
            )

            loaded_count += 1
            if loaded_count % 50 == 0:
                print(f"    已加载 {loaded_count} 个说话人...")

    def _compute_speaker_centroids(self):
        """预计算每个说话人的 embedding 质心"""
        print("  预计算说话人质心...")
        from collections import defaultdict

        # 按说话人分组收集所有 embedding
        speaker_embeddings: Dict[str, List[np.ndarray]] = defaultdict(list)
        for profile in self.speaker_profiles.values():
            speaker_embeddings[profile.speaker_id].append(profile.embedding)

        # 计算每个说话人的质心
        for speaker_id, embeddings in speaker_embeddings.items():
            if len(embeddings) == 1:
                self._speaker_centroids[speaker_id] = embeddings[0].copy()
            else:
                stacked = np.array(embeddings)
                centroid = np.mean(stacked, axis=0)
                # L2 归一化
                centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
                self._speaker_centroids[speaker_id] = centroid

        print(f"  已计算 {len(self._speaker_centroids)} 个说话人质心")

    def _collect_global_embeddings(self):
        """收集所有说话人的 embedding 用于计算全局统计"""
        print("  收集全局 embedding 统计...")

        all_embeddings = []
        for profile in self.speaker_profiles.values():
            all_embeddings.append(profile.embedding.copy())

        if not all_embeddings:
            return

        stacked = np.array(all_embeddings)
        self.global_stats.embeddings = all_embeddings
        self.global_stats.mean_embedding = np.mean(stacked, axis=0)
        self.global_stats.dim_variance = np.var(stacked, axis=0)

        # 计算维度权重（方差大的维度区分度更高）
        max_var = np.max(self.global_stats.dim_variance) + 1e-8
        self.global_stats.dim_weights = self.global_stats.dim_variance / max_var

        print(f"  全局均值 embedding 计算完成，维度: {len(self.global_stats.mean_embedding)}")

    def _fit_pca(self, n_components: int = 128):
        """拟合 PCA 变换矩阵"""
        if self.global_stats.pca_fitted:
            return

        print("  拟合 PCA 变换矩阵...")
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import StandardScaler

        all_embeddings = self.global_stats.embeddings
        if len(all_embeddings) < 10:
            print("    样本不足，跳过 PCA")
            return

        stacked = np.array(all_embeddings)

        # 先标准化，再 PCA
        scaler = StandardScaler()
        scaled = scaler.fit_transform(stacked)

        n_comp = min(n_components, len(all_embeddings) - 1, stacked.shape[1])
        pca = PCA(n_components=n_comp)
        transformed = pca.fit_transform(scaled)

        self.global_stats.pca_matrix = pca.components_.T  # (n_features, n_components)
        self.global_stats.pca_scaler = scaler
        self.global_stats.pca_explained_var = pca.explained_variance_ratio_
        self.global_stats.pca_fitted = True

        print(f"  PCA 拟合完成，保留 {n_comp} 个主成分，解释方差: {sum(pca.explained_variance_ratio_)*100:.1f}%")

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

    def _extract_embedding(self, audio: np.ndarray) -> Optional[np.ndarray]:
        """提取单个 embedding"""
        try:
            emb = self.extractor.extract(audio)
            if emb is None or len(emb) == 0 or np.linalg.norm(emb) < 1e-6:
                return None
            return emb
        except Exception:
            return None

    def _extract_multi_window(self, audio: np.ndarray, n_windows: int = 3,
                              step_ratio: float = 0.25) -> List[Tuple[np.ndarray, float, bool]]:
        """提取多窗口 embedding"""
        try:
            return self.extractor.extract_multi_window(audio, n_windows, step_ratio)
        except Exception:
            return []

    def _compute_cosine(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """计算余弦相似度（归一化）"""
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 < 1e-8 or norm2 < 1e-8:
            return 0.5
        return float(np.dot(emb1, emb2) / (norm1 * norm2))

    def _compute_l2(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """计算 L2 距离（对归一化向量）"""
        # 先归一化
        n1 = emb1 / (np.linalg.norm(emb1) + 1e-8)
        n2 = emb2 / (np.linalg.norm(emb2) + 1e-8)
        dist = np.linalg.norm(n1 - n2)
        # 转为相似度分数（0-1）
        return 1.0 / (1.0 + dist)

    def _compute_scores_baseline(self, test_emb: np.ndarray) -> Dict[str, float]:
        """基线：余弦相似度"""
        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            scores[speaker_id] = self._compute_cosine(test_emb, profile.embedding)
        return scores

    def _compute_scores_baseline_l2(self, test_emb: np.ndarray) -> Dict[str, float]:
        """基线：L2 距离（归一化后）"""
        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            scores[speaker_id] = self._compute_l2(test_emb, profile.embedding)
        return scores

    def _compute_scores_pca_whitening(self, test_emb: np.ndarray) -> Dict[str, float]:
        """PCA 白化变换"""
        self._fit_pca()

        if not self.global_stats.pca_fitted:
            return self._compute_scores_baseline(test_emb)

        try:
            # 变换测试 embedding
            scaled = self.global_stats.pca_scaler.transform(test_emb.reshape(1, -1))
            transformed = np.dot(scaled, self.global_stats.pca_matrix)

            scores = {}
            for speaker_id, profile in self.speaker_profiles.items():
                # 变换注册 embedding
                reg_scaled = self.global_stats.pca_scaler.transform(profile.embedding.reshape(1, -1))
                reg_transformed = np.dot(reg_scaled, self.global_stats.pca_matrix)
                scores[speaker_id] = self._compute_cosine(transformed[0], reg_transformed[0])

            return scores
        except Exception:
            return self._compute_scores_baseline(test_emb)

    def _compute_scores_center_subtract(self, test_emb: np.ndarray) -> Dict[str, float]:
        """中心化：减去全局均值"""
        if self.global_stats.mean_embedding is None:
            return self._compute_scores_baseline(test_emb)

        # 中心化
        test_centered = test_emb - self.global_stats.mean_embedding
        test_centered = test_centered / (np.linalg.norm(test_centered) + 1e-8)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            reg_centered = profile.embedding - self.global_stats.mean_embedding
            reg_centered = reg_centered / (np.linalg.norm(reg_centered) + 1e-8)
            scores[speaker_id] = self._compute_cosine(test_centered, reg_centered)

        return scores

    def _compute_scores_normalize_before(self, test_emb: np.ndarray) -> Dict[str, float]:
        """提前做 L2 归一化"""
        test_norm = test_emb / (np.linalg.norm(test_emb) + 1e-8)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            reg_norm = profile.embedding / (np.linalg.norm(profile.embedding) + 1e-8)
            scores[speaker_id] = self._compute_cosine(test_norm, reg_norm)

        return scores

    def _compute_scores_dimension_weighted(self, test_emb: np.ndarray) -> Dict[str, float]:
        """维度加权：高区分度维度权重更高"""
        if self.global_stats.dim_weights is None:
            return self._compute_scores_baseline(test_emb)

        # 加权 embedding
        weights = self.global_stats.dim_weights
        test_weighted = test_emb * weights
        test_weighted = test_weighted / (np.linalg.norm(test_weighted) + 1e-8)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            reg_weighted = profile.embedding * weights
            reg_weighted = reg_weighted / (np.linalg.norm(reg_weighted) + 1e-8)
            scores[speaker_id] = self._compute_cosine(test_weighted, reg_weighted)

        return scores

    def _compute_scores_cosine_plus_l2(self, test_emb: np.ndarray) -> Dict[str, float]:
        """余弦 + L2 组合"""
        cos_scores = self._compute_scores_baseline(test_emb)
        l2_scores = self._compute_scores_baseline_l2(test_emb)

        scores = {}
        for speaker_id in cos_scores:
            # 组合：0.6 * cosine + 0.4 * l2
            scores[speaker_id] = 0.6 * cos_scores[speaker_id] + 0.4 * l2_scores[speaker_id]

        return scores

    def _compute_scores_angle_magnitude(self, test_emb: np.ndarray) -> Dict[str, float]:
        """角度 + 幅度分离"""
        test_norm = test_emb / (np.linalg.norm(test_emb) + 1e-8)
        test_mag = np.linalg.norm(test_emb)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            reg_norm = profile.embedding / (np.linalg.norm(profile.embedding) + 1e-8)
            reg_mag = np.linalg.norm(profile.embedding)

            # 角度相似度
            angle_sim = self._compute_cosine(test_norm, reg_norm)

            # 幅度相似度（用高斯核）
            mag_diff = abs(test_mag - reg_mag)
            mag_sim = np.exp(-mag_diff ** 2 / 0.1)

            # 组合
            scores[speaker_id] = 0.85 * angle_sim + 0.15 * mag_sim

        return scores

    def _compute_scores_mahalanobis(self, test_emb: np.ndarray) -> Dict[str, float]:
        """马氏距离（简化为对角协方差）"""
        if self.global_stats.dim_variance is None:
            return self._compute_scores_baseline(test_emb)

        var = self.global_stats.dim_variance + 1e-6

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            diff = test_emb - profile.embedding
            # 马氏距离的简化形式
            mahal_sq = np.sum(diff ** 2 / var)
            # 转为相似度
            scores[speaker_id] = 1.0 / (1.0 + mahal_sq ** 0.5)

        return scores

    def _compute_scores_softmax(self, test_emb: np.ndarray, temperature: float = 0.1) -> Dict[str, float]:
        """Softmax 归一化分数"""
        raw_scores = self._compute_scores_baseline(test_emb)

        if not raw_scores:
            return {}

        speakers = list(raw_scores.keys())
        values = np.array(list(raw_scores.values()))

        # Softmax
        exp_values = np.exp((values - np.max(values)) / temperature)
        softmax_values = exp_values / np.sum(exp_values)

        return {sp: float(sv) for sp, sv in zip(speakers, softmax_values)}

    def _compute_scores_topk_verify(self, test_emb: np.ndarray, test_windows: List,
                                   top_k: int = 5) -> Tuple[Dict[str, float], bool]:
        """Top-K 验证：先用余弦筛选 top-k，再用多窗口验证"""
        raw_scores = self._compute_scores_baseline(test_emb)

        if not raw_scores:
            return {}, False

        # 取 top-k 候选
        sorted_speakers = sorted(raw_scores.items(), key=lambda x: x[1], reverse=True)
        top_candidates = [s[0] for s in sorted_speakers[:top_k]]

        if not test_windows:
            return {s: raw_scores[s] for s in top_candidates}, False

        # 多窗口验证
        window_scores: Dict[str, List[float]] = {sp: [] for sp in top_candidates}

        for emb, _, ok in test_windows:
            if not ok:
                continue
            for speaker_id in top_candidates:
                profile = self.speaker_profiles.get(speaker_id)
                if profile:
                    score = self._compute_cosine(emb, profile.embedding)
                    window_scores[speaker_id].append(score)

        # 平均窗口分数
        final_scores = {}
        for speaker_id, scores in window_scores.items():
            if scores:
                final_scores[speaker_id] = np.mean(scores)
            else:
                final_scores[speaker_id] = raw_scores.get(speaker_id, 0.5)

        # 检查一致性
        uncertain = False
        if len(window_scores) >= 2:
            score_values = [np.mean(scores) for scores in window_scores.values() if scores]
            if len(score_values) >= 2:
                sorted_vals = sorted(score_values, reverse=True)
                if sorted_vals[0] - sorted_vals[1] < 0.02:  # 差距太小
                    uncertain = True

        return final_scores, uncertain

    def _compute_scores_diff_threshold(self, test_emb: np.ndarray,
                                       threshold: float = 0.05) -> Tuple[Dict[str, float], bool]:
        """差异阈值拒绝：top1-top2 差距小时标记不确定"""
        raw_scores = self._compute_scores_baseline(test_emb)

        if not raw_scores:
            return {}, False

        sorted_scores = sorted(raw_scores.values(), reverse=True)
        if len(sorted_scores) >= 2:
            diff = sorted_scores[0] - sorted_scores[1]
            uncertain = diff < threshold
        else:
            uncertain = False

        return raw_scores, uncertain

    def _compute_scores_confidence_calibrate(self, test_emb: np.ndarray) -> Dict[str, float]:
        """置信度校准：sigmoid 变换"""
        raw_scores = self._compute_scores_baseline(test_emb)

        if not raw_scores:
            return {}

        # 找到 max 和 min
        values = np.array(list(raw_scores.values()))
        v_max = np.max(values)
        v_min = np.min(values)

        # Sigmoid 校准
        scale = 10.0  # 缩放因子
        centered = values - (v_max + v_min) / 2
        calibrated = 1.0 / (1.0 + np.exp(-centered * scale))

        speakers = list(raw_scores.keys())
        return {sp: float(cv) for sp, cv in zip(speakers, calibrated)}

    def _compute_scores_bayesian(self, test_emb: np.ndarray,
                                 prior_strength: float = 0.1) -> Dict[str, float]:
        """贝叶斯后验：结合先验和似然"""
        likelihood = self._compute_scores_baseline(test_emb)

        if not likelihood:
            return {}

        # 统一先验（每个说话人等概率）
        speakers = list(likelihood.keys())
        prior = {sp: 1.0 / len(speakers) for sp in speakers}

        # 后验 ∝ 似然 * 先验^alpha
        posterior = {}
        for sp in speakers:
            posterior[sp] = likelihood[sp] * (prior[sp] ** prior_strength)

        # 归一化
        total = sum(posterior.values())
        if total > 0:
            posterior = {sp: p / total for sp, p in posterior.items()}

        return posterior

    def _compute_scores_median_fusion(self, audio: np.ndarray) -> Dict[str, float]:
        """中位数融合：对多窗口 embedding 取中位数"""
        windows = self._extract_multi_window(audio)
        valid = [(emb, ts) for emb, ts, ok in windows if ok]

        if not valid:
            emb = self._extract_embedding(audio)
            if emb is None:
                return {}
            return self._compute_scores_baseline(emb)

        embeddings = [emb for emb, _ in valid]
        stacked = np.array(embeddings)

        if len(embeddings) == 1:
            fused = embeddings[0]
        else:
            fused = np.median(stacked, axis=0)

        fused = fused / (np.linalg.norm(fused) + 1e-8)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            scores[speaker_id] = self._compute_cosine(fused, profile.embedding)

        return scores

    def _compute_scores_weighted_window(self, audio: np.ndarray) -> Dict[str, float]:
        """窗口一致性加权：按窗口与均值的相似度加权"""
        windows = self._extract_multi_window(audio)
        valid = [(emb, ts) for emb, ts, ok in windows if ok]

        if not valid:
            emb = self._extract_embedding(audio)
            if emb is None:
                return {}
            return self._compute_scores_baseline(emb)

        embeddings = [emb for emb, _ in valid]

        # 计算均值
        mean_emb = np.mean(embeddings, axis=0)
        mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-8)

        # 计算每个窗口的权重（与均值的相似度）
        weights = []
        for emb in embeddings:
            emb_norm = emb / (np.linalg.norm(emb) + 1e-8)
            sim = self._compute_cosine(emb_norm, mean_emb)
            weights.append(max(sim, 0.5))  # 保证最小权重

        # 加权融合
        total_weight = sum(weights)
        fused = np.zeros_like(embeddings[0])
        for emb, w in zip(embeddings, weights):
            fused += emb * (w / total_weight)

        fused = fused / (np.linalg.norm(fused) + 1e-8)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            scores[speaker_id] = self._compute_cosine(fused, profile.embedding)

        return scores

    def _compute_scores_trimmed_mean(self, audio: np.ndarray, trim_ratio: float = 0.2) -> Dict[str, float]:
        """截断均值：去掉最高和最低的离群窗口"""
        windows = self._extract_multi_window(audio)
        valid = [(emb, ts) for emb, ts, ok in windows if ok]

        if not valid:
            emb = self._extract_embedding(audio)
            if emb is None:
                return {}
            return self._compute_scores_baseline(emb)

        if len(valid) < 3:
            return self._compute_scores_median_fusion(audio)

        embeddings = [emb for emb, _ in valid]

        # 对每个维度计算截断均值
        stacked = np.array(embeddings)  # (n, dim)
        n = len(embeddings)
        trim_count = max(1, int(n * trim_ratio))

        # 按值排序后去掉最高和最低
        sorted_idx = np.argsort(stacked, axis=0)
        trimmed = np.delete(stacked, np.concatenate([
            sorted_idx[:trim_count, :],
            sorted_idx[-trim_count:, :]
        ]), axis=0)

        if len(trimmed) == 0:
            fused = np.mean(stacked, axis=0)
        else:
            fused = np.mean(trimmed, axis=0)

        fused = fused / (np.linalg.norm(fused) + 1e-8)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            scores[speaker_id] = self._compute_cosine(fused, profile.embedding)

        return scores

    def _compute_scores_geometric_mean(self, audio: np.ndarray) -> Dict[str, float]:
        """几何平均：对 embedding 的每个维度取几何平均"""
        windows = self._extract_multi_window(audio)
        valid = [(emb, ts) for emb, ts, ok in windows if ok]

        if not valid:
            emb = self._extract_embedding(audio)
            if emb is None:
                return {}
            return self._compute_scores_baseline(emb)

        embeddings = [emb for emb, _ in valid]
        stacked = np.array(embeddings)

        # 几何平均 = exp(mean(log(x)))
        # 避免 log(0)
        eps = 1e-10
        stacked_pos = np.abs(stacked) + eps
        log_mean = np.mean(np.log(stacked_pos), axis=0)
        fused = np.exp(log_mean)

        # 处理符号（如果原值有正有负，取算术平均）
        sign = np.sign(np.mean(stacked, axis=0))
        fused = fused * sign

        fused = fused / (np.linalg.norm(fused) + 1e-8)

        scores = {}
        for speaker_id, profile in self.speaker_profiles.items():
            scores[speaker_id] = self._compute_cosine(fused, profile.embedding)

        return scores

    def _compute_scores_ensemble(self, audio: np.ndarray, mode: str = "vote") -> Dict[str, float]:
        """多算法集成"""
        # 收集多个算法的结果
        algorithms = [
            self._compute_scores_baseline,
            lambda emb: self._compute_scores_cosine_plus_l2(emb),
            lambda emb: self._compute_scores_center_subtract(emb),
            lambda emb: self._compute_scores_normalize_before(emb),
        ]

        emb = self._extract_embedding(audio)
        if emb is None:
            return {}

        all_scores = []
        for algo in algorithms:
            scores = algo(emb)
            if scores:
                all_scores.append(scores)

        if not all_scores:
            return {}

        # 投票模式：每个算法投一票
        if mode == "vote":
            votes: Dict[str, float] = {sp: 0.0 for sp in self.speaker_id_set}

            for scores in all_scores:
                if scores:
                    sorted_sp = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    for rank, (sp, _) in enumerate(sorted_sp):
                        # 排名越高得分越高
                        votes[sp] += 1.0 / (1.0 + rank)

            # 归一化
            total = sum(votes.values())
            if total > 0:
                votes = {sp: v / total for sp, v in votes.items()}

            return votes

        # 加权平均模式
        else:
            # 对齐所有候选
            all_speakers = set()
            for scores in all_scores:
                all_speakers.update(scores.keys())

            aligned_scores = []
            for scores in all_scores:
                aligned = np.array([scores.get(sp, 0.0) for sp in all_speakers])
                aligned_scores.append(aligned)

            # 加权平均
            avg_scores = np.mean(aligned_scores, axis=0)

            return {sp: float(score) for sp, score in zip(all_speakers, avg_scores)}

    def _get_algorithm_func(self, mode: RecognitionMode) -> Callable:
        """获取算法对应的函数"""
        algorithm_map = {
            RecognitionMode.BASELINE_COSINE: (self._compute_scores_baseline, False),
            RecognitionMode.BASELINE_L2: (self._compute_scores_baseline_l2, False),
            RecognitionMode.PCA_WHITENING: (self._compute_scores_pca_whitening, False),
            RecognitionMode.CENTER_SUBTRACT: (self._compute_scores_center_subtract, False),
            RecognitionMode.NORMALIZE_BEFORE: (self._compute_scores_normalize_before, False),
            RecognitionMode.DIMENSION_WEIGHTED: (self._compute_scores_dimension_weighted, False),
            RecognitionMode.COSINE_PLUS_L2: (self._compute_scores_cosine_plus_l2, False),
            RecognitionMode.ANGLE_MAGNITUDE: (self._compute_scores_angle_magnitude, False),
            RecognitionMode.MAHALANOBIS: (self._compute_scores_mahalanobis, False),
            RecognitionMode.SOFTMAX_SCORE: (self._compute_scores_softmax, False),
            RecognitionMode.TOPK_VERIFY: (self._compute_scores_topk_verify, True),
            RecognitionMode.DIFF_THRESHOLD: (self._compute_scores_diff_threshold, True),
            RecognitionMode.CONFIDENCE_CALIBRATE: (self._compute_scores_confidence_calibrate, False),
            RecognitionMode.BAYESIAN_POSTERIOR: (self._compute_scores_bayesian, False),
            RecognitionMode.MEDIAN_FUSION: (self._compute_scores_median_fusion, False),
            RecognitionMode.WEIGHTED_WINDOW: (self._compute_scores_weighted_window, False),
            RecognitionMode.TRIMMED_MEAN: (self._compute_scores_trimmed_mean, False),
            RecognitionMode.GEOMETRIC_MEAN: (self._compute_scores_geometric_mean, False),
            RecognitionMode.ENSEMBLE_VOTE: (lambda emb: self._compute_scores_ensemble(emb, "vote"), False),
            RecognitionMode.ENSEMBLE_WEIGHTED: (lambda emb: self._compute_scores_ensemble(emb, "weighted"), False),
        }
        result = algorithm_map.get(mode, (self._compute_scores_baseline, False))
        return result

    def _run_single_algorithm(self, audio: np.ndarray, mode: RecognitionMode):
        """运行单个算法，返回分数和不确定标记"""
        func, has_uncertainty = self._get_algorithm_func(mode)

        if mode in [RecognitionMode.MEDIAN_FUSION, RecognitionMode.WEIGHTED_WINDOW,
                   RecognitionMode.TRIMMED_MEAN, RecognitionMode.GEOMETRIC_MEAN,
                   RecognitionMode.ENSEMBLE_VOTE, RecognitionMode.ENSEMBLE_WEIGHTED]:
            # 这些算法需要音频
            scores = func(audio)
            return scores, False, []
        elif has_uncertainty:
            emb = self._extract_embedding(audio)
            if emb is None:
                return {}, False, []
            windows = self._extract_multi_window(audio)
            if mode == RecognitionMode.TOPK_VERIFY:
                scores, uncertain = self._compute_scores_topk_verify(emb, windows)
            else:
                scores, uncertain = func(emb)
            return scores, uncertain, windows
        else:
            emb = self._extract_embedding(audio)
            if emb is None:
                return {}, False, []
            scores = func(emb)
            return scores, False, []

    def run_test(self, n_samples: int = 200, mode: RecognitionMode = RecognitionMode.BASELINE_COSINE) -> TestSummary:
        """运行单个算法测试"""
        print(f"\n[5/5] 运行声纹识别测试（随机 {n_samples} 条）...")
        print(f"       算法模式: {mode.value}")
        print("-" * 60)

        if len(self.valid_test_samples) < n_samples:
            test_samples = self.valid_test_samples
        else:
            test_samples = _system_random.sample(self.valid_test_samples, n_samples)

        results: List[TestResult] = []
        uncertain_count = 0
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
                scores, uncertain, _ = self._run_single_algorithm(audio, mode)

                if not scores:
                    continue

                sorted_matches = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                top1_id, top1_score = sorted_matches[0]
                top3_ids = [s[0] for s in sorted_matches[:3]]

                is_correct = (top1_id == user_id)
                top3_includes_correct = user_id in top3_ids

                if uncertain:
                    uncertain_count += 1

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
                    uncertainty_flag=uncertain,
                )
                results.append(result)

            except Exception as e:
                print(f"    ❌ 错误: {e}")
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
            uncertain_count=uncertain_count,
            results=results,
            algorithm_name=algorithm_name,
        )

    def run_comparison(self, n_samples: int = 100) -> Dict[str, TestSummary]:
        """运行多算法对比测试"""
        print("\n" + "=" * 60)
        print("算法对比测试")
        print("=" * 60)

        if len(self.valid_test_samples) < n_samples:
            test_samples = self.valid_test_samples
        else:
            test_samples = _system_random.sample(self.valid_test_samples, n_samples)

        results = {}

        # 测试所有算法
        algorithms = list(RecognitionMode)

        for algo in algorithms:
            print(f"\n{'='*40}")
            print(f"测试算法: {algo.value}")
            print(f"{'='*40}")

            # 收集测试样本的音频
            sample_data = []
            valid_indices = []

            for idx, sample in enumerate(test_samples):
                file_name = sample["file"]
                audio_path = self._find_audio_file(file_name)
                if audio_path is None:
                    continue

                audio_data = self._load_wav_audio(audio_path)
                if audio_data is None:
                    continue

                audio, _ = audio_data
                if len(audio) < 16000:
                    continue

                sample_data.append((idx, sample, audio))
                valid_indices.append(idx)

            if not sample_data:
                print("  无有效样本，跳过")
                continue

            # 运行算法
            algo_results = []
            uncertain_count = 0

            for idx, sample, audio in sample_data:
                user_id = sample["user_id"]
                duration = float(sample.get("length", 0))

                try:
                    scores, uncertain, _ = self._run_single_algorithm(audio, algo)

                    if not scores:
                        continue

                    sorted_matches = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    top1_id, top1_score = sorted_matches[0]
                    top3_ids = [s[0] for s in sorted_matches[:3]]

                    is_correct = (top1_id == user_id)
                    top3_includes_correct = user_id in top3_ids

                    if uncertain:
                        uncertain_count += 1

                    result = TestResult(
                        segment_id=idx + 1,
                        audio_path=sample["file"],
                        ground_truth_speaker_id=user_id,
                        recognized_speaker_id=top1_id,
                        recognized_speaker_name=self.speaker_id_to_name.get(top1_id, top1_id),
                        recognized_score=top1_score,
                        is_correct=is_correct,
                        top3_includes_correct=top3_includes_correct,
                        duration_sec=duration,
                        algorithm_used=algo.value,
                        all_scores=dict(sorted_matches[:10]),
                        uncertainty_flag=uncertain,
                    )
                    algo_results.append(result)

                except Exception:
                    continue

            total = len(algo_results)
            top1_correct = sum(1 for r in algo_results if r.is_correct)
            top3_correct = sum(1 for r in algo_results if r.top3_includes_correct)

            summary = TestSummary(
                total_segments=total,
                top1_correct=top1_correct,
                top1_accuracy=top1_correct / total if total > 0 else 0,
                top3_correct=top3_correct,
                top3_accuracy=top3_correct / total if total > 0 else 0,
                uncertain_count=uncertain_count,
                results=algo_results,
                algorithm_name=algo.value,
            )
            results[algo.value] = summary

            print(f"\n  Top-1 准确率: {summary.top1_accuracy * 100:.2f}%")
            print(f"  Top-3 准确率: {summary.top3_accuracy * 100:.2f}%")

        return results

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
                uncertain_marker = "?" if r.uncertainty_flag else ""
                print(f"  [{r.segment_id}] GT={r.ground_truth_speaker_id} ({gt_name}) | 识别={recognized_name} | 得分={r.recognized_score:.4f} | 时长={r.duration_sec:.1f}s {top3_marker}{uncertain_marker}")

        print("=" * 60)

    def print_comparison(self, results: Dict[str, TestSummary]):
        """打印算法对比结果"""
        print("\n" + "=" * 70)
        print("算法对比结果（按 Top-1 准确率排序）")
        print("=" * 70)
        print(f"{'算法':<25} {'Top-1':<12} {'Top-3':<12} {'不确定':<10} {'样本数':<8}")
        print("-" * 70)

        sorted_results = sorted(results.items(), key=lambda x: x[1].top1_accuracy, reverse=True)

        for algo_name, summary in sorted_results:
            print(f"{algo_name:<25} {summary.top1_accuracy*100:>6.2f}%     {summary.top3_accuracy*100:>6.2f}%     {summary.uncertain_count:>6}     {summary.total_segments:>6}")

        print("=" * 70)

        # 最佳算法
        best = sorted_results[0]
        worst = sorted_results[-1]
        print(f"\n最佳算法: {best[0]} (Top-1: {best[1].top1_accuracy*100:.2f}%)")
        print(f"最差算法: {worst[0]} (Top-1: {worst[1].top1_accuracy*100:.2f}%)")
        print(f"提升空间: {(best[1].top1_accuracy - worst[1].top1_accuracy)*100:.2f}%")

    def run_sample_detail(self, n_samples: int = 20,
                          algorithms: List[RecognitionMode] = None,
                          output_file: str = None):
        """
        详细展示每个样本在多个算法下的得分对比

        Args:
            n_samples: 展示的样本数量
            algorithms: 要对比的算法列表，默认前几个高分算法
            output_file: 保存路径
        """
        if algorithms is None:
            # 默认对比 Top-5 算法
            algorithms = [
                RecognitionMode.BASELINE_COSINE,
                RecognitionMode.PCA_WHITENING,
                RecognitionMode.CENTER_SUBTRACT,
                RecognitionMode.MAHALANOBIS,
                RecognitionMode.BASELINE_L2,
            ]

        print("\n" + "=" * 80)
        print("样本级别详细得分对比")
        print("=" * 80)

        # 准备测试样本
        if len(self.valid_test_samples) < n_samples:
            test_samples = self.valid_test_samples
        else:
            test_samples = _system_random.sample(self.valid_test_samples, n_samples)

        # 预加载所有样本的音频
        print("\n加载测试样本音频...")
        sample_data = []
        for idx, sample in enumerate(test_samples):
            file_name = sample["file"]
            audio_path = self._find_audio_file(file_name)
            if audio_path is None:
                continue

            audio_data = self._load_wav_audio(audio_path)
            if audio_data is None:
                continue

            audio, _ = audio_data
            if len(audio) < 16000:
                continue

            sample_data.append((idx, sample, audio))

        if not sample_data:
            print("  无有效样本")
            return

        print(f"  成功加载 {len(sample_data)} 个有效样本\n")

        # 算法简称映射
        algo_short = {
            "baseline_cosine": "COS",
            "baseline_l2": "L2",
            "pca_whitening": "PCA",
            "center_subtract": "CTR",
            "mahalanobis": "MAH",
            "normalize_before": "NRM",
            "dimension_weighted": "DIM",
            "cosine_plus_l2": "C+L",
            "angle_magnitude": "ANG",
            "softmax_score": "SFT",
            "diff_threshold": "DIF",
            "confidence_calibrate": "CON",
            "bayesian_posterior": "BAY",
        }

        # 收集所有样本的各算法结果
        all_results = []

        for idx, sample, audio in sample_data:
            user_id = sample["user_id"]
            gt_name = self.speaker_id_to_name.get(user_id, user_id)
            duration = float(sample.get("length", 0))

            sample_result = {
                "idx": idx,
                "file": sample["file"],
                "gt_id": user_id,
                "gt_name": gt_name,
                "duration": duration,
                "algorithms": {},
                "correct_algorithms": [],
                "top1_algorithms": [],
            }

            # 运行每个算法
            for algo in algorithms:
                try:
                    scores, uncertain, _ = self._run_single_algorithm(audio, algo)

                    if not scores:
                        sample_result["algorithms"][algo.value] = None
                        continue

                    sorted_matches = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                    top1_id, top1_score = sorted_matches[0]
                    top3_ids = [s[0] for s in sorted_matches[:3]]

                    is_correct = (top1_id == user_id)
                    top3_includes = user_id in top3_ids

                    sample_result["algorithms"][algo.value] = {
                        "top1_id": top1_id,
                        "top1_score": top1_score,
                        "top3_ids": top3_ids,
                        "is_correct": is_correct,
                        "top3_includes": top3_includes,
                        "all_sorted": sorted_matches[:5],
                    }

                    if is_correct:
                        sample_result["correct_algorithms"].append(algo.value)
                    sample_result["top1_algorithms"].append(top1_id)

                except Exception as e:
                    sample_result["algorithms"][algo.value] = None

            all_results.append(sample_result)

        # 打印每个样本的详细对比
        print("-" * 80)
        for sr in all_results:
            gt = f"{sr['gt_name']}({sr['gt_id']})"

            # 检查是否所有算法都正确
            all_correct = len(sr["correct_algorithms"]) == len(algorithms)
            any_correct = len(sr["correct_algorithms"]) > 0
            none_correct = len(sr["correct_algorithms"]) == 0

            if all_correct:
                status = "✓ ALL"
            elif any_correct:
                status = f"✓ {len(sr['correct_algorithms'])}/{len(algorithms)}"
            else:
                status = f"✗ ALL WRONG"

            print(f"\n[{sr['idx']}] {sr['file']}")
            print(f"    GT: {gt}  时长: {sr['duration']:.1f}s  状态: {status}")
            print(f"    {'算法':<18} {'Top-1 识别':<25} {'得分':<10} {'Top-3'}")
            print(f"    {'-'*18} {'-'*25} {'-'*10} {'-'*20}")

            for algo in algorithms:
                algo_name = algo.value
                short = algo_short.get(algo_name, algo_name[:6])
                result = sr["algorithms"].get(algo_name)

                if result is None:
                    print(f"    {short:<18} {'ERROR':<25}")
                    continue

                top1_id = result["top1_id"]
                top1_name = self.speaker_id_to_name.get(top1_id, top1_id)
                score = result["top1_score"]
                top3 = result["top3_ids"]

                mark = "✓" if result["is_correct"] else "✗"
                top3_str = ", ".join([
                    (self.speaker_id_to_name.get(s, s) if s != sr["gt_id"] else f"[{self.speaker_id_to_name.get(s, s)}]")
                    for s in top3[:3]
                ])

                print(f"    {short:<18} {mark} {top1_name}({top1_id})  {score:.4f}   {top3_str}")

        print("\n" + "=" * 80)

        # 汇总：哪些样本算法间有分歧
        print("\n【分歧样本分析】- 不同算法给出不同结果的样本")
        print("-" * 80)

        disagree_samples = []
        for sr in all_results:
            unique_top1 = set()
            for algo in algorithms:
                result = sr["algorithms"].get(algo.value)
                if result and result["top1_id"]:
                    unique_top1.add(result["top1_id"])

            if len(unique_top1) > 1:
                disagree_samples.append(sr)

        if not disagree_samples:
            print("  所有样本各算法结果一致！")
        else:
            print(f"  发现 {len(disagree_samples)} 个分歧样本:\n")
            for sr in disagree_samples:
                gt = f"{sr['gt_name']}({sr['gt_id']})"
                print(f"  [{sr['idx']}] {sr['file']}  GT={gt}")

                for algo in algorithms:
                    result = sr["algorithms"].get(algo.value)
                    if result:
                        short = algo_short.get(algo.value, algo.value[:6])
                        top1_id = result["top1_id"]
                        top1_name = self.speaker_id_to_name.get(top1_id, top1_id)
                        score = result["top1_score"]
                        mark = "✓" if result["is_correct"] else "✗"
                        print(f"    {short}: {mark} {top1_name} {score:.4f}")
                print()

        # 保存到文件
        if output_file:
            output = {
                "algorithms": [a.value for a in algorithms],
                "summary": {
                    "total_samples": len(all_results),
                    "all_correct_count": sum(1 for r in all_results if len(r["correct_algorithms"]) == len(algorithms)),
                    "any_correct_count": sum(1 for r in all_results if len(r["correct_algorithms"]) > 0),
                    "all_wrong_count": sum(1 for r in all_results if len(r["correct_algorithms"]) == 0),
                    "disagree_count": len(disagree_samples),
                },
                "samples": all_results,
            }
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            print(f"详细结果已保存到: {output_file}")

    def save_results(self, summary: TestSummary, output_file: str = None):
        """保存测试结果到 JSON 文件"""
        if output_file is None:
            output_file = Path(__file__).parent / "data" / "speaker_test_results_mode4.json"

        output_data = {
            "algorithm": summary.algorithm_name,
            "summary": {
                "total_segments": summary.total_segments,
                "top1_correct": summary.top1_correct,
                "top1_accuracy": summary.top1_accuracy,
                "top3_correct": summary.top3_correct,
                "top3_accuracy": summary.top3_accuracy,
                "uncertain_count": summary.uncertain_count,
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
                    "uncertain": r.uncertainty_flag,
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

    parser = argparse.ArgumentParser(description="模式四：批量声纹识别算法测试（识别侧优化）")

    # 获取所有算法名称
    all_algo_names = [algo.value for algo in RecognitionMode]

    parser.add_argument("--n-samples", "-n", type=int, default=200,
                        help="测试样本数量（默认 200）")
    parser.add_argument("--mode", "-m", type=str, default="baseline_cosine",
                        choices=all_algo_names + ["compare", "all"],
                        help="算法模式")
    parser.add_argument("--compare", "-c", action="store_true",
                        help="运行多算法对比测试")
    parser.add_argument("--save", "-s", action="store_true",
                        help="保存结果到 JSON 文件")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（用于复现结果）")
    parser.add_argument("--detail", "-d", type=int, default=0,
                        help="样本级别详细对比，展示 N 个样本的各算法得分（默认关闭，设为 >0 启用）")
    parser.add_argument("--detail-algos", type=str, default=None,
                        help="详细对比使用的算法，逗号分隔，默认: baseline_cosine,pca_whitening,center_subtract,mahalanobis,baseline_l2")
    parser.add_argument("--detail-output", type=str, default=None,
                        help="详细对比结果保存路径")

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

    # 样本级别详细对比
    if args.detail > 0:
        # 解析算法列表
        default_algos = "baseline_cosine,pca_whitening,center_subtract,mahalanobis,baseline_l2"
        algo_str = args.detail_algos or default_algos
        algo_names = [a.strip() for a in algo_str.split(",")]

        algos = []
        for name in algo_names:
            try:
                algos.append(RecognitionMode(name))
            except ValueError:
                print(f"警告: 未知算法 '{name}'，跳过")
                continue

        if not algos:
            print("错误: 没有有效的算法")
            return

        print(f"\n将对比以下算法: {[a.value for a in algos]}")

        output_path = args.detail_output or str(
            Path(__file__).parent / "data" / "speaker_detail_comparison.json"
        )

        tester.run_sample_detail(
            n_samples=args.detail,
            algorithms=algos,
            output_file=output_path,
        )
        return

    if args.compare or args.mode in ["compare", "all"]:
        # 运行对比测试
        results = tester.run_comparison(n_samples=args.n_samples)
        tester.print_comparison(results)
    else:
        # 运行单个算法测试
        mode = RecognitionMode(args.mode)
        summary = tester.run_test(n_samples=args.n_samples, mode=mode)
        tester.print_summary(summary)

        if args.save:
            tester.save_results(summary)


if __name__ == "__main__":
    main()
