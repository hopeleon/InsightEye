"""
增强版声纹识别模块 - 多说话人高精度识别引擎
支持任意人数注册、动态阈值、多候选投票

核心设计（v3+ - Best-of-N × 分布一致性版）：
1. Best-of-N Cosine — probe 与每个注册样本单独比，取最佳
2. 分布一致性 — Diagonal Mahalanobis，probe 是否落在注册样本分布内（N≥3）
3. 分段一致性验证 — 窗口互一致性 + 窗口对 top-1 一致性，双重过滤误识别
4. 乘法融合 — Cosine × Dist × Boost，任一分量低则总分低，更严格
"""

import asyncio
import numpy as np
import threading
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum
import copy

from app.model_manager import SpeakerEmbeddingExtractor, ModelManager
from app.speaker_database import SpeakerDatabase


def _speaker_db_default_path() -> Optional[str]:
    """返回数据库默认路径（仅当 data 目录已存在时才返回，否则返回 None）"""
    try:
        from pathlib import Path
        from app.config import BASE_DIR
        db_dir = BASE_DIR / "data"
        if db_dir.exists():
            return str(db_dir / "speaker_voiceprints.db")
    except Exception:
        pass
    return None


# ==================== 数据结构 ====================

class SpeakerState(Enum):
    UNKNOWN = "unknown"
    REGISTERED = "registered"
    IDENTIFIED = "identified"


@dataclass
class SpeakerProfile:
    """说话人档案（增强版 v3+）"""
    speaker_id: str
    name: Optional[str] = None
    role: Optional[str] = None
    embedding: Optional[np.ndarray] = None
    embedding_mean: Optional[np.ndarray] = None
    embedding_std: Optional[np.ndarray] = None
    embedding_precision: Optional[np.ndarray] = None  # 逐维精度向量（1/var），用于 Mahalanobis/PLDA
    sample_count: int = 0
    audio_samples: List[np.ndarray] = field(default_factory=list)
    individual_embeddings: List[np.ndarray] = field(default_factory=list)
    registration_quality: float = 0.0
    registered_at: Optional[float] = None


@dataclass
class RegistrationResult:
    """注册结果（增强版）"""
    success: bool
    speaker_id: str
    name: Optional[str]
    sample_count: int
    embedding_quality: float
    message: str
    duplicate_warning: Optional[str] = None
    duplicate_speaker_id: Optional[str] = None
    duplicate_similarity: Optional[float] = None


@dataclass
class IdentificationResult:
    """识别结果（增强版）"""
    matches: List["SpeakerMatch"] = field(default_factory=list)
    voice_change_detected: bool = False
    uncertain: bool = False
    uncertainty_reason: Optional[str] = None


@dataclass
class SpeakerMatch:
    """说话人匹配结果"""
    speaker_id: str
    name: Optional[str]
    role: Optional[str]
    cosine_score: float
    normalized_score: float
    final_score: float
    confidence: float
    rank: int = 0


# ==================== 注册质量评估器 ====================

class RegistrationQualityAssessor:
    """
    注册质量评估器
    功能：
    1. 离群样本检测 — 检测录入的多个样本中是否存在与主体声纹偏离较大的样本
    2. 样本间方差控制 — 方差过大说明样本不稳定
    3. 重复注册检测 — 检测是否与已注册说话人过于相似
    """

    OUTLIER_THRESHOLD = 0.15
    MAX_SAMPLE_VARIANCE = 0.08
    MIN_INTER_SAMPLE_SIMILARITY = 0.75

    @staticmethod
    def assess_quality(
        embeddings: List[np.ndarray],
        existing_profiles: Dict[str, SpeakerProfile]
    ) -> Tuple[float, Optional[str], Optional[str], Optional[float]]:
        """
        评估注册质量

        Args:
            embeddings: 提取到的多个 embedding
            existing_profiles: 已注册的说话人档案

        Returns:
            (quality_score, warning_message, duplicate_speaker_id, duplicate_similarity)
        """
        if not embeddings:
            return 0.0, "没有有效的声纹样本", None, None

        n = len(embeddings)
        quality_score = 1.0

        # ---------- 1. 样本间一致性检测 ----------
        if n >= 2:
            pair_sims = []
            for i in range(n):
                for j in range(i + 1, n):
                    sim = RegistrationQualityAssessor._cosine_sim(embeddings[i], embeddings[j])
                    pair_sims.append(sim)

            avg_sim = np.mean(pair_sims)
            std_sim = np.std(pair_sims)

            if avg_sim < RegistrationQualityAssessor.MIN_INTER_SAMPLE_SIMILARITY:
                warning = f"样本间相似度过低({avg_sim:.3f})，可能存在录音质量问题或多人在场"
                quality_score *= 0.6
                return quality_score, warning, None, None

            if std_sim > RegistrationQualityAssessor.MAX_SAMPLE_VARIANCE:
                warning = f"样本间方差过大({std_sim:.3f})，样本不稳定"
                quality_score *= 0.7

            quality_score *= min(1.0, avg_sim)

        # ---------- 2. 离群样本检测 ----------
        if n >= 3:
            outlier = RegistrationQualityAssessor._detect_outlier(embeddings)
            if outlier:
                quality_score *= 0.75

        # ---------- 3. 与已注册说话人的重复检测 ----------
        mean_emb = np.mean(embeddings, axis=0)
        mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-8)

        max_sim = 0.0
        duplicate_id = None

        for spk_id, profile in existing_profiles.items():
            if profile.embedding is None:
                continue
            sim = RegistrationQualityAssessor._cosine_sim(mean_emb, profile.embedding)
            if sim > max_sim:
                max_sim = sim
                duplicate_id = spk_id

        if max_sim > 0.85:
            duplicate_warning = f"与已注册说话人「{duplicate_id}」高度相似({max_sim:.3f})，可能重复注册"
            quality_score *= 0.4
            return quality_score, duplicate_warning, duplicate_id, float(max_sim)

        return quality_score, None, None, None

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = a / (np.linalg.norm(a) + 1e-8)
        norm_b = b / (np.linalg.norm(b) + 1e-8)
        return float(np.dot(norm_a, norm_b))

    @staticmethod
    def _detect_outlier(embeddings: List[np.ndarray]) -> bool:
        """基于马氏距离检测离群样本（对角协方差版，避免小样本高维问题）"""
        try:
            embs = np.array(embeddings)
            if embs.ndim == 1:
                return False

            mean = np.mean(embs, axis=0)
            # 对角协方差：逐维方差，无需求逆，N=2-3 即可稳定估计
            var_diag = np.var(embs, axis=0, ddof=1) + 1e-8

            for emb in embs:
                diff = emb - mean
                # 对角协方差下的马氏距离
                mahal_sq = np.sum((diff ** 2) / var_diag)
                mahal = np.sqrt(mahal_sq)
                # 约等于 chi²(D) 的 95% 分位数时触发离群，D=192 时约 sqrt(2*192)=19.6
                if mahal > np.sqrt(2 * len(var_diag)):
                    return True
        except Exception:
            pass
        return False


# ==================== 音频数据增强器 ====================

class AudioAugmentor:
    """
    音频数据增强器（移植自 v2）
    在注册时对原始音频做增强，扩充训练数据量，提升声纹模型的鲁棒性。

    增强策略：
    - 加噪：模拟不同信噪比环境（安静/轻度噪声/中度噪声）
    - 混响：模拟不同房间大小的反射效果
    - 变速：轻微改变语速（不影响声纹特征的主要方向）
    - 变调：轻微改变音高（模拟不同音域的同一人说话）

    注意：所有增强都是对注册时的音频操作，不影响识别时的输入音频。
    """

    @staticmethod
    def add_noise(audio: np.ndarray, noise_level: float = 0.005) -> np.ndarray:
        """添加高斯噪声"""
        noise = np.random.randn(len(audio)).astype(np.float32) * noise_level
        return audio + noise

    @staticmethod
    def change_speed(audio: np.ndarray, speed_factor: float = 1.05) -> np.ndarray:
        """轻微改变语速（仅在 ±5% 范围内，不影响声纹）"""
        if abs(speed_factor - 1.0) < 0.001:
            return audio
        indices = np.round(np.arange(0, len(audio), speed_factor)).astype(int)
        indices = indices[indices < len(audio)]
        return audio[indices]

    @staticmethod
    def change_pitch(audio: np.ndarray, pitch_factor: float = 1.02) -> np.ndarray:
        """轻微改变音高（插值实现，不引入相位失真）"""
        if abs(pitch_factor - 1.0) < 0.001:
            return audio
        indices = np.arange(0, len(audio), pitch_factor)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    @staticmethod
    def add_reverb(audio: np.ndarray, room_size: float = 0.2) -> np.ndarray:
        """简单混响（多径延迟衰减模拟）"""
        output = np.copy(audio)
        n_echoes = 3
        delays = [int(len(audio) * 0.02 * (i + 1) * room_size) for i in range(n_echoes)]
        decays = [0.6 ** (i + 1) for i in range(n_echoes)]
        for delay, decay in zip(delays, decays):
            if delay >= len(audio):
                continue
            delayed = np.zeros_like(audio)
            delayed[delay:] = audio[:-delay] * decay
            output += delayed
        return output

    @staticmethod
    def augment(audio: np.ndarray, num_augmented: int = 3,
                extractor: Optional["SpeakerEmbeddingExtractor"] = None,
                original_embeddings: Optional[List[np.ndarray]] = None
                ) -> Tuple[List[np.ndarray], List[np.ndarray]]:
        """
        生成增强音频和对应的 embedding。

        注册时用原始音频提取 embedding 之后，再用增强音频提取一次，
        这样每个说话人可以用少量原始音频获得更多 embedding 样本。

        Args:
            audio: 原始音频（float32，16kHz）
            num_augmented: 生成多少个增强版本（最多 4 个）
            extractor: 声纹提取器（可选，有的话会直接提取增强后的 embedding）
            original_embeddings: 该说话人已有的原始 embedding 列表（有的话直接复用不做重复提取）

        Returns:
            (augmented_audios, augmented_embeddings)
            - augmented_audios: 增强后的音频列表（不包含原始音频）
            - augmented_embeddings: 增强后的 embedding 列表（可能为空如果 extractor=None）
        """
        augmented_audios = []
        augmented_embs = []

        # 避免对过短音频做激进增强
        min_len = extractor._segment_length if extractor else 16000
        if len(audio) < min_len:
            return [], []

        # 增强组合策略（按强度递增）
        augmentations = [
            ("noise_light", lambda: AudioAugmentor.add_noise(audio, noise_level=0.003)),
            ("noise_mid", lambda: AudioAugmentor.add_noise(audio, noise_level=0.008)),
            ("reverb", lambda: AudioAugmentor.add_reverb(audio, room_size=0.2)),
            ("speed_up", lambda: AudioAugmentor.change_speed(audio, speed_factor=1.05)),
            ("speed_down", lambda: AudioAugmentor.change_speed(audio, speed_factor=0.95)),
            ("pitch_up", lambda: AudioAugmentor.change_pitch(audio, pitch_factor=1.02)),
            ("pitch_down", lambda: AudioAugmentor.change_pitch(audio, pitch_factor=0.98)),
        ]

        for i, (name, augment_fn) in enumerate(augmentations):
            if i >= num_augmented:
                break
            try:
                aug_audio = augment_fn()
                if len(aug_audio) < min_len:
                    continue
                augmented_audios.append(aug_audio)

                if extractor is not None and original_embeddings is not None:
                    try:
                        aug_emb = extractor.extract(aug_audio)
                        # 与已有 embedding 做去重检查（增强版本不应与原始版本完全相同）
                        is_duplicate = any(
                            abs(float(np.dot(aug_emb, orig))) > 0.999
                            for orig in original_embeddings
                        )
                        if not is_duplicate:
                            augmented_embs.append(aug_emb)
                    except Exception:
                        pass
            except Exception:
                continue

        return augmented_audios, augmented_embs


