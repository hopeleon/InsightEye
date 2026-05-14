import sqlite3
conn = sqlite3.connect('d:/InsightEye/data/speaker_voiceprints.db')
cursor = conn.cursor()
cursor.execute('SELECT speaker_id, name, sample_count FROM speakers LIMIT 10')
for row in cursor.fetchall():
    print(row)
cursor.execute('SELECT COUNT(*) FROM speakers')
print('Total:', cursor.fetchone()[0])
conn.close()
