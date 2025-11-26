/**
 * 🧪 자동화 폴더 버튼 통합 테스트
 *
 * 테스트 대상:
 * 1. 진행 큐와 실행 큐의 폴더 버튼 기능
 * 2. handleOpenFolder 함수의 파라미터 전달
 * 3. open-folder API의 jobId 처리
 * 4. 모든 상태(processing, waiting_for_upload, failed, completed)에서의 폴더 열기
 */

const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const TEST_RESULTS = {
  passed: 0,
  failed: 0,
  tests: [],
  details: []
};

function addTestResult(name, passed, message, details = '') {
  TEST_RESULTS.tests.push({ name, passed, message, details });
  if (passed) {
    TEST_RESULTS.passed++;
    console.log(`✅ ${name}: ${message}`);
  } else {
    TEST_RESULTS.failed++;
    console.error(`❌ ${name}: ${message}`);
  }
  if (details) {
    TEST_RESULTS.details.push(`\n[${name}] ${details}`);
  }
}

function log(message, level = 'log') {
  const timestamp = new Date().toISOString().split('T')[1].slice(0, 8);
  const levelEmoji = {
    log: '📋',
    info: 'ℹ️',
    warn: '⚠️',
    error: '❌',
    success: '✅'
  }[level] || '📋';
  console.log(`[${timestamp}] ${levelEmoji} ${message}`);
}

// ===== 테스트 1: 자동화 페이지 폴더 버튼 코드 확인 =====
function testAutomationPageFolderButton() {
  log('테스트 1: 자동화 페이지 폴더 버튼 코드 확인', 'info');

  try {
    const pageContent = fs.readFileSync(
      path.join(__dirname, 'trend-video-frontend/src/app/automation/page.tsx'),
      'utf-8'
    );

    // 1-1. handleOpenFolder 함수 확인
    const hasHandleOpenFolder = pageContent.includes('async function handleOpenFolder');
    addTestResult(
      '1-1. handleOpenFolder 함수 정의',
      hasHandleOpenFolder,
      hasHandleOpenFolder ? '함수 정의됨' : '함수 미정의'
    );

    // 1-2. handleOpenFolder 호출 확인
    const folderButtonCall = pageContent.match(/handleOpenFolder\(([^)]+)\)/);
    addTestResult(
      '1-2. handleOpenFolder 호출',
      folderButtonCall !== null,
      folderButtonCall ? `호출됨: ${folderButtonCall[1]}` : '호출 없음'
    );

    // 1-3. 폴더 버튼의 조건 확인
    const folderButtonCondition = pageContent.includes('schedule.video_id || null, schedule.script_id || null');
    addTestResult(
      '1-3. 폴더 버튼 파라미터',
      folderButtonCondition,
      folderButtonCondition ? 'video_id와 script_id 전달' : '파라미터 오류'
    );

    // 1-4. 폴더 버튼 표시 조건 확인
    const folderButtonDisplay = pageContent.includes("title.status === 'processing' || title.status === 'waiting_for_upload'");
    addTestResult(
      '1-4. 폴더 버튼 표시 조건',
      folderButtonDisplay,
      folderButtonDisplay ? '조건식 정의됨' : '조건식 누락'
    );

  } catch (error) {
    addTestResult(
      '1. 자동화 페이지 코드 확인',
      false,
      `파일 읽기 오류: ${error.message}`
    );
  }
}

