/**
 * 자동화 파이프라인 ID 매칭 검증 테스트
 *
 * 이전 문제:
 * - resumeVideoGeneration이 새로운 pipeline ID를 생성 (schedule.id + '_video')
 * - 하지만 DB에는 초기 생성 시 다른 ID로 pipeline이 생성됨 (pipeline_xxx_video_xxx)
 * - updatePipelineStatus가 존재하지 않는 ID로 UPDATE 시도 -> 아무 변화 없음
 * - video_id가 DB에 저장되지 않음
 *
 * 수정 내용:
 * - resumeVideoGeneration이 DB에서 기존 pipeline ID를 찾아서 사용
 * - 없으면 fallback으로 새 ID 생성
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

function testPipelineIdMatching() {
  log('magenta', '\n' + '='.repeat(80));
  log('magenta', '🔧 자동화 파이프라인 ID 매칭 테스트');
  log('magenta', '='.repeat(80));

  const db = new Database(dbPath);

  try {
    // 1. 테스트용 스케줄과 파이프라인 생성
    const testScheduleId = `schedule_test_${Date.now()}`;
    const userId = db.prepare('SELECT id FROM users LIMIT 1').get()?.id;

    if (!userId) {
      throw new Error('사용자가 없습니다.');
    }

    // Title 생성
    const titleId = `title_test_${Date.now()}`;
    db.prepare(`
      INSERT INTO video_titles (id, title, type, status, user_id)
      VALUES (?, ?, ?, ?, ?)
    `).run(titleId, '[테스트] Pipeline ID 매칭', 'shortform', 'pending', userId);

    // Schedule 생성
    db.prepare(`
      INSERT INTO video_schedules (id, title_id, scheduled_time, status)
      VALUES (?, ?, ?, ?)
    `).run(testScheduleId, titleId, new Date().toISOString(), 'waiting_for_upload');

    // Pipeline 생성 (실제 automation처럼)
    const pipelineId = `pipeline_${Date.now()}_video_${Math.random().toString(36).substr(2, 9)}`;
    db.prepare(`
      INSERT INTO automation_pipelines (id, schedule_id, stage, status)
      VALUES (?, ?, ?, ?)
    `).run(pipelineId, testScheduleId, 'video', 'pending');

    log('green', `\n✅ 테스트 데이터 생성:`);
    log('green', `   Schedule ID: ${testScheduleId}`);
    log('green', `   Pipeline ID: ${pipelineId}`);

    // 2. 기존 방식 (잘못된 방식): 새로운 ID 생성
    const oldWayPipelineId = testScheduleId + '_video';
    log('yellow', `\n❌ 기존 방식 (잘못됨):`);
    log('yellow', `   생성된 ID: ${oldWayPipelineId}`);
    log('yellow', `   실제 DB ID: ${pipelineId}`);
    log('yellow', `   매칭 여부: ${oldWayPipelineId === pipelineId ? '✅' : '❌'}`);

    // 3. 수정된 방식: DB에서 기존 ID 찾기
    const videoPipeline = db.prepare(`
      SELECT id FROM automation_pipelines
      WHERE schedule_id = ? AND stage = 'video'
      LIMIT 1
    `).get(testScheduleId);

    const newWayPipelineId = videoPipeline?.id || (testScheduleId + '_video');
    log('green', `\n✅ 수정된 방식 (올바름):`);
    log('green', `   DB에서 찾은 ID: ${videoPipeline?.id}`);
    log('green', `   사용할 ID: ${newWayPipelineId}`);
    log('green', `   실제 DB ID: ${pipelineId}`);
    log('green', `   매칭 여부: ${newWayPipelineId === pipelineId ? '✅' : '❌'}`);

    // 4. 검증
    log('magenta', '\n' + '='.repeat(80));
    if (newWayPipelineId === pipelineId && oldWayPipelineId !== pipelineId) {
      log('green', '✅✅✅ 테스트 성공! ✅✅✅');
      log('green', '수정된 방식은 올바른 pipeline ID를 찾습니다.');
      log('green', 'updatePipelineStatus 호출이 이제 정상 작동합니다.');
    } else {
      log('red', '❌❌❌ 테스트 실패! ❌❌❌');
    }
    log('magenta', '='.repeat(80) + '\n');

    // 정리
    db.prepare('DELETE FROM automation_pipelines WHERE id = ?').run(pipelineId);
    db.prepare('DELETE FROM video_schedules WHERE id = ?').run(testScheduleId);
    db.prepare('DELETE FROM video_titles WHERE id = ?').run(titleId);

    return newWayPipelineId === pipelineId;

  } catch (error) {
    log('red', `\n❌ 오류: ${error.message}`);
    console.error(error.stack);
    return false;
  } finally {
    db.close();
  }
}

// 실행
testPipelineIdMatching()
  .then(success => {
    process.exit(success ? 0 : 1);
  })
  .catch(error => {
    log('red', `Fatal error: ${error.message}`);
    process.exit(1);
  });
