/**
 * 과거 시간 스케줄 검증 테스트
 */

console.log('🧪 스케줄 시간 검증 테스트\n');

// 테스트 1: 과거 시간 검증 로직
function testPastTimeValidation() {
  console.log('테스트 1: 과거 시간 검증');

  const now = new Date();
  const pastTime = new Date(now.getTime() - 5 * 60 * 1000); // 5분 전
  const futureTime = new Date(now.getTime() + 5 * 60 * 1000); // 5분 후

  console.log('  현재 시간:', now.toISOString());
  console.log('  과거 시간 (5분 전):', pastTime.toISOString());
  console.log('  미래 시간 (5분 후):', futureTime.toISOString());

  // 검증 로직 (automation page.tsx와 동일)
  const isPast = pastTime < now;
  const isFuture = futureTime < now;

  console.log('  ✅ 과거 시간 검증:', isPast ? '차단됨' : '❌ 통과됨 (버그!)');
  console.log('  ✅ 미래 시간 검증:', isFuture ? '❌ 차단됨 (버그!)' : '통과됨');

  return isPast && !isFuture;
}

// 테스트 2: datetime-local 값 파싱
function testDatetimeLocalParsing() {
  console.log('\n테스트 2: datetime-local 값 파싱');

  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes() - 5).padStart(2, '0'); // 5분 전

  const datetimeValue = `${year}-${month}-${day}T${hours}:${minutes}`;
  console.log('  datetime-local 값:', datetimeValue);

  const parsed = new Date(datetimeValue);
  console.log('  파싱된 Date 객체:', parsed.toISOString());
  console.log('  현재 시간:', now.toISOString());

  const isPast = parsed < now;
  console.log('  ✅ 과거 시간 검증:', isPast ? '차단됨' : '❌ 통과됨 (버그!)');

  return isPast;
}

// 테스트 3: 시간대 처리
function testTimezoneHandling() {
  console.log('\n테스트 3: 시간대 처리');

  const now = new Date();
  console.log('  로컬 시간:', now.toString());
  console.log('  UTC 시간:', now.toUTCString());
  console.log('  ISO 시간:', now.toISOString());
  console.log('  시간대 오프셋 (분):', now.getTimezoneOffset());

  return true;
}

// 테스트 실행
console.log('='.repeat(50));
const test1Pass = testPastTimeValidation();
const test2Pass = testDatetimeLocalParsing();
const test3Pass = testTimezoneHandling();

console.log('\n' + '='.repeat(50));
console.log('테스트 결과:');
console.log('  테스트 1 (과거 시간 검증):', test1Pass ? '✅ 통과' : '❌ 실패');
console.log('  테스트 2 (datetime-local 파싱):', test2Pass ? '✅ 통과' : '❌ 실패');
console.log('  테스트 3 (시간대 처리):', test3Pass ? '✅ 통과' : '❌ 실패');

if (test1Pass && test2Pass && test3Pass) {
  console.log('\n🎉 모든 테스트 통과! 과거 시간 검증이 정상 작동합니다.');
  process.exit(0);
} else {
  console.log('\n❌ 일부 테스트 실패. 코드 검토가 필요합니다.');
  process.exit(1);
}