// ===== 테스트 2: open-folder API 확인 =====
function testOpenFolderAPI() {
  log('테스트 2: open-folder API 확인', 'info');

  try {
    const apiContent = fs.readFileSync(
      path.join(__dirname, 'trend-video-frontend/src/app/api/open-folder/route.ts'),
      'utf-8'
    );

    // 2-1. jobId 파라미터 처리 확인
    const hasJobIdParam = apiContent.includes('const jobId = searchParams.get(\'jobId\')');
    addTestResult(
      '2-1. jobId 파라미터 처리',
      hasJobIdParam,
      hasJobIdParam ? 'jobId 파라미터 처리함' : '파라미터 미처리'
    );

    // 2-2. jobId로 폴더 경로 추정 로직 확인
    const hasUploadedPrefix = apiContent.includes('uploaded_');
    addTestResult(
      '2-2. uploaded_ 접두사 사용',
      hasUploadedPrefix,
      hasUploadedPrefix ? '사용함' : '미사용'
    );

    // 2-3. uploads, input, output 폴더 처리 확인
    const hasMultipleFolders = apiContent.includes('uploads') && apiContent.includes('input') && apiContent.includes('output');
    addTestResult(
      '2-3. 다중 폴더 경로 지원',
      hasMultipleFolders,
      hasMultipleFolders ? 'uploads/input/output 모두 지원' : '지원 부분적'
    );

    // 2-4. 직접 경로(path) 파라미터 처리 확인
    const hasDirectPath = apiContent.includes('const directPath = searchParams.get(\'path\')');
    addTestResult(
      '2-4. 직접 경로(path) 파라미터',
      hasDirectPath,
      hasDirectPath ? 'path 파라미터 지원' : '미지원'
    );

    // 2-5. 에러 처리 확인
    const hasErrorHandling = apiContent.includes('폴더가 존재하지 않습니다');
    addTestResult(
      '2-5. 폴더 미존재 에러 처리',
      hasErrorHandling,
      hasErrorHandling ? '404 에러 반환' : '에러 처리 미흡'
    );

  } catch (error) {
    addTestResult(
      '2. open-folder API 코드 확인',
      false,
      `파일 읽기 오류: ${error.message}`
    );
  }
}

// ===== 테스트 3: 데이터베이스 스키마 확인 =====
function testDatabaseSchema() {
  log('테스트 3: 데이터베이스 스키마 확인', 'info');

  try {
    const dbPath = path.join(__dirname, 'trend-video-frontend/data/database.sqlite');

    if (!fs.existsSync(dbPath)) {
      addTestResult(
        '3-1. 데이터베이스 파일 존재',
        false,
        `DB 파일 없음: ${dbPath}`
      );
      return;
    }

    const db = new Database(dbPath, { readonly: true });

    // 3-1. video_schedules 테이블 확인
    try {
      const schedules = db.prepare('SELECT * FROM video_schedules LIMIT 1').all();
      addTestResult(
        '3-1. video_schedules 테이블',
        true,
        'video_schedules 테이블 존재'
      );

      // 3-2. video_id 컬럼 확인
      const tableInfo = db.prepare('PRAGMA table_info(video_schedules)').all();
      const hasVideoId = tableInfo.some(col => col.name === 'video_id');
      addTestResult(
        '3-2. video_id 컬럼',
        hasVideoId,
        hasVideoId ? 'video_id 컬럼 존재' : 'video_id 컬럼 없음'
      );

      // 3-3. script_id 컬럼 확인
      const hasScriptId = tableInfo.some(col => col.name === 'script_id');
      addTestResult(
        '3-3. script_id 컬럼',
        hasScriptId,
        hasScriptId ? 'script_id 컬럼 존재' : 'script_id 컬럼 없음'
      );

      // 3-4. 실제 데이터 확인
      const scheduleData = db.prepare(`
        SELECT id, title_id, video_id, script_id, status
        FROM video_schedules
        WHERE (video_id IS NOT NULL OR script_id IS NOT NULL)
        LIMIT 5
      `).all();

      addTestResult(
        '3-4. video_id/script_id 데이터',
        scheduleData.length > 0,
        scheduleData.length > 0
          ? `${scheduleData.length}개 스케줄 확인`
          : '데이터 없음'
      );

      if (scheduleData.length > 0) {
        const sampleData = scheduleData[0];
        const details = `샘플: id=${sampleData.id}, video_id=${sampleData.video_id}, script_id=${sampleData.script_id}`;
        TEST_RESULTS.details.push(`\n[3-4. 데이터 샘플] ${details}`);
      }

    } catch (tableError) {
      addTestResult(
        '3-1. video_schedules 테이블',
        false,
        `테이블 오류: ${tableError.message}`
      );
    }

    db.close();

  } catch (error) {
    addTestResult(
      '3. 데이터베이스 확인',
      false,
      `오류: ${error.message}`
    );
  }
}

