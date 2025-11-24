"""
FFmpeg utility functions for video processing
Extracted from long_form_creator.py, create_video_from_folder.py, and video_merge.py
"""

import os
import platform
import subprocess
import shutil
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def get_ffmpeg_path() -> str:
    """
    Get the FFmpeg executable path based on the operating system.

    Returns:
        str: Path to FFmpeg executable

    Raises:
        RuntimeError: If FFmpeg is not found
    """
    system = platform.system()

    if system == "Windows":
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path

        # Check common Windows installation paths
        possible_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
            os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin", "ffmpeg.exe"),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        raise RuntimeError("FFmpeg not found. Please install FFmpeg or add it to PATH.")

    elif system in ["Linux", "Darwin"]:  # Darwin is macOS
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path

        # Check common Unix installation paths
        possible_paths = [
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/opt/homebrew/bin/ffmpeg",  # macOS Homebrew on Apple Silicon
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        raise RuntimeError("FFmpeg not found. Please install FFmpeg using your package manager.")

    else:
        raise RuntimeError(f"Unsupported operating system: {system}")


def get_ffprobe_path() -> str:
    """
    Get the FFprobe executable path based on the operating system.

    Returns:
        str: Path to FFprobe executable

    Raises:
        RuntimeError: If FFprobe is not found
    """
    system = platform.system()

    if system == "Windows":
        ffprobe_path = shutil.which("ffprobe")
        if ffprobe_path:
            return ffprobe_path

        possible_paths = [
            r"C:\ffmpeg\bin\ffprobe.exe",
            r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
            os.path.join(os.environ.get("ProgramFiles", ""), "ffmpeg", "bin", "ffprobe.exe"),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        raise RuntimeError("FFprobe not found. Please install FFmpeg or add it to PATH.")

    elif system in ["Linux", "Darwin"]:
        ffprobe_path = shutil.which("ffprobe")
        if ffprobe_path:
            return ffprobe_path

        possible_paths = [
            "/usr/bin/ffprobe",
            "/usr/local/bin/ffprobe",
            "/opt/homebrew/bin/ffprobe",
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path

        raise RuntimeError("FFprobe not found. Please install FFmpeg using your package manager.")

    else:
        raise RuntimeError(f"Unsupported operating system: {system}")


def get_video_duration(video_path: str) -> float:
    """
    Get the duration of a video file in seconds using FFprobe.

    Args:
        video_path: Path to the video file

    Returns:
        float: Duration in seconds

    Raises:
        RuntimeError: If duration cannot be determined
    """
    try:
        ffprobe_path = get_ffprobe_path()

        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        duration = float(result.stdout.strip())
        return duration

    except Exception as e:
        logger.error(f"Failed to get video duration for {video_path}: {e}")
        raise RuntimeError(f"Failed to get video duration: {e}")


def get_audio_duration(audio_path: str) -> float:
    """
    Get the duration of an audio file in seconds using FFprobe.

    Args:
        audio_path: Path to the audio file

    Returns:
        float: Duration in seconds

    Raises:
        RuntimeError: If duration cannot be determined
    """
    try:
        ffprobe_path = get_ffprobe_path()

        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        duration = float(result.stdout.strip())
        return duration

    except Exception as e:
        logger.error(f"Failed to get audio duration for {audio_path}: {e}")
        raise RuntimeError(f"Failed to get audio duration: {e}")


def detect_best_encoder() -> Tuple[str, str]:
    """
    Detect the best available video encoder (GPU or CPU).

    Returns:
        Tuple[str, str]: (encoder_name, encoder_type) where encoder_type is 'gpu' or 'cpu'
    """
    ffmpeg_path = get_ffmpeg_path()

    # Check for NVIDIA GPU encoder
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        encoders = result.stdout

        if "h264_nvenc" in encoders:
            logger.info("Using NVIDIA GPU encoder (h264_nvenc)")
            return ("h264_nvenc", "gpu")
        elif "h264_qsv" in encoders:
            logger.info("Using Intel Quick Sync encoder (h264_qsv)")
            return ("h264_qsv", "gpu")
        elif "h264_videotoolbox" in encoders:
            logger.info("Using Apple VideoToolbox encoder (h264_videotoolbox)")
            return ("h264_videotoolbox", "gpu")
        else:
            logger.info("Using CPU encoder (libx264)")
            return ("libx264", "cpu")

    except Exception as e:
        logger.warning(f"Failed to detect encoder, defaulting to libx264: {e}")
        return ("libx264", "cpu")


def concatenate_videos(
    video_paths: list[str],
    output_path: str,
    use_concat_demuxer: bool = True,
    fps: int = 30,
    preset: str = "medium"
) -> bool:
    """
    Concatenate multiple video files into a single video.

    Args:
        video_paths: List of video file paths to concatenate
        output_path: Path for the output video file
        use_concat_demuxer: If True, use concat demuxer (faster, requires same codec)
                           If False, use concat filter (slower, re-encodes)
        fps: Frame rate for output video (used with concat filter)
        preset: FFmpeg encoding preset (used with concat filter)

    Returns:
        bool: True if successful, False otherwise
    """
    if not video_paths:
        logger.error("No video paths provided for concatenation")
        return False

    if len(video_paths) == 1:
        # Single video, just copy it
        try:
            shutil.copy2(video_paths[0], output_path)
            logger.info(f"Copied single video to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to copy video: {e}")
            return False

    ffmpeg_path = get_ffmpeg_path()
    encoder, encoder_type = detect_best_encoder()

    try:
        if use_concat_demuxer:
            # Create a temporary file list for concat demuxer
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
                concat_file = f.name
                for video_path in video_paths:
                    # Escape single quotes in file paths
                    escaped_path = video_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            try:
                cmd = [
                    ffmpeg_path,
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy",
                    "-y",
                    output_path
                ]

                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True
                )

                logger.info(f"Successfully concatenated {len(video_paths)} videos using concat demuxer")
                return True

            finally:
                # Clean up temporary file
                try:
                    os.unlink(concat_file)
                except Exception:
                    pass

        else:
            # Use concat filter (re-encodes)
            inputs = []
            for video_path in video_paths:
                inputs.extend(["-i", video_path])

            filter_complex = "".join([f"[{i}:v:0][{i}:a:0]" for i in range(len(video_paths))])
            filter_complex += f"concat=n={len(video_paths)}:v=1:a=1[outv][outa]"

            cmd = [
                ffmpeg_path,
                *inputs,
                "-filter_complex", filter_complex,
                "-map", "[outv]",
                "-map", "[outa]",
                "-c:v", encoder,
                "-preset", preset,
                "-r", str(fps),
                "-c:a", "aac",
                "-b:a", "192k",
                "-y",
                output_path
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )

            logger.info(f"Successfully concatenated {len(video_paths)} videos using concat filter")
            return True

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg concatenation failed: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Failed to concatenate videos: {e}")
        return False


def add_audio_to_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    subtitle_path: Optional[str] = None,
    force_style: Optional[str] = None
) -> bool:
    """
    Add audio and optionally subtitles to a video file.

    Args:
        video_path: Path to input video file
        audio_path: Path to audio file to add
        output_path: Path for output video file
        subtitle_path: Optional path to ASS subtitle file
        force_style: Optional ASS style override string

    Returns:
        bool: True if successful, False otherwise
    """
    ffmpeg_path = get_ffmpeg_path()

    try:
        cmd = [
            ffmpeg_path,
            "-i", video_path,
            "-i", audio_path
        ]

        filter_parts = []

        if subtitle_path:
            # Escape subtitle path for FFmpeg filter
            escaped_subtitle = subtitle_path.replace('\\', '/').replace(':', '\\:')

            if force_style:
                filter_parts.append(f"subtitles='{escaped_subtitle}':force_style='{force_style}'")
            else:
                filter_parts.append(f"subtitles='{escaped_subtitle}'")

        if filter_parts:
            cmd.extend(["-vf", ",".join(filter_parts)])
        else:
            cmd.extend(["-c:v", "copy"])

        cmd.extend([
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-y",
            output_path
        ])

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        logger.info(f"Successfully added audio to video: {output_path}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed to add audio: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Failed to add audio to video: {e}")
        return False


def extract_audio_from_video(video_path: str, output_audio_path: str) -> bool:
    """
    Extract audio from a video file.

    Args:
        video_path: Path to input video file
        output_audio_path: Path for output audio file

    Returns:
        bool: True if successful, False otherwise
    """
    ffmpeg_path = get_ffmpeg_path()

    try:
        cmd = [
            ffmpeg_path,
            "-i", video_path,
            "-vn",  # No video
            "-acodec", "pcm_s16le",  # PCM audio codec
            "-ar", "44100",  # 44.1kHz sample rate
            "-ac", "2",  # Stereo
            "-y",
            output_audio_path
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        logger.info(f"Successfully extracted audio from video: {output_audio_path}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed to extract audio: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Failed to extract audio from video: {e}")
        return False


def resize_video(
    input_path: str,
    output_path: str,
    width: int,
    height: int,
    maintain_aspect: bool = True
) -> bool:
    """
    Resize a video to specified dimensions.

    Args:
        input_path: Path to input video
        output_path: Path for output video
        width: Target width
        height: Target height
        maintain_aspect: If True, maintain aspect ratio (may result in different dimensions)

    Returns:
        bool: True if successful, False otherwise
    """
    ffmpeg_path = get_ffmpeg_path()
    encoder, encoder_type = detect_best_encoder()

    try:
        if maintain_aspect:
            scale_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease"
        else:
            scale_filter = f"scale={width}:{height}"

        cmd = [
            ffmpeg_path,
            "-i", input_path,
            "-vf", scale_filter,
            "-c:v", encoder,
            "-preset", "medium",
            "-c:a", "copy",
            "-y",
            output_path
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        logger.info(f"Successfully resized video: {output_path}")
        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg failed to resize video: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Failed to resize video: {e}")
        return False
