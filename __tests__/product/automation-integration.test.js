const fs = require('fs');
const path = require('path');

console.log('🧪 상품 자동화 통합 테스트\n');
console.log('='.repeat(60));

// 1. 상품관리 → 자동화 데이터 전달 확인
console.log('\n📦 1단계: 상품관리 → 자동화 데이터 전달');
const coupangProductsPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'admin', 'coupang-products', 'page.tsx');
const coupangContent = fs.readFileSync(coupangProductsPath, 'utf-8');

const hasProductData = coupangContent.includes('productData: {') &&
                        coupangContent.includes('title: product.title') &&
                        coupangContent.includes('thumbnail: product.image_url') &&
                        coupangContent.includes('product_link: product.deep_link') &&
                        coupangContent.includes('description: product.description');

console.log(hasProductData ? '✅' : '❌', 'automation_prefill에 productData 포함');

// 2. 자동화 페이지: localStorage 읽기
console.log('\n📥 2단계: 자동화 페이지 데이터 로드');
const automationPagePath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'automation', 'page.tsx');
const automationContent = fs.readFileSync(automationPagePath, 'utf-8');

const loadsFromLocalStorage = automationContent.includes('localStorage.getItem(\'automation_prefill\')') &&
                                automationContent.includes('setCurrentProductData');
console.log(loadsFromLocalStorage ? '✅' : '❌', 'automation_prefill 읽어서 state 설정');

const savesToCurrentProductData = automationContent.includes('localStorage.setItem(\'current_product_data\'');
console.log(savesToCurrentProductData ? '✅' : '❌', 'current_product_data에 저장');

// 3. 제목 추가: productData 전달
console.log('\n📝 3단계: 제목 추가 시 productData 전달');
const sendsProductDataInPost = automationContent.includes('current_product_data') &&
                                automationContent.includes('productData: productData') &&
                                automationContent.includes('/api/automation/titles');
console.log(sendsProductDataInPost ? '✅' : '❌', 'POST /api/automation/titles에 productData 포함');

// 4. DB 저장 확인
console.log('\n💾 4단계: DB 저장');
const automationLibPath = path.join(__dirname, 'trend-video-frontend', 'src', 'lib', 'automation.ts');
const automationLibContent = fs.readFileSync(automationLibPath, 'utf-8');

const savesToDB = automationLibContent.includes('product_data') &&
                   automationLibContent.includes('INSERT INTO video_titles');
console.log(savesToDB ? '✅' : '❌', 'video_titles.product_data에 저장');

// 5. 스케줄러: product_data SELECT
console.log('\n🔄 5단계: 스케줄러 product_data 조회');
const schedulerPath = path.join(__dirname, 'trend-video-frontend', 'src', 'lib', 'automation-scheduler.ts');
const schedulerContent = fs.readFileSync(schedulerPath, 'utf-8');

const selectsProductData = schedulerContent.includes('t.product_data') &&
                            schedulerContent.includes('SELECT');
console.log(selectsProductData ? '✅' : '❌', 'getPendingSchedules에서 product_data SELECT');

const parsesProductData = schedulerContent.includes('JSON.parse(schedule.product_data)') &&
                           schedulerContent.includes('productInfo =');
console.log(parsesProductData ? '✅' : '❌', 'product_data JSON 파싱 → productInfo');

const sendsToAPI = schedulerContent.includes('productInfo: productInfo') &&
                    schedulerContent.includes('/api/scripts/generate');
console.log(sendsToAPI ? '✅' : '❌', 'scripts/generate API에 productInfo 전달');

// 6. scripts/generate API: productInfo 처리
console.log('\n🤖 6단계: scripts/generate API - productInfo 처리');
const generateAPIPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'scripts', 'generate', 'route.ts');
const generateContent = fs.readFileSync(generateAPIPath, 'utf-8');

const receivesProductInfo = generateContent.includes('productInfo') &&
                             generateContent.includes('const.*productInfo|let.*productInfo');
console.log(receivesProductInfo ? '✅' : '❌', 'productInfo 파라미터 수신');

