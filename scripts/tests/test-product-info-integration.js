/**
 * 상품정보 플레이스홀더 치환 통합 테스트
 *
 * 테스트 시나리오:
 * 1. 상품 데이터를 DB에 저장 (product-info 타입)
 * 2. 스케줄러가 실행되면서 대본 생성 API 호출
 * 3. 프롬프트에서 플레이스홀더 치환 확인
 * 4. AI 응답 후처리에서도 플레이스홀더 치환 확인
 */

const path = require('path');
const { randomUUID } = require('crypto');

// frontend의 node_modules 사용
const Database = require(path.join(__dirname, 'trend-video-frontend', 'node_modules', 'better-sqlite3'));

const BASE_URL = 'http://localhost:3000';
const dbPath = path.join(__dirname, 'trend-video-frontend', 'data', 'database.sqlite');

// 테스트용 상품 데이터
const TEST_PRODUCT_DATA = {
  title: '카시오 MQ-24-7B 시계',
  thumbnail: 'https://example.com/thumbnail.jpg',
  product_link: 'https://www.coupang.com/vp/products/12345',
  description: '클래식한 디자인의 카시오 시계입니다.'
};

// 색상 출력
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

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// 1단계: DB에 title과 schedule 생성
function createTestData() {
  log('blue', '\n📝 Step 1: DB에 테스트 데이터 생성');

  const db = new Database(dbPath);

  // 테스트용 사용자 확인
  const user = db.prepare('SELECT id FROM users LIMIT 1').get();
  if (!user) {
    throw new Error('사용자가 없습니다. 먼저 로그인해주세요.');
  }
  log('green', `✅ 사용자 ID: ${user.id}`);

  const titleId = randomUUID();
  const scheduleId = randomUUID();
  const productDataJson = JSON.stringify(TEST_PRODUCT_DATA);

  // video_titles 생성
  db.prepare(`
    INSERT INTO video_titles (
      id, title, type, category, tags,
      product_data, channel, script_mode, media_mode,
      model, youtube_schedule, user_id, status
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    titleId,
    '[테스트] 상품정보 플레이스홀더 치환 테스트',
    'product-info',
    '상품정보',
    '테스트',
    productDataJson,
    null,
    'api',
    'upload',
    'chatgpt',
    'immediate',
    user.id,
    'pending'
  );

  log('green', `✅ Title 생성: ${titleId}`);
  log('cyan', `📦 Product Data: ${productDataJson}`);

  // video_schedules 생성 (즉시 실행)
  const now = new Date();
  const scheduledTime = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}T${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`;

  db.prepare(`
    INSERT INTO video_schedules (
      id, title_id, scheduled_time, status
    ) VALUES (?, ?, ?, ?)
  `).run(scheduleId, titleId, scheduledTime, 'pending');

  log('green', `✅ Schedule 생성: ${scheduleId}`);
  log('cyan', `⏰ Scheduled Time: ${scheduledTime}`);

  db.close();

  return { titleId, scheduleId, userId: user.id };
}

// 2단계: 스케줄러 실행 대기 및 결과 확인
async function waitForScriptGeneration(titleId, scheduleId, userId) {
  log('blue', '\n🔄 Step 2: 스케줄러 실행 대기 (최대 30초)');

  const maxWaitTime = 30 * 1000; // 30초
  const startTime = Date.now();

  while (Date.now() - startTime < maxWaitTime) {
    await sleep(2000); // 2초마다 체크

    const db = new Database(dbPath);

    // 스케줄 상태 확인
    const schedule = db.prepare('SELECT status, script_id FROM video_schedules WHERE id = ?').get(scheduleId);

    if (schedule.status === 'failed') {
      db.close();
      throw new Error('❌ 스케줄이 실패했습니다.');
    }

    if (schedule.script_id) {
      log('green', `✅ 대본 생성 완료! Script ID: ${schedule.script_id}`);

      // 대본 내용 확인
      const script = db.prepare('SELECT content FROM contents WHERE id = ?').get(schedule.script_id);
      db.close();

      if (!script) {
        throw new Error('❌ 대본을 찾을 수 없습니다.');
      }

      return { scriptId: schedule.script_id, content: script.content };
    }

    db.close();
    log('yellow', `⏳ 대기 중... (${Math.floor((Date.now() - startTime) / 1000)}초 경과)`);
  }

  throw new Error('❌ 타임아웃: 30초 내에 대본이 생성되지 않았습니다.');
}

// 3단계: 플레이스홀더 치환 확인
function verifyPlaceholderReplacement(content) {
  log('blue', '\n🔍 Step 3: 플레이스홀더 치환 확인');

  const hasPlaceholder = {
    thumbnail: content.includes('{thumbnail}'),
    product_link: content.includes('{product_link}'),
    product_description: content.includes('{product_description}')
  };

  const hasRealValue = {
    thumbnail: content.includes(TEST_PRODUCT_DATA.thumbnail),
    product_link: content.includes(TEST_PRODUCT_DATA.product_link),
    description: content.includes(TEST_PRODUCT_DATA.description)
  };

  log('cyan', '📄 대본 내용 (첫 500자):');
  console.log(content.substring(0, 500));
  console.log('...\n');

  let allPassed = true;

  // 플레이스홀더가 남아있는지 확인
  if (hasPlaceholder.thumbnail) {
    log('red', '❌ {thumbnail} 플레이스홀더가 치환되지 않았습니다!');
    allPassed = false;
  } else {
    log('green', '✅ {thumbnail} 플레이스홀더 치환됨');
  }

  if (hasPlaceholder.product_link) {
    log('red', '❌ {product_link} 플레이스홀더가 치환되지 않았습니다!');
    allPassed = false;
  } else {
    log('green', '✅ {product_link} 플레이스홀더 치환됨');
  }

  if (hasPlaceholder.product_description) {
    log('red', '❌ {product_description} 플레이스홀더가 치환되지 않았습니다!');
    allPassed = false;
  } else {
    log('green', '✅ {product_description} 플레이스홀더 치환됨');
  }

  // 실제 값이 포함되어 있는지 확인
  if (hasRealValue.thumbnail) {
    log('green', '✅ 실제 썸네일 URL 포함됨');
  } else {
    log('yellow', '⚠️ 실제 썸네일 URL이 포함되지 않았습니다.');
  }

  if (hasRealValue.product_link) {
    log('green', '✅ 실제 상품 링크 포함됨');
  } else {
    log('yellow', '⚠️ 실제 상품 링크가 포함되지 않았습니다.');
  }

  if (hasRealValue.description) {
    log('green', '✅ 실제 상품 설명 포함됨');
  } else {
    log('yellow', '⚠️ 실제 상품 설명이 포함되지 않았습니다.');
  }

  return allPassed;
}

// 4단계: 정리
function cleanup(titleId, scheduleId) {
  log('blue', '\n🧹 Step 4: 테스트 데이터 정리');

  const db = new Database(dbPath);

  try {
    // 파이프라인 삭제
    db.prepare('DELETE FROM automation_pipelines WHERE schedule_id = ?').run(scheduleId);
    log('green', '✅ Pipeline 삭제');

    // 스케줄 삭제
    db.prepare('DELETE FROM video_schedules WHERE id = ?').run(scheduleId);
    log('green', '✅ Schedule 삭제');

    // 타이틀 삭제
    db.prepare('DELETE FROM video_titles WHERE id = ?').run(titleId);
    log('green', '✅ Title 삭제');

  } catch (error) {
    log('yellow', `⚠️ 정리 중 오류: ${error.message}`);
  } finally {
    db.close();
  }
}

// 메인 테스트 실행
async function runIntegrationTest() {
  log('magenta', '\n' + '='.repeat(80));
  log('magenta', '🧪 상품정보 플레이스홀더 치환 통합 테스트 시작');
  log('magenta', '='.repeat(80));

  let testData = null;

  try {
    // 1. 테스트 데이터 생성
    testData = createTestData();

    // 2. 스케줄러 실행 대기
    log('yellow', '\n⏰ 스케줄러가 자동으로 실행될 때까지 대기 중...');
    log('yellow', '   (스케줄러가 비활성화되어 있으면 수동으로 활성화해주세요)');

    const result = await waitForScriptGeneration(
      testData.titleId,
      testData.scheduleId,
      testData.userId
    );

    // 3. 플레이스홀더 치환 확인
    const passed = verifyPlaceholderReplacement(result.content);

    // 4. 결과 출력
    log('magenta', '\n' + '='.repeat(80));
    if (passed) {
      log('green', '✅✅✅ 통합 테스트 성공! ✅✅✅');
      log('green', '모든 플레이스홀더가 정상적으로 치환되었습니다.');
    } else {
      log('red', '❌❌❌ 통합 테스트 실패! ❌❌❌');
      log('red', '일부 플레이스홀더가 치환되지 않았습니다.');
    }
    log('magenta', '='.repeat(80) + '\n');

    return passed;

  } catch (error) {
    log('red', '\n❌ 테스트 실행 중 오류 발생:');
    log('red', error.message);
    log('red', error.stack);
    return false;

  } finally {
    // 정리
    if (testData) {
      cleanup(testData.titleId, testData.scheduleId);
    }
  }
}

// 실행
runIntegrationTest()
  .then(success => {
    process.exit(success ? 0 : 1);
  })
  .catch(error => {
    log('red', `Fatal error: ${error.message}`);
    process.exit(1);
  });
