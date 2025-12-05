
import subprocess
import os
import shutil
from pathlib import Path
import json
from PIL import Image

# --- Configuration ---
TEST_TASK_ID = "test_BTS-0000442"
BACKEND_ROOT = Path(__file__).parent.parent.parent
TASKS_DIR = BACKEND_ROOT / "tasks"
INPUT_FOLDER = TASKS_DIR / TEST_TASK_ID
VIDEO_GENERATOR_SCRIPT = BACKEND_ROOT / "src" / "video_generator" / "create_video_from_folder.py"

# --- Setup Test Environment ---
def setup_test_environment():
    print(f"Setting up test environment in {INPUT_FOLDER}...")
    if INPUT_FOLDER.exists():
        shutil.rmtree(INPUT_FOLDER)
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    # Create dummy story.json
    story_json_content = {
      "title": "완료 탭 썸네일 개선",
      "scenes": [
        {
          "sceneNumber": 1,
          "narration": "이것은 완료 탭 썸네일 버그를 위한 테스트 시나리오입니다.",
          "imagePrompt": "A highly detailed, vibrant image of a happy person looking at a beautiful thumbnail."
        }
      ]
    }
    (INPUT_FOLDER / "story.json").write_text(json.dumps(story_json_content, indent=2, ensure_ascii=False))
    print(f"Created dummy story.json: {INPUT_FOLDER / 'story.json'}")

    # Create dummy image
    try:
        img = Image.new('RGB', (1920, 1080), color = 'red')
        img.save(INPUT_FOLDER / "01.png")
        print(f"Created dummy image: {INPUT_FOLDER / '01.png'}")
    except ImportError:
        print("Pillow not installed. Please install it (`pip install Pillow`) or place a dummy 01.png manually.")
        (INPUT_FOLDER / "01.png").write_text("Dummy image content if Pillow not available") # Fallback, though not a real image

    print(f"Test environment set up in {INPUT_FOLDER}")

# --- Run Video Generation Script ---
def run_video_generation():
    # Pass the folder path relative to the backend root, as create_video_from_folder.py expects it.
    # The --folder argument takes the project name, which is the folder name inside 'tasks'
    folder_name_relative_to_backend_root = INPUT_FOLDER.relative_to(BACKEND_ROOT)

    python_args = [
        "python",
        str(VIDEO_GENERATOR_SCRIPT),
        "--folder", str(folder_name_relative_to_backend_root), 
        "--image-source", "none", # Using the placeholder image
        "--aspect-ratio", "16:9",
        "--voice", "ko-KR-SoonBokNeural", # Example voice
        "--speed", "1.0",
        "--image-provider", "openai",
        "--job-id", TEST_TASK_ID
    ]

    print(f"\nRunning command: {' '.join(python_args)}")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    process = subprocess.Popen(
        python_args,
        cwd=BACKEND_ROOT, # Execute from backend root
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        env=env # Pass the modified environment variables
    )

    stdout, stderr = process.communicate()

    print("\n--- STDOUT ---")
    print(stdout)
    print("\n--- STDERR ---")
    print(stderr)
    print(f"\nProcess exited with code: {process.returncode}")

# --- Main Execution ---
if __name__ == "__main__":
    setup_test_environment()
    run_video_generation()
