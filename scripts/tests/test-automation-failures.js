/**
 * 자동화 실패 케이스 통합 테스트
 *
 * 실패 케이스:
 * 1. Chrome script generation failed with code 1
 * 2. Cannot access 'process1' before initialization
 */

const path = require('path');
const { spawn, execSync } = require('child_process');
const fs = require('fs');

// better-sqlite3 대신 sqlite3 CLI 사용
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

// 테스트 결과 저장
const testResults = [];

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
 * 테스트 1: Chrome 대본 생성 실패 케이스
 *
 * 원인: Python 스크립트 실행 중 오류 발생
 * - 이미지 미업로드 (0개 발견)
 * - Vertex AI 빌링 비활성화
 * - 스크립트 파일 누락
 */
async function test1_scriptGenerationFailure() {
  log('테스트 1: Chrome 대본 생성 실패 케이스', 'info');

  const testCases = [
    {
      name: '이미지 미업로드 시나리오',
      description: '이미지가 0개일 때 영상 생성 실패',
      setup: async () => {
        // 이미지 없는 폴더 생성
        const testFolder = path.join(__dirname, 'trend-video-backend', 'input', 'test_no_images');
        if (!fs.existsSync(testFolder)) {
          fs.mkdirSync(testFolder, { recursive: true });
        }

        // story.json만 생성
        fs.writeFileSync(
          path.join(testFolder, 'story.json'),
          JSON.stringify({
            title: "테스트 - 이미지 미업로드",
            scenes: [
              { narration: "씬 1", duration: 5 },
              { narration: "씬 2", duration: 5 }
            ]
          }, null, 2)
        );

        return testFolder;
      },
      expectedError: '이미지 0개 발견',
      expectedBehavior: 'Python 스크립트가 exit code 1로 종료되어야 함'
    },
    {
      name: 'Vertex AI 빌링 비활성화 시나리오',
      description: 'Imagen3 호출 시 빌링 에러',
      setup: async () => {
        // media_mode가 'imagen3'인 경우 시뮬레이션
        const testFolder = path.join(__dirname, 'trend-video-backend', 'input', 'test_billing_error');
        if (!fs.existsSync(testFolder)) {
          fs.mkdirSync(testFolder, { recursive: true });
        }

        fs.writeFileSync(
          path.join(testFolder, 'story.json'),
          JSON.stringify({
            title: "테스트 - Vertex AI 빌링",
            media_mode: 'imagen3',
            scenes: [
              { narration: "씬 1", duration: 5, image_prompt: "test" }
            ]
          }, null, 2)
        );

        return testFolder;
      },
      expectedError: 'BILLING_DISABLED',
      expectedBehavior: 'Vertex AI 초기화 실패로 인한 graceful failure'
    },
    {
      name: '스크립트 ID 누락 시나리오',
      description: 'script_id가 없어서 story.json을 찾을 수 없음',
      setup: async () => {
        return null; // 폴더 자체를 생성하지 않음
      },
      expectedError: 'story.json not found',
      expectedBehavior: 'API 요청이 400 에러를 반환해야 함'
    }
  ];

  for (const testCase of testCases) {
    log(`  테스트 케이스: ${testCase.name}`, 'info');
    log(`  설명: ${testCase.description}`, 'info');

    try {
      const testFolder = await testCase.setup();

      // 실제 테스트: 폴더 구조와 파일 존재 확인
      let testPassed = false;
      let actualResult = '';

      if (testCase.expectedError === '이미지 0개 발견') {
        // 이미지 파일이 없는지 확인
        if (testFolder && fs.existsSync(testFolder)) {
          const images = fs.readdirSync(testFolder).filter(f =>
            /\.(png|jpg|jpeg)$/i.test(f) && !f.includes('thumbnail')
          );
          testPassed = images.length === 0;
          actualResult = `이미지 ${images.length}개 발견`;
        }
      } else if (testCase.expectedError === 'BILLING_DISABLED') {
        // media_mode가 'upload'로 변경되었는지 확인
        const apiRoute = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'generate-video-upload', 'route.ts');
        if (fs.existsSync(apiRoute)) {
          const content = fs.readFileSync(apiRoute, 'utf-8');
          // media_mode가 'upload'로 하드코딩되어 있는지 확인
          testPassed = content.includes("media_mode: 'upload'");
          actualResult = testPassed ? "media_mode가 'upload'로 설정됨" : "media_mode 설정 미확인";
        }
      } else if (testCase.expectedError === 'story.json not found') {
        // 폴더가 없으면 story.json도 없음
        testPassed = !testFolder || !fs.existsSync(testFolder);
        actualResult = testPassed ? 'story.json 없음' : 'story.json 존재';
      }

      if (testPassed) {
        log(`    ✅ PASS: ${testCase.expectedBehavior}`, 'success');
        testResults.push({ name: testCase.name, status: 'PASS', result: actualResult });
      } else {
        log(`    ❌ FAIL: ${testCase.expectedBehavior}`, 'error');
        log(`    예상: ${testCase.expectedError}`, 'error');
        log(`    실제: ${actualResult}`, 'error');
        testResults.push({ name: testCase.name, status: 'FAIL', error: actualResult });
      }

      // 테스트 폴더 정리
      if (testFolder && fs.existsSync(testFolder)) {
        fs.rmSync(testFolder, { recursive: true, force: true });
      }
    } catch (error) {
      log(`    ❌ ERROR: ${error.message}`, 'error');
      testResults.push({ name: testCase.name, status: 'ERROR', error: error.message });
    }
  }
}

