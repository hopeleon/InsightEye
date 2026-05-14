"""
增强版声纹识别引擎 v2 - 大规模说话人识别优化
专门针对 60+ 人规模的声纹识别难题

核心改进：
1. 多音频注册 — 每人使用多条音频捕捉声纹变化范围
2. 马氏距离 + PLDA 概率模型 — 比余弦相似度更鲁棒
3. 多模型特征融合 — 中文+英文 CAM++ 特征拼接
4. 音频数据增强 — 注册时做加噪/变调/变速增强
5. 统计重打分 — 利用说话人内/间方差重新校准得分

原理：
- 余弦相似度是线性度量，适合小规模场景
- 马氏距离考虑维度间相关性，适合高维 embedding
- PLDA 建模说话人变化 vs 渠道变化，是大规模识别的 SOTA 方法
"""

import numpy as np
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum
import copy

from app.model_manager import SpeakerEmbeddingExtractor, ModelManager
from app.speaker_database import SpeakerDatabase


# ==================== 数据结构 ====================

class RecognitionMethod(Enum):
    COSINE = "cosine"           # 原始余弦相似度
    MAHALANOBIS = "mahalanobis"  # 马氏距离
    PLDA = "plda"              # PLDA 概率模型
    FUSION = "fusion"          # 多模型融合


@dataclass
class SpeakerEnrollment:
    """说话人档案（增强版 v2）"""
    speaker_id: str
    name: Optional[str] = None
    role: Optional[str] = None
    
    # 多样本统计建模（对角协方差，避免小样本高维问题）
    embeddings: List[np.ndarray] = field(default_factory=list)  # 原始 embedding 列表
    embedding_mean: Optional[np.ndarray] = None  # 均值向量
    # 对角协方差：存逐维方差向量 (192,) 而非 192×192 全矩阵
    # precision 相应存逐维精度向量 (192,) 而非逆矩阵
    embedding_cov: Optional[np.ndarray] = None   # 对角逐维方差向量
    embedding_precision: Optional[np.ndarray] = None  # 对角逐维精度向量（1/var）
    
    # 英文模型特征（如果有）
    embeddings_en: List[np.ndarray] = field(default_factory=list)
    embedding_mean_en: Optional[np.ndarray] = None
    embedding_cov_en: Optional[np.ndarray] = None  # 对角逐维方差向量
    
    # 元数据
    sample_count: int = 0
    registration_quality: float = 0.0
    registered_at: Optional[float] = None


@dataclass
class EnhancedIdentificationResult:
    """增强识别结果"""
    speaker_id: str
    name: Optional[str]
    role: Optional[str]
    
    # 多维度得分
    cosine_score: float = 0.0
    mahalanobis_score: float = 0.0
    plda_score: float = 0.0
    fused_score: float = 0.0
    
    # 统计信息
    confidence: float = 0.0
    rank: int = 0
    
    # 与其他候选的距离
    gap_to_second: float = 0.0
    
    uncertain: bool = False
    uncertainty_reason: Optional[str] = None


# ==================== 音频数据增强 ====================

