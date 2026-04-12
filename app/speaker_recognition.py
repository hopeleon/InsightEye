"""
说话人声纹识别模块
基于 CAM++ 模型，实现说话人注册、声纹比对和实时识别
"""

import asyncio
import numpy as np
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.model_manager import SpeakerEmbeddingExtractor, ModelManager


class SpeakerState(Enum):
    """说话人状态"""
    UNKNOWN = "unknown"       # 未知
    REGISTERED = "registered"  # 已注册
    IDENTIFIED = "identified"  # 已识别


@dataclass
class SpeakerProfile:
    """说话人档案"""
    speaker_id: str
    name: Optional[str] = None  # 可选的友好名称
    role: Optional[str] = None  # 角色：interviewer / candidate
    embedding: Optional[np.ndarray] = None  # 声纹向量
    sample_count: int = 0       # 样本数量
    audio_samples: List[np.ndarray] = field(default_factory=list)  # 原始音频样本


@dataclass
class SpeakerMatch:
    """说话人匹配结果"""
    speaker_id: str
    role: Optional[str]
    similarity: float
    confidence: float  # 置信度


@dataclass 
class RegistrationResult:
    """注册结果"""
    success: bool
    speaker_id: str
    sample_count: int
    embedding_quality: float  # 嵌入质量评估
    message: str


