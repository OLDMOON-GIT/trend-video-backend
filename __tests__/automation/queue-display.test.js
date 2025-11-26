const fs = require('fs');
const path = require('path');

let testResults = { passed: 0, failed: 0, tests: [] };

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

async function runTests() {
  console.log('🧪 [자동화 큐 상태 표시 테스트] 시작\n');

  // 테스트 1: API 코드 변경 확인 - /api/my-videos
  const myVideosPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'my-videos', 'route.ts');
  const myVideosContent = fs.readFileSync(myVideosPath, 'utf-8');

  const hasAutomationDbImport = myVideosContent.includes('import Database') && myVideosContent.includes('better-sqlite3');
  addTestResult('API: Database import', hasAutomationDbImport, 'better-sqlite3 import 확인');

  const hasAutomationQuery = myVideosContent.includes('video_schedules');
  addTestResult('API: 자동화 큐 조회', hasAutomationQuery, 'video_schedules 테이블 조회');

  const hasQueueMapping = myVideosContent.includes('automationQueue: queueStatusMap');
  addTestResult('API: 큐 정보 매핑', hasQueueMapping, '영상에 큐 정보 추가');

  // 테스트 2: UI 코드 변경 확인 - my-content/page.tsx
  const myContentPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'my-content', 'page.tsx');
  const myContentContent = fs.readFileSync(myContentPath, 'utf-8');

  const hasJobInterface = myContentContent.includes('interface Job') &&
                          myContentContent.includes('automationQueue?:');
  addTestResult('UI: Job 인터페이스', hasJobInterface, 'automationQueue 필드 추가');

  const hasVideoBadge = myContentContent.match(/item\.data as Job.*automationQueue.*inQueue/);
  addTestResult('UI: 영상 큐 배지', !!hasVideoBadge, '영상 카드에 자동화 큐 배지 표시');

  const hasScriptBadge = myContentContent.match(/item\.data as Script.*automationQueue.*inQueue/);
  addTestResult('UI: 대본 큐 배지', !!hasScriptBadge, '대본 카드에 자동화 큐 배지 표시');

  // 테스트 3: 배지 상태 매핑 확인
  const statusMappings = [
    { status: 'pending', label: '⏳ 큐 대기', color: 'bg-yellow-500' },
    { status: 'processing', label: '⚙️ 자동화 중', color: 'bg-blue-500' },
    { status: 'waiting_for_upload', label: '📤 업로드 대기', color: 'bg-purple-500' },
    { status: 'cancelled', label: '❌ 큐 취소됨', color: 'bg-gray-500' }
  ];

  let allStatusesFound = true;
  for (const mapping of statusMappings) {
    if (!myContentContent.includes(mapping.label) || !myContentContent.includes(mapping.color)) {
      allStatusesFound = false;
      break;
    }
  }
  addTestResult('UI: 상태 매핑', allStatusesFound, '모든 큐 상태 배지 매핑 확인');

  // 테스트 4: 서버 로그 확인
  const logPath = path.join(__dirname, 'trend-video-frontend', 'logs', 'server.log');
  if (fs.existsSync(logPath)) {
    const logContent = fs.readFileSync(logPath, 'utf-8');
    const recentLogs = logContent.split('\n').slice(-100).join('\n');

    const hasError = recentLogs.includes('❌ Error') || recentLogs.includes('ERROR');
    addTestResult('서버 로그', !hasError, hasError ? '최근 에러 발견' : '정상');
  } else {
    addTestResult('서버 로그', true, '로그 파일 없음 (정상)');
  }

  // 결과 출력
  console.log(`\n${'='.repeat(50)}`);
  console.log(`테스트 결과: ${testResults.passed}/${testResults.tests.length} 통과`);
  console.log(`${'='.repeat(50)}\n`);

  if (testResults.failed > 0) {
    console.log('❌ 실패한 테스트:');
    testResults.tests
      .filter(t => !t.passed)
      .forEach(t => console.log(`  - ${t.name}: ${t.message}`));
    console.log('');
  }

  // 사용법 안내
  console.log('📋 자동화 큐 상태 표시 안내:\n');
  console.log('1. 내콘텐츠 페이지에서 대본/영상 카드를 확인하세요');
  console.log('2. 자동화에 등록된 콘텐츠에는 다음 배지가 표시됩니다:');
  console.log('   - ⏳ 큐 대기 (노란색): 자동화 예약됨');
  console.log('   - ⚙️ 자동화 중 (파란색): 현재 자동화 진행 중');
  console.log('   - 📤 업로드 대기 (보라색): 영상 생성 완료, YouTube 업로드 대기');
  console.log('   - ❌ 큐 취소됨 (회색): 자동화가 취소됨');
  console.log('   - ✅ 자동화 완료 (초록색): 모든 자동화 완료\n');

  process.exit(testResults.failed === 0 ? 0 : 1);
}

runTests();