// ===== 테스트 4: 실제 폴더 구조 확인 =====
function testBackendFolderStructure() {
  log('테스트 4: 백엔드 폴더 구조 확인', 'info');

  try {
    const backendPath = path.join(__dirname, 'trend-video-backend');

    // 4-1. backend 폴더 존재 확인
    const backendExists = fs.existsSync(backendPath);
    addTestResult(
      '4-1. trend-video-backend 폴더',
      backendExists,
      backendExists ? 'backend 폴더 존재' : 'backend 폴더 미존재'
    );

    if (!backendExists) return;

    // 4-2. uploads 폴더 확인
    const uploadsPath = path.join(backendPath, 'uploads');
    const uploadsExists = fs.existsSync(uploadsPath);
    addTestResult(
      '4-2. uploads 폴더',
      uploadsExists,
      uploadsExists ? 'uploads 폴더 존재' : 'uploads 폴더 미존재'
    );

    // 4-3. input 폴더 확인
    const inputPath = path.join(backendPath, 'input');
    const inputExists = fs.existsSync(inputPath);
    addTestResult(
      '4-3. input 폴더',
      inputExists,
      inputExists ? 'input 폴더 존재' : 'input 폴더 미존재'
    );

    // 4-4. output 폴더 확인
    const outputPath = path.join(backendPath, 'output');
    const outputExists = fs.existsSync(outputPath);
    addTestResult(
      '4-4. output 폴더',
      outputExists,
      outputExists ? 'output 폴더 존재' : 'output 폴더 미존재'
    );

    // 4-5. uploads 폴더의 프로젝트 폴더 확인
    if (uploadsExists) {
      const uploadedFolders = fs.readdirSync(uploadsPath).filter(f => {
        const fullPath = path.join(uploadsPath, f);
        return fs.statSync(fullPath).isDirectory();
      });
      addTestResult(
        '4-5. uploads 내 프로젝트 폴더',
        uploadedFolders.length > 0,
        uploadedFolders.length > 0 ? `${uploadedFolders.length}개 폴더 발견` : '프로젝트 폴더 없음'
      );

      if (uploadedFolders.length > 0) {
        TEST_RESULTS.details.push(`\n[4-5. uploads 폴더 목록]\n${uploadedFolders.slice(0, 5).join(', ')}...`);
      }
    }

  } catch (error) {
    addTestResult(
      '4. 백엔드 폴더 구조 확인',
      false,
      `오류: ${error.message}`
    );
  }
}

// ===== 테스트 5: 자동화 페이지 상태별 폴더 버튼 위치 확인 =====
function testFolderButtonLocations() {
  log('테스트 5: 자동화 페이지 폴더 버튼 위치 확인', 'info');

  try {
    const pageContent = fs.readFileSync(
      path.join(__dirname, 'trend-video-frontend/src/app/automation/page.tsx'),
      'utf-8'
    );

    // 5-1. processing 상태에서 표시
    const processingCheck = pageContent.includes("title.status === 'processing'");
    addTestResult(
      '5-1. processing 상태',
      processingCheck,
      processingCheck ? 'processing 상태에서 표시' : '상태 조건 미흡'
    );

    // 5-2. waiting_for_upload 상태에서 표시
    const waitingCheck = pageContent.includes("title.status === 'waiting_for_upload'");
    addTestResult(
      '5-2. waiting_for_upload 상태',
      waitingCheck,
      waitingCheck ? 'waiting_for_upload 상태에서 표시' : '상태 조건 미흡'
    );

    // 5-3. failed 상태에서 표시
    const failedCheck = pageContent.includes("title.status === 'failed'");
    addTestResult(
      '5-3. failed 상태',
      failedCheck,
      failedCheck ? 'failed 상태에서 표시' : '상태 조건 미흡'
    );

    // 5-4. completed 상태에서 표시
    const completedCheck = pageContent.includes("title.status === 'completed'");
    addTestResult(
      '5-4. completed 상태',
      completedCheck,
      completedCheck ? 'completed 상태에서 표시' : '상태 조건 미흡'
    );

  } catch (error) {
    addTestResult(
      '5. 폴더 버튼 위치 확인',
      false,
      `파일 읽기 오류: ${error.message}`
    );
  }
}

