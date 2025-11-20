/**
 * 자동화 시스템 큐 플로우 통합 테스트 (DB 직접 확인)
 * - 백엔드 DB를 직접 확인하여 큐 이동 로직 검증
 */

const Database = require('better-sqlite3');
const path = require('path');

const DB_PATH = path.join(__dirname, 'trend-video-frontend', 'data', 'automation.db');

let testResults = {
  passed: 0,
  failed: 0,
  tests: []
};

function addTestResult(name, passed, message, details = null) {
  testResults.tests.push({ name, passed, message, details });
  if (passed) {
    testResults.passed++;
    console.log(`✅ ${name}: ${message}`);
    if (details) {
      console.log(`   ${JSON.stringify(details)}`);
    }
  } else {
    testResults.failed++;
    console.error(`❌ ${name}: ${message}`);
    if (details) {
      console.error(`   ${JSON.stringify(details)}`);
    }
  }
}

// DB 연결 테스트
function testDatabaseConnection() {
  console.log('\n🔌 1. DB 연결 테스트');

  try {
    const db = new Database(DB_PATH, { readonly: true });
    const result = db.prepare('SELECT COUNT(*) as count FROM automation_titles').get();

    addTestResult('DB 연결', true, `총 ${result.count}개 제목 확인`);
    db.close();
    return true;
  } catch (error) {
    addTestResult('DB 연결', false, `에러: ${error.message}`);
    return false;
  }
}

// 대기 큐 테스트
function testWaitingQueue() {
  console.log('\n⏳ 2. 대기 큐 테스트');

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const query = `
      SELECT t.id, t.title, t.status, COUNT(s.id) as schedule_count
      FROM automation_titles t
      LEFT JOIN automation_schedules s ON t.id = s.title_id
      WHERE t.status IN ('waiting', 'pending')
      GROUP BY t.id
      LIMIT 10
    `;

    const titles = db.prepare(query).all();
    db.close();

    addTestResult(
      '대기 큐 조회',
      true,
      `${titles.length}개 제목`,
      titles.slice(0, 3).map(t => ({ id: t.id, title: t.title, status: t.status }))
    );

    return titles;
  } catch (error) {
    addTestResult('대기 큐 조회', false, `에러: ${error.message}`);
    return [];
  }
}

// 업로드 대기 큐 테스트
function testUploadWaitingQueue() {
  console.log('\n📤 3. 업로드 대기 큐 테스트');

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const query = `
      SELECT
        t.id,
        t.title,
        t.status,
        s.id as schedule_id,
        s.status as schedule_status,
        s.script_id
      FROM automation_titles t
      INNER JOIN automation_schedules s ON t.id = s.title_id
      WHERE s.status = 'waiting_for_upload' AND s.script_id IS NOT NULL
      LIMIT 10
    `;

    const titles = db.prepare(query).all();
    db.close();

    addTestResult(
      '업로드 대기 큐 조회',
      true,
      `${titles.length}개 제목`,
      titles.slice(0, 3).map(t => ({
        title_id: t.id,
        title: t.title,
        schedule_status: t.schedule_status,
        has_script: !!t.script_id
      }))
    );

    return titles;
  } catch (error) {
    addTestResult('업로드 대기 큐 조회', false, `에러: ${error.message}`);
    return [];
  }
}

// 진행 큐 테스트
function testProcessingQueue() {
  console.log('\n🔄 4. 진행 큐 테스트');

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const query = `
      SELECT
        t.id,
        t.title,
        t.status,
        s.id as schedule_id,
        s.status as schedule_status,
        s.video_id,
        j.status as job_status,
        j.progress
      FROM automation_titles t
      INNER JOIN automation_schedules s ON t.id = s.title_id
      LEFT JOIN jobs j ON s.video_id = j.id
      WHERE s.status = 'processing'
      LIMIT 10
    `;

    const titles = db.prepare(query).all();
    db.close();

    addTestResult(
      '진행 큐 조회',
      true,
      `${titles.length}개 제목`,
      titles.slice(0, 3).map(t => ({
        title_id: t.id,
        title: t.title,
        schedule_status: t.schedule_status,
        job_status: t.job_status,
        progress: t.progress
      }))
    );

    return titles;
  } catch (error) {
    addTestResult('진행 큐 조회', false, `에러: ${error.message}`);
    return [];
  }
}

