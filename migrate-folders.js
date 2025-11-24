/**
 * Migrate all project_* folders to tasks/task_* structure
 */
const fs = require('fs');
const path = require('path');

const inputDir = path.join(__dirname, 'input');
const tasksDir = path.join(inputDir, 'tasks');

// Ensure tasks directory exists
if (!fs.existsSync(tasksDir)) {
  fs.mkdirSync(tasksDir, { recursive: true });
  console.log('✅ Created tasks/ directory');
}

// Get all project_* directories
const entries = fs.readdirSync(inputDir, { withFileTypes: true });
const projectDirs = entries.filter(entry =>
  entry.isDirectory() && entry.name.startsWith('project_') && entry.name !== 'tasks'
);

console.log(`📁 Found ${projectDirs.length} project folders to migrate\n`);

let successCount = 0;
let errorCount = 0;

// Move each project_* folder to tasks/task_*
for (const dir of projectDirs) {
  const oldName = dir.name;
  const newName = oldName.replace('project_', 'task_');
  const oldPath = path.join(inputDir, oldName);
  const newPath = path.join(tasksDir, newName);

  try {
    // Check if target already exists
    if (fs.existsSync(newPath)) {
      console.log(`⚠️  Skip: ${newName} already exists`);
      continue;
    }

    // Move the folder
    fs.renameSync(oldPath, newPath);
    console.log(`✅ Moved: ${oldName} → tasks/${newName}`);
    successCount++;
  } catch (error) {
    console.error(`❌ Error moving ${oldName}: ${error.message}`);
    errorCount++;
  }
}

console.log(`\n📊 Migration complete:`);
console.log(`   ✅ Success: ${successCount}`);
console.log(`   ❌ Errors: ${errorCount}`);
console.log(`   ⚠️  Skipped: ${projectDirs.length - successCount - errorCount}`);
