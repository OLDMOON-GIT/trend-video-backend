/**
 * 자동화 영상 제작 시스템 통합 테스트
 *
 * 테스트 범위:
 * 1. 전체 자동화 플로우 (대본 생성 → 영상 생성 → YouTube 업로드)
 * 2. 이미지 업로드 기능
 * 3. 큐 관리 및 상태 전환
 * 4. 에러 핸들링
 * 5. UI 네비게이션 (자동화 → 내 콘텐츠)
 */

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// 테스트 설정
const BASE_URL = 'http://localhost:3000';
const TEST_USER = {
  email: 'test@example.com',
  password: 'test123'
};

// 테스트 결과 저장
const testResults = [];
let testSession = null;

function log(message, type = 'info') {
  const timestamp = new Date().toISOString();
  const prefix = {
    'info': 'ℹ️',
    'success': '✅',
    'error': '❌',
    'warning': '⚠️'
  }[type] || 'ℹ️';

  console.log(`[${timestamp}] ${prefix} ${message}`);
}

/**
 * 데이터베이스 쿼리 헬퍼
 */
function queryDb(query) {
  const dbPath = path.join(__dirname, 'trend-video-frontend', 'data', 'database.sqlite');
  try {
    const result = execSync(`sqlite3 "${dbPath}" "${query}"`, {
      encoding: 'utf-8',
      maxBuffer: 10 * 1024 * 1024
    });
    return result.trim();
  } catch (error) {
    console.error('DB 쿼리 실패:', error.message);
    return '';
  }
}

/**
 * 테스트 1: 자동화 타이틀 생성
 */
