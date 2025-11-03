# Regression Tests for Trend Video Backend

## Overview

These regression tests verify core functionality using small test data:
- **Longform video generation** (2 scenes)
- **Shortform video generation** (2 scenes)
- **SORA2 video generation** (1 simple prompt)
- **Video merge with TTS and subtitles**

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
# Longform only
python -m pytest tests/test_regression.py::TestLongformGeneration -v

# Shortform only
python -m pytest tests/test_regression.py::TestShortformGeneration -v

# SORA2 only
python -m pytest tests/test_regression.py::TestSora2Generation -v

# Video merge only
python -m pytest tests/test_regression.py::TestVideoMerge -v
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
- `shortform_test/` - Shortform generation outputs
- `sora2_test/` - SORA2 generation outputs
- `merge_test/` - Video merge outputs

**Note**: These folders are kept after test runs for inspection. Delete manually if needed.

## Success Criteria

Each test passes if:
1. ✅ Script exits with code 0
2. ✅ Output video file is created
3. ✅ Video file is valid (can be opened by ffprobe)
4. ✅ Video has non-zero duration

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