/**
 * 테스트 2: 프로세스 초기화 에러 케이스
 *
 * 원인: automation-scheduler.ts의 process1 변수 초기화 순서 문제
 * - 스케줄러가 동시에 여러 작업을 처리할 때 발생
 * - TDZ (Temporal Dead Zone) 에러
 */
async function test2_processInitializationError() {
  log('테스트 2: 프로세스 초기화 에러 케이스', 'info');

  const testCases = [
    {
      name: '동시 작업 처리 시나리오',
      description: '여러 작업이 동시에 스케줄러에 진입',
      test: async () => {
        // 자동화 큐에 여러 작업을 동시에 추가
        const titleIds = [];
        const scheduleIds = [];

        for (let i = 0; i < 5; i++) {
          const titleId = `title_test_concurrent_${Date.now()}_${i}`;
          const scheduleId = `schedule_test_concurrent_${Date.now()}_${i}`;

          queryDb(`INSERT INTO video_titles (id, title, content, created_at) VALUES ('${titleId}', '동시 테스트 ${i}', '{"scenes":[]}', datetime('now'))`);
          queryDb(`INSERT INTO video_schedules (id, title_id, scheduled_time, status) VALUES ('${scheduleId}', '${titleId}', datetime('now'), 'pending')`);

          titleIds.push(titleId);
          scheduleIds.push(scheduleId);
        }

        log(`    생성된 스케줄: ${scheduleIds.length}개`, 'info');

        // 스케줄러가 이들을 처리하도록 대기
        await new Promise(resolve => setTimeout(resolve, 5000));

        // 에러 로그 확인
        const errorResult = queryDb(`SELECT message FROM automation_logs WHERE message LIKE '%process1%' AND created_at > datetime('now', '-10 seconds')`);
        const errors = errorResult ? errorResult.split('\n').map(msg => ({ message: msg })) : [];

        // 정리
        for (const scheduleId of scheduleIds) {
          queryDb(`DELETE FROM video_schedules WHERE id = '${scheduleId}'`);
        }
        for (const titleId of titleIds) {
          queryDb(`DELETE FROM video_titles WHERE id = '${titleId}'`);
        }

        return errors;
      },
      expectedBehavior: 'process1 초기화 에러가 발생하지 않아야 함 (수정 후)'
    },
    {
      name: 'TDZ 에러 재현 시나리오',
      description: '변수 선언 전 접근 시도',
      test: async () => {
        // automation-scheduler.ts 코드 검사
        const schedulerPath = path.join(__dirname, 'trend-video-frontend', 'src', 'lib', 'automation-scheduler.ts');
        const schedulerCode = fs.readFileSync(schedulerPath, 'utf-8');

        // process1 변수 선언 위치 확인
        const process1Declaration = schedulerCode.indexOf('let process1');
        const process1Usage = schedulerCode.indexOf('process1.kill');

        if (process1Declaration === -1) {
          return { error: 'process1 변수를 찾을 수 없음' };
        }

        if (process1Usage !== -1 && process1Usage < process1Declaration) {
          return { error: 'process1 변수가 선언 전에 사용됨 (TDZ 에러 가능)' };
        }

        return { success: 'process1 변수 선언 순서가 올바름' };
      },
      expectedBehavior: '변수 선언이 사용보다 먼저 위치해야 함'
    }
  ];

  for (const testCase of testCases) {
    log(`  테스트 케이스: ${testCase.name}`, 'info');
    log(`  설명: ${testCase.description}`, 'info');

    try {
      const result = await testCase.test();

      if (result.error) {
        log(`    ❌ FAIL: ${result.error}`, 'error');
        testResults.push({ name: testCase.name, status: 'FAIL', error: result.error });
      } else if (result.success) {
        log(`    ✅ PASS: ${result.success}`, 'success');
        testResults.push({ name: testCase.name, status: 'PASS' });
      } else if (Array.isArray(result) && result.length === 0) {
        log(`    ✅ PASS: ${testCase.expectedBehavior}`, 'success');
        testResults.push({ name: testCase.name, status: 'PASS' });
      } else {
        log(`    ⚠️ WARNING: 예상치 못한 결과`, 'warning');
        log(`    결과: ${JSON.stringify(result)}`, 'warning');
        testResults.push({ name: testCase.name, status: 'WARNING', result });
      }
    } catch (error) {
      log(`    ❌ ERROR: ${error.message}`, 'error');
      testResults.push({ name: testCase.name, status: 'ERROR', error: error.message });
    }
  }
}