class SpeakerRecognizer:
    """
    说话人识别器
    使用 CAM++ 声纹模型进行说话人注册和识别
    """
    
    # 相似度阈值
    DEFAULT_THRESHOLD = 0.7
    MIN_SAMPLES_FOR_REGISTRATION = 2  # 最少需要的样本数
    
    def __init__(self, model_manager: ModelManager):
        """
        Args:
            model_manager: 模型管理器实例
        """
        self.model_manager = model_manager
        self.extractor = SpeakerEmbeddingExtractor(
            model_manager.get_camp_model(),
            device=model_manager.device
        )
        
        # 注册的说话人档案
        self.speakers: Dict[str, SpeakerProfile] = {}
        
        # 相似度阈值
        self.threshold = self.DEFAULT_THRESHOLD
        
        # 说话人计数器
        self._speaker_counter = 0
    
    def register_speaker(
        self,
        speaker_id: str,
        audio_samples: List[np.ndarray],
        name: Optional[str] = None,
        role: Optional[str] = None
    ) -> RegistrationResult:
        """
        注册说话人声纹
        
        Args:
            speaker_id: 说话人唯一标识
            audio_samples: 音频样本列表（每段至少 0.5 秒）
            name: 说话人名称（可选）
            role: 说话人角色（可选，如 "interviewer", "candidate"）
        
        Returns:
            RegistrationResult 注册结果
        """
        if len(audio_samples) < self.MIN_SAMPLES_FOR_REGISTRATION:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id,
                sample_count=len(audio_samples),
                embedding_quality=0.0,
                message=f"需要至少 {self.MIN_SAMPLES_FOR_REGISTRATION} 个音频样本，当前只有 {len(audio_samples)} 个"
            )
        
        embeddings = []
        quality_scores = []
        
        for sample in audio_samples:
            try:
                emb = self.extractor.extract(sample)
                embeddings.append(emb)
                
                # 简单质量评估：embedding 的 L2 范数（理想值接近 1）
                quality = np.linalg.norm(emb)
                quality_scores.append(quality)
                
            except Exception as e:
                print(f"[SpeakerRecognizer] 提取声纹失败: {e}")
                continue
        
        if not embeddings:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id,
                sample_count=0,
                embedding_quality=0.0,
                message="所有音频样本提取声纹失败"
            )
        
        # 平均多个样本得到最终声纹
        avg_embedding = np.mean(embeddings, axis=0)
        
        # 归一化
        avg_embedding = avg_embedding / (np.linalg.norm(avg_embedding) + 1e-8)
        
        # 计算平均质量
        avg_quality = np.mean(quality_scores) if quality_scores else 0.0
        
        # 创建说话人档案
        profile = SpeakerProfile(
            speaker_id=speaker_id,
            name=name,
            role=role,
            embedding=avg_embedding,
            sample_count=len(embeddings),
            audio_samples=audio_samples
        )
        
        self.speakers[speaker_id] = profile
        
        print(f"[SpeakerRecognizer] 注册说话人: {speaker_id}, 样本数: {len(embeddings)}, 质量: {avg_quality:.2f}")
        
        return RegistrationResult(
            success=True,
            speaker_id=speaker_id,
            sample_count=len(embeddings),
            embedding_quality=avg_quality,
            message=f"成功注册说话人 {speaker_id}"
        )

    def register_embedding(
        self,
        speaker_id: str,
        embedding: np.ndarray,
        name: Optional[str] = None,
        role: Optional[str] = None
    ) -> RegistrationResult:
        """
        直接用已提取的声纹 embedding 注册说话人（快速模式）
        """
        if embedding is None:
            return RegistrationResult(
                success=False,
                speaker_id=speaker_id,
                sample_count=0,
                embedding_quality=0.0,
                message="embedding 为空"
            )

        emb_norm = np.linalg.norm(embedding)

        profile = SpeakerProfile(
            speaker_id=speaker_id,
            name=name,
            role=role,
            embedding=embedding,
            sample_count=1,
            audio_samples=[]
        )

        self.speakers[speaker_id] = profile

        print(f"[SpeakerRecognizer] 注册说话人(embedding): {speaker_id}, 范数={emb_norm:.2f}")

        return RegistrationResult(
            success=True,
            speaker_id=speaker_id,
            sample_count=1,
            embedding_quality=emb_norm,
            message=f"成功注册说话人 {speaker_id}"
        )
    
    def identify_speaker(self, audio_sample: np.ndarray) -> Optional[SpeakerMatch]:
        """
        识别音频片段属于哪个已注册的说话人
        
        Args:
            audio_sample: 音频数据，float32，16kHz
        
        Returns:
            SpeakerMatch 如果匹配成功，否则 None
        """
        if not self.speakers:
            return None
        
        try:
            # 提取声纹
            embedding = self.extractor.extract(audio_sample)
            
            best_match: Optional[SpeakerMatch] = None
            best_similarity = 0.0
            
            for speaker_id, profile in self.speakers.items():
                if profile.embedding is None:
                    continue
                
                # 计算相似度
                similarity = self.extractor.compute_similarity(
                    embedding, 
                    profile.embedding
                )
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = SpeakerMatch(
                        speaker_id=speaker_id,
                        role=profile.role,
                        similarity=similarity,
                        confidence=similarity  # 简化：置信度 = 相似度
                    )
            
            # 检查是否超过阈值
            if best_match and best_match.similarity >= self.threshold:
                return best_match
            
            return None
            
        except Exception as e:
            print(f"[SpeakerRecognizer] 识别说话人失败: {e}")
            return None
    
    async def identify_speaker_async(self, audio_sample: np.ndarray) -> Optional[SpeakerMatch]:
        """
        异步识别说话人（在后台线程执行）
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.identify_speaker,
            audio_sample
        )
    
    def register_interview_participants(
        self,
        interviewer_samples: List[np.ndarray],
        candidate_samples: List[np.ndarray]
    ) -> Tuple[RegistrationResult, RegistrationResult]:
        """
        注册面试双方说话人
        
        Args:
            interviewer_samples: 面试官的音频样本列表
            candidate_samples: 候选人的音频样本列表
        
        Returns:
            (interviewer_result, candidate_result)
        """
        interviewer_result = self.register_speaker(
            speaker_id="interviewer",
            audio_samples=interviewer_samples,
            name="面试官",
            role="interviewer"
        )
        
        candidate_result = self.register_speaker(
            speaker_id="candidate",
            audio_samples=candidate_samples,
            name="候选人",
            role="candidate"
        )
        
        return interviewer_result, candidate_result
    
    def update_speaker_embedding(
        self,
        speaker_id: str,
        new_audio_sample: np.ndarray,
        weight: float = 0.2
    ) -> bool:
        """
        用新的音频样本更新说话人的声纹（增量学习）
        
        Args:
            speaker_id: 说话人 ID
            new_audio_sample: 新音频样本
            weight: 新样本的权重（0-1），越大表示新样本影响越大
        
        Returns:
            True 如果更新成功
        """
        if speaker_id not in self.speakers:
            return False
        
        try:
            # 提取新样本的声纹
            new_embedding = self.extractor.extract(new_audio_sample)
            new_embedding = new_embedding / (np.linalg.norm(new_embedding) + 1e-8)
            
            profile = self.speakers[speaker_id]
            
            if profile.embedding is None:
                profile.embedding = new_embedding
            else:
                # 指数移动平均更新
                profile.embedding = (
                    (1 - weight) * profile.embedding + 
                    weight * new_embedding
                )
                # 重新归一化
                profile.embedding = profile.embedding / (
                    np.linalg.norm(profile.embedding) + 1e-8
                )
            
            profile.sample_count += 1
            profile.audio_samples.append(new_audio_sample)
            
            return True
            
        except Exception as e:
            print(f"[SpeakerRecognizer] 更新声纹失败: {e}")
            return False
    
    def get_speaker_info(self, speaker_id: str) -> Optional[SpeakerProfile]:
        """获取说话人信息"""
        return self.speakers.get(speaker_id)
    
    def list_speakers(self) -> List[str]:
        """列出所有已注册的说话人 ID"""
        return list(self.speakers.keys())
    
    def set_threshold(self, threshold: float) -> None:
        """设置相似度阈值"""
        self.threshold = max(0.0, min(1.0, threshold))
        print(f"[SpeakerRecognizer] 相似度阈值设置为: {self.threshold}")
    
    def clear_all(self) -> None:
        """清除所有注册的说话人"""
        self.speakers.clear()
        self._speaker_counter = 0


class InterviewSpeakerManager:
    """
    面试场景的说话人管理器
    封装面试开始的声纹注册流程
    """
    
    def __init__(self, speaker_recognizer: SpeakerRecognizer):
        self.recognizer = speaker_recognizer
        self.is_registered = False
        
        # 临时存储注册阶段的音频
        self._interviewer_samples: List[np.ndarray] = []
        self._candidate_samples: List[np.ndarray] = []
        self._current_phase: Optional[str] = None  # "interviewer" / "candidate"
    
    def start_registration(self) -> str:
        """
        开始注册流程，返回当前应该收集谁的音频
        
        Returns:
            "interviewer" 或 "candidate"
        """
        self._interviewer_samples = []
        self._candidate_samples = []
        self._current_phase = "interviewer"
        self.is_registered = False
        
        print("[InterviewSpeakerManager] 开始声纹注册流程")
        
        return self._current_phase
    
    def add_sample(self, speaker_type: str, audio_sample: np.ndarray) -> None:
        """
        添加一个音频样本到对应说话人的收集列表
        
        Args:
            speaker_type: "interviewer" 或 "candidate"
            audio_sample: 音频数据
        """
        if speaker_type == "interviewer":
            self._interviewer_samples.append(audio_sample)
        elif speaker_type == "candidate":
            self._candidate_samples.append(audio_sample)
    
    def finish_registration(self) -> Tuple[bool, str]:
        """
        完成注册，返回注册结果
        
        Returns:
            (success, message)
        """
        # 检查样本数量
        min_samples = SpeakerRecognizer.MIN_SAMPLES_FOR_REGISTRATION
        
        if len(self._interviewer_samples) < min_samples:
            return False, f"面试官音频样本不足（需要 {min_samples} 个）"
        
        if len(self._candidate_samples) < min_samples:
            return False, f"候选人音频样本不足（需要 {min_samples} 个）"
        
        # 注册说话人
        int_result, cand_result = self.recognizer.register_interview_participants(
            interviewer_samples=self._interviewer_samples,
            candidate_samples=self._candidate_samples
        )
        
        if int_result.success and cand_result.success:
            self.is_registered = True
            return True, "声纹注册成功"
        else:
            msg = []
            if not int_result.success:
                msg.append(f"面试官: {int_result.message}")
            if not cand_result.success:
                msg.append(f"候选人: {cand_result.message}")
            return False, "; ".join(msg)
    
    def get_registration_status(self) -> Dict:
        """获取当前注册状态"""
        min_samples = SpeakerRecognizer.MIN_SAMPLES_FOR_REGISTRATION
        
        return {
            "is_registered": self.is_registered,
            "current_phase": self._current_phase,
            "interviewer_samples": len(self._interviewer_samples),
            "candidate_samples": len(self._candidate_samples),
            "samples_needed": min_samples,
            "can_complete": (
                len(self._interviewer_samples) >= min_samples and
                len(self._candidate_samples) >= min_samples
            )
        }


def create_speaker_recognizer(model_manager: ModelManager) -> SpeakerRecognizer:
    """创建说话人识别器的快捷函数"""
    return SpeakerRecognizer(model_manager)
