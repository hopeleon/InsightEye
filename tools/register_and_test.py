"""
Primewords SLR47 批量声纹注册 + 测试数据生成脚本
===================================================
适配数据集结构：
    E:\primewords_md_2018_set1\primewords_md_2018_set1\
        set1_transcript.json          ← 50,902 条标注
        audio_files/
            {hex1}/{hex2}/{uuid}.wav  ← 三层目录，按 UUID hex 分组

步骤：
    1. 注册全部 296 人到 speaker_voiceprints.db
    2. 随机选取 8 人注册并生成 3~5 分钟测试音频 + GT JSON
"""

import json
import os
import random
import sys
import time
import wave
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


# ======================== 数据集路径 ========================

DATASET_ROOT = Path(r"E:\primewords_md_2018_set1\primewords_md_2018_set1")
JSON_FILE = DATASET_ROOT / "set1_transcript.json"
AUDIO_ROOT = DATASET_ROOT / "audio_files"
DB_PATH = PROJECT_ROOT / "data" / "speaker_voiceprints.db"
OUT_DIR = PROJECT_ROOT / "data"


# ======================== 姓名池 ========================

_SURNAMES = ["张", "王", "李", "赵", "陈", "刘", "吴", "周", "徐", "孙",
             "马", "朱", "胡", "郭", "林", "何", "高", "梁", "罗", "郑",
             "杨", "黄", "徐", "孙", "马", "朱", "胡", "郭", "林", "何"]
_GIVEN_NAMES = ["伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "军",
                "洋", "勇", "艳", "杰", "涛", "明", "超", "秀兰", "霞", "平",
                "刚", "桂英", "建华", "建国", "志强", "永强", "秀珍", "海燕", "小华", "鹏",
                "婷", "颖", "丹", "莉", "波", "宇", "浩", "鑫", "琪", "琳"]

_used_names = set()


def _make_name(seed: int) -> str:
    rng = random.Random(seed)
    while True:
        name = rng.choice(_SURNAMES) + rng.choice(_GIVEN_NAMES)
        if name not in _used_names and len(name) <= 4:
            _used_names.add(name)
            return name


# ======================== 数据集加载 ========================

def _build_audio_path(uuid_filename: str) -> str:
    uuid = uuid_filename.replace(".wav", "")
    p1 = uuid[0]
    p2 = uuid[:2]
    return str(AUDIO_ROOT / p1 / p2 / uuid_filename)


def _load_dataset() -> tuple[dict, dict]:
    """返回 (user_id -> [item]), (uuid -> item)"""
    print(f"[加载] 读取 {JSON_FILE} ...")
    with open(JSON_FILE, encoding="utf-8") as f:
        data = json.load(f)

    by_user = defaultdict(list)
    by_uuid = {}
    for item in data:
        uid = item["user_id"]
        by_user[uid].append(item)
        by_uuid[item["file"]] = item

    print(f"[加载] 完成：{len(by_user)} 个说话人，{len(data)} 条音频")
    return by_user, by_uuid


# ======================== 音频读取 ========================

def _read_wav_float32(path: str) -> np.ndarray:
    """读取 WAV 文件为 16kHz float32 单声道 numpy 数组"""
    with wave.open(path, "rb") as wf:
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
    """快速获取 WAV 文件时长（秒）"""
    try:
        with wave.open(path, "rb") as wf:
            frames = wf.getnframes()
            sr = wf.getframerate()
            return frames / sr
    except Exception:
        return 0.0


# ======================== 声纹注册 ========================

@dataclass
class RegResult:
    speaker_id: str
    name: str
    success: bool
    quality: float
    sample_count: int
    duration_sec: float
    message: str


