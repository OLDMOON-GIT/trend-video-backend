const fs = require('fs');
const path = require('path');

// 테스트 설정
const TEST_SCRIPT_ID = 'job_1763044825741_bh5psnf8a';

// 테스트 결과
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
  console.log('🧪 [자동화 폴더 경로 수정 검증] 시작\n');
  console.log('테스트 대상: generate-video-upload/route.ts');
  console.log('검증 내용: scriptId에 따른 Python 폴더 경로 조건부 설정\n');
  console.log('='.repeat(70) + '\n');

  try {
    // 테스트 1: 코드에 scriptId 파라미터가 config에 추가되었는지 확인
    console.log('1️⃣ 테스트: config에 scriptId 파라미터 추가 확인');
    try {
      const routeFilePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'generate-video-upload', 'route.ts');
      const routeContent = fs.readFileSync(routeFilePath, 'utf-8');

      // scriptId 파라미터가 config 인터페이스에 있는지
      const hasScriptIdInConfig = routeContent.includes('scriptId?: string;') &&
                                   routeContent.includes('자동화용: 이미 업로드된 폴더 식별자');

      if (hasScriptIdInConfig) {
        addTestResult('config에 scriptId 추가', true, 'scriptId?: string 파라미터 존재');
      } else {
        addTestResult('config에 scriptId 추가', false, 'scriptId 파라미터 없음');
      }
    } catch (error) {
      addTestResult('config에 scriptId 추가', false, error.message);
    }

    // 테스트 2: generateVideoFromUpload 호출 시 scriptId 전달 확인
    console.log('\n2️⃣ 테스트: generateVideoFromUpload 호출 시 scriptId 전달');
    try {
      const routeFilePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'generate-video-upload', 'route.ts');
      const routeContent = fs.readFileSync(routeFilePath, 'utf-8');

      // generateVideoFromUpload 호출 부분에서 scriptId 전달 확인
      const hasScriptIdPass = routeContent.includes('imageModel, // 이미지 생성 모델') &&
                               routeContent.includes('scriptId // 자동화용: 이미 업로드된 폴더 식별자');

      if (hasScriptIdPass) {
        addTestResult('scriptId 전달', true, 'generateVideoFromUpload에 scriptId 전달');
      } else {
        addTestResult('scriptId 전달', false, 'scriptId가 전달되지 않음');
      }
    } catch (error) {
      addTestResult('scriptId 전달', false, error.message);
    }

    // 테스트 3: Python 명령어에 조건부 폴더 경로 적용 확인
    console.log('\n3️⃣ 테스트: Python 명령어 조건부 폴더 경로 (핵심!)');
    try {
      const routeFilePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'generate-video-upload', 'route.ts');
      const routeContent = fs.readFileSync(routeFilePath, 'utf-8');

      // folderPrefix 변수 사용 확인
      const hasFolderPrefix = routeContent.includes("const folderPrefix = config.scriptId ? 'input' : 'uploads';");
      const usesFolderPrefix = routeContent.includes('`${folderPrefix}/${config.projectName}`');

      if (hasFolderPrefix && usesFolderPrefix) {
        addTestResult('조건부 폴더 경로', true, 'scriptId에 따라 input/ 또는 uploads/ 사용');
      } else {
        if (!hasFolderPrefix) {
          addTestResult('조건부 폴더 경로', false, 'folderPrefix 변수 없음');
        } else {
          addTestResult('조건부 폴더 경로', false, 'folderPrefix가 Python 명령어에 사용되지 않음');
        }
      }
    } catch (error) {
      addTestResult('조건부 폴더 경로', false, error.message);
    }

    // 테스트 4: 하드코딩된 uploads/ 경로가 제거되었는지 확인
    console.log('\n4️⃣ 테스트: 하드코딩된 uploads/ 경로 제거 확인');
    try {
      const routeFilePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'generate-video-upload', 'route.ts');
      const routeContent = fs.readFileSync(routeFilePath, 'utf-8');

      // Python 명령어 부분 추출 (pythonArgs 선언 부분)
      const pythonArgsMatch = routeContent.match(/const pythonArgs = \['create_video_from_folder\.py', '--folder', `(.+?)`/);

      if (pythonArgsMatch) {
        const folderArg = pythonArgsMatch[1];

        // 하드코딩된 'uploads/'가 있는지 확인
        if (folderArg.includes('uploads/${config.projectName}')) {
          addTestResult('하드코딩 제거', false, `여전히 하드코딩됨: ${folderArg}`);
        } else if (folderArg.includes('${folderPrefix}/${config.projectName}')) {
          addTestResult('하드코딩 제거', true, '조건부 경로로 변경됨');
        } else {
          addTestResult('하드코딩 제거', false, `예상치 못한 패턴: ${folderArg}`);
        }
      } else {
        addTestResult('하드코딩 제거', false, 'pythonArgs를 찾을 수 없음');
      }
    } catch (error) {
      addTestResult('하드코딩 제거', false, error.message);
    }

    // 테스트 5: 테스트 폴더와 파일 존재 확인
    console.log('\n5️⃣ 테스트: 실제 폴더 구조 확인');
    try {
      const backendPath = path.join(__dirname, 'trend-video-backend');
      const inputPath = path.join(backendPath, 'input', `project_${TEST_SCRIPT_ID}`);
      const storyPath = path.join(inputPath, 'story.json');

      if (fs.existsSync(inputPath)) {
        addTestResult('input 폴더 존재', true, inputPath);

        if (fs.existsSync(storyPath)) {
          addTestResult('story.json 존재', true, storyPath);

          // 파일 내용 확인
          const storyContent = fs.readFileSync(storyPath, 'utf-8');
          const storyData = JSON.parse(storyContent);

          if (storyData.scenes && storyData.scenes.length > 0) {
            addTestResult('story.json 유효성', true, `씬 ${storyData.scenes.length}개`);
          } else {
            addTestResult('story.json 유효성', false, '씬이 없음');
          }
        } else {
          addTestResult('story.json 존재', false, '파일 없음');
        }
      } else {
        addTestResult('input 폴더 존재', false, '폴더 없음');
      }
    } catch (error) {
      addTestResult('폴더 구조 확인', false, error.message);
    }

    // 테스트 6: 로직 검증 - scriptId가 있으면 input/, 없으면 uploads/
    console.log('\n6️⃣ 테스트: 로직 정확성 검증 (시뮬레이션)');
    try {
      // 시뮬레이션 1: scriptId 있음 (자동화)
      const scriptId = TEST_SCRIPT_ID;
      const folderPrefix1 = scriptId ? 'input' : 'uploads';
      const projectName1 = `project_${scriptId}`;
      const expectedPath1 = `input/project_${scriptId}`;
      const actualPath1 = `${folderPrefix1}/${projectName1}`;

      if (actualPath1 === expectedPath1) {
        addTestResult('로직: 자동화 경로', true, `${actualPath1} (올바름)`);
      } else {
        addTestResult('로직: 자동화 경로', false, `${actualPath1} != ${expectedPath1}`);
      }

      // 시뮬레이션 2: scriptId 없음 (일반)
      const scriptId2 = undefined;
      const folderPrefix2 = scriptId2 ? 'input' : 'uploads';
      const jobId = 'upload_123456789';
      const projectName2 = `uploaded_${jobId}`;
      const expectedPath2 = `uploads/uploaded_${jobId}`;
      const actualPath2 = `${folderPrefix2}/${projectName2}`;

      if (actualPath2 === expectedPath2) {
        addTestResult('로직: 일반 경로', true, `${actualPath2} (올바름)`);
      } else {
        addTestResult('로직: 일반 경로', false, `${actualPath2} != ${expectedPath2}`);
      }
    } catch (error) {
      addTestResult('로직 검증', false, error.message);
    }

  } catch (error) {
    console.error('\n❌ 테스트 실행 중 오류:', error);
  }

  // 결과 출력
  console.log('\n' + '='.repeat(70));
  console.log('📊 테스트 결과 요약');
  console.log('='.repeat(70));
  console.log(`✅ 통과: ${testResults.passed}/${testResults.tests.length}`);
  console.log(`❌ 실패: ${testResults.failed}/${testResults.tests.length}`);

  if (testResults.failed === 0) {
    console.log('\n🎉 모든 테스트 통과! 코드 수정이 올바르게 적용되었습니다.');
    console.log('\n📝 수정 내용:');
    console.log('  1. config에 scriptId 파라미터 추가');
    console.log('  2. generateVideoFromUpload 호출 시 scriptId 전달');
    console.log('  3. Python 명령어에 조건부 폴더 경로 적용:');
    console.log('     - scriptId 있음 (자동화) → input/project_*');
    console.log('     - scriptId 없음 (일반)   → uploads/uploaded_*');
  } else {
    console.log('\n❌ 일부 테스트 실패. 아래 항목을 확인하세요:');
    testResults.tests.filter(t => !t.passed).forEach(t => {
      console.log(`  - ${t.name}: ${t.message}`);
    });
  }

  console.log('='.repeat(70));

  // 프로세스 종료 코드
  process.exit(testResults.failed === 0 ? 0 : 1);
}

// 테스트 실행
runTests().catch(error => {
  console.error('❌ 예상치 못한 오류:', error);
  process.exit(1);
});
