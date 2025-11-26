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
  console.log('🧪 상품정보 치환 완전 통합 테스트\n');
  console.log('=' .repeat(70));

  // ===== 1단계: 자동화 페이지 - product_data 전달 =====
  console.log('\n📦 1단계: 자동화 페이지 - product_data POST 전달');
  const automationPagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
  const automationPageContent = fs.readFileSync(automationPagePath, 'utf-8');

  // localStorage에서 product_data 읽기
  const readsProductData = automationPageContent.includes('current_product_data') &&
                             automationPageContent.includes('localStorage.getItem');
  addTestResult('localStorage 읽기', readsProductData,
    readsProductData ? 'current_product_data 읽기' : '읽기 로직 누락');

  // POST /api/automation/titles에 productData 포함
  const sendsProductDataToAPI = automationPageContent.includes('productData:') &&
                                  automationPageContent.includes('/api/automation/titles');
  addTestResult('POST productData', sendsProductDataToAPI,
    sendsProductDataToAPI ? '/api/automation/titles에 productData 전달' : 'productData 전달 누락');

  // ===== 2단계: automation.ts - DB 저장 =====
  console.log('\n💾 2단계: automation.ts - DB 저장');
  const automationLibPath = path.join(__dirname, 'trend-video-frontend', 'src', 'lib', 'automation.ts');
  const automationLibContent = fs.readFileSync(automationLibPath, 'utf-8');

  // INSERT에 product_data 포함
  const insertsProductData = automationLibContent.includes('product_data') &&
                              automationLibContent.includes('INSERT INTO video_titles');
  addTestResult('INSERT product_data', insertsProductData,
    insertsProductData ? 'video_titles.product_data에 저장' : 'INSERT 누락');

  // ===== 3단계: automation.ts - DB 조회 =====
  console.log('\n🔍 3단계: automation.ts - DB 조회 (getPendingSchedules)');

  // SELECT에 t.product_data 포함
  const selectsProductDataInPending = automationLibContent.match(/SELECT[\s\S]*?t\.product_data[\s\S]*?FROM video_schedules/);
  addTestResult('SELECT product_data (pending)', !!selectsProductDataInPending,
    selectsProductDataInPending ? 'getPendingSchedules에서 SELECT' : 'SELECT 누락');

  // getWaitingForUploadSchedules에서도 SELECT
  const selectsProductDataInWaiting = automationLibContent.match(/getWaitingForUploadSchedules[\s\S]*?SELECT[\s\S]*?t\.product_data/);
  addTestResult('SELECT product_data (waiting)', !!selectsProductDataInWaiting,
    selectsProductDataInWaiting ? 'getWaitingForUploadSchedules에서 SELECT' : 'SELECT 누락');

  // ===== 4단계: automation-scheduler.ts - JSON 파싱 =====
  console.log('\n🔄 4단계: automation-scheduler.ts - product_data 파싱');
  const schedulerPath = path.join(__dirname, 'trend-video-frontend', 'src', 'lib', 'automation-scheduler.ts');
  const schedulerContent = fs.readFileSync(schedulerPath, 'utf-8');

  // schedule.product_data 존재 확인
  const checksProductData = schedulerContent.includes('schedule.product_data');
  addTestResult('product_data 확인', checksProductData,
    checksProductData ? 'schedule.product_data 체크' : '확인 로직 누락');

  // JSON.parse 실행
  const parsesProductData = schedulerContent.includes('JSON.parse(schedule.product_data)');
  addTestResult('JSON 파싱', parsesProductData,
    parsesProductData ? 'JSON.parse 실행' : '파싱 로직 누락');

  // productInfo 변수 선언
  const declaresProductInfo = schedulerContent.includes('productInfo =') ||
                                schedulerContent.includes('let productInfo') ||
                                schedulerContent.includes('const productInfo');
  addTestResult('productInfo 변수', declaresProductInfo,
    declaresProductInfo ? 'productInfo 변수 선언' : '변수 선언 누락');

  // requestBody에 productInfo 포함
  const sendsProductInfoToAPI = schedulerContent.includes('productInfo:') &&
                                  schedulerContent.includes('/api/scripts/generate');
  addTestResult('API에 productInfo 전달', sendsProductInfoToAPI,
    sendsProductInfoToAPI ? 'scripts/generate에 전달' : '전달 로직 누락');

  // ===== 5단계: scripts/generate/route.ts - productInfo 수신 =====
  console.log('\n🤖 5단계: scripts/generate API - productInfo 수신 및 치환');
  const generateAPIPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'scripts', 'generate', 'route.ts');
  const generateContent = fs.readFileSync(generateAPIPath, 'utf-8');

  // productInfo 파라미터 추출
  const extractsProductInfo = generateContent.includes('productInfo') &&
                                (generateContent.includes('body.productInfo') ||
                                 generateContent.includes('const { productInfo }') ||
                                 generateContent.includes('let { productInfo }') ||
                                 generateContent.includes('productInfo,'));
  addTestResult('productInfo 추출', extractsProductInfo,
    extractsProductInfo ? 'request body에서 productInfo 추출' : '추출 로직 누락');

  // product-info 타입 처리
  const handlesProductInfoType = generateContent.includes("scriptType === 'product-info'") ||
                                   generateContent.includes('type === "product-info"');
  addTestResult('product-info 타입 처리', handlesProductInfoType,
    handlesProductInfoType ? 'product-info 타입 분기' : '타입 처리 누락');

  // {thumbnail} 치환
  const replacesThumbnail = generateContent.includes('.replace(/{thumbnail}/g');
  addTestResult('{thumbnail} 치환', replacesThumbnail,
    replacesThumbnail ? 'thumbnail 플레이스홀더 치환' : '치환 로직 누락');

  // {product_link} 치환
  const replacesProductLink = generateContent.includes('.replace(/{product_link}/g');
  addTestResult('{product_link} 치환', replacesProductLink,
    replacesProductLink ? 'product_link 플레이스홀더 치환' : '치환 로직 누락');

  // {product_description} 치환
  const replacesDescription = generateContent.includes('.replace(/{product_description}/g');
  addTestResult('{product_description} 치환', replacesDescription,
    replacesDescription ? 'product_description 플레이스홀더 치환' : '치환 로직 누락');

  // ===== 6단계: 상품 대본 완료 후 자동 상품정보 대본 생성 =====
  console.log('\n🛍️ 6단계: 상품 대본 완료 → 상품정보 대본 자동 생성');

  // scriptType === 'product' && productInfo 체크
  const checksProductTypeCompletion = generateContent.includes("scriptType === 'product' && productInfo");
  addTestResult('상품 대본 완료 체크', checksProductTypeCompletion,
    checksProductTypeCompletion ? '상품 대본 + productInfo 확인' : '확인 로직 누락');

  // 재귀 API 호출
  const callsProductInfoAPI = generateContent.includes("type: 'product-info'") &&
                                generateContent.includes('fetch') &&
                                generateContent.includes('/api/scripts/generate');
  addTestResult('product-info API 재호출', callsProductInfoAPI,
    callsProductInfoAPI ? 'product-info 대본 자동 생성' : '재호출 로직 누락');

  // productInfo 전달 in recursion
  const passesProductInfoInRecursion = generateContent.match(/type:\s*['"]product-info['"][\s\S]*?productInfo:\s*productInfo/);
  addTestResult('재귀 호출 시 productInfo 전달', !!passesProductInfoInRecursion,
    passesProductInfoInRecursion ? 'productInfo 재전달' : '전달 로직 누락');

  // ===== 7단계: YouTube 업로드 - product-info 대본 설명 삽입 =====
  console.log('\n📤 7단계: YouTube 업로드 - product-info 대본 description 삽입');
  const uploadAPIPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'youtube', 'upload', 'route.ts');
  const uploadContent = fs.readFileSync(uploadAPIPath, 'utf-8');

  // job.type === 'product' 체크
  const checksProductType = uploadContent.includes("job.type === 'product'") ||
                             uploadContent.includes('type === "product"');
  addTestResult('product 타입 체크', checksProductType,
    checksProductType ? 'product 타입 감지' : '타입 체크 누락');

  // product-info 대본 SELECT
  const queriesProductInfoScript = uploadContent.includes('상품 기입 정보') &&
                                     uploadContent.includes('SELECT content FROM scripts');
  addTestResult('product-info 대본 조회', queriesProductInfoScript,
    queriesProductInfoScript ? 'DB에서 상품정보 대본 조회' : '조회 로직 누락');

  // description 설정
  const setsDescription = uploadContent.includes('autoGeneratedDescription') ||
                           uploadContent.includes('description =');
  addTestResult('description 설정', setsDescription,
    setsDescription ? 'description에 상품정보 삽입' : '설정 로직 누락');

  // ===== 결과 요약 =====
  console.log('\n' + '='.repeat(70));
  console.log('📊 테스트 결과 요약\n');

  const totalTests = testResults.tests.length;
  const passedCount = testResults.passed;
  const failedCount = testResults.failed;
  const passRate = ((passedCount / totalTests) * 100).toFixed(1);

  console.log(`✅ 통과: ${passedCount}/${totalTests} (${passRate}%)`);
  console.log(`❌ 실패: ${failedCount}/${totalTests}`);

  if (failedCount > 0) {
    console.log('\n🔍 실패한 테스트:');
    testResults.tests.filter(t => !t.passed).forEach((t, i) => {
      console.log(`  ${i + 1}. ${t.name}: ${t.message}`);
    });
    console.log('\n⚠️ 위 항목들을 구현해야 합니다.');
  } else {
    console.log('\n🎉 모든 테스트 통과!');
    console.log('\n📋 전체 플로우:');
    console.log('  1. 상품관리 → 자동화: productData localStorage 저장');
    console.log('  2. 자동화 → DB: product_data 컬럼에 JSON 저장');
    console.log('  3. 스케줄러: product_data SELECT & JSON.parse → productInfo');
    console.log('  4. scripts/generate API: productInfo로 치환');
    console.log('     - {thumbnail} → productInfo.thumbnail');
    console.log('     - {product_link} → productInfo.product_link');
    console.log('     - {product_description} → productInfo.description');
    console.log('  5. 상품 대본 완료 → 자동으로 product-info 대본 생성');
    console.log('  6. YouTube 업로드: product-info 대본 → description');
    console.log('\n💡 이제 실제 실행 테스트를 하세요:');
    console.log('  1. 상품관리에서 "🤖 자동화" 클릭');
    console.log('  2. 자동화 페이지에서 제목 추가 및 스케줄 설정');
    console.log('  3. "⚡ 즉시 실행" 클릭');
    console.log('  4. 로그 확인:');
    console.log('     - "🛍️🛍️🛍️ 상품 정보 치환 시작"');
    console.log('     - "✅ 상품 정보 플레이스홀더 치환 완료"');
    console.log('  5. 대본 생성 완료 후 내 콘텐츠에서 확인');
    console.log('  6. YouTube 업로드 후 description 확인');
  }

  console.log('\n' + '='.repeat(70));

  process.exit(failedCount === 0 ? 0 : 1);
}

runTests().catch(error => {
  console.error('❌ 테스트 실행 오류:', error);
  process.exit(1);
});