// ===== 테스트 6: 로그 분석 (실제 에러 원인 파악) =====
function testServerLogs() {
  log('테스트 6: 서버 로그 분석', 'info');

  try {
    const logPath = path.join(__dirname, 'trend-video-frontend/logs/server.log');

    if (!fs.existsSync(logPath)) {
      addTestResult(
        '6-1. 서버 로그 파일',
        false,
        '서버 로그 파일 없음'
      );
      return;
    }

    const logContent = fs.readFileSync(logPath, 'utf-8');
    const recentLogs = logContent.split('\n').slice(-100).join('\n');

    // 6-1. 폴더 열기 API 호출 확인
    const hasFolderAPI = recentLogs.includes('📁 폴더 열기 API');
    addTestResult(
      '6-1. 폴더 열기 API 호출',
      hasFolderAPI,
      hasFolderAPI ? 'API 호출 로그 확인' : 'API 호출 로그 없음'
    );

    // 6-2. 404 에러 확인
    const has404Error = recentLogs.includes('404') || logContent.includes('폴더가 존재하지 않습니다');
    addTestResult(
      '6-2. 404 에러 발생',
      has404Error,
      has404Error ? '404 에러 발견' : '404 에러 없음'
    );

    // 6-3. jobId 관련 로그
    const jobIdLogs = recentLogs.match(/auto_\d+_[a-z0-9]+/g);
    addTestResult(
      '6-3. jobId 로그',
      jobIdLogs && jobIdLogs.length > 0,
      jobIdLogs && jobIdLogs.length > 0 ? `${jobIdLogs.length}개 jobId 발견` : 'jobId 로그 없음'
    );

    // 6-4. 폴더 경로 추정 로그
    const pathLogs = recentLogs.match(/폴더.*경로|📁.*경로|📂.*경로/g);
    addTestResult(
      '6-4. 폴더 경로 로그',
      pathLogs && pathLogs.length > 0,
      pathLogs && pathLogs.length > 0 ? `${pathLogs.length}개 경로 로그 발견` : '경로 로그 없음'
    );

    // 6-5. uploads 폴더 관련 로그
    const uploadsLogs = recentLogs.includes('uploads');
    addTestResult(
      '6-5. uploads 폴더 관련 로그',
      uploadsLogs,
      uploadsLogs ? 'uploads 관련 로그 발견' : 'uploads 로그 없음'
    );

  } catch (error) {
    addTestResult(
      '6. 서버 로그 분석',
      false,
      `오류: ${error.message}`
    );
  }
}

// ===== 실행 =====
async function runAllTests() {
  log('🧪 자동화 폴더 버튼 통합테스트 시작', 'success');
  console.log('\n');

  testAutomationPageFolderButton();
  console.log('\n');

  testOpenFolderAPI();
  console.log('\n');

  testDatabaseSchema();
  console.log('\n');

  testBackendFolderStructure();
  console.log('\n');

  testFolderButtonLocations();
  console.log('\n');

  testServerLogs();
  console.log('\n');

  // 결과 출력
  console.log('═'.repeat(60));
  console.log('📊 테스트 결과 요약');
  console.log('═'.repeat(60));
  console.log(`\n✅ 통과: ${TEST_RESULTS.passed}/${TEST_RESULTS.tests.length}`);
  console.log(`❌ 실패: ${TEST_RESULTS.failed}/${TEST_RESULTS.tests.length}`);

  if (TEST_RESULTS.details.length > 0) {
    console.log('\n' + '═'.repeat(60));
    console.log('📝 상세 정보');
    console.log('═'.repeat(60));
    TEST_RESULTS.details.forEach(detail => console.log(detail));
  }

  // 실패한 테스트 정리
  if (TEST_RESULTS.failed > 0) {
    console.log('\n' + '═'.repeat(60));
    console.log('❌ 실패 테스트');
    console.log('═'.repeat(60));
    TEST_RESULTS.tests.filter(t => !t.passed).forEach(test => {
      console.log(`\n  ${test.name}`);
      console.log(`  → ${test.message}`);
    });
  }

  console.log('\n' + '═'.repeat(60));
  process.exit(TEST_RESULTS.failed === 0 ? 0 : 1);
}

runAllTests().catch(error => {
  console.error('테스트 실행 중 오류:', error);
  process.exit(1);
});
