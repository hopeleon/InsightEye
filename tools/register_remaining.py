"""
增量声纹注册脚本
================
从 register_and_test.py 的数据集路径加载数据，
跳过已在 DB 中的说话人，只注册剩余的人。

用法：
    python tools/register_remaining.py
"""
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SAMPLE_RATE = 16000
MIN_DURATION_SEC = 1.0
MIN_SAMPLES_PER_SPEAKER = 3

DATASET_ROOT = Path(r"E:\primewords_md_2018_set1\primewords_md_2018_set1")
JSON_FILE = DATASET_ROOT / "set1_transcript.json"
AUDIO_ROOT = DATASET_ROOT / "audio_files"
DB_PATH = PROJECT_ROOT / "data" / "speaker_voiceprints.db"


@dataclass
class RegResult:
    speaker_id: str
    success: bool
    quality: float
    sample_count: int
    duration_sec: float
    message: str


def _build_audio_path(uuid_filename: str) -> str:
    uuid = uuid_filename.replace(".wav", "")
    p1 = uuid[0]
    p2 = uuid[:2]
    return str(AUDIO_ROOT / p1 / p2 / uuid_filename)


def _read_wav_float32(path: str) -> np.ndarray:
    import wave as _wave
    with _wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    if sw == 2:
        arr = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 4:
        arr = np.frombuffer(frames, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        arr = np.frombuffer(frames, dtype=np.float32)

    if nch > 1:
        arr = arr.reshape(-1, nch).mean(axis=1)
    else:
        arr = arr.ravel()

    if sr != SAMPLE_RATE:
        import librosa
        arr = librosa.resample(arr, orig_sr=sr, target_sr=SAMPLE_RATE)

    return np.clip(arr, -1.0, 1.0).astype(np.float32)


def _get_audio_duration(path: str) -> float:
    try:
        import wave as _wave
        with _wave.open(path, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _load_dataset() -> tuple[dict, int, int]:
    """返回 (user_id -> [item], 总说话人数, 总音频数)"""
    print(f"[加载] 读取 {JSON_FILE} ...")
    with open(JSON_FILE, encoding="utf-8") as f:
        data = json.load(f)

    by_user = defaultdict(list)
    for item in data:
        by_user[item["user_id"]].append(item)

    print(f"[加载] 完成：{len(by_user)} 个说话人，{len(data)} 条音频")
    return by_user, len(by_user), len(data)


def _get_registered_ids() -> set[str]:
    """从数据库读取已注册的 speaker_id"""
    import sqlite3
    registered = set()
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.execute(
            "SELECT speaker_id FROM speaker_profiles"
        )
        for row in cursor.fetchall():
            registered.add(row[0])
        conn.close()
    except Exception as e:
        print(f"[警告] 读取已注册列表失败: {e}")
    return registered


def _main():
    print("=" * 60)
    print("增量声纹注册 — 只注册尚未入库的说话人")
    print("=" * 60)
    print(f"数据集: {DATASET_ROOT}")
    print(f"数据库: {DB_PATH}")
    print()

    # 初始化模型
    from app.model_manager import ModelManager
    from app.enhanced_speaker_recognition import (
        MultiSpeakerRegistry,
        SpeakerEmbeddingExtractor,
    )
    from app.speaker_database import SpeakerDatabase

    print("[初始化] 加载 CAM++ 模型...")
    mgr = ModelManager.get_instance()
    if not mgr.is_initialized():
        import asyncio
        asyncio.run(mgr.initialize())
    print("[初始化] 模型就绪")

    extractor = SpeakerEmbeddingExtractor(mgr.get_camp_model(), device=mgr.device)
    db = SpeakerDatabase(str(DB_PATH))
    registry = MultiSpeakerRegistry(mgr, db_path=str(DB_PATH))

    # 加载数据集
    by_user, total_speakers, total_audios = _load_dataset()

    # 找出已注册的人
    registered_ids = _get_registered_ids()
    print(f"[DB] 已注册: {len(registered_ids)} 人")

    # 过滤出未注册的
    all_user_ids = sorted(by_user.keys(), key=lambda x: int(x))
    pending_ids = [uid for uid in all_user_ids if uid not in registered_ids]
    print(f"[待注册] {len(pending_ids)} 人")
    print()

    if not pending_ids:
        print("没有需要注册的说话人，全部已完成。")
        return

    results = []
    errors = []
    t_start = time.time()

    for idx, uid in enumerate(pending_ids, 1):
        items = by_user[uid]
        print(f"[{idx}/{len(pending_ids)}] {uid} ({len(items)} 条音频) ... ", end="", flush=True)

        # 收集音频
        audio_list = []
        for item in items:
            path = _build_audio_path(item["file"])
            if not os.path.exists(path):
                continue
            dur_str = item.get("length", "0")
            try:
                dur = float(dur_str)
            except (ValueError, TypeError):
                dur = _get_audio_duration(path)
            if dur < MIN_DURATION_SEC:
                continue
            try:
                audio = _read_wav_float32(path)
                if len(audio) < SAMPLE_RATE * MIN_DURATION_SEC:
                    continue
                audio_list.append(audio)
            except Exception as e:
                continue

        if len(audio_list) < MIN_SAMPLES_PER_SPEAKER:
            print(f"跳过（音频不足 {len(audio_list)}<{MIN_SAMPLES_PER_SPEAKER}）")
            results.append(RegResult(
                uid, False, 0.0, len(audio_list), 0.0,
                f"有效音频不足（{len(audio_list)} < {MIN_SAMPLES_PER_SPEAKER}）"
            ))
            continue

        # 提取声纹
        t0 = time.time()
        embeddings = []
        qualities = []
        for audio in audio_list:
            try:
                emb = extractor.extract(audio)
                embeddings.append(emb)
                qualities.append(float(np.linalg.norm(emb)))
            except Exception:
                continue

        if len(embeddings) < MIN_SAMPLES_PER_SPEAKER:
            print(f"声纹提取失败（{len(embeddings)} 成功）")
            results.append(RegResult(
                uid, False, 0.0, 0, time.time() - t0,
                f"声纹提取失败（{len(embeddings)} 成功）"
            ))
            continue

        # 平均 + 归一化
        avg_emb = np.mean(embeddings, axis=0)
        avg_emb = avg_emb / (np.linalg.norm(avg_emb) + 1e-8)
        quality = float(np.mean(qualities))

        # 存入数据库
        try:
            db.save_speaker(
                speaker_id=uid,
                embedding=avg_emb.astype(np.float32),
                name=f"pw_{uid}",
                individual_embeddings=[e.astype(np.float32) for e in embeddings],
                quality=quality,
                sample_count=len(embeddings),
                overwrite=False,
            )
        except Exception as e:
            print(f"DB 保存失败: {e}")
            errors.append({"speaker_id": uid, "error": str(e)})
            results.append(RegResult(
                uid, False, quality, len(embeddings), time.time() - t0,
                f"DB 保存失败: {e}"
            ))
            continue

        # 注册到内存引擎
        try:
            registry.register_embedding(uid, avg_emb, name=f"pw_{uid}", force=False)
        except Exception as e:
            pass

        elapsed = time.time() - t0
        print(f"OK 质量={quality:.3f} 样本={len(embeddings)} 耗时={elapsed:.1f}s")
        results.append(RegResult(
            uid, True, round(quality, 4), len(embeddings), elapsed, "成功"
        ))

    # 统计
    success = [r for r in results if r.success]
    failed = [r for r in results if not r.success]

    print()
    print("=" * 60)
    print("注册完成")
    print("=" * 60)
    print(f"本次成功: {len(success)} 人")
    print(f"本次失败: {len(failed)} 人（含音频不足跳过）")
    print(f"错误: {len(errors)} 条")
    print(f"总耗时: {time.time() - t_start:.1f}s")

    # 最终 DB 计数
    final_count = _get_registered_ids()
    print(f"数据库当前总计: {len(final_count)} 人")

    # 保存报告
    report_path = PROJECT_ROOT / "data" / "registration_incremental_report.json"
    report = {
        "generated_at": datetime.now().isoformat(),
        "total_in_dataset": total_speakers,
        "previously_registered": len(registered_ids),
        "this_run_success": len(success),
        "this_run_failed": len(failed),
        "total_in_db_now": len(final_count),
        "duration_sec": round(time.time() - t_start, 1),
        "results": [asdict(r) for r in results],
        "errors": errors,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"报告: {report_path}")


if __name__ == "__main__":
    _main()