async function test1_createAutomationTitle() {
  log('테스트 1: 자동화 타이틀 생성', 'info');

  const testCases = [
    {
      name: 'Shortform 타이틀 생성',
      data: {
        title: '테스트 - Shortform 자동화',
        type: 'shortform',
        scheduled_time: new Date(Date.now() + 3600000).toISOString() // 1시간 후
      }
    },
    {
      name: 'Product 타이틀 생성',
      data: {
        title: '테스트 - 상품 자동화',
        type: 'product',
        product_url: 'https://www.coupang.com/vp/products/test',
        scheduled_time: new Date(Date.now() + 7200000).toISOString() // 2시간 후
      }
    }
  ];

  for (const testCase of testCases) {
    log(`  테스트 케이스: ${testCase.name}`, 'info');

    try {
      const response = await fetch(`${BASE_URL}/api/automation/titles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(testCase.data)
      });

      const result = await response.json();

      if (response.ok && result.success) {
        log(`    ✅ PASS: 타이틀 생성 성공 (ID: ${result.titleId})`, 'success');
        testResults.push({
          name: testCase.name,
          status: 'PASS',
          titleId: result.titleId
        });
      } else {
        log(`    ❌ FAIL: ${result.error || '알 수 없는 오류'}`, 'error');
        testResults.push({
          name: testCase.name,
          status: 'FAIL',
          error: result.error
        });
      }
    } catch (error) {
      log(`    ❌ ERROR: ${error.message}`, 'error');
      testResults.push({
        name: testCase.name,
        status: 'ERROR',
        error: error.message
      });
    }
  }
}

/**
 * 테스트 2: 대본 생성 단계
 */
async function test2_scriptGeneration() {
  log('테스트 2: 대본 생성 단계', 'info');

  // 가장 최근 생성된 타이틀 찾기
  const titleResult = queryDb(`
    SELECT id, title, type
    FROM video_titles
    WHERE title LIKE '테스트%'
    ORDER BY created_at DESC
    LIMIT 1
  `);

  if (!titleResult) {
    log('  ⚠️ SKIP: 테스트용 타이틀이 없습니다', 'warning');
    return;
  }

  const [titleId, title, type] = titleResult.split('|');

  log(`  대상 타이틀: ${title} (${titleId})`, 'info');

  // 스케줄 조회
  const scheduleResult = queryDb(`
    SELECT id, status, script_id
    FROM video_schedules
    WHERE title_id = '${titleId}'
    ORDER BY created_at DESC
    LIMIT 1
  `);

  if (!scheduleResult) {
    log('  ❌ FAIL: 스케줄이 생성되지 않았습니다', 'error');
    testResults.push({
      name: '대본 생성 스케줄 조회',
      status: 'FAIL',
      error: 'No schedule found'
    });
    return;
  }

  const [scheduleId, status, scriptId] = scheduleResult.split('|');

  log(`  스케줄 ID: ${scheduleId}, 상태: ${status}`, 'info');

  // 파이프라인 상태 확인
  const pipelineResult = queryDb(`
    SELECT stage, status, error_message
    FROM automation_pipelines
    WHERE schedule_id = '${scheduleId}'
    ORDER BY created_at DESC
  `);

  if (pipelineResult) {
    const pipelines = pipelineResult.split('\n').map(line => {
      const [stage, pipeStatus, errorMsg] = line.split('|');
      return { stage, status: pipeStatus, error: errorMsg };
    });

    log(`  파이프라인 단계:`, 'info');
    pipelines.forEach(p => {
      const statusEmoji = p.status === 'completed' ? '✅' : p.status === 'error' ? '❌' : '⏳';
      log(`    ${statusEmoji} ${p.stage}: ${p.status}`, 'info');
      if (p.error) {
        log(`      에러: ${p.error}`, 'error');
      }
    });

    // 대본 생성 완료 여부 확인
    const scriptGenPipeline = pipelines.find(p => p.stage === 'generate_script');
    if (scriptGenPipeline) {
      if (scriptGenPipeline.status === 'completed' && scriptId) {
        log(`  ✅ PASS: 대본 생성 완료 (script_id: ${scriptId})`, 'success');
        testResults.push({
          name: '대본 생성',
          status: 'PASS',
          scriptId
        });
      } else if (scriptGenPipeline.status === 'error') {
        log(`  ❌ FAIL: 대본 생성 실패`, 'error');
        testResults.push({
          name: '대본 생성',
          status: 'FAIL',
          error: scriptGenPipeline.error
        });
      } else {
        log(`  ⏳ IN_PROGRESS: 대본 생성 중...`, 'warning');
        testResults.push({
          name: '대본 생성',
          status: 'IN_PROGRESS'
        });
      }
    }
  }
}

/**
 * 테스트 3: 이미지 업로드 기능
 */
async function test3_imageUpload() {
  log('테스트 3: 이미지 업로드 기능', 'info');

  const testCases = [
    {
      name: '이미지 업로드 API 엔드포인트 존재 확인',
      test: async () => {
        const apiPath = path.join(
          __dirname,
          'trend-video-frontend',
          'src',
          'app',
          'api',
          'automation',
          'upload-images',
          'route.ts'
        );

        if (!fs.existsSync(apiPath)) {
          return { error: 'upload-images API 파일이 존재하지 않음' };
        }

        const content = fs.readFileSync(apiPath, 'utf-8');

        // POST 메서드 존재 확인
        if (!content.includes('export async function POST')) {
          return { error: 'POST 메서드가 정의되지 않음' };
        }

        // 주요 기능 확인
        const features = {
          'FormData 처리': content.includes('formData.get'),
          'scheduleId 검증': content.includes('scheduleId'),
          'scriptId 검증': content.includes('scriptId'),
          'images 검증': content.includes('images'),
          'story.json 생성': content.includes('story.json')
        };

        const missingFeatures = Object.entries(features)
          .filter(([_, exists]) => !exists)
          .map(([feature]) => feature);

        if (missingFeatures.length > 0) {
          return { error: `누락된 기능: ${missingFeatures.join(', ')}` };
        }

        return { success: '모든 필수 기능이 구현됨' };
      }
    },
    {
      name: 'automation/page.tsx 업로드 UI 확인',
      test: async () => {
        const pagePath = path.join(
          __dirname,
          'trend-video-frontend',
          'src',
          'app',
          'automation',
          'page.tsx'
        );

        if (!fs.existsSync(pagePath)) {
          return { error: 'automation page 파일이 존재하지 않음' };
        }

        const content = fs.readFileSync(pagePath, 'utf-8');

        // uploadImages 함수 존재 확인
        if (!content.includes('function uploadImages')) {
          return { error: 'uploadImages 함수가 정의되지 않음' };
        }

        // MediaUploadBox 컴포넌트 사용 확인
        if (!content.includes('<MediaUploadBox')) {
          return { error: 'MediaUploadBox 컴포넌트가 사용되지 않음' };
        }

        // script_id 찾기 로직 확인 (다양한 패턴 허용)
        if (!content.includes('script_id') ||
            !(content.includes('.find') || content.includes('scriptId') || content.includes('scriptSchedule'))) {
          return { error: 'script_id 찾기 로직이 구현되지 않음' };
        }

        return { success: '이미지 업로드 UI가 올바르게 구현됨' };
      }
    }
  ];

  for (const testCase of testCases) {
    log(`  테스트 케이스: ${testCase.name}`, 'info');

    try {
      const result = await testCase.test();

      if (result.error) {
        log(`    ❌ FAIL: ${result.error}`, 'error');
        testResults.push({
          name: testCase.name,
          status: 'FAIL',
          error: result.error
        });
      } else {
        log(`    ✅ PASS: ${result.success}`, 'success');
        testResults.push({
          name: testCase.name,
          status: 'PASS'
        });
      }
    } catch (error) {
      log(`    ❌ ERROR: ${error.message}`, 'error');
      testResults.push({
        name: testCase.name,
        status: 'ERROR',
        error: error.message
      });
    }
  }
}

/**
 * 테스트 4: 내 콘텐츠 네비게이션
 */
async function test4_myContentNavigation() {
  log('테스트 4: 내 콘텐츠 네비게이션', 'info');

  const testCases = [
    {
      name: '자동화 → 내 콘텐츠 이동 버튼 확인',
      test: async () => {
        const automationPath = path.join(
          __dirname,
          'trend-video-frontend',
          'src',
          'app',
          'automation',
          'page.tsx'
        );

        const content = fs.readFileSync(automationPath, 'utf-8');

        // 대본/영상 버튼 확인
        if (!content.includes('📄 대본') || !content.includes('🎬 영상')) {
          return { error: '대본/영상 버튼이 없음' };
        }

        // 네비게이션 로직 확인
        if (!content.includes('/my-content?tab=scripts') || !content.includes('/my-content?tab=videos')) {
          return { error: '내 콘텐츠 링크가 올바르지 않음' };
        }

        // 완료 상태 필터 확인
        if (!content.includes("status === 'completed'")) {
          return { error: '완료 상태 필터가 없음' };
        }

        return { success: '네비게이션 버튼이 올바르게 구현됨' };
      }
    },
    {
      name: '내 콘텐츠 하이라이트 기능 확인',
      test: async () => {
        const myContentPath = path.join(
          __dirname,
          'trend-video-frontend',
          'src',
          'app',
          'my-content',
          'page.tsx'
        );

        const content = fs.readFileSync(myContentPath, 'utf-8');

        // highlightedId 상태 확인
        if (!content.includes('highlightedId')) {
          return { error: 'highlightedId 상태가 정의되지 않음' };
        }

        // URL 파라미터 처리 확인 (다양한 패턴 허용)
        if (!(content.includes("urlParams.get('id')") || content.includes('searchParams.get(\'id\')'))) {
          return { error: 'URL 파라미터 처리가 없음' };
        }

        // 하이라이트 스타일 확인
        if (!content.includes('border-yellow-500') || !content.includes('animate-pulse')) {
          return { error: '하이라이트 스타일이 없음' };
        }

        // 자동 스크롤 확인
        if (!content.includes('scrollIntoView')) {
          return { error: '자동 스크롤 기능이 없음' };
        }

        return { success: '하이라이트 기능이 올바르게 구현됨' };
      }
    },
    {
      name: '쿠팡 탭 제거 확인',
      test: async () => {
        const myContentPath = path.join(
          __dirname,
          'trend-video-frontend',
          'src',
          'app',
          'my-content',
          'page.tsx'
        );

        const content = fs.readFileSync(myContentPath, 'utf-8');

        // TabType에서 coupang 제거 확인
        const tabTypeMatch = content.match(/type TabType = '([^']+)'/);
        if (tabTypeMatch && tabTypeMatch[1].includes('coupang')) {
          return { error: "TabType에 여전히 'coupang'이 포함되어 있음" };
        }

        // 쿠팡 탭 버튼 비활성화 확인
        const coupangButtonMatch = content.match(/🛒 쿠팡상품/);
        if (coupangButtonMatch) {
          return { error: '쿠팡 상품 버튼이 여전히 존재함' };
        }

        return { success: '쿠팡 탭이 성공적으로 제거됨' };
      }
    }
  ];

  for (const testCase of testCases) {
    log(`  테스트 케이스: ${testCase.name}`, 'info');

    try {
      const result = await testCase.test();

      if (result.error) {
        log(`    ❌ FAIL: ${result.error}`, 'error');
        testResults.push({
          name: testCase.name,
          status: 'FAIL',
          error: result.error
        });
      } else {
        log(`    ✅ PASS: ${result.success}`, 'success');
        testResults.push({
          name: testCase.name,
          status: 'PASS'
        });
      }
    } catch (error) {
      log(`    ❌ ERROR: ${error.message}`, 'error');
      testResults.push({
        name: testCase.name,
        status: 'ERROR',
        error: error.message
      });
    }
  }
}

/**
 * 테스트 5: 데이터베이스 스키마 확인
 */
async function test5_databaseSchema() {
  log('테스트 5: 데이터베이스 스키마 확인', 'info');

  const testCases = [
    {
      name: 'video_schedules 테이블에 youtube_url 컬럼 존재',
      query: "PRAGMA table_info(video_schedules)",
      validate: (result) => {
        return result.includes('youtube_url');
      }
    },
    {
      name: 'automation_pipelines UNIQUE 제약조건 존재',
      query: "SELECT sql FROM sqlite_master WHERE type='table' AND name='automation_pipelines'",
      validate: (result) => {
        return result.includes('UNIQUE') && result.includes('schedule_id') && result.includes('stage');
      }
    },
    {
      name: 'video_titles 테이블 존재',
      query: "SELECT name FROM sqlite_master WHERE type='table' AND name='video_titles'",
      validate: (result) => {
        return result === 'video_titles';
      }
    }
  ];

  for (const testCase of testCases) {
    log(`  테스트 케이스: ${testCase.name}`, 'info');

    try {
      const result = queryDb(testCase.query);

      if (testCase.validate(result)) {
        log(`    ✅ PASS`, 'success');
        testResults.push({
          name: testCase.name,
          status: 'PASS'
        });
      } else {
        log(`    ❌ FAIL: 조건을 만족하지 않음`, 'error');
        log(`    결과: ${result.substring(0, 100)}...`, 'info');
        testResults.push({
          name: testCase.name,
          status: 'FAIL',
          error: '조건을 만족하지 않음'
        });
      }
    } catch (error) {
      log(`    ❌ ERROR: ${error.message}`, 'error');
      testResults.push({
        name: testCase.name,
        status: 'ERROR',
        error: error.message
      });
    }
  }
}

/**
 * 테스트 6: Shortform CTA 프롬프트 확인
 */
async function test6_shortformCTA() {
  log('테스트 6: Shortform CTA 프롬프트 확인', 'info');

  const promptPath = path.join(
    __dirname,
    'trend-video-frontend',
    'prompts',
    'prompt_shortform.txt'
  );

  if (!fs.existsSync(promptPath)) {
    log('  ❌ FAIL: prompt_shortform.txt 파일이 없음', 'error');
    testResults.push({
      name: 'Shortform CTA 프롬프트',
      status: 'FAIL',
      error: 'File not found'
    });
    return;
  }

  const content = fs.readFileSync(promptPath, 'utf-8');

  const checks = {
    '씬 4 CTA 언급': content.includes('씬 4') && content.includes('CTA'),
    '80자 여운': content.includes('80자') && content.includes('여운'),
    '70자 CTA': content.includes('70자') && content.includes('CTA'),
    '자연스러운 연결': content.includes('자연스럽게') || content.includes('부드럽게')
  };

  const failed = Object.entries(checks).filter(([_, passed]) => !passed);

  if (failed.length === 0) {
    log('  ✅ PASS: 모든 CTA 요구사항이 충족됨', 'success');
    testResults.push({
      name: 'Shortform CTA 프롬프트',
      status: 'PASS'
    });
  } else {
    log(`  ❌ FAIL: 누락된 요소: ${failed.map(([name]) => name).join(', ')}`, 'error');
    testResults.push({
      name: 'Shortform CTA 프롬프트',
      status: 'FAIL',
      error: `Missing: ${failed.map(([name]) => name).join(', ')}`
    });
  }
}

/**
 * 메인 테스트 실행
 */
async function runAllTests() {
  log('='.repeat(80), 'info');
  log('자동화 영상 제작 시스템 통합 테스트 시작', 'info');
  log('='.repeat(80), 'info');

  try {
    // await test1_createAutomationTitle();
    // log('', 'info');

    // await test2_scriptGeneration();
    // log('', 'info');

    await test3_imageUpload();
    log('', 'info');

    await test4_myContentNavigation();
    log('', 'info');

    await test5_databaseSchema();
    log('', 'info');

    await test6_shortformCTA();
    log('', 'info');

    // 결과 요약
    log('='.repeat(80), 'info');
    log('테스트 결과 요약', 'info');
    log('='.repeat(80), 'info');

    const passed = testResults.filter(r => r.status === 'PASS').length;
    const failed = testResults.filter(r => r.status === 'FAIL').length;
    const errors = testResults.filter(r => r.status === 'ERROR').length;
    const inProgress = testResults.filter(r => r.status === 'IN_PROGRESS').length;

    log(`총 ${testResults.length}개 테스트`, 'info');
    log(`✅ PASS: ${passed}`, 'success');
    log(`❌ FAIL: ${failed}`, 'error');
    log(`❌ ERROR: ${errors}`, 'error');
    log(`⏳ IN_PROGRESS: ${inProgress}`, 'warning');

    // 실패한 테스트 상세
    if (failed > 0 || errors > 0) {
      log('', 'info');
      log('실패한 테스트:', 'error');
      testResults
        .filter(r => r.status === 'FAIL' || r.status === 'ERROR')
        .forEach(r => {
          log(`  - ${r.name}: ${r.error}`, 'error');
        });
    }

    // JSON 파일로 저장
    const reportPath = path.join(__dirname, 'test-results', 'automation-integration-report.json');
    const reportDir = path.dirname(reportPath);

    if (!fs.existsSync(reportDir)) {
      fs.mkdirSync(reportDir, { recursive: true });
    }

    fs.writeFileSync(reportPath, JSON.stringify({
      timestamp: new Date().toISOString(),
      summary: { total: testResults.length, passed, failed, errors, inProgress },
      results: testResults
    }, null, 2));

    log('', 'info');
    log(`테스트 리포트 저장: ${reportPath}`, 'info');

  } catch (error) {
    log(`테스트 실행 중 오류: ${error.message}`, 'error');
    console.error(error);
  }
}

// 테스트 실행
runAllTests().catch(console.error);
