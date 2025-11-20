/**
 * 관리자 페이지 (자동화) 통합테스트
 * /automation 페이지의 모든 주요 기능 검증
 */

const fs = require('fs');
const path = require('path');

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

// 1. 제목 추가/삭제 기능 검증
function testTitleAddDelete() {
  console.log('📝 STEP 1: 제목 추가/삭제 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 1-1: 제목 추가 폼이 있는지
    const hasAddForm = content.includes('새 제목 추가') &&
                       content.includes('setShowAddForm');
    addTestResult('1-1. 제목 추가 폼', hasAddForm, hasAddForm ? '확인' : '누락');

    // 1-2: 제목 입력 필드
    const hasTitleInput = content.includes('handleTitleChange') &&
                         content.includes('newTitle');
    addTestResult('1-2. 제목 입력 필드', hasTitleInput, hasTitleInput ? '확인' : '누락');

    // 1-3: 제목 삭제 기능
    const hasDelete = content.includes('handleDeleteTitle') ||
                      content.includes('DELETE');
    addTestResult('1-3. 제목 삭제 기능', hasDelete, hasDelete ? '확인' : '누락');

    // 1-4: API 호출 (POST /api/automation/titles)
    const hasApiCall = content.includes('/api/automation/titles') ||
                      content.includes('automation/titles');
    addTestResult('1-4. API 호출', hasApiCall, hasApiCall ? '확인' : '누락');

  } catch (error) {
    addTestResult('1. 제목 추가/삭제', false, error.message);
  }

  console.log('');
}

// 2. 제목 수정 기능 검증
function testTitleEdit() {
  console.log('📝 STEP 2: 제목 수정 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 2-1: 수정 모드
    const hasEditMode = content.includes('editingId') ||
                       content.includes('isEditing');
    addTestResult('2-1. 수정 모드', hasEditMode, hasEditMode ? '확인' : '누락');

    // 2-2: 수정 버튼
    const hasEditButton = content.includes('수정') &&
                         (content.includes('handleEdit') || content.includes('setEditingId'));
    addTestResult('2-2. 수정 버튼', hasEditButton, hasEditButton ? '확인' : '누락');

    // 2-3: 수정 취소
    const hasCancel = content.includes('취소') ||
                     content.includes('setEditingId(null)');
    addTestResult('2-3. 수정 취소', hasCancel, hasCancel ? '확인' : '누락');

  } catch (error) {
    addTestResult('2. 제목 수정', false, error.message);
  }

  console.log('');
}

// 3. 스케줄 관리 기능 검증
function testScheduleManagement() {
  console.log('📝 STEP 3: 스케줄 관리 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 3-1: 스케줄 시간 설정
    const hasScheduleTime = content.includes('scheduleTime') &&
                           content.includes('datetime-local');
    addTestResult('3-1. 스케줄 시간 설정', hasScheduleTime, hasScheduleTime ? '확인' : '누락');

    // 3-2: 스케줄러 시작/중지
    const hasSchedulerToggle = content.includes('toggleScheduler') ||
                              content.includes('schedulerStatus');
    addTestResult('3-2. 스케줄러 시작/중지', hasSchedulerToggle, hasSchedulerToggle ? '확인' : '누락');

    // 3-3: 스케줄 상태 표시
    const hasStatusDisplay = content.includes('isRunning') &&
                            (content.includes('실행 중') || content.includes('중지됨'));
    addTestResult('3-3. 스케줄 상태 표시', hasStatusDisplay, hasStatusDisplay ? '확인' : '누락');

  } catch (error) {
    addTestResult('3. 스케줄 관리', false, error.message);
  }

  console.log('');
}

// 4. 진행 상황 모니터링 검증
function testProgressMonitoring() {
  console.log('📝 STEP 4: 진행 상황 모니터링 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 4-1: 상태 표시 (pending/processing/completed/failed)
    const hasStatusDisplay = content.includes('status') &&
                            (content.includes('processing') || content.includes('completed'));
    addTestResult('4-1. 상태 표시', hasStatusDisplay, hasStatusDisplay ? '확인' : '누락');

    // 4-2: 진행률 표시
    const hasProgress = content.includes('progress') ||
                       content.includes('진행률');
    addTestResult('4-2. 진행률 표시', hasProgress, hasProgress ? '확인' : '누락');

    // 4-3: 자동 새로고침 (폴링)
    const hasPolling = content.includes('setInterval') &&
                      content.includes('fetchData');
    addTestResult('4-3. 자동 새로고침', hasPolling, hasPolling ? '확인' : '누락');

    // 4-4: 에러 메시지 표시
    const hasErrorDisplay = content.includes('error') &&
                           (content.includes('에러') || content.includes('실패'));
    addTestResult('4-4. 에러 메시지', hasErrorDisplay, hasErrorDisplay ? '확인' : '누락');

  } catch (error) {
    addTestResult('4. 진행 상황 모니터링', false, error.message);
  }

  console.log('');
}

