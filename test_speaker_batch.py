"""
模式三：批量声纹识别测试模式 v2
用于离线测试声纹识别准确率

功能：
1. 从 E:\primewords_md_2018_set1 随机抽取 200 条音频
2. 从已注册的 speaker_voiceprints.db 数据库加载声纹
3. 对每条音频进行识别
4. 输出准确率统计（包括 Top-1 和 Top-3 准确率）
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
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from app.model_manager import SpeakerEmbeddingExtractor, ModelManager
from app.enhanced_speaker_recognition import (
    MultiSpeakerRegistry,
    SpeakerProfile,
)
from app.speaker_database import SpeakerDatabase


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
    top3_includes_correct: bool  # Top-3 是否包含正确答案
    duration_sec: float


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


class BatchSpeakerRecognitionTester:
    """
    批量声纹识别测试器 v2
    使用已注册的声纹数据库进行测试
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
        self.speaker_id_set: set = set()  # 数据库中已注册的说话人ID集合

    def load_resources(self):
        """加载测试资源和初始化模型"""
        print("=" * 60)
        print("模式三：批量声纹识别测试 v2")
        print("=" * 60)

        # 加载音频转录文件
        print("\n[1/5] 加载音频转录文件...")
        with open(self.transcript_file, "r", encoding="utf-8") as f:
            self.transcripts = json.load(f)
        print(f"  总共有 {len(self.transcripts)} 条音频记录")

        # 加载已注册的说话人数据库
        print("\n[2/5] 加载声纹数据库...")
        self.speaker_db = SpeakerDatabase(db_path=str(self.db_path))
        
        # 获取所有已注册的说话人
        all_speakers = self.speaker_db.load_all(active_only=True)
        print(f"  数据库中有 {len(all_speakers)} 个已注册的说话人")
        
        # 收集已注册的说话人ID（user_id）
        self.speaker_id_set = set()
        self.speaker_id_to_name = {}
        for speaker in all_speakers:
            sid = speaker["speaker_id"]
            self.speaker_id_set.add(sid)
            self.speaker_id_to_name[sid] = speaker.get("name", sid)
        
        # 找出测试集中属于已注册说话人的音频
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
        
        # 获取 CAM++ 模型
        camp_model = model_mgr.get_camp_model()
        if camp_model is None:
            raise RuntimeError("CAM++ 模型加载失败")
        
        extractor = SpeakerEmbeddingExtractor(camp_model=camp_model, device=model_mgr.device)

        # 创建 MultiSpeakerRegistry
        self.registry = MultiSpeakerRegistry(model_manager=model_mgr)

        # 从数据库加载已注册的说话人声纹
        print("\n[4/5] 从数据库加载已注册说话人的声纹...")
        self._load_registered_speakers_from_db()
        print(f"  已加载 {len(self.registry.speakers)} 个说话人的声纹到内存")

    def _load_registered_speakers_from_db(self):
        """从数据库加载已注册的说话人声纹"""
        # 获取数据库中的所有说话人
        all_speakers = self.speaker_db.load_all(active_only=True)
        
        loaded_count = 0
        for speaker in all_speakers:
            speaker_id = speaker["speaker_id"]
            
            # 获取说话人的 embedding（已经是 dict 中的字段）
            embedding_bytes = speaker.get("embedding")
            if embedding_bytes is None:
                continue
            
            # 反序列化 embedding
            import numpy as np
            try:
                embedding = np.frombuffer(embedding_bytes, dtype=np.float32)
            except Exception as e:
                print(f"    反序列化 embedding 失败 for {speaker_id}: {e}")
                continue
            
            # 创建 SpeakerProfile
            profile = SpeakerProfile(
                speaker_id=speaker_id,
                name=speaker.get("name"),
                embedding=embedding,
                embedding_mean=embedding,
                sample_count=speaker.get("sample_count", 1),
                individual_embeddings=[embedding],
                registration_quality=speaker.get("quality", 0.8),
            )
            self.registry.speakers[speaker_id] = profile
            
            # 注册到 matching engine
            self.registry.matching_engine.register_speaker(
                speaker_id=speaker_id,
                embedding=embedding,
            )
            
            loaded_count += 1
            
            if loaded_count % 50 == 0:
                print(f"    已加载 {loaded_count} 个说话人...")

    def _find_audio_file(self, file_name: str) -> Optional[str]:
        """根据文件名查找音频文件路径"""
        # 文件名格式: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.wav
        # 目录结构: audio_files/0/00/文件.wav
        base_name = file_name.replace(".wav", "")
        
        # 前两个字符决定一级目录
        prefix = base_name[:2]
        first_dir = prefix[0]
        second_dir = prefix[:2]
        
        possible_path = self.audio_files_dir / first_dir / second_dir / file_name
        if possible_path.exists():
            return str(possible_path)
        
        # 遍历查找（作为备选）
        for root, dirs, files in os.walk(self.audio_files_dir):
            if file_name in files:
                return os.path.join(root, file_name)
        
        return None

    def _load_wav_audio(self, filepath: str) -> Optional[Tuple["np.ndarray", int]]:
        """加载 WAV 音频文件，返回 (audio_data, sample_rate)"""
        import numpy as np
        try:
            with wave.open(filepath, "rb") as wf:
                n_channels = wf.getnchannels()
                sample_width = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                
                # 转换为单声道 16kHz
                frames = wf.readframes(n_frames)
                
                if sample_width == 2:
                    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
                else:
                    audio = np.frombuffer(frames, dtype=np.float32)
                
                if n_channels > 1:
                    # 转换为单声道
                    audio = audio.reshape(-1, n_channels).mean(axis=1)
                
                # 重采样到 16kHz（如需要）
                if framerate != 16000:
                    import scipy.signal as signal
                    num_samples = int(len(audio) * 16000 / framerate)
                    audio = signal.resample(audio, num_samples)
                
                return audio.astype(np.float32), 16000
        except Exception as e:
            print(f"    加载音频失败 {filepath}: {e}")
            return None

    def run_test(self, n_samples: int = 200, n_windows: int = 3,
                 window_step_ratio: float = 0.25,
                 vote_method: str = "score_weighted") -> TestSummary:
        """
        运行批量测试

        Args:
            n_samples: 测试样本数量
            n_windows: 滑动窗口数量
            window_step_ratio: 步长比例
            vote_method: 投票方法

        Returns:
            TestSummary: 测试结果汇总
        """
        print(f"\n[5/5] 运行声纹识别测试（随机 {n_samples} 条）...")
        print("-" * 60)

        # 随机选择样本
        if len(self.valid_test_samples) < n_samples:
            print(f"  警告: 只有 {len(self.valid_test_samples)} 条有效样本，使用全部")
            test_samples = self.valid_test_samples
        else:
            test_samples = _system_random.sample(self.valid_test_samples, n_samples)

        results: List[TestResult] = []
        uncertain_count = 0

        for idx, sample in enumerate(test_samples):
            file_name = sample["file"]
            user_id = sample["user_id"]
            duration = float(sample.get("length", 0))
            
            print(f"\n  [{idx+1}/{len(test_samples)}] 处理: {file_name}")

            # 查找音频文件
            audio_path = self._find_audio_file(file_name)
            if audio_path is None:
                print(f"    警告: 找不到音频文件，跳过")
                continue

            # 加载音频
            audio_data = self._load_wav_audio(audio_path)
            if audio_data is None:
                print(f"    警告: 加载音频失败，跳过")
                continue
            
            audio, _ = audio_data
            
            if len(audio) < 16000:  # 少于1秒
                print(f"    警告: 音频过短（{len(audio)/16000:.1f}s），跳过")
                continue

            # 使用与模式二完全相同的识别方法
            result_obj, stats = self.registry.identify_with_voting(
                audio_sample=audio,
                n_windows=n_windows,
                window_step_ratio=window_step_ratio,
                vote_method=vote_method,
                top_k=3,
                track_id=idx + 1,
            )

            matches = result_obj.matches
            is_uncertain = result_obj.uncertain
            if is_uncertain:
                uncertain_count += 1

            if not matches:
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
                )
                results.append(result)
                gt_name = self.speaker_id_to_name.get(user_id, user_id)
                print(f"    ❌ 无识别结果 | GT: {user_id} ({gt_name})")
                continue

            # 获取识别结果
            top1_match = matches[0]
            recognized_id = top1_match.speaker_id
            recognized_name = top1_match.name or recognized_id

            # 判断是否正确（Top-1 和 Top-3）
            is_correct = (recognized_id == user_id)
            top3_includes_correct = any(m.speaker_id == user_id for m in matches[:3])

            result = TestResult(
                segment_id=idx + 1,
                audio_path=file_name,
                ground_truth_speaker_id=user_id,
                recognized_speaker_id=recognized_id,
                recognized_speaker_name=recognized_name,
                recognized_score=top1_match.final_score,
                is_correct=is_correct,
                top3_includes_correct=top3_includes_correct,
                duration_sec=duration,
            )
            results.append(result)

            # 打印结果
            status = "✓" if is_correct else "✗"
            top3_marker = "" if is_correct else ("*" if top3_includes_correct else "")
            uncertain_str = "⚠" if is_uncertain else ""
            gt_name = self.speaker_id_to_name.get(user_id, user_id)
            print(f"    {status} Top-1: {recognized_name} | GT: {user_id} ({gt_name}) {uncertain_str}{top3_marker}")
            print(f"       得分: {top1_match.final_score:.4f} | 时长: {duration:.1f}s")

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
        )

        return summary

    def print_summary(self, summary: TestSummary):
        """打印测试结果汇总"""
        print("\n" + "=" * 60)
        print("测试结果汇总")
        print("=" * 60)
        print(f"总测试样本数: {summary.total_segments}")
        print(f"识别不确定样本: {summary.uncertain_count}")
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

    def save_results(self, summary: TestSummary, output_file: str = None):
        """保存测试结果到 JSON 文件"""
        if output_file is None:
            output_file = Path(__file__).parent / "data" / "speaker_test_results_v2.json"

        output_data = {
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
                    "ground_truth_name": self.speaker_id_to_name.get(r.ground_truth_speaker_id, r.ground_truth_speaker_id),
                    "recognized": {
                        "speaker_id": r.recognized_speaker_id,
                        "speaker_name": r.recognized_speaker_name,
                        "score": r.recognized_score,
                    },
                    "is_correct": r.is_correct,
                    "top3_includes_correct": r.top3_includes_correct,
                    "duration_sec": r.duration_sec,
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

    parser = argparse.ArgumentParser(description="模式三：批量声纹识别测试 v2")
    parser.add_argument("--n-samples", "-n", type=int, default=200,
                        help="测试样本数量（默认 200）")
    parser.add_argument("--save", "-s", action="store_true",
                        help="保存结果到 JSON 文件")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子（用于复现结果，不指定则每次随机）")

    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)
        print(f"随机种子设置为: {args.seed}（可复现）")
    else:
        import time
        seed = int(time.time() * 1000) % (2**32)
        random.seed(seed)
        print(f"使用时间随机种子: {seed}")

    # 创建测试器
    tester = BatchSpeakerRecognitionTester()

    # 加载资源
    tester.load_resources()

    # 运行测试
    summary = tester.run_test(n_samples=args.n_samples)

    # 打印汇总
    tester.print_summary(summary)

    # 保存结果
    if args.save:
        tester.save_results(summary)


if __name__ == "__main__":
    main()
