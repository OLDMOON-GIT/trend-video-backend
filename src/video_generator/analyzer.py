"""Video analyzer for detecting scenes, silence, and static content."""

import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any
import cv2
import numpy as np
from scenedetect import detect, AdaptiveDetector, split_video_ffmpeg


class VideoAnalyzer:
    """Analyze video for editing decisions."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("AutoShortsEditor.Analyzer")

    def analyze(self, video_path: Path) -> Dict[str, Any]:
        """
        Perform full video analysis.

        Args:
            video_path: Path to video file

        Returns:
            Analysis results dictionary
        """
        self.logger.info(f"Analyzing video: {video_path}")

        results = {
            "video_path": str(video_path),
            "scenes": [],
            "silence_segments": [],
            "static_segments": [],
            "duration": 0,
            "has_audio": False
        }

        # Get basic info
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(str(video_path))
        results["duration"] = clip.duration
        results["has_audio"] = clip.audio is not None
        clip.close()

        # Detect scenes
        self.logger.info("Detecting scene changes...")
        results["scenes"] = self.detect_scenes(video_path)
        self.logger.info(f"Found {len(results['scenes'])} scenes")

        # Detect silence (if audio exists)
        if results["has_audio"]:
            self.logger.info("Detecting silence...")
            results["silence_segments"] = self.detect_silence(video_path)
            self.logger.info(f"Found {len(results['silence_segments'])} silent segments")

        # Detect static scenes
        self.logger.info("Detecting static scenes...")
        results["static_segments"] = self.detect_static_scenes(video_path)
        self.logger.info(f"Found {len(results['static_segments'])} static segments")

        return results

    def detect_scenes(self, video_path: Path) -> List[Tuple[float, float]]:
        """
        Detect scene changes in video.

        Args:
            video_path: Path to video file

        Returns:
            List of (start_time, end_time) tuples for each scene
        """
        try:
            # Use scenedetect library
            scene_list = detect(str(video_path), AdaptiveDetector())

            # Convert to time tuples
            scenes = []
            for i, scene in enumerate(scene_list):
                start_time = scene[0].get_seconds()
                end_time = scene[1].get_seconds()

                # Filter out very short scenes
                min_duration = self.config["video"].get("min_scene_duration", 2.0)
                if end_time - start_time >= min_duration:
                    scenes.append((start_time, end_time))

            return scenes

        except Exception as e:
            self.logger.error(f"Scene detection failed: {e}")
            # Return single scene for entire video as fallback
            from moviepy.editor import VideoFileClip
            clip = VideoFileClip(str(video_path))
            duration = clip.duration
            clip.close()
            return [(0, duration)]

    def detect_silence(self, video_path: Path) -> List[Tuple[float, float]]:
        """
        Detect silence in audio track using moviepy.

        Args:
            video_path: Path to video file

        Returns:
            List of (start_time, end_time) tuples for silent segments
        """
        try:
            from moviepy.editor import VideoFileClip

            clip = VideoFileClip(str(video_path))

            if clip.audio is None:
                clip.close()
                return []

            # Get audio as numpy array
            fps = clip.audio.fps
            audio_array = clip.audio.to_soundarray(fps=fps)

            # If stereo, convert to mono by averaging channels
            if len(audio_array.shape) > 1 and audio_array.shape[1] > 1:
                audio_array = np.mean(audio_array, axis=1)

            clip.close()

            # Calculate RMS (Root Mean Square) for volume detection
            silence_thresh_linear = 10 ** (self.config["audio"]["silence_threshold_db"] / 20.0)
            min_silence_samples = int(self.config["audio"]["min_silence_duration"] * fps)

            # Sliding window to detect silence
            window_size = int(fps * 0.1)  # 100ms windows
            silence_segments = []
            is_silent = False
            silence_start = 0

            for i in range(0, len(audio_array), window_size):
                window = audio_array[i:i + window_size]
                rms = np.sqrt(np.mean(window ** 2))

                if rms < silence_thresh_linear:
                    if not is_silent:
                        silence_start = i
                        is_silent = True
                else:
                    if is_silent:
                        silence_duration = i - silence_start
                        if silence_duration >= min_silence_samples:
                            start_time = silence_start / fps
                            end_time = i / fps
                            silence_segments.append((start_time, end_time))
                        is_silent = False

            # Check for silence at the end
            if is_silent:
                silence_duration = len(audio_array) - silence_start
                if silence_duration >= min_silence_samples:
                    start_time = silence_start / fps
                    end_time = len(audio_array) / fps
                    silence_segments.append((start_time, end_time))

            return silence_segments

        except Exception as e:
            self.logger.error(f"Silence detection failed: {e}")
            return []

    def detect_static_scenes(self, video_path: Path) -> List[Tuple[float, float]]:
        """
        Detect static (unchanging) scenes in video.

        Args:
            video_path: Path to video file

        Returns:
            List of (start_time, end_time) tuples for static segments
        """
        try:
            cap = cv2.VideoCapture(str(video_path))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            if fps == 0 or total_frames == 0:
                cap.release()
                return []

            threshold = self.config["video"].get("static_threshold", 30.0)
            min_duration = self.config["video"].get("min_scene_duration", 2.0)
            min_frames = int(min_duration * fps)

            static_segments = []
            prev_frame = None
            static_start = None
            static_count = 0

            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Convert to grayscale for comparison
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_frame is not None:
                    # Calculate difference
                    diff = cv2.absdiff(prev_frame, gray)
                    mean_diff = np.mean(diff)

                    if mean_diff < threshold:
                        # Static frame
                        if static_start is None:
                            static_start = frame_idx
                        static_count += 1
                    else:
                        # Motion detected
                        if static_count >= min_frames and static_start is not None:
                            start_time = static_start / fps
                            end_time = frame_idx / fps
                            static_segments.append((start_time, end_time))

                        static_start = None
                        static_count = 0

                prev_frame = gray
                frame_idx += 1

                # Progress indication every 100 frames
                if frame_idx % 100 == 0:
                    progress = (frame_idx / total_frames) * 100
                    self.logger.debug(f"Static scene detection: {progress:.1f}%")

            # Check for static segment at the end
            if static_count >= min_frames and static_start is not None:
                start_time = static_start / fps
                end_time = frame_idx / fps
                static_segments.append((start_time, end_time))

            cap.release()

            return static_segments

        except Exception as e:
            self.logger.error(f"Static scene detection failed: {e}")
            return []

    def score_scenes(self, scenes: List[Tuple[float, float]], video_path: Path) -> List[Dict[str, Any]]:
        """
        Score scenes by importance (for highlight extraction).

        Args:
            scenes: List of scene time ranges
            video_path: Path to video file

        Returns:
            List of scene dictionaries with scores
        """
        scored_scenes = []

        for i, (start, end) in enumerate(scenes):
            score = 0.0
            duration = end - start

            # Longer scenes are generally more important
            if 3 <= duration <= 15:
                score += 10
            elif duration > 15:
                score += 5

            # Middle scenes tend to be more important than start/end
            scene_position = i / len(scenes) if len(scenes) > 1 else 0.5
            if 0.2 <= scene_position <= 0.8:
                score += 5

            scored_scenes.append({
                "start": start,
                "end": end,
                "duration": duration,
                "score": score
            })

        # Sort by score
        scored_scenes.sort(key=lambda x: x["score"], reverse=True)

        return scored_scenes
