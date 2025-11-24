const fs = require('fs');
const path = require('path');

console.log('🚀 uploads 폴더를 tasks 폴더로 마이그레이션 시작\n');

const backendPath = __dirname;
const uploadsPath = path.join(backendPath, 'uploads');
const tasksPath = path.join(backendPath, 'tasks');

// tasks 폴더가 없으면 생성
if (!fs.existsSync(tasksPath)) {
  fs.mkdirSync(tasksPath, { recursive: true });
  console.log('✅ tasks 폴더 생성됨');
}

// uploads 폴더 확인
if (!fs.existsSync(uploadsPath)) {
  console.log('⚠️ uploads 폴더가 없습니다.');
  process.exit(0);
}

// uploads 폴더의 모든 항목 읽기
const items = fs.readdirSync(uploadsPath);
console.log(`📁 uploads 폴더에 ${items.length}개 항목 발견\n`);

let movedCount = 0;
let skippedCount = 0;

for (const item of items) {
  const sourcePath = path.join(uploadsPath, item);
  const stats = fs.statSync(sourcePath);

  // 디렉토리만 처리
  if (stats.isDirectory()) {
    // uploaded_upload_ 형태인 경우
    if (item.startsWith('uploaded_upload_')) {
      // uploaded_upload_1763873873131_qk6rzqzdr -> task_1763873873131_qk6rzqzdr
      const newName = item.replace('uploaded_upload_', 'task_');
      const targetPath = path.join(tasksPath, newName);

      // 이미 존재하는지 확인
      if (fs.existsSync(targetPath)) {
        console.log(`⚠️ 이미 존재함: ${newName} (건너뜀)`);
        skippedCount++;
      } else {
        // 폴더 이동
        try {
          fs.renameSync(sourcePath, targetPath);
          console.log(`✅ 이동 완료: ${item} → tasks/${newName}`);
          movedCount++;
        } catch (error) {
          console.error(`❌ 이동 실패: ${item}`, error.message);
        }
      }
    } else if (item === 'chinese-converter') {
      // chinese-converter는 그대로 유지
      console.log(`ℹ️ ${item} 폴더는 유지`);
      skippedCount++;
    } else if (item.startsWith('uploaded_')) {
      // uploaded_ 형태도 task_로 변경
      const newName = item.replace('uploaded_', 'task_');
      const targetPath = path.join(tasksPath, newName);

      if (fs.existsSync(targetPath)) {
        console.log(`⚠️ 이미 존재함: ${newName} (건너뜀)`);
        skippedCount++;
      } else {
        try {
          fs.renameSync(sourcePath, targetPath);
          console.log(`✅ 이동 완료: ${item} → tasks/${newName}`);
          movedCount++;
        } catch (error) {
          console.error(`❌ 이동 실패: ${item}`, error.message);
        }
      }
    } else {
      console.log(`ℹ️ ${item} - 처리하지 않음 (uploaded_ 형태 아님)`);
      skippedCount++;
    }
  } else {
    // 파일은 건너뜀
    console.log(`ℹ️ ${item} - 파일 (건너뜀)`);
    skippedCount++;
  }
}

console.log('\n' + '='.repeat(60));
console.log('📊 마이그레이션 완료 요약:');
console.log(`   ✅ 이동된 폴더: ${movedCount}개`);
console.log(`   ⚠️ 건너뛴 항목: ${skippedCount}개`);
console.log('='.repeat(60));

// uploads 폴더가 비어있으면 삭제 제안
const remainingItems = fs.readdirSync(uploadsPath);
if (remainingItems.length === 0) {
  console.log('\n💡 uploads 폴더가 비어있습니다. 삭제해도 됩니다.');
} else if (remainingItems.length === 1 && remainingItems[0] === 'chinese-converter') {
  console.log('\n💡 uploads 폴더에 chinese-converter만 남아있습니다.');
} else {
  console.log(`\n📁 uploads 폴더에 ${remainingItems.length}개 항목이 남아있습니다:`);
  remainingItems.forEach(item => console.log(`   - ${item}`));
}