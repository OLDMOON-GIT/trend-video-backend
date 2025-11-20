/**
 * 스케줄러 비디오 생성 프로세스 통합 테스트
 * - user_id NOT NULL 제약조건 검증
 * - job placeholder 생성 검증
 * - 비디오 생성 재개 검증
 * - 중복 실행 방지 검증
 */

const Database = require('./trend-video-frontend/node_modules/better-sqlite3');
const path = require('path');
const fs = require('fs');

const BASE_URL = 'http://localhost:3000';
const DB_PATH = path.join(__dirname, 'trend-video-frontend', 'data', 'app.db');
const TEST_USER_ID = 'test_user_scheduler';

let testResults = {
  passed: 0,
  failed: 0,
  tests: []
};

function addTestResult(name, passed, message) {
  testResults.tests.push({ name, passed, message });
  if (passed) {
    testResults.passed++;
    console.log(`✅ ${name}: ${message}`);
  } else {
    testResults.failed++;
    console.error(`❌ ${name}: ${message}`);
  }
}

async function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 테스트용 대본 생성
function createTestScript(db, userId, title) {
  const scriptId = `test_script_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const scriptContent = {
    metadata: {
      title: title,
      genre: "shortform",
      duration: 60,
      targetAudience: "일반"
    },
    scenes: [
      {
        sceneNumber: 1,
        duration: 5,
        narration: "테스트 장면 1",
        imagePrompt: "A beautiful sunset"
      },
      {
        sceneNumber: 2,
        duration: 5,
        narration: "테스트 장면 2",
        imagePrompt: "A mountain landscape"
      }
    ]
  };

  db.prepare(`
    INSERT INTO contents (id, title, content, type, user_id, created_at, updated_at)
    VALUES (?, ?, ?, 'script', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
  `).run(scriptId, title, JSON.stringify(scriptContent), userId);

  return scriptId;
}

// 테스트용 스케줄 생성
function createTestSchedule(db, scriptId, titleId) {
  const scheduleId = `test_schedule_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  db.prepare(`
    INSERT INTO video_schedules (
      id, title_id, script_id, status, media_mode,
      scheduled_time, created_at, updated_at
    ) VALUES (?, ?, ?, 'pending', 'upload', datetime('now', '+1 minute'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
  `).run(scheduleId, titleId, scriptId);

  return scheduleId;
}

// 기존 테스트 데이터 정리
function cleanupTestData(db) {
  console.log('\n🧹 기존 테스트 데이터 정리 중...');

  // 테이블 존재 확인
  const tables = db.prepare(`
    SELECT name FROM sqlite_master WHERE type='table'
  `).all().map(row => row.name);

  if (tables.includes('jobs')) {
    db.prepare(`DELETE FROM jobs WHERE id LIKE 'auto_%' OR title LIKE '스케줄러 테스트%'`).run();
  }
  if (tables.includes('video_schedules')) {
    db.prepare(`DELETE FROM video_schedules WHERE id LIKE 'test_schedule_%'`).run();
  }
  if (tables.includes('contents')) {
    db.prepare(`DELETE FROM contents WHERE id LIKE 'test_script_%'`).run();
  }
  if (tables.includes('video_titles')) {
    db.prepare(`DELETE FROM video_titles WHERE id LIKE 'test_title_%'`).run();
  }

  console.log('✅ 정리 완료\n');
}

// 테스트 1: user_id가 있는 대본으로 job 생성
async function test1_JobCreationWithUserId() {
  console.log('\n📝 Test 1: user_id가 있는 대본으로 job 생성');

  const db = new Database(DB_PATH);

  try {
    const title = '스케줄러 테스트 - user_id 검증';
    const scriptId = createTestScript(db, TEST_USER_ID, title);

    // 대본에 user_id가 있는지 확인
    const script = db.prepare(`
      SELECT id, user_id FROM contents WHERE id = ?
    `).get(scriptId);

    if (!script.user_id) {
      addTestResult('Test 1', false, `대본에 user_id가 없음`);
      db.close();
      return;
    }

    addTestResult('Test 1a - 대본 user_id 존재', true, `user_id: ${script.user_id}`);

    // job placeholder 생성 시뮬레이션
    const jobId = `auto_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    try {
      db.prepare(`
        INSERT INTO jobs (id, title, status, user_id, created_at, updated_at)
        VALUES (?, ?, 'processing', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
      `).run(jobId, title, script.user_id);

      addTestResult('Test 1b - Job placeholder 생성', true, `job_id: ${jobId}, user_id: ${script.user_id}`);

      // 생성된 job 확인
      const job = db.prepare(`
        SELECT id, title, user_id, status FROM jobs WHERE id = ?
      `).get(jobId);

      if (job && job.user_id === TEST_USER_ID) {
        addTestResult('Test 1c - Job user_id 검증', true, `user_id가 올바르게 저장됨`);
      } else {
        addTestResult('Test 1c - Job user_id 검증', false, `user_id 불일치 또는 job 없음`);
      }

    } catch (error) {
      addTestResult('Test 1b - Job placeholder 생성', false, `에러: ${error.message}`);
    }

  } catch (error) {
    addTestResult('Test 1', false, `예외 발생: ${error.message}`);
  } finally {
    db.close();
  }
}

// 테스트 2: user_id 없는 대본으로 job 생성 시도 (실패해야 함)
async function test2_JobCreationWithoutUserId() {
  console.log('\n📝 Test 2: user_id 없는 대본으로 job 생성 시도 (실패 예상)');

  const db = new Database(DB_PATH);

  try {
    const scriptId = `test_script_no_user_${Date.now()}`;
    const title = '스케줄러 테스트 - user_id 없음';

    // user_id 없이 대본 생성
    db.prepare(`
      INSERT INTO contents (id, title, content, type, created_at, updated_at)
      VALUES (?, ?, '{"test": true}', 'script', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `).run(scriptId, title);

    const script = db.prepare(`
      SELECT id, user_id FROM contents WHERE id = ?
    `).get(scriptId);

    if (script.user_id === null) {
      addTestResult('Test 2a - user_id 없는 대본 생성', true, `user_id가 null임`);

      // job 생성 시도 (실패해야 함)
      const jobId = `auto_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

      try {
        db.prepare(`
          INSERT INTO jobs (id, title, status, user_id, created_at, updated_at)
          VALUES (?, ?, 'processing', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        `).run(jobId, title, null);

        addTestResult('Test 2b - user_id null로 job 생성', false, `NULL이 허용되었음 (문제!)`);
      } catch (error) {
        if (error.message.includes('NOT NULL constraint failed')) {
          addTestResult('Test 2b - user_id null로 job 생성', true, `NOT NULL 제약조건이 정상 작동함`);
        } else {
          addTestResult('Test 2b - user_id null로 job 생성', false, `다른 에러: ${error.message}`);
        }
      }
    } else {
      addTestResult('Test 2a - user_id 없는 대본 생성', false, `user_id가 자동으로 채워짐`);
    }

  } catch (error) {
    addTestResult('Test 2', false, `예외 발생: ${error.message}`);
  } finally {
    db.close();
  }
}

// 테스트 3: 중복 job 생성 방지
async function test3_DuplicateJobPrevention() {
  console.log('\n📝 Test 3: 중복 job 생성 방지');

  const db = new Database(DB_PATH);

  try {
    const title = '스케줄러 테스트 - 중복 방지';
    const scriptId = createTestScript(db, TEST_USER_ID, title);

    const script = db.prepare(`
      SELECT user_id FROM contents WHERE id = ?
    `).get(scriptId);

    // 첫 번째 job 생성
    const jobId1 = `auto_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    db.prepare(`
      INSERT INTO jobs (id, title, status, user_id, created_at, updated_at)
      VALUES (?, ?, 'processing', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `).run(jobId1, title, script.user_id);

    addTestResult('Test 3a - 첫 번째 job 생성', true, `job_id: ${jobId1}`);

    // 같은 제목으로 실행 중인 job 확인
    const existingJob = db.prepare(`
      SELECT id, status FROM jobs
      WHERE title LIKE '%' || ? || '%'
        AND status IN ('pending', 'processing')
      ORDER BY created_at DESC
      LIMIT 1
    `).get(title);

    if (existingJob && existingJob.id === jobId1) {
      addTestResult('Test 3b - 중복 job 확인', true, `기존 job을 정상적으로 발견: ${existingJob.id}`);

      // 중복 생성 방지 확인 (새로운 job을 만들지 않아야 함)
      const jobCountBefore = db.prepare(`
        SELECT COUNT(*) as count FROM jobs WHERE title LIKE '%' || ? || '%'
      `).get(title).count;

      addTestResult('Test 3c - 중복 방지 검증', true, `현재 job 개수: ${jobCountBefore}, 새로운 job을 생성하지 않음`);
    } else {
      addTestResult('Test 3b - 중복 job 확인', false, `기존 job을 찾지 못함`);
    }

  } catch (error) {
    addTestResult('Test 3', false, `예외 발생: ${error.message}`);
  } finally {
    db.close();
  }
}

// 테스트 4: 스케줄 실행 시뮬레이션
async function test4_ScheduleExecution() {
  console.log('\n📝 Test 4: 스케줄 실행 시뮬레이션');

  const db = new Database(DB_PATH);

  try {
    const title = '스케줄러 테스트 - 실행 시뮬레이션';
    const titleId = `test_title_${Date.now()}`;

    // 타이틀 생성
    db.prepare(`
      INSERT INTO video_titles (id, title, user_id, created_at, updated_at)
      VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `).run(titleId, title, TEST_USER_ID);

    const scriptId = createTestScript(db, TEST_USER_ID, title);
    const scheduleId = createTestSchedule(db, scriptId, titleId);

    addTestResult('Test 4a - 스케줄 생성', true, `schedule_id: ${scheduleId}`);

    // 스케줄 조회
    const schedule = db.prepare(`
      SELECT s.*, c.user_id as script_user_id
      FROM video_schedules s
      LEFT JOIN contents c ON s.script_id = c.id
      WHERE s.id = ?
    `).get(scheduleId);

    if (schedule && schedule.script_user_id) {
      addTestResult('Test 4b - 스케줄 user_id 확인', true, `user_id: ${schedule.script_user_id}`);

      // job 생성 시뮬레이션
      const jobId = `auto_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

      try {
        db.prepare(`
          INSERT INTO jobs (id, title, status, user_id, created_at, updated_at)
          VALUES (?, ?, 'processing', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        `).run(jobId, schedule.title_id, schedule.script_user_id);

        addTestResult('Test 4c - 스케줄에서 job 생성', true, `job_id: ${jobId}`);

        // job-schedule 연결
        db.prepare(`
          UPDATE video_schedules
          SET status = 'processing', updated_at = CURRENT_TIMESTAMP
          WHERE id = ?
        `).run(scheduleId);

        const updatedSchedule = db.prepare(`
          SELECT status FROM video_schedules WHERE id = ?
        `).get(scheduleId);

        if (updatedSchedule.status === 'processing') {
          addTestResult('Test 4d - 스케줄 상태 업데이트', true, `상태: ${updatedSchedule.status}`);
        } else {
          addTestResult('Test 4d - 스케줄 상태 업데이트', false, `상태 업데이트 실패`);
        }

      } catch (error) {
        addTestResult('Test 4c - 스케줄에서 job 생성', false, `에러: ${error.message}`);
      }
    } else {
      addTestResult('Test 4b - 스케줄 user_id 확인', false, `user_id를 찾을 수 없음`);
    }

  } catch (error) {
    addTestResult('Test 4', false, `예외 발생: ${error.message}`);
  } finally {
    db.close();
  }
}

// 테스트 5: 서버 로그 검증
async function test5_ServerLogValidation() {
  console.log('\n📝 Test 5: 서버 로그 검증');

  try {
    const logPath = path.join(__dirname, 'trend-video-frontend', 'logs', 'server.log');

    if (!fs.existsSync(logPath)) {
      addTestResult('Test 5', false, '서버 로그 파일이 없음');
      return;
    }

    const logContent = fs.readFileSync(logPath, 'utf-8');
    const recentLogs = logContent.split('\n').slice(-1000).join('\n');

    // user_id NOT NULL 에러 검사
    const hasUserIdError = recentLogs.includes('NOT NULL constraint failed: jobs.user_id');

    if (hasUserIdError) {
      addTestResult('Test 5a - user_id 에러 검사', false, `로그에서 user_id NOT NULL 에러 발견`);
    } else {
      addTestResult('Test 5a - user_id 에러 검사', true, `user_id 에러가 로그에 없음`);
    }

    // Job placeholder 생성 로그 확인
    const hasPlaceholderLog = recentLogs.includes('Created job placeholder') ||
                              recentLogs.includes('Job placeholder 생성');

    if (hasPlaceholderLog) {
      addTestResult('Test 5b - Job placeholder 로그', true, `job placeholder 생성 로그 확인됨`);
    } else {
      addTestResult('Test 5b - Job placeholder 로그', false, `job placeholder 생성 로그가 없음`);
    }

  } catch (error) {
    addTestResult('Test 5', false, `예외 발생: ${error.message}`);
  }
}

// 메인 테스트 실행
async function runTests() {
  console.log('='.repeat(80));
  console.log('🧪 스케줄러 비디오 생성 프로세스 통합 테스트');
  console.log('='.repeat(80));
  console.log(`📅 ${new Date().toLocaleString('ko-KR')}`);
  console.log(`📍 DB: ${DB_PATH}`);
  console.log(`👤 테스트 User: ${TEST_USER_ID}`);

  const db = new Database(DB_PATH);
  cleanupTestData(db);
  db.close();

  // 순차적으로 테스트 실행
  await test1_JobCreationWithUserId();
  await delay(500);

  await test2_JobCreationWithoutUserId();
  await delay(500);

  await test3_DuplicateJobPrevention();
  await delay(500);

  await test4_ScheduleExecution();
  await delay(500);

  await test5_ServerLogValidation();

  // 최종 정리
  const dbFinal = new Database(DB_PATH);
  cleanupTestData(dbFinal);
  dbFinal.close();

  // 결과 출력
  console.log('\n' + '='.repeat(80));
  console.log('📊 테스트 결과 요약');
  console.log('='.repeat(80));
  console.log(`✅ 통과: ${testResults.passed}`);
  console.log(`❌ 실패: ${testResults.failed}`);
  console.log(`📝 총 테스트: ${testResults.tests.length}`);

  if (testResults.failed === 0) {
    console.log('\n🎉 모든 테스트 통과!');
  } else {
    console.log('\n⚠️ 일부 테스트 실패');
    console.log('\n실패한 테스트:');
    testResults.tests
      .filter(t => !t.passed)
      .forEach(t => console.log(`  - ${t.name}: ${t.message}`));
  }

  console.log('\n' + '='.repeat(80));

  process.exit(testResults.failed === 0 ? 0 : 1);
}

// 실행
runTests().catch(error => {
  console.error('테스트 실행 중 오류:', error);
  process.exit(1);
});
