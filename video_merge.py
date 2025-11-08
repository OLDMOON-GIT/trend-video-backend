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

# 워터마크 제거 기능
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logging.warning("⚠️ OpenCV가 설치되지 않아 워터마크 제거 기능을 사용할 수 없습니다.")

# 로깅 설정 (stderr 에러 방지)
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stdout,  # stderr 대신 stdout 사용
    force=True
)
logger = logging.getLogger(__name__)


def detect_watermark_region(frame, threshold=200):
    """프레임에서 워터마크 영역 감지"""
    if not OPENCV_AVAILABLE:
        return []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    kernel = np.ones((5, 5), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    watermark_regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        frame_area = frame.shape[0] * frame.shape[1]
        if 0.005 * frame_area < area < 0.1 * frame_area:
            watermark_regions.append((x, y, w, h))

    return watermark_regions


def inpaint_region(frame, x, y, w, h):
    """특정 영역을 주변 픽셀로 채우기 (inpainting)"""
    if not OPENCV_AVAILABLE:
        return frame

    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    padding = 5
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(frame.shape[1], x + w + padding)
    y2 = min(frame.shape[0], y + h + padding)

    mask[y1:y2, x1:x2] = 255
    result = cv2.inpaint(frame, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)
    return result


def remove_watermark_from_video(input_path: Path, output_path: Path, threshold: int = 150) -> Path:
    """
    비디오에서 워터마크 제거 - 워터마크 제거는 건너뛰고 원본 복사
    (현재는 워터마크 제거 기능 비활성화)
    """
    logger.info(f"⏭️ 워터마크 제거 건너뛰기: {input_path.name}")
    logger.info(f"   (워터마크 제거 기능은 현재 비활성화되어 있습니다)")

    # 원본을 그대로 복사
    import shutil
    shutil.copy(input_path, output_path)
    return output_path


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
    FFmpeg를 사용하여 비디오 병합 (filter_complex 방식)
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg or imageio-ffmpeg.")

    logger.info(f"📹 {len(video_paths)}개 비디오 병합 중...")
    logger.info(f"   비디오 목록:")
    for i, path in enumerate(video_paths, 1):
        logger.info(f"   {i}. {path.name}")

    # filter_complex 방식으로 병합 (타임스탬프 문제 해결)
    # 입력 파일들
    input_args = []
    for path in video_paths:
        input_args.extend(['-i', str(path)])

    # filter_complex 문자열 생성
    # [0:v][0:a][1:v][1:a]...[n:v][n:a]concat=n=N:v=1:a=1[outv][outa]
    filter_parts = []
    for i in range(len(video_paths)):
        filter_parts.append(f"[{i}:v][{i}:a]")
    filter_str = "".join(filter_parts) + f"concat=n={len(video_paths)}:v=1:a=1[outv][outa]"

    logger.info(f"🎬 FFmpeg filter_complex 명령 실행 중...")

    cmd = [
        ffmpeg,
        '-y',  # 덮어쓰기
        *input_args,  # 입력 파일들
        '-filter_complex', filter_str,
        '-map', '[outv]',
        '-map', '[outa]',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '18',  # 고품질
        '-c:a', 'aac',
        '-b:a', '192k',
        str(output_path)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600
    )

    if result.returncode != 0:
        logger.error(f"❌ FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")

    logger.info(f"✅ 비디오 병합 완료: {output_path.name}")

    if not output_path.exists():
        raise RuntimeError(f"출력 비디오가 생성되지 않았습니다: {output_path}")

    return output_path


def align_videos_to_scenes(video_paths: list, scenes: list, whisper_segments: list, output_path: Path) -> Path:
    """
    scenes 배열에 맞춰 비디오를 배치 (원본 대본 구조 사용)

    Args:
        video_paths: 입력 비디오 파일 경로 리스트
        scenes: scenes 배열 (각 scene은 narration, duration 포함)
        whisper_segments: Whisper 세그먼트 (전체 타임스탬프)
        output_path: 출력 비디오 경로
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg or imageio-ffmpeg.")

    logger.info(f"\n🎬 scenes 배열에 맞춰 비디오 배치 중...")
    logger.info(f"   scenes: {len(scenes)}개")
    logger.info(f"   비디오: {len(video_paths)}개")

    # scenes와 비디오 매칭
    video_segments = []
    current_time = 0.0

    for i, scene in enumerate(scenes):
        # 비디오 선택 (순차적으로, 마지막 비디오 반복)
        video_idx = min(i, len(video_paths) - 1)
        video_path = video_paths[video_idx]

        # scene의 duration 사용 (Whisper 세그먼트에서 실제 길이 계산)
        scene_narration = scene.get('narration', '')
        scene_duration = scene.get('duration', 0)

        # Whisper 세그먼트에서 이 scene에 해당하는 구간 찾기
        scene_start = current_time
        scene_end = scene_start

        # scene의 narration과 매칭되는 Whisper 세그먼트 찾기
        for seg in whisper_segments:
            if seg['start'] >= current_time:
                if scene_end == scene_start:
                    scene_end = seg['end']
                else:
                    scene_end = seg['end']

                # scene_narration이 seg['text']에 포함되거나 유사하면 계속
                # 간단하게 시간 기준으로 판단
                if scene_duration > 0 and (scene_end - scene_start) >= scene_duration * 0.9:
                    break

        # scene_end가 업데이트되지 않았으면 duration 사용
        if scene_end == scene_start and scene_duration > 0:
            scene_end = scene_start + scene_duration

        duration = scene_end - scene_start
        current_time = scene_end

        video_segments.append({
            'video_path': video_path,
            'duration': duration,
            'scene_text': scene_narration[:30]
        })

        logger.info(f"   씬 {i+1}: {duration:.2f}초 → {video_path.name}")

    # FFmpeg filter_complex로 각 비디오를 trim하고 concat
    input_args = []
    trim_filters = []
    concat_inputs = []

    for i, vs in enumerate(video_segments):
        input_args.extend(['-i', str(vs['video_path'])])
        trim_filters.append(f"[{i}:v]trim=duration={vs['duration']},setpts=PTS-STARTPTS[v{i}]")
        trim_filters.append(f"[{i}:a]atrim=duration={vs['duration']},asetpts=PTS-STARTPTS[a{i}]")
        concat_inputs.append(f"[v{i}][a{i}]")

    trim_filter_str = ";".join(trim_filters)
    concat_input_str = "".join(concat_inputs)
    concat_filter = f"{concat_input_str}concat=n={len(video_segments)}:v=1:a=1[outv][outa]"
    filter_complex = f"{trim_filter_str};{concat_filter}"

    logger.info(f"🎬 FFmpeg filter_complex 실행 중...")

    cmd = [
        ffmpeg,
        '-y',
        *input_args,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '[outa]',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '192k',
        str(output_path)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600
    )

    if result.returncode != 0:
        logger.error(f"❌ FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")

    logger.info(f"✅ scenes 기반 비디오 병합 완료: {output_path.name}")

    if not output_path.exists():
        raise RuntimeError(f"출력 비디오가 생성되지 않았습니다: {output_path}")

    return output_path


def align_videos_to_segments(video_paths: list, segments: list, output_path: Path) -> Path:
    """
    나레이션 세그먼트에 맞춰 비디오를 배치

    Args:
        video_paths: 입력 비디오 파일 경로 리스트
        segments: Whisper 세그먼트 리스트 (각 세그먼트는 start, end, text 포함)
        output_path: 출력 비디오 경로
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg or imageio-ffmpeg.")

    logger.info(f"\n🎬 세그먼트에 맞춰 비디오 배치 중...")
    logger.info(f"   세그먼트: {len(segments)}개")
    logger.info(f"   비디오: {len(video_paths)}개")

    # 세그먼트와 비디오 매칭 (순환 없음, 마지막 비디오 유지)
    video_segments = []
    for i, seg in enumerate(segments):
        # 비디오 개수를 넘어가면 마지막 비디오 계속 사용
        video_idx = min(i, len(video_paths) - 1)
        video_path = video_paths[video_idx]
        duration = seg['end'] - seg['start']

        video_segments.append({
            'video_path': video_path,
            'duration': duration,
            'segment_text': seg['text'][:30]  # 로그용
        })

        logger.info(f"   세그먼트 {i+1}: {duration:.2f}초 → {video_path.name}")

    # FFmpeg filter_complex로 각 비디오를 trim하고 concat
    input_args = []
    trim_filters = []
    concat_inputs = []

    for i, vs in enumerate(video_segments):
        # 각 비디오 파일을 입력으로 추가 (중복 가능)
        input_args.extend(['-i', str(vs['video_path'])])

        # 해당 비디오를 duration에 맞춰 trim
        # trim은 처음부터 duration만큼만 가져옴
        trim_filters.append(f"[{i}:v]trim=duration={vs['duration']},setpts=PTS-STARTPTS[v{i}]")
        trim_filters.append(f"[{i}:a]atrim=duration={vs['duration']},asetpts=PTS-STARTPTS[a{i}]")

        concat_inputs.append(f"[v{i}][a{i}]")

    # filter_complex 문자열 조합
    trim_filter_str = ";".join(trim_filters)
    concat_input_str = "".join(concat_inputs)
    concat_filter = f"{concat_input_str}concat=n={len(video_segments)}:v=1:a=1[outv][outa]"

    filter_complex = f"{trim_filter_str};{concat_filter}"

    logger.info(f"🎬 FFmpeg filter_complex 실행 중...")

    cmd = [
        ffmpeg,
        '-y',
        *input_args,
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-map', '[outa]',
        '-c:v', 'libx264',
        '-preset', 'medium',
        '-crf', '23',
        '-c:a', 'aac',
        '-b:a', '192k',
        str(output_path)
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600
    )

    if result.returncode != 0:
        logger.error(f"❌ FFmpeg stderr: {result.stderr}")
        raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")

    logger.info(f"✅ 세그먼트 기반 비디오 병합 완료: {output_path.name}")

    if not output_path.exists():
        raise RuntimeError(f"출력 비디오가 생성되지 않았습니다: {output_path}")

    return output_path


def transcribe_audio_with_whisper(audio_path: Path, original_text: str) -> list:
    """
    Whisper로 타임스탬프만 얻고, 텍스트는 원본 나레이션 사용
    """
    try:
        import whisper
        import re

        logger.info(f"🎧 Whisper로 타이밍 분석 중...")

        # Whisper 모델 로드 (base 모델 사용)
        model = whisper.load_model("base")

        # 오디오 인식 (타임스탬프만 필요)
        result = model.transcribe(
            str(audio_path),
            language="ko",
            verbose=False
        )

        # Whisper 세그먼트 타임스탬프 추출
        whisper_segments = result["segments"]
        logger.info(f"✅ Whisper 타이밍 분석 완료: {len(whisper_segments)}개 세그먼트")

        # 원본 텍스트를 문장 단위로 분리
        sentences = re.split(r'([.!?。！？]+)', original_text)

        # 분리된 구두점을 앞 문장에 붙이기
        original_sentences = []
        for i in range(0, len(sentences)-1, 2):
            if i+1 < len(sentences):
                sentence = (sentences[i] + sentences[i+1]).strip()
                if sentence:
                    original_sentences.append(sentence)

        # 마지막 문장 처리
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            original_sentences.append(sentences[-1].strip())

        if not original_sentences:
            original_sentences = [original_text.strip()]

        logger.info(f"📝 원본 텍스트: {len(original_sentences)}개 문장")

        # Whisper 타임스탬프 + 원본 텍스트 결합
        subtitle_data = []

        # 세그먼트 개수와 문장 개수가 다를 경우 조정
        num_segments = min(len(whisper_segments), len(original_sentences))

        if len(whisper_segments) != len(original_sentences):
            logger.warning(f"⚠️ 세그먼트 개수 불일치: Whisper {len(whisper_segments)}개, 원본 {len(original_sentences)}개")
            logger.warning(f"   → {num_segments}개만 사용")

        for i in range(num_segments):
            subtitle_data.append({
                "start": whisper_segments[i]["start"],
                "end": whisper_segments[i]["end"],
                "text": original_sentences[i]  # 원본 텍스트 사용!
            })

        # 남은 원본 문장이 있으면 마지막 세그먼트에 이어붙이기
        if len(original_sentences) > num_segments:
            remaining = " ".join(original_sentences[num_segments:])
            if subtitle_data:
                subtitle_data[-1]["text"] += " " + remaining
                logger.info(f"📝 남은 문장을 마지막 세그먼트에 추가")

        # 타임스탬프 샘플 출력
        if subtitle_data:
            logger.info(f"📊 타임스탬프 + 원본 텍스트 (처음 3개):")
            for i, seg in enumerate(subtitle_data[:3]):
                duration = seg['end'] - seg['start']
                logger.info(f"   {i+1}. {seg['start']:.3f}s ~ {seg['end']:.3f}s ({duration:.3f}초): '{seg['text'][:50]}'")

        return subtitle_data

    except Exception as e:
        logger.warning(f"⚠️ Whisper 분석 실패: {e}")
        logger.warning(f"   타임스탬프 없이 진행합니다.")
        return None


async def generate_tts(text: str, output_path: Path, voice: str = "ko-KR-SunHiNeural"):
    """
    Edge TTS로 음성 생성 후 Whisper로 정확한 타임스탬프 얻기
    Returns: (audio_path, subtitle_data)
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

    # Edge TTS로 음성만 생성 (타임스탬프는 Whisper에서 얻음)
    communicate = edge_tts.Communicate(clean_text, voice)

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])

    logger.info(f"✅ TTS 생성 완료: {output_path.name}")

    # Whisper로 오디오 인식해서 정확한 타임스탬프 얻기
    subtitle_data = transcribe_audio_with_whisper(output_path, clean_text)

    # Whisper 실패 시 빈 리스트 반환 (자막 없이 진행)
    if subtitle_data is None:
        subtitle_data = []

    return output_path, subtitle_data


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


def create_ass_from_timestamps(subtitle_data: list, output_path: Path, max_chars_per_line: int = 30) -> Path:
    """Whisper 세그먼트 데이터에서 ASS 자막 파일 생성

    Args:
        subtitle_data: Whisper 세그먼트 데이터 (이미 문장 단위로 분리됨)
        output_path: 출력 파일 경로
        max_chars_per_line: 한 줄 최대 글자 수 (현재 미사용)
    """
    if not subtitle_data:
        logger.error("❌ 자막 생성 실패: 타임스탬프 데이터가 비어있습니다.")
        return None

    # Whisper 세그먼트를 그대로 사용 (이미 문장 단위로 분리됨)
    logger.info(f"📝 Whisper 세그먼트 기반 자막 생성: {len(subtitle_data)}개 세그먼트")

    # 자막 샘플 로그 (디버깅)
    if subtitle_data:
        logger.info(f"📊 자막 샘플 (처음 3개):")
        for i, sub in enumerate(subtitle_data[:3]):
            duration = sub['end'] - sub['start']
            logger.info(f"   {i+1}. {sub['start']:.3f}s ~ {sub['end']:.3f}s ({duration:.3f}초): '{sub['text'][:50]}'")

    # ASS 파일 작성
    ass_path = output_path.with_suffix('.ass')

    with open(ass_path, 'w', encoding='utf-8') as f:
        # ASS 헤더
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write("PlayResX: 1920\n")
        f.write("PlayResY: 1080\n")
        f.write("\n")

        # 스타일 정의
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write("Style: Default,Pretendard Variable,48,&H00FFFFFF,&H000088EF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,30,30,40,1\n")
        f.write("\n")

        # 이벤트 (자막)
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        for sub in subtitle_data:
            start_time = format_ass_timestamp(sub["start"])
            end_time = format_ass_timestamp(sub["end"])
            text = sub["text"]
            f.write(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n")

    logger.info(f"✅ ASS 자막 파일 생성 완료: {ass_path} ({len(subtitle_data)}개 라인)")
    return ass_path


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


def get_audio_duration(audio_path: Path) -> float:
    """FFprobe로 오디오 길이 확인"""
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
            str(audio_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return float(result.stdout.strip())
    except Exception as e:
        logger.warning(f"⚠️ 오디오 길이 확인 실패: {e}")
        return 0.0


def add_audio_to_video(video_path: Path, audio_path: Path, output_path: Path, subtitle_text: str = None, add_subtitles: bool = False, subtitle_data: list = None) -> Path:
    """
    FFmpeg로 비디오에 오디오 (및 선택적으로 자막) 추가
    TTS가 짧아도 비디오 전체 길이에 맞춰 무음 추가
    subtitle_data: TTS 타임스탬프 데이터 (있으면 정확한 동기화)
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found.")

    logger.info(f"🔊 비디오에 오디오 추가 중...")

    # 비디오와 오디오 길이 확인
    video_duration = get_video_duration(video_path)
    audio_duration = get_audio_duration(audio_path)

    logger.info(f"⏱️ 비디오 길이: {video_duration:.2f}초")
    logger.info(f"⏱️ 오디오 길이: {audio_duration:.2f}초")

    # 비디오와 오디오 길이 비교하여 필터 준비
    video_filter = None
    audio_filter = None

    if video_duration < audio_duration:
        # 비디오가 짧으면: 마지막 프레임을 freeze하여 오디오 길이에 맞춤
        freeze_duration = audio_duration - video_duration
        video_filter = f"tpad=stop_mode=clone:stop_duration={freeze_duration:.3f}"
        logger.info(f"⚠️ 비디오가 TTS보다 짧습니다. 마지막 프레임을 {freeze_duration:.2f}초 freeze합니다.")
        logger.info(f"🎬 비디오 패딩 필터 적용: {video_filter}")
    elif audio_duration < video_duration:
        # 오디오가 짧으면: 무음 추가하여 비디오 길이에 맞춤
        audio_filter = f"apad=whole_dur={video_duration:.3f}"
        logger.info(f"⚠️ TTS가 비디오보다 짧습니다. 무음을 추가하여 비디오 길이에 맞춥니다.")
        logger.info(f"🔇 오디오 패딩 필터 적용: {audio_filter}")

    # 자막이 있는 경우
    if subtitle_text and add_subtitles:
        logger.info(f"📝 자막 추가 시작...")
        logger.info(f"📝 자막 텍스트 길이: {len(subtitle_text)}자")
        logger.info(f"📝 자막 텍스트 미리보기: {subtitle_text[:100]}...")

        # ASS 자막 파일 생성
        temp_path = video_path.parent / f"{video_path.stem}_temp.srt"

        # 타임스탬프 데이터가 있으면 정확한 동기화 사용
        if subtitle_data:
            logger.info(f"⏱️ TTS 타임스탬프 기반 자막 생성 (완벽 동기화)")
            ass_path = create_ass_from_timestamps(subtitle_data, temp_path)
        else:
            # 타임스탬프가 없으면 텍스트 기반 추정
            logger.info(f"⏱️ 텍스트 기반 자막 생성 (TTS 오디오 길이 기준)")
            duration = audio_duration if audio_duration > 0 else get_video_duration(video_path)
            logger.info(f"⏱️ 자막 기준 길이: {duration}초")

            if duration == 0:
                logger.warning("⚠️ 오디오/비디오 길이를 확인할 수 없어 자막을 건너뜁니다.")
                subtitle_text = None
                ass_path = None
            else:
                ass_path = create_ass_from_text(subtitle_text, duration, temp_path)

        if subtitle_text:

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

                # 비디오 필터 생성 (tpad + ass 결합)
                vf_parts = []
                if video_filter:
                    vf_parts.append(video_filter)
                vf_parts.append(f"ass={ass_path_str}")
                vf_combined = ",".join(vf_parts)

                # FFmpeg 명령어 (ASS 자막 포함)
                # 비디오 길이를 TTS에 맞추고, 오디오가 짧으면 나머지는 무음
                # 주의: -vf 사용 시 비디오 재인코딩 필요 (자막을 비디오에 오버레이)
                cmd = [
                    ffmpeg,
                    '-y',
                    '-i', str(video_path),
                    '-i', str(audio_path),
                    '-vf', vf_combined,
                    '-c:v', 'libx264',  # 자막 오버레이를 위해 재인코딩 필요
                    '-preset', 'medium',
                    '-crf', '23',
                    '-c:a', 'aac',
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                ]

                # 오디오 필터 추가 (패딩이 필요한 경우)
                if audio_filter:
                    cmd.extend(['-af', audio_filter])

                cmd.append(str(output_path))

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
        ]

        # 비디오 필터가 있으면 재인코딩 필요
        if video_filter:
            cmd.extend([
                '-vf', video_filter,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
            ])
        else:
            cmd.extend(['-c:v', 'copy'])  # 비디오는 복사

        cmd.extend([
            '-c:a', 'aac',   # 오디오는 aac로 인코딩
            '-map', '0:v:0',  # 첫 번째 입력의 비디오
            '-map', '1:a:0',  # 두 번째 입력의 오디오
        ])

        # 오디오 필터 추가 (패딩이 필요한 경우)
        if audio_filter:
            cmd.extend(['-af', audio_filter])

        cmd.append(str(output_path))

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

        # 파일명에 시퀀스 번호가 있는지 확인
        def extract_sequence(filename: str):
            """파일명에서 시퀀스 번호 추출 (예: video_001.mp4 -> 1, clip_03.mp4 -> 3)"""
            match = re.search(r'_(\d+)\.(mp4|mov|avi|mkv)$', filename, re.IGNORECASE)
            if match:
                return int(match.group(1))
            return None

        # 시퀀스 번호가 있는 파일이 하나라도 있는지 확인
        has_sequence = any(extract_sequence(p.name) is not None for p in video_files)

        if has_sequence:
            # 시퀀스가 있으면: 시퀀스 번호로 정렬
            logger.info(f"📋 시퀀스 번호로 정렬")
            video_files.sort(key=lambda p: (extract_sequence(p.name) or 0, p.name))
        else:
            # 시퀀스가 없으면: 파일 생성 시간으로 정렬 (오래된 파일 먼저)
            logger.info(f"📋 파일 생성 시간으로 정렬 (오래된 파일 먼저)")
            video_files.sort(key=lambda p: p.stat().st_ctime)

        narration_text = config.get('narration_text', '')
        add_subtitles = config.get('add_subtitles', False)
        remove_watermark = config.get('remove_watermark', False)
        title = config.get('title', '')  # 대본의 title
        scenes = config.get('scenes', None)  # scenes 배열 (비디오 배치용)
        output_dir = Path(config['output_dir'])
        output_dir.mkdir(parents=True, exist_ok=True)

        # 비디오 파일 존재 확인
        for video_file in video_files:
            if not video_file.exists():
                raise FileNotFoundError(f"비디오 파일을 찾을 수 없습니다: {video_file}")

        logger.info(f"\n{'='*60}")
        logger.info(f"🎞️ 비디오 병합 시작")
        logger.info(f"{'='*60}")
        logger.info(f"입력 비디오: {len(video_files)}개 (정렬됨)")
        for i, vf in enumerate(video_files, 1):
            logger.info(f"  {i}. {vf.name}")

        # 워터마크 제거 기능 비활성화 (작동하지 않음)
        processed_video_files = video_files

        # 나레이션이 있으면 TTS를 먼저 생성하고 세그먼트에 맞춰 비디오 배치
        if narration_text:
            logger.info(f"\n🎙️ TTS 나레이션 생성 (비디오 배치 기준)")
            logger.info(f"텍스트: {narration_text[:100]}...")

            tts_audio = output_dir / 'narration.mp3'
            # TTS 생성 및 Whisper 세그먼트 수집
            tts_path, subtitle_data = await generate_tts(narration_text, tts_audio)

            if subtitle_data:
                logger.info(f"\n🎬 나레이션 세그먼트에 맞춰 비디오 배치")
                logger.info(f"   세그먼트 개수: {len(subtitle_data)}개")
                logger.info(f"   비디오 개수: {len(processed_video_files)}개")

                # scenes 배열이 있으면 scenes 기준으로 비디오 배치
                merged_video = output_dir / 'merged_video.mp4'
                if scenes:
                    logger.info(f"   📋 scenes 배열 사용: {len(scenes)}개 씬")
                    align_videos_to_scenes(processed_video_files, scenes, subtitle_data, merged_video)
                else:
                    logger.info(f"   📋 Whisper 세그먼트 사용")
                    align_videos_to_segments(processed_video_files, subtitle_data, merged_video)

                # 비디오에 오디오 + 자막 추가
                final_with_audio = output_dir / 'final_with_narration.mp4'
                add_audio_to_video(merged_video, tts_audio, final_with_audio, narration_text, add_subtitles, subtitle_data)
                final_output = final_with_audio
            else:
                # Whisper 실패 시 기존 방식 (순차 병합)
                logger.warning(f"⚠️ 세그먼트 정보 없음, 기존 방식으로 병합")
                merged_video = output_dir / 'merged_video.mp4'
                concatenate_videos(processed_video_files, merged_video)

                final_with_audio = output_dir / 'final_with_narration.mp4'
                add_audio_to_video(merged_video, tts_audio, final_with_audio, narration_text, add_subtitles, [])
                final_output = final_with_audio
        else:
            # 나레이션 없이 병합만 수행
            logger.info(f"\nℹ️ 나레이션 없이 병합만 수행")
            merged_video = output_dir / 'merged_video.mp4'
            concatenate_videos(processed_video_files, merged_video)
            final_output = merged_video

        # title이 있으면 최종 파일명을 title.mp4로 변경
        if title:
            # 파일명으로 사용할 수 없는 문자 제거
            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
            final_output_with_title = output_dir / f"{safe_title}.mp4"

            # 파일 이동 (리네임)
            import shutil
            shutil.move(str(final_output), str(final_output_with_title))
            final_output = final_output_with_title
            logger.info(f"📝 파일명을 대본 제목으로 변경: {safe_title}.mp4")

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 비디오 병합 완료!")
        logger.info(f"📁 출력 파일: {final_output}")
        logger.info(f"{'='*60}\n")

        # 성공 응답 (stdout으로 명시적 출력)
        result_json = json.dumps({
            "success": True,
            "output_video": str(final_output),
            "output_dir": str(output_dir)
        })
        sys.stdout.write(result_json + '\n')
        sys.stdout.flush()
        sys.exit(0)

    except Exception as e:
        logger.error(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc(file=sys.stdout)  # stderr 대신 stdout 사용

        error_json = json.dumps({
            "success": False,
            "error": str(e)
        })
        sys.stdout.write(error_json + '\n')
        sys.stdout.flush()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
