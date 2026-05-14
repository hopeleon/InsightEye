import sqlite3
db_path = r'D:\InsightEye\data\speaker_voiceprints.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# Show speaker_profiles columns
cur.execute("PRAGMA table_info(speaker_profiles)")
cols = cur.fetchall()
print("speaker_profiles columns:", [c[1] for c in cols])

# Show speaker_embeddings columns
cur.execute("PRAGMA table_info(speaker_embeddings)")
cols2 = cur.fetchall()
print("speaker_embeddings columns:", [c[1] for c in cols2])

# Count embeddings per speaker
# Count embeddings per speaker
cur.execute("""
    SELECT sp.speaker_id, sp.name, sp.sample_count, COUNT(se.speaker_id) as embed_count
    FROM speaker_profiles sp
    LEFT JOIN speaker_embeddings se ON sp.speaker_id = se.speaker_id
    GROUP BY sp.speaker_id
    ORDER BY sp.speaker_id
""")
rows = cur.fetchall()
print(f"\nRegistered speakers: {len(rows)}")
for r in rows:
    print(f"  {r[0]}: {r[1]} | DB sample_count={r[2]}, embeddings in DB={r[3]}")

conn.close()
