"""
模型管理器 - 统一管理 FunASR、CAM++ 和 Silero VAD 模型的加载
"""

import os
import asyncio
from typing import Optional
from dataclasses import dataclass
import numpy as np

import torch

from funasr import AutoModel


@dataclass
class ModelPaths:
    """模型路径配置"""
    funasr_model: str
    campplus_model: str
    campplus_en_model: str
    device: str


def get_default_model_paths() -> ModelPaths:
    """从配置中获取默认模型路径（打印实际使用的路径）"""
    from . import config
    paths = ModelPaths(
        funasr_model=config.FUNASR_MODEL_DIR,
        campplus_model=config.CAMPPLUS_MODEL_DIR,
        campplus_en_model=config.CAMPPLUS_EN_MODEL_DIR,
        device=config.LOCAL_DEVICE
    )
    print(f"[ModelPaths] FunASR 模型路径: {paths.funasr_model}")
    print(f"[ModelPaths] CAM++ 中文模型路径: {paths.campplus_model}")
    print(f"[ModelPaths] CAM++ 英文模型路径: {paths.campplus_en_model}")
    print(f"[ModelPaths] 使用设备: {paths.device}")
    return paths


def _get_local_model_dir() -> str:
    """获取本地模型目录（用于 VAD 模型缓存）"""
    from . import config
    return config.LOCAL_MODEL_DIR


