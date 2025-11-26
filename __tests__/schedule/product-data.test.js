const Database = require('better-sqlite3');
const path = require('path');

const dbPath = path.join(__dirname, 'trend-video-frontend', 'data', 'database.sqlite');
const db = new Database(dbPath);

// 1. Test raw SQL query
console.log('=== Test 1: Raw SQL Query ===');
const rawResult = db.prepare(`
  SELECT
    s.*,
    t.title,
    t.type,
    t.product_data,
    t.product_url
  FROM video_schedules s
  JOIN video_titles t ON s.title_id = t.id
  WHERE s.id = 'schedule_1763293799387_xt22871o7'
`).get();

console.log('Keys:', Object.keys(rawResult));
console.log('Has product_data?:', !!rawResult.product_data);
console.log('product_data value:', rawResult.product_data);
console.log('type:', rawResult.type);
console.log('');

// 2. Test getPendingSchedules query format
console.log('=== Test 2: getPendingSchedules Format ===');
const pendingResult = db.prepare(`
  SELECT
    s.*,
    t.title,
    t.type,
    t.category,
    t.tags,
    t.user_id,
    t.product_url,
    t.product_data,
    t.script_mode,
    t.media_mode,
    t.model,
    t.youtube_schedule,
    t.channel as channel
  FROM video_schedules s
  JOIN video_titles t ON s.title_id = t.id
  WHERE s.id = 'schedule_1763293799387_xt22871o7'
`).get();

console.log('Keys:', Object.keys(pendingResult));
console.log('Has product_data?:', !!pendingResult.product_data);
console.log('product_data value:', pendingResult.product_data);
console.log('type:', pendingResult.type);

db.close();