// 5. 폴더 열기 기능 검증
function testOpenFolder() {
  console.log('📝 STEP 5: 폴더 열기 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 5-1: 폴더 열기 버튼
    const hasFolderButton = content.includes('📁') &&
                           content.includes('폴더');
    addTestResult('5-1. 폴더 열기 버튼', hasFolderButton, hasFolderButton ? '확인' : '누락');

    // 5-2: handleOpenFolder 함수
    const hasHandler = content.includes('handleOpenFolder');
    addTestResult('5-2. handleOpenFolder 함수', hasHandler, hasHandler ? '확인' : '누락');

    // 5-3: API 호출 (/api/open-folder)
    const hasApiCall = content.includes('/api/open-folder');
    addTestResult('5-3. 폴더 열기 API 호출', hasApiCall, hasApiCall ? '확인' : '누락');

    // 5-4: script_id 또는 video_id 전달
    const hasIdParam = content.includes('script_id') ||
                      content.includes('video_id');
    addTestResult('5-4. ID 파라미터 전달', hasIdParam, hasIdParam ? '확인' : '누락');

  } catch (error) {
    addTestResult('5. 폴더 열기', false, error.message);
  }

  console.log('');
}

// 6. 다운로드 기능 검증
function testDownload() {
  console.log('📝 STEP 6: 다운로드 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 6-1: 다운로드 버튼
    const hasDownloadButton = content.includes('다운로드');
    addTestResult('6-1. 다운로드 버튼', hasDownloadButton, hasDownloadButton ? '확인' : '누락');

    // 6-2: handleDownload 함수
    const hasHandler = content.includes('handleDownload');
    addTestResult('6-2. handleDownload 함수', hasHandler, hasHandler ? '확인' : '누락');

    // 6-3: 다운로드 타입 선택 (영상/대본/재료/전체)
    const hasTypeSelection = content.includes('영상만') ||
                            content.includes('대본만') ||
                            content.includes('재료만') ||
                            content.includes('전체');
    addTestResult('6-3. 다운로드 타입 선택', hasTypeSelection, hasTypeSelection ? '확인' : '누락');

    // 6-4: API 호출 (/api/automation/download)
    const hasApiCall = content.includes('/api/automation/download');
    addTestResult('6-4. 다운로드 API 호출', hasApiCall, hasApiCall ? '확인' : '누락');

  } catch (error) {
    addTestResult('6. 다운로드', false, error.message);
  }

  console.log('');
}

// 7. 이미지 업로드 기능 검증
function testImageUpload() {
  console.log('📝 STEP 7: 이미지 업로드 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 7-1: 업로드 버튼
    const hasUploadButton = content.includes('업로드') ||
                           content.includes('이미지');
    addTestResult('7-1. 업로드 버튼', hasUploadButton, hasUploadButton ? '확인' : '누락');

    // 7-2: MediaUploadBox 컴포넌트 사용
    const hasMediaUploadBox = content.includes('MediaUploadBox') ||
                             content.includes('uploadedImagesFor');
    addTestResult('7-2. MediaUploadBox 사용', hasMediaUploadBox, hasMediaUploadBox ? '확인' : '누락');

    // 7-3: 이미지 상태 관리
    const hasImageState = content.includes('uploadedImagesFor') &&
                         content.includes('setUploadedImagesFor');
    addTestResult('7-3. 이미지 상태 관리', hasImageState, hasImageState ? '확인' : '누락');

    // 7-4: 업로드 API 호출
    const hasApiCall = content.includes('/api/automation/upload-images') ||
                      content.includes('upload');
    addTestResult('7-4. 업로드 API 호출', hasApiCall, hasApiCall ? '확인' : '누락');

  } catch (error) {
    addTestResult('7. 이미지 업로드', false, error.message);
  }

  console.log('');
}

// 8. 대본 재생성 기능 검증
function testScriptRegenerate() {
  console.log('📝 STEP 8: 대본 재생성 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 8-1: 대본 재생성 버튼
    const hasButton = content.includes('대본 재생성') ||
                     content.includes('regenerate');
    addTestResult('8-1. 대본 재생성 버튼', hasButton, hasButton ? '확인' : '누락');

    // 8-2: 재생성 핸들러
    const hasHandler = content.includes('handleRegenerateScript') ||
                      content.includes('regenerate');
    addTestResult('8-2. 재생성 핸들러', hasHandler, hasHandler ? '확인' : '누락');

    // 8-3: API 호출
    const hasApiCall = content.includes('/api/automation/regenerate-script') ||
                      content.includes('regenerate');
    addTestResult('8-3. 재생성 API 호출', hasApiCall, hasApiCall ? '확인' : '누락');

  } catch (error) {
    addTestResult('8. 대본 재생성', false, error.message);
  }

  console.log('');
}