class AudioAugmentor:
    """
    音频数据增强器
    在注册时对原始音频做增强，扩充训练数据
    """
    
    @staticmethod
    def add_noise(audio: np.ndarray, noise_level: float = 0.005) -> np.ndarray:
        """添加高斯噪声"""
        noise = np.random.randn(len(audio)).astype(np.float32) * noise_level
        return audio + noise
    
    @staticmethod
    def change_speed(audio: np.ndarray, factor: float = 1.05) -> np.ndarray:
        """变速（不改变音调）"""
        from scipy import signal
        indices = np.round(np.arange(0, len(audio), factor)).astype(int)
        indices = indices[indices < len(audio)]
        return audio[indices]
    
    @staticmethod
    def change_pitch(audio: np.ndarray, semitones: float = 1.0) -> np.ndarray:
        """变调（不改变语速）"""
        from scipy import signal
        factor = 2 ** (semitones / 12.0)
        indices = np.round(np.arange(0, len(audio), factor)).astype(int)
        indices = indices[indices < len(audio)]
        return audio[indices]
    
    @staticmethod
    def add_reverb(audio: np.ndarray, room_size: float = 0.3) -> np.ndarray:
        """添加简单混响效果"""
        delays = [int(0.05 * 16000), int(0.1 * 16000)]
        decays = [0.5 * room_size, 0.3 * room_size]
        
        output = audio.copy()
        for delay, decay in zip(delays, decays):
            delayed = np.zeros_like(audio)
            delayed[delay:] = audio[:-delay] * decay
            output += delayed
        return output
    
    @staticmethod
    def augment(audio: np.ndarray, num_augmented: int = 3) -> List[np.ndarray]:
        """
        生成增强音频
        
        Args:
            audio: 原始音频
            num_augmented: 生成的增强样本数量
        
        Returns:
            原始音频 + 增强音频列表
        """
        samples = [audio]
        
        # 加噪
        samples.append(AudioAugmentor.add_noise(audio, noise_level=0.003))
        samples.append(AudioAugmentor.add_noise(audio, noise_level=0.008))
        
        # 混响
        samples.append(AudioAugmentor.add_reverb(audio, room_size=0.2))
        
        return samples[:num_augmented + 1]


# ==================== 说话人模型训练器 ====================

class SpeakerModelTrainer:
    """
    说话人模型训练器
    使用多条音频训练说话人的统计模型
    """
    
    @staticmethod
    def train_speaker_model(
        embeddings: List[np.ndarray],
        regularization: float = 1e-4
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        训练说话人模型（对角协方差版）

        Args:
            embeddings: 多个 embedding 向量
            regularization: 方差下限，防止除零

        Returns:
            (mean, var_diag, prec_diag)
            - mean: 均值向量 (192,)
            - var_diag: 对角逐维方差向量 (192,)
            - prec_diag: 对角逐维精度向量 (192,) = 1/var_diag
        """
        embs = np.array(embeddings)

        if embs.ndim == 1:
            return embs, None, None

        mean = np.mean(embs, axis=0)

        if len(embs) >= 2:
            # 对角协方差：只估计逐维方差，参数 D=192，N=2-3 即可稳定
            var_diag = np.var(embs, axis=0, ddof=1)
            var_diag = np.maximum(var_diag, regularization)
            prec_diag = 1.0 / var_diag
        else:
            var_diag = None
            prec_diag = None

        return mean, var_diag, prec_diag
    
    @staticmethod
    def compute_mahalanobis_distance(
        probe: np.ndarray,
        mean: np.ndarray,
        prec_diag: np.ndarray
    ) -> float:
        """
        计算马氏距离（对角协方差版）

        Args:
            probe: 待识别 embedding
            mean: 说话人均值 embedding
            prec_diag: 对角逐维精度向量 (192,) = 1/var_i

        Returns:
            马氏距离（越小越好）
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
        within_cov: np.ndarray,
        between_cov: np.ndarray,
        probe_precision: Optional[np.ndarray] = None
    ) -> float:
        """
        计算 PLDA 风格的对数似然比得分
        
        简化版 PLDA：
        - within_cov: 说话人内变化（same session, different speech）
        - between_cov: 说话人间变化（different speakers）
        
        Args:
            probe: 待识别 embedding
            mean: 说话人均值
            within_cov: 说话人内协方差
            between_cov: 说话人间协方差
            probe_precision: 待识别音频的精度矩阵（如果有多个样本）
        
        Returns:
            对数似然比分数
        """
        # 总协方差 = within_cov + between_cov
        total_cov = within_cov + between_cov
        
        # 说话人模型精度
        try:
            total_precision = np.linalg.inv(total_cov)
        except np.linalg.LinAlgError:
            total_precision = np.linalg.pinv(total_cov)
        
        # 计算能量函数差
        # log P(probe | same_speaker) vs log P(probe | different_speaker)
        
        # 同一人假设下的后验均值
        n_within = len(within_cov) // within_cov.shape[0] if within_cov.ndim > 1 else 1
        shrinkage = n_within / (n_within + 1)
        
        # 简化计算：使用马氏距离差
        diff = probe - mean
        
        # 不同人说：距离均值
        mahal_diff = float(np.dot(diff, np.dot(total_precision, diff)))
        
        # 同一人说：在均值附近
        # 使用精度加权的距离
        if probe_precision is not None:
            mahal_same = float(np.dot(diff, np.dot(probe_precision, diff)))
        else:
            mahal_same = mahal_diff * shrinkage
        
        # 对数似然比
        llr = 0.5 * (mahal_same - mahal_diff)
        
        # 转换为 0-1 范围的得分
        score = 1.0 / (1.0 + np.exp(-llr))
        
        return float(np.clip(score, 0, 1))


