"""
从已注册的 250 人中选取说话人，生成 benchmark 测试音频 + 标准答案
从 register_and_test.py 的数据集路径加载音频。
"""
import json
import os
import random
import sys
import time
import wave
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SAMPLE_RATE = 16000

DATASET_ROOT = Path(r"E:\primewords_md_2018_set1\primewords_md_2018_set1")
JSON_FILE = DATASET_ROOT / "set1_transcript.json"
AUDIO_ROOT = DATASET_ROOT / "audio_files"
DB_PATH = PROJECT_ROOT / "data" / "speaker_voiceprints.db"
OUT_DIR = PROJECT_ROOT / "data" / "benchmark"
OUT_DIR.mkdir(exist_ok=True)


def _build_audio_path(fname: str) -> str:
    p1 = fname[0]
    p2 = fname[:2]
    return str(AUDIO_ROOT / p1 / p2 / fname)


def _read_wav_float32(path: str) -> np.ndarray:
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
    try:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _load_dataset() -> tuple[dict, dict]:
    print(f"[加载] 读取 {JSON_FILE} ...")
    with open(JSON_FILE, encoding="utf-8") as f:
        data = json.load(f)

    by_user = defaultdict(list)
    by_uuid = {}
    for item in data:
        by_user[item["user_id"]].append(item)
        by_uuid[item["file"]] = item

    print(f"[加载] 完成：{len(by_user)} 个说话人，{len(data)} 条音频")
    return by_user, by_uuid


def _get_registered_speakers() -> dict[str, str]:
    """返回 {speaker_id: chinese_name}"""
    import sqlite3
    rows = {}
    conn = sqlite3.connect(str(DB_PATH))
    for sid, name in conn.execute("SELECT speaker_id, name FROM speaker_profiles"):
        rows[str(sid)] = name
    conn.close()
    return rows


