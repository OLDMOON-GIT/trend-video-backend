#!/usr/bin/env python3
"""
전체 롱폼 비디오 생성 테스트 및 마지막 10초 오디오 검증
"""
import asyncio
import json
import sys
from pathlib import Path
from video_merge import generate_tts, add_audio_to_video, concatenate_videos
from test_audio_last_10s import check_last_10s_audio


async def test_full_generation(task_dir: Path):
    """전체 롱폼 비디오 생성 테스트"""

    # story.json 읽기
    with open(task_dir / 'story.json', 'r', encoding='utf-8') as f:
        story = json.load(f)

    scenes = story.get('scenes', [])
    media_files = [task_dir / '01.mp4'] + [task_dir / f'{i:02d}.png' for i in range(2, 9)]

    gen_dir = task_dir / 'generated_videos_test'
    gen_dir.mkdir(exist_ok=True)

    scene_videos = []

    print(f"\n{'='*60}")
    print(f"Starting longform video generation test")
    print(f"Scenes: {len(scenes)}")
    print(f"Media files: {len(media_files)}")
    print(f"{'='*60}\n")

    for i, scene in enumerate(scenes):
        narration = scene.get('narration', '').strip()
        if not narration:
            continue

        print(f'\nProcessing scene {i+1}/{len(scenes)}...')

        # 미디어 선택
        media_idx = min(i, len(media_files) - 1)
        media_path = media_files[media_idx]

        # TTS 생성
        audio_path = gen_dir / f'scene_{i+1:02d}_audio.mp3'
        tts_path, subtitle_data = await generate_tts(narration, audio_path, 'ko-KR-SunHiNeural')

        # 비디오 생성
        video_path = gen_dir / f'scene_{i+1:02d}.mp4'
        add_audio_to_video(media_path, tts_path, video_path, narration, True, subtitle_data)

        scene_videos.append(video_path)

        # 각 씬 비디오의 마지막 10초 오디오 체크
        result = check_last_10s_audio(video_path)
        status = "PASS" if result['pass'] else "FAIL"
        print(f"  Scene {i+1} audio check: {status} (duration: {result['duration']:.2f}s)")

    # 병합
    print(f'\n{"="*60}')
    print(f'Merging {len(scene_videos)} scenes...')
    print(f'{"="*60}\n')

    final_output = gen_dir / 'final_merged.mp4'
    concatenate_videos(scene_videos, final_output)

    print(f'\nMerge complete: {final_output}')

    # 최종 병합 비디오의 마지막 10초 오디오 체크
    print(f'\n{"="*60}')
    print(f'Final audio check...')
    print(f'{"="*60}\n')

    result = check_last_10s_audio(final_output)

    print(f"Duration: {result['duration']:.2f}s")
    print(f"Has audio in last 10s: {'YES' if result['has_audio'] else 'NO'}")

    if result['pass']:
        print(f"\n*** TEST PASSED ***")
        return 0
    else:
        print(f"\n*** TEST FAILED ***")
        return 1


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_full_longform.py <task_dir>")
        sys.exit(1)

    task_dir = Path(sys.argv[1])
    exit_code = asyncio.run(test_full_generation(task_dir))
    sys.exit(exit_code)
