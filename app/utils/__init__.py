"""
Common utility modules for video processing
"""

from .ffmpeg_utils import (
    get_ffmpeg_path,
    get_ffprobe_path,
    get_video_duration,
    get_audio_duration,
    detect_best_encoder,
    concatenate_videos,
    add_audio_to_video,
    extract_audio_from_video,
    resize_video,
)

from .file_sorting import (
    extract_sequence_number,
    sort_files_by_sequence,
    filter_video_files,
    filter_audio_files,
    get_sorted_video_files,
    get_sorted_audio_files,
    pair_video_audio_files,
    validate_file_sequence,
)

from .tts_generator import (
    WordTimestamp,
    generate_tts_with_timestamps,
    generate_tts_sync,
    generate_tts_simple,
    generate_tts_simple_sync,
    generate_batch_tts,
    generate_batch_tts_sync,
    get_available_voices,
    validate_voice,
    estimate_tts_duration,
)

from .subtitle_generator import (
    SubtitleSegment,
    format_ass_time,
    generate_ass_subtitle,
    transcribe_audio_to_segments,
    generate_subtitle_from_audio,
    merge_short_segments,
    split_long_segments,
    adjust_subtitle_timing,
    create_korean_subtitle_style,
    create_english_subtitle_style,
    validate_subtitle_file,
)

__all__ = [
    # FFmpeg utilities
    "get_ffmpeg_path",
    "get_ffprobe_path",
    "get_video_duration",
    "get_audio_duration",
    "detect_best_encoder",
    "concatenate_videos",
    "add_audio_to_video",
    "extract_audio_from_video",
    "resize_video",
    # File sorting utilities
    "extract_sequence_number",
    "sort_files_by_sequence",
    "filter_video_files",
    "filter_audio_files",
    "get_sorted_video_files",
    "get_sorted_audio_files",
    "pair_video_audio_files",
    "validate_file_sequence",
    # TTS utilities
    "WordTimestamp",
    "generate_tts_with_timestamps",
    "generate_tts_sync",
    "generate_tts_simple",
    "generate_tts_simple_sync",
    "generate_batch_tts",
    "generate_batch_tts_sync",
    "get_available_voices",
    "validate_voice",
    "estimate_tts_duration",
    # Subtitle utilities
    "SubtitleSegment",
    "format_ass_time",
    "generate_ass_subtitle",
    "transcribe_audio_to_segments",
    "generate_subtitle_from_audio",
    "merge_short_segments",
    "split_long_segments",
    "adjust_subtitle_timing",
    "create_korean_subtitle_style",
    "create_english_subtitle_style",
    "validate_subtitle_file",
]
