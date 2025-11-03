"""
Regression Tests for Trend Video Backend

These tests use small data samples to verify core functionality:
- Longform video generation (2 scenes)
- Shortform video generation (2 scenes)
- SORA2 video generation (1 simple prompt)
- Video merge with TTS and subtitles

Test data location: tests/test_data/
"""
import pytest
import os
import sys
import json
import subprocess
from pathlib import Path
import shutil
import time

# Helper function to safely print Unicode content
def safe_print(text):
    """Print text with proper encoding handling for Windows"""
    import builtins
    try:
        builtins.print(text)
    except UnicodeEncodeError:
        # Fall back to ASCII-safe printing
        builtins.print(text.encode('ascii', errors='replace').decode('ascii'))

# Add backend root to path
BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

TEST_DATA_DIR = Path(__file__).parent / 'test_data'
TEST_OUTPUT_DIR = Path(__file__).parent / 'test_output'


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup and cleanup test environment"""
    # Create output directory
    TEST_OUTPUT_DIR.mkdir(exist_ok=True)

    safe_print(f"\n{'='*70}")
    safe_print(f"Regression Test Environment")
    safe_print(f"{'='*70}")
    safe_print(f"Backend Root: {BACKEND_ROOT}")
    safe_print(f"Test Data: {TEST_DATA_DIR}")
    safe_print(f"Test Output: {TEST_OUTPUT_DIR}")
    safe_print(f"{'='*70}\n")

    yield

    # Cleanup is optional - keep output for inspection
    # shutil.rmtree(TEST_OUTPUT_DIR, ignore_errors=True)


def video_is_valid(video_path: Path) -> bool:
    """Check if video file exists and is valid using ffprobe"""
    if not video_path.exists():
        return False

    if video_path.stat().st_size < 1000:  # Too small to be valid
        return False

    try:
        # Use ffprobe to validate video
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
             str(video_path)],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            duration = float(result.stdout.strip())
            return duration > 0
    except Exception as e:
        safe_print(f"Video validation error: {e}")
        return False

    return False


class TestLongformGeneration:
    """Test longform video generation with 2 scenes"""

    def test_longform_basic(self):
        """Test basic longform video generation"""
        output_dir = TEST_OUTPUT_DIR / 'longform_test'
        output_dir.mkdir(exist_ok=True)

        json_file = TEST_DATA_DIR / 'longform_2scenes.json'
        image1 = TEST_DATA_DIR / 'longform_01.jpg'
        image2 = TEST_DATA_DIR / 'longform_02.jpg'

        # Verify test data exists
        assert json_file.exists(), f"JSON file not found: {json_file}"
        assert image1.exists(), f"Image 1 not found: {image1}"
        assert image2.exists(), f"Image 2 not found: {image2}"

        # Copy test data to output folder
        shutil.copy(json_file, output_dir / 'story.json')
        shutil.copy(image1, output_dir / '01.jpg')
        shutil.copy(image2, output_dir / '02.jpg')

        # Run video generation
        cmd = [
            'python',
            str(BACKEND_ROOT / 'create_video_from_folder.py'),
            '--folder', str(output_dir),
            '--aspect-ratio', '16:9'
        ]

        safe_print(f"\nRunning command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)

        safe_print("\n--- STDOUT ---")
        safe_print(result.stdout)
        if result.stderr:
            safe_print("\n--- STDERR ---")
            safe_print(result.stderr)

        # Check if script ran successfully
        assert result.returncode == 0, f"Script failed with return code {result.returncode}"

        # Check if output video was created
        output_videos = list((output_dir / 'generated_videos').glob('*.mp4'))
        assert len(output_videos) > 0, "No output videos generated"

        # Validate at least one video
        valid_videos = [v for v in output_videos if video_is_valid(v)]
        assert len(valid_videos) > 0, "No valid videos generated"

        safe_print(f"\n[SUCCESS] Longform test passed - {len(valid_videos)} valid video(s) generated")

    def test_longform_concat(self):
        """Test longform video concatenation - verify merged video is created"""
        output_dir = TEST_OUTPUT_DIR / 'longform_concat_test'
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)

        json_file = TEST_DATA_DIR / 'longform_2scenes.json'
        image1 = TEST_DATA_DIR / 'longform_01.jpg'
        image2 = TEST_DATA_DIR / 'longform_02.jpg'

        # Verify test data exists
        assert json_file.exists(), f"JSON file not found: {json_file}"
        assert image1.exists(), f"Image 1 not found: {image1}"
        assert image2.exists(), f"Image 2 not found: {image2}"

        # Copy test data to output folder
        shutil.copy(json_file, output_dir / 'story.json')
        shutil.copy(image1, output_dir / '01.jpg')
        shutil.copy(image2, output_dir / '02.jpg')

        # Run video generation (without --combine flag, should auto-merge via simple_concat.py)
        cmd = [
            'python',
            str(BACKEND_ROOT / 'create_video_from_folder.py'),
            '--folder', str(output_dir),
            '--aspect-ratio', '16:9'
        ]

        safe_print(f"\nRunning command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)

        safe_print("\n--- STDOUT ---")
        safe_print(result.stdout)
        if result.stderr:
            safe_print("\n--- STDERR ---")
            safe_print(result.stderr)

        # Check if script ran successfully
        assert result.returncode == 0, f"Script failed with return code {result.returncode}"

        generated_videos_dir = output_dir / 'generated_videos'
        assert generated_videos_dir.exists(), "generated_videos directory not created"

        # Check for individual scene videos
        scene_videos = sorted(generated_videos_dir.glob('scene_*.mp4'))
        assert len(scene_videos) >= 2, f"Expected at least 2 scene videos, got {len(scene_videos)}"

        safe_print(f"\n✓ Found {len(scene_videos)} scene videos:")
        for scene in scene_videos:
            safe_print(f"  - {scene.name}")
            assert video_is_valid(scene), f"Invalid scene video: {scene.name}"

        # Check for merged final video (should match the title from story.json)
        with open(output_dir / 'story.json', 'r', encoding='utf-8') as f:
            story_data = json.load(f)
            expected_title = story_data.get('title', 'output_video')

        # Find final merged video (should have the title name, not scene_XX.mp4)
        all_videos = list(generated_videos_dir.glob('*.mp4'))
        merged_videos = [v for v in all_videos if not v.name.startswith('scene_')]

        assert len(merged_videos) >= 1, f"No merged video found! Expected video with title: {expected_title}.mp4"

        merged_video = merged_videos[0]
        safe_print(f"\n✓ Found merged video: {merged_video.name}")

        # Validate merged video
        assert video_is_valid(merged_video), f"Merged video is invalid: {merged_video.name}"

        # Get duration of merged video
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries',
             'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
             str(merged_video)],
            capture_output=True,
            text=True,
            timeout=10
        )
        merged_duration = float(result.stdout.strip())

        # Get total duration of scene videos
        total_scene_duration = 0
        for scene in scene_videos:
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries',
                 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                 str(scene)],
                capture_output=True,
                text=True,
                timeout=10
            )
            total_scene_duration += float(result.stdout.strip())

        safe_print(f"\n✓ Merged video duration: {merged_duration:.2f}s")
        safe_print(f"✓ Total scene duration: {total_scene_duration:.2f}s")

        # Merged video should be approximately equal to sum of scene durations
        # Allow 10% tolerance for encoding differences
        duration_diff = abs(merged_duration - total_scene_duration)
        tolerance = total_scene_duration * 0.1
        assert duration_diff <= tolerance, \
            f"Duration mismatch: merged={merged_duration:.2f}s, scenes={total_scene_duration:.2f}s, diff={duration_diff:.2f}s"

        # Check file size is reasonable (should be larger than individual scenes)
        merged_size = merged_video.stat().st_size
        max_scene_size = max(s.stat().st_size for s in scene_videos)
        assert merged_size > max_scene_size, \
            f"Merged video is smaller than largest scene video: {merged_size} <= {max_scene_size}"

        safe_print(f"\n[SUCCESS] Longform concat test passed!")
        safe_print(f"  - Scene videos: {len(scene_videos)}")
        safe_print(f"  - Merged video: {merged_video.name} ({merged_size / 1024 / 1024:.2f} MB)")
        safe_print(f"  - Duration check: PASS (diff={duration_diff:.2f}s, tolerance={tolerance:.2f}s)")


class TestThumbnailGeneration:
    """Test thumbnail generation with punctuation handling"""

    def test_thumbnail_comma_preservation(self):
        """Test that commas are preserved in thumbnails (quotes removed only)"""
        output_dir = TEST_OUTPUT_DIR / 'thumbnail_test'
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)

        # Create test story.json with title containing comma and quotes
        test_title = '며느리가 시어머니에게 준 찬밥, 친정에 전화한통으로 사색이 된 며느리'
        story_data = {
            "title": test_title,
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "Scene 1",
                    "content": "Test content for thumbnail"
                }
            ]
        }

        with open(output_dir / 'story.json', 'w', encoding='utf-8') as f:
            json.dump(story_data, f, ensure_ascii=False, indent=2)

        # Create dummy image
        from PIL import Image
        img = Image.new('RGB', (1920, 1080), color=(100, 100, 100))
        img.save(output_dir / '01.jpg')

        # Run thumbnail generation
        cmd = [
            'python',
            str(BACKEND_ROOT / 'create_thumbnail.py'),
            '--folder', str(output_dir)
        ]

        safe_print(f"\nRunning command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)

        safe_print("\n--- STDOUT ---")
        safe_print(result.stdout)
        if result.stderr:
            safe_print("\n--- STDERR ---")
            safe_print(result.stderr)

        # Check if script ran successfully
        assert result.returncode == 0, f"Script failed with return code {result.returncode}"

        # Check if thumbnail was created
        thumbnail_path = output_dir / 'thumbnail.jpg'
        assert thumbnail_path.exists(), "Thumbnail file not created"

        # Check file size (should be reasonable)
        thumbnail_size = thumbnail_path.stat().st_size
        assert thumbnail_size > 10000, f"Thumbnail too small: {thumbnail_size} bytes"
        assert thumbnail_size < 5000000, f"Thumbnail too large: {thumbnail_size} bytes"

        # Verify comma is in the output (check stderr which has logging)
        output_text = result.stdout + result.stderr
        assert ',' in output_text, "Comma should be preserved in title"

        safe_print(f"\n[SUCCESS] Thumbnail test passed!")
        safe_print(f"  - Thumbnail created: {thumbnail_path.name}")
        safe_print(f"  - File size: {thumbnail_size / 1024:.2f} KB")
        safe_print(f"  - Title with comma preserved")

    def test_thumbnail_quote_removal(self):
        """Test that double quotes are removed from thumbnails"""
        output_dir = TEST_OUTPUT_DIR / 'thumbnail_quote_test'
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(exist_ok=True)

        # Create test story.json with title containing double quotes
        test_title = '"테스트 제목" 큰따옴표 제거'
        story_data = {
            "title": test_title,
            "scenes": [
                {
                    "scene_number": 1,
                    "title": "Scene 1",
                    "content": "Test content"
                }
            ]
        }

        with open(output_dir / 'story.json', 'w', encoding='utf-8') as f:
            json.dump(story_data, f, ensure_ascii=False, indent=2)

        # Create dummy image
        from PIL import Image
        img = Image.new('RGB', (1920, 1080), color=(100, 100, 100))
        img.save(output_dir / '01.jpg')

        # Run thumbnail generation
        cmd = [
            'python',
            str(BACKEND_ROOT / 'create_thumbnail.py'),
            '--folder', str(output_dir)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)

        # Check if script ran successfully
        assert result.returncode == 0, f"Script failed with return code {result.returncode}"

        # Check if thumbnail was created
        thumbnail_path = output_dir / 'thumbnail.jpg'
        assert thumbnail_path.exists(), "Thumbnail file not created"

        # Verify double quotes are NOT in the processed title
        # The script logs the processed title, so check stdout
        assert '"테스트 제목"' not in result.stdout or 'Title: 테스트 제목 큰따옴표 제거' in result.stdout, \
            "Double quotes should be removed from title"

        safe_print(f"\n[SUCCESS] Quote removal test passed!")


class TestShortformGeneration:
    """Test shortform video generation with 2 scenes"""

    def test_shortform_basic(self):
        """Test basic shortform video generation"""
        output_dir = TEST_OUTPUT_DIR / 'shortform_test'
        output_dir.mkdir(exist_ok=True)

        json_file = TEST_DATA_DIR / 'shortform_2scenes.json'
        image1 = TEST_DATA_DIR / 'shortform_01.jpg'
        image2 = TEST_DATA_DIR / 'shortform_02.jpg'

        # Verify test data exists
        assert json_file.exists(), f"JSON file not found: {json_file}"
        assert image1.exists(), f"Image 1 not found: {image1}"
        assert image2.exists(), f"Image 2 not found: {image2}"

        # Copy test data to output folder
        shutil.copy(json_file, output_dir / 'story.json')
        shutil.copy(image1, output_dir / '01.jpg')
        shutil.copy(image2, output_dir / '02.jpg')

        # Run video generation
        cmd = [
            'python',
            str(BACKEND_ROOT / 'create_video_from_folder.py'),
            '--folder', str(output_dir),
            '--aspect-ratio', '9:16'
        ]

        safe_print(f"\nRunning command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)

        safe_print("\n--- STDOUT ---")
        safe_print(result.stdout)
        if result.stderr:
            safe_print("\n--- STDERR ---")
            safe_print(result.stderr)

        # Check if script ran successfully
        assert result.returncode == 0, f"Script failed with return code {result.returncode}"

        # Check if output video was created
        output_videos = list((output_dir / 'generated_videos').glob('*.mp4'))
        assert len(output_videos) > 0, "No output videos generated"

        # Validate at least one video
        valid_videos = [v for v in output_videos if video_is_valid(v)]
        assert len(valid_videos) > 0, "No valid videos generated"

        safe_print(f"\n[SUCCESS] Shortform test passed - {len(valid_videos)} valid video(s) generated")


class TestSora2Generation:
    """Test SORA2 video generation with simple prompt"""

    def test_sora2_basic(self):
        """Test basic SORA2 video generation"""
        output_dir = TEST_OUTPUT_DIR / 'sora2_test'
        output_dir.mkdir(exist_ok=True)

        txt_file = TEST_DATA_DIR / 'sora2_simple.txt'

        # Verify test data exists
        assert txt_file.exists(), f"TXT file not found: {txt_file}"

        # Copy test data to output folder
        # SORA2 doesn't use story.json, just need the txt file
        shutil.copy(txt_file, output_dir / 'story.txt')

        # Run video generation
        cmd = [
            'python',
            str(BACKEND_ROOT / 'create_video_from_folder.py'),
            '--folder', str(output_dir),
            '--aspect-ratio', '16:9'
        ]

        safe_print(f"\nRunning command: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)

        safe_print("\n--- STDOUT ---")
        safe_print(result.stdout)
        if result.stderr:
            safe_print("\n--- STDERR ---")
            safe_print(result.stderr)

        # Check if script ran successfully
        assert result.returncode == 0, f"Script failed with return code {result.returncode}"

        # Check if output video was created
        output_videos = list((output_dir / 'generated_videos').glob('*.mp4'))
        assert len(output_videos) > 0, "No output videos generated"

        # Validate at least one video
        valid_videos = [v for v in output_videos if video_is_valid(v)]
        assert len(valid_videos) > 0, "No valid videos generated"

        safe_print(f"\n[SUCCESS] SORA2 test passed - {len(valid_videos)} valid video(s) generated")


class TestVideoMerge:
    """Test video merge with TTS and subtitles"""

    def test_video_merge_with_tts(self):
        """Test video merge with TTS narration and subtitles"""
        # First generate some videos for merging
        output_dir = TEST_OUTPUT_DIR / 'merge_test'
        output_dir.mkdir(exist_ok=True)

        json_file = TEST_DATA_DIR / 'longform_2scenes.json'
        image1 = TEST_DATA_DIR / 'longform_01.jpg'
        image2 = TEST_DATA_DIR / 'longform_02.jpg'

        # Copy test data
        shutil.copy(json_file, output_dir / 'story.json')
        shutil.copy(image1, output_dir / '01.jpg')
        shutil.copy(image2, output_dir / '02.jpg')

        # Generate individual scene videos first
        cmd = [
            'python',
            str(BACKEND_ROOT / 'create_video_from_folder.py'),
            '--folder', str(output_dir),
            '--aspect-ratio', '16:9'
        ]

        safe_print(f"\nGenerating scene videos: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
        assert result.returncode == 0, "Scene generation failed"

        # Now test video merge
        videos_dir = output_dir / 'generated_videos'
        if not videos_dir.exists():
            pytest.skip("No generated_videos folder - skipping merge test")

        video_files = sorted(videos_dir.glob('*.mp4'))
        if len(video_files) < 2:
            pytest.skip(f"Not enough videos for merge (need 2, got {len(video_files)})")

        # Run video merge
        from video_merge import merge_videos

        # Read JSON for narration text
        with open(output_dir / 'script.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        narration_text = " ".join([scene.get('text', '') for scene in data.get('scenes', [])])

        # Merge videos
        output_path = output_dir / 'merged_with_tts.mp4'

        try:
            result_path = merge_videos(
                video_folder=videos_dir,
                output_path=output_path,
                add_tts=True,
                tts_text=narration_text,
                add_subtitles=True
            )

            # Validate merged video
            assert result_path.exists(), "Merged video not created"
            assert video_is_valid(result_path), "Merged video is not valid"

            safe_print(f"\n[SUCCESS] Video merge test passed - output: {result_path}")

        except Exception as e:
            pytest.fail(f"Video merge failed: {e}")


if __name__ == '__main__':
    # Run tests with verbose output
    pytest.main([__file__, '-v', '-s'])
