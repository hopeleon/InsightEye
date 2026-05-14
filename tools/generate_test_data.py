"""
测试数据生成器 + 说话人注册脚本
====================================
功能：
  1. 从 primewords 数据集选取 5~10 个说话人
  2. 给每个说话人分配中文姓名
  3. 提取声纹并注册到 voiceprint DB
  4. 生成多人穿插拼接音频 + Ground Truth JSON（用于 benchmark 测试）

Ground Truth JSON 格式：
  {
    "_meta": { "total_duration_sec": ..., "num_speakers": ..., ... },
    "segments": [
      { "id": 1, "speaker_id": "p001", "speaker_name": "张伟",
        "start_ms": 0, "end_ms": 8200,
        "text": "标准答案文本", "audio_file": "...", ... },
      ...
    ]
  }

输出文件：
  data/test_spliced_audio.wav   — 拼接音频
  data/test_ground_truth.json   — 标准答案
  data/test_registration.json   — 注册摘要（已注册说话人列表）
"""

from __future__ import annotations

import json
import os
import random
import wave
from pathlib import Path
from typing import Optional

import numpy as np


# ======================== 配置 ========================

# Primewords 数据集根目录（指向解压后的目录）
# 下载: https://openslr.org/resources/47/primewords_md_2018_set1.tar.gz
# 解压后目录结构: E:\primewords_md_2018_set1\
#     ├── set1/
#     │   ├── 0000a4e8ef14b6bb48d200b00a42a0be/
#     │   │   └── *.mp3
#     │   └── ...
#     └── primewords_file_mapping_transcript.json
# 如解压后多了一层 primewords_md_2018_set1/ 子目录，则拼上它
DATASET_ROOT = r"E:\primewords_md_2018_set1"

# 数据集根目录（与 tools/primewords_loader.py 保持一致）
_JSON_FILENAME = "primewords_file_mapping_transcript.json"

def _resolve_dataset_paths():
    """检测实际的 JSON 和 audio root 路径"""
    root = Path(DATASET_ROOT)
    json_candidates = [
        root / _JSON_FILENAME,
        root / "primewords_md_2018_set1" / _JSON_FILENAME,
    ]
    json_path = next((p for p in json_candidates if p.exists()), None)
    if json_path is None:
        raise FileNotFoundError(
            f"找不到 {_JSON_FILENAME}，请确认数据集已解压到 {DATASET_ROOT}。"
        )
    # audio root = json 所在的 parent（即数据集根目录，由它去找 set1/）
    audio_root = json_path.parent
    return json_path, audio_root

_JSON_FILE, _AUDIO_ROOT = _resolve_dataset_paths()
JSON_FILE = str(_JSON_FILE)
AUDIO_ROOT = str(_AUDIO_ROOT)

# 输出目录
OUT_DIR = Path(r"D:\InsightEye\data")
OUT_DIR.mkdir(exist_ok=True)

SPLICED_AUDIO_PATH = OUT_DIR / "test_spliced_audio.wav"
GT_JSON_PATH = OUT_DIR / "test_ground_truth.json"
REG_JSON_PATH = OUT_DIR / "test_registration.json"

# 测试用说话人数量
NUM_SPEAKERS = 8

# 每个说话人选取多少条音频参与拼接（>=3 条用于注册，>=5 条用于拼接）
MIN_REG_SAMPLES = 3      # 最少注册样本数
MIN_AUDIO_DURATION = 1.5  # 秒，最少音频时长

# 拼接配置
# 每段音频播放时长（秒），实际会取整段（如果短于这个值）或截取（如果长于这个值）
SEGMENT_PLAY_SEC = 5.0
# 说话人之间的最小间隔（秒，静音填充）
MIN_SILENCE_SEC = 0.3
MAX_SILENCE_SEC = 1.0
# 总目标时长（秒）
TARGET_TOTAL_SEC = 180.0  # 3 分钟


# ======================== 姓名池 ========================

