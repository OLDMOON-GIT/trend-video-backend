/**
 * 롱폼 비디오 concat 통합 테스트
 *
 * 테스트 항목:
 * 1. 모든 씬이 동일한 비디오 파라미터를 가지는지 (해상도, fps)
 * 2. 모든 씬이 동일한 오디오 파라미터를 가지는지 (sample_rate, channels)
 * 3. 모든 씬에 .ass 자막 파일이 있는지
 * 4. concat demuxer로 병합 시 타임스탬프 경고가 없는지
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// 테스트할 프로젝트 경로 (인자로 받거나 기본값)
const PROJECT_DIR = process.argv[2] || 'C:\\Users\\oldmoon\\workspace\\trend-video-backend\\input\\project_197951ed-d849-4c50-97c5-2282bb8e7b56';
const VIDEOS_DIR = path.join(PROJECT_DIR, 'generated_videos');

console.log('\n롱폼 비디오 Concat 통합 테스트');
console.log('='.repeat(70));
console.log(`프로젝트: ${PROJECT_DIR}\n`);

const results = {
  totalTests: 0,
  passed: 0,
  failed: 0,
  details: []
};

function test(name, condition, details = '') {
  results.totalTests++;
  if (condition) {
    results.passed++;
    console.log(`✅ PASS: ${name}`);
    if (details) console.log(`   ${details}`);
  } else {
    results.failed++;
    console.log(`❌ FAIL: ${name}`);
    if (details) console.log(`   ${details}`);
  }
  results.details.push({ name, passed: condition, details });
}

// 폴더 존재 확인
if (!fs.existsSync(VIDEOS_DIR)) {
  console.error(`❌ 비디오 폴더가 없습니다: ${VIDEOS_DIR}`);
  process.exit(1);
}

// 모든 scene 파일 찾기
const files = fs.readdirSync(VIDEOS_DIR)
  .filter(f => f.match(/^scene_\d+\.mp4$/))
  .sort((a, b) => {
    const numA = parseInt(a.match(/scene_(\d+)\.mp4/)[1]);
    const numB = parseInt(b.match(/scene_(\d+)\.mp4/)[1]);
    return numA - numB;
  });

console.log(`발견된 씬: ${files.length}개\n`);

// 씬 파라미터 수집
const sceneParams = [];
files.forEach(f => {
  const scenePath = path.join(VIDEOS_DIR, f);
  const sceneNum = f.match(/scene_(\d+)\.mp4/)[1];

  // 비디오 파라미터
  const videoParams = execSync(
    `ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate,codec_name -of csv=p=0 "${scenePath}"`,
    { encoding: 'utf-8' }
  ).trim().split(',');

  // 오디오 파라미터
  const audioParams = execSync(
    `ffprobe -v error -select_streams a:0 -show_entries stream=sample_rate,channels,codec_name -of csv=p=0 "${scenePath}"`,
    { encoding: 'utf-8' }
  ).trim().split(',');

  sceneParams.push({
    file: f,
    num: sceneNum,
    video: {
      codec: videoParams[0],
      width: parseInt(videoParams[1]),
      height: parseInt(videoParams[2]),
      fps: videoParams[3]
    },
    audio: {
      codec: audioParams[0],
      sampleRate: parseInt(audioParams[1]),
      channels: parseInt(audioParams[2])
    }
  });
});

// Test 1: 비디오 파라미터 일관성
console.log('='.repeat(70));
console.log('Test 1: 비디오 파라미터 일관성\n');

const firstVideo = sceneParams[0].video;
let videoConsistent = true;
let videoInconsistencies = [];

sceneParams.forEach(scene => {
  const v = scene.video;
  if (v.width !== firstVideo.width || v.height !== firstVideo.height || v.fps !== firstVideo.fps) {
    videoConsistent = false;
    videoInconsistencies.push(`${scene.file}: ${v.width}x${v.height} @ ${v.fps}`);
  }
});

test(
  '모든 씬이 동일한 비디오 파라미터',
  videoConsistent,
  videoConsistent
    ? `모두 ${firstVideo.width}x${firstVideo.height} @ ${firstVideo.fps}`
    : `불일치 발견:\n     기준: ${firstVideo.width}x${firstVideo.height} @ ${firstVideo.fps}\n     ${videoInconsistencies.join('\n     ')}`
);

// Test 2: 오디오 파라미터 일관성
console.log('\n' + '='.repeat(70));
console.log('Test 2: 오디오 파라미터 일관성\n');

const firstAudio = sceneParams[0].audio;
let audioConsistent = true;
let audioInconsistencies = [];

sceneParams.forEach(scene => {
  const a = scene.audio;
  if (a.sampleRate !== firstAudio.sampleRate || a.channels !== firstAudio.channels) {
    audioConsistent = false;
    audioInconsistencies.push(`${scene.file}: ${a.sampleRate}Hz ${a.channels}ch`);
  }
});

test(
  '모든 씬이 동일한 오디오 파라미터',
  audioConsistent,
  audioConsistent
    ? `모두 ${firstAudio.sampleRate}Hz ${firstAudio.channels}ch`
    : `불일치 발견:\n     기준: ${firstAudio.sampleRate}Hz ${firstAudio.channels}ch\n     ${audioInconsistencies.join('\n     ')}`
);

// Test 3: ASS 자막 파일 존재
console.log('\n' + '='.repeat(70));
console.log('Test 3: ASS 자막 파일 존재\n');

let allHaveAss = true;
let missingAss = [];

files.forEach(f => {
  const sceneNum = f.match(/scene_(\d+)\.mp4/)[1];
  const assFile = path.join(VIDEOS_DIR, `scene_${sceneNum}_audio.ass`);

  if (!fs.existsSync(assFile)) {
    allHaveAss = false;
    missingAss.push(`scene_${sceneNum}_audio.ass`);
  }
});

test(
  '모든 씬에 ASS 자막 파일 존재',
  allHaveAss,
  allHaveAss
    ? `${files.length}개 씬 모두 .ass 파일 있음`
    : `누락: ${missingAss.join(', ')}`
);

// Test 4: Concat 시뮬레이션 (타임스탬프 경고 체크)
console.log('\n' + '='.repeat(70));
console.log('Test 4: Concat 시뮬레이션 (타임스탬프 체크)\n');

if (videoConsistent && audioConsistent) {
  const tempDir = path.join(PROJECT_DIR, 'temp_test');
  if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir, { recursive: true });
  }

  const concatList = files.map(f => `file '${path.join(VIDEOS_DIR, f).replace(/\\/g, '/')}'`).join('\n');
  const concatListPath = path.join(tempDir, 'test_concat_list.txt');
  fs.writeFileSync(concatListPath, concatList, 'utf-8');

  const testOutputPath = path.join(tempDir, 'test_output.mp4');

  try {
    const result = execSync(
      `ffmpeg -y -f concat -safe 0 -i "${concatListPath}" -c copy -t 1 "${testOutputPath}" 2>&1`,
      { encoding: 'utf-8' }
    );

    // 타임스탬프 경고 체크
    const hasTimestampWarnings = result.includes('Non-monotonic DTS');

    test(
      'Concat 시 타임스탬프 경고 없음',
      !hasTimestampWarnings,
      hasTimestampWarnings
        ? '타임스탬프 경고 발견 - 오디오 파라미터 불일치 가능성'
        : 'concat demuxer 정상 작동'
    );

  } catch (error) {
    test(
      'Concat 시 타임스탬프 경고 없음',
      false,
      `FFmpeg 오류: ${error.message.substring(0, 100)}`
    );
  } finally {
    // 정리
    if (fs.existsSync(tempDir)) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  }
} else {
  test(
    'Concat 시 타임스탬프 경고 없음',
    false,
    '비디오 또는 오디오 파라미터 불일치로 인해 테스트 건너뜀'
  );
}

// 최종 결과
console.log('\n' + '='.repeat(70));
console.log('테스트 결과 요약\n');

console.log(`총 테스트: ${results.totalTests}개`);
console.log(`✅ 성공: ${results.passed}개`);
console.log(`❌ 실패: ${results.failed}개`);
console.log(`성공률: ${((results.passed / results.totalTests) * 100).toFixed(1)}%`);

console.log('\n' + '='.repeat(70));

if (results.failed === 0) {
  console.log('🎉 모든 테스트 통과!');
  console.log('\n✅ Concat 준비 완료:');
  console.log('  • 모든 씬의 비디오 파라미터가 일치');
  console.log('  • 모든 씬의 오디오 파라미터가 일치');
  console.log('  • 모든 씬에 .ass 자막 파일 존재');
  console.log('  • concat demuxer로 빠르게 병합 가능');
  process.exit(0);
} else {
  console.log('❌ 일부 테스트 실패\n');
  console.log('실패한 테스트:');
  results.details
    .filter(d => !d.passed)
    .forEach(d => console.log(`  • ${d.name}`));

  console.log('\n⚠️  권장 조치:');
  if (!videoConsistent || !audioConsistent) {
    console.log('  1. 불일치한 씬들을 통일된 파라미터로 재변환');
    console.log('  2. concat filter를 사용하여 병합 (느리지만 안전)');
  }
  if (!allHaveAss) {
    console.log('  3. 누락된 .ass 파일 생성');
  }

  process.exit(1);
}