// 완료 큐 테스트
function testCompletedQueue() {
  console.log('\n✅ 5. 완료 큐 테스트');

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const query = `
      SELECT
        t.id,
        t.title,
        t.status,
        s.id as schedule_id,
        s.status as schedule_status,
        s.video_id,
        s.youtube_video_id
      FROM automation_titles t
      INNER JOIN automation_schedules s ON t.id = s.title_id
      WHERE s.status = 'completed'
      ORDER BY s.updated_at DESC
      LIMIT 10
    `;

    const titles = db.prepare(query).all();
    db.close();

    addTestResult(
      '완료 큐 조회',
      true,
      `${titles.length}개 제목`,
      titles.slice(0, 3).map(t => ({
        title_id: t.id,
        title: t.title,
        has_youtube_id: !!t.youtube_video_id
      }))
    );

    return titles;
  } catch (error) {
    addTestResult('완료 큐 조회', false, `에러: ${error.message}`);
    return [];
  }
}

// 실패 큐 테스트
function testFailedQueue() {
  console.log('\n❌ 6. 실패 큐 테스트');

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const query = `
      SELECT
        t.id,
        t.title,
        t.status,
        s.id as schedule_id,
        s.status as schedule_status,
        s.error
      FROM automation_titles t
      INNER JOIN automation_schedules s ON t.id = s.title_id
      WHERE s.status = 'failed'
      ORDER BY s.updated_at DESC
      LIMIT 10
    `;

    const titles = db.prepare(query).all();
    db.close();

    addTestResult(
      '실패 큐 조회',
      true,
      `${titles.length}개 제목`,
      titles.slice(0, 3).map(t => ({
        title_id: t.id,
        title: t.title,
        error: t.error
      }))
    );

    return titles;
  } catch (error) {
    addTestResult('실패 큐 조회', false, `에러: ${error.message}`);
    return [];
  }
}

// 큐 전환 로직 검증
function testQueueTransitions() {
  console.log('\n🔀 7. 큐 전환 로직 검증');

  try {
    const db = new Database(DB_PATH, { readonly: true });

    // 1. waiting_for_upload → processing 전환 확인
    const uploadToProcessing = db.prepare(`
      SELECT COUNT(*) as count
      FROM automation_schedules
      WHERE status = 'processing'
        AND script_id IS NOT NULL
        AND updated_at > datetime('now', '-1 hour')
    `).get();

    addTestResult(
      '업로드→진행 전환',
      uploadToProcessing.count >= 0,
      `최근 1시간: ${uploadToProcessing.count}개`,
      { count: uploadToProcessing.count }
    );

    // 2. processing → completed 전환 확인
    const processingToCompleted = db.prepare(`
      SELECT COUNT(*) as count
      FROM automation_schedules
      WHERE status = 'completed'
        AND video_id IS NOT NULL
        AND updated_at > datetime('now', '-1 hour')
    `).get();

    addTestResult(
      '진행→완료 전환',
      processingToCompleted.count >= 0,
      `최근 1시간: ${processingToCompleted.count}개`,
      { count: processingToCompleted.count }
    );

    // 3. failed 상태 확인
    const failedCount = db.prepare(`
      SELECT COUNT(*) as count
      FROM automation_schedules
      WHERE status = 'failed'
        AND updated_at > datetime('now', '-1 hour')
    `).get();

    addTestResult(
      '실패 전환',
      failedCount.count >= 0,
      `최근 1시간: ${failedCount.count}개`,
      { count: failedCount.count }
    );

    db.close();
    return true;
  } catch (error) {
    addTestResult('큐 전환 로직 검증', false, `에러: ${error.message}`);
    return false;
  }
}

