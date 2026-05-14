"""
为数据库中所有说话人分配唯一中文姓名
"""
import random
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "speaker_voiceprints.db"

_SURNAMES = [
    "张", "王", "李", "赵", "陈", "刘", "吴", "周", "徐", "孙",
    "马", "朱", "胡", "郭", "林", "何", "高", "梁", "罗", "郑",
    "杨", "黄", "徐", "孙", "马", "朱", "胡", "郭", "林", "何",
]
_GIVEN_NAMES = [
    "伟", "芳", "娜", "秀英", "敏", "静", "丽", "强", "磊", "军",
    "洋", "勇", "艳", "杰", "涛", "明", "超", "秀兰", "霞", "平",
    "刚", "桂英", "建华", "建国", "志强", "永强", "秀珍", "海燕", "小华", "鹏",
    "婷", "颖", "丹", "莉", "波", "宇", "浩", "鑫", "琪", "琳",
    "欣", "晨", "雪", "梅", "娟", "芬", "燕", "玲", "红", "兰",
    "龙", "华", "峰", "志", "勇", "杰", "鹏", "云", "飞", "辉",
]

def generate_unique_name(seed: int, used: set) -> str:
    rng = random.Random(seed)
    attempts = 0
    while attempts < 10000:
        name = rng.choice(_SURNAMES) + rng.choice(_GIVEN_NAMES)
        if len(name) <= 4 and name not in used:
            return name
        attempts += 1
    # fallback: append number
    for i in range(1000):
        name = rng.choice(_SURNAMES) + rng.choice(_GIVEN_NAMES) + str(i)
        if name not in used:
            return name
    return f"用户{seed}"

def main():
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute("SELECT speaker_id FROM speaker_profiles").fetchall()
    print(f"读取到 {len(rows)} 个说话人")

    used_names: set[str] = set()
    updated = 0

    for (sid,) in rows:
        # Check current name
        current = conn.execute(
            "SELECT name FROM speaker_profiles WHERE speaker_id = ?", (sid,)
        ).fetchone()
        current_name = current[0] if current else ""

        # If already has a proper Chinese name (len <= 4, no 'pw_' prefix), skip
        if current_name and not current_name.startswith("pw_") and len(current_name) <= 6:
            used_names.add(current_name)
            continue

        # Generate new name
        name = generate_unique_name(int(sid) * 7 + 13, used_names)
        used_names.add(name)
        conn.execute(
            "UPDATE speaker_profiles SET name = ? WHERE speaker_id = ?",
            (name, sid)
        )
        updated += 1

    conn.commit()
    conn.close()
    print(f"更新了 {updated} 个姓名")

    # Verify uniqueness
    conn2 = sqlite3.connect(str(DB_PATH))
    all_names = [r[0] for r in conn2.execute("SELECT name FROM speaker_profiles").fetchall()]
    conn2.close()
    dupes = len(all_names) - len(set(all_names))
    print(f"总计 {len(all_names)} 人，重复姓名: {dupes}")

if __name__ == "__main__":
    main()
