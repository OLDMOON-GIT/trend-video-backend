#!/usr/bin/env python3
"""
TTS 미리듣기 샘플 파일 사전 생성 스크립트
"""
import asyncio
import os
import sys
from pathlib import Path
import edge_tts

# Windows UTF-8 출력 설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Google Cloud TTS (선택적)
try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False

# AWS Polly (선택적)
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    AWS_POLLY_AVAILABLE = True
except ImportError:
    AWS_POLLY_AVAILABLE = False

# Edge TTS 음성 목록 (무료)
EDGE_VOICES = [
    # 여성 음성
    'ko-KR-SunHiNeural',
    'ko-KR-JiMinNeural',
    'ko-KR-SeoHyeonNeural',
    'ko-KR-SoonBokNeural',
    'ko-KR-YuJinNeural',
    # 남성 음성
    'ko-KR-InJoonNeural',
    'ko-KR-HyunsuMultilingualNeural',
    'ko-KR-BongJinNeural',
    'ko-KR-GookMinNeural',
    'ko-KR-HyunsuNeural',
]

# Google Cloud TTS 음성 목록 (프리미엄)
GOOGLE_VOICES = [
    'google-ko-KR-Neural2-A',
    'google-ko-KR-Neural2-B',
    'google-ko-KR-Neural2-C',
    'google-ko-KR-Wavenet-D',
]

# AWS Polly 음성 목록 (프리미엄)
AWS_VOICES = [
    'aws-Seoyeon',
    'aws-Jihye',
]

# 속도 목록
SPEEDS = [0.5, 1.0, 1.5, 2.0]

# 샘플 텍스트
SAMPLE_TEXT = "안녕하세요, 이 음성으로 영상을 제작합니다."

async def generate_edge_sample(voice: str, speed: float, output_dir: Path):
    """Edge TTS 샘플 생성"""
    # 속도 조절 (edge-tts는 rate를 -50% ~ +100% 형식으로 받음)
    rate_percent = int((speed - 1.0) * 100)
    rate = f"{rate_percent:+d}%"

    # 파일명: sample_음성ID_속도.mp3
    filename = f"sample_{voice}_{speed}.mp3"
    output_path = output_dir / filename

    # 파일이 이미 있으면 스킵
    if output_path.exists():
        size_kb = output_path.stat().st_size / 1024
        return filename, size_kb, True

    # TTS 생성
    communicate = edge_tts.Communicate(SAMPLE_TEXT, voice, rate=rate)
    await communicate.save(str(output_path))

    # 파일 크기 확인
    size_kb = output_path.stat().st_size / 1024

    return filename, size_kb, False

def generate_google_sample(voice: str, speed: float, output_dir: Path):
    """Google Cloud TTS 샘플 생성"""
    filename = f"sample_{voice}_{speed}.mp3"
    output_path = output_dir / filename

    # 파일이 이미 있으면 스킵
    if output_path.exists():
        size_kb = output_path.stat().st_size / 1024
        return filename, size_kb, True

    # Google Cloud TTS 클라이언트 초기화
    client = texttospeech.TextToSpeechClient()

    # 음성 매핑 (google-ko-KR-Neural2-A -> ko-KR-Neural2-A)
    voice_name = voice.replace('google-', '')

    # TTS 요청 설정
    synthesis_input = texttospeech.SynthesisInput(text=SAMPLE_TEXT)
    voice_params = texttospeech.VoiceSelectionParams(
        language_code="ko-KR",
        name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speed,
    )

    # TTS 생성
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice_params,
        audio_config=audio_config
    )

    # 오디오 파일 저장
    with open(output_path, "wb") as f:
        f.write(response.audio_content)

    # 파일 크기 확인
    size_kb = output_path.stat().st_size / 1024

    return filename, size_kb, False

def generate_aws_sample(voice: str, speed: float, output_dir: Path):
    """AWS Polly 샘플 생성"""
    filename = f"sample_{voice}_{speed}.mp3"
    output_path = output_dir / filename

    # 파일이 이미 있으면 스킵
    if output_path.exists():
        size_kb = output_path.stat().st_size / 1024
        return filename, size_kb, True

    # AWS Polly 클라이언트 초기화
    polly_client = boto3.client('polly', region_name='us-east-1')

    # 음성 매핑 (aws-Seoyeon -> Seoyeon)
    voice_id = voice.replace('aws-', '')

    # 속도를 SSML prosody rate로 변환 (50%, 100%, 150%, 200%)
    rate_percent = f"{int(speed * 100)}%"
    ssml_text = f'<speak><prosody rate="{rate_percent}">{SAMPLE_TEXT}</prosody></speak>'

    # 오디오 요청
    response = polly_client.synthesize_speech(
        Text=ssml_text,
        TextType='ssml',
        OutputFormat='mp3',
        VoiceId=voice_id,
        Engine='neural',
        LanguageCode='ko-KR'
    )

    # 오디오 파일 저장
    with open(output_path, "wb") as f:
        f.write(response['AudioStream'].read())

    # 파일 크기 확인
    size_kb = output_path.stat().st_size / 1024

    return filename, size_kb, False