# 常用中文姓名，确保不重复
_CHINESE_SURNAMES = [
    "张", "王", "李", "赵", "陈", "刘", "吴", "周", "徐", "孙",
    "马", "朱", "胡", "郭", "林", "何", "高", "梁", "罗", "郑",
]

_CHINESE_GIVEN_NAMES = [
    "伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "军",
    "洋", "勇", "艳", "杰", "涛", "明", "超", "秀兰", "霞", "平",
    "刚", "桂英", "建华", "建国", "志强", "永强", "建华", "秀珍", "海燕", "小华",
]


def _generate_chinese_name(seed: int) -> str:
    """根据种子生成不重复的中文姓名"""
    rng = random.Random(seed)
    while True:
        surname = rng.choice(_CHINESE_SURNAMES)
        given = rng.choice(_CHINESE_GIVEN_NAMES)
        name = surname + given
        if len(name) <= 4:
            return name


# ======================== 数据集加载 ========================

def _load_dataset() -> dict:
    """加载数据集 JSON，返回 {file_id: {file_id, text, speaker_id, ...}}"""
    with open(JSON_FILE, encoding="utf-8") as f:
        data = json.load(f)
    # Primewords JSON：顶层是 dict，key=file_id，value={text, ...}
    if isinstance(data, dict):
        return data
    # 也可能是 list: [{"file_id":..., "text":..., ...}, ...]
    return {item["file_id"]: item for item in data}


def _discover_speakers() -> dict:
    """
    扫描音频目录，按说话人（UUID 目录名）分组音频文件。

    Returns:
        dict: {speaker_id (uuid): [file_id, ...]}
    """
    set1_root = Path(AUDIO_ROOT) / "set1"
    if not set1_root.exists():
        raise FileNotFoundError(
            f"找不到 set1/ 目录，请确认数据集解压正确。当前 AUDIO_ROOT={AUDIO_ROOT}"
        )

    speaker_index: dict[str, list[str]] = {}
    for mp3_path in sorted(set1_root.rglob("*.mp3")):
        speaker_id = mp3_path.parent.name  # UUID 就是目录名
        file_id = mp3_path.stem
        speaker_index.setdefault(speaker_id, []).append(file_id)
    return speaker_index


def _get_audio_path(file_id: str, speaker_id: str) -> str:
    """根据 file_id 和 speaker_id 返回完整音频路径（MP3）"""
    return str(Path(AUDIO_ROOT) / "set1" / speaker_id / f"{file_id}.mp3")


def _read_audio_float32(path: str) -> np.ndarray:
    """读取 MP3/WAV 文件，返回 16kHz float32 单声道 numpy 数组"""
    import librosa
    audio, sr = librosa.load(path, sr=16000, mono=True)
    return audio.astype(np.float32)


def _count_audio_files() -> int:
    """快速统计 MP3 文件总数"""
    set1_root = Path(AUDIO_ROOT) / "set1"
    if not set1_root.exists():
        return 0
    return sum(1 for _ in set1_root.rglob("*.mp3"))


# ======================== 说话人选择 ========================

