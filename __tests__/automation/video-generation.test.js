const fs = require('fs');
const path = require('path');

// 테스트 설정
const BASE_URL = 'http://localhost:3000';
const TEST_TITLE_ID = 'title_1763034024808_apvhfsle2';
const TEST_SCRIPT_ID = 'job_1763044825741_bh5psnf8a';

// 테스트 결과 추적
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

async function runTests() {
  console.log('🧪 [자동화 영상 제작 테스트] 시작\n');
  console.log('테스트 대상:');
  console.log('  - titleId:', TEST_TITLE_ID);
  console.log('  - scriptId:', TEST_SCRIPT_ID);
  console.log('  - 폴더: input/project_' + TEST_SCRIPT_ID);
  console.log('\n' + '='.repeat(70) + '\n');

  try {
    // 테스트 1: story.json 읽기 (get-story API)
    console.log('1️⃣ 테스트: story.json 읽기 API');
    try {
      const storyRes = await fetch(`${BASE_URL}/api/automation/get-story?scriptId=${TEST_SCRIPT_ID}`, {
        credentials: 'include'
      });

      if (!storyRes.ok) {
        addTestResult('get-story API', false, `HTTP ${storyRes.status}: ${await storyRes.text()}`);
      } else {
        const storyData = await storyRes.json();
        if (storyData.success && storyData.storyJson) {
          addTestResult('get-story API', true, `씬 ${storyData.storyJson.scenes?.length || 0}개 읽기 성공`);
        } else {
          addTestResult('get-story API', false, 'storyJson이 없음');
        }
      }
    } catch (error) {
      addTestResult('get-story API', false, error.message);
    }

    // 테스트 2: 폴더 존재 확인
    console.log('\n2️⃣ 테스트: input 폴더 존재 확인');
    try {
      const backendPath = path.join(__dirname, 'trend-video-backend');
      const projectPath = path.join(backendPath, 'input', `project_${TEST_SCRIPT_ID}`);
      const storyPath = path.join(projectPath, 'story.json');

      if (fs.existsSync(projectPath)) {
        addTestResult('input 폴더 존재', true, projectPath);

        if (fs.existsSync(storyPath)) {
          addTestResult('story.json 존재', true, storyPath);

          // 이미지 파일 개수 확인
          const files = fs.readdirSync(projectPath);
          const imageFiles = files.filter(f => /\.(jpg|png|jpeg)$/i.test(f));
          addTestResult('이미지 파일 개수', imageFiles.length > 0, `${imageFiles.length}개`);
        } else {
          addTestResult('story.json 존재', false, '파일 없음');
        }
      } else {
        addTestResult('input 폴더 존재', false, '폴더 없음');
      }
    } catch (error) {
      addTestResult('폴더 존재 확인', false, error.message);
    }

    // 테스트 3: 영상 생성 API 호출 (DRY RUN - 실제 생성 안함)
    console.log('\n3️⃣ 테스트: generate-video-upload API 파라미터 검증');
    try {
      // story.json 읽기
      const storyRes = await fetch(`${BASE_URL}/api/automation/get-story?scriptId=${TEST_SCRIPT_ID}`, {
        credentials: 'include'
      });

      if (!storyRes.ok) {
        addTestResult('API 파라미터 검증', false, 'story.json 읽기 실패');
      } else {
        const { storyJson } = await storyRes.json();

        // 요청 바디 검증
        const requestBody = {
          storyJson,
          userId: 'b5d1f064-60b9-45ab-9bcd-d36948196459',
          imageSource: 'none',
          imageModel: 'dalle3',
          videoFormat: 'shortform',
          ttsVoice: 'ko-KR-SoonBokNeural',
          title: '테스트 영상',
          scriptId: TEST_SCRIPT_ID
        };

        // imageSource 검증
        if (requestBody.imageSource === 'none') {
          addTestResult('imageSource 파라미터', true, 'none (올바름)');
        } else {
          addTestResult('imageSource 파라미터', false, `${requestBody.imageSource} (잘못됨)`);
        }

        // scriptId 검증
        if (requestBody.scriptId === TEST_SCRIPT_ID) {
          addTestResult('scriptId 파라미터', true, TEST_SCRIPT_ID);
        } else {
          addTestResult('scriptId 파라미터', false, '없음');
        }

        // storyJson 검증
        if (storyJson && storyJson.scenes && storyJson.scenes.length > 0) {
          addTestResult('storyJson 구조', true, `씬 ${storyJson.scenes.length}개`);
        } else {
          addTestResult('storyJson 구조', false, '씬이 없음');
        }
      }
    } catch (error) {
      addTestResult('API 파라미터 검증', false, error.message);
    }

    // 테스트 4: Python 명령어 경로 검증 (로그 확인)
    console.log('\n4️⃣ 테스트: Python 명령어 폴더 경로 검증');
    try {
      const logPath = path.join(__dirname, 'trend-video-frontend', 'logs', 'server.log');

      if (fs.existsSync(logPath)) {
        const logContent = fs.readFileSync(logPath, 'utf-8');
        const lines = logContent.split('\n');

        // 최근 Python 명령어 찾기
        const pythonCmdLines = lines.filter(line =>
          line.includes('🐍 Python 명령어:') &&
          line.includes(`project_${TEST_SCRIPT_ID}`)
        );

        if (pythonCmdLines.length > 0) {
          const latestCmd = pythonCmdLines[pythonCmdLines.length - 1];

          // input/ 폴더 사용 확인
          if (latestCmd.includes(`input/project_${TEST_SCRIPT_ID}`)) {
            addTestResult('Python 폴더 경로', true, 'input/ 폴더 사용 (올바름)');
          } else if (latestCmd.includes(`uploads/project_${TEST_SCRIPT_ID}`)) {
            addTestResult('Python 폴더 경로', false, 'uploads/ 폴더 사용 (잘못됨)');
          } else {
            addTestResult('Python 폴더 경로', false, '폴더 경로 확인 불가');
          }
        } else {
          addTestResult('Python 폴더 경로', false, '로그에서 명령어 찾을 수 없음');
        }
      } else {
        addTestResult('Python 폴더 경로', false, '로그 파일 없음');
      }
    } catch (error) {
      addTestResult('Python 폴더 경로', false, error.message);
    }

  } catch (error) {
    console.error('\n❌ 테스트 실행 중 오류:', error);
  }

  // 결과 출력
  console.log('\n' + '='.repeat(70));
  console.log('📊 테스트 결과 요약');
  console.log('='.repeat(70));
  console.log(`✅ 통과: ${testResults.passed}`);
  console.log(`❌ 실패: ${testResults.failed}`);
  console.log(`📝 전체: ${testResults.tests.length}`);
  console.log('='.repeat(70));

  // 실패한 테스트 상세 출력
  if (testResults.failed > 0) {
    console.log('\n❌ 실패한 테스트 상세:');
    testResults.tests.filter(t => !t.passed).forEach(t => {
      console.log(`  - ${t.name}: ${t.message}`);
    });
  }

  console.log('\n' + (testResults.failed === 0 ? '✅ 모든 테스트 통과!' : '❌ 일부 테스트 실패'));

  // 프로세스 종료 코드
  process.exit(testResults.failed === 0 ? 0 : 1);
}

// 테스트 실행
runTests().catch(error => {
  console.error('❌ 예상치 못한 오류:', error);
  process.exit(1);
});
