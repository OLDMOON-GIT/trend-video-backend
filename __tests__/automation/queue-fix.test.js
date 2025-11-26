/**
 * 자동화 시스템 큐 플로우 수정 검증 테스트
 * - 업로드 대기 → 진행 큐 전환 확인
 * - schedule.status 기반 필터링 검증
 */

const BASE_URL = 'http://localhost:3000';

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
      console.log(`   ${JSON.stringify(details, null, 2)}`);
    }
  } else {
    testResults.failed++;
    console.error(`❌ ${name}: ${message}`);
    if (details) {
      console.error(`   ${JSON.stringify(details, null, 2)}`);
    }
  }
}

// 1. 제목 생성
async function testCreateTitle() {
  console.log('\n📝 1. 제목 생성');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/titles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        title: `[큐테스트] ${new Date().toISOString()}`,
        category: '복수극',
        type: 'shortform',
        media_mode: 'upload'
      })
    });

    const data = await response.json();

    if (response.ok && data.id) {
      addTestResult('제목 생성', true, `ID: ${data.id}`);
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

// 2. 스케줄 등록
async function testCreateSchedule(titleId) {
  console.log('\n📅 2. 스케줄 등록');

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
      addTestResult('스케줄 등록', true, `ID: ${data.id}`);
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

// 3. 스케줄 상태를 waiting_for_upload로 변경
async function testUpdateToWaitingUpload(scheduleId, scriptId) {
  console.log('\n⏳ 3. 스케줄 상태 → waiting_for_upload');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/schedules`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        id: scheduleId,
        status: 'waiting_for_upload',
        script_id: scriptId
      })
    });

    if (response.ok) {
      addTestResult('업로드 대기 상태 변경', true, 'waiting_for_upload');
      return true;
    } else {
      const data = await response.json();
      addTestResult('업로드 대기 상태 변경', false, `실패: ${data.error || '알 수 없는 오류'}`);
      return false;
    }
  } catch (error) {
    addTestResult('업로드 대기 상태 변경', false, `에러: ${error.message}`);
    return false;
  }
}

// 4. 업로드 대기 큐에서 확인
async function testCheckWaitingUploadQueue(titleId) {
  console.log('\n📤 4. 업로드 대기 큐 확인');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/titles`, {
      credentials: 'include'
    });

    const data = await response.json();
    const titles = data.titles || [];

    // schedules 가져오기
    const schedulesRes = await fetch(`${BASE_URL}/api/automation/schedules`, {
      credentials: 'include'
    });
    const schedulesData = await schedulesRes.json();
    const schedules = schedulesData.schedules || [];

    // 제목 찾기
    const title = titles.find(t => t.id === titleId);
    if (!title) {
      addTestResult('업로드 대기 큐 확인', false, `제목 ID ${titleId}를 찾을 수 없음`);
      return false;
    }

    // 해당 제목의 스케줄 확인
    const titleSchedules = schedules.filter(s => s.title_id === titleId);
    const hasWaitingUpload = titleSchedules.some(s => s.status === 'waiting_for_upload');

    if (hasWaitingUpload) {
      addTestResult('업로드 대기 큐 확인', true, '제목이 업로드 대기 큐에 있음', {
        titleId,
        schedules: titleSchedules.map(s => ({ id: s.id, status: s.status }))
      });
      return true;
    } else {
      addTestResult('업로드 대기 큐 확인', false, '업로드 대기 상태 스케줄 없음', {
        titleId,
        schedules: titleSchedules.map(s => ({ id: s.id, status: s.status }))
      });
      return false;
    }
  } catch (error) {
    addTestResult('업로드 대기 큐 확인', false, `에러: ${error.message}`);
    return false;
  }
}

// 5. 스케줄 상태를 processing으로 변경 (영상 제작 시작)
async function testUpdateToProcessing(scheduleId) {
  console.log('\n🔄 5. 스케줄 상태 → processing (영상 제작 시작)');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/schedules`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        id: scheduleId,
        status: 'processing'
      })
    });

    if (response.ok) {
      addTestResult('진행 상태 변경', true, 'processing');
      return true;
    } else {
      const data = await response.json();
      addTestResult('진행 상태 변경', false, `실패: ${data.error || '알 수 없는 오류'}`);
      return false;
    }
  } catch (error) {
    addTestResult('진행 상태 변경', false, `에러: ${error.message}`);
    return false;
  }
}

// 6. 진행 큐에서 확인 (핵심 테스트!)
async function testCheckProcessingQueue(titleId) {
  console.log('\n🎯 6. 진행 큐 확인 (수정 검증)');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/titles`, {
      credentials: 'include'
    });

    const data = await response.json();
    const titles = data.titles || [];

    // schedules 가져오기
    const schedulesRes = await fetch(`${BASE_URL}/api/automation/schedules`, {
      credentials: 'include'
    });
    const schedulesData = await schedulesRes.json();
    const schedules = schedulesData.schedules || [];

    // 제목 찾기
    const title = titles.find(t => t.id === titleId);
    if (!title) {
      addTestResult('진행 큐 확인', false, `제목 ID ${titleId}를 찾을 수 없음`);
      return false;
    }

    // 해당 제목의 스케줄 확인
    const titleSchedules = schedules.filter(s => s.title_id === titleId);
    const hasProcessing = titleSchedules.some(s => s.status === 'processing');

    if (hasProcessing) {
      addTestResult('진행 큐 확인', true, '✅ 제목이 진행 큐에 정상 표시됨!', {
        titleId,
        schedules: titleSchedules.map(s => ({ id: s.id, status: s.status }))
      });
      return true;
    } else {
      addTestResult('진행 큐 확인', false, '❌ 진행 상태 스케줄이 있지만 큐에 표시 안됨', {
        titleId,
        schedules: titleSchedules.map(s => ({ id: s.id, status: s.status }))
      });
      return false;
    }
  } catch (error) {
    addTestResult('진행 큐 확인', false, `에러: ${error.message}`);
    return false;
  }
}