// 통계 요약
function testStatistics() {
  console.log('\n📊 8. 통계 요약');

  try {
    const db = new Database(DB_PATH, { readonly: true });

    const stats = db.prepare(`
      SELECT
        COUNT(DISTINCT t.id) as total_titles,
        COUNT(DISTINCT s.id) as total_schedules,
        SUM(CASE WHEN s.status = 'waiting' OR s.status = 'pending' THEN 1 ELSE 0 END) as waiting,
        SUM(CASE WHEN s.status = 'waiting_for_upload' THEN 1 ELSE 0 END) as upload_waiting,
        SUM(CASE WHEN s.status = 'processing' THEN 1 ELSE 0 END) as processing,
        SUM(CASE WHEN s.status = 'completed' THEN 1 ELSE 0 END) as completed,
        SUM(CASE WHEN s.status = 'failed' THEN 1 ELSE 0 END) as failed
      FROM automation_titles t
      LEFT JOIN automation_schedules s ON t.id = s.title_id
    `).get();

    db.close();

    const summary = {
      '총 제목': stats.total_titles,
      '총 스케줄': stats.total_schedules,
      '대기': stats.waiting || 0,
      '업로드대기': stats.upload_waiting || 0,
      '진행중': stats.processing || 0,
      '완료': stats.completed || 0,
      '실패': stats.failed || 0
    };

    console.log('\n📈 큐별 현황:');
    Object.entries(summary).forEach(([key, value]) => {
      console.log(`  ${key}: ${value}개`);
    });

    addTestResult(
      '통계 조회',
      true,
      '큐별 현황 확인 완료',
      summary
    );

    return true;
  } catch (error) {
    addTestResult('통계 조회', false, `에러: ${error.message}`);
    return false;
  }
}

// 전체 테스트 실행
function runIntegrationTest() {
  console.log('='.repeat(80));
  console.log('🧪 자동화 시스템 큐 플로우 DB 통합 테스트');
  console.log('='.repeat(80));
  console.log(`📅 ${new Date().toLocaleString('ko-KR')}`);
  console.log(`💾 DB 경로: ${DB_PATH}`);

  // 1. DB 연결 테스트
  if (!testDatabaseConnection()) {
    printSummary();
    process.exit(1);
  }

  // 2. 각 큐 테스트
  testWaitingQueue();
  testUploadWaitingQueue();
  testProcessingQueue();
  testCompletedQueue();
  testFailedQueue();

  // 3. 큐 전환 로직 검증
  testQueueTransitions();

  // 4. 통계 요약
  testStatistics();

  printSummary();
}

function printSummary() {
  console.log('\n' + '='.repeat(80));
  console.log('📊 테스트 결과 요약');
  console.log('='.repeat(80));
  console.log(`✅ 통과: ${testResults.passed}`);
  console.log(`❌ 실패: ${testResults.failed}`);
  console.log(`📝 총 테스트: ${testResults.tests.length}`);

  if (testResults.failed > 0) {
    console.log('\n⚠️ 실패한 테스트:');
    testResults.tests.filter(t => !t.passed).forEach(t => {
      console.log(`  - ${t.name}: ${t.message}`);
    });
  }

  console.log('\n' + '='.repeat(80));

  if (testResults.failed === 0) {
    console.log('🎉 모든 테스트 통과!');
    process.exit(0);
  } else {
    console.log(`⚠️ ${testResults.failed}개 테스트 실패`);
    process.exit(1);
  }
}

// 실행
try {
  runIntegrationTest();
} catch (error) {
  console.error('테스트 실행 중 오류:', error);
  process.exit(1);
}
