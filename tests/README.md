# Regression Tests for Trend Video Backend

## Overview

These regression tests verify core functionality using small test data:
- **Longform video generation** (2 scenes + concatenation)
- **Thumbnail generation** (comma preservation, quote removal)
- **Shortform video generation** (2 scenes)
- **SORA2 video generation** (1 simple prompt) - *currently skipped*
- **Video merge with TTS and subtitles** - *currently skipped*
- **Process control** (STOP signal detection)
- **TTS functions** (timestamp formatting, subtitle generation)
- **File safety** (filename sanitization, Unicode preservation)
- **Edge cases** (empty text, long text, special characters)
- **Video quality** (resolution, audio stream detection)

## Test Data

Location: `tests/test_data/`

### Files
- `longform_2scenes.json` - 2-scene longform script (16:9)
- `shortform_2scenes.json` - 2-scene shortform script (9:16)
- `sora2_simple.txt` - Simple SORA2 prompt
- `longform_01.jpg`, `longform_02.jpg` - Test images for longform
- `shortform_01.jpg`, `shortform_02.jpg` - Test images for shortform

### Regenerating Test Images

If test images are missing or corrupted:

```bash
cd tests/test_data
python create_test_images.py
```

## Prerequisites

1. **Python dependencies** (from backend root):
   ```bash
   pip install -r requirements.txt
   pip install pytest
   ```

2. **FFmpeg** must be installed and in PATH

3. **Edge TTS** for narration (automatically installed with requirements)

## Running Tests

### Run all tests
```bash
python -m pytest tests/test_regression.py -v
```

### Run specific test class
```bash
# Longform generation
python -m pytest tests/test_regression.py::TestLongformGeneration -v

# Thumbnail generation
python -m pytest tests/test_regression.py::TestThumbnailGeneration -v

# Shortform generation
python -m pytest tests/test_regression.py::TestShortformGeneration -v

# SORA2 (currently skipped)
python -m pytest tests/test_regression.py::TestSora2Generation -v

# Video merge (currently skipped)
python -m pytest tests/test_regression.py::TestVideoMerge -v

# Process control
python -m pytest tests/test_regression.py::TestProcessControl -v

# TTS functions
python -m pytest tests/test_regression.py::TestTTSFunctions -v

# File safety
python -m pytest tests/test_regression.py::TestFileSafety -v

# Edge cases
python -m pytest tests/test_regression.py::TestEdgeCases -v

# Video quality
python -m pytest tests/test_regression.py::TestVideoQuality -v
```

### Run with output displayed
```bash
python -m pytest tests/test_regression.py -v -s
```

### Direct execution
```bash
python tests/test_regression.py
```

## Test Output

Test outputs are saved to `tests/test_output/`:
- `longform_test/` - Longform generation outputs
- `longform_concat_test/` - Longform concatenation test outputs
- `thumbnail_test/` - Thumbnail generation test outputs
- `thumbnail_quote_test/` - Quote removal test outputs
- `shortform_test/` - Shortform generation outputs
- `sora2_test/` - SORA2 generation outputs (skipped)
- `merge_test/` - Video merge outputs (skipped)
- `process_control_test/` - Process control test outputs
- `process_controller_init/` - Process controller initialization
- `subtitle_test/` - Subtitle generation test outputs
- `edge_case_test/` - Edge case test outputs

**Note**: These folders are kept after test runs for inspection. Delete manually if needed.

## Success Criteria

### Video Generation Tests
Each test passes if:
1. ✅ Script exits with code 0
2. ✅ Output video file is created
3. ✅ Video file is valid (can be opened by ffprobe)
4. ✅ Video has non-zero duration

### Unit Tests
Each test passes if:
1. ✅ Function returns expected output
2. ✅ Edge cases are handled correctly
3. ✅ Files are created with proper structure
4. ✅ Unicode and special characters are preserved/sanitized correctly

### Current Test Count
- **18 tests passing**
- **2 tests skipped** (SORA2, VideoMerge - require API updates)
- **0 tests failing**

## When to Update Tests

From `DEVELOPMENT_GUIDE.md`:

> **Regression tests should be updated when:**
> 1. A stable version is ready to push
> 2. Core functionality changes (new formats, new features)
> 3. Critical bugs are fixed (add test to prevent regression)

**DO NOT** update tests for:
- Minor UI changes
- Performance optimizations (unless they affect output)
- Non-functional refactoring

## Debugging Failed Tests

### Check test output folder
```bash
ls tests/test_output/longform_test/generated_videos/
```

### Run single test with full output
```bash
python -m pytest tests/test_regression.py::TestLongformGeneration::test_longform_basic -v -s
```

### Check video with ffprobe
```bash
ffprobe tests/test_output/longform_test/generated_videos/*.mp4
```

### Common issues
1. **FFmpeg not found**: Install FFmpeg and add to PATH
2. **Edge TTS timeout**: Network issue, retry test
3. **Invalid video**: Check backend logs in test stdout
4. **Missing dependencies**: Run `pip install -r requirements.txt`

## Notes

- Tests use small data (2 scenes) for speed
- Each test is independent (can run in any order)
- Test data is version-controlled
- Test output is NOT version-controlled (in .gitignore)
- Tests may take 2-5 minutes each (video generation is slow)