def _extract_and_register(
    speakers: list[dict],
    num_reg_samples: int = 5,
) -> list[dict]:
    """
    从数据集中加载指定说话人的音频，注册声纹，生成测试音频。
    speakers: [{speaker_id, name, uuid, utterances}]
    """
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

    by_user, _ = _load_dataset()

    registered = []
    for spk in speakers:
        raw_uid = spk["speaker_id"]
        sid = raw_uid.replace("pw_", "")  # "pw_1136" -> "1136"
        name = spk["name"]
        items = by_user.get(sid, [])

        print(f"\n[注册] {sid} {name}，{len(items)} 条音频")

        # 收集音频（>= 1秒）
        audio_list = []
        valid_items = []
        for item in items:
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
            except Exception as e:
                print(f"  跳过: {item['file']} — {e}")
                continue
            if len(audio_list) >= 20:
                break

        if len(audio_list) < 3:
            print(f"  [跳过] 有效音频不足 {len(audio_list)}")
            continue

        # 提取声纹（前 num_reg_samples 条用于注册）
        embeddings = []
        for audio in audio_list[:num_reg_samples]:
            try:
                emb = extractor.extract(audio)
                embeddings.append(emb)
            except Exception as e:
                print(f"  声纹提取失败: {e}")
                continue

        if len(embeddings) < 2:
            print(f"  [跳过] 声纹提取成功数不足 {len(embeddings)}")
            continue

        avg_emb = np.mean(embeddings, axis=0)
        avg_emb = avg_emb / (np.linalg.norm(avg_emb) + 1e-8)
        quality = float(np.mean([np.linalg.norm(e) for e in embeddings]))

        # 更新 DB 中的姓名（确保一致）
        db.save_speaker(
            speaker_id=sid,
            embedding=avg_emb.astype(np.float32),
            name=name,
            individual_embeddings=[e.astype(np.float32) for e in embeddings],
            quality=quality,
            sample_count=len(embeddings),
            overwrite=True,
        )
        registry.register_embedding(sid, avg_emb, name=name, force=True)

        # 写注册音频到 benchmark 目录（用于参考）
        reg_dir = OUT_DIR / "registration_audio" / f"pw_{sid}"
        reg_dir.mkdir(parents=True, exist_ok=True)
        reg_audio = audio_list[0]
        reg_path = reg_dir / "reg_audio.wav"
        with wave.open(str(reg_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            int16 = np.clip(reg_audio * 32767, -32768, 32767).astype(np.int16)
            wf.writeframes(int16.tobytes())
        print(f"  注册音频已保存: {reg_path}")

        registered.append({
            "speaker_id": f"pw_{sid}",
            "name": name,
            "uid": sid,
            "reg_audio": str(reg_path),
            "num_reg": len(embeddings),
            "audio_list": audio_list,
            "items": valid_items,
        })
        print(f"  [成功] 质量={quality:.3f}，注册样本={len(embeddings)}，"
              f"测试样本={len(audio_list) - num_reg_samples}")

    return registered


def _splice_audio(
    speakers: list[dict],
    target_total_sec: float = 240.0,
    segment_play_sec: float = 5.0,
    min_silence: float = 0.3,
    max_silence: float = 1.0,
    seed: int = 42,
) -> tuple[list[dict], float]:
    """生成拼接音频 + ground truth segments"""
    rng = random.Random(seed)
    SEGMENT_PLAY_SEC = segment_play_sec

    segments = []
    current_ms = 0
    round_idx = 0

    while current_ms / 1000.0 < target_total_sec:
        any_added = False
        for spk in speakers:
            if round_idx >= len(spk["audio_list"]):
                continue

            audio = spk["audio_list"][round_idx]
            item = spk["items"][round_idx]

            # 不截断，使用完整音频，确保音频与文本一致
            audio_clip = audio
            dur_ms = int(len(audio_clip) / SAMPLE_RATE * 1000)

            text = item.get("text", "").strip()

            segments.append({
                "id": len(segments) + 1,
                "speaker_id": spk["speaker_id"],
                "speaker_name": spk["name"],
                "start_ms": current_ms,
                "end_ms": current_ms + dur_ms,
                "duration_ms": dur_ms,
                "text": text[:100] if text else "",
                "audio_file": item["file"],
                "round": round_idx + 1,
                "_audio_clip": audio_clip,  # 直接存储裁剪后的音频，不依赖 round 索引重查
            })

            silence_ms = int(rng.uniform(min_silence, max_silence) * 1000)
            current_ms = current_ms + dur_ms + silence_ms
            any_added = True

        round_idx += 1
        if round_idx > 50 or not any_added:
            break

    # 写入 WAV
    print(f"\n[拼接] {len(segments)} 个片段，总时长 {current_ms/1000:.1f}s，"
          f"写入 {OUT_DIR / 'test_meeting_spliced.wav'} ...")
    wav_path = OUT_DIR / "test_meeting_spliced.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)

        for i, seg in enumerate(segments):
            audio_clip = seg["_audio_clip"]
            int16 = np.clip(audio_clip * 32767, -32768, 32767).astype(np.int16)
            wf.writeframes(int16.tobytes())

            # 静音间隔
            silence_ms = 0
            if i < len(segments) - 1:
                silence_ms = segments[i + 1]["start_ms"] - seg["end_ms"]
            else:
                silence_ms = seg["start_ms"] - segments[i - 1]["end_ms"] if i > 0 else 0
            silence_ms = max(0, silence_ms)
            if silence_ms > 0:
                silence_len = int(silence_ms / 1000 * SAMPLE_RATE)
                wf.writeframes(b"\x00" * (silence_len * 2))

    print(f"[拼接] 完成: {wav_path} ({len(segments)} segments)")

    total_dur_ms = segments[-1]["end_ms"] if segments else 0
    return segments, total_dur_ms / 1000.0


def main():
    print("=" * 60)
    print("InsightEye Benchmark 测试数据生成")
    print("=" * 60)
    print(f"数据集: {DATASET_ROOT}")
    print(f"数据库: {DB_PATH}")
    print(f"输出目录: {OUT_DIR}")
    print()

    # Step 1: 从 DB 读取已注册说话人
    registered = _get_registered_speakers()
    print(f"[DB] 已注册说话人: {len(registered)} 人")
    eligible = [(sid, name) for sid, name in registered.items()]
    print(f"[候选] 可用说话人: {len(eligible)} 人")

    if len(eligible) < 8:
        print("[错误] 可用说话人不足 8 人")
        sys.exit(1)

    # Step 2: 随机选取 8 人（固定种子保证可复现）
    rng = random.Random(999)
    selected = rng.sample(eligible, 8)
    print(f"[选择] 选取 8 人:")
    for sid, name in selected:
        print(f"  pw_{sid} -> {name}")

    # Step 3: 加载音频并提取声纹（更新 DB 姓名）
    print(f"\n{'='*60}")
    print("Step 1: 加载音频 + 注册声纹")
    print("=" * 60)
    speaker_objs = []
    for sid, name in selected:
        speaker_objs.append({
            "speaker_id": f"pw_{sid}",
            "name": name,
            "uuid": sid,
        })

    reg_speakers = _extract_and_register(speaker_objs)
    print(f"\n[注册] 成功注册 {len(reg_speakers)}/{len(speaker_objs)} 人")

    if not reg_speakers:
        print("[错误] 没有成功注册的说话人")
        sys.exit(1)

    # Step 4: 生成拼接音频
    print(f"\n{'='*60}")
    print("Step 2: 生成拼接音频 + 标准答案")
    print("=" * 60)
    segments, total_dur = _splice_audio(reg_speakers, target_total_sec=240.0)

    # Step 5: 保存 Ground Truth JSON
    serializable_segments = [
        {k: v for k, v in seg.items() if not k.startswith("_")}
        for seg in segments
    ]
    gt_data = {
        "_meta": {
            "total_duration_sec": round(total_dur, 2),
            "num_speakers": len(reg_speakers),
            "num_segments": len(segments),
            "generated_at": datetime.now().isoformat(),
            "splicing_method": "round_robin",
            "speakers": [
                {"speaker_id": s["speaker_id"], "speaker_name": s["name"], "uid": s["uid"]}
                for s in reg_speakers
            ],
        },
        "segments": serializable_segments,
    }
    gt_path = OUT_DIR / "test_ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(gt_data, f, ensure_ascii=False, indent=2)
    print(f"[GT] 已保存: {gt_path}")

    # Step 6: 保存 Speaker Name Map
    name_map = {s["uid"]: s["name"] for s in reg_speakers}
    name_map_path = OUT_DIR / "speaker_name_map.json"
    with open(name_map_path, "w", encoding="utf-8") as f:
        json.dump(name_map, f, ensure_ascii=False, indent=2)
    print(f"[NameMap] 已保存: {name_map_path}")

    # Step 7: 保存 Generation Summary
    summary = {
        "output_dir": str(OUT_DIR),
        "wav": str(OUT_DIR / "test_meeting_spliced.wav"),
        "gt_json": str(gt_path),
        "name_map": str(name_map_path),
        "num_speakers": len(reg_speakers),
        "total_duration_sec": round(total_dur, 2),
        "num_segments": len(segments),
        "speakers": [
            {
                "speaker_id": s["speaker_id"],
                "name": s["name"],
                "uid": s["uid"],
                "reg_audio": s["reg_audio"],
                "num_reg": s["num_reg"],
                "num_test": len(s["audio_list"]),
            }
            for s in reg_speakers
        ],
    }
    summary_path = OUT_DIR / "generation_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[Summary] 已保存: {summary_path}")

    print()
    print("=" * 60)
    print("全部完成！")
    print("=" * 60)
    for s in reg_speakers:
        print(f"  {s['speaker_id']} {s['name']}: "
              f"注册样本={s['num_reg']}, 测试样本={len(s['audio_list'])}")
    print(f"\n下一步：启动 run_demo.py，然后用 benchmark_engine.py 测试识别准确率")


if __name__ == "__main__":
    main()