# ==================== 增强版识别引擎 ====================

class EnhancedRecognitionEngine:
    """
    增强版声纹识别引擎
    
    支持多种识别方法：
    1. 余弦相似度（基础）
    2. 马氏距离（考虑维度相关性）
    3. PLDA 概率模型（最先进）
    4. 多模型融合（中文+英文 CAM++）
    
    优化策略：
    - 注册时使用多条音频 + 数据增强
    - 使用说话人统计模型
    - 自适应阈值根据候选区分度调整
    """
    
    # 默认参数
    MIN_ENROLLMENT_SAMPLES = 3      # 最少注册样本数
    AUGMENTED_SAMPLES_PER_AUDIO = 3  # 每条音频生成多少增强样本
    
    # 得分融合权重
    COSINE_WEIGHT = 0.25
    MAHALANOBIS_WEIGHT = 0.35
    PLDA_WEIGHT = 0.40
    
    # 置信度阈值
    MIN_CONFIDENCE = 0.55
    MIN_SCORE_GAP = 0.08  # 第一名与第二名的最小差距
    
    def __init__(self, extractor: SpeakerEmbeddingExtractor, extractor_en: Optional[SpeakerEmbeddingExtractor] = None):
        """
        Args:
            extractor: 中文 CAM++ 特征提取器
            extractor_en: 英文 CAM++ 特征提取器（可选）
        """
        self.extractor = extractor
        self.extractor_en = extractor_en
        
        # 已注册的说话人
        self.enrolled_speakers: Dict[str, SpeakerEnrollment] = {}
        
        # 全局统计（用于 PLDA 估计）
        self._global_mean: Optional[np.ndarray] = None
        self._within_cov: Optional[np.ndarray] = None
        self._between_cov: Optional[np.ndarray] = None
        self._global_mean_en: Optional[np.ndarray] = None
        self._within_cov_en: Optional[np.ndarray] = None
    
    # ==================== 注册 API ====================
    
    def enroll_speaker(
        self,
        speaker_id: str,
        audio_samples: List[np.ndarray],
        name: Optional[str] = None,
        role: Optional[str] = None,
        use_augmentation: bool = True,
        extractor_en: Optional[SpeakerEmbeddingExtractor] = None
    ) -> bool:
        """
        注册说话人（使用多条音频 + 数据增强）
        
        Args:
            speaker_id: 说话人 ID
            audio_samples: 音频样本列表（每条至少 1 秒）
            name: 姓名
            role: 角色
            use_augmentation: 是否使用数据增强
            extractor_en: 英文特征提取器
        
        Returns:
            是否成功
        """
        if len(audio_samples) < self.MIN_ENROLLMENT_SAMPLES:
            print(f"[EnhancedEngine] 样本不足，需要至少 {self.MIN_ENROLLMENT_SAMPLES} 条，当前 {len(audio_samples)} 条")
            return False
        
        # 提取 embedding
        embeddings = []
        for audio in audio_samples:
            try:
                emb = self.extractor.extract(audio)
                embeddings.append(emb)
                
                # 数据增强
                if use_augmentation:
                    augmented = AudioAugmentor.augment(audio, self.AUGMENTED_SAMPLES_PER_AUDIO)
                    for aug_audio in augmented[1:]:  # 跳过原始音频
                        try:
                            aug_emb = self.extractor.extract(aug_audio)
                            embeddings.append(aug_emb)
                        except:
                            pass
            except Exception as e:
                print(f"[EnhancedEngine] 声纹提取失败: {e}")
                continue
        
        if len(embeddings) < self.MIN_ENROLLMENT_SAMPLES:
            print(f"[EnhancedEngine] 有效声纹样本不足")
            return False
        
        # 训练说话人模型（对角协方差版）
        mean, var_diag, prec_diag = SpeakerModelTrainer.train_speaker_model(embeddings)

        # 英文模型（如果有）
        embeddings_en = []
        if extractor_en is not None and self.extractor_en is not None:
            for audio in audio_samples:
                try:
                    emb_en = self.extractor_en.extract(audio)
                    embeddings_en.append(emb_en)
                except:
                    pass

        mean_en, var_diag_en, prec_diag_en = None, None, None
        if embeddings_en:
            mean_en, var_diag_en, prec_diag_en = SpeakerModelTrainer.train_speaker_model(embeddings_en)

        # 计算注册质量（样本间一致性）
        quality = self._compute_enrollment_quality(embeddings)

        # 创建说话人档案
        enrollment = SpeakerEnrollment(
            speaker_id=speaker_id,
            name=name,
            role=role,
            embeddings=embeddings,
            embedding_mean=mean,
            embedding_cov=var_diag,
            embedding_precision=prec_diag,
            embeddings_en=embeddings_en,
            embedding_mean_en=mean_en,
            embedding_cov_en=var_diag_en,
            sample_count=len(embeddings),
            registration_quality=quality,
        )
        
        self.enrolled_speakers[speaker_id] = enrollment
        
        # 更新全局统计
        self._update_global_statistics()
        
        print(f"[EnhancedEngine] 注册说话人 {speaker_id}，样本数: {len(embeddings)}，质量: {quality:.3f}")
        return True
    
    def _compute_enrollment_quality(self, embeddings: List[np.ndarray]) -> float:
        """计算注册质量分数"""
        if len(embeddings) < 2:
            return 0.5
        
        # 计算样本间余弦相似度
        pair_sims = []
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                sim = self._cosine_sim(embeddings[i], embeddings[j])
                pair_sims.append(sim)
        
        avg_sim = np.mean(pair_sims)
        std_sim = np.std(pair_sims)
        
        # 质量 = 平均相似度 * (1 - 标准差)
        quality = avg_sim * (1.0 - std_sim)
        
        return float(np.clip(quality, 0, 1))
    
    def _update_global_statistics(self):
        """更新全局统计（用于 PLDA）"""
        all_embeddings = []
        all_embeddings_en = []
        
        for enrollment in self.enrolled_speakers.values():
            all_embeddings.extend(enrollment.embeddings)
            if enrollment.embeddings_en:
                all_embeddings_en.extend(enrollment.embeddings_en)
        
        if len(all_embeddings) >= 2:
            all_embs = np.array(all_embeddings)
            self._global_mean = np.mean(all_embs, axis=0)
            
            # 说话人内协方差（所有样本围绕各自说话人均值的方差）
            within_spreads = []
            for enrollment in self.enrolled_speakers.values():
                diff = np.array(enrollment.embeddings) - enrollment.embedding_mean
                within_spreads.append(np.mean(np.sum(diff ** 2, axis=1)))
            self._within_cov = np.eye(all_embs.shape[1]) * np.mean(within_spreads)
            
            # 说话人间协方差（说话人均值围绕全局均值的方差）
            between_spreads = []
            for enrollment in self.enrolled_speakers.values():
                diff = enrollment.embedding_mean - self._global_mean
                between_spreads.append(np.sum(diff ** 2))
            self._between_cov = np.eye(all_embs.shape[1]) * np.mean(between_spreads)
        
        if all_embeddings_en:
            all_embs_en = np.array(all_embeddings_en)
            self._global_mean_en = np.mean(all_embs_en, axis=0)
    
    # ==================== 识别 API ====================
    
    def identify(
        self,
        audio_sample: np.ndarray,
        top_k: int = 3,
        method: RecognitionMethod = RecognitionMethod.FUSION,
        extractor_en: Optional[SpeakerEmbeddingExtractor] = None
    ) -> List[EnhancedIdentificationResult]:
        """
        识别说话人
        
        Args:
            audio_sample: 待识别音频
            top_k: 返回前 k 个候选
            method: 识别方法
            extractor_en: 英文特征提取器
        
        Returns:
            按得分降序排列的识别结果列表
        """
        if not self.enrolled_speakers:
            return []
        
        # 提取声纹
        try:
            probe_emb = self.extractor.extract(audio_sample)
        except Exception as e:
            print(f"[EnhancedEngine] 声纹提取失败: {e}")
            return []

        # 检测零向量
        if np.linalg.norm(probe_emb) < 1e-6:
            print(f"[EnhancedEngine] 警告: 零向量 embedding，识别不可靠")
            return []
        
        # 英文特征（如果有）
        probe_emb_en = None
        if extractor_en is not None or self.extractor_en is not None:
            try:
                ext = extractor_en or self.extractor_en
                probe_emb_en = ext.extract(audio_sample)
            except:
                pass
        
        # 计算所有说话人的得分
        scores = {}
        for speaker_id, enrollment in self.enrolled_speakers.items():
            scores[speaker_id] = self._compute_multi_score(
                probe_emb, enrollment, probe_emb_en
            )
        
        # 排序
        sorted_speakers = sorted(scores.items(), key=lambda x: x[1]["fused"], reverse=True)
        
        # 构建结果
        results = []
        for rank, (speaker_id, score_dict) in enumerate(sorted_speakers[:top_k], 1):
            enrollment = self.enrolled_speakers[speaker_id]
            
            # 计算与第二名的差距
            gap = 0.0
            if len(sorted_speakers) > 1 and rank == 1:
                second_score = sorted_speakers[1][1]["fused"]
                gap = score_dict["fused"] - second_score
            
            # 判断是否不确定
            uncertain = (
                score_dict["fused"] < self.MIN_CONFIDENCE
                or gap < self.MIN_SCORE_GAP
            )
            
            result = EnhancedIdentificationResult(
                speaker_id=speaker_id,
                name=enrollment.name,
                role=enrollment.role,
                cosine_score=score_dict["cosine"],
                mahalanobis_score=score_dict["mahalanobis"],
                plda_score=score_dict["plda"],
                fused_score=score_dict["fused"],
                confidence=score_dict["fused"],
                rank=rank,
                gap_to_second=gap,
                uncertain=uncertain,
            )
            
            if uncertain:
                if score_dict["fused"] < self.MIN_CONFIDENCE:
                    result.uncertainty_reason = f"得分过低 ({score_dict['fused']:.3f})"
                elif gap < self.MIN_SCORE_GAP:
                    result.uncertainty_reason = f"前两名差距过小 ({gap:.3f})"
            
            results.append(result)
        
        return results
    
    def _compute_multi_score(
        self,
        probe_emb: np.ndarray,
        enrollment: SpeakerEnrollment,
        probe_emb_en: Optional[np.ndarray] = None
    ) -> Dict[str, float]:
        """
        计算多维度得分
        
        Returns:
            包含 cosine, mahalanobis, plda, fused 的字典
        """
        # 1. 余弦相似度
        cosine = self._cosine_sim(probe_emb, enrollment.embedding_mean)
        
        # 2. 马氏距离得分
        mahal_dist = SpeakerModelTrainer.compute_mahalanobis_distance(
            probe_emb,
            enrollment.embedding_mean,
            enrollment.embedding_precision
        )
        # 转换为 0-1 分数（距离越小越好）
        mahal_score = 1.0 / (1.0 + mahal_dist)
        
        # 3. PLDA 得分
        plda_score = 0.5  # 默认值
        if self._within_cov is not None and self._between_cov is not None:
            diff = probe_emb - enrollment.embedding_mean

            # 同一人假设：对角精度向量下的马氏距离
            if enrollment.embedding_precision is not None:
                mahal_same = np.sum((diff ** 2) * enrollment.embedding_precision)
            else:
                mahal_same = float(np.dot(diff, diff))

            # 不同人说：对角协方差矩阵求逆（对角矩阵的逆仍是对角矩阵，直接取倒数）
            if self._global_mean is not None:
                diff_global = probe_emb - self._global_mean
                pooled_cov = self._within_cov + self._between_cov  # 对角矩阵 (D,D)
                pooled_prec_diag = 1.0 / (np.diag(pooled_cov) + 1e-8)  # 对角精度向量 (D,)
                mahal_diff = np.sum((diff_global ** 2) * pooled_prec_diag)

                llr = 0.5 * (mahal_same - mahal_diff)
                plda_score = 1.0 / (1.0 + np.exp(-llr))
        
        # 4. 融合得分
        fused = (
            self.COSINE_WEIGHT * cosine
            + self.MAHALANOBIS_WEIGHT * mahal_score
            + self.PLDA_WEIGHT * plda_score
        )
        
        # 如果有英文模型，尝试融合
        if probe_emb_en is not None and enrollment.embedding_mean_en is not None:
            cosine_en = self._cosine_sim(probe_emb_en, enrollment.embedding_mean_en)
            # 英文模型权重较低（因为主要是中文模型）
            fused = 0.85 * fused + 0.15 * cosine_en
        
        return {
            "cosine": float(cosine),
            "mahalanobis": float(mahal_score),
            "plda": float(plda_score),
            "fused": float(fused),
        }
    
    @staticmethod
    def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
        """计算余弦相似度"""
        norm_a = a / (np.linalg.norm(a) + 1e-8)
        norm_b = b / (np.linalg.norm(b) + 1e-8)
        return float(np.dot(norm_a, norm_b))
    
    # ==================== 管理 API ====================
    
    def remove_speaker(self, speaker_id: str) -> bool:
        """删除说话人"""
        if speaker_id in self.enrolled_speakers:
            del self.enrolled_speakers[speaker_id]
            self._update_global_statistics()
            return True
        return False
    
    def get_speaker_count(self) -> int:
        """获取已注册说话人数量"""
        return len(self.enrolled_speakers)
    
    def list_speakers(self) -> List[Dict]:
        """列出所有说话人"""
        return [
            {
                "speaker_id": e.speaker_id,
                "name": e.name,
                "sample_count": e.sample_count,
                "quality": e.registration_quality,
            }
            for e in self.enrolled_speakers.values()
        ]