def select_speakers(
    speaker_index: dict,
    dataset: dict,
    num_speakers: int = 8,
    min_utterances: int = 5,
    min_duration_sec: float = 1.5,
    seed: int = 42,
    registered_uuids: Optional[set] = None,
) -> list[dict]:
    """
    从数据集中选取音频充足、质量好的说话人。

    Args:
        speaker_index: _discover_speakers() 返回的说话人索引
        dataset: 加载好的数据集字典 {file_id: {text: ...}}
        num_speakers: 选取的说话人数量
        min_utterances: 最少需要的音频条数
        min_duration_sec: 每条音频的最短时长要求
        registered_uuids: 可选，已在主数据库注册的说话人UUID集合。
            如果提供，则只会选择这些UUID中的说话人。

    Returns:
        list of dicts: [
            {
                "speaker_id": "p001",
                "uuid": "0000a4e8ef14...",  # Primewords 原始 UUID
                "name": "张伟",
                "utterances": [
                    {"file_id": "...", "text": "...", "duration_sec": ...,
                     "audio_path": "..."},
                    ...
                ],
            },
            ...
        ]
    """
    rng = random.Random(seed)

    # 过滤出音频数量充足的说话人
    eligible = {
        sid: fids
        for sid, fids in speaker_index.items()
        if len(fids) >= min_utterances
    }

    # 如果指定了已注册UUID集合，则只从这些UUID中选择
    # （过滤掉不在主数据库中的说话人，如样本不足被跳过的46人）
    if registered_uuids is not None:
        eligible = {
            sid: fids
            for sid, fids in eligible.items()
            if sid in registered_uuids
        }

    print(f"[数据加载] 总说话人数: {len(speaker_index)}, "
          f"音频>={min_utterances}条的: {len(eligible)} 人")

    if len(eligible) < num_speakers:
        print(f"[警告] 满足条件的说话人不足 {num_speakers} 人，"
              f"将使用全部 {len(eligible)} 人")
        num_speakers = len(eligible)

    # 随机选取（固定种子确保可复现）
    selected_uuids = rng.sample(list(eligible.keys()), num_speakers)

    # 分配姓名，确保不重名
    used_names: set[str] = set()
    speakers = []
    for i, uuid in enumerate(selected_uuids):
        file_ids = eligible[uuid]
        # 构建 utterances 列表
        utterances = []
        for fid in file_ids:
            meta = dataset.get(fid, {})
            text = meta.get("text", "") or meta.get("transcript", "")
            audio_path = _get_audio_path(fid, uuid)
            if not os.path.exists(audio_path):
                continue
            # Primewords JSON 中不含 duration 字段，实际读取估算
            # 用 text 长度粗估（平均每秒 ~5 字符），后续加载时再精确计算
            duration_sec = max(len(text) / 5.0, min_duration_sec)

            utterances.append({
                "file_id": fid,
                "text": text,
                "duration_sec": duration_sec,
                "audio_path": audio_path,
            })

        if len(utterances) < min_utterances:
            continue

        # 分配姓名
        name = None
        for seed_name in range(42, 42 + 1000):
            candidate = _generate_chinese_name(seed_name)
            if candidate not in used_names:
                name = candidate
                used_names.add(name)
                break

        # 每条音频最多截取到 SEGMENT_PLAY_SEC 秒
        for utt in utterances:
            utt["play_duration_sec"] = min(utt["duration_sec"], SEGMENT_PLAY_SEC)

        speakers.append({
            "speaker_id": f"p{i+1:03d}",
            "uuid": uuid,
            "name": name,
            "utterances": utterances,
        })

    return speakers


# ======================== 声纹注册 ========================