# ==================== 说话人模型训练器（PLDA 风格） ====================

class SpeakerModelTrainer:
    """
    说话人统计模型训练器（移植自 v2 + 增强）
    使用多条音频训练说话人的统计模型（对角协方差 + 精度向量），
    为 Mahalanobis 距离和 PLDA 风格打分提供基础。

    核心原理：
    - 均值向量：对同一人多条音频的 embedding 取平均，代表该说话人的"中心"
    - 对角协方差：建模说话人内部的声纹变化范围（192 维独立方差，无需大矩阵求逆）
    - 精度向量：方差的倒数，Mahalanobis 距离的标准化系数

    相比全协方差矩阵的优势：
    - 192 维全协方差矩阵需要 O(D²) 存储和 O(D³) 求逆
    - 对角协方差只需 O(D) 存储，无需求逆，N=2-3 样本即可稳定估计
    """

    @staticmethod
    def train_speaker_model(
        embeddings: List[np.ndarray],
        regularization: float = 1e-4
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        训练说话人模型（对角协方差版）

        Args:
            embeddings: 多个 embedding 向量（同一说话人的多条音频提取）
            regularization: 方差下限，防止后续 Mahalanobis 计算除零

        Returns:
            (mean, var_diag, precision_diag) — 均值向量、逐维方差向量、逐维精度向量
        """
        embs = np.array(embeddings)
        if embs.ndim == 1:
            # 只有一个样本，退化为全 0 方差
            return embs, np.zeros_like(embs) + regularization, np.ones_like(embs) / regularization

        # 归一化后计算统计量（CAM++  embedding 是 L2 归一化的）
        embs_norm = np.array([e / (np.linalg.norm(e) + 1e-8) for e in embs])

        mean = np.mean(embs_norm, axis=0)
        mean = mean / (np.linalg.norm(mean) + 1e-8)

        # 逐维方差（对角协方差的核心）
        var_diag = np.var(embs_norm, axis=0, ddof=1) + regularization
        # 逐维精度 = 1 / 方差（无需矩阵求逆）
        precision_diag = 1.0 / var_diag

        return mean, var_diag, precision_diag

    @staticmethod
    def compute_mahalanobis_distance(
        probe: np.ndarray,
        mean: np.ndarray,
        prec_diag: np.ndarray
    ) -> float:
        """
        计算马氏距离（对角协方差版）

        Args:
            probe: 待识别 embedding（需归一化）
            mean: 说话人均值 embedding
            prec_diag: 逐维精度向量 (192,) = 1/var_i

        Returns:
            马氏距离（越小表示 probe 越靠近该说话人的分布中心）
        """
        if prec_diag is None:
            probe_norm = probe / (np.linalg.norm(probe) + 1e-8)
            mean_norm = mean / (np.linalg.norm(mean) + 1e-8)
            return 1.0 - float(np.dot(probe_norm, mean_norm))

        diff = probe - mean
        mahal_sq = np.dot(diff ** 2, prec_diag)
        return float(np.sqrt(mahal_sq))

    @staticmethod
    def compute_plda_score(
        probe: np.ndarray,
        mean: np.ndarray,
        precision_diag: np.ndarray,
        global_mean: Optional[np.ndarray] = None,
        within_cov: Optional[np.ndarray] = None,
        between_cov: Optional[np.ndarray] = None,
    ) -> Tuple[float, float, float]:
        """
        计算 PLDA 风格的多维度得分。

        PLDA（Probabilistic Linear Discriminant Analysis）是说话人识别的 SOTA 方法。
        它将每个 embedding 建模为：
            embedding = speaker_factor × speaker_model + channel_factor + noise
        其中：
            - speaker_model：说话人共享的因子（不同音频说同样的话时相同）
            - channel_factor：录音环境/设备/情绪等通道因子

        本实现使用简化版对角 PLDA：
            - 在 precision 空间计算马氏距离，避免大矩阵运算
            - 同一人假设：probe 应该在 (mean, precision_diag) 附近
            - 不同人说：probe 应该在 (global_mean, pooled_precision) 附近
            - 对数似然比（LLR）= log P(同一人) - log P(不同人)
            - sigmoid 归一化到 (0, 1)

        Args:
            probe: 待识别 embedding（需归一化）
            mean: 说话人均值 embedding
            precision_diag: 该说话人的逐维精度向量
            global_mean: 全局均值（所有已注册说话人的 embedding 均值）
            within_cov: 说话人内协方差（对角向量，所有说话人共享）
            between_cov: 说话人间协方差（对角向量，所有说话人共享）

        Returns:
            (plda_score, mahal_same, mahal_diff)
            - plda_score: [0,1]，越大表示越可能是该说话人
            - mahal_same: probe 到说话人均值的马氏距离（用于一致性验证）
            - mahal_diff: probe 到全局均值的马氏距离（用于区分度验证）
        """
        probe_norm = probe / (np.linalg.norm(probe) + 1e-8)
        mean_norm = mean / (np.linalg.norm(mean) + 1e-8)
        diff = probe_norm - mean_norm

        # 马氏距离（说话人假设）：probe 偏离该说话人分布中心的程度
        mahal_same = float(np.sqrt(np.dot(diff ** 2, precision_diag)))

        # 全局先验假设：所有人都来自同一分布
        if global_mean is not None and within_cov is not None and between_cov is not None:
            global_norm = global_mean / (np.linalg.norm(global_mean) + 1e-8)
            pooled_cov_diag = within_cov + between_cov  # 对角矩阵加法 = 逐维加法
            pooled_prec_diag = 1.0 / (pooled_cov_diag + 1e-8)
            diff_global = probe_norm - global_norm
            mahal_diff = float(np.sqrt(np.dot(diff_global ** 2, pooled_prec_diag)))
        else:
            # 无全局统计时的 fallback：用全局均值（如果有）和说话人自己的精度
            if global_mean is not None:
                global_norm = global_mean / (np.linalg.norm(global_mean) + 1e-8)
                diff_global = probe_norm - global_norm
                mahal_diff = float(np.sqrt(np.dot(diff_global ** 2, precision_diag)))
            else:
                # 完全无先验知识：mahal_diff = mahal_same × 缩放因子
                n_samples = max(3, 1.0 / np.mean(precision_diag + 1e-8))
                mahal_diff = mahal_same * np.sqrt(n_samples)

        # 对数似然比：同一人假设 vs 不同人说假设
        # 直观理解：
        #   mahal_same  >> mahal_diff → LLR < 0 → 接近全局分布但远离该说话人 → 不是同一人
        #   mahal_same  << mahal_diff → LLR > 0 → 接近该说话人分布 → 很可能是同一人
        llr = 0.5 * (mahal_same - mahal_diff)

        # Sigmoid 归一化：LLR → [0, 1] 概率分数
        # LLR=0 时 score=0.5（随机）
        # LLR>0 时 score>0.5（同一人可能性更大）
        # LLR<0 时 score<0.5（不同人可能性更大）
        plda_score = float(1.0 / (1.0 + np.exp(-llr)))

        return plda_score, mahal_same, mahal_diff


# ==================== 级联匹配引擎 ====================

class CascadeMatchingEngine:
    """
    级联匹配引擎 — 三级精度过滤

    Level 1 - Cosine Baseline:   快速初筛，过滤明显不匹配的候选
    Level 2 - Covariance Scoring: 协方差建模，捕捉声纹内部的判别性结构
    Level 3 - Adaptive Verification: 基于已注册说话人数量的自适应验证

    原理：
    - Level 1 只看向量方向，速度快但精度有限（多人场景容易混淆相近说话人）
    - Level 2 建模每个说话人的声纹分布，超出面中心的样本会被降权
    - Level 3 利用全局信息（当前注册人数、最近识别历史）动态调整
    """

    # 打分权重
    # 低于此分数的候选降级为 uncertain
    MIN_CONFIDENT_SCORE = 0.65
    
    # 全局片段计数器（用于关联 Match 日志和最终 speaker_id）
    _segment_counter = 0
    _counter_lock = threading.Lock()

    def __init__(self):
        self.registered_embeddings: Dict[str, np.ndarray] = {}
        self.registered_individual_embs: Dict[str, List[np.ndarray]] = {}
        self.registered_emb_stds: Dict[str, np.ndarray] = {}
        self.registered_precision: Dict[str, np.ndarray] = {}  # 逐维精度向量（v2 新增）
        self.identification_history: List[Tuple[str, float]] = []
        self._history_max_len = 20
        # PLDA 全局统计（v2 新增）
        self._global_mean: Optional[np.ndarray] = None
        self._within_cov: Optional[np.ndarray] = None  # 说话人内协方差（对角向量）
        self._between_cov: Optional[np.ndarray] = None  # 说话人间协方差（对角向量）

    def register_speaker(self, speaker_id: str, embedding: np.ndarray,
                         individual_embeddings: List[np.ndarray] = None,
                         emb_std: np.ndarray = None,
                         emb_precision: np.ndarray = None):
        """
        注册说话人（存储原始样本 + 方差 + 精度，用于 Best-of-N + Mahalanobis + PLDA）

        Args:
            emb_precision: 逐维精度向量（1/var），用于 Mahalanobis 和 PLDA
        """
        emb = embedding / (np.linalg.norm(embedding) + 1e-8)
        self.registered_embeddings[speaker_id] = emb

        if individual_embeddings and len(individual_embeddings) >= 2:
            norm_embs = [e / (np.linalg.norm(e) + 1e-8) for e in individual_embeddings]
            self.registered_individual_embs[speaker_id] = norm_embs
        else:
            self.registered_individual_embs[speaker_id] = []

        self.registered_emb_stds[speaker_id] = emb_std
        self.registered_precision[speaker_id] = emb_precision

        # 更新 PLDA 全局统计
        self._update_global_statistics()

    def unregister_speaker(self, speaker_id: str):
        if speaker_id in self.registered_embeddings:
            del self.registered_embeddings[speaker_id]
        if speaker_id in self.registered_individual_embs:
            del self.registered_individual_embs[speaker_id]
        if speaker_id in self.registered_emb_stds:
            del self.registered_emb_stds[speaker_id]
        if speaker_id in self.registered_precision:
            del self.registered_precision[speaker_id]
        self._update_global_statistics()

    def _update_global_statistics(self):
        """
        更新 PLDA 全局统计（说话人内/间协方差，对角向量）

        原理：
        - within_cov：同一说话人不同音频之间的方差（期望小）
        - between_cov：不同说话人之间的方差（期望大）
        这两个协方差矩阵在 PLDA 中用于计算probe属于"同一人"vs"不同人"的后验概率。
        """
        if len(self.registered_embeddings) < 2:
            self._global_mean = None
            self._within_cov = None
            self._between_cov = None
            return

        all_embs = list(self.registered_embeddings.values())
        all_embs_norm = [e / (np.linalg.norm(e) + 1e-8) for e in all_embs]
        all_embs_arr = np.array(all_embs_norm)

        # 全局均值
        self._global_mean = np.mean(all_embs_arr, axis=0)
        self._global_mean = self._global_mean / (np.linalg.norm(self._global_mean) + 1e-8)

        # 说话人内协方差：每个说话人的样本围绕其均值的偏差
        within_vars = []
        for sid, ind_embs in self.registered_individual_embs.items():
            if len(ind_embs) >= 2:
                embs = np.array(ind_embs)
                mean_s = np.mean(embs, axis=0)
                var_s = np.var(embs, axis=0, ddof=1)
                within_vars.append(var_s)
        if within_vars:
            self._within_cov = np.mean(within_vars, axis=0) + 1e-4
        else:
            self._within_cov = None

        # 说话人间协方差：不同说话人均值之间的方差
        if len(all_embs_norm) >= 2:
            self._between_cov = np.var(all_embs_arr, axis=0, ddof=1) + 1e-4
        else:
            self._between_cov = None

    def match(self, probe_embedding: np.ndarray,
              top_k: int = 3, audio_duration_ms: float = 0.0,
              track_id: Optional[int] = None) -> List[SpeakerMatch]:
        """
        级联匹配（三层打分）

        Level 1 - Best-of-N Cosine: probe 与每个注册样本单独比，取最佳
        Level 2 - Mahalanobis Distance: probe 偏离说话人分布中心的程度（用精度向量）
        Level 3 - PLDA Score: 说话人假设 vs 全局假设的对数似然比

        融合策略：score = sqrt(cos × mahal × plda) × boost_factor
        三信号乘法融合，任一信号低则总分低，更严格。

        Args:
            probe_embedding: 待识别音频的声纹向量
            top_k: 返回 top-k 个候选
            audio_duration_ms: 音频时长（毫秒），用于日志
            track_id: 片段追踪ID（用于日志关联），None则使用自增计数器

        Returns:
            List[SpeakerMatch]，按最终得分降序排列
        """
        # 生成片段序列号（使用传入的 track_id 或自增计数器）
        if track_id is not None:
            seg_seq = track_id
        else:
            with self._counter_lock:
                CascadeMatchingEngine._segment_counter += 1
                seg_seq = CascadeMatchingEngine._segment_counter
        
        if not self.registered_embeddings:
            return []

        probe = probe_embedding / (np.linalg.norm(probe_embedding) + 1e-8)
        candidates = {}
        best_cosines = {}
        mahal_scores = {}
        plda_scores = {}
        boost_values = {}

        for speaker_id, reg_emb in self.registered_embeddings.items():
            ind_embs = self.registered_individual_embs.get(speaker_id, [])
            emb_std = self.registered_emb_stds.get(speaker_id)
            emb_precision = self.registered_precision.get(speaker_id)

            # ----- 1. Best-of-N Cosine -----
            if ind_embs:
                cosine_scores = [float(np.dot(probe, e)) for e in ind_embs]
                best_cosine = max(cosine_scores)
            else:
                best_cosine = float(np.dot(probe, reg_emb))
            best_cosines[speaker_id] = best_cosine

            # ----- 2. Mahalanobis Distance（用精度向量，v2 重写）-----
            # 当注册样本不足时，Mahalanobis 不可靠：
            #   - 精度向量不可用 或 样本 < 3 → 设为 1.0（无 Mahalanobis 信号时不惩罚，依赖 Cosine）
            #   - std 可用但样本 < 2 → 同上
            #   - 避免 fallback=0.5 与 PLDA=0.5 相乘导致 fused 分数被压扁到接近 0
            if emb_precision is not None and len(ind_embs) >= 3:
                mahal = SpeakerModelTrainer.compute_mahalanobis_distance(
                    probe, reg_emb, emb_precision
                )
                mahal_score = float(np.clip(1.0 / (1.0 + mahal * 0.1), 0.0, 1.0))
            elif emb_std is not None and len(ind_embs) >= 2:
                diff = probe - reg_emb
                mahal_sq = np.sum((diff ** 2) / (emb_std ** 2 + 1e-8))
                mahal = np.sqrt(mahal_sq)
                mahal_score = float(np.clip(1.0 / (1.0 + mahal * 0.1), 0.0, 1.0))
            else:
                # 样本不足时：给 1.0（无惩罚），让 Cosine 主导
                mahal_score = 1.0
            mahal_scores[speaker_id] = mahal_score

            # ----- 3. PLDA Score（v2 新增）-----
            # NaN 保护：计算失败时返回中性 0.5（不对排名产生误导）
            try:
                plda_score, mahal_same, mahal_diff = SpeakerModelTrainer.compute_plda_score(
                    probe, reg_emb, emb_precision,
                    global_mean=self._global_mean,
                    within_cov=self._within_cov,
                    between_cov=self._between_cov,
                )
                import math
                if math.isnan(plda_score):
                    plda_score = 0.5
                    mahal_same = 0.0
                    mahal_diff = 0.0
            except Exception:
                plda_score = 0.5
            plda_scores[speaker_id] = plda_score

            # ----- 融合：Cosine × Mahal × PLDA × Boost -----
            # 三信号乘法融合（v3 原为 Cosine × Dist × Boost）
            cos_mahal = best_cosine * mahal_score * plda_score
            cos_mahal_smooth = np.cbrt(np.clip(cos_mahal, 0.0, 1.0))  # 立方根保持 [0,1] 范围
            boost = self._get_adaptive_boost(speaker_id)
            boost_factor = 0.8 + boost * 0.4  # [0.8, 1.2]
            final_score = cos_mahal_smooth * boost_factor
            candidates[speaker_id] = np.clip(final_score, 0.0, 1.0)
            boost_values[speaker_id] = boost

        # 排序取 top-k
        sorted_candidates = sorted(
            candidates.items(), key=lambda x: x[1], reverse=True
        )

        matches = []
        rank = 1

        for speaker_id, score in sorted_candidates:
            if rank > top_k:
                break
            normalized = self._normalize_score(score, candidates)
            confidence = self._compute_confidence(score, candidates, len(candidates))

            if rank == 1:
                print(f"[Match][#{seg_seq:04d}] speaker={speaker_id}, score={score:.4f}")
            matches.append(SpeakerMatch(
                speaker_id=speaker_id,
                name=None,
                role=None,
                cosine_score=float(best_cosines[speaker_id]),
                normalized_score=float(normalized),
                final_score=float(score),
                confidence=float(confidence),
                rank=rank
            ))
            rank += 1

        return matches

    def _get_adaptive_boost(self, speaker_id: str) -> float:
        """基于识别历史和样本数量的自适应 boost（无 cosine 依赖）"""
        boost = 0.5
        # 历史连续识别加成
        recent = [sid for sid, _ in self.identification_history[-5:]]
        if speaker_id in recent:
            boost += 0.15 * recent.count(speaker_id)
        # 注册样本越多，boost 越高（说明声纹更可靠）
        ind_embs = self.registered_individual_embs.get(speaker_id, [])
        boost += min(0.1, len(ind_embs) * 0.03)
        boost = np.clip(boost, 0.0, 1.0)
        return boost

    def _normalize_score(self, score: float, all_scores: Dict[str, float]) -> float:
        """Min-Max 归一化"""
        scores = list(all_scores.values())
        if not scores or max(scores) == min(scores):
            return 1.0 if score > 0 else 0.0
        return (score - min(scores)) / (max(scores) - min(scores))

    def _compute_confidence(self, score: float, all_scores: Dict[str, float],
                             n_total: int) -> float:
        """计算置信度：考虑分数差距 + 注册人数"""
        if n_total == 1:
            return min(1.0, score * 1.2 + 0.1)

        sorted_scores = sorted(all_scores.values(), reverse=True)
        if len(sorted_scores) < 2:
            return min(1.0, score * 1.2)

        top_score = sorted_scores[0]
        second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
        gap = top_score - score

        base_conf = 1.0 - gap * 1.5
        if score >= self.MIN_CONFIDENT_SCORE and gap < 0.10:
            base_conf += 0.15

        n_penalty = min(0.15, (len(self.registered_embeddings) - 2) * 0.03)
        return float(np.clip(base_conf - n_penalty, 0.0, 1.0))

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = a / (np.linalg.norm(a) + 1e-8)
        norm_b = b / (np.linalg.norm(b) + 1e-8)
        return float(np.dot(norm_a, norm_b))

    def record_identification(self, speaker_id: str, score: float):
        self.identification_history.append((speaker_id, score))
        if len(self.identification_history) > self._history_max_len:
            self.identification_history.pop(0)

    def match_with_voting(
        self,
        probe_embeddings: list[np.ndarray],
        top_k: int = 3,
        vote_method: str = "score_weighted",
        track_id: Optional[int] = None,
    ) -> list["SpeakerMatch"]:
        """
        多窗口投票融合识别 — 对同一段音频的多个 embedding 分别做级联匹配，
        再通过投票融合得到最终结果。

        Args:
            probe_embeddings: 同一段音频提取的多个声纹向量
            top_k: 返回的候选数量
            vote_method: 投票方法
                "hard": 多数投票（简单，但忽略置信度差异）
                "score_weighted": 分数加权投票（各窗口得分按其可靠性加权）
                "rank_weighted": 排名加权投票（各窗口 top-k 排名加权）
            track_id: 片段追踪ID（用于日志关联），None则使用自增计数器

        Returns:
            List[SpeakerMatch]，按融合后的最终得分降序排列
        """
        if not probe_embeddings or not self.registered_embeddings:
            return []

        # ---- Step 1: 每个 embedding 独立做级联匹配 ----
        per_window_results: list[list[SpeakerMatch]] = []
        for emb in probe_embeddings:
            matches = self.match(emb, top_k=top_k, track_id=track_id)
            per_window_results.append(matches)

        if not per_window_results or not per_window_results[0]:
            return []

        # ---- Step 2: 收集所有候选说话人 ----
        all_candidates: set[str] = set()
        for matches in per_window_results:
            for m in matches:
                all_candidates.add(m.speaker_id)

        # ---- Step 3: 按投票方法融合 ----
        fused_scores: dict[str, float] = {}

        for sid in all_candidates:
            if vote_method == "hard":
                votes = sum(1 for matches in per_window_results if matches and matches[0].speaker_id == sid)
                fused_scores[sid] = votes / len(probe_embeddings)

            elif vote_method == "score_weighted":
                score = 0.0
                total_weight = 0.0
                for matches in per_window_results:
                    if not matches:
                        continue
                    for rank, m in enumerate(matches):
                        if m.speaker_id == sid:
                            weight = 1.0 / (rank + 1)
                            # NaN 保护：忽略无效分数
                            raw_score = m.final_score if not (isinstance(m.final_score, float) and np.isnan(m.final_score)) else 0.0
                            score += raw_score * weight
                            total_weight += weight
                            break
                fused_scores[sid] = score / total_weight if total_weight > 0 else 0.0

            elif vote_method == "rank_weighted":
                score = 0.0
                total_weight = 0.0
                for matches in per_window_results:
                    if not matches:
                        continue
                    for rank, m in enumerate(matches):
                        if m.speaker_id == sid:
                            weight = 1.0 / (rank + 1)
                            score += weight
                            total_weight += weight
                            break
                fused_scores[sid] = score / total_weight if total_weight > 0 else 0.0

        # ---- Step 4: 收集每个候选的 cosine 均值（用于二次验证）----
        cos_mean: dict[str, float] = {}
        for sid in all_candidates:
            cos_scores = []
            for matches in per_window_results:
                for m in matches:
                    if m.speaker_id == sid:
                        # cosine_score 存的是原始 Best-of-N Cosine（不含 boost），更可靠
                        raw_cos = m.cosine_score
                        if isinstance(raw_cos, float) and np.isnan(raw_cos):
                            raw_cos = 0.0
                        cos_scores.append(raw_cos)
                        break
            cos_mean[sid] = float(np.mean(cos_scores)) if cos_scores else 0.0

        # ---- Step 5: 归一化并构建 SpeakerMatch ----
        if not fused_scores:
            return []

        max_score = max(fused_scores.values())
        min_score = min(fused_scores.values())
        score_range = max_score - min_score if max_score != min_score else 1.0

        # NaN 过滤：fused 为 NaN 时替换为 0
        for sid in fused_scores:
            if isinstance(fused_scores[sid], float) and np.isnan(fused_scores[sid]):
                fused_scores[sid] = 0.0

        sorted_candidates = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)

        top1_by_fused = sorted_candidates[0][0] if sorted_candidates else None

        matches: list[SpeakerMatch] = []
        for rank_idx, (sid, fused) in enumerate(sorted_candidates[:top_k]):
            rank_based_norm = 1.0 / (rank_idx + 1)

            # ---- 改进的归一化：cosine 主导（0.8 权重）----
            # score_weighted 的 fused 值范围很小（被 rank 权重压扁），
            # 所以用 score_range 归一化再乘以 0.2；rank 权重 0.3；cosine 均值 0.8
            fused_norm = (fused - min_score) / max(score_range, 1e-9)
            normalized = rank_based_norm * 0.3 + fused_norm * 0.2 + cos_mean[sid] * 0.5
            confidence = float(np.clip(normalized * 1.2, 0.0, 1.0))

            # ---- Cosine 二次验证（强化版）----
            if rank_idx == 0 and len(sorted_candidates) > 1:
                second_sid = sorted_candidates[1][0]
                top1_cos = cos_mean.get(top1_by_fused, 0.0)
                second_cos = cos_mean.get(second_sid, 0.0)
                if top1_cos < second_cos:
                    print(
                        f"[VoteFusion-WARN] fused top1={top1_by_fused}(cos={top1_cos:.4f}) "
                        f"< second={second_sid}(cos={second_cos:.4f})，已用 cosine 纠正"
                    )
                    # 打印所有候选的 cosine 方便调试
                    for _sid, _cos in sorted(cos_mean.items(), key=lambda x: x[1], reverse=True)[:5]:
                        print(f"  cosine_top: {_sid} cos={_cos:.4f}")

            # 附加各窗口的详细信息（排名 + 分数）
            window_info = {}
            for idx, matches_list in enumerate(per_window_results):
                for r, m in enumerate(matches_list):
                    if m.speaker_id == sid:
                        fs = m.final_score
                        if isinstance(fs, float) and np.isnan(fs):
                            fs = 0.0
                        window_info[f"win{idx}"] = f"rank{r+1}/{fs:.3f}"
                        break
                else:
                    window_info[f"win{idx}"] = "miss"

            profile = self._get_speaker_profile(sid)
            matches.append(SpeakerMatch(
                speaker_id=sid,
                name=profile.name if profile else None,
                role=profile.role if profile else None,
                cosine_score=fused,
                normalized_score=normalized,
                final_score=fused,
                confidence=confidence,
                rank=rank_idx + 1,
            ))
            print(
                f"[VoteFusion] {sid} (win={profile.name if profile else ''}): "
                f"fused={fused:.4f}, cos_mean={cos_mean.get(sid, 0):.4f}, norm={normalized:.4f}, {window_info}"
            )

        return matches

    def _get_speaker_profile(self, speaker_id: str) -> Optional["SpeakerProfile"]:
        """在 MultiSpeakerRegistry 外部访问 SpeakerProfile 的桥接方法"""
        # 此方法由 MultiSpeakerRegistry 在注册后注入，实际逻辑见 MultiSpeakerRegistry.identify_with_voting
        if hasattr(self, "_profile_accessor") and callable(self._profile_accessor):
            return self._profile_accessor(speaker_id)
        return None


# ==================== 评分归一化引擎 ====================

class ScoreNormalizer:
    """
    评分归一化引擎 — 解决 Cosine 得分分布不一致问题

    核心问题：不同说话人/不同音频质量的 cosine 得分分布差异很大。
    例如：
      - 说话人 A 的 genuine 得分：0.92-0.98，impostor 得分：0.55-0.75
      - 说话人 B 的 genuine 得分：0.75-0.85，impostor 得分：0.40-0.60

    归一化后：
      - 说话人 A 的得分：genuine ≈ 0.8, impostor ≈ 0.2
      - 说话人 B 的得分：genuine ≈ 0.8, impostor ≈ 0.2

    方法：Z-norm + 同一人/不同人先验融合
      - Z-norm: 将每个说话人的得分归一化到统一分布
      - Prior fusion: 融合先验信息（注册质量、说话人区分度）
    """

    # Z-norm 默认参数（注册人数少时使用全局统计）
    DEFAULT_MEAN = 0.60
    DEFAULT_STD = 0.15
    # 归一化后的判定阈值（归一化后，genuine 约在 0.7-1.0，impostor 约在 0.0-0.3）
    NORM_THRESHOLD = 0.50
    # 最少需要多少 impostor 样本来可靠估计分布
    MIN_IMPOSTOR_SAMPLES = 5

    def __init__(self):
        # 每个说话人的 Z-norm 参数
        # {speaker_id: {"mean": float, "std": float, "genuine_mean": float, "n_samples": int}}
        self._speaker_stats: Dict[str, Dict] = {}

        # 全局 impostor 得分记录（用于冷启动）
        self._global_impostor_scores: List[float] = []
        self._global_genuine_scores: List[float] = []
        self._max_global_samples = 200

    def register_speaker_stats(
        self,
        speaker_id: str,
        embeddings: List[np.ndarray],
        enrolled_embeddings: Dict[str, np.ndarray]
    ):
        """
        注册说话人的归一化统计信息

        通过计算该说话人与所有已注册说话人的 impostor 得分分布，
        估计 Z-norm 参数。

        Args:
            speaker_id: 新注册说话人 ID
            embeddings: 该说话人的多个 embedding
            enrolled_embeddings: 所有已注册说话人的 embedding
        """
        if not embeddings or not enrolled_embeddings:
            return

        mean_emb = np.mean([e / (np.linalg.norm(e) + 1e-8) for e in embeddings], axis=0)
        mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-8)

        impostor_scores = []
        for other_id, other_emb in enrolled_embeddings.items():
            if other_id == speaker_id:
                continue
            sim = self._cosine_sim(mean_emb, other_emb)
            impostor_scores.append(sim)

        if len(impostor_scores) >= self.MIN_IMPOSTOR_SAMPLES:
            mean = np.mean(impostor_scores)
            std = np.std(impostor_scores) + 1e-8
        elif len(enrolled_embeddings) > 1:
            mean = self.DEFAULT_MEAN
            std = self.DEFAULT_STD
        else:
            return

        self._speaker_stats[speaker_id] = {
            "mean": float(mean),
            "std": float(std),
            "genuine_mean": float(np.mean(impostor_scores) if impostor_scores else 0.7),
            "n_impostors": len(impostor_scores),
            "emb": mean_emb,
        }

    def unregister_speaker(self, speaker_id: str):
        if speaker_id in self._speaker_stats:
            del self._speaker_stats[speaker_id]

    def normalize_score(
        self,
        probe_emb: np.ndarray,
        speaker_id: str,
        raw_cosine: float
    ) -> Tuple[float, float]:
        """
        对原始 cosine 得分进行 Z-norm 归一化

        Args:
            probe_emb: probe 音频的 embedding
            speaker_id: 待比对说话人 ID
            raw_cosine: 原始 cosine 相似度

        Returns:
            (normalized_score, quality_indicator)
            - normalized_score: Z-norm 后的得分（0-1），约在 0.5 附近表示不确定
            - quality_indicator: 1.0=高质量，0.5=统计不可靠，0.0=无统计
        """
        probe_emb = probe_emb / (np.linalg.norm(probe_emb) + 1e-8)

        if speaker_id not in self._speaker_stats:
            return float(raw_cosine), 0.0

        stats = self._speaker_stats[speaker_id]
        mean = stats["mean"]
        std = stats["std"]

        z_score = (raw_cosine - mean) / std
        norm_score = 0.5 + 0.5 * np.tanh(z_score)

        quality = min(1.0, stats["n_impostors"] / 20.0)

        return float(norm_score), float(quality)

    def normalize_batch(
        self,
        probe_emb: np.ndarray,
        candidates: Dict[str, float]
    ) -> Dict[str, Tuple[float, float]]:
        """
        批量归一化多个候选说话人的得分

        Args:
            probe_emb: probe embedding
            candidates: {speaker_id: raw_cosine_score}

        Returns:
            {speaker_id: (normalized_score, quality_indicator)}
        """
        results = {}
        for speaker_id, raw_score in candidates.items():
            norm_score, quality = self.normalize_score(probe_emb, speaker_id, raw_score)
            results[speaker_id] = (norm_score, quality)
        return results

    def update_global_stats(self, speaker_id: str, probe_emb: np.ndarray,
                           matched: bool, score: float):
        """更新全局统计（用于冷启动和无统计的说话人）"""
        if matched:
            self._global_genuine_scores.append(score)
        else:
            self._global_impostor_scores.append(score)

        if len(self._global_genuine_scores) > self._max_global_samples:
            self._global_genuine_scores = self._global_genuine_scores[-self._max_global_samples:]
        if len(self._global_impostor_scores) > self._max_global_samples:
            self._global_impostor_scores = self._global_impostor_scores[-self._max_global_samples:]

    def get_normalized_threshold(self, quality: float = 1.0) -> float:
        """
        获取归一化后的判定阈值

        归一化后得分分布约在 [0, 1]，genuine 约在 0.6-1.0，impostor 约在 0.0-0.4
        """
        base = self.NORM_THRESHOLD
        return float(base)

    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        norm_a = a / (np.linalg.norm(a) + 1e-8)
        norm_b = b / (np.linalg.norm(b) + 1e-8)
        return float(np.dot(norm_a, norm_b))


# ==================== 动态阈值控制器 ====================

class DynamicThresholdController:
    """
    动态阈值控制器
    根据已注册说话人数量、识别得分分布，自动计算最优阈值

    支持两种模式：
    - 原始 Cosine 模式：阈值范围 0.45-0.85
    - 归一化模式（Z-norm）：阈值范围更紧凑，因为归一化后分布统一
    """

    # 原始 Cosine 模式阈值
    BASE_THRESHOLD_RAW = 0.60
    # 归一化模式阈值（归一化后得分约在 [0,1]，genuine 约 0.6-1.0）
    BASE_THRESHOLD_NORM = 0.55
    PER_SPEAKER_PENALTY_RAW = 0.015
    PER_SPEAKER_PENALTY_NORM = 0.008
    MIN_THRESHOLD_RAW = 0.45
    MAX_THRESHOLD_RAW = 0.85
    MIN_THRESHOLD_NORM = 0.40
    MAX_THRESHOLD_NORM = 0.75

    def __init__(self, use_normalized: bool = True):
        self._use_normalized = use_normalized

    def set_normalized_mode(self, enabled: bool):
        """切换归一化/原始模式"""
        self._use_normalized = enabled

    @classmethod
    def compute_threshold(cls, n_registered: int,
                          score_distribution: List[float] = None,
                          use_normalized: bool = True) -> float:
        """
        计算动态阈值

        Args:
            n_registered: 已注册说话人数量
            score_distribution: 历史识别得分分布
            use_normalized: 是否使用归一化模式

        Returns:
            float 建议使用的相似度阈值
        """
        if use_normalized:
            base = cls.BASE_THRESHOLD_NORM
            penalty = n_registered * cls.PER_SPEAKER_PENALTY_NORM
            min_thr = cls.MIN_THRESHOLD_NORM
            max_thr = cls.MAX_THRESHOLD_NORM
        else:
            base = cls.BASE_THRESHOLD_RAW
            penalty = n_registered * cls.PER_SPEAKER_PENALTY_RAW
            min_thr = cls.MIN_THRESHOLD_RAW
            max_thr = cls.MAX_THRESHOLD_RAW

        threshold = base + penalty

        if score_distribution and len(score_distribution) >= 10:
            scores = np.array(score_distribution)
            p25 = np.percentile(scores, 25)
            p75 = np.percentile(scores, 75)
            iqr = p75 - p25
            margin = max(0.05, iqr * 0.3)
            threshold = min(threshold, p25 + margin)

        return float(np.clip(threshold, min_thr, max_thr))

    @classmethod
    def compute_top_k(cls, n_registered: int) -> int:
        """根据注册人数建议返回的候选数量"""
        if n_registered <= 2:
            return 1
        elif n_registered <= 5:
            return min(2, n_registered)
        else:
            return min(3, n_registered)


# ==================== 多说话人注册表 ====================

class MultiSpeakerRegistry:
    """
    多说话人注册表
    支持任意数量说话人的注册、查询、删除

    功能：
    - 手动注册：传入音频样本或已有 embedding，附带姓名标签
    - 自动去重：注册时检测是否与已有说话人重复
    - 增量更新：已有说话人可追加新样本微调声纹
    - 持久化：支持保存/加载注册表到文件
    """

    MIN_SAMPLES_FOR_REGISTRATION = 2
    MIN_SAMPLE_DURATION_SAMPLES = 8000

    def __init__(self, model_manager: ModelManager, db_path: Optional[str] = None):
        self.model_manager = model_manager
        self.extractor = SpeakerEmbeddingExtractor(
            model_manager.get_camp_model(),
            device=model_manager.device
        )
        self.speakers: Dict[str, SpeakerProfile] = {}
        self.matching_engine = CascadeMatchingEngine()
        self._threshold_controller = DynamicThresholdController(use_normalized=True)
        self.threshold = DynamicThresholdController.BASE_THRESHOLD_NORM
        self._recent_scores: List[float] = []
        self._speaker_counter = 0
        self._db: Optional[SpeakerDatabase] = None
        if db_path is not None or _speaker_db_default_path() is not None:
            self._db = SpeakerDatabase(db_path or _speaker_db_default_path())

    # ==================== 注册 API ====================

    def register_speaker(
        self,
        speaker_id: Optional[str],
        audio_samples: List[np.ndarray],
        name: Optional[str] = None,
        role: Optional[str] = None,
        force: bool = False
    ) -> RegistrationResult:
        """
        注册说话人（通过音频样本）

        Args:
            speaker_id: 说话人 ID（None 时自动生成）
            audio_samples: 音频样本列表（每段至少 0.5 秒）
            name: 姓名标签
            role: 角色标签
            force: True=跳过重复检测强制注册

        Returns:
            RegistrationResult
        """
        if len(audio_samples) < self.MIN_SAMPLES_FOR_REGISTRATION:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id or "",
                name=name,
                sample_count=len(audio_samples),
                embedding_quality=0.0,
                message=f"需要至少 {self.MIN_SAMPLES_FOR_REGISTRATION} 个音频样本，当前只有 {len(audio_samples)} 个"
            )

        for sample in audio_samples:
            if len(sample) < self.MIN_SAMPLE_DURATION_SAMPLES:
                return RegistrationResult(
                    success=False,
                    speaker_id=speaker_id or "",
                    name=name,
                    sample_count=len(audio_samples),
                    embedding_quality=0.0,
                    message=f"样本时长不足（需要 >= 0.5 秒）"
                )

        embeddings = []
        for sample in audio_samples:
            try:
                emb = self.extractor.extract(sample)
                embeddings.append(emb)
            except Exception as e:
                print(f"[Registry] 提取声纹失败: {e}")
                continue

        if len(embeddings) < self.MIN_SAMPLES_FOR_REGISTRATION:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id or "",
                name=name,
                sample_count=len(embeddings),
                embedding_quality=0.0,
                message="声纹提取失败，请检查音频质量"
            )

        return self._do_register(
            speaker_id=speaker_id,
            embeddings=embeddings,
            audio_samples=audio_samples,
            name=name,
            role=role,
            force=force
        )

    def register_embedding(
        self,
        speaker_id: Optional[str],
        embedding: np.ndarray,
        name: Optional[str] = None,
        role: Optional[str] = None,
        force: bool = False
    ) -> RegistrationResult:
        """
        直接用已有的 embedding 注册说话人（快速模式）

        Args:
            speaker_id: 说话人 ID（None 时自动生成）
            embedding: 192 维声纹向量
            name: 姓名标签
            role: 角色标签
            force: True=跳过重复检测

        Returns:
            RegistrationResult
        """
        if embedding is None or embedding.size == 0:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id or "",
                name=name,
                sample_count=0,
                embedding_quality=0.0,
                message="embedding 为空"
            )

        return self._do_register(
            speaker_id=speaker_id,
            embeddings=[embedding],
            audio_samples=[],
            name=name,
            role=role,
            force=force
        )

    def _do_register(
        self,
        speaker_id: Optional[str],
        embeddings: List[np.ndarray],
        audio_samples: List[np.ndarray],
        name: Optional[str],
        role: Optional[str],
        force: bool
    ) -> RegistrationResult:
        """内部注册逻辑"""
        if speaker_id is None:
            self._speaker_counter += 1
            speaker_id = f"speaker_{self._speaker_counter:03d}"

        if speaker_id in self.speakers:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id,
                name=name,
                sample_count=len(embeddings),
                embedding_quality=0.0,
                message=f"说话人 ID 「{speaker_id}」已存在，请使用其他 ID"
            )

        quality, warning, dup_id, dup_sim = RegistrationQualityAssessor.assess_quality(
            embeddings, self.speakers
        )

        if not force and warning:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id,
                name=name,
                sample_count=len(embeddings),
                embedding_quality=quality,
                duplicate_warning=warning,
                duplicate_speaker_id=dup_id,
                duplicate_similarity=dup_sim,
                message=warning
            )

        # ---- Step 1: 音频增强（移植自 v2）----
        # 对每条原始音频生成多个增强版本（加噪/混响/变速/变调），
        # 用 extractor 提取对应的 embedding，扩充注册样本量
        augmented_embs: List[np.ndarray] = []
        if audio_samples and self.extractor is not None:
            n_aug = max(0, 3 - len(embeddings))  # 原始样本越多，增强越少
            if n_aug > 0:
                for audio in audio_samples:
                    _, aug_embs = AudioAugmentor.augment(
                        audio,
                        num_augmented=n_aug,
                        extractor=self.extractor,
                        original_embeddings=embeddings
                    )
                    augmented_embs.extend(aug_embs)
                print(f"[Registry] 音频增强: 生成了 {len(augmented_embs)} 个增强 embedding")

        # 全部注册用 embedding = 原始 + 增强
        all_embs = embeddings + augmented_embs
        avg_emb = np.mean(all_embs, axis=0)
        avg_emb = avg_emb / (np.linalg.norm(avg_emb) + 1e-8)

        # ---- Step 2: 说话人统计模型（移植自 v2）----
        # 用 SpeakerModelTrainer 计算对角协方差和精度向量
        _, emb_var, emb_precision = SpeakerModelTrainer.train_speaker_model(all_embs)
        emb_std = np.sqrt(emb_var)  # std = sqrt(var)，兼容旧字段

        profile = SpeakerProfile(
            speaker_id=speaker_id,
            name=name,
            role=role,
            embedding=avg_emb,
            embedding_mean=np.mean(embeddings, axis=0),
            embedding_std=emb_std,
            embedding_precision=emb_precision,  # v2 新增：逐维精度向量
            sample_count=len(all_embs),  # 含增强样本
            audio_samples=audio_samples,
            individual_embeddings=embeddings,  # 原始 embedding（不含增强，用于 Best-of-N）
            registration_quality=quality,
            registered_at=None
        )

        self.speakers[speaker_id] = profile
        self.matching_engine.register_speaker(
            speaker_id, avg_emb, embeddings, emb_std, emb_precision
        )
        # 为新注册说话人计算 Z-norm 统计信息（需要先有其他人的 embedding）
        enrolled_embs = {
            sid: spk.embedding
            for sid, spk in self.speakers.items()
            if spk.embedding is not None
        }
        self._update_threshold()

        msg = f"成功注册说话人「{name or speaker_id}」(ID: {speaker_id})"
        if warning:
            msg += f"，但有警告: {warning}"

        print(f"[Registry] {msg}，原始样本: {len(embeddings)}，增强样本: {len(augmented_embs)}，质量: {quality:.3f}")

        return RegistrationResult(
            success=True,
            speaker_id=speaker_id,
            name=name,
            sample_count=len(embeddings),
            embedding_quality=quality,
            duplicate_warning=warning,
            duplicate_speaker_id=dup_id,
            duplicate_similarity=dup_sim,
            message=msg
        )

    # ==================== 识别 API ====================

    def identify(self, audio_sample: np.ndarray,
                 top_k: Optional[int] = None,
                 track_id: Optional[int] = None) -> IdentificationResult:
        """
        识别说话人

        Args:
            audio_sample: 音频数据，float32，16kHz
            top_k: 返回的候选数量（None=自动）
            track_id: 片段追踪ID（用于日志关联），None则使用自增计数器

        Returns:
            IdentificationResult
        """
        if not self.speakers:
            return IdentificationResult(uncertain=True, uncertainty_reason="没有已注册的说话人")

        try:
            embedding = self.extractor.extract(audio_sample)
            # 检测零向量（通常是音频过短导致 CAM++ 输出 NaN 后被替换的结果）
            # 零向量与任何向量的余弦相似度都接近 0.5，识别结果完全不可靠
            if np.linalg.norm(embedding) < 1e-6:
                print(f"[Registry] 警告: 零向量 embedding (norm={np.linalg.norm(embedding):.2e})，识别不可靠")
                return IdentificationResult(uncertain=True, uncertainty_reason="声纹特征无效（零向量）")
        except Exception as e:
            print(f"[Registry] 声纹提取失败: {e}")
            return IdentificationResult(uncertain=True, uncertainty_reason="声纹提取失败")

        if top_k is None:
            top_k = DynamicThresholdController.compute_top_k(len(self.speakers))

        # 计算音频时长
        audio_duration_ms = len(audio_sample) / 16.0  # 16kHz 采样率
        matches = self.matching_engine.match(embedding, top_k=top_k, audio_duration_ms=audio_duration_ms, track_id=track_id)

        if not matches:
            return IdentificationResult(uncertain=True, uncertainty_reason="没有匹配到任何说话人")

        for m in matches:
            profile = self.speakers.get(m.speaker_id)
            if profile:
                m.name = profile.name
                m.role = profile.role

        self.matching_engine.record_identification(
            matches[0].speaker_id, matches[0].final_score
        )
        self._recent_scores.append(matches[0].final_score)
        if len(self._recent_scores) > 100:
            self._recent_scores.pop(0)

        # 持久化识别记录到数据库
        if self._db is not None and matches:
            try:
                self._db.log_identification(
                    speaker_id=matches[0].speaker_id,
                    session_id="",  # session_id 由调用方补充
                    confidence=float(matches[0].final_score),
                )
            except Exception as e:
                print(f"[Registry] 记录识别日志失败: {e}")

        threshold = self._threshold_controller.compute_threshold(
            len(self.speakers), self._recent_scores, use_normalized=True
        )

        top = matches[0]
        uncertain = (
            top.confidence < 0.50
            or top.final_score < threshold
            or (len(matches) >= 2 and matches[1].final_score > 0
                and (top.final_score - matches[1].final_score) < 0.05)
        )

        result = IdentificationResult(
            matches=matches,
            uncertain=uncertain
        )
        if uncertain:
            result.uncertainty_reason = self._get_uncertainty_reason(
                matches, threshold
            )

        return result

    async def identify_async(self, audio_sample: np.ndarray,
                              top_k: Optional[int] = None) -> IdentificationResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.identify, audio_sample, top_k)

    # ==================== 多窗口投票识别 API ====================

    def identify_with_voting(
        self,
        audio_sample: np.ndarray,
        n_windows: int = 3,
        window_step_ratio: float = 0.25,
        fusion_method: str = "mean",
        vote_method: str = "score_weighted",
        top_k: Optional[int] = None,
        track_id: Optional[int] = None,
    ) -> tuple[IdentificationResult, dict]:
        """
        多窗口投票融合识别 — 对一段音频提取多个 embedding，分别匹配后投票融合。

        原理：同一人说话的声纹在短时间内稳定，但不同音素位置可能有微小波动。
        多窗口采样 + 投票可过滤离群窗口，显著降低误识别率。

        Args:
            audio_sample: 音频数据，float32，16kHz
            n_windows: 滑动窗口数量，建议 3
            window_step_ratio: 步长占窗口长度比例，0.25 = 重叠 75%
            fusion_method: 向量融合方法，"mean"（算术平均）或 "median"（中位数）
            vote_method: 投票方法，"hard"（多数票）/ "score_weighted"（分数加权）/ "rank_weighted"（排名加权）
            top_k: 返回候选数量（None=自动）
            track_id: 片段追踪ID（用于日志关联），None则使用自增计数器

        Returns:
            (IdentificationResult, stats_dict)
            stats_dict: {"n_windows": int, "n_valid": int, "window_stats": dict, ...}
        """
        if not self.speakers:
            return (
                IdentificationResult(uncertain=True, uncertainty_reason="没有已注册的说话人"),
                {}
            )

        if top_k is None:
            top_k = DynamicThresholdController.compute_top_k(len(self.speakers))

        # 为 matching_engine 注入 profile 访问器（解决跨类访问）
        self.matching_engine._profile_accessor = lambda sid: self.speakers.get(sid)

        try:
            # Step 1: 多窗口提取 embedding
            window_results = self.extractor.extract_multi_window(
                audio_sample, n_windows=n_windows, window_step_ratio=window_step_ratio
            )
            valid_results = [(emb, ts, ok) for emb, ts, ok in window_results if ok]

            if not valid_results:
                return (
                    IdentificationResult(uncertain=True, uncertainty_reason="所有窗口均提取失败"),
                    {"n_windows": n_windows, "n_valid": 0}
                )

            embeddings = [emb for emb, _, _ in valid_results]
            timestamps = [ts for _, ts, _ in valid_results]

            print(
                f"[Registry-Vote] 多窗口提取完成: {len(embeddings)}/{n_windows} 有效窗口, "
                f"位置={timestamps}"
            )

            # Step 2: 投票融合识别（传入 track_id 用于日志关联）
            fused_matches = self.matching_engine.match_with_voting(
                embeddings, top_k=top_k, vote_method=vote_method, track_id=track_id
            )

            if not fused_matches:
                return (
                    IdentificationResult(uncertain=True, uncertainty_reason="投票匹配无结果"),
                    {"n_valid": len(valid_results)}
                )

            # Step 3: 附加姓名和角色
            for m in fused_matches:
                profile = self.speakers.get(m.speaker_id)
                if profile:
                    m.name = profile.name
                    m.role = profile.role

            # Step 3b: 三层信号兜底纠正（v2 移植）
            # 在 VoteFusion 之后，用 Cosine/Mahalanobis/PLDA 三层独立信号做二次验证
            # 每层都对每个候选计算所有窗口的均值，取最高者作为该层的 top1
            # 多数层支持的候选才能确认为最终 top1
            all_candidate_ids = [m.speaker_id for m in fused_matches]
            cand_cos_means: dict[str, float] = {}
            cand_mahal_means: dict[str, float] = {}
            cand_plda_means: dict[str, float] = {}

            for sid in all_candidate_ids:
                cos_list, mahal_list, plda_list = [], [], []
                profile = self.speakers.get(sid)
                if profile is None:
                    continue

                emb_precision = getattr(profile, 'embedding_precision', None)
                emb_std = profile.embedding_std
                ind_embs = profile.individual_embeddings

                for emb in embeddings:
                    p = emb / (np.linalg.norm(emb) + 1e-8)
                    reg_emb = profile.embedding
                    if reg_emb is None:
                        continue

                    # Layer 1: Best-of-N Cosine
                    if ind_embs:
                        cos_scores = [float(np.dot(p, e)) for e in ind_embs]
                        cos_list.append(max(cos_scores))
                    else:
                        cos_list.append(float(np.dot(p, reg_emb)))

                    # Layer 2: Mahalanobis Distance
                    if emb_precision is not None and ind_embs and len(ind_embs) >= 3:
                        mahal = SpeakerModelTrainer.compute_mahalanobis_distance(
                            p, reg_emb, emb_precision
                        )
                        mahal_score = float(np.clip(1.0 / (1.0 + mahal * 0.1), 0.0, 1.0))
                    elif emb_std is not None and ind_embs and len(ind_embs) >= 2:
                        diff = p - reg_emb
                        mahal_sq = np.sum((diff ** 2) / (emb_std ** 2 + 1e-8))
                        mahal = np.sqrt(mahal_sq)
                        mahal_score = float(np.clip(1.0 / (1.0 + mahal * 0.1), 0.0, 1.0))
                    else:
                        n = len(ind_embs) if ind_embs else 0
                        mahal_score = min(1.0, (n + 1) / 3)
                    mahal_list.append(mahal_score)

                    # Layer 3: PLDA Score
                    if emb_precision is not None:
                        plda_score, _, _ = SpeakerModelTrainer.compute_plda_score(
                            p, reg_emb, emb_precision,
                            global_mean=self.matching_engine._global_mean,
                            within_cov=self.matching_engine._within_cov,
                            between_cov=self.matching_engine._between_cov,
                        )
                    else:
                        # 无精度信息时使用余弦相似度作为 fallback
                        cos_sim = float(np.dot(p, reg_emb))
                        plda_score = (cos_sim + 1.0) / 2.0
                    plda_list.append(plda_score)

                cand_cos_means[sid] = float(np.mean(cos_list)) if cos_list else 0.0
                cand_mahal_means[sid] = float(np.mean(mahal_list)) if mahal_list else 0.0
                cand_plda_means[sid] = float(np.mean(plda_list)) if plda_list else 0.0

            # 每层的 top1
            top1_by_cos = max(cand_cos_means, key=lambda s: cand_cos_means[s]) if cand_cos_means else None
            top1_by_mahal = max(cand_mahal_means, key=lambda s: cand_mahal_means[s]) if cand_mahal_means else None
            top1_by_plda = max(cand_plda_means, key=lambda s: cand_plda_means[s]) if cand_plda_means else None

            fused_top1 = fused_matches[0].speaker_id
            top1_layers = [top1_by_cos, top1_by_mahal, top1_by_plda]

            # 多数层（>=2/3）同意才纠正
            if fused_top1 not in top1_layers:
                # fused top1 在三层中没有获得任何层的支持，强制纠正
                top1_count = sum(1 for t in top1_layers if t == top1_layers[0])
                if top1_layers[0] is not None and top1_count >= 2:
                    real_top1 = top1_layers[0]
                    if real_top1 != fused_top1:
                        print(
                            f"[Registry-Vote] 三层纠正: fused_top1={fused_top1} 在三层中无支持，"
                            f"多数层({top1_count}/3)认 top1={real_top1}，互换"
                        )
                        # 找到 real_top1 对应的 match 并交换
                        for i, m in enumerate(fused_matches):
                            if m.speaker_id == real_top1:
                                fused_matches[0], fused_matches[i] = fused_matches[i], fused_matches[0]
                                break
            elif top1_layers.count(fused_top1) == 1 and len(set(top1_layers)) > 1:
                # fused top1 只被 1/3 层支持，另外两层都支持另一个人
                other_layers = [t for t in top1_layers if t != fused_top1]
                if other_layers and other_layers[0] == other_layers[1]:
                    # 另外两层一致同意另一个候选
                    real_top1 = other_layers[0]
                    print(
                        f"[Registry-Vote] 三层纠正: fused={fused_top1}(cos={cand_cos_means.get(fused_top1, 0):.4f}) "
                        f"只被1/3层支持，2/3层认 top1={real_top1}(cos={cand_cos_means.get(real_top1, 0):.4f})，互换"
                    )
                    for i, m in enumerate(fused_matches):
                        if m.speaker_id == real_top1:
                            fused_matches[0], fused_matches[i] = fused_matches[i], fused_matches[0]
                            break

            # Step 4: 更新识别历史（用纠正后的 top-1）
            self.matching_engine.record_identification(
                fused_matches[0].speaker_id, fused_matches[0].final_score
            )
            self._recent_scores.append(fused_matches[0].final_score)
            if len(self._recent_scores) > 100:
                self._recent_scores.pop(0)

            # Step 5: 分段一致性验证（Best-of-N + 窗口互相印证）
            top1_id = fused_matches[0].speaker_id
            top1_ind_embs = self.speakers[top1_id].individual_embeddings
            n_top1 = len(top1_ind_embs) if top1_ind_embs else 0

            # 5a: 每个窗口对 top-1 的 Best-of-N cosine
            top1_window_scores = []
            for emb in embeddings:
                p = emb / (np.linalg.norm(emb) + 1e-8)
                if n_top1 > 0:
                    scores = [float(np.dot(p, e)) for e in top1_ind_embs]
                    top1_window_scores.append(max(scores))
                else:
                    reg = self.speakers[top1_id].embedding
                    top1_window_scores.append(float(np.dot(p, reg)))

            # 5b: 窗口之间的互一致性（top-1 视角）
            # 同一人说话，各窗口 embedding 两两相似度高 → 一致
            # 若某窗口与其他窗口都远 → 可能不是该说话人
            if len(embeddings) >= 2:
                p_list = [emb / (np.linalg.norm(emb) + 1e-8) for emb in embeddings]
                pair_sims = []
                for i in range(len(p_list)):
                    for j in range(i + 1, len(p_list)):
                        pair_sims.append(float(np.dot(p_list[i], p_list[j])))
                window_consistency = float(np.mean(pair_sims))
            else:
                window_consistency = 1.0

            # 5c: 综合一致性 = 窗口对 top-1 的 Best-of-N 均值 × 窗口互一致性
            consistency = float(np.mean(top1_window_scores)) * window_consistency

            # Step 6: 计算动态阈值
            threshold = self._threshold_controller.compute_threshold(
                len(self.speakers), self._recent_scores, use_normalized=True
            )

            # Step 7: 判断 uncertain
            top = fused_matches[0]
            second_score = fused_matches[1].final_score if len(fused_matches) > 1 else 0.0
            uncertain = (
                top.confidence < 0.50
                or top.final_score < threshold
                or (top.final_score - second_score) < 0.05
                or consistency < 0.55
            )

            print(
                f"[Registry-Vote] 最终结果: {top1_id} (score={top.final_score:.4f}, "
                f"conf={top.confidence:.4f}, consis={consistency:.4f}, "
                f"win_consis={window_consistency:.4f}, "
                f"thr={threshold:.4f}, uncertain={uncertain})"
            )

            stats = {
                "n_windows": n_windows,
                "n_valid": len(valid_results),
                "window_timestamps_sec": [round(t, 3) for t in timestamps],
                "vote_method": vote_method,
                "fusion_method": fusion_method,
                "top1_consistency": round(consistency, 4),
                "window_consistency": round(window_consistency, 4),
                "top1_window_scores": {
                    f"win_{idx}": round(s, 4)
                    for idx, s in enumerate(top1_window_scores)
                },
                "threshold_used": round(threshold, 4),
            }

            result = IdentificationResult(
                matches=fused_matches,
                uncertain=uncertain,
            )
            if uncertain:
                reason = self._get_uncertainty_reason(fused_matches, threshold)
                if consistency < 0.55:
                    reason = f"分段一致性低 ({consistency:.3f})，" + reason
                result.uncertainty_reason = reason

            return result, stats

        except Exception as e:
            print(f"[Registry-Vote] 多窗口识别异常: {e}")
            import traceback
            traceback.print_exc()
            return (
                IdentificationResult(uncertain=True, uncertainty_reason=f"异常: {e}"),
                {}
            )

    async def identify_with_voting_async(
        self,
        audio_sample: np.ndarray,
        n_windows: int = 3,
        window_step_ratio: float = 0.25,
        fusion_method: str = "mean",
        vote_method: str = "score_weighted",
        top_k: Optional[int] = None,
        track_id: Optional[int] = None,
    ) -> tuple[IdentificationResult, dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.identify_with_voting,
            audio_sample, n_windows, window_step_ratio, fusion_method, vote_method, top_k, track_id
        )

    # ==================== 更新 API ====================

    def update_speaker(
        self,
        speaker_id: str,
        new_audio_sample: np.ndarray,
        weight: float = 0.15
    ) -> bool:
        """
        用新样本增量更新说话人声纹（在线学习）
        使用较小的 weight 避免新样本覆盖原有特征
        """
        if speaker_id not in self.speakers:
            return False

        try:
            new_emb = self.extractor.extract(new_audio_sample)
            new_emb = new_emb / (np.linalg.norm(new_emb) + 1e-8)

            profile = self.speakers[speaker_id]
            if profile.embedding is None:
                profile.embedding = new_emb
            else:
                profile.embedding = (
                    (1 - weight) * profile.embedding
                    + weight * new_emb
                )
                profile.embedding = profile.embedding / (
                    np.linalg.norm(profile.embedding) + 1e-8
                )

            profile.sample_count += 1
            profile.audio_samples.append(new_audio_sample)
            profile.individual_embeddings.append(new_emb)

            upd_emb_std = None
            if len(profile.individual_embeddings) > 1:
                embs_n = [e / (np.linalg.norm(e) + 1e-8) for e in profile.individual_embeddings]
                upd_emb_std = np.std(embs_n, axis=0)

            self.matching_engine.register_speaker(
                speaker_id, profile.embedding, profile.individual_embeddings, upd_emb_std
            )

            print(f"[Registry] 更新说话人「{speaker_id}」，样本数: {profile.sample_count}")
            return True

        except Exception as e:
            print(f"[Registry] 更新声纹失败: {e}")
            return False

    # ==================== 管理 API ====================

    def unregister_speaker(self, speaker_id: str) -> bool:
        """删除已注册的说话人"""
        if speaker_id not in self.speakers:
            return False

        del self.speakers[speaker_id]
        self.matching_engine.unregister_speaker(speaker_id)
        self._update_threshold()
        print(f"[Registry] 已删除说话人: {speaker_id}")
        return True

    def list_speakers(self, with_info: bool = False) -> List[Dict]:
        """列出已注册的说话人"""
        if not with_info:
            return list(self.speakers.keys())

        return [
            {
                "speaker_id": spk.speaker_id,
                "name": spk.name,
                "role": spk.role,
                "sample_count": spk.sample_count,
                "quality": spk.registration_quality,
            }
            for spk in self.speakers.values()
        ]

    def get_speaker(self, speaker_id: str) -> Optional[SpeakerProfile]:
        return self.speakers.get(speaker_id)

    def set_threshold(self, threshold: float):
        self.threshold = float(np.clip(threshold, 0.0, 1.0))

    def clear_all(self):
        self.speakers.clear()
        self.matching_engine = CascadeMatchingEngine()
        self._speaker_counter = 0
        self._recent_scores.clear()
        self._update_threshold()

    def get_threshold(self) -> float:
        return self._threshold_controller.compute_threshold(
            len(self.speakers), self._recent_scores, use_normalized=True
        )

    def get_stats(self) -> Dict:
        return {
            "registered_count": len(self.speakers),
            "current_threshold": self.get_threshold(),
            "recent_score_avg": float(np.mean(self._recent_scores)) if self._recent_scores else 0.0,
            "recent_score_count": len(self._recent_scores),
        }

    # ==================== 工具方法 ====================

    def _update_threshold(self):
        self.threshold = self._threshold_controller.compute_threshold(
            len(self.speakers), self._recent_scores, use_normalized=True
        )

    def _get_uncertainty_reason(self, matches: List[SpeakerMatch],
                                  threshold: float) -> str:
        if len(matches) == 1:
            if matches[0].confidence < 0.5:
                return f"置信度过低({matches[0].confidence:.2f})"
            if matches[0].final_score < threshold:
                return f"得分低于阈值({matches[0].final_score:.3f} < {threshold:.3f})"
            return "识别不确定"

        top = matches[0]
        second = matches[1]
        gap = top.final_score - second.final_score

        if gap < 0.05:
            return f"前两名得分接近({top.final_score:.3f} vs {second.final_score:.3f})，无法区分"
        if top.confidence < 0.5:
            return f"最高置信度过低({top.confidence:.2f})"
        return "识别存在不确定性"

    # ==================== 数据库持久化集成 ====================

    def _init_db(self, db_path: Optional[str] = None) -> SpeakerDatabase:
        """初始化数据库（懒加载，只在首次调用时创建）"""
        if self._db is None:
            self._db = SpeakerDatabase(db_path)
        return self._db

    def save_to_db(self, speaker_id: str, db_path: Optional[str] = None) -> bool:
        """
        将指定说话人的声纹保存到数据库。
        用于注册成功后持久化，无需重启即可被后续服务实例读取。

        兼容路径：
            1. registry.save_to_db("emp_001")  — 使用已关联的 DB 实例
            2. registry.save_to_db("emp_001", db_path="/custom/path.db") — 临时指定路径
        """
        if speaker_id not in self.speakers:
            return False

        profile = self.speakers[speaker_id]
        db = self._init_db(db_path)
        return db.save_from_profile(profile, overwrite=True)

    def save_all_to_db(self, db_path: Optional[str] = None) -> int:
        """
        将内存中所有说话人批量写入数据库。
        用于批量导入场景或定期备份。
        """
        if not self.speakers:
            return 0
        db = self._init_db(db_path)
        return db.save_batch(list(self.speakers.values()))

    def load_from_db(
        self,
        db_path: Optional[str] = None,
        active_only: bool = True,
        department: Optional[str] = None
    ) -> int:
        """
        从数据库加载说话人到内存注册表。
        服务启动时调用一次，之后所有识别均在内存中完成。

        Args:
            db_path:       数据库路径（None=使用已关联的 DB 实例）
            active_only:   是否只加载在职员工
            department:    可选，指定部门，仅加载该部门的声纹

        Returns:
            实际加载的说话人数量

        典型用法：
            # 启动时，加载全公司在职员工
            registry = MultiSpeakerRegistry(model_manager)
            loaded = registry.load_from_db()

            # 或者，只加载某部门参会人员
            loaded = registry.load_from_db(department="研发部")
        """
        db = self._init_db(db_path)

        if department:
            rows = db.load_by_department(department)
        else:
            rows = db.load_all(active_only=active_only)

        loaded = 0
        for row in rows:
            emb = row.get("embedding")
            if emb is None:
                continue

            # 如果内存中已有（来自 load_from_db + 后续动态注册），跳过
            if row["speaker_id"] in self.speakers:
                continue

            reg_result = self.register_embedding(
                speaker_id=row["speaker_id"],
                embedding=emb,
                name=row.get("name"),
                role=row.get("role"),
                force=True,
            )
            if reg_result.success:
                # 回填 profile 中数据库独有的字段
                profile = self.speakers.get(row["speaker_id"])
                if profile:
                    profile.sample_count = row.get("sample_count", profile.sample_count)
                    profile.registration_quality = row.get("quality", 0.0)
                    if row.get("embedding_mean") is not None:
                        profile.embedding_mean = row["embedding_mean"]
                    if row.get("embedding_std") is not None:
                        profile.embedding_std = row["embedding_std"]
                    if row.get("individual_embeddings"):
                        profile.individual_embeddings = row.get("individual_embeddings", [])
                        norm_embs = [
                            e / (np.linalg.norm(e) + 1e-8)
                            for e in profile.individual_embeddings
                        ]
                        self.matching_engine.registered_individual_embs[row["speaker_id"]] = norm_embs
                    if row.get("embedding_std") is not None:
                        self.matching_engine.registered_emb_stds[row["speaker_id"]] = row["embedding_std"]
                loaded += 1

        return loaded

    def sync_to_db(self, speaker_id: str, db_path: Optional[str] = None) -> bool:
        """
        将说话人增量更新（调用 update_speaker 后）同步写入数据库。
        等价于 save_to_db，但语义上表示"同步更新"。
        """
        return self.save_to_db(speaker_id, db_path)

    def remove_from_db(self, speaker_id: str, soft: bool = True, db_path: Optional[str] = None) -> bool:
        """
        从数据库中删除说话人。

        Args:
            speaker_id: 说话人 ID
            soft:       True=软删除（离职），False=物理删除

        Returns:
            操作是否成功
        """
        db = self._init_db(db_path)
        if soft:
            return db.deactivate_speaker(speaker_id)
        else:
            return db.delete_speaker(speaker_id)

    def get_db(self) -> Optional[SpeakerDatabase]:
        """获取当前关联的数据库实例"""
        return self._db


# ==================== 兼容旧接口 ====================

def create_multi_speaker_registry(
    model_manager: ModelManager,
    db_path: Optional[str] = None
) -> MultiSpeakerRegistry:
    """创建多说话人注册表的快捷函数"""
    return MultiSpeakerRegistry(model_manager, db_path=db_path)
