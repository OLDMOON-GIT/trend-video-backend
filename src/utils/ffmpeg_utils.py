"""
FFmpeg 공통 유틸리티 함수
video_merge.py와 create_video_from_folder.py에서 공통으로 사용
"""
import subprocess
import logging
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_ffmpeg_path() -> Optional[str]:
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


# Alias for backward compatibility
format_ass_time = format_ass_timestamp


def detect_best_encoder() -> Tuple[str, str]:
    """
    Detect the best available video encoder (GPU or CPU).

    Returns:
        Tuple[str, str]: (encoder_name, encoder_type) where encoder_type is 'gpu' or 'cpu'
    """
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        logger.warning("FFmpeg not found, defaulting to libx264")
        return ("libx264", "cpu")

    # Check for NVIDIA GPU encoder
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10
        )

        encoders = result.stdout

        if "h264_nvenc" in encoders:
            logger.info("Using NVIDIA GPU encoder (h264_nvenc)")
            return ("h264_nvenc", "gpu")
        elif "h264_qsv" in encoders:
            logger.info("Using Intel Quick Sync encoder (h264_qsv)")
            return ("h264_qsv", "gpu")
        elif "h264_amf" in encoders:
            logger.info("Using AMD AMF encoder (h264_amf)")
            return ("h264_amf", "gpu")
        elif "h264_videotoolbox" in encoders:
            logger.info("Using Apple VideoToolbox encoder (h264_videotoolbox)")
            return ("h264_videotoolbox", "gpu")
        else:
            logger.info("Using CPU encoder (libx264)")
            return ("libx264", "cpu")

    except Exception as e:
        logger.warning(f"Failed to detect encoder, defaulting to libx264: {e}")
        return ("libx264", "cpu")


def concatenate_videos_with_fps_normalization(
    video_paths: List[Path],
    output_path: Path,
    target_fps: int = 25,
    target_width: int = 1920,
    target_height: int = 1080
) -> Path:
    """
    FFmpeg filter_complex를 사용하여 비디오 병합 (FPS/해상도 통일)

    Args:
        video_paths: 입력 비디오 파일 경로 리스트
        output_path: 출력 비디오 경로
        target_fps: 목표 FPS (기본값: 25)
        target_width: 목표 너비 (기본값: 1920)
        target_height: 목표 높이 (기본값: 1080)

    Returns:
        출력 비디오 경로
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg or imageio-ffmpeg.")

    logger.info(f"📹 {len(video_paths)}개 비디오 병합 중... (FPS: {target_fps}, 해상도: {target_width}x{target_height})")
    logger.info(f"   비디오 목록:")
    for i, path in enumerate(video_paths, 1):
        logger.info(f"   {i}. {path.name}")

    # 입력 파일들
    input_args = []
    for path in video_paths:
        input_args.extend(['-i', str(path)])

    # filter_complex 문자열 생성
    # 모든 비디오를 target_width x target_height로 통일 + SAR 1:1 정규화 + FPS 통일 후 concat
    scale_filters = []
    concat_inputs = []
    for i in range(len(video_paths)):
        scale_filters.append(
            f"[{i}:v]scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={target_fps}[v{i}]"
        )
        concat_inputs.append(f"[v{i}][{i}:a]")

    filter_str = ";".join(scale_filters) + ";" + "".join(concat_inputs) + f"concat=n={len(video_paths)}:v=1:a=1[outv][outa]"

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


def build_ffmpeg_video_filter(
    width: int,
    height: int,
    fps: int = 25,
    include_subtitle: bool = False,
    subtitle_path: Optional[str] = None
) -> str:
    """
    FFmpeg 비디오 필터 문자열 생성

    Args:
        width: 목표 너비
        height: 목표 높이
        fps: 목표 FPS (기본값: 25)
        include_subtitle: 자막 포함 여부
        subtitle_path: 자막 파일 경로 (Unix 스타일, 콜론 이스케이프 완료)

    Returns:
        FFmpeg -vf 필터 문자열
    """
    filter_parts = [
        f"scale={width}:{height}:force_original_aspect_ratio=decrease",
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
        f"fps={fps}"
    ]

    if include_subtitle and subtitle_path:
        filter_parts.append(f"ass={subtitle_path}")

    return ",".join(filter_parts)
