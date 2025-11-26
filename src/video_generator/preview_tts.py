#!/usr/bin/env python3
"""
TTS 미리듣기 샘플 생성 스크립트
"""
import asyncio
import sys
import edge_tts
import os
import argparse
from pathlib import Path

async def generate_preview(voice: str, speed: float, output_path: str):
    """
    TTS 미리듣기 샘플 생성

    Args:
        voice: TTS 음성 ID (예: ko-KR-SunHiNeural)
        speed: 재생 속도 (0.5 ~ 2.0)
        output_path: 출력 파일 경로
    """
    # 샘플 텍스트
    sample_text = "안녕하세요, 이 음성으로 영상을 제작합니다."

    # 속도 조절 (edge-tts는 rate를 -50% ~ +100% 형식으로 받음)
    # speed 1.0 = +0%, 0.5 = -50%, 2.0 = +100%
    rate_percent = int((speed - 1.0) * 100)
    rate = f"{rate_percent:+d}%"

    # TTS 생성
    communicate = edge_tts.Communicate(sample_text, voice, rate=rate)
    await communicate.save(output_path)

    return output_path

def main():
    parser = argparse.ArgumentParser(description='TTS 미리듣기 샘플 생성')
    parser.add_argument('--voice', required=True, help='TTS 음성 ID')
    parser.add_argument('--speed', type=float, default=1.0, help='재생 속도 (0.5 ~ 2.0)')
    parser.add_argument('--output', required=True, help='출력 파일 경로')

    args = parser.parse_args()

    # 출력 디렉토리 생성
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 비동기 실행
    try:
        asyncio.run(generate_preview(args.voice, args.speed, args.output))
        print(f"[OK] TTS preview sample created: {args.output}")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] TTS preview creation failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