def _register_all_speakers() -> list[RegResult]:
    """注册全部 296 人"""
    print("\n" + "=" * 60)
    print("第一步：注册全部 296 说话人到数据库")
    print("=" * 60)

    # 初始化模型
    from app.model_manager import ModelManager, SpeakerEmbeddingExtractor
    from app.enhanced_speaker_recognition import (
        MultiSpeakerRegistry,
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
    by_user, _ = _load_dataset()

    results = []
    user_ids = sorted(by_user.keys(), key=lambda x: int(x))
    total = len(user_ids)
    print(f"\n[注册] 开始处理 {total} 个说话人...")

    for idx, uid in enumerate(user_ids, 1):
        items = by_user[uid]

        # 收集音频（时长 >= MIN_DURATION_SEC）
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
                print(f"  [警告] 读取失败 {item['file']}: {e}")
                continue

        if len(audio_list) < MIN_SAMPLES_PER_SPEAKER:
            results.append(RegResult(
                speaker_id=uid, name=f"pw_{uid}", success=False,
                quality=0.0, sample_count=len(audio_list), duration_sec=0.0,
                message=f"有效音频不足（{len(audio_list)} < {MIN_SAMPLES_PER_SPEAKER}）"
            ))
            if idx % 20 == 0:
                print(f"[进度] {idx}/{total} ... {uid} 跳过（音频不足）")
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
            except Exception as e:
                print(f"  [警告] 提取声纹失败: {e}")
                continue

        if len(embeddings) < MIN_SAMPLES_PER_SPEAKER:
            results.append(RegResult(
                speaker_id=uid, name=f"pw_{uid}", success=False,
                quality=0.0, sample_count=0, duration_sec=time.time() - t0,
                message="声纹提取全部失败"
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
            print(f"  [错误] DB 保存失败: {e}")

        # 注册到内存引擎
        try:
            registry.register_embedding(uid, avg_emb, name=f"pw_{uid}", force=True)
        except Exception as e:
            print(f"  [警告] Registry 注册失败: {e}")

        results.append(RegResult(
            speaker_id=uid, name=f"pw_{uid}", success=True,
            quality=round(quality, 4), sample_count=len(embeddings),
            duration_sec=time.time() - t0, message="成功"
        ))

        if idx % 20 == 0:
            print(f"[进度] {idx}/{total} - {uid} OK")

    success_count = sum(1 for r in results if r.success)
    print(f"\n[完成] 成功 {success_count}/{total} 人")
    return results


# ======================== 测试音频生成 ========================

def _generate_test_data(num_speakers: int = 8) -> None:
    """随机选 8 人，生成 3~5 分钟拼接音频 + GT JSON"""
    print("\n" + "=" * 60)
    print(f"第二步：生成测试音频（{num_speakers} 人）")
    print("=" * 60)

    from app.model_manager import ModelManager, SpeakerEmbeddingExtractor
    from app.enhanced_speaker_recognition import (
        MultiSpeakerRegistry,
    )
    from app.speaker_database import SpeakerDatabase

    mgr = ModelManager.get_instance()
    extractor = SpeakerEmbeddingExtractor(mgr.get_camp_model(), device=mgr.device)
    db = SpeakerDatabase(str(DB_PATH))
    registry = MultiSpeakerRegistry(mgr, db_path=str(DB_PATH))

    by_user, _ = _load_dataset()

    # 从数据库获取已注册的说话人ID，只从这些ID中随机选择
    all_db_speakers = db.load_all(active_only=True)
    registered_ids = {s["speaker_id"] for s in all_db_speakers}
    print(f"[DB] 已注册说话人: {len(registered_ids)} 人")

    # 随机选说话人（选音频多的，且必须在数据库中已注册）
    eligible = [
        (uid, len(items))
        for uid, items in by_user.items()
        if uid in registered_ids and len(items) >= 5
    ]
    eligible.sort(key=lambda x: -x[1])  # 音频多的优先
    rng = random.Random(999)
    selected = rng.sample(eligible, min(num_speakers, len(eligible)))

    print(f"[选择] 从 {len(eligible)} 个已注册且音频充足的说话人中选取 {len(selected)} 人")

    # 注册 + 分配姓名
    speakers = []
    for idx, (uid, count) in enumerate(selected):
        name = _make_name(42 + idx)
        items = by_user[uid]

        # 选前 10 条音频
        audio_list = []
        valid_items = []
        for item in items[:15]:
            path = _build_audio_path(item["file"])
            if not os.path.exists(path):
                continue
            dur_str = item.get("length", "0")
            try:
                dur = float(dur_str)
            except (ValueError, TypeError):
                dur = _get_audio_duration(path)
            if dur < 1.0:
                continue
            try:
                audio = _read_wav_float32(path)
                audio_list.append(audio)
                valid_items.append(item)
            except Exception:
                continue
            if len(audio_list) >= 10:
                break

        if len(audio_list) < 3:
            print(f"  [跳过] {uid} 有效音频不足")
            continue

        # 提取声纹（前 5 条）
        embeddings = []
        for audio in audio_list[:5]:
            try:
                emb = extractor.extract(audio)
                embeddings.append(emb)
            except Exception:
                continue

        if len(embeddings) < 2:
            print(f"  [跳过] {uid} 声纹提取失败")
            continue

        avg_emb = np.mean(embeddings, axis=0)
        avg_emb = avg_emb / (np.linalg.norm(avg_emb) + 1e-8)

        # 存数据库（覆盖）
        db.save_speaker(
            speaker_id=uid, embedding=avg_emb.astype(np.float32),
            name=name, individual_embeddings=[e.astype(np.float32) for e in embeddings],
            quality=float(np.mean([np.linalg.norm(e) for e in embeddings])),
            sample_count=len(embeddings), overwrite=True,
        )
        registry.register_embedding(uid, avg_emb, name=name, force=True)

        speakers.append({
            "speaker_id": uid,
            "name": name,
            "audio_list": audio_list,
            "items": valid_items[:len(audio_list)],
        })
        print(f"  注册: {uid} -> {name} ({len(audio_list)} 条音频)")

    if not speakers:
        print("[错误] 没有可用的说话人")
        return

    # 生成拼接音频
    print("\n[拼接] 开始生成音频...")
    SEGMENT_PLAY_SEC = 5.0
    MIN_SILENCE = 0.3
    MAX_SILENCE = 1.0
    TARGET_TOTAL = 240.0  # 4 分钟

    segments = []
    current_ms = 0
    round_idx = 0
    rng = random.Random(42)

    while current_ms / 1000.0 < TARGET_TOTAL:
        any_added = False
        for spk in speakers:
            if round_idx >= len(spk["audio_list"]):
                continue
            audio = spk["audio_list"][round_idx]
            item = spk["items"][round_idx]

            # 截取
            max_samp = int(SEGMENT_PLAY_SEC * SAMPLE_RATE)
            if len(audio) > max_samp:
                audio = audio[:max_samp]

            dur_ms = int(len(audio) / SAMPLE_RATE * 1000)
            seg_start = current_ms
            seg_end = current_ms + dur_ms

            text = item.get("text", "").strip()

            segments.append({
                "id": len(segments) + 1,
                "speaker_id": spk["speaker_id"],
                "speaker_name": spk["name"],
                "start_ms": seg_start,
                "end_ms": seg_end,
                "duration_ms": dur_ms,
                "text": text[:100] if text else "",
                "audio_file": item["file"],
            })

            silence_ms = int(rng.uniform(MIN_SILENCE, MAX_SILENCE) * 1000)
            current_ms = seg_end + silence_ms
            any_added = True

        round_idx += 1
        if round_idx > 50 or not any_added:
            break

    print(f"[拼接] 生成 {len(segments)} 个片段，总时长 {current_ms/1000:.1f}s")

    # 写入 WAV
    print(f"[拼接] 写入音频...")
    wav_path = OUT_DIR / "test_meeting_spliced.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)

        for seg in segments:
            spk = next(s for s in speakers if s["speaker_id"] == seg["speaker_id"])
            audio = spk["audio_list"][seg["id"] - 1]
            max_samp = int(seg["duration_ms"] / 1000 * SAMPLE_RATE)
            if len(audio) > max_samp:
                audio = audio[:max_samp]

            int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
            wf.writeframes(int16.tobytes())

            # 静音间隔
            idx_in_list = segments.index(seg)
            if idx_in_list < len(segments) - 1:
                next_seg = segments[idx_in_list + 1]
                silence_ms = next_seg["start_ms"] - seg["end_ms"]
            else:
                silence_ms = 0
            silence_ms = max(0, silence_ms)
            if silence_ms > 0:
                silence_len = int(silence_ms / 1000 * SAMPLE_RATE)
                wf.writeframes(b"\x00" * (silence_len * 2))

    print(f"[拼接] 写入完成: {wav_path}")

    # Ground Truth JSON
    gt_path = OUT_DIR / "test_ground_truth.json"
    total_dur_ms = segments[-1]["end_ms"] if segments else 0
    gt_data = {
        "_meta": {
            "total_duration_sec": round(total_dur_ms / 1000, 2),
            "num_speakers": len(speakers),
            "num_segments": len(segments),
            "generated_at": datetime.now().isoformat(),
        },
        "segments": segments,
    }
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(gt_data, f, ensure_ascii=False, indent=2)
    print(f"[GT] 已保存: {gt_path}")

    # 注册摘要
    reg_path = OUT_DIR / "test_registration.json"
    reg_data = {
        "generated_at": datetime.now().isoformat(),
        "num_speakers": len(speakers),
        "speakers": [{"speaker_id": s["speaker_id"], "name": s["name"]} for s in speakers],
    }
    with open(reg_path, "w", encoding="utf-8") as f:
        json.dump(reg_data, f, ensure_ascii=False, indent=2)
    print(f"[注册] 已保存: {reg_path}")


# ======================== 主流程 ========================

def main():
    print("=" * 60)
    print("InsightEye 声纹注册 + 测试数据生成")
    print("=" * 60)
    print(f"数据集: {DATASET_ROOT}")
    print(f"数据库: {DB_PATH}")
    print(f"输出目录: {OUT_DIR}")
    print()

    t_start = time.time()

    # Step 1: 注册全部 296 人
    results = _register_all_speakers()

    # 保存注册报告
    report_path = OUT_DIR / "registration_results_v3plus.json"
    report = {
        "generated_at": datetime.now().isoformat(),
        "total": len(results),
        "successful": sum(1 for r in results if r.success),
        "failed": sum(1 for r in results if not r.success),
        "results": [asdict(r) for r in results],
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[报告] 已保存: {report_path}")

    # Step 2: 生成测试音频
    _generate_test_data(num_speakers=8)

    print(f"\n总计耗时: {time.time() - t_start:.1f}s")
    print("\n全部完成!")


if __name__ == "__main__":
    main()