def register_speakers_to_db(speakers: list[dict], overwrite: bool = True) -> dict:
    """
    对选中的说话人提取声纹并注册到 SQLite 数据库。

    Args:
        speakers: select_speakers() 返回的说话人列表
        overwrite: 是否覆盖已有记录

    Returns:
        注册结果摘要 dict
    """
    print("\n" + "=" * 60)
    print("开始注册声纹...")
    print("=" * 60)

    # 导入模型管理器
    import sys
    project_root = str(Path(__file__).parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from app.model_manager import ModelManager
    from app.enhanced_speaker_recognition import MultiSpeakerRegistry

    # 初始化模型管理器（只加载 CAM++，不需要 ASR）
    print("[声纹注册] 正在加载 CAM++ 模型...")
    manager = ModelManager.get_instance()

    import asyncio
    if not manager.initialized:
        asyncio.run(manager.initialize())

    # 创建注册表
    db_path = str(OUT_DIR / "speaker_voiceprints.db")
    registry = MultiSpeakerRegistry(manager, db_path=db_path)

    results = []
    for spk in speakers:
        sid = spk["speaker_id"]
        name = spk["name"]
        utts = spk["utterances"]

        print(f"\n[注册] {sid} {name}，共 {len(utts)} 条音频")

        # 加载音频（至少取 MIN_REG_SAMPLES 条）
        audio_samples = []
        for utt in utts[:max(MIN_REG_SAMPLES, len(utts))]:
            try:
                audio = _read_audio_float32(utt["audio_path"])
                audio_samples.append(audio)
                print(f"  加载: {utt['file']} ({utt['duration_sec']:.1f}s)")
            except Exception as e:
                print(f"  跳过（读取失败）: {utt['file']} — {e}")
                continue

        if len(audio_samples) < MIN_REG_SAMPLES:
            print(f"[跳过] {name} 有效音频不足 {MIN_REG_SAMPLES} 条")
            results.append({
                "speaker_id": sid,
                "name": name,
                "success": False,
                "reason": f"有效音频仅 {len(audio_samples)} 条",
            })
            continue

        # 注册
        result = registry.register_speaker(
            speaker_id=sid,
            audio_samples=audio_samples,
            name=name,
            role="测试",
            force=overwrite,
        )

        if result.success:
            # 持久化到数据库
            registry.save_to_db(sid)
            print(f"[注册成功] {name} (ID={sid})，质量={result.embedding_quality:.3f}")
        else:
            print(f"[注册失败] {name}: {result.message}")

        results.append({
            "speaker_id": sid,
            "uuid": spk["uuid"],
            "name": name,
            "success": result.success,
            "quality": result.embedding_quality,
            "sample_count": result.sample_count,
            "message": result.message,
        })

    # 保存注册摘要
    reg_summary = {
        "generated_at": __import__("datetime").datetime.now().isoformat(),
        "num_speakers": len(speakers),
        "results": results,
    }
    with open(REG_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(reg_summary, f, ensure_ascii=False, indent=2)

    success_count = sum(1 for r in results if r["success"])
    print(f"\n[注册完成] 成功 {success_count}/{len(results)} 人")
    print(f"[注册摘要] 已保存到: {REG_JSON_PATH}")

    return reg_summary


# ======================== 拼接音频 + GT 生成 ========================

def generate_spliced_audio_and_gt(
    speakers: list[dict],
    target_total_sec: float = TARGET_TOTAL_SEC,
    segment_play_sec: float = SEGMENT_PLAY_SEC,
    min_silence_sec: float = MIN_SILENCE_SEC,
    max_silence_sec: float = MAX_SILENCE_SEC,
    seed: int = 123,
) -> dict:
    """
    生成拼接音频和 Ground Truth JSON。

    拼接策略：
    - 按"穿插轮换"模式拼接：speaker_1 的第1段 → speaker_2 的第1段 → ...
      → speaker_N 的第1段 → speaker_1 的第2段 → ...
    - 每段之间插入 0.3~1.0 秒静音
    - 重复轮换直到达到目标总时长
    - 如果某个说话人音频不够，跳过他继续

    Args:
        speakers: 选中的说话人列表
        target_total_sec: 目标总时长（秒）
        segment_play_sec: 每段最长播放秒数
        seed: 随机种子（保证可复现）

    Returns:
        生成结果摘要 dict
    """
    rng = random.Random(seed)
    SAMPLE_RATE = 16000

    print("\n" + "=" * 60)
    print("开始生成拼接音频...")
    print("=" * 60)

    segments: list[dict] = []  # GT 片段列表
    current_ms = 0              # 当前已拼接的时长（毫秒）
    round_idx = 0               # 当前轮次

    # 预先加载所有音频到内存（避免频繁磁盘读取）
    print("[拼接] 预加载所有音频到内存...")
    loaded: dict[str, list[np.ndarray]] = {}
    for spk in speakers:
        spk_id = spk["speaker_id"]
        loaded[spk_id] = []
        for utt in spk["utterances"]:
            try:
                audio = _read_audio_float32(utt["audio_path"])
                # 截取到 segment_play_sec 秒
                max_samples = int(segment_play_sec * SAMPLE_RATE)
                if len(audio) > max_samples:
                    audio = audio[:max_samples]
                loaded[spk_id].append(audio)
                print(f"  {spk['name']}: {utt['file_id']} ({len(audio)/SAMPLE_RATE:.1f}s)")
            except Exception as e:
                print(f"  跳过: {utt['file']} — {e}")

    # 统计可用音频数量
    total_available = sum(len(auds) for auds in loaded.values())
    print(f"[拼接] 可用音频片段: {total_available} 段")
    if total_available == 0:
        raise RuntimeError("没有可用的音频片段！")

    # 穿插轮换拼接
    print("[拼接] 开始轮换拼接...")
    while current_ms / 1000.0 < target_total_sec:
        any_added = False

        for spk in speakers:
            spk_id = spk["speaker_id"]
            spk_name = spk["name"]
            auds = loaded.get(spk_id, [])

            if round_idx >= len(auds):
                # 该说话人这段用完了
                continue

            audio = auds[round_idx]
            audio_len_samples = len(audio)
            audio_dur_ms = int(audio_len_samples / SAMPLE_RATE * 1000)

            # 找到对应的文本（如果音频被截断，文本也要对应截取）
            utt = spk["utterances"][round_idx]
            text = utt["text"]

            # 如果音频被截断，文本也按比例截取
            if utt["duration_sec"] > segment_play_sec:
                # 按比例截取文本（简单取前 70% 的字符）
                keep_ratio = segment_play_sec / utt["duration_sec"]
                keep_chars = int(len(text) * keep_ratio * 0.85)
                text = text[:max(keep_chars, 1)]

            seg_start_ms = current_ms
            seg_end_ms = current_ms + audio_dur_ms

            segments.append({
                "id": len(segments) + 1,
                "speaker_id": spk_id,
                "speaker_name": spk_name,
                "start_ms": seg_start_ms,
                "end_ms": seg_end_ms,
                "duration_ms": audio_dur_ms,
                "text": text,
                "audio_file": utt["file_id"],
                "round": round_idx + 1,
            })

            # 写入静音间隔
            silence_len_ms = int(
                rng.uniform(min_silence_sec, max_silence_sec) * 1000
            )
            current_ms = seg_end_ms + silence_len_ms
            any_added = True

        round_idx += 1

        # 防止无限循环（万一音频太少无法达到目标时长）
        if round_idx > 50:
            print(f"[警告] 轮次已达 {round_idx}，停止拼接（可能音频不足）")
            break

        if not any_added:
            break

    # 合并相邻静音区（去除过短的静音）
    print(f"[拼接] 生成 {len(segments)} 个片段，总时长 {current_ms/1000:.1f}s")

    # 构建拼接音频（在内存中拼接所有片段 + 静音）
    print(f"[拼接] 构建拼接音频波形...")
    all_samples: list[np.ndarray] = []
    for seg in segments:
        spk = next(s for s in speakers if s["speaker_id"] == seg["speaker_id"])
        utt = next(u for u in spk["utterances"] if u["file_id"] == seg["audio_file"])
        audio = _read_audio_float32(utt["audio_path"])

        # 截取到片段时长
        max_samples = int(seg["duration_ms"] / 1000 * SAMPLE_RATE)
        if len(audio) > max_samples:
            audio = audio[:max_samples]
        all_samples.append(audio)

        # 在末尾追加静音
        idx = segments.index(seg)
        if idx < len(segments) - 1:
            silence_ms = segments[idx + 1]["start_ms"] - seg["end_ms"]
        elif idx > 0:
            silence_ms = seg["start_ms"] - segments[idx - 1]["end_ms"]
        else:
            silence_ms = 0
        silence_ms = max(0, silence_ms)
        if silence_ms > 0:
            silence_len = int(silence_ms / 1000 * SAMPLE_RATE)
            all_samples.append(np.zeros(silence_len, dtype=np.float32))

    # 写入 WAV 文件
    spliced_audio = np.concatenate(all_samples) if all_samples else np.zeros(int(1 * SAMPLE_RATE), dtype=np.float32)
    print(f"[拼接] 写入音频: {SPLICED_AUDIO_PATH}")
    with wave.open(str(SPLICED_AUDIO_PATH), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        int16_data = np.clip(spliced_audio * 32767, -32768, 32767).astype(np.int16)
        wf.writeframes(int16_data.tobytes())
    print(f"[拼接] 写入完成: {len(spliced_audio)} 样本, {len(spliced_audio)/SAMPLE_RATE:.1f}s")

    # 生成 GT JSON
    total_dur_ms = segments[-1]["end_ms"] if segments else 0
    gt_data = {
        "_meta": {
            "total_duration_sec": round(total_dur_ms / 1000, 2),
            "num_speakers": len(speakers),
            "num_segments": len(segments),
            "target_duration_sec": target_total_sec,
            "generated_at": __import__("datetime").datetime.now().isoformat(),
            "splicing_method": "round_robin",
            "speakers": [
                {"speaker_id": s["speaker_id"], "speaker_name": s["name"]}
                for s in speakers
            ],
        },
        "segments": segments,
    }

    with open(GT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(gt_data, f, ensure_ascii=False, indent=2)

    print(f"[拼接] 标准答案已保存: {GT_JSON_PATH}")
    print(f"[拼接] 片段分布：")
    for spk in speakers:
        cnt = sum(1 for seg in segments if seg["speaker_id"] == spk["speaker_id"])
        print(f"  {spk['name']} ({spk['speaker_id']}): {cnt} 段")

    return {
        "total_segments": len(segments),
        "total_duration_sec": round(total_dur_ms / 1000, 2),
        "num_speakers": len(speakers),
        "spliced_audio_path": str(SPLICED_AUDIO_PATH),
        "gt_json_path": str(GT_JSON_PATH),
    }


# ======================== 主流程 ========================

def main():
    import sys
    from pathlib import Path
    project_root = str(Path(__file__).parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    print("=" * 60)
    print("InsightEye 测试数据生成器")
    print("=" * 60)
    print(f"数据集: {DATASET_ROOT}")
    print(f"输出目录: {OUT_DIR}")
    print(f"目标说话人: {NUM_SPEAKERS} 人")
    print(f"目标拼接时长: {TARGET_TOTAL_SEC} 秒")
    print()

    # Step 1: 加载数据集
    print("[1/4] 加载数据集...")
    print(f"  JSON: {JSON_FILE}")
    print(f"  音频根目录: {AUDIO_ROOT}")
    dataset = _load_dataset()
    print(f"  加载完成：{len(dataset)} 条音频记录")
    speaker_index = _discover_speakers()
    print(f"  扫描完成：{len(speaker_index)} 个说话人，{_count_audio_files()} 个 MP3 文件")

    # Step 2: 选择说话人
    print(f"\n[2/4] 从数据集中选取 {NUM_SPEAKERS} 个说话人...")
    speakers = select_speakers(
        speaker_index,
        dataset,
        num_speakers=NUM_SPEAKERS,
        min_utterances=5,
        min_duration_sec=MIN_AUDIO_DURATION,
        seed=42,
    )
    for spk in speakers:
        total_dur = sum(u["duration_sec"] for u in spk["utterances"])
        print(f"  {spk['speaker_id']} {spk['name']}: "
              f"{len(spk['utterances'])} 条音频, 共 {total_dur:.0f}s")

    global _current_speakers
    _current_speakers = speakers

    # Step 3: 注册声纹
    print(f"\n[3/4] 提取并注册 {len(speakers)} 个说话人的声纹...")
    reg_summary = register_speakers_to_db(speakers, overwrite=True)

    # Step 4: 生成拼接音频 + GT
    print(f"\n[4/4] 生成拼接音频和标准答案...")
    gen_result = generate_spliced_audio_and_gt(
        speakers,
        target_total_sec=TARGET_TOTAL_SEC,
        seed=123,
    )

    # 完成
    print("\n" + "=" * 60)
    print("全部完成！")
    print("=" * 60)
    print(f"  声纹数据库: {OUT_DIR / 'speaker_voiceprints.db'}")
    print(f"  注册摘要:   {REG_JSON_PATH}")
    print(f"  拼接音频:   {SPLICED_AUDIO_PATH}")
    print(f"  标准答案:   {GT_JSON_PATH}")
    print()
    print("下一步：启动 run_demo.py，然后用 benchmark_engine.py 测试识别准确率")


if __name__ == "__main__":
    main()
