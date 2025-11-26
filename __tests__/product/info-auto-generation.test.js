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
  console.log('🧪 상품 대본 생성 시 상품정보 대본 자동 생성 테스트\n');

  const generatePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'scripts', 'generate', 'route.ts');
  const generateContent = fs.readFileSync(generatePath, 'utf-8');

  // 테스트 1: scriptType === 'product' 체크 존재
  const hasProductCheck = generateContent.includes("scriptType === 'product'") &&
                          generateContent.includes('productInfo');
  addTestResult('product 타입 체크', hasProductCheck,
    hasProductCheck ? 'scriptType === "product" && productInfo 체크 존재' : '체크 누락');

  // 테스트 2: 상품정보 대본 자동 생성 로그
  const hasAutoGenLog = generateContent.includes('상품정보 대본 자동 생성');
  addTestResult('자동 생성 로그', hasAutoGenLog,
    hasAutoGenLog ? '상품정보 대본 자동 생성 로그 존재' : '로그 누락');

  // 테스트 3: 상품정보 제목 생성
  const hasProductInfoTitle = generateContent.includes('상품 기입 정보') &&
                               generateContent.includes('${title} - 상품 기입 정보');
  addTestResult('상품정보 제목 생성', hasProductInfoTitle,
    hasProductInfoTitle ? '"{제목} - 상품 기입 정보" 형식' : '제목 형식 누락');

  // 테스트 4: API 호출 (fetch)
  const hasFetchCall = generateContent.includes('/api/scripts/generate') &&
                       generateContent.includes('X-Internal-Request');
  addTestResult('API 호출', hasFetchCall,
    hasFetchCall ? 'scripts/generate API 내부 호출' : 'API 호출 누락');

  // 테스트 5: type과 videoFormat 설정
  const hasTypeFormat = generateContent.includes("type: 'product-info'") &&
                        generateContent.includes("videoFormat: 'product-info'");
  addTestResult('type/videoFormat 설정', hasTypeFormat,
    hasTypeFormat ? 'product-info 타입 설정' : '타입 설정 누락');

  // 테스트 6: productInfo 전달
  const passesProductInfo = generateContent.includes('productInfo: productInfo');
  addTestResult('productInfo 전달', passesProductInfo,
    passesProductInfo ? '상품 정보 전달됨' : 'productInfo 전달 누락');

  // 테스트 7: userId 전달
  const passesUserId = generateContent.includes('userId: currentUserId');
  addTestResult('userId 전달', passesUserId,
    passesUserId ? '같은 사용자로 생성' : 'userId 누락');

  // 테스트 8: useClaudeLocal, scriptModel 전달
  const passesModel = generateContent.includes('useClaudeLocal: useClaudeLocal') &&
                      generateContent.includes('scriptModel');
  addTestResult('모델 설정 전달', passesModel,
    passesModel ? 'useClaudeLocal, scriptModel 전달' : '모델 설정 누락');

  // 테스트 9: 에러 처리
  const hasErrorHandling = generateContent.includes('productInfoError') &&
                           generateContent.includes('상품정보 대본 생성 오류');
  addTestResult('에러 처리', hasErrorHandling,
    hasErrorHandling ? 'try-catch 에러 처리' : '에러 처리 누락');

  // 테스트 10: 성공/실패 로그
  const hasResponseLog = generateContent.includes('상품정보 대본 생성 시작됨') &&
                         generateContent.includes('상품정보 대본 생성 실패');
  addTestResult('응답 로그', hasResponseLog,
    hasResponseLog ? '성공/실패 로그 존재' : '응답 로그 누락');

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
    console.log('  1. 상품 대본 생성 완료 시 자동으로 상품정보 대본 생성');
    console.log('  2. 생성 조건: scriptType === "product" && productInfo 존재');
    console.log('  3. 상품정보 제목: "{원본제목} - 상품 기입 정보"');
    console.log('  4. 내부 API 호출로 자동 생성');
    console.log('  5. productInfo, userId, model 설정 모두 전달');
    console.log('\n💡 동작 흐름:');
    console.log('  1. 사용자가 상품 대본 생성 요청');
    console.log('  2. 상품 대본 생성 완료');
    console.log('  3. 🔥 자동으로 상품정보 대본 생성 시작');
    console.log('  4. 상품정보 대본 생성 완료');
    console.log('  5. YouTube 업로드 시 상품정보 대본 내용이 description에 자동 삽입');
    console.log('\n⚠️ 주의사항:');
    console.log('  - 상품정보 대본은 비동기로 생성됨 (별도 프로세스)');
    console.log('  - 상품 대본 생성이 실패해도 상품정보 대본 생성은 시도됨');
    console.log('  - 상품정보 대본 생성 실패 시에도 상품 대본은 완료 상태');
  }

  process.exit(testResults.failed === 0 ? 0 : 1);
}

runTests().catch(error => {
  console.error('❌ 테스트 실행 오류:', error);
  process.exit(1);
});
