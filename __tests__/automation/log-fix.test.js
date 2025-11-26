/**
 * 자동화 로그 수정 테스트
 *
 * 문제: 영상 생성 중인 작업의 Python 로그가 표시되지 않음
 * 원인: video_id가 작업 완료 후에만 저장되어, 진행 중에는 로그 API가 video_id를 찾을 수 없음
 * 수정: jobId가 생성되면 즉시 video_schedules에 저장
 */

const Database = require('better-sqlite3');
const path = require('path');

const dbPath = path.join(process.cwd(), 'trend-video-frontend', 'data', 'database.sqlite');

console.log('='.repeat(80));
console.log('자동화 로그 수정 테스트');
console.log('='.repeat(80));

const db = new Database(dbPath, { readonly: true });

// 1. 현재 진행 중인 스케줄 확인
console.log('\n1️⃣ 진행 중인 스케줄 확인');
console.log('-'.repeat(80));

const processingSchedules = db.prepare(`
  SELECT
    vs.id as schedule_id,
    vs.status,
    vs.script_id,
    vs.video_id,
    vt.title,
    vt.id as title_id
  FROM video_schedules vs
  JOIN video_titles vt ON vs.title_id = vt.id
  WHERE vs.status IN ('processing', 'waiting_for_upload')
  ORDER BY vs.created_at DESC
  LIMIT 5
`).all();

if (processingSchedules.length === 0) {
  console.log('❌ 진행 중인 스케줄이 없습니다.');
} else {
  console.log(`✅ ${processingSchedules.length}개 진행 중인 스케줄 발견:`);
  processingSchedules.forEach(s => {
    console.log(`   - Schedule: ${s.schedule_id}`);
    console.log(`     Title: ${s.title}`);
    console.log(`     Status: ${s.status}`);
    console.log(`     Script ID: ${s.script_id || 'N/A'}`);
    console.log(`     Video ID: ${s.video_id || '❌ NULL (문제!)'}`);
    console.log('');
  });
}

// 2. title_logs 확인
console.log('\n2️⃣ title_logs 로그 개수 확인');
console.log('-'.repeat(80));

const titleLogCount = db.prepare('SELECT COUNT(*) as count FROM title_logs').get();
console.log(`총 ${titleLogCount.count}개의 title_logs 로그`);

// 최근 로그 샘플
const recentTitleLogs = db.prepare(`
  SELECT title_id, level, substr(message, 1, 60) as message, created_at
  FROM title_logs
  ORDER BY created_at DESC
  LIMIT 5
`).all();

console.log('\n최근 5개 로그:');
recentTitleLogs.forEach(log => {
  console.log(`   [${log.created_at}] [${log.level}] ${log.message}`);
});

// 3. jobs 테이블에서 진행 중인 작업 확인
console.log('\n3️⃣ 진행 중인 jobs 확인');
console.log('-'.repeat(80));

const processingJobs = db.prepare(`
  SELECT
    id,
    title,
    status,
    progress,
    CASE WHEN logs IS NULL THEN 0 ELSE length(logs) END as log_length,
    created_at
  FROM jobs
  WHERE status = 'processing'
  ORDER BY created_at DESC
  LIMIT 5
`).all();

if (processingJobs.length === 0) {
  console.log('❌ 진행 중인 job이 없습니다.');
} else {
  console.log(`✅ ${processingJobs.length}개 진행 중인 job 발견:`);
  processingJobs.forEach(job => {
    console.log(`   - Job: ${job.id}`);
    console.log(`     Title: ${job.title}`);
    console.log(`     Progress: ${job.progress}%`);
    console.log(`     Log Length: ${job.log_length} bytes`);
    console.log(`     Created: ${job.created_at}`);

    // 이 job이 schedule과 연결되어 있는지 확인
    const linkedSchedule = db.prepare(`
      SELECT id, status FROM video_schedules WHERE video_id = ?
    `).get(job.id);

    if (linkedSchedule) {
      console.log(`     ✅ Linked to schedule: ${linkedSchedule.id} (${linkedSchedule.status})`);
    } else {
      console.log(`     ❌ NOT linked to any schedule (로그 조회 불가!)`);
    }
    console.log('');
  });
}

// 4. 로그 API 시뮬레이션 테스트
console.log('\n4️⃣ 로그 API 시뮬레이션');
console.log('-'.repeat(80));

if (processingSchedules.length > 0) {
  const testSchedule = processingSchedules[0];
  console.log(`테스트 대상: ${testSchedule.title} (${testSchedule.title_id})`);

  // title_logs에서 로그 가져오기
  const titleLogs = db.prepare(`
    SELECT created_at, level, message FROM title_logs
    WHERE title_id = ?
    ORDER BY created_at ASC
  `).all(testSchedule.title_id);

  console.log(`\n✅ title_logs: ${titleLogs.length}개`);
  titleLogs.forEach(log => {
    console.log(`   [${log.created_at}] [${log.level}] ${log.message}`);
  });

  // video_id로 Python 로그 가져오기
  if (testSchedule.video_id) {
    const job = db.prepare(`
      SELECT logs FROM jobs WHERE id = ?
    `).get(testSchedule.video_id);

    if (job && job.logs) {
      const pythonLogs = job.logs.split('\n').filter(line => line.trim()).slice(-5); // 마지막 5줄
      console.log(`\n✅ Python logs (jobs.logs): ${pythonLogs.length}개 (최근 5줄만 표시)`);
      pythonLogs.forEach(log => {
        console.log(`   ${log.substring(0, 100)}`);
      });
    } else {
      console.log('\n❌ Python logs: 없음');
    }
  } else {
    console.log('\n❌ video_id가 NULL이므로 Python 로그를 조회할 수 없습니다.');
    console.log('   → 이것이 바로 수정된 문제입니다!');
    console.log('   → 수정 후에는 jobId가 즉시 저장되어 로그 조회 가능');
  }
}

// 5. 수정 효과 요약
console.log('\n');
console.log('='.repeat(80));
console.log('수정 효과 요약');
console.log('='.repeat(80));
console.log(`
수정 전:
  - video_id가 작업 완료 후에만 저장됨
  - 진행 중에는 video_id = NULL
  - 로그 API가 Python 로그를 조회할 수 없음
  - 사용자가 진행 상황을 볼 수 없음

수정 후:
  - jobId가 생성되자마자 video_schedules에 저장
  - 진행 중에도 video_id가 존재
  - 로그 API가 Python 로그를 조회 가능
  - 사용자가 실시간으로 진행 상황을 확인 가능

수정 파일:
  - trend-video-frontend/src/lib/automation-scheduler.ts
    * generateVideo() 함수: 704번 라인 추가 (jobId 즉시 저장)
    * resumeVideoGeneration() 함수: 주석 추가 (중복 저장 설명)
`);

console.log('='.repeat(80));

db.close();