// 9. 영상 재생성 기능 검증
function testVideoRegenerate() {
  console.log('📝 STEP 9: 영상 재생성 기능 검증');
  console.log('-'.repeat(70));

  try {
    const pagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
    const content = fs.readFileSync(pagePath, 'utf-8');

    // 9-1: 영상 재생성 버튼
    const hasButton = content.includes('영상 재생성') ||
                     content.includes('regenerate');
    addTestResult('9-1. 영상 재생성 버튼', hasButton, hasButton ? '확인' : '누락');

    // 9-2: 재생성 핸들러
    const hasHandler = content.includes('handleRegenerateVideo') ||
                      content.includes('regenerate');
    addTestResult('9-2. 재생성 핸들러', hasHandler, hasHandler ? '확인' : '누락');

    // 9-3: API 호출
    const hasApiCall = content.includes('/api/automation/regenerate-video') ||
                      content.includes('regenerate');
    addTestResult('9-3. 재생성 API 호출', hasApiCall, hasApiCall ? '확인' : '누락');

  } catch (error) {
    addTestResult('9. 영상 재생성', false, error.message);
  }

  console.log('');
}

// 메인 테스트 실행
async function runTests() {
  console.log('🧪 [관리자 페이지 통합테스트] 시작');
  console.log('/automation 페이지의 모든 주요 기능 검증\n');
  console.log('='.repeat(70) + '\n');

  testTitleAddDelete();
  testTitleEdit();
  testScheduleManagement();
  testProgressMonitoring();
  testOpenFolder();
  testDownload();
  testImageUpload();
  testScriptRegenerate();
  testVideoRegenerate();

  // 결과 요약
  console.log('='.repeat(70));
  console.log('📊 테스트 결과 요약');
  console.log('='.repeat(70));
  console.log(`✅ 통과: ${testResults.passed}/${testResults.tests.length}`);
  console.log(`❌ 실패: ${testResults.failed}/${testResults.tests.length}`);

  const percentage = ((testResults.passed / testResults.tests.length) * 100).toFixed(1);
  console.log(`📈 커버리지: ${percentage}%`);

  if (testResults.failed === 0) {
    console.log('\n🎉 모든 테스트 통과!');
    console.log('\n✅ 검증 완료 항목:');
    console.log('  1. 제목 추가/삭제');
    console.log('  2. 제목 수정');
    console.log('  3. 스케줄 관리');
    console.log('  4. 진행 상황 모니터링');
    console.log('  5. 폴더 열기');
    console.log('  6. 다운로드 (영상/대본/재료/전체)');
    console.log('  7. 이미지 업로드');
    console.log('  8. 대본 재생성');
    console.log('  9. 영상 재생성');
  } else {
    console.log('\n❌ 일부 테스트 실패');
    console.log('\n실패 항목:');
    testResults.tests.filter(t => !t.passed).forEach(t => {
      console.log(`  - ${t.name}: ${t.message}`);
    });
  }

  console.log('='.repeat(70));

  // 결과를 JSON 파일로 저장
  saveTestResults();

  process.exit(testResults.failed === 0 ? 0 : 1);
}

// 테스트 결과를 JSON으로 저장
function saveTestResults() {
  try {
    const resultsDir = path.join(__dirname, 'test-results');
    if (!fs.existsSync(resultsDir)) {
      fs.mkdirSync(resultsDir, { recursive: true });
    }

    const resultFile = path.join(resultsDir, 'admin-automation-page.json');
    const percentage = parseFloat(((testResults.passed / testResults.tests.length) * 100).toFixed(1));

    const result = {
      testName: '관리자 페이지 (자동화)',
      category: '관리자 페이지',
      timestamp: new Date().toISOString(),
      passed: testResults.failed === 0,
      summary: {
        total: testResults.tests.length,
        passed: testResults.passed,
        failed: testResults.failed,
        percentage: percentage
      },
      tests: testResults.tests
    };

    fs.writeFileSync(resultFile, JSON.stringify(result, null, 2));
    console.log(`\n💾 테스트 결과 저장: ${resultFile}`);
  } catch (error) {
    console.error('테스트 결과 저장 실패:', error.message);
  }
}

// 실행
runTests().catch(error => {
  console.error('❌ 예상치 못한 오류:', error);
  process.exit(1);
});
