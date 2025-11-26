/**
 * 자동화 시스템 큐 플로우 통합 테스트
 * - 대기 → 대본생성 → 업로드대기 → 진행 → 완료/실패 전체 플로우 검증
 */

const BASE_URL = 'http://localhost:3000';
const TEST_USER_EMAIL = 'test@example.com';

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

// 1. 제목 생성 테스트
async function testCreateTitle() {
  console.log('\n📝 1. 제목 생성 테스트');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/titles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        title: `[테스트] 자동화 큐 플로우 ${new Date().toISOString()}`,
        category: '복수극',
        type: 'shortform',
        media_mode: 'upload'
      })
    });

    const data = await response.json();

    if (response.ok && data.id) {
      addTestResult('제목 생성', true, `제목 ID: ${data.id}`);
      return data.id;
    } else {
      addTestResult('제목 생성', false, `실패: ${data.error || '알 수 없는 오류'}`);
      return null;
    }
  } catch (error) {
    addTestResult('제목 생성', false, `에러: ${error.message}`);
    return null;
  }
}

// 2. 스케줄 등록 테스트
async function testCreateSchedule(titleId) {
  console.log('\n📅 2. 스케줄 등록 테스트');

  try {
    const scheduleTime = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

    const response = await fetch(`${BASE_URL}/api/automation/schedules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        title_id: titleId,
        scheduled_time: scheduleTime
      })
    });

    const data = await response.json();

    if (response.ok && data.id) {
      addTestResult('스케줄 등록', true, `스케줄 ID: ${data.id}`);
      return data.id;
    } else {
      addTestResult('스케줄 등록', false, `실패: ${data.error || '알 수 없는 오류'}`);
      return null;
    }
  } catch (error) {
    addTestResult('스케줄 등록', false, `에러: ${error.message}`);
    return null;
  }
}

// 3. 대본 생성 시작 테스트
async function testStartScriptGeneration(scheduleId) {
  console.log('\n✍️ 3. 대본 생성 시작 테스트');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/generate-script`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        scheduleId: scheduleId
      })
    });

    const data = await response.json();

    if (response.ok && data.scriptId) {
      addTestResult('대본 생성 시작', true, `대본 ID: ${data.scriptId}`);
      return data.scriptId;
    } else {
      addTestResult('대본 생성 시작', false, `실패: ${data.error || '알 수 없는 오류'}`);
      return null;
    }
  } catch (error) {
    addTestResult('대본 생성 시작', false, `에러: ${error.message}`);
    return null;
  }
}

// 4. 대본 생성 완료 대기 테스트
async function testWaitForScriptCompletion(scriptId, maxWaitSeconds = 60) {
  console.log('\n⏳ 4. 대본 생성 완료 대기 테스트');

  const startTime = Date.now();

  while ((Date.now() - startTime) < maxWaitSeconds * 1000) {
    try {
      const response = await fetch(`${BASE_URL}/api/scripts/${scriptId}`, {
        credentials: 'include'
      });

      const data = await response.json();

      if (data.status === 'completed') {
        addTestResult('대본 생성 완료', true, `${((Date.now() - startTime) / 1000).toFixed(1)}초 소요`);
        return true;
      } else if (data.status === 'failed') {
        addTestResult('대본 생성 완료', false, `대본 생성 실패: ${data.error || '알 수 없는 오류'}`);
        return false;
      }

      // 2초 대기
      await new Promise(resolve => setTimeout(resolve, 2000));
    } catch (error) {
      addTestResult('대본 생성 완료', false, `에러: ${error.message}`);
      return false;
    }
  }

  addTestResult('대본 생성 완료', false, `타임아웃 (${maxWaitSeconds}초 초과)`);
  return false;
}

