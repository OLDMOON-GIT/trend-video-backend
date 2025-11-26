/**
 * Product Data 전달 플로우 실제 테스트
 * DB의 실제 데이터로 스케줄러 → API 플로우 시뮬레이션
 */

const path = require('path');
const Database = require(path.join(__dirname, 'trend-video-frontend', 'node_modules', 'better-sqlite3'));

const dbPath = path.join(__dirname, 'trend-video-frontend', 'data', 'database.sqlite');

const colors = {
  reset: '\x1b[0m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m'
};

function log(color, message) {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

// 가장 최근 product 타입 스케줄 가져오기
function getLatestProductSchedule() {
  const db = new Database(dbPath);

  const schedule = db.prepare(`
    SELECT
      s.*,
      t.title,
      t.type,
      t.product_data,
      t.user_id
    FROM video_schedules s
    JOIN video_titles t ON s.title_id = t.id
    WHERE t.type = 'product'
    ORDER BY s.created_at DESC
    LIMIT 1
  `).get();

  db.close();

  return schedule;
}

// 스케줄러 로직 시뮬레이션 (automation-scheduler.ts와 동일)
function simulateSchedulerLogic(schedule) {
  log('cyan', '\n📋 스케줄 정보:');
  log('cyan', `   Title: ${schedule.title}`);
  log('cyan', `   Type: ${schedule.type}`);
  log('cyan', `   Schedule ID: ${schedule.id}`);
  log('cyan', `   Product Data: ${schedule.product_data ? 'YES' : 'NO'}`);

  // automation-scheduler.ts line 365-374와 동일
  let productInfo = undefined;
  if (schedule.product_data) {
    try {
      productInfo = JSON.parse(schedule.product_data);
      log('green', '\n✅ Product data 파싱 성공:');
      log('green', `   - title: ${productInfo.title}`);
      log('green', `   - thumbnail: ${productInfo.thumbnail}`);
      log('green', `   - product_link: ${productInfo.product_link}`);
      log('green', `   - description: ${productInfo.description}`);
    } catch (e) {
      log('red', `\n❌ Product data 파싱 실패: ${e.message}`);
      log('red', `   Raw data: ${schedule.product_data}`);
    }
  } else {
    log('red', '\n❌ Product data 없음!');
  }

  // automation-scheduler.ts line 376-385와 동일
  const requestBody = {
    title: schedule.title,
    type: schedule.type,
    productUrl: schedule.product_url,
    productInfo: productInfo || null,
    model: schedule.model || 'claude',
    useClaudeLocal: schedule.script_mode !== 'api',
    userId: schedule.user_id,
    category: schedule.category
  };

  log('cyan', '\n📤 API로 전달될 Request Body:');
  log('cyan', `   productInfo: ${requestBody.productInfo ? 'YES ✅' : 'NO ❌'}`);

  if (requestBody.productInfo) {
    log('cyan', `   - title: ${requestBody.productInfo.title}`);
    log('cyan', `   - thumbnail: ${requestBody.productInfo.thumbnail?.substring(0, 50)}...`);
    log('cyan', `   - product_link: ${requestBody.productInfo.product_link}`);
    log('cyan', `   - description: ${requestBody.productInfo.description?.substring(0, 50)}...`);
  }

  return { productInfo, requestBody };
}

// API 수신 시뮬레이션 (scripts/generate/route.ts와 동일)
function simulateAPIReceive(requestBody) {
  // scripts/generate/route.ts line 271
  const { productInfo } = requestBody;

  log('cyan', '\n📥 API에서 수신:');
  log('cyan', `   productInfo: ${productInfo ? 'YES ✅' : 'NO ❌'}`);

  if (productInfo) {
    log('green', '   - title: ' + productInfo.title);
    log('green', '   - thumbnail: ' + productInfo.thumbnail?.substring(0, 50) + '...');
    log('green', '   - product_link: ' + productInfo.product_link);
    log('green', '   - description: ' + productInfo.description?.substring(0, 50) + '...');
  } else {
    log('red', '\n❌ productInfo가 없어서 플레이스홀더 치환 불가!');
  }

  return productInfo;
}

// 프롬프트 치환 시뮬레이션
function simulatePromptReplacement(productInfo) {
  const mockPrompt = `당신은 상품 마케팅 전문가입니다.

📦 **상품 정보:**
- 제목: {title}
- 썸네일: {thumbnail}
- 상품링크: {product_link}
- 상품상세: {product_description}
`;

  log('cyan', '\n📝 원본 프롬프트 (샘플):');
  console.log(colors.yellow + mockPrompt.substring(0, 200) + '...' + colors.reset);

  if (productInfo) {
    const replacedPrompt = mockPrompt
      .replace(/{thumbnail}/g, productInfo.thumbnail || '')
      .replace(/{product_link}/g, productInfo.product_link || '')
      .replace(/{product_description}/g, productInfo.description || '');

    log('green', '\n✅ 치환된 프롬프트:');
    console.log(colors.green + replacedPrompt.substring(0, 300) + '...' + colors.reset);

    // 플레이스홀더 남아있는지 확인
    const hasPlaceholder = replacedPrompt.includes('{thumbnail}') ||
                          replacedPrompt.includes('{product_link}') ||
                          replacedPrompt.includes('{product_description}');

    if (hasPlaceholder) {
      log('red', '\n❌ 플레이스홀더가 여전히 남아있습니다!');
      return false;
    } else {
      log('green', '\n✅ 모든 플레이스홀더가 치환되었습니다!');
      return true;
    }
  } else {
    log('red', '\n❌ productInfo가 없어서 플레이스홀더 치환 불가!');
    log('red', '프롬프트에 플레이스홀더가 그대로 남아있을 것입니다:');
    console.log(colors.red + mockPrompt + colors.reset);
    return false;
  }
}

// 메인 테스트
async function runTest() {
  log('magenta', '\n' + '='.repeat(80));
  log('magenta', '🧪 Product Data 전달 플로우 실제 테스트');
  log('magenta', '   (실제 DB 데이터 사용)');
  log('magenta', '='.repeat(80));

  try {
    // 1. DB에서 가장 최근 product 스케줄 가져오기
    log('blue', '\n📝 Step 1: DB에서 최근 product 스케줄 조회');
    const schedule = getLatestProductSchedule();

    if (!schedule) {
      log('red', '\n❌ Product 타입 스케줄을 찾을 수 없습니다!');
      return false;
    }

    // 2. 스케줄러 로직 시뮬레이션
    log('blue', '\n🔄 Step 2: 스케줄러 로직 시뮬레이션');
    const { productInfo, requestBody } = simulateSchedulerLogic(schedule);

    // 3. API 수신 시뮬레이션
    log('blue', '\n📡 Step 3: API 수신 시뮬레이션');
    const receivedProductInfo = simulateAPIReceive(requestBody);

    // 4. 프롬프트 치환 시뮬레이션
    log('blue', '\n📄 Step 4: 프롬프트 치환 시뮬레이션');
    const replacementSuccess = simulatePromptReplacement(receivedProductInfo);

    // 결과
    log('magenta', '\n' + '='.repeat(80));
    if (productInfo && receivedProductInfo && replacementSuccess) {
      log('green', '✅✅✅ 테스트 성공! ✅✅✅');
      log('green', 'Product Data가 정상적으로 전달되고 치환됩니다.');
    } else {
      log('red', '❌❌❌ 테스트 실패! ❌❌❌');
      if (!productInfo) {
        log('red', '문제: DB의 product_data가 없거나 파싱 실패');
      } else if (!receivedProductInfo) {
        log('red', '문제: API로 productInfo 전달 실패');
      } else if (!replacementSuccess) {
        log('red', '문제: 프롬프트 플레이스홀더 치환 실패');
      }
    }
    log('magenta', '='.repeat(80) + '\n');

    return productInfo && receivedProductInfo && replacementSuccess;

  } catch (error) {
    log('red', `\n❌ 테스트 실행 중 오류: ${error.message}`);
    console.error(error.stack);
    return false;
  }
}

// 실행
runTest()
  .then(success => {
    process.exit(success ? 0 : 1);
  })
  .catch(error => {
    log('red', `Fatal error: ${error.message}`);
    process.exit(1);
  });