async def main():
    print("=" * 70)
    print("  TTS 미리듣기 샘플 파일 생성 시작")
    print("=" * 70)
    print()

    # 출력 디렉토리 생성
    output_dir = Path(__file__).parent / "preview_samples"
    output_dir.mkdir(exist_ok=True)

    # 사용 가능한 제공자 확인
    print("사용 가능한 TTS 제공자:")
    print(f"  - Edge TTS: ✅ (무료)")
    print(f"  - Google Cloud TTS: {'✅' if GOOGLE_TTS_AVAILABLE else '❌ (패키지 미설치)'}")
    print(f"  - AWS Polly: {'✅' if AWS_POLLY_AVAILABLE else '❌ (패키지 미설치)'}")
    print()

    # 전체 음성 목록 생성
    all_voices = []
    all_voices.extend(EDGE_VOICES)
    if GOOGLE_TTS_AVAILABLE:
        all_voices.extend(GOOGLE_VOICES)
    if AWS_POLLY_AVAILABLE:
        all_voices.extend(AWS_VOICES)

    print(f"출력 디렉토리: {output_dir}")
    print(f"음성 수: {len(all_voices)}개 (Edge: {len(EDGE_VOICES)}, Google: {len(GOOGLE_VOICES) if GOOGLE_TTS_AVAILABLE else 0}, AWS: {len(AWS_VOICES) if AWS_POLLY_AVAILABLE else 0})")
    print(f"속도 수: {len(SPEEDS)}개")
    print(f"총 샘플 수: {len(all_voices) * len(SPEEDS)}개")
    print()

    total_size = 0
    success_count = 0
    skip_count = 0
    fail_count = 0

    # Edge TTS 샘플 생성
    print("=" * 70)
    print("  Edge TTS (무료)")
    print("=" * 70)
    for voice in EDGE_VOICES:
        print(f"\n[{voice}]")
        for speed in SPEEDS:
            try:
                filename, size_kb, skipped = await generate_edge_sample(voice, speed, output_dir)
                total_size += size_kb
                if skipped:
                    skip_count += 1
                    print(f"  [SKIP] {speed}x: {size_kb:.2f} KB (이미 존재)")
                else:
                    success_count += 1
                    print(f"  [OK] {speed}x: {size_kb:.2f} KB")
            except Exception as e:
                fail_count += 1
                print(f"  [FAIL] {speed}x: {e}")

    # Google Cloud TTS 샘플 생성
    if GOOGLE_TTS_AVAILABLE:
        print()
        print("=" * 70)
        print("  Google Cloud TTS (프리미엄)")
        print("=" * 70)
        for voice in GOOGLE_VOICES:
            print(f"\n[{voice}]")
            for speed in SPEEDS:
                try:
                    filename, size_kb, skipped = generate_google_sample(voice, speed, output_dir)
                    total_size += size_kb
                    if skipped:
                        skip_count += 1
                        print(f"  [SKIP] {speed}x: {size_kb:.2f} KB (이미 존재)")
                    else:
                        success_count += 1
                        print(f"  [OK] {speed}x: {size_kb:.2f} KB")
                except Exception as e:
                    fail_count += 1
                    print(f"  [FAIL] {speed}x: {e}")

    # AWS Polly 샘플 생성
    if AWS_POLLY_AVAILABLE:
        print()
        print("=" * 70)
        print("  AWS Polly (프리미엄)")
        print("=" * 70)
        for voice in AWS_VOICES:
            print(f"\n[{voice}]")
            for speed in SPEEDS:
                try:
                    filename, size_kb, skipped = generate_aws_sample(voice, speed, output_dir)
                    total_size += size_kb
                    if skipped:
                        skip_count += 1
                        print(f"  [SKIP] {speed}x: {size_kb:.2f} KB (이미 존재)")
                    else:
                        success_count += 1
                        print(f"  [OK] {speed}x: {size_kb:.2f} KB")
                except Exception as e:
                    fail_count += 1
                    print(f"  [FAIL] {speed}x: {e}")

    print()
    print("=" * 70)
    print("  생성 완료")
    print("=" * 70)
    print(f"성공: {success_count}개")
    print(f"스킵: {skip_count}개 (이미 존재)")
    print(f"실패: {fail_count}개")
    print(f"총 크기: {total_size:.2f} KB ({total_size / 1024:.2f} MB)")
    if success_count + skip_count > 0:
        print(f"평균 크기: {total_size / (success_count + skip_count):.2f} KB")
    print()

if __name__ == '__main__':
    asyncio.run(main())