// 5. 스케줄 상태 확인 테스트
async function testScheduleStatus(scheduleId, expectedStatus) {
  console.log(`\n🔍 5. 스케줄 상태 확인 테스트 (기대: ${expectedStatus})`);

  try {
    const response = await fetch(`${BASE_URL}/api/automation/schedules/${scheduleId}`, {
      credentials: 'include'
    });

    const data = await response.json();

    if (response.ok && data.status === expectedStatus) {
      addTestResult('스케줄 상태 확인', true, `상태: ${data.status}`);
      return true;
    } else {
      addTestResult('스케줄 상태 확인', false, `기대: ${expectedStatus}, 실제: ${data.status || '없음'}`);
      return false;
    }
  } catch (error) {
    addTestResult('스케줄 상태 확인', false, `에러: ${error.message}`);
    return false;
  }
}

// 6. 제목 큐 상태 확인 테스트
async function testTitleInQueue(titleId, queueName) {
  console.log(`\n📊 6. 제목 큐 확인 테스트 (큐: ${queueName})`);

  try {
    const response = await fetch(`${BASE_URL}/api/automation/titles`, {
      credentials: 'include'
    });

    const data = await response.json();
    const titles = data.titles || [];

    const title = titles.find(t => t.id === titleId);

    if (!title) {
      addTestResult('제목 큐 확인', false, `제목 ID ${titleId}를 찾을 수 없음`);
      return false;
    }

    const queueStatusMap = {
      'waiting': ['waiting', 'pending'],
      'processing': ['processing'],
      'waiting_upload': ['waiting_for_upload'],
      'failed': ['failed'],
      'completed': ['completed']
    };

    const expectedStatuses = queueStatusMap[queueName] || [queueName];

    if (expectedStatuses.includes(title.status)) {
      addTestResult('제목 큐 확인', true, `제목이 ${queueName} 큐에 있음 (상태: ${title.status})`);
      return true;
    } else {
      addTestResult('제목 큐 확인', false, `기대 큐: ${queueName}, 실제 상태: ${title.status}`);
      return false;
    }
  } catch (error) {
    addTestResult('제목 큐 확인', false, `에러: ${error.message}`);
    return false;
  }
}

// 전체 통합 테스트 실행
async function runIntegrationTest() {
  console.log('='.repeat(80));
  console.log('🧪 자동화 시스템 큐 플로우 통합 테스트');
  console.log('='.repeat(80));
  console.log(`📅 ${new Date().toLocaleString('ko-KR')}`);
  console.log(`🌐 테스트 서버: ${BASE_URL}`);

  // 1. 제목 생성
  const titleId = await testCreateTitle();
  if (!titleId) {
    console.log('\n⚠️ 제목 생성 실패로 테스트 중단');
    printSummary();
    return;
  }

  // 2. 스케줄 등록
  const scheduleId = await testCreateSchedule(titleId);
  if (!scheduleId) {
    console.log('\n⚠️ 스케줄 등록 실패로 테스트 중단');
    printSummary();
    return;
  }

  // 3. 대기 큐 확인
  await new Promise(resolve => setTimeout(resolve, 1000));
  await testTitleInQueue(titleId, 'waiting');

  // 4. 대본 생성 시작
  const scriptId = await testStartScriptGeneration(scheduleId);
  if (!scriptId) {
    console.log('\n⚠️ 대본 생성 시작 실패로 테스트 중단');
    printSummary();
    return;
  }

  // 5. 대본 생성 완료 대기
  const scriptCompleted = await testWaitForScriptCompletion(scriptId, 120);
  if (!scriptCompleted) {
    console.log('\n⚠️ 대본 생성 완료 실패로 테스트 중단');
    printSummary();
    return;
  }

  // 6. 업로드 대기 큐 확인
  await new Promise(resolve => setTimeout(resolve, 2000));
  await testTitleInQueue(titleId, 'waiting_upload');
  await testScheduleStatus(scheduleId, 'waiting_for_upload');

  console.log('\n✅ 기본 플로우 테스트 완료!');
  console.log('\n📝 다음 단계 (수동):');
  console.log('  1. 자동화 페이지에서 업로드 대기 큐 확인');
  console.log('  2. 미디어 업로드 후 진행 큐로 이동 확인');
  console.log('  3. 영상 제작 완료 후 완료/실패 큐 이동 확인');

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
runIntegrationTest().catch(error => {
  console.error('테스트 실행 중 오류:', error);
  process.exit(1);
});
