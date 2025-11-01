"""
비디오 병합 스크립트
여러 비디오를 하나로 연결하고, 선택적으로 TTS 나레이션과 자막을 추가합니다.
"""
import sys
import asyncio
import json
from pathlib import Path
from typing import List
import subprocess
import logging
import re

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def get_ffmpeg_path():
    """FFmpeg 경로 확인"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            return 'ffmpeg'
    except FileNotFoundError:
        pass

    # imageio-ffmpeg 시도
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass

    return None


def concatenate_videos(video_paths: List[Path], output_path: Path) -> Path:
    """
    FFmpeg를 사용하여 비디오 병합 (lossless)
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg or imageio-ffmpeg.")

    logger.info(f"📹 {len(video_paths)}개 비디오 병합 중...")

    # Concat 파일 생성
    concat_file = output_path.with_suffix('.txt')
    with open(concat_file, 'w', encoding='utf-8') as f:
        for path in video_paths:
            path_str = str(path.resolve()).replace('\\', '/')
            f.write(f"file '{path_str}'\n")

    try:
        cmd = [
            ffmpeg,
            '-y',  # 덮어쓰기
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',  # Lossless copy
            str(output_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")

        logger.info(f"✅ 비디오 병합 완료: {output_path.name}")

    finally:
        if concat_file.exists():
            concat_file.unlink()

    if not output_path.exists():
        raise RuntimeError(f"출력 비디오가 생성되지 않았습니다: {output_path}")

    return output_path


async def generate_tts(text: str, output_path: Path, voice: str = "ko-KR-SunHiNeural") -> Path:
    """
    Edge TTS로 음성 생성
    """
    try:
        import edge_tts
    except ImportError:
        raise ImportError("edge-tts가 설치되지 않았습니다. pip install edge-tts 를 실행하세요.")

    logger.info(f"🎙️ TTS 생성 중: {voice}")

    # 텍스트 정리
    clean_text = text.strip()
    if not clean_text:
        raise ValueError("나레이션 텍스트가 비어있습니다.")

    # Edge TTS로 음성 생성
    communicate = edge_tts.Communicate(clean_text, voice)
    await communicate.save(str(output_path))

    logger.info(f"✅ TTS 생성 완료: {output_path.name}")
    return output_path


def format_srt_time(seconds: float) -> str:
    """초를 SRT 시간 형식으로 변환 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millisecs = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"


def format_ass_timestamp(seconds: float) -> str:
    """초를 ASS 타임스탬프 형식으로 변환 (h:mm:ss.cc)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centisecs = int((seconds % 1) * 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"


def create_ass_from_text(text: str, duration: float, output_path: Path, max_chars_per_line: int = 22) -> Path:
    """텍스트에서 ASS 자막 파일 생성 (롱폼 방식)"""
    if not text or not text.strip():
        logger.error("❌ 자막 생성 실패: 텍스트가 비어있습니다.")
        return None

    # 제어 명령어 제거 ([무음 3초], [침묵] 등)
    text = re.sub(r'\[(무음|침묵|pause)\s*(\d+(?:\.\d+)?)?초?\]', '', text)

    # 문장 분리
    sentences = re.split(r'([.!?。！？])', text)

    # 분리된 구두점을 앞 문장에 붙이기
    combined_sentences = []
    for i in range(0, len(sentences)-1, 2):
        if i+1 < len(sentences):
            combined_sentences.append((sentences[i] + sentences[i+1]).strip())

    # 마지막 문장 처리
    if len(sentences) % 2 == 1 and sentences[-1].strip():
        combined_sentences.append(sentences[-1].strip())

    # 문장이 없으면 전체 텍스트를 하나의 문장으로
    if not combined_sentences:
        combined_sentences = [text.strip()]

    # 전체 글자 수 계산
    total_text = " ".join(combined_sentences)
    total_chars = len(total_text)
    time_per_char = duration / total_chars if total_chars > 0 else 0

    # 각 문장을 max_chars_per_line자 단위로 분할
    subtitles = []
    current_time = 0.0
    MIN_REMAINING_CHARS = 5

    for sentence in combined_sentences:
        words = sentence.split()
        if not words:
            continue

        current_text = ""
        for i, word in enumerate(words):
            next_text = current_text + (" " if current_text else "") + word
            remaining_words = words[i+1:]
            remaining_text = " ".join(remaining_words) if remaining_words else ""

            if len(next_text) > max_chars_per_line and current_text:
                if len(remaining_text) > 0 and len(remaining_text) < MIN_REMAINING_CHARS:
                    current_text = next_text + (" " + remaining_text if remaining_text else "")
                    duration_calc = len(current_text) * time_per_char
                    end_time = current_time + duration_calc
                    subtitles.append({
                        "start": current_time,
                        "end": end_time,
                        "text": current_text.strip()
                    })
                    current_text = ""
                    current_time = end_time
                    break
                else:
                    duration_calc = len(current_text) * time_per_char
                    end_time = current_time + duration_calc
                    subtitles.append({
                        "start": current_time,
                        "end": end_time,
                        "text": current_text.strip()
                    })
                    current_text = word
                    current_time = end_time
            else:
                current_text = next_text

        if current_text:
            duration_calc = len(current_text) * time_per_char
            end_time = current_time + duration_calc
            subtitles.append({
                "start": current_time,
                "end": end_time,
                "text": current_text.strip()
            })
            current_time = end_time

    # ASS 파일 작성
    ass_path = output_path.with_suffix('.ass')

    with open(ass_path, 'w', encoding='utf-8') as f:
        # ASS 헤더
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write("PlayResX: 1920\n")
        f.write("PlayResY: 1080\n\n")

        # 스타일 정의 (NanumGothic 폰트, 흰색, 검은 테두리)
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("Style: Default,NanumGothic,96,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,20,1\n\n")

        # 이벤트 (자막)
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for sub in subtitles:
            start = format_ass_timestamp(sub["start"])
            end = format_ass_timestamp(sub["end"])
            text_escaped = sub['text'].replace('\n', '\\N')
            f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text_escaped}\n")

    logger.info(f"✅ ASS 자막 파일 생성: {ass_path.name} ({len(subtitles)}개 구간)")
    return ass_path


def get_video_duration(video_path: Path) -> float:
    """FFprobe로 비디오 길이 확인"""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found.")

    ffprobe_path = ffmpeg.replace('ffmpeg', 'ffprobe')

    try:
        cmd = [
            ffprobe_path,
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"⚠️ 비디오 길이 확인 실패: {e}")
        return 0.0


def add_audio_to_video(video_path: Path, audio_path: Path, output_path: Path, subtitle_text: str = None, add_subtitles: bool = False) -> Path:
    """
    FFmpeg로 비디오에 오디오 (및 선택적으로 자막) 추가
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found.")

    logger.info(f"🔊 비디오에 오디오 추가 중...")

    # 자막이 있는 경우
    if subtitle_text and add_subtitles:
        logger.info(f"📝 자막 추가 시작...")
        logger.info(f"📝 자막 텍스트 길이: {len(subtitle_text)}자")
        logger.info(f"📝 자막 텍스트 미리보기: {subtitle_text[:100]}...")

        # 비디오 길이 확인
        duration = get_video_duration(video_path)
        logger.info(f"⏱️ 비디오 길이: {duration}초")

        if duration == 0:
            logger.warning("⚠️ 비디오 길이를 확인할 수 없어 자막을 건너뜁니다.")
            subtitle_text = None
        else:
            # ASS 자막 파일 생성 (롱폼 방식)
            temp_path = video_path.parent / f"{video_path.stem}_temp.srt"
            ass_path = create_ass_from_text(subtitle_text, duration, temp_path)

            if not ass_path or not ass_path.exists():
                logger.error(f"❌ ASS 자막 파일 생성 실패!")
                subtitle_text = None
            else:
                logger.info(f"✅ ASS 자막 파일 생성 완료: {ass_path}")

                # ASS 파일 내용 확인 (디버깅)
                try:
                    with open(ass_path, 'r', encoding='utf-8') as f:
                        ass_content = f.read()
                        logger.info(f"📝 ASS 파일 내용 ({len(ass_content)}자):")
                        logger.info(ass_content[:300])
                except Exception as e:
                    logger.warning(f"⚠️ ASS 파일 읽기 실패: {e}")

                # Windows 경로를 FFmpeg 호환 경로로 변환 (롱폼 방식)
                ass_path_str = str(ass_path).replace('\\', '/').replace(':', '\\\\:')

                # FFmpeg 명령어 (ASS 자막 포함)
                # 비디오 길이에 맞추고, 오디오가 짧으면 나머지는 무음
                # 주의: -vf 사용 시 비디오 재인코딩 필요 (자막을 비디오에 오버레이)
                cmd = [
                    ffmpeg,
                    '-y',
                    '-i', str(video_path),
                    '-i', str(audio_path),
                    '-vf', f"ass={ass_path_str}",
                    '-c:v', 'libx264',  # 자막 오버레이를 위해 재인코딩 필요
                    '-preset', 'medium',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    str(output_path)
                ]

                logger.info(f"🎬 FFmpeg 명령어 실행 중...")
                logger.info(f"   자막 필터: ass={ass_path_str}")

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600
                )

                logger.info(f"📤 FFmpeg 반환 코드: {result.returncode}")
                if result.stdout:
                    logger.info(f"📤 FFmpeg stdout: {result.stdout[:500]}")
                if result.stderr:
                    logger.info(f"📤 FFmpeg stderr: {result.stderr[:500]}")

                # ASS 파일 정리
                if ass_path.exists():
                    ass_path.unlink()
                    logger.info(f"🗑️ ASS 임시 파일 삭제됨")

                if result.returncode != 0:
                    logger.error(f"❌ FFmpeg 자막 추가 실패 (코드: {result.returncode})")
                    logger.error(f"❌ FFmpeg stderr: {result.stderr}")
                    logger.warning(f"⚠️ 자막 없이 재시도...")
                    subtitle_text = None
                else:
                    logger.info(f"✅ 자막 추가 성공!")

    # 자막이 없거나 실패한 경우
    if not subtitle_text or not add_subtitles:
        cmd = [
            ffmpeg,
            '-y',
            '-i', str(video_path),
            '-i', str(audio_path),
            '-c:v', 'copy',  # 비디오는 복사
            '-c:a', 'aac',   # 오디오는 aac로 인코딩
            '-map', '0:v:0',  # 첫 번째 입력의 비디오
            '-map', '1:a:0',  # 두 번째 입력의 오디오
            str(output_path)
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

    if result.returncode != 0:
        raise RuntimeError(f"오디오 추가 실패:\n{result.stderr}")

    logger.info(f"✅ 오디오 추가 완료: {output_path.name}")
    return output_path


async def main():
    """메인 실행 함수"""
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "사용법: python video_merge.py <config.json>"
        }))
        sys.exit(1)

    config_path = Path(sys.argv[1])
    if not config_path.exists():
        print(json.dumps({
            "success": False,
            "error": f"설정 파일을 찾을 수 없습니다: {config_path}"
        }))
        sys.exit(1)

    try:
        # 설정 파일 읽기
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        video_files = [Path(p) for p in config['video_files']]
        narration_text = config.get('narration_text', '')
        add_subtitles = config.get('add_subtitles', False)
        output_dir = Path(config['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        # 비디오 파일 존재 확인
        for video_file in video_files:
            if not video_file.exists():
                raise FileNotFoundError(f"비디오 파일을 찾을 수 없습니다: {video_file}")

        logger.info(f"\n{'='*60}")
        logger.info(f"🎞️ 비디오 병합 시작")
        logger.info(f"{'='*60}")
        logger.info(f"입력 비디오: {len(video_files)}개")
        for i, vf in enumerate(video_files, 1):
            logger.info(f"  {i}. {vf.name}")

        # 1단계: 비디오 병합
        merged_video = output_dir / 'merged_video.mp4'
        concatenate_videos(video_files, merged_video)

        final_output = merged_video

        # 2단계: TTS 나레이션 (및 자막) 추가 (선택사항)
        if narration_text:
            logger.info(f"\n🎙️ TTS 나레이션 추가")
            logger.info(f"텍스트: {narration_text[:100]}...")
            if add_subtitles:
                logger.info(f"📝 자막: 추가됨")

            tts_audio = output_dir / 'narration.mp3'
            await generate_tts(narration_text, tts_audio)

            final_with_audio = output_dir / 'final_with_narration.mp4'
            # 자막 추가 여부에 따라 처리
            add_audio_to_video(merged_video, tts_audio, final_with_audio, narration_text, add_subtitles)
            final_output = final_with_audio
        else:
            logger.info(f"\nℹ️ 나레이션 없이 병합만 수행")

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 비디오 병합 완료!")
        logger.info(f"📁 출력 파일: {final_output}")
        logger.info(f"{'='*60}\n")

        # 성공 응답
        print(json.dumps({
            "success": True,
            "output_video": str(final_output),
            "output_dir": str(output_dir)
        }))
        sys.exit(0)

    except Exception as e:
        logger.error(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()

        print(json.dumps({
            "success": False,
            "error": str(e)
        }))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