const replacesPlaceholders = generateContent.includes('replace(/{thumbnail}/g') &&
                              generateContent.includes('replace(/{product_link}/g') &&
                              generateContent.includes('replace(/{product_description}/g');
console.log(replacesPlaceholders ? '✅' : '❌', '프롬프트 플레이스홀더 치환');

// 7. 상품정보 대본 자동 생성
console.log('\n🛍️ 7단계: 상품정보 대본 자동 생성');
const autoGeneratesProductInfo = generateContent.includes("scriptType === 'product' && productInfo") &&
                                  generateContent.includes('상품정보 대본 자동 생성');
console.log(autoGeneratesProductInfo ? '✅' : '❌', '상품 대본 완료 후 자동 생성');

const callsProductInfoAPI = generateContent.includes("type: 'product-info'") &&
                             generateContent.includes('productInfo: productInfo');
console.log(callsProductInfoAPI ? '✅' : '❌', 'product-info 타입으로 재호출');

// 8. YouTube 업로드: 상품정보 대본 description 삽입
console.log('\n📤 8단계: YouTube 업로드');
const uploadAPIPath = path.join(__dirname, 'trend-video-frontend', 'src', 'app', 'api', 'youtube', 'upload', 'route.ts');
const uploadContent = fs.readFileSync(uploadAPIPath, 'utf-8');

const queriesProductInfoScript = uploadContent.includes("job.type === 'product'") &&
                                  uploadContent.includes('SELECT content FROM scripts') &&
                                  uploadContent.includes('상품 기입 정보');
console.log(queriesProductInfoScript ? '✅' : '❌', 'product-info 대본 DB 조회');

const setsDescription = uploadContent.includes('autoGeneratedDescription = productInfoScript.content');
console.log(setsDescription ? '✅' : '❌', 'content → description 설정');

// 최종 결과
console.log('\n' + '='.repeat(60));
console.log('📊 테스트 결과 요약\n');

const allTests = [
  hasProductData,
  loadsFromLocalStorage,
  savesToCurrentProductData,
  sendsProductDataInPost,
  savesToDB,
  selectsProductData,
  parsesProductData,
  sendsToAPI,
  receivesProductInfo,
  replacesPlaceholders,
  autoGeneratesProductInfo,
  callsProductInfoAPI,
  queriesProductInfoScript,
  setsDescription
];

const passedTests = allTests.filter(t => t).length;
const totalTests = allTests.length;

console.log(`✅ 통과: ${passedTests}/${totalTests}`);
console.log(`❌ 실패: ${totalTests - passedTests}/${totalTests}`);

if (passedTests === totalTests) {
  console.log('\n✅ 모든 코드가 구현되어 있습니다!');
  console.log('\n💡 실제 작동 테스트 방법:');
  console.log('  1. 상품관리에서 "자동화" 버튼 클릭');
  console.log('  2. 자동화 페이지에서 상품정보 미리보기 확인');
  console.log('  3. 스케줄 설정 후 제목 추가');
  console.log('  4. 즉시 실행 또는 스케줄 대기');
  console.log('  5. 대본 생성 로그에서 "상품정보 치환" 확인');
  console.log('  6. 대본 완료 후 "상품정보 대본 생성 시작" 로그 확인');
  console.log('  7. 영상 생성 완료 후 내 콘텐츠에서 상품정보 대본 확인');
  console.log('  8. YouTube 업로드 후 description에 상품정보 포함 확인');
  console.log('\n🔍 디버깅 방법:');
  console.log('  - 브라우저 콘솔에서 로그 확인');
  console.log('  - "🛍️ Product data found" 메시지 확인');
  console.log('  - "상품정보 치환 시작" 로그 확인');
  console.log('  - productInfo 객체 내용 확인');
} else {
  console.log('\n❌ 일부 코드가 누락되었습니다.');
  console.log('실패한 테스트를 확인하여 코드를 수정하세요.');
}

console.log('\n' + '='.repeat(60));

process.exit(passedTests === totalTests ? 0 : 1);
