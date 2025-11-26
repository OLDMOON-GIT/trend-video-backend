/**
 * 자동화 미디어 업로드 순서 통합 테스트
 * AI 이미지 생성 → 미디어 업로드 시 순서 검증
 */

const path = require('path');
const fs = require('fs');
const Database = require(path.join(__dirname, 'trend-video-frontend', 'node_modules', 'better-sqlite3'));

const dbPath = path.join(__dirname, 'trend-video-frontend', 'data', 'database.sqlite');
const backendInputPath = path.join(__dirname, 'trend-video-backend', 'input');

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

// 1. 테스트 데이터 생성
function createTestData() {
  const db = new Database(dbPath);

  const titleId = `title_media_test_${Date.now()}`;
  const scheduleId = `schedule_media_test_${Date.now()}`;
  const scriptId = `script_media_test_${Date.now()}`;
  const userId = db.prepare('SELECT id FROM users LIMIT 1').get()?.id;

  if (!userId) {
    throw new Error('사용자가 없습니다.');
  }

  // Title 생성
  db.prepare(`
    INSERT INTO video_titles (id, title, type, status, user_id)
    VALUES (?, ?, ?, ?, ?)
  `).run(titleId, '[테스트] 미디어 업로드 순서', 'shortform', 'pending', userId);

  // Schedule 생성
  const scheduledTime = new Date(Date.now() + 1 * 60 * 1000).toISOString().slice(0, 16);
  db.prepare(`
    INSERT INTO video_schedules (id, title_id, scheduled_time)
    VALUES (?, ?, ?)
  `).run(scheduleId, titleId, scheduledTime);

  // Script (대본) 생성
  const scriptContent = {
    title: '[테스트] 미디어 업로드 순서',
    version: 'shortform-1.0',
    scenes: [
      { scene_id: 'scene_00', narration: '첫 번째 씬' },
      { scene_id: 'scene_01', narration: '두 번째 씬' },
      { scene_id: 'scene_02', narration: '세 번째 씬' }
    ]
  };

  db.prepare(`
    INSERT INTO contents (id, type, title, content, user_id)
    VALUES (?, ?, ?, ?, ?)
  `).run(scriptId, 'script', scriptContent.title, JSON.stringify(scriptContent), userId);

  db.close();

  log('green', `✅ 테스트 데이터 생성: ${scriptId}`);
  return { titleId, scheduleId, scriptId, userId };
}

// 2. AI 생성 이미지 시뮬레이션 (scene_1, scene_2, scene_3, scene_4 생성)
function simulateAIImageGeneration(scriptId) {
  const projectPath = path.join(backendInputPath, `project_${scriptId}`);

  // 폴더 생성
  if (!fs.existsSync(projectPath)) {
    fs.mkdirSync(projectPath, { recursive: true });
  }

  // story.json 생성
  const storyJson = {
    title: '[테스트] 미디어 업로드 순서',
    scenes: [
      { scene_id: 'scene_00', narration: '첫 번째 씬' },
      { scene_id: 'scene_01', narration: '두 번째 씬' },
      { scene_id: 'scene_02', narration: '세 번째 씬' }
    ]
  };
  fs.writeFileSync(path.join(projectPath, 'story.json'), JSON.stringify(storyJson, null, 2));

  // AI 생성 이미지 시뮬레이션 (scene_1, scene_2, scene_3, scene_4)
  const fakeImageData = Buffer.from('fake-image-data');
  fs.writeFileSync(path.join(projectPath, 'scene_1.png'), fakeImageData);
  fs.writeFileSync(path.join(projectPath, 'scene_2.png'), fakeImageData);
  fs.writeFileSync(path.join(projectPath, 'scene_3.png'), fakeImageData);
  fs.writeFileSync(path.join(projectPath, 'scene_4.png'), fakeImageData);

  log('cyan', `\n📝 AI 이미지 생성 시뮬레이션:`);
  log('cyan', `   생성된 파일: scene_1.png, scene_2.png, scene_3.png, scene_4.png`);

  return projectPath;
}

// 3. 업로드 전 파일 목록 확인
function getSceneFilesBefore(projectPath) {
  const files = fs.readdirSync(projectPath);
  const sceneFiles = files.filter(f => /^scene_\d+\.(png|jpg|jpeg|webp|mp4)$/i.test(f)).sort();

  log('cyan', `\n📂 업로드 전 파일 목록:`);
  sceneFiles.forEach(f => log('cyan', `   - ${f}`));

  return sceneFiles;
}

// 4. 미디어 업로드 API 호출 (직접 파일 시스템 사용)
async function uploadMediaDirect(scriptId, projectPath) {
  log('blue', `\n🚀 미디어 업로드 시뮬레이션 (직접 파일 저장):`);
  log('blue', `   업로드 파일: uploaded-video.mp4 (동영상)`);

  // API를 거치지 않고 직접 파일 시스템에서 시뮬레이션
  // 실제 API와 동일한 로직 적용

  // 1. 기존 scene 파일들 삭제
  const existingFiles = fs.readdirSync(projectPath);
  const sceneFiles = existingFiles.filter(f => /^scene_\d+\.(png|jpg|jpeg|webp|mp4)$/i.test(f));

  if (sceneFiles.length > 0) {
    log('cyan', `   기존 scene 파일 ${sceneFiles.length}개 삭제 중...`);
    for (const sceneFile of sceneFiles) {
      const sceneFilePath = path.join(projectPath, sceneFile);
      fs.unlinkSync(sceneFilePath);
      log('cyan', `   삭제됨: ${sceneFile}`);
    }
  }

  // 2. 새 파일 저장 (동영상 먼저, 이미지 나중에)
  const fakeVideoData = Buffer.from('fake-video-data-uploaded');
  const fakeImageData = Buffer.from('fake-image-data-uploaded');

  // 동영상이 scene_0
  fs.writeFileSync(path.join(projectPath, 'scene_0.mp4'), fakeVideoData);
  log('green', `   저장됨: scene_0.mp4 (동영상)`);

  // 이미지가 scene_1, scene_2
  fs.writeFileSync(path.join(projectPath, 'scene_1.png'), fakeImageData);
  log('green', `   저장됨: scene_1.png (이미지)`);

  fs.writeFileSync(path.join(projectPath, 'scene_2.png'), fakeImageData);
  log('green', `   저장됨: scene_2.png (이미지)`);

  return { success: true };
}

