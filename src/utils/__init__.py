"""Utility modules for trend-video-backend."""
from .db_log_handler import DatabaseLogHandler, setup_db_logging, auto_setup_db_logging
from .ffmpeg_utils import (
    get_ffmpeg_path,
    get_video_duration,
    get_audio_duration,
    detect_best_encoder,
    format_ass_time,
    format_ass_timestamp,
)

__all__ = [
    'DatabaseLogHandler',
    'setup_db_logging',
    'auto_setup_db_logging',
    'get_ffmpeg_path',
    'get_video_duration',
    'get_audio_duration',
    'detect_best_encoder',
    'format_ass_time',
    'format_ass_timestamp',
]