class ModelManager:
    """
    模型管理器 - 单例模式，全局共享模型实例
    
    使用方式:
        manager = ModelManager.get_instance()
        await manager.initialize()
        asr_model = manager.get_asr_model()
        camp_model = manager.get_camp_model()
    """
    
    _instance: Optional["ModelManager"] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        self.funasr_model = None  # FunASR 模型（VAD + ASR）
        self.camp_model = None     # CAM++ 中文声纹模型
        self.camp_en_model = None  # CAM++ 英文声纹模型
        self.vad_model = None      # Silero VAD
        self.vad_get_speech_timestamps = None  # Silero VAD 工具函数
        self.vad_model_samplerate = 16000
        self._initialized = False
        self._init_task: Optional[asyncio.Task] = None
        self._paths = get_default_model_paths()
    
    @classmethod
    def get_instance(cls) -> "ModelManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def initialize(self, paths: Optional[ModelPaths] = None) -> None:
        """
        初始化所有模型（在后台线程中加载，避免阻塞）
        
        Args:
            paths: 模型路径配置，如果为 None 则使用从配置读取的路径
        """
        if self._initialized:
            return
        
        if paths:
            self._paths = paths
        
        async with self._lock:
            if self._initialized:
                return
            
            print("[ModelManager] 开始加载模型...")
            print(f"[ModelManager] FunASR 模型路径 (实际): {self._paths.funasr_model}")
            print(f"[ModelManager] CAM++ 中文模型路径 (实际): {self._paths.campplus_model}")
            print(f"[ModelManager] CAM++ 英文模型路径 (实际): {self._paths.campplus_en_model}")
            print(f"[ModelManager] 使用设备: {self._paths.device}")
            
            # 在线程池中加载模型，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            
            # 依次加载，避免并行加载导致内存问题
            try:
                await loop.run_in_executor(None, self._load_vad)
                print("[ModelManager] Silero VAD 加载完成")
            except Exception as e:
                print(f"[ModelManager] Silero VAD 加载失败，将使用备选方案: {e}")
            
            try:
                await loop.run_in_executor(None, self._load_funasr)
                print("[ModelManager] FunASR 加载完成")
            except Exception as e:
                print(f"[ModelManager] FunASR 加载失败: {e}")
            
            try:
                await loop.run_in_executor(None, self._load_campplus)
                print("[ModelManager] CAM++ 中文声纹模型加载完成")
            except Exception as e:
                print(f"[ModelManager] CAM++ 中文声纹模型加载失败: {e}")
            
            try:
                await loop.run_in_executor(None, self._load_campplus_en)
                print("[ModelManager] CAM++ 英文声纹模型加载完成")
            except Exception as e:
                print(f"[ModelManager] CAM++ 英文声纹模型加载失败: {e}")
            
            self._initialized = True
            print("[ModelManager] 所有模型加载完成（或部分完成）！")
    
    def _load_funasr(self) -> None:
        """加载 FunASR 模型（使用本地路径）"""
        try:
            model_path = self._paths.funasr_model
            print(f"[ModelManager] 加载 FunASR 模型 from: {model_path}")
            
            # 验证模型目录存在
            if not os.path.exists(model_path):
                raise FileNotFoundError(f"FunASR 模型目录不存在: {model_path}")
            
            print(f"[ModelManager] FunASR 使用本地路径: {model_path}")
            
            from funasr import AutoModel
            
            # 方式1: 直接使用本地模型路径
            try:
                self.funasr_model = AutoModel(
                    model=model_path,
                    device=self._paths.device,
                    disable_update=True,
                    ncpu=4,
                )
            except Exception as e1:
                print(f"[ModelManager] 方式1失败，尝试方式2: {e1}")
                # 方式2: 使用 model_id 格式但指定本地目录
                model_id = "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
                self.funasr_model = AutoModel(
                    model=model_id,
                    model_revision="v2.0.4",
                    cache_dir=_get_local_model_dir(),
                    device=self._paths.device,
                    disable_update=True,
                    ncpu=4,
                )
            
            print(f"[ModelManager] FunASR 模型加载成功，使用设备: {self._paths.device}")
            
        except Exception as e:
            print(f"[ModelManager] FunASR 模型加载失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_campplus(self) -> None:
        """加载 CAM++ 中文声纹模型（直接加载模型类）"""
        try:
            model_dir = self._paths.campplus_model
            print(f"[ModelManager] 加载 CAM++ 中文声纹模型 from: {model_dir}")
            
            # 安装缺失的依赖
            try:
                import addict
            except ImportError:
                print("[ModelManager] 安装 addict 依赖...")
                import subprocess
                subprocess.run([torch.__file__.split('\\lib\\')[0] + "\\Scripts\\pip.exe", "install", "addict"], 
                             capture_output=True)
            
            # 检查模型文件是否存在
            if not os.path.exists(model_dir):
                raise FileNotFoundError(f"CAM++ 中文模型目录不存在: {model_dir}")
            
            # 直接加载 CAM++ 模型
            import yaml
            from funasr.models.campplus.model import CAMPPlus
            
            # 读取配置
            config_path = os.path.join(model_dir, "config.yaml")
            with open(config_path, 'r', encoding='utf-8') as f:
                model_conf = yaml.safe_load(f)
            
            # 创建模型实例
            camp_config = model_conf.get("model_conf", {})
            self.camp_model = CAMPPlus(
                feat_dim=camp_config.get("feat_dim", 80),
                embedding_size=camp_config.get("embedding_size", 192),
                growth_rate=camp_config.get("growth_rate", 32),
                bn_size=camp_config.get("bn_size", 4),
                init_channels=camp_config.get("init_channels", 128),
                config_str=camp_config.get("config_str", "batchnorm-relu"),
                memory_efficient=camp_config.get("memory_efficient", True),
                output_level=camp_config.get("output_level", "segment"),
            )
            
            # 加载权重（model_file 在顶层配置中）
            model_file = os.path.join(model_dir, model_conf.get("model_file") or "campplus_cn_common.bin")
            print(f"[ModelManager] CAM++ 中文模型权重文件: {model_file}")
            state_dict = torch.load(model_file, map_location=self._paths.device)
            self.camp_model.load_state_dict(state_dict, strict=False)
            self.camp_model.to(self._paths.device)
            self.camp_model.eval()
            
            print(f"[ModelManager] CAM++ 中文声纹模型加载成功")
            
        except Exception as e:
            print(f"[ModelManager] CAM++ 中文声纹模型加载失败: {e}")
            import traceback
            traceback.print_exc()

    def _load_campplus_en(self) -> None:
        """加载 CAM++ 英文声纹模型（VoxCeleb）"""
        try:
            model_dir = self._paths.campplus_en_model
            print(f"[ModelManager] 加载 CAM++ 英文声纹模型 from: {model_dir}")
            
            # 检查模型目录是否存在
            if not os.path.exists(model_dir):
                print(f"[ModelManager] CAM++ 英文模型目录不存在: {model_dir}，跳过加载")
                return
            
            import json
            from funasr.models.campplus.model import CAMPPlus
            
            # 读取配置（英文模型用 configuration.json）
            config_path = os.path.join(model_dir, "configuration.json")
            with open(config_path, 'r', encoding='utf-8') as f:
                model_conf = json.load(f)
            
            # 创建模型实例（英文模型参数不同）
            camp_config = model_conf.get("model", {}).get("model_config", {})
            self.camp_en_model = CAMPPlus(
                feat_dim=camp_config.get("fbank_dim", 80),
                embedding_size=camp_config.get("emb_size", 512),
                growth_rate=32,
                bn_size=4,
                init_channels=128,
                config_str="batchnorm-relu",
                memory_efficient=True,
                output_level="segment",
            )
            
            # 加载权重
            model_file = os.path.join(model_dir, model_conf.get("model", {}).get("pretrained_model", "campplus_voxceleb.bin"))
            print(f"[ModelManager] CAM++ 英文模型权重文件: {model_file}")
            state_dict = torch.load(model_file, map_location=self._paths.device)
            self.camp_en_model.load_state_dict(state_dict, strict=False)
            self.camp_en_model.to(self._paths.device)
            self.camp_en_model.eval()
            
            print(f"[ModelManager] CAM++ 英文声纹模型加载成功")
            
        except Exception as e:
            print(f"[ModelManager] CAM++ 英文声纹模型加载失败（不影响主功能）: {e}")
    
    def _load_vad(self) -> None:
        """加载 Silero VAD 模型（使用 torch.hub）"""
        try:
            print("[ModelManager] 加载 Silero VAD 模型（torch.hub）...")
            
            # 设置模型下载目录
            torch_hub_dir = os.path.join(_get_local_model_dir(), "silero-vad")
            print(f"[ModelManager] Silero VAD 缓存目录: {torch_hub_dir}")
            os.makedirs(torch_hub_dir, exist_ok=True)
            os.environ["TORCH_HUB_DIR"] = torch_hub_dir
            
            # 设置线程数以优化 CPU 推理
            torch.set_num_threads(1)
            
            # 使用 torch.hub 加载 Silero VAD
            model, utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                trust_repo=True
            )
            
            # 提取工具函数
            (get_speech_timestamps, _, read_audio, _, _) = utils
            
            self.vad_model = model
            self.vad_get_speech_timestamps = get_speech_timestamps
            self.vad_read_audio = read_audio
            
            print("[ModelManager] Silero VAD 模型加载成功")
            
        except Exception as e:
            print(f"[ModelManager] Silero VAD 模型加载失败: {e}")
            # 不抛出异常，让服务继续运行
    
    def get_asr_model(self):
        """获取 FunASR 模型"""
        return self.funasr_model
    
    def get_camp_model(self):
        """获取 CAM++ 中文声纹模型"""
        return self.camp_model
    
    def get_camp_en_model(self):
        """获取 CAM++ 英文声纹模型"""
        return self.camp_en_model
    
    def get_camp_pipeline(self):
        """获取 CAM++ ModelScope pipeline"""
        return getattr(self, 'camp_pipeline', None)
    
    def get_vad_model(self):
        """获取 Silero VAD 模型"""
        return self.vad_model
    
    def get_vad_tools(self):
        """获取 Silero VAD 工具函数"""
        return self.vad_get_speech_timestamps, self.vad_read_audio
    
    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized
    
    @property
    def device(self) -> str:
        """获取当前使用的设备"""
        return self._paths.device


