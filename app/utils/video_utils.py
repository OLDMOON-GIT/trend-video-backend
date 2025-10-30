"""Video processing utilities."""

from pathlib import Path
from typing import Dict, Any


def get_video_info(video_path: Path) -> Dict[str, Any]:
    """
    Get video file information.

    TODO: Implement using moviepy or ffmpeg-python
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Placeholder implementation
    return {
        "duration": 0.0,
        "width": 1080,
        "height": 1920,
        "fps": 30.0,
        "audio": True,
        "size": video_path.stat().st_size if video_path.exists() else 0
    }


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS or HH:MM:SS."""
    if seconds < 3600:
        return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"
