import sqlite3

conn = sqlite3.connect('D:/InsightEye/data/speaker_voiceprints.db')
cursor = conn.cursor()

# 删除钟一、钟二、钟三（彻底删除，不只是标记为非活跃）
for name in ['钟一', '钟二', '钟三']:
    cursor.execute('DELETE FROM speaker_profiles WHERE name = ?', (name,))
    print(f"删除 {name}: 影响 {cursor.rowcount} 条")

conn.commit()

# 验证
cursor.execute('SELECT COUNT(*) FROM speaker_profiles WHERE is_active = 1')
count = cursor.fetchone()[0]
print(f"\n删除后活跃人员总数: {count}")

conn.close()
print("\n已彻底删除钟一、钟二、钟三！")
