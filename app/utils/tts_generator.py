"""
Text-to-Speech generation utilities using Edge TTS
Extracted from long_form_creator.py, create_video_from_folder.py, and video_merge.py
"""

import asyncio
import edge_tts
from typing import List, Tuple, Optional, Dict
import logging
import os

logger = logging.getLogger(__name__)


class WordTimestamp:
    """Represents a word with its timing information."""

    def __init__(self, word: str, start_time: float, end_time: float):
        self.word = word
        self.start_time = start_time
        self.end_time = end_time

    def __repr__(self):
        return f"WordTimestamp(word='{self.word}', start={self.start_time:.3f}, end={self.end_time:.3f})"


async def generate_tts_with_timestamps(
    text: str,
    output_path: str,
    voice: str = "ko-KR-SunHiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> Tuple[List[WordTimestamp], float]:
    """
    Generate TTS audio with word-level timestamps using Edge TTS.

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: Voice to use (default: Korean female voice)
        rate: Speech rate adjustment (e.g., "+10%", "-5%")
        pitch: Pitch adjustment (e.g., "+5Hz", "-10Hz")

    Returns:
        Tuple[List[WordTimestamp], float]: (word_timestamps, total_duration)

    Raises:
        RuntimeError: If TTS generation fails
    """
    word_timestamps = []
    total_duration = 0.0

    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)

        # Track word boundaries
        current_word = None
        current_start = None

        with open(output_path, "wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])

                elif chunk["type"] == "WordBoundary":
                    # Save previous word if exists
                    if current_word is not None and current_start is not None:
                        end_time = chunk["offset"] / 10_000_000.0  # Convert to seconds
                        word_timestamps.append(
                            WordTimestamp(current_word, current_start, end_time)
                        )

                    # Start new word
                    current_word = chunk.get("text", "")
                    current_start = chunk["offset"] / 10_000_000.0

                    # Update total duration
                    total_duration = chunk["offset"] / 10_000_000.0 + chunk.get("duration", 0) / 10_000_000.0

        # Add the last word if exists
        if current_word is not None and current_start is not None:
            word_timestamps.append(
                WordTimestamp(current_word, current_start, total_duration)
            )

        logger.info(f"Generated TTS audio: {output_path} ({total_duration:.2f}s, {len(word_timestamps)} words)")

        return word_timestamps, total_duration

    except Exception as e:
        logger.error(f"Failed to generate TTS: {e}")
        raise RuntimeError(f"TTS generation failed: {e}")


def generate_tts_sync(
    text: str,
    output_path: str,
    voice: str = "ko-KR-SunHiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> Tuple[List[WordTimestamp], float]:
    """
    Synchronous wrapper for TTS generation with timestamps.

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: Voice to use
        rate: Speech rate adjustment
        pitch: Pitch adjustment

    Returns:
        Tuple[List[WordTimestamp], float]: (word_timestamps, total_duration)
    """
    return asyncio.run(
        generate_tts_with_timestamps(text, output_path, voice, rate, pitch)
    )


async def generate_tts_simple(
    text: str,
    output_path: str,
    voice: str = "ko-KR-SunHiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> float:
    """
    Generate TTS audio without word timestamps (faster).

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: Voice to use
        rate: Speech rate adjustment
        pitch: Pitch adjustment

    Returns:
        float: Estimated audio duration in seconds

    Raises:
        RuntimeError: If TTS generation fails
    """
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)

        await communicate.save(output_path)

        # Estimate duration (rough calculation: ~150 words per minute for Korean)
        word_count = len(text.split())
        estimated_duration = (word_count / 150) * 60

        logger.info(f"Generated TTS audio: {output_path} (~{estimated_duration:.2f}s)")

        return estimated_duration

    except Exception as e:
        logger.error(f"Failed to generate TTS: {e}")
        raise RuntimeError(f"TTS generation failed: {e}")


def generate_tts_simple_sync(
    text: str,
    output_path: str,
    voice: str = "ko-KR-SunHiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> float:
    """
    Synchronous wrapper for simple TTS generation.

    Args:
        text: Text to convert to speech
        output_path: Path to save the audio file
        voice: Voice to use
        rate: Speech rate adjustment
        pitch: Pitch adjustment

    Returns:
        float: Estimated audio duration in seconds
    """
    return asyncio.run(
        generate_tts_simple(text, output_path, voice, rate, pitch)
    )


async def generate_batch_tts(
    texts: List[Tuple[str, str]],
    voice: str = "ko-KR-SunHiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> List[Tuple[str, List[WordTimestamp], float]]:
    """
    Generate TTS for multiple texts in batch.

    Args:
        texts: List of (text, output_path) tuples
        voice: Voice to use
        rate: Speech rate adjustment
        pitch: Pitch adjustment

    Returns:
        List[Tuple[str, List[WordTimestamp], float]]: List of (output_path, timestamps, duration)
    """
    results = []

    tasks = []
    for text, output_path in texts:
        task = generate_tts_with_timestamps(text, output_path, voice, rate, pitch)
        tasks.append((output_path, task))

    # Run all TTS generations concurrently
    for output_path, task in tasks:
        try:
            timestamps, duration = await task
            results.append((output_path, timestamps, duration))
        except Exception as e:
            logger.error(f"Failed to generate TTS for {output_path}: {e}")
            results.append((output_path, [], 0.0))

    return results


def generate_batch_tts_sync(
    texts: List[Tuple[str, str]],
    voice: str = "ko-KR-SunHiNeural",
    rate: str = "+0%",
    pitch: str = "+0Hz"
) -> List[Tuple[str, List[WordTimestamp], float]]:
    """
    Synchronous wrapper for batch TTS generation.

    Args:
        texts: List of (text, output_path) tuples
        voice: Voice to use
        rate: Speech rate adjustment
        pitch: Pitch adjustment

    Returns:
        List[Tuple[str, List[WordTimestamp], float]]: List of (output_path, timestamps, duration)
    """
    return asyncio.run(
        generate_batch_tts(texts, voice, rate, pitch)
    )


def get_available_voices() -> Dict[str, List[str]]:
    """
    Get available voices grouped by language.

    Returns:
        Dict[str, List[str]]: Dictionary mapping language codes to voice names
    """
    # Common voices for different languages
    voices = {
        "ko-KR": [
            "ko-KR-SunHiNeural",  # Female
            "ko-KR-InJoonNeural",  # Male
            "ko-KR-BongJinNeural",  # Male
            "ko-KR-GookMinNeural",  # Male
            "ko-KR-JiMinNeural",  # Female
        ],
        "en-US": [
            "en-US-AriaNeural",  # Female
            "en-US-GuyNeural",  # Male
            "en-US-JennyNeural",  # Female
            "en-US-ChristopherNeural",  # Male
        ],
        "ja-JP": [
            "ja-JP-NanamiNeural",  # Female
            "ja-JP-KeitaNeural",  # Male
        ],
        "zh-CN": [
            "zh-CN-XiaoxiaoNeural",  # Female
            "zh-CN-YunxiNeural",  # Male
        ]
    }

    return voices


def validate_voice(voice: str) -> bool:
    """
    Validate if a voice name is in the known voices list.

    Args:
        voice: Voice name to validate

    Returns:
        bool: True if voice is valid, False otherwise
    """
    all_voices = get_available_voices()

    for language_voices in all_voices.values():
        if voice in language_voices:
            return True

    return False


def estimate_tts_duration(text: str, words_per_minute: int = 150) -> float:
    """
    Estimate TTS duration based on text length.

    Args:
        text: Text to estimate duration for
        words_per_minute: Speaking rate (default: 150 for Korean)

    Returns:
        float: Estimated duration in seconds
    """
    word_count = len(text.split())
    duration = (word_count / words_per_minute) * 60
    return duration