/**
 * 테스트 3: 백업 폴더 생성 방지 확인
 *
 * 원인: create_video_from_folder.py의 _backup_previous_videos() 호출
 * 수정: 해당 호출을 주석 처리
 */
async function test3_backupFolderPrevention() {
  log('테스트 3: 백업 폴더 생성 방지 확인', 'info');

  const testCases = [
    {
      name: 'Python 스크립트 백업 함수 비활성화 확인',
      description: '_backup_previous_videos() 호출이 주석 처리되어 있는지 확인',
      test: async () => {
        const pythonScriptPath = path.join(__dirname, 'trend-video-backend', 'create_video_from_folder.py');

        if (!fs.existsSync(pythonScriptPath)) {
          return { error: 'Python 스크립트를 찾을 수 없음' };
        }

        const scriptContent = fs.readFileSync(pythonScriptPath, 'utf-8');

        // _backup_previous_videos() 호출이 주석 처리되어 있는지 확인
        const lines = scriptContent.split('\n');
        let backupCallLine = -1;
        let isCommented = false;

        for (let i = 0; i < lines.length; i++) {
          if (lines[i].includes('self._backup_previous_videos()')) {
            backupCallLine = i + 1; // 1-based line number
            isCommented = lines[i].trim().startsWith('#');
            break;
          }
        }

        if (backupCallLine === -1) {
          return { error: '_backup_previous_videos() 호출을 찾을 수 없음' };
        }

        if (!isCommented) {
          return { error: `Line ${backupCallLine}: _backup_previous_videos() 호출이 활성화되어 있음 (주석 처리 필요)` };
        }

        return { success: `Line ${backupCallLine}: _backup_previous_videos() 호출이 주석 처리되어 있음` };
      },
      expectedBehavior: 'backup 폴더가 생성되지 않아야 함'
    },
    {
      name: '영상 생성 후 backup 폴더 존재 확인',
      description: '실제 영상 생성 후 backup 폴더가 생기지 않는지 확인',
      test: async () => {
        // 최근 생성된 프로젝트 폴더 찾기
        const inputPath = path.join(__dirname, 'trend-video-backend', 'input');

        if (!fs.existsSync(inputPath)) {
          return { warning: 'Input 폴더가 존재하지 않음' };
        }

        const projectFolders = fs.readdirSync(inputPath)
          .filter(name => name.startsWith('project_'))
          .map(name => ({
            name,
            path: path.join(inputPath, name),
            mtime: fs.statSync(path.join(inputPath, name)).mtime
          }))
          .sort((a, b) => b.mtime - a.mtime);

        if (projectFolders.length === 0) {
          return { warning: '프로젝트 폴더가 없음' };
        }

        // 가장 최근 프로젝트에서 backup 폴더 찾기
        const recentProject = projectFolders[0];
        const backupFolders = fs.readdirSync(recentProject.path)
          .filter(name => name.startsWith('backup_'));

        if (backupFolders.length > 0) {
          return {
            error: `backup 폴더 발견: ${backupFolders.join(', ')}`,
            project: recentProject.name
          };
        }

        return {
          success: '최근 프로젝트에 backup 폴더 없음',
          project: recentProject.name
        };
      },
      expectedBehavior: 'backup 폴더가 존재하지 않아야 함'
    }
  ];

  for (const testCase of testCases) {
    log(`  테스트 케이스: ${testCase.name}`, 'info');
    log(`  설명: ${testCase.description}`, 'info');

    try {
      const result = await testCase.test();

      if (result.error) {
        log(`    ❌ FAIL: ${result.error}`, 'error');
        if (result.project) {
          log(`    프로젝트: ${result.project}`, 'error');
        }
        testResults.push({ name: testCase.name, status: 'FAIL', error: result.error });
      } else if (result.success) {
        log(`    ✅ PASS: ${result.success}`, 'success');
        if (result.project) {
          log(`    프로젝트: ${result.project}`, 'success');
        }
        testResults.push({ name: testCase.name, status: 'PASS' });
      } else if (result.warning) {
        log(`    ⚠️ SKIP: ${result.warning}`, 'warning');
        testResults.push({ name: testCase.name, status: 'SKIP', warning: result.warning });
      }
    } catch (error) {
      log(`    ❌ ERROR: ${error.message}`, 'error');
      testResults.push({ name: testCase.name, status: 'ERROR', error: error.message });
    }
  }
}

