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
        self.punc_model = None     # FunASR 标点恢复模型（ct-punc）
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
            
            print("[ModelManager] 开始加载模型...", flush=True)
            print(f"[ModelManager] FunASR 模型路径 (实际): {self._paths.funasr_model}", flush=True)
            print(f"[ModelManager] CAM++ 中文模型路径 (实际): {self._paths.campplus_model}", flush=True)
            print(f"[ModelManager] CAM++ 英文模型路径 (实际): {self._paths.campplus_en_model}", flush=True)
            print(f"[ModelManager] 使用设备: {self._paths.device}", flush=True)
            
            # 在线程池中加载模型，避免阻塞事件循环
            loop = asyncio.get_event_loop()
            
            # 依次加载，避免并行加载导致内存问题
            try:
                await loop.run_in_executor(None, self._load_vad)
                print("[ModelManager] Silero VAD 加载完成", flush=True)
            except Exception as e:
                print(f"[ModelManager] Silero VAD 加载失败，将使用备选方案: {e}", flush=True)
            
            try:
                await loop.run_in_executor(None, self._load_funasr)
                print("[ModelManager] FunASR 加载完成", flush=True)
            except Exception as e:
                print(f"[ModelManager] FunASR 加载失败: {e}", flush=True)
            
            try:
                await loop.run_in_executor(None, self._load_campplus)
                print("[ModelManager] CAM++ 中文声纹模型加载完成", flush=True)
            except Exception as e:
                print(f"[ModelManager] CAM++ 中文声纹模型加载失败: {e}", flush=True)
            
            try:
                await loop.run_in_executor(None, self._load_campplus_en)
                print("[ModelManager] CAM++ 英文声纹模型加载完成", flush=True)
            except Exception as e:
                print(f"[ModelManager] CAM++ 英文声纹模型加载失败: {e}", flush=True)
            
            self._initialized = True
            vad_status = "[PASS] 已加载" if self.vad_model is not None else "[FAIL] 未加载（无 VAD 模型）"
            funasr_status = "[PASS] 已加载" if self.funasr_model is not None else "[FAIL] 未加载（无 FunASR 模型）"
            camp_status = "[PASS] 已加载" if self.camp_model is not None else "[FAIL] 未加载（无 CAM++ 中文模型）"
            camp_en_status = "[PASS] 已加载" if self.camp_en_model is not None else "[FAIL] 未加载（无 CAM++ 英文模型）"
            print("[ModelManager] ============================================", flush=True)
            print(f"[ModelManager] 模型加载结果汇总：", flush=True)
            print(f"[ModelManager]   VAD (Silero):        {vad_status}", flush=True)
            print(f"[ModelManager]   ASR (FunASR):        {funasr_status}", flush=True)
            print(f"[ModelManager]   声纹 (CAM++ zh):     {camp_status}", flush=True)
            print(f"[ModelManager]   声纹 (CAM++ en):     {camp_en_status}", flush=True)
            print("[ModelManager] ============================================", flush=True)
            if self.vad_model is None:
                print("[ModelManager] [!] 警告: VAD 模型未加载，实时转录将使用能量检测模式", flush=True)
            print("[ModelManager] 模型初始化流程结束", flush=True)
    
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
                    punc_model="ct-punc",       # 自动标点恢复（ct-punc）
                    punc_model_revision="v2.0.4",
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
                    punc_model="ct-punc",       # 自动标点恢复
                    punc_model_revision="v2.0.4",
                    cache_dir=_get_local_model_dir(),
                    device=self._paths.device,
                    disable_update=True,
                    ncpu=4,
                )
            
            print(f"[ModelManager] FunASR 模型加载成功，使用设备: {self._paths.device}")

            # 尝试加载标点模型（ct-punc）
            self._load_punc_model()

        except Exception as e:
            print(f"[ModelManager] FunASR 模型加载失败: {e}")
            import traceback
            traceback.print_exc()

    def _load_punc_model(self) -> None:
        """加载标点恢复模型（ct-punc）"""
        try:
            from funasr import AutoModel

            self.punc_model = AutoModel(
                model="ct-punc",
                model_revision="v2.0.4",
                device=self._paths.device,
                disable_update=True,
                ncpu=2,
            )
            print("[ModelManager] 标点恢复模型(ct-punc)加载成功")
        except Exception as e:
            print(f"[ModelManager] 标点恢复模型加载失败（不影响主功能）: {e}")
            self.punc_model = None

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
                import sys
                subprocess.run([sys.executable, "-m", "pip", "install", "addict"], capture_output=True)
            
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
            
            # 尝试使用配置的设备加载，如果失败则回退到 CPU
            try:
                state_dict = torch.load(model_file, map_location=self._paths.device)
            except (RuntimeError, AssertionError):
                print(f"[ModelManager] CUDA 加载失败，尝试 CPU 模式...")
                state_dict = torch.load(model_file, map_location=torch.device('cpu'))
            
            self.camp_model.load_state_dict(state_dict, strict=False)
            # 如果 CUDA 不可用，强制用 CPU
            try:
                self.camp_model.to(self._paths.device)
            except AssertionError:
                print(f"[ModelManager] CUDA 不可用，使用 CPU...")
                self.camp_model.to(torch.device('cpu'))
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
            
            # 尝试使用配置的设备加载，如果失败则回退到 CPU
            try:
                state_dict = torch.load(model_file, map_location=self._paths.device)
            except (RuntimeError, AssertionError):
                print(f"[ModelManager] CUDA 加载失败，尝试 CPU 模式...")
                state_dict = torch.load(model_file, map_location=torch.device('cpu'))
            
            self.camp_en_model.load_state_dict(state_dict, strict=False)
            try:
                self.camp_en_model.to(self._paths.device)
            except AssertionError:
                print(f"[ModelManager] CUDA 不可用，使用 CPU...")
                self.camp_en_model.to(torch.device('cpu'))
            self.camp_en_model.eval()
            
            print(f"[ModelManager] CAM++ 英文声纹模型加载成功")
            
        except Exception as e:
            print(f"[ModelManager] CAM++ 英文声纹模型加载失败（不影响主功能）: {e}")
    
    def _load_vad(self) -> None:
        """加载 Silero VAD 模型（优先本地缓存，否则联网下载）"""
        try:
            torch.set_num_threads(1)

            # 检查本地模型目录中是否存在 Silero VAD
            # torch.hub.load 的 repo_or_dir 需要一个包含 hubconf.py 的根目录，
            # 然后它会在内部查找 files/silero-vad/silero_vad.jit
            local_master_dir = os.path.join(
                _get_local_model_dir(), "silero-vad", "snakers4_silero-vad_master"
            )
            local_model_file_v1 = os.path.join(local_master_dir, "files", "silero-vad", "silero_vad.jit")
            local_model_file_v2 = os.path.join(local_master_dir, "src", "silero_vad", "data", "silero_vad.jit")

            if os.path.exists(local_model_file_v1):
                print(f"[ModelManager] 发现本地 Silero VAD 模型: {local_model_file_v1}", flush=True)
                print(f"[ModelManager] 开始加载本地 VAD 模型...", flush=True)
                os.environ["TORCH_HUB_DIR"] = os.path.join(_get_local_model_dir(), "silero-vad")
                model, utils = torch.hub.load(
                    repo_or_dir=local_master_dir,
                    model='silero_vad',
                    trust_repo=True
                )
            elif os.path.exists(local_model_file_v2):
                # 用户手动放置的模型可能在 src/silero_vad/data/ 下
                # 需要通过 hubconf 直接加载 ONNX 文件
                print(f"[ModelManager] 发现本地 Silero VAD 模型: {local_model_file_v2}", flush=True)
                print(f"[ModelManager] 开始加载本地 VAD 模型...", flush=True)
                model, utils = self._load_silero_from_local(
                    os.path.join(local_master_dir, "src", "silero_vad")
                )
            else:
                print(f"[ModelManager] 未找到本地 Silero VAD，尝试联网下载...", flush=True)
                torch_hub_dir = os.path.join(_get_local_model_dir(), "silero-vad")
                os.makedirs(torch_hub_dir, exist_ok=True)
                os.environ["TORCH_HUB_DIR"] = torch_hub_dir
                print(f"[ModelManager] 正在从 GitHub (snakers4/silero-vad) 下载 VAD 模型...", flush=True)
                model, utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    trust_repo=True
                )
                local_cached = os.path.join(torch_hub_dir, "snakers4_silero-vad_master", "files", "silero-vad", "silero_vad.jit")
                if os.path.exists(local_cached):
                    print(f"[ModelManager] VAD 模型已缓存到本地: {local_cached}", flush=True)

            if model is None:
                raise RuntimeError("VAD 模型加载返回了 None")

            (get_speech_timestamps, _, read_audio, _, _) = utils
            self.vad_model = model
            self.vad_get_speech_timestamps = get_speech_timestamps
            self.vad_read_audio = read_audio
            print("[ModelManager] Silero VAD 模型加载成功", flush=True)

        except Exception as e:
            print(f"[ModelManager] Silero VAD 模型加载失败: {e}", flush=True)
            import traceback as tb
            print(f"[ModelManager] 详细错误:\n{tb.format_exc()}", flush=True)

    def _load_silero_from_local(self, src_dir: str):
        """直接从本地 .jit 文件加载 Silero VAD（不依赖 torch.hub 联网）

        返回的 model 可以像 torch.hub 加载的模型一样调用：model(tensor, sample_rate) -> 概率
        注意：get_speech_timestamps 不在 streaming pipeline 的关键路径上，
        StreamingVAD 直接调用 model(chunk, sr) 获取概率，不依赖此工具函数。
        """
        jit_file = os.path.join(src_dir, "data", "silero_vad.jit")
        if not os.path.exists(jit_file):
            raise FileNotFoundError(f"找不到 Silero VAD .jit 文件: {jit_file}")

        print(f"[ModelManager] 直接加载本地 .jit 模型: {jit_file}", flush=True)
        model = torch.jit.load(jit_file)
        model.eval()

        def read_audio(path):
            import torchaudio
            waveform, sr = torchaudio.load(path)
            if sr != 16000:
                waveform = torchaudio.functional.resample(waveform, sr, 16000)
            return waveform.squeeze(0).numpy()

        utils = (lambda *a, **kw: [], lambda: None, read_audio, lambda: None, lambda: None)
        return model, utils
    
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

    def get_punc_model(self):
        """获取标点恢复模型"""
        return self.punc_model

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
            try:
                features_padded = features_padded.to(device=self.device)
            except AssertionError:
                # Torch 未编译 CUDA支持，降级到 CPU
                self.device = "cpu"
                features_padded = features_padded.to(device="cpu")
            
            # 使用 CAM++ 模型提取 embedding
            try:
                embedding = self.camp_model.forward(features_padded)
            except AssertionError:
                self.device = "cpu"
                features_padded = features_padded.to(device="cpu")
                embedding = self.camp_model.forward(features_padded)
            
            # 如果输出有多余维度，取第一个
            if len(embedding.shape) > 2:
                embedding = embedding.squeeze(0)
            
            # 转换为 numpy 数组
            embedding_np = embedding.cpu().detach().numpy()
            
            # 如果还有批次维度，去掉
            if embedding_np.ndim > 1:
                embedding_np = embedding_np[0] if embedding_np.shape[0] == 1 else embedding_np.mean(axis=0)

            # 检查 NaN 并降级处理
            if np.any(np.isnan(embedding_np)):
                n_nan = np.sum(np.isnan(embedding_np))
                total = embedding_np.size
                pct = n_nan * 100.0 / total
                print(f"[SpeakerEmbedding] 警告: embedding 包含 {n_nan}/{total} 个 NaN ({pct:.1f}%)")
                # 少量 NaN（<10%）用均值填充，保留部分有效信息；大量 NaN 则标记失败
                if pct < 10.0:
                    mean_val = np.nanmean(embedding_np)
                    embedding_np = np.nan_to_num(embedding_np, nan=mean_val)
                else:
                    raise ValueError(
                        f"Embedding 失效率过高 ({pct:.1f}%)，可能是音频过短（<{int(self.sample_rate * 0.3)}样本）"
                        f"或音频格式异常，无法提取有效声纹"
                    )

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

    def _detect_speech_ranges(self, audio_data: np.ndarray) -> list[tuple[int, int]]:
        """
        用能量阈值检测音频中的语音区间。

        Returns:
            [(start_sample, end_sample), ...]  语音区列表（可能有多段）
        """
        win_size = int(self.sample_rate * 0.025)   # 25ms 帧
        win_step = int(win_size * 0.5)              # 10ms 步长
        n_samples = len(audio_data)
        energy_threshold = 0.01  # 能量阈值（归一化音频）

        speech_ranges = []
        in_speech = False
        speech_start = 0

        i = 0
        while i * win_step < n_samples:
            start = i * win_step
            end = min(start + win_size, n_samples)
            frame = audio_data[start:end]
            energy = float(np.sqrt(np.mean(frame ** 2)))

            if energy > energy_threshold:
                if not in_speech:
                    speech_start = start
                    in_speech = True
            else:
                if in_speech:
                    speech_ranges.append((speech_start, end))
                    in_speech = False
            i += 1

        if in_speech:
            speech_ranges.append((speech_start, n_samples))

        # 合并相邻或重叠的区间（间隔 < 0.1s 则合并）
        if not speech_ranges:
            return []
        merged = [speech_ranges[0]]
        for start, end in speech_ranges[1:]:
            if start - merged[-1][1] < int(self.sample_rate * 0.1):
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        return merged
    
    def compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """计算两个声纹向量的余弦相似度"""
        emb1_norm = emb1 / (np.linalg.norm(emb1) + 1e-8)
        emb2_norm = emb2 / (np.linalg.norm(emb2) + 1e-8)
        similarity = np.dot(emb1_norm, emb2_norm)
        return (similarity + 1.0) / 2.0

    def extract_multi_window(
        self,
        audio_data: np.ndarray,
        n_windows: int = 3,
        window_step_ratio: float = 0.25,
    ) -> list[np.ndarray]:
        """
        从一段音频中提取多个滑动窗口的声纹向量，然后取平均。

        原理：同一个人说话的声纹在短时间内是稳定的，但不同位置的
        音素可能带来微小波动。多窗口采样可以过滤掉某个窗口因恰好
        捕捉到非常规音素而产生的离群 embedding，整体更鲁棒。

        Args:
            audio_data: 音频数据，float32，16kHz，范围 [-1, 1]
            n_windows: 滑动窗口数量，建议 3~5
            window_step_ratio: 步长占窗口长度的比例，默认 0.25（重叠 75%）

        Returns:
            [(embedding, window_start_sec, valid), ...] 列表
            embedding: 192 维声纹向量（归一化）
            window_start_sec: 该窗口在音频中的起始时间（秒）
            valid: 是否成功提取（False 表示该窗口过短/提取失败）
        """
        n_samples = len(audio_data)
        min_samples = int(self.sample_rate * 0.3)  # 至少 0.3 秒

        # 若音频太短，不够开多个窗口，直接退化为单窗口
        window_len = n_samples
        if n_samples < min_samples * n_windows:
            try:
                emb = self.extract(audio_data)
                return [(emb, 0.0, True)]
            except Exception:
                return []

        # 用 VAD 定位语音区，避免窗口落在静音区
        speech_ranges = self._detect_speech_ranges(audio_data)
        if speech_ranges and len(speech_ranges) >= 2:
            # 有多段语音：以语音区为中心放置窗口
            # 取最后一段语音（最接近说话人当前状态）
            last_speech_start, last_speech_end = speech_ranges[-1]
            speech_len = last_speech_end - last_speech_start
            # 窗口长度 = 最后一段语音长度（不够长时用整段音频的一半）
            window_len = max(min(speech_len, n_samples // 2), int(self.sample_rate * 0.5))
            # 窗口起点 = 从语音段末端往前 window_len
            win_start = max(0, last_speech_end - window_len)
            step = int(window_len * window_step_ratio)
        else:
            # 无清晰语音区或只有一段：均匀分段（防止延伸到末尾静音）
            window_len = n_samples // n_windows
            step = int(window_len * window_step_ratio)

        results: list[tuple[np.ndarray, float, bool]] = []
        for i in range(n_windows):
            start = i * step
            end = min(start + window_len, n_samples)
            if end - start < min_samples:
                break
            window_audio = audio_data[start:end]
            # 零能量检测：避免纯静音窗口
            energy = float(np.sqrt(np.mean(window_audio ** 2)))
            if energy < 1e-4:
                print(f"[MultiWindow] 窗口 {i} 能量={energy:.6f}（接近静音），跳过")
                continue
            try:
                emb = self.extract(window_audio)
                if np.linalg.norm(emb) < 1e-6:
                    print(f"[MultiWindow] 窗口 {i} 提取到零向量，跳过")
                    continue
                results.append((emb, start / self.sample_rate, True))
            except Exception as e:
                print(f"[MultiWindow] 窗口 {i} 提取失败: {e}")
                results.append((np.array([]), start / self.sample_rate, False))

        return results

    def extract_fused(
        self,
        audio_data: np.ndarray,
        n_windows: int = 3,
        window_step_ratio: float = 0.25,
        fusion_method: str = "mean",
    ) -> tuple[np.ndarray, dict]:
        """
        提取多窗口声纹并融合为单一向量。

        Args:
            audio_data: 音频数据，float32，16kHz
            n_windows: 窗口数量
            window_step_ratio: 步长比例
            fusion_method: 融合方法，"mean"（算术平均）或 "median"（中位数，对离群点更鲁棒）

        Returns:
            (fused_embedding, stats_dict)
            stats_dict: {"n_windows": int, "n_valid": int, "window_scores": dict}
        """
        windows = self.extract_multi_window(audio_data, n_windows, window_step_ratio)
        valid = [(emb, ts) for emb, ts, ok in windows if ok]

        if not valid:
            raise ValueError("所有窗口均提取失败，无法融合声纹")

        embeddings = [emb for emb, _ in valid]
        timestamps = [ts for _, ts in valid]

        if fusion_method == "median":
            stacked = np.array(embeddings)
            fused = np.median(stacked, axis=0)
        else:  # mean
            fused = np.mean(embeddings, axis=0)

        fused = fused / (np.linalg.norm(fused) + 1e-8)

        # 计算各窗口两两余弦相似度（衡量窗口间一致性）
        window_scores: dict[str, float] = {}
        for idx, (emb, ts) in enumerate(valid):
            sim = float(np.dot(emb, fused))
            window_scores[f"window_{idx}_t{sec(ts):.2f}s"] = round(sim, 4)

        # 统计离群窗口
        mean_sim = np.mean(list(window_scores.values()))
        std_sim = np.std(list(window_scores.values())) if len(window_scores) > 1 else 0.0
        outlier_count = sum(
            1 for v in window_scores.values()
            if abs(v - mean_sim) > 2.5 * std_sim
        ) if std_sim > 0 else 0

        stats = {
            "n_windows": n_windows,
            "n_valid": len(valid),
            "fusion_method": fusion_method,
            "window_scores": window_scores,
            "mean_window_sim": round(float(mean_sim), 4),
            "std_window_sim": round(float(std_sim), 4),
            "outlier_count": outlier_count,
            "timestamps_sec": [round(t, 3) for t in timestamps],
        }
        print(
            f"[MultiWindow] 融合完成: {len(valid)}/{n_windows} 有效窗口, "
            f"窗口间一致性={mean_sim:.4f}±{std_sim:.4f}, "
            f"离群={outlier_count}, 方法={fusion_method}"
        )

        return fused, stats


def get_model_manager() -> ModelManager:
    """获取模型管理器实例的快捷函数"""
    return ModelManager.get_instance()
