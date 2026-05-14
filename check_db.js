const sqlite3 = require('better-sqlite3');
const path = require('path');

const dbPath = path.join(__dirname, 'data', 'speaker_voiceprints.db');
console.log('DB path:', dbPath);

let db;
try {
    db = sqlite3(dbPath);
} catch (e) {
    console.error('Failed to open db:', e.message);
    process.exit(1);
}

// 查看所有说话人
console.log('\n=== 所有说话人 ===');
const rows = db.prepare('SELECT speaker_id, name, role, is_active FROM speaker_profiles ORDER BY speaker_id').all();
for (const row of rows) {
    console.log(`speaker_id=${row.speaker_id}, name=${row.name}, role=${row.role}, is_active=${row.is_active}`);
}

// 查看名字为'高伟'的说话人
console.log('\n=== 名字包含"高伟"的说话人 ===');
const rows2 = db.prepare('SELECT speaker_id, name, role, is_active FROM speaker_profiles WHERE name LIKE ?').all('%高伟%');
for (const row of rows2) {
    console.log(`speaker_id=${row.speaker_id}, name=${row.name}, role=${row.role}, is_active=${row.is_active}`);
}

db.close();
