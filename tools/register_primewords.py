"""
Primewords Chinese Corpus Set 1 (SLR47) 批量声纹注册工具

功能：
    - 从 Primewords 数据集加载所有说话人的音频
    - 提取每人的声纹 embedding 并注册到 SQLite 数据库
    - 生成注册报告（JSON）

用法：
    python -m tools.register_primewords [--data-dir DIR] [--min-samples N] [--max-speakers N] [--force]

数据集下载：
    https://openslr.org/resources/47/primewords_md_2018_set1.tar.gz (9.0 GB)

解压后目录结构：
    data_primewords/                          ← 指向此目录
    ├── set1/
    │   ├── 0000a4e8ef14b6bb48d200b00a42a0be/
    │   │   └── *.mp3
    │   └── ...
    └── primewords_file_mapping_transcript.json

依赖：
    pip install soundfile  (MP3 解码)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 将项目根目录加入 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from app.config import PRIMEWORDS_DATA_DIR
from app.model_manager import ModelManager
from app.speaker_database import SpeakerDatabase
from app.enhanced_speaker_recognition import (
    MultiSpeakerRegistry,
    SpeakerEmbeddingExtractor,
)
from tools.primewords_loader import PrimewordsDataset, PrimewordsUtterance


# ==================== 参数 ====================

MIN_DURATION_SEC = 1.0   # 最小音频时长（秒），过滤过短片段
MIN_SAMPLES_PER_SPEAKER = 3   # 每个说话人最少需要有效音频段数
EMBEDDING_DIM = 192      # CAM++ 声纹向量维度
SAMPLE_RATE = 16000


# ==================== 结果记录 ====================


@dataclass
class SpeakerRegistrationResult:
    speaker_id: str
    name: str
    num_loaded_samples: int
    num_valid_samples: int
    embedding_quality: float
    registration_quality: float
    success: bool
    message: str
    duration_sec: float


@dataclass
class BatchRegistrationReport:
    dataset_summary: Dict[str, Any]
    params: Dict[str, Any]
    started_at: str
    finished_at: str
    total_time_sec: float
    total_speakers: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]
    errors: List[Dict[str, str]]


# ==================== 核心逻辑 ====================


def _extract_embedding_batch(
    extractor: SpeakerEmbeddingExtractor,
    audio_samples: List[np.ndarray],
) -> tuple[Optional[np.ndarray], float, int]:
    """
    从多个音频样本中提取平均声纹向量。

    Returns:
        (embedding, quality_score, num_successful)
        quality_score：各样本 embedding L2 范数的均值（越大说明信号越强）
    """
    embeddings: List[np.ndarray] = []
    quality_scores: List[float] = []

    for audio in audio_samples:
        try:
            if len(audio) < SAMPLE_RATE * 0.5:
                continue
            emb = extractor.extract(audio)
            embeddings.append(emb)
            quality_scores.append(float(np.linalg.norm(emb)))
        except Exception as e:
            print(f"      [警告] 提取声纹失败: {e}")
            continue

    if not embeddings:
        return None, 0.0, 0

    avg_emb = np.mean(embeddings, axis=0)
    avg_emb = avg_emb / (np.linalg.norm(avg_emb) + 1e-8)
    quality = float(np.mean(quality_scores))

    return avg_emb, quality, len(embeddings)


def register_primewords_dataset(
    data_dir: Optional[str] = None,
    min_samples: int = MIN_SAMPLES_PER_SPEAKER,
    max_speakers: Optional[int] = None,
    force: bool = False,
    verbose: bool = True,
) -> BatchRegistrationReport:
    """
    主函数：从 Primewords 加载所有说话人并注册声纹。

    Args:
        data_dir: 数据集根目录（None 使用 config.PRIMEWORDS_DATA_DIR）
        min_samples: 每个说话人最少有效音频段数（低于此数跳过）
        max_speakers: 最多处理多少个说话人（用于快速测试）
        force: True=覆盖已存在的记录
        verbose: 打印详细进度

    Returns:
        BatchRegistrationReport
    """
    started_at = datetime.utcnow().isoformat()

    # 初始化数据集
    dataset = PrimewordsDataset(data_dir=data_dir)
    summary = dataset.summary()

    if verbose:
        print("=" * 60)
        print("Primewords 批量声纹注册")
        print("=" * 60)
        print(f"数据集路径: {summary['data_dir']}")
        print(f"说话人数量: {summary['num_speakers']}")
        print(f"总音频段数: {summary['total_utterances']}")
        print(f"总时长: {summary['total_duration_hours']} 小时")
        print(f"最少样本数/人: {min_samples}")
        print(f"最多处理人数: {max_speakers or '全部'}")
        print(f"最短音频时长: {MIN_DURATION_SEC}s")
        print("=" * 60)

    # 初始化模型和数据库
    if verbose:
        print("\n[1/3] 初始化模型...")
    model_mgr = ModelManager()
    # 不阻塞，等模型就绪
    import asyncio
    asyncio.get_event_loop().run_until_complete(model_mgr.ensure_initialized())

    extractor = SpeakerEmbeddingExtractor(model_mgr)
    db = SpeakerDatabase()
    registry = MultiSpeakerRegistry(model_mgr)

    if verbose:
        print("[2/3] 加载数据集索引...")

    all_speakers = list(dataset.iter_speakers())
    if max_speakers:
        all_speakers = all_speakers[:max_speakers]

    results: List[SpeakerRegistrationResult] = []
    errors: List[Dict[str, str]] = []

    if verbose:
        print(f"[3/3] 开始注册（共 {len(all_speakers)} 人）...")
    print()

    for idx, speaker in enumerate(all_speakers, 1):
        sid = speaker.speaker_id
        name = f"pw_{sid}"  # Primewords 说话人用 UUID 前缀命名

        if verbose:
            print(f"[{idx}/{len(all_speakers)}] {sid} ({speaker.num_utterances} 段音频, "
                  f"{speaker.total_duration_sec / 60:.1f} 分钟)", end="")

        # 跳过已注册
        if not force and db.exists(sid):
            if verbose:
                print(" → 已注册，跳过")
            continue

        # 加载音频
        t0 = time.time()
        try:
            audio_list = dataset.get_speaker_audio(
                sid,
                min_duration_sec=MIN_DURATION_SEC,
            )
        except Exception as e:
            msg = f"加载音频失败: {e}"
            if verbose:
                print(f" ✗ {msg}")
            errors.append({"speaker_id": sid, "error": msg})
            results.append(SpeakerRegistrationResult(
                speaker_id=sid, name=name,
                num_loaded_samples=0, num_valid_samples=0,
                embedding_quality=0.0, registration_quality=0.0,
                success=False, message=msg, duration_sec=time.time() - t0,
            ))
            continue

        num_valid = len(audio_list)

        if num_valid < min_samples:
            msg = f"有效音频不足（{num_valid} < {min_samples}）"
            if verbose:
                print(f" → 跳过: {msg}")
            results.append(SpeakerRegistrationResult(
                speaker_id=sid, name=name,
                num_loaded_samples=num_valid, num_valid_samples=num_valid,
                embedding_quality=0.0, registration_quality=0.0,
                success=False, message=msg, duration_sec=time.time() - t0,
            ))
            continue

        # 提取声纹（同时获取各样本的独立 embedding）
        emb, quality, num_extracted, all_embeddings = _extract_embedding_batch(extractor, audio_list)

        if emb is None or num_extracted == 0:
            msg = "声纹提取全部失败"
            if verbose:
                print(f" ✗ {msg}")
            errors.append({"speaker_id": sid, "error": msg})
            results.append(SpeakerRegistrationResult(
                speaker_id=sid, name=name,
                num_loaded_samples=num_valid, num_valid_samples=0,
                embedding_quality=0.0, registration_quality=0.0,
                success=False, message=msg, duration_sec=time.time() - t0,
            ))
            continue

        # 存入数据库
        try:
            db.save_speaker(
                speaker_id=sid,
                embedding=emb.astype(np.float32),
                name=name,
                individual_embeddings=[e.astype(np.float32) for e in all_embeddings],
                quality=quality,
                sample_count=num_extracted,
                overwrite=force,
            )
        except Exception as e:
            msg = f"数据库保存失败: {e}"
            if verbose:
                print(f" ✗ {msg}")
            errors.append({"speaker_id": sid, "error": msg})
            continue

        # 注入到实时识别引擎
        try:
            reg_result = registry.register_embedding(
                sid, emb, name=name, force=force
            )
            reg_quality = getattr(reg_result, "registration_quality", 0.0) or quality
        except Exception as e:
            reg_quality = quality
            if verbose:
                print(f"  (registry 警告: {e})")

        result = SpeakerRegistrationResult(
            speaker_id=sid,
            name=name,
            num_loaded_samples=num_valid,
            num_valid_samples=num_extracted,
            embedding_quality=round(quality, 4),
            registration_quality=round(reg_quality, 4),
            success=True,
            message="注册成功",
            duration_sec=time.time() - t0,
        )
        results.append(result)

        if verbose:
            print(f" ✓ 质量={quality:.3f} | 样本={num_extracted}/{num_valid} | "
                  f"耗时={time.time() - t0:.1f}s")

    finished_at = datetime.utcnow().isoformat()
    total_time = sum(r.duration_sec for r in results)

    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    report = BatchRegistrationReport(
        dataset_summary=summary,
        params={
            "data_dir": data_dir or PRIMEWORDS_DATA_DIR,
            "min_samples_per_speaker": min_samples,
            "max_speakers": max_speakers,
            "force": force,
            "min_duration_sec": MIN_DURATION_SEC,
        },
        started_at=started_at,
        finished_at=finished_at,
        total_time_sec=round(total_time, 1),
        total_speakers=len(all_speakers),
        successful=len(successful),
        failed=len(failed),
        results=[asdict(r) for r in results],
        errors=errors,
    )

    if verbose:
        print()
        print("=" * 60)
        print("注册完成")
        print("=" * 60)
        print(f"成功: {len(successful)} 人")
        print(f"失败: {len(failed)} 人（音频不足或提取失败）")
        print(f"错误: {len(errors)} 条")
        print(f"总耗时: {total_time:.1f}s")
        print(f"数据库: {db.db_path}")

    return report


# ==================== 入口 ====================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Primewords 数据集批量声纹注册工具"
    )
    parser.add_argument(
        "--data-dir", "-d",
        help=f"数据集根目录（默认: {PRIMEWORDS_DATA_DIR}）"
    )
    parser.add_argument(
        "--min-samples", "-m", type=int, default=MIN_SAMPLES_PER_SPEAKER,
        help=f"每人最少音频样本数（默认: {MIN_SAMPLES_PER_SPEAKER}）"
    )
    parser.add_argument(
        "--max-speakers", "-n", type=int, default=None,
        help="最多处理多少个说话人（用于快速测试，默认全部）"
    )
    parser.add_argument(
        "--force", "-f", action="store_true",
        help="覆盖已存在的声纹记录"
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="减少输出"
    )
    parser.add_argument(
        "--output", "-o",
        help="注册报告输出路径（JSON），默认不保存"
    )

    args = parser.parse_args()

    report = register_primewords_dataset(
        data_dir=args.data_dir,
        min_samples=args.min_samples,
        max_speakers=args.max_speakers,
        force=args.force,
        verbose=not args.quiet,
    )

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, ensure_ascii=False, indent=2)
        print(f"报告已保存: {output_path}")

    sys.exit(0 if report.failed == 0 else 1)


if __name__ == "__main__":
    main()