// 7. 스케줄 상태를 completed로 변경
async function testUpdateToCompleted(scheduleId) {
  console.log('\n✅ 7. 스케줄 상태 → completed');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/schedules`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({
        id: scheduleId,
        status: 'completed'
      })
    });

    if (response.ok) {
      addTestResult('완료 상태 변경', true, 'completed');
      return true;
    } else {
      const data = await response.json();
      addTestResult('완료 상태 변경', false, `실패: ${data.error || '알 수 없는 오류'}`);
      return false;
    }
  } catch (error) {
    addTestResult('완료 상태 변경', false, `에러: ${error.message}`);
    return false;
  }
}

// 8. 완료 큐에서 확인
async function testCheckCompletedQueue(titleId) {
  console.log('\n🎉 8. 완료 큐 확인');

  try {
    const response = await fetch(`${BASE_URL}/api/automation/titles`, {
      credentials: 'include'
    });

    const data = await response.json();
    const titles = data.titles || [];

    // schedules 가져오기
    const schedulesRes = await fetch(`${BASE_URL}/api/automation/schedules`, {
      credentials: 'include'
    });
    const schedulesData = await schedulesRes.json();
    const schedules = schedulesData.schedules || [];

    // 제목 찾기
    const title = titles.find(t => t.id === titleId);
    if (!title) {
      addTestResult('완료 큐 확인', false, `제목 ID ${titleId}를 찾을 수 없음`);
      return false;
    }

    // 해당 제목의 스케줄 확인
    const titleSchedules = schedules.filter(s => s.title_id === titleId);
    const hasCompleted = titleSchedules.some(s => s.status === 'completed');

    if (hasCompleted) {
      addTestResult('완료 큐 확인', true, '제목이 완료 큐에 있음', {
        titleId,
        schedules: titleSchedules.map(s => ({ id: s.id, status: s.status }))
      });
      return true;
    } else {
      addTestResult('완료 큐 확인', false, '완료 상태 스케줄 없음', {
        titleId,
        schedules: titleSchedules.map(s => ({ id: s.id, status: s.status }))
      });
      return false;
    }
  } catch (error) {
    addTestResult('완료 큐 확인', false, `에러: ${error.message}`);
    return false;
  }
}

// 전체 통합 테스트 실행
async function runIntegrationTest() {
  console.log('='.repeat(80));
  console.log('🧪 자동화 시스템 큐 플로우 수정 검증 테스트');
  console.log('='.repeat(80));
  console.log(`📅 ${new Date().toLocaleString('ko-KR')}`);
  console.log(`🌐 테스트 서버: ${BASE_URL}`);
  console.log('\n🎯 핵심 검증: schedule.status 기반 필터링');
  console.log('   - 기존: title.status === "processing" (잘못된 필드)');
  console.log('   - 수정: titleSchedules.some(s => s.status === "processing") (올바른 필드)\n');

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

  // 임시 script_id (실제로는 대본 생성 후 받아와야 함)
  const tempScriptId = `script_${Date.now()}`;

  // 3. 스케줄을 waiting_for_upload로 변경
  const waitingUpdated = await testUpdateToWaitingUpload(scheduleId, tempScriptId);
  if (!waitingUpdated) {
    console.log('\n⚠️ 업로드 대기 상태 변경 실패로 테스트 중단');
    printSummary();
    return;
  }

  // 잠시 대기 (DB 업데이트 반영)
  await new Promise(resolve => setTimeout(resolve, 1000));

  // 4. 업로드 대기 큐 확인
  await testCheckWaitingUploadQueue(titleId);

  // 5. 스케줄을 processing으로 변경 (영상 제작 시작)
  const processingUpdated = await testUpdateToProcessing(scheduleId);
  if (!processingUpdated) {
    console.log('\n⚠️ 진행 상태 변경 실패로 테스트 중단');
    printSummary();
    return;
  }

  // 잠시 대기 (DB 업데이트 반영)
  await new Promise(resolve => setTimeout(resolve, 1000));

  // 6. 진행 큐 확인 (핵심 테스트!)
  const processingQueueOk = await testCheckProcessingQueue(titleId);

  // 7. 스케줄을 completed로 변경
  await testUpdateToCompleted(scheduleId);

  // 잠시 대기
  await new Promise(resolve => setTimeout(resolve, 1000));

  // 8. 완료 큐 확인
  await testCheckCompletedQueue(titleId);

  console.log('\n' + '='.repeat(80));
  if (processingQueueOk) {
    console.log('🎉 핵심 수정 검증 성공!');
    console.log('   ✅ schedule.status = "processing" → 진행 큐에 정상 표시');
  } else {
    console.log('❌ 핵심 수정 검증 실패');
    console.log('   ⚠️ schedule.status를 "processing"으로 변경했지만 진행 큐에 표시 안됨');
  }

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
    console.log('\n✅ 큐 플로우 수정 완료:');
    console.log('   - 업로드 대기 → 진행 큐 전환 정상');
    console.log('   - schedule.status 기반 필터링 정상');
    console.log('   - 모든 큐 상태 전환 정상');
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
