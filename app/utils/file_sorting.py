"""
File sorting utilities for video processing
Extracted from long_form_creator.py, create_video_from_folder.py, and video_merge.py
"""

import os
import re
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


def extract_sequence_number(filename: str) -> Tuple[int, int, int]:
    """
    Extract sequence number from filename for sorting.

    Handles various filename formats:
    - scene_XX_YYYY.mp4 -> (XX, YYYY, 0)
    - scene_XX.mp4 -> (XX, 0, 0)
    - YYYY.mp4 -> (0, YYYY, 0)
    - other.mp4 -> (999999, 999999, 999999)

    Args:
        filename: The filename to extract sequence from

    Returns:
        Tuple[int, int, int]: (scene_number, sequence_number, fallback)
    """
    # Remove file extension
    name = os.path.splitext(filename)[0]

    # Try to match scene_XX_YYYY pattern
    match = re.match(r'scene_(\d+)_(\d+)', name)
    if match:
        scene_num = int(match.group(1))
        seq_num = int(match.group(2))
        return (scene_num, seq_num, 0)

    # Try to match scene_XX pattern
    match = re.match(r'scene_(\d+)', name)
    if match:
        scene_num = int(match.group(1))
        return (scene_num, 0, 0)

    # Try to match just numbers (YYYY pattern)
    match = re.match(r'^(\d+)$', name)
    if match:
        seq_num = int(match.group(1))
        return (0, seq_num, 0)

    # If no pattern matches, return large numbers to sort last
    logger.warning(f"Could not extract sequence number from filename: {filename}")
    return (999999, 999999, 999999)


def sort_files_by_sequence(file_list: List[str]) -> List[str]:
    """
    Sort a list of files by their sequence numbers.

    Args:
        file_list: List of filenames to sort

    Returns:
        List[str]: Sorted list of filenames
    """
    return sorted(file_list, key=extract_sequence_number)


def filter_video_files(file_list: List[str], extensions: Optional[List[str]] = None) -> List[str]:
    """
    Filter a list of files to only include video files.

    Args:
        file_list: List of filenames to filter
        extensions: List of valid video extensions (default: ['.mp4', '.avi', '.mov', '.mkv', '.webm'])

    Returns:
        List[str]: Filtered list containing only video files
    """
    if extensions is None:
        extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm']

    # Normalize extensions to lowercase
    extensions = [ext.lower() for ext in extensions]

    video_files = []
    for filename in file_list:
        ext = os.path.splitext(filename)[1].lower()
        if ext in extensions:
            video_files.append(filename)
        else:
            logger.debug(f"Skipping non-video file: {filename}")

    return video_files


def filter_audio_files(file_list: List[str], extensions: Optional[List[str]] = None) -> List[str]:
    """
    Filter a list of files to only include audio files.

    Args:
        file_list: List of filenames to filter
        extensions: List of valid audio extensions (default: ['.mp3', '.wav', '.aac', '.m4a', '.flac'])

    Returns:
        List[str]: Filtered list containing only audio files
    """
    if extensions is None:
        extensions = ['.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg']

    # Normalize extensions to lowercase
    extensions = [ext.lower() for ext in extensions]

    audio_files = []
    for filename in file_list:
        ext = os.path.splitext(filename)[1].lower()
        if ext in extensions:
            audio_files.append(filename)
        else:
            logger.debug(f"Skipping non-audio file: {filename}")

    return audio_files


def get_sorted_video_files(directory: str, extensions: Optional[List[str]] = None) -> List[str]:
    """
    Get all video files from a directory, sorted by sequence number.

    Args:
        directory: Directory path to search for videos
        extensions: List of valid video extensions

    Returns:
        List[str]: Full paths to video files, sorted by sequence

    Raises:
        FileNotFoundError: If directory does not exist
        ValueError: If no video files are found
    """
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not os.path.isdir(directory):
        raise ValueError(f"Path is not a directory: {directory}")

    # Get all files in directory
    all_files = os.listdir(directory)

    # Filter video files
    video_files = filter_video_files(all_files, extensions)

    if not video_files:
        raise ValueError(f"No video files found in directory: {directory}")

    # Sort by sequence number
    sorted_files = sort_files_by_sequence(video_files)

    # Convert to full paths
    full_paths = [os.path.join(directory, f) for f in sorted_files]

    logger.info(f"Found {len(full_paths)} video files in {directory}")

    return full_paths