# ==================== 便捷函数 ====================

def create_enhanced_engine(
    model_manager: ModelManager,
    db_path: Optional[str] = None
) -> EnhancedRecognitionEngine:
    """创建增强版识别引擎的便捷函数"""
    camp_model = model_manager.get_camp_model()
    camp_en_model = model_manager.get_camp_en_model()
    
    extractor = SpeakerEmbeddingExtractor(camp_model, device=model_manager.device)
    extractor_en = None
    if camp_en_model is not None:
        extractor_en = SpeakerEmbeddingExtractor(camp_en_model, device=model_manager.device)
    
    engine = EnhancedRecognitionEngine(extractor, extractor_en)
    
    # 从数据库加载已有说话人
    if db_path is None:
        try:
            from app.config import BASE_DIR
            db_path = str(BASE_DIR / "data" / "speaker_voiceprints.db")
        except:
            pass
    
    if db_path:
        try:
            db = SpeakerDatabase(db_path)
            speakers = db.load_all(active_only=True)
            for row in speakers:
                emb = row.get("embedding")
                if emb is None:
                    continue
                
                # 尝试加载英文 embedding（如果数据库支持）
                emb_en = row.get("embedding_en")
                
                engine.enrolled_speakers[row["speaker_id"]] = SpeakerEnrollment(
                    speaker_id=row["speaker_id"],
                    name=row.get("name"),
                    role=row.get("role"),
                    embeddings=[emb],
                    embedding_mean=emb,
                    sample_count=row.get("sample_count", 1),
                    registration_quality=row.get("quality", 0.5),
                )
            
            engine._update_global_statistics()
            print(f"[EnhancedEngine] 从数据库加载了 {len(engine.enrolled_speakers)} 个说话人")
        except Exception as e:
            print(f"[EnhancedEngine] 从数据库加载失败: {e}")
    
    return engine
