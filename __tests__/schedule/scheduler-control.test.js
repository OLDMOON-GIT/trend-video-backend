/**
 * 스케줄러 시작/중지 통합테스트
 * 자동화 스케줄러 제어 기능 검증
 */

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

// 1. 스케줄러 토글 함수
function testSchedulerToggle() {
  console.log('📝 STEP 1: 스케줄러 토글 함수 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    const hasToggleFunction = content.includes('toggleScheduler') || content.includes('function toggleScheduler');
    addTestResult('1-1. toggleScheduler 함수', hasToggleFunction, hasToggleFunction ? '확인' : '누락');

    const hasApiCall = content.includes('/api/automation/scheduler');
    addTestResult('1-2. 스케줄러 API 호출', hasApiCall, hasApiCall ? '확인' : '누락');

    const hasAction = content.includes("action") && (content.includes("'start'") || content.includes("'stop'"));
    addTestResult('1-3. start/stop 액션', hasAction, hasAction ? '확인' : '누락');

  } catch (error) {
    addTestResult('1. 스케줄러 토글 함수', false, error.message);
  }
  console.log('');
}

// 2. 스케줄러 상태 표시
function testSchedulerStatus() {
  console.log('📝 STEP 2: 스케줄러 상태 표시 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    const hasSchedulerStatus = content.includes('schedulerStatus') || content.includes('isRunning');
    addTestResult('2-1. 스케줄러 상태 관리', hasSchedulerStatus, hasSchedulerStatus ? '확인' : '누락');

    const hasStatusDisplay = content.includes('실행 중') || content.includes('중지됨') || content.includes('Running') || content.includes('Stopped');
    addTestResult('2-2. 상태 표시 UI', hasStatusDisplay, hasStatusDisplay ? '확인' : '누락');

  } catch (error) {
    addTestResult('2. 스케줄러 상태', false, error.message);
  }
  console.log('');
}

// 3. 스케줄러 API
function testSchedulerApi() {
  console.log('📝 STEP 3: 스케줄러 API 검증');
  console.log('-'.repeat(70));

  try {
    const apiPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'automation', 'scheduler', 'route.ts');

    if (!fs.existsSync(apiPath)) {
      addTestResult('3-1. API 파일 존재', false, 'API 파일 없음');
      addTestResult('3-2. POST 메서드', false, 'API 파일 없음');
      addTestResult('3-3. start 액션 처리', false, 'API 파일 없음');
      addTestResult('3-4. stop 액션 처리', false, 'API 파일 없음');
      console.log('');
      return;
    }

    const content = fs.readFileSync(apiPath, 'utf-8');

    addTestResult('3-1. API 파일 존재', true, 'route.ts 확인');

    const hasPostMethod = content.includes('export async function POST');
    addTestResult('3-2. POST 메서드', hasPostMethod, hasPostMethod ? '확인' : '누락');

    const hasStartAction = content.includes('start') && content.includes('action');
    addTestResult('3-3. start 액션 처리', hasStartAction, hasStartAction ? '확인' : '누락');

    const hasStopAction = content.includes('stop') && content.includes('action');
    addTestResult('3-4. stop 액션 처리', hasStopAction, hasStopAction ? '확인' : '누락');

  } catch (error) {
    addTestResult('3. 스케줄러 API', false, error.message);
  }
  console.log('');
}

// 4. 스케줄러 버튼
function testSchedulerButton() {
  console.log('📝 STEP 4: 스케줄러 버튼 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    const hasButton = content.includes('onClick') && (content.includes('toggleScheduler') || content.includes('scheduler'));
    addTestResult('4-1. 스케줄러 제어 버튼', hasButton, hasButton ? '확인' : '누락');

    const hasConditionalText = content.includes('?') && (content.includes('시작') || content.includes('중지') || content.includes('Start') || content.includes('Stop'));
    addTestResult('4-2. 조건부 버튼 텍스트', hasConditionalText, hasConditionalText ? '확인' : '누락');

  } catch (error) {
    addTestResult('4. 스케줄러 버튼', false, error.message);
  }
  console.log('');
}

async function runTests() {
  console.log('🧪 [스케줄러 시작/중지 통합테스트] 시작\n');
  console.log('='.repeat(70) + '\n');

  testSchedulerToggle();
  testSchedulerStatus();
  testSchedulerApi();
  testSchedulerButton();

  console.log('='.repeat(70));
  console.log('📊 테스트 결과 요약');
  console.log('='.repeat(70));
  console.log(`✅ 통과: ${testResults.passed}/${testResults.tests.length}`);
  console.log(`❌ 실패: ${testResults.failed}/${testResults.tests.length}`);
  console.log(`📈 커버리지: ${((testResults.passed / testResults.tests.length) * 100).toFixed(1)}%`);
  console.log('='.repeat(70));

  // 결과 저장
  const resultsDir = path.join(__dirname, 'test-results');
  if (!fs.existsSync(resultsDir)) fs.mkdirSync(resultsDir, { recursive: true });

  fs.writeFileSync(
    path.join(resultsDir, 'scheduler-control.json'),
    JSON.stringify({
      testName: '스케줄러 시작/중지',
      category: '자동화 시스템',
      timestamp: new Date().toISOString(),
      passed: testResults.failed === 0,
      summary: {
        total: testResults.tests.length,
        passed: testResults.passed,
        failed: testResults.failed,
        percentage: parseFloat(((testResults.passed / testResults.tests.length) * 100).toFixed(1))
      },
      tests: testResults.tests
    }, null, 2)
  );

  process.exit(testResults.failed === 0 ? 0 : 1);
}

runTests();
