/**
 * 실제 API 테스트 - 과거 시간 스케줄 추가 시도
 */
const fetch = require('node-fetch');

async function testPastSchedule() {
  console.log('🧪 실제 API 테스트: 과거 시간 스케줄 추가 시도\n');

  // 1. 먼저 제목 추가
  const titleResponse = await fetch('http://localhost:3000/api/automation/titles', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Cookie': 'sessionId=test_session' // 관리자 세션 필요
    },
    body: JSON.stringify({
      title: '과거 시간 테스트',
      type: 'longform',
      category: '테스트',
      tags: 'test',
      channel: '',
      scriptMode: 'chrome',
      mediaMode: 'imagen3',
      model: 'gpt-4o'
    })
  });

  if (!titleResponse.ok) {
    console.error('❌ 제목 추가 실패:', titleResponse.status);
    const error = await titleResponse.text();
    console.error('에러:', error);
    return;
  }

  const titleData = await titleResponse.json();
  console.log('✅ 제목 추가 성공:', titleData.titleId);

  // 2. 과거 시간으로 스케줄 추가 시도 (5분 전)
  const now = new Date();
  const pastTime = new Date(now.getTime() - 5 * 60 * 1000);
  const year = pastTime.getFullYear();
  const month = String(pastTime.getMonth() + 1).padStart(2, '0');
  const day = String(pastTime.getDate()).padStart(2, '0');
  const hours = String(pastTime.getHours()).padStart(2, '0');
  const minutes = String(pastTime.getMinutes()).padStart(2, '0');
  const scheduledTime = `${year}-${month}-${day}T${hours}:${minutes}`;

  console.log(`\n📅 과거 시간 스케줄 추가 시도: ${scheduledTime}`);
  console.log(`   현재 시간: ${now.toISOString()}`);
  console.log(`   스케줄 시간: ${pastTime.toISOString()}`);

  const scheduleResponse = await fetch('http://localhost:3000/api/automation/schedules', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Cookie': 'sessionId=test_session'
    },
    body: JSON.stringify({
      titleId: titleData.titleId,
      scheduledTime: scheduledTime
    })
  });

  console.log(`\n📡 API 응답 상태: ${scheduleResponse.status}`);

  const scheduleData = await scheduleResponse.json();
  console.log('📦 응답 본문:', JSON.stringify(scheduleData, null, 2));

  if (scheduleResponse.ok) {
    console.log('\n❌❌❌ 버그 발견! 과거 시간 스케줄이 추가되었습니다!');
    console.log('스케줄 ID:', scheduleData.scheduleId);
    process.exit(1);
  } else {
    console.log('\n✅✅✅ 정상 작동! 과거 시간 스케줄이 차단되었습니다!');
    console.log('에러 메시지:', scheduleData.error);
    process.exit(0);
  }
}

testPastSchedule().catch(err => {
  console.error('테스트 실패:', err);
  process.exit(1);
});