class SpeakerEmbeddingExtractor:
    """
    说话人声纹特征提取器
    使用 CAM++ 模型提取音频的声纹向量
    """
    
    def __init__(self, camp_model, device="cuda"):
        """
        Args:
            camp_model: CAM++ 模型（从 ModelManager 获取）
            device: 模型设备
        """
        self.camp_model = camp_model
        self.device = device
        self.sample_rate = 16000
    
    def extract(self, audio_data: np.ndarray) -> np.ndarray:
        """
        从音频数据中提取声纹特征向量
        
        Args:
            audio_data: numpy 数组，16kHz 采样率，float32 格式，范围 [-1, 1]
        
        Returns:
            192 维声纹向量（CAM++ 输出维度）
        """
        if self.camp_model is None:
            raise RuntimeError("CAM++ 模型未加载")
        
        try:
            import torch
            from funasr.models.campplus.utils import extract_feature
            from funasr.utils.load_utils import load_audio_text_image_video
            
            # 将 numpy 数组转换为 torch tensor
            audio_tensor = torch.from_numpy(audio_data).float()
            audio_list = [audio_tensor]
            
            # 提取 fbank 特征
            features_padded, feature_lengths, feature_times = extract_feature(audio_list)
            features_padded = features_padded.to(device=self.device)
            
            # 使用 CAM++ 模型提取 embedding
            embedding = self.camp_model.forward(features_padded)
            
            # 如果输出有多余维度，取第一个
            if len(embedding.shape) > 2:
                embedding = embedding.squeeze(0)
            
            # 转换为 numpy 数组
            embedding_np = embedding.cpu().detach().numpy()
            
            # 如果还有批次维度，去掉
            if embedding_np.ndim > 1:
                embedding_np = embedding_np[0] if embedding_np.shape[0] == 1 else embedding_np.mean(axis=0)
            
            return embedding_np
            
        except Exception as e:
            print(f"[SpeakerEmbedding] 声纹提取失败: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def extract_from_bytes(self, audio_bytes: bytes) -> np.ndarray:
        """从字节数据中提取声纹特征"""
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        return self.extract(audio_float32)
    
    def compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """计算两个声纹向量的余弦相似度"""
        emb1_norm = emb1 / (np.linalg.norm(emb1) + 1e-8)
        emb2_norm = emb2 / (np.linalg.norm(emb2) + 1e-8)
        similarity = np.dot(emb1_norm, emb2_norm)
        return (similarity + 1.0) / 2.0


def get_model_manager() -> ModelManager:
    """获取模型管理器实例的快捷函数"""
    return ModelManager.get_instance()