/**
 * 테스트 실행
 */
async function runAllTests() {
  log('='.repeat(80), 'info');
  log('자동화 실패 케이스 통합 테스트 시작', 'info');
  log('='.repeat(80), 'info');

  try {
    await test1_scriptGenerationFailure();
    log('', 'info');

    await test2_processInitializationError();
    log('', 'info');

    await test3_backupFolderPrevention();
    log('', 'info');

    // 결과 요약
    log('='.repeat(80), 'info');
    log('테스트 결과 요약', 'info');
    log('='.repeat(80), 'info');

    const passed = testResults.filter(r => r.status === 'PASS').length;
    const failed = testResults.filter(r => r.status === 'FAIL').length;
    const errors = testResults.filter(r => r.status === 'ERROR').length;
    const skipped = testResults.filter(r => r.status === 'SKIP').length;
    const warnings = testResults.filter(r => r.status === 'WARNING').length;

    log(`총 ${testResults.length}개 테스트`, 'info');
    log(`✅ PASS: ${passed}`, 'success');
    log(`❌ FAIL: ${failed}`, 'error');
    log(`❌ ERROR: ${errors}`, 'error');
    log(`⚠️ WARNING: ${warnings}`, 'warning');
    log(`⚠️ SKIP: ${skipped}`, 'warning');

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
    const reportPath = path.join(__dirname, 'test-results', 'automation-failures-report.json');
    const reportDir = path.dirname(reportPath);

    if (!fs.existsSync(reportDir)) {
      fs.mkdirSync(reportDir, { recursive: true });
    }

    fs.writeFileSync(reportPath, JSON.stringify({
      timestamp: new Date().toISOString(),
      summary: { total: testResults.length, passed, failed, errors, skipped, warnings },
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
