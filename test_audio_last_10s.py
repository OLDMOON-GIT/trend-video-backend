#!/usr/bin/env python3
"""
롱폼 비디오 마지막 10초 오디오 체크 테스트
- 마지막 10초 구간에 오디오가 있는지 검증
- RMS (Root Mean Square) 값으로 음성 유무 판단
"""
import subprocess
import sys
from pathlib import Path


def check_last_10s_audio(video_path: Path, threshold: float = 0.001) -> dict:
    """
    비디오 마지막 10초에 오디오가 있는지 체크

    Args:
        video_path: 비디오 파일 경로
        threshold: 오디오 존재 판단 임계값 (RMS)

    Returns:
        dict: {
            'has_audio': bool,
            'duration': float,
            'rms_last_10s': float,
            'pass': bool
        }
    """
    if not video_path.exists():
        return {
            'has_audio': False,
            'duration': 0,
            'rms_last_10s': 0,
            'pass': False,
            'error': f'File not found: {video_path}'
        }

    try:
        # 1. 전체 길이 확인
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        duration = float(result.stdout.strip())

        if duration < 10:
            return {
                'has_audio': False,
                'duration': duration,
                'rms_last_10s': 0,
                'pass': False,
                'error': f'Video too short: {duration}s < 10s'
            }

        # 2. 마지막 10초 오디오의 RMS 값 측정
        start_time = duration - 10
        cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-t', '10',
            '-i', str(video_path),
            '-af', 'astats=metadata=1:reset=1',
            '-f', 'null',
            '-'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        stderr = result.stderr

        # RMS 값 추출 (여러 줄 중 평균)
        rms_values = []
        for line in stderr.split('\n'):
            if 'RMS level dB' in line or 'RMS_level' in line:
                try:
                    # [Parsed_astats_0 @ ...] lavfi.astats.1.RMS_level: -30.5
                    parts = line.split(':')
                    if len(parts) >= 2:
                        value = float(parts[-1].strip())
                        # dB 값을 선형 스케일로 변환 (대략적)
                        # -60dB ≈ 0.001, -30dB ≈ 0.03
                        if value < -50:  # 매우 작은 값
                            linear = 10 ** (value / 20)
                            rms_values.append(linear)
                except:
                    continue

        # volumedetect로 체크 (더 정확함)
        cmd = [
            'ffmpeg',
            '-ss', str(start_time),
            '-t', '10',
            '-i', str(video_path),
            '-af', 'volumedetect',
            '-f', 'null',
            '-'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        stderr = result.stderr

        # mean_volume 추출
        has_audio = False
        avg_rms = 0.0
        for line in stderr.split('\n'):
            if 'mean_volume:' in line:
                try:
                    # [Parsed_volumedetect_0 @ ...] mean_volume: -25.5 dB
                    parts = line.split('mean_volume:')
                    if len(parts) >= 2:
                        value_str = parts[1].strip().replace('dB', '').strip()
                        db_value = float(value_str)
                        # -50dB 이하는 거의 무음으로 간주
                        has_audio = db_value > -50
                        avg_rms = 1.0 if has_audio else 0.0
                        break
                except Exception as e:
                    print(f"Parse error: {e}, line: {line}")
                    continue

        return {
            'has_audio': has_audio,
            'duration': duration,
            'rms_last_10s': avg_rms,
            'pass': has_audio,
            'threshold': threshold
        }

    except Exception as e:
        return {
            'has_audio': False,
            'duration': 0,
            'rms_last_10s': 0,
            'pass': False,
            'error': str(e)
        }


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python test_audio_last_10s.py <video_path>")
        sys.exit(1)

    video_path = Path(sys.argv[1])
    result = check_last_10s_audio(video_path)

    print(f"\n{'='*60}")
    print(f"Video: {video_path.name}")
    print(f"{'='*60}")
    print(f"Duration: {result.get('duration', 0):.2f}s")
    print(f"RMS (last 10s): {result.get('rms_last_10s', 0):.6f}")
    print(f"Threshold: {result.get('threshold', 0.001):.6f}")
    print(f"Has audio in last 10s: {'YES' if result.get('has_audio') else 'NO'}")
    print(f"{'='*60}")

    if 'error' in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)

    if result['pass']:
        print("✓ TEST PASSED - Audio present in last 10 seconds")
        sys.exit(0)
    else:
        print("✗ TEST FAILED - No audio in last 10 seconds")
        sys.exit(1)