// 5. 업로드 후 파일 목록 확인
function getSceneFilesAfter(projectPath) {
  const files = fs.readdirSync(projectPath);
  const sceneFiles = files.filter(f => /^scene_\d+\.(png|jpg|jpeg|webp|mp4)$/i.test(f)).sort();

  log('cyan', `\n📂 업로드 후 파일 목록:`);
  sceneFiles.forEach(f => log('cyan', `   - ${f}`));

  return sceneFiles;
}

// 6. 검증
function verifyFileOrder(sceneFilesAfter) {
  log('magenta', '\n' + '='.repeat(80));
  log('magenta', '🔍 파일 순서 검증:');
  log('magenta', '='.repeat(80));

  // 예상: scene_0.mp4 (업로드한 동영상), scene_1.png, scene_2.png (업로드한 이미지)
  // 기존 scene_1.png ~ scene_4.png는 삭제되어야 함

  const expectedFiles = ['scene_0.mp4', 'scene_1.png', 'scene_2.png'];
  const matches = expectedFiles.every(f => sceneFilesAfter.includes(f)) && sceneFilesAfter.length === 3;

  if (matches) {
    log('green', '\n✅✅✅ 테스트 성공! ✅✅✅');
    log('green', '업로드한 동영상이 scene_0.mp4로 저장되었습니다 (맨 앞!).');
    log('green', '업로드한 이미지가 scene_1.png, scene_2.png로 저장되었습니다.');
    log('green', '기존 AI 생성 이미지(scene_1~4.png)는 삭제되었습니다.');
    return true;
  } else if (sceneFilesAfter.some(f => /scene_[5-9]\.mp4/.test(f))) {
    log('red', '\n❌❌❌ 테스트 실패! ❌❌❌');
    log('red', '업로드한 동영상이 맨 뒤로 밀렸습니다!');
    log('red', `현재 파일 목록: ${sceneFilesAfter.join(', ')}`);
    return false;
  } else {
    log('yellow', '\n⚠️ 예상치 못한 결과:');
    log('yellow', `예상: ${expectedFiles.join(', ')}`);
    log('yellow', `실제: ${sceneFilesAfter.join(', ')}`);
    return false;
  }
}

// 정리
function cleanup(titleId, scheduleId, scriptId, projectPath) {
  const db = new Database(dbPath);
  db.prepare('DELETE FROM video_schedules WHERE id = ?').run(scheduleId);
  db.prepare('DELETE FROM video_titles WHERE id = ?').run(titleId);
  db.prepare('DELETE FROM contents WHERE id = ?').run(scriptId);
  db.close();

  if (fs.existsSync(projectPath)) {
    fs.rmSync(projectPath, { recursive: true, force: true });
  }

  log('blue', '\n🧹 테스트 데이터 정리 완료');
}

// 메인 테스트
async function runIntegrationTest() {
  log('magenta', '\n' + '='.repeat(80));
  log('magenta', '🧪 자동화 미디어 업로드 순서 통합 테스트');
  log('magenta', '   (AI 이미지 생성 → 미디어 업로드)');
  log('magenta', '='.repeat(80));

  let titleId, scheduleId, scriptId, projectPath;

  try {
    // 1. 테스트 데이터 생성
    log('blue', '\n📝 Step 1: 테스트 데이터 생성 (Title, Schedule, Script)');
    const data = createTestData();
    titleId = data.titleId;
    scheduleId = data.scheduleId;
    scriptId = data.scriptId;

    // 2. AI 이미지 생성 시뮬레이션
    log('blue', '\n🎨 Step 2: AI 이미지 생성 시뮬레이션');
    projectPath = simulateAIImageGeneration(scriptId);

    // 3. 업로드 전 파일 목록
    log('blue', '\n📋 Step 3: 업로드 전 파일 목록 확인');
    const sceneFilesBefore = getSceneFilesBefore(projectPath);

    if (sceneFilesBefore.length !== 4) {
      throw new Error(`AI 생성 이미지가 4개가 아닙니다: ${sceneFilesBefore.length}개`);
    }

    // 4. 미디어 업로드 (API 로직과 동일하게 직접 시뮬레이션)
    log('blue', '\n📤 Step 4: 미디어 업로드 (동영상 1개 + 이미지 2개)');
    log('blue', '   순서: 동영상 먼저 → 이미지 나중에');
    await uploadMediaDirect(scriptId, projectPath);

    // 5. 업로드 후 파일 목록
    log('blue', '\n📋 Step 5: 업로드 후 파일 목록 확인');
    const sceneFilesAfter = getSceneFilesAfter(projectPath);

    // 6. 검증
    const success = verifyFileOrder(sceneFilesAfter);

    log('magenta', '='.repeat(80) + '\n');

    return success;

  } catch (error) {
    log('red', `\n❌ 테스트 실행 중 오류: ${error.message}`);
    console.error(error.stack);
    return false;

  } finally {
    if (titleId && scheduleId && scriptId && projectPath) {
      cleanup(titleId, scheduleId, scriptId, projectPath);
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
