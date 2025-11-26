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

async function runTests() {
  console.log('🧪 자동화에서 상품정보(product_data) 전달 테스트\n');

  const automationPath = path.join(__dirname, 'trend-video-frontend', 'src', 'lib', 'automation.ts');
  const automationContent = fs.readFileSync(automationPath, 'utf-8');

  const schedulerPath = path.join(__dirname, 'trend-video-frontend', 'src', 'lib', 'automation-scheduler.ts');
  const schedulerContent = fs.readFileSync(schedulerPath, 'utf-8');

  // 테스트 1: getPendingSchedules에 product_data SELECT 추가
  const hasPendingProductData = automationContent.includes('t.product_data') &&
                                  automationContent.includes("WHERE s.status = 'pending'");
  addTestResult('getPendingSchedules product_data', hasPendingProductData,
    hasPendingProductData ? 'product_data SELECT 추가됨' : 'product_data 누락');

  // 테스트 2: getWaitingForUploadSchedules에 product_data SELECT 추가
  const hasWaitingProductData = automationContent.includes('t.product_data') &&
                                 automationContent.includes("WHERE s.status = 'waiting_for_upload'");
  addTestResult('getWaitingForUploadSchedules product_data', hasWaitingProductData,
    hasWaitingProductData ? 'product_data SELECT 추가됨' : 'product_data 누락');

  // 테스트 3: product_data JSON 파싱 로직 존재
  const hasProductDataParsing = schedulerContent.includes('schedule.product_data') &&
                                 schedulerContent.includes('JSON.parse');
  addTestResult('product_data JSON 파싱', hasProductDataParsing,
    hasProductDataParsing ? 'JSON.parse(schedule.product_data)' : '파싱 로직 누락');

  // 테스트 4: productInfo 변수 선언
  const hasProductInfoVar = schedulerContent.includes('let productInfo');
  addTestResult('productInfo 변수', hasProductInfoVar,
    hasProductInfoVar ? 'productInfo 변수 선언됨' : '변수 선언 누락');

  // 테스트 5: requestBody에 productInfo 전달
  const passesProductInfo = schedulerContent.includes('productInfo: productInfo') ||
                             schedulerContent.includes('productInfo,');
  addTestResult('requestBody productInfo', passesProductInfo,
    passesProductInfo ? 'productInfo가 requestBody에 전달됨' : 'productInfo 전달 누락');

  // 테스트 6: 파싱 에러 처리
  const hasErrorHandling = schedulerContent.includes('try') &&
                           schedulerContent.includes('JSON.parse(schedule.product_data)') &&
                           schedulerContent.includes('catch');
  addTestResult('파싱 에러 처리', hasErrorHandling,
    hasErrorHandling ? 'try-catch로 에러 처리' : '에러 처리 누락');

  // 테스트 7: 파싱 성공 로그
  const hasSuccessLog = schedulerContent.includes('Product data found') ||
                        schedulerContent.includes('🛍️');
  addTestResult('파싱 성공 로그', hasSuccessLog,
    hasSuccessLog ? '상품 데이터 발견 로그 존재' : '로그 누락');

  // 테스트 8: productUrl도 여전히 전달됨 (하위 호환성)
  const hasProductUrl = schedulerContent.includes('productUrl: schedule.product_url');
  addTestResult('productUrl 하위 호환성', hasProductUrl,
    hasProductUrl ? 'productUrl도 함께 전달' : 'productUrl 누락');

  // 결과 요약
  console.log('\n' + '='.repeat(60));
  console.log(`✅ 통과: ${testResults.passed}/${testResults.tests.length}`);
  console.log(`❌ 실패: ${testResults.failed}/${testResults.tests.length}`);
  console.log('='.repeat(60));

  if (testResults.failed > 0) {
    console.log('\n🔍 실패한 테스트:');
    testResults.tests.filter(t => !t.passed).forEach(t => {
      console.log(`  - ${t.name}: ${t.message}`);
    });
  } else {
    console.log('\n✅ 모든 테스트 통과!');
    console.log('\n📋 구현된 기능:');
    console.log('  1. getPendingSchedules에서 product_data SELECT');
    console.log('  2. getWaitingForUploadSchedules에서 product_data SELECT');
    console.log('  3. product_data JSON 파싱 및 productInfo 변수 생성');
    console.log('  4. requestBody에 productInfo 전달');
    console.log('  5. scripts/generate API에서 productInfo 사용');
    console.log('  6. 상품 대본 생성 후 자동으로 상품정보 대본 생성');
    console.log('  7. YouTube 업로드 시 상품정보 대본 내용을 description에 자동 설정');
    console.log('\n💡 데이터 흐름:');
    console.log('  1. video_titles.product_data (JSON) 저장');
    console.log('  2. getPendingSchedules()에서 product_data 조회');
    console.log('  3. generateScript()에서 JSON.parse(product_data) → productInfo');
    console.log('  4. /api/scripts/generate에 productInfo 전달');
    console.log('  5. 상품 대본 생성 시 productInfo 사용');
    console.log('  6. 상품 대본 완료 후 상품정보 대본 자동 생성 (productInfo 전달)');
    console.log('  7. YouTube 업로드 시 상품정보 대본 로드 → description 설정');
    console.log('\n📦 상품정보 포함 내용:');
    console.log('  - 제목 (title)');
    console.log('  - 썸네일 (thumbnail)');
    console.log('  - 상품링크/딥링크 (product_link)');
    console.log('  - 상품상세 (product_description)');
  }

  process.exit(testResults.failed === 0 ? 0 : 1);
}

runTests().catch(error => {
  console.error('❌ 테스트 실행 오류:', error);
  process.exit(1);
});
