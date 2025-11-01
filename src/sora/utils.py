"""Utility functions for Sora Extend."""

import os
import sys
import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional, List
import mimetypes

import cv2
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)


def setup_logging(log_file: str = "logs/sora_extend.log", level: str = "INFO") -> logging.Logger:
    """Setup logging configuration."""
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("SoraExtend")
    logger.setLevel(getattr(logging, level.upper()))

    # File handler
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(file_fmt)

    # Console handler with colors
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    console_fmt = ColoredFormatter('%(levelname)s: %(message)s')
    ch.setFormatter(console_fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    return logger


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors."""

    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT
    }

    def format(self, record):
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{Style.RESET_ALL}"
        return super().format(record)


def load_config(config_path: str = "config/config.json") -> dict:
    """Load configuration from JSON file."""
    with open(config_path, 'r') as f:
        return json.load(f)


def get_ffmpeg_path() -> Optional[str]:
    """Get FFmpeg executable path."""
    # Try system ffmpeg first
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg

    # Try imageio-ffmpeg
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    return None


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        return False

    try:
        result = subprocess.run(
            [ffmpeg, "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def extract_last_frame(video_path: Path, output_path: Path) -> Path:
    """Extract the last frame from a video file."""
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open video: {video_path}")

    # Try to seek to last frame
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame = None
    success = False

    if total_frames > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)
        success, frame = cap.read()

    # Fallback: read all frames
    if not success or frame is None:
        cap.release()
        cap = cv2.VideoCapture(str(video_path))
        while True:
            ret, f = cap.read()
            if not ret:
                break
            frame = f
            success = True

    cap.release()

    if not success or frame is None:
        raise RuntimeError(f"Could not read last frame from {video_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(output_path), frame)
    if not ok:
        raise RuntimeError(f"Failed to write frame to {output_path}")

    return output_path


def concatenate_videos_lossless(segment_paths: List[Path], output_path: Path) -> Path:
    """
    Concatenate videos using FFmpeg lossless concat demuxer.
    Much faster and no quality loss compared to re-encoding.
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("FFmpeg not found. Install FFmpeg or imageio-ffmpeg.")

    # Create concat file
    concat_file = output_path.with_suffix('.txt')
    with open(concat_file, 'w', encoding='utf-8') as f:
        for path in segment_paths:
            # FFmpeg concat format requires forward slashes even on Windows
            path_str = str(path.resolve()).replace('\\', '/')
            f.write(f"file '{path_str}'\n")

    try:
        cmd = [
            ffmpeg,
            '-y',  # Overwrite output
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
            raise RuntimeError(f"FFmpeg failed:\n{result.stderr}")

    finally:
        # Clean up concat file
        if concat_file.exists():
            concat_file.unlink()

    if not output_path.exists():
        raise RuntimeError(f"Output video not created: {output_path}")

    return output_path


def concatenate_videos_fallback(segment_paths: List[Path], output_path: Path) -> Path:
    """
    Fallback concatenation using MoviePy (re-encodes, slower but more compatible).
    """
    try:
        from moviepy.editor import VideoFileClip, concatenate_videoclips
    except ImportError:
        raise ImportError("MoviePy not available. Install with: pip install moviepy")

    clips = []
    try:
        for path in segment_paths:
            clips.append(VideoFileClip(str(path)))

        if not clips:
            raise ValueError("No video clips to concatenate")

        target_fps = clips[0].fps or 24
        result = concatenate_videoclips(clips, method="compose")
        result.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            fps=target_fps,
            preset="medium",
            threads=0,
            logger=None  # Suppress MoviePy logs
        )

    finally:
        for clip in clips:
            try:
                clip.close()
            except Exception:
                pass

    return output_path


def guess_mime_type(path: Path) -> str:
    """Guess MIME type of a file."""
    mime_type = mimetypes.guess_type(str(path))[0]
    return mime_type or "application/octet-stream"


def validate_duration(seconds: int, supported: List[int]) -> None:
    """Validate video duration is supported."""
    if seconds not in supported:
        raise ValueError(
            f"Invalid duration: {seconds}s. "
            f"Sora 2 only supports: {', '.join(map(str, supported))}s"
        )


def validate_size(size: str, supported: List[str]) -> None:
    """Validate video size is supported."""
    if size not in supported:
        raise ValueError(
            f"Invalid size: {size}. "
            f"Supported sizes: {', '.join(supported)}"
        )


def create_progress_bar(total: int, desc: str = "") -> 'tqdm':
    """Create a progress bar."""
    from tqdm import tqdm
    return tqdm(
        total=total,
        desc=desc,
        bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]',
        colour='green'
    )
