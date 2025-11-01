"""Utility functions for AutoShortsEditor."""

import json
import logging
from pathlib import Path
from typing import Dict, Any


def load_config(config_path: str = "config/config.json") -> Dict[str, Any]:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config file

    Returns:
        Configuration dictionary
    """
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def setup_logging(log_file: str = "logs/auto_shorts.log", level: str = "INFO") -> logging.Logger:
    """
    Setup logging configuration.

    Args:
        log_file: Path to log file
        level: Logging level

    Returns:
        Configured logger
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

    return logging.getLogger("AutoShortsEditor")


def format_time(seconds: float) -> str:
    """
    Format seconds to HH:MM:SS.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def get_video_info(video_path: Path) -> Dict[str, Any]:
    """
    Get basic video information.

    Args:
        video_path: Path to video file

    Returns:
        Dictionary with video info
    """
    from moviepy.editor import VideoFileClip

    clip = VideoFileClip(str(video_path))
    info = {
        "duration": clip.duration,
        "fps": clip.fps,
        "size": clip.size,
        "width": clip.w,
        "height": clip.h,
        "aspect_ratio": clip.w / clip.h if clip.h > 0 else 0,
        "audio": clip.audio is not None
    }
    clip.close()

    return info