def get_sorted_audio_files(directory: str, extensions: Optional[List[str]] = None) -> List[str]:
    """
    Get all audio files from a directory, sorted by sequence number.

    Args:
        directory: Directory path to search for audio files
        extensions: List of valid audio extensions

    Returns:
        List[str]: Full paths to audio files, sorted by sequence

    Raises:
        FileNotFoundError: If directory does not exist
        ValueError: If no audio files are found
    """
    if not os.path.exists(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    if not os.path.isdir(directory):
        raise ValueError(f"Path is not a directory: {directory}")

    # Get all files in directory
    all_files = os.listdir(directory)

    # Filter audio files
    audio_files = filter_audio_files(all_files, extensions)

    if not audio_files:
        raise ValueError(f"No audio files found in directory: {directory}")

    # Sort by sequence number
    sorted_files = sort_files_by_sequence(audio_files)

    # Convert to full paths
    full_paths = [os.path.join(directory, f) for f in sorted_files]

    logger.info(f"Found {len(full_paths)} audio files in {directory}")

    return full_paths


def pair_video_audio_files(video_files: List[str], audio_files: List[str]) -> List[Tuple[str, Optional[str]]]:
    """
    Pair video files with corresponding audio files based on sequence numbers.

    Args:
        video_files: List of video file paths (should be sorted)
        audio_files: List of audio file paths (should be sorted)

    Returns:
        List[Tuple[str, Optional[str]]]: List of (video_path, audio_path) pairs
                                         audio_path is None if no matching audio found
    """
    pairs = []

    # Create a map of sequence number to audio file
    audio_map = {}
    for audio_file in audio_files:
        filename = os.path.basename(audio_file)
        seq = extract_sequence_number(filename)
        audio_map[seq] = audio_file

    # Pair videos with audio
    for video_file in video_files:
        filename = os.path.basename(video_file)
        seq = extract_sequence_number(filename)

        audio_file = audio_map.get(seq)
        pairs.append((video_file, audio_file))

        if audio_file:
            logger.debug(f"Paired {filename} with {os.path.basename(audio_file)}")
        else:
            logger.warning(f"No matching audio found for {filename}")

    return pairs


def validate_file_sequence(file_list: List[str], check_gaps: bool = True) -> Tuple[bool, List[str]]:
    """
    Validate that files have a proper sequence with no unexpected gaps.

    Args:
        file_list: List of filenames to validate
        check_gaps: If True, report gaps in sequence numbers

    Returns:
        Tuple[bool, List[str]]: (is_valid, list of warning messages)
    """
    warnings = []

    if not file_list:
        return False, ["File list is empty"]

    sequences = [extract_sequence_number(f) for f in file_list]

    # Check for duplicates
    if len(sequences) != len(set(sequences)):
        warnings.append("Duplicate sequence numbers detected")

    if check_gaps:
        # Extract scene numbers and sequence numbers
        scene_nums = [s[0] for s in sequences if s[0] != 999999]
        seq_nums = [s[1] for s in sequences if s[1] != 999999]

        # Check for gaps in scene numbers
        if scene_nums:
            scene_nums_sorted = sorted(set(scene_nums))
            for i in range(len(scene_nums_sorted) - 1):
                if scene_nums_sorted[i+1] - scene_nums_sorted[i] > 1:
                    warnings.append(
                        f"Gap detected in scene numbers: {scene_nums_sorted[i]} -> {scene_nums_sorted[i+1]}"
                    )

        # Check for gaps in sequence numbers
        if seq_nums:
            seq_nums_sorted = sorted(set(seq_nums))
            if seq_nums_sorted[0] != 0:  # Sequences should start at 0
                for i in range(len(seq_nums_sorted) - 1):
                    if seq_nums_sorted[i+1] - seq_nums_sorted[i] > 1:
                        warnings.append(
                            f"Gap detected in sequence numbers: {seq_nums_sorted[i]} -> {seq_nums_sorted[i+1]}"
                        )

    is_valid = len(warnings) == 0
    return is_valid, warnings
