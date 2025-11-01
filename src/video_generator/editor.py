"""Auto video editor for creating shorts."""

import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any
from moviepy.editor import (
    VideoFileClip, concatenate_videoclips, CompositeVideoClip,
    vfx, ColorClip
)
from moviepy.video.fx.all import crop, resize


class AutoEditor:
    """Automatically edit videos for shorts format."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("AutoShortsEditor.Editor")

    def edit(
        self,
        video_path: Path,
        analysis: Dict[str, Any],
        output_path: Path
    ) -> Path:
        """
        Perform automatic editing.

        Args:
            video_path: Path to input video
            analysis: Analysis results from VideoAnalyzer
            output_path: Path for output video

        Returns:
            Path to edited video
        """
        self.logger.info(f"Starting auto-edit: {video_path.name}")

        # Load video
        clip = VideoFileClip(str(video_path))
        original_duration = clip.duration

        # Step 1: Extract best scenes if video is too long
        target_duration = self.config["video"]["target_duration"]
        if original_duration > target_duration * 1.5:
            print(f"\n✂ Original video is {original_duration:.1f}s, extracting best scenes...")
            clip = self._extract_best_scenes(clip, analysis, target_duration)
        else:
            # Step 1b: Remove unwanted segments
            clip = self._remove_unwanted_segments(clip, analysis)

        # Step 2: Convert to shorts aspect ratio
        if self.config["editing"]["auto_crop"]:
            clip = self._convert_to_shorts_format(clip)

        # Step 3: Ensure target duration
        clip = self._adjust_duration(clip)

        # Step 4: Add transitions (if enabled)
        if self.config["editing"]["add_transitions"]:
            clip = self._add_transitions(clip)

        # Step 5: Normalize audio
        if clip.audio and self.config["audio"]["normalize"]:
            clip = self._normalize_audio(clip)

        # Step 6: Add subtitles (if enabled)
        if self.config["ai"]["add_subtitles"]:
            clip = self._add_subtitles_to_clip(clip, video_path, output_path)

        # Step 7: Add narration (if enabled)
        if self.config["ai"]["add_narration"]:
            clip = self._add_narration_to_clip(clip, video_path)

        # Export
        self.logger.info(f"Exporting to: {output_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"\n[Export] Exporting video...")
        print(f"   Output: {output_path.name}")
        print(f"   Duration: {clip.duration:.1f}s\n")

        clip.write_videofile(
            str(output_path),
            codec=self.config["output"]["codec"],
            audio_codec=self.config["output"]["audio_codec"],
            bitrate=self.config["output"]["bitrate"],
            audio_bitrate=self.config["output"]["audio_bitrate"],
            fps=self.config["video"]["fps"],
            preset='medium',
            threads=4,
            logger='bar'  # Show progress bar
        )

        clip.close()

        self.logger.info(f"[OK] Edit complete: {output_path}")
        return output_path

    def _extract_best_scenes(
        self,
        clip: VideoFileClip,
        analysis: Dict[str, Any],
        target_duration: float
    ) -> VideoFileClip:
        """
        Extract best scenes to fit target duration.

        Args:
            clip: Video clip
            analysis: Analysis results
            target_duration: Target duration in seconds

        Returns:
            Edited clip with best scenes
        """
        from .analyzer import VideoAnalyzer
        analyzer = VideoAnalyzer(self.config)

        # Score scenes
        scored_scenes = analyzer.score_scenes(analysis["scenes"], Path("temp"))

        # Select best scenes that fit target duration
        selected_clips = []
        current_duration = 0

        for scene in scored_scenes:
            if current_duration >= target_duration:
                break

            scene_duration = scene["end"] - scene["start"]
            remaining = target_duration - current_duration

            if scene_duration <= remaining:
                # Take whole scene
                selected_clips.append(clip.subclip(scene["start"], scene["end"]))
                current_duration += scene_duration
            else:
                # Take part of scene
                selected_clips.append(clip.subclip(scene["start"], scene["start"] + remaining))
                current_duration += remaining
                break

        if selected_clips:
            print(f"   Selected {len(selected_clips)} best scenes → {current_duration:.1f}s")
            return concatenate_videoclips(selected_clips, method="compose")

        return clip

    def _remove_unwanted_segments(
        self,
        clip: VideoFileClip,
        analysis: Dict[str, Any]
    ) -> VideoFileClip:
        """Remove silence and static segments."""
        segments_to_keep = []
        duration = clip.duration

        # Start with full video
        keep_ranges = [(0, duration)]

        # Remove silence
        if self.config["editing"]["remove_silence"] and analysis["silence_segments"]:
            self.logger.info(f"Removing {len(analysis['silence_segments'])} silent segments")
            keep_ranges = self._subtract_segments(keep_ranges, analysis["silence_segments"])

        # Remove static scenes
        if self.config["editing"]["remove_static_scenes"] and analysis["static_segments"]:
            self.logger.info(f"Removing {len(analysis['static_segments'])} static segments")
            keep_ranges = self._subtract_segments(keep_ranges, analysis["static_segments"])

        # Extract clips
        if keep_ranges:
            clips = []
            for start, end in keep_ranges:
                if end - start > 0.5:  # Skip very short segments
                    subclip = clip.subclip(start, end)
                    clips.append(subclip)

            if clips:
                self.logger.info(f"Concatenating {len(clips)} segments")
                return concatenate_videoclips(clips, method="compose")

        return clip

    def _subtract_segments(
        self,
        keep_ranges: List[Tuple[float, float]],
        remove_ranges: List[Tuple[float, float]]
    ) -> List[Tuple[float, float]]:
        """Subtract remove_ranges from keep_ranges."""
        result = []

        for keep_start, keep_end in keep_ranges:
            current_start = keep_start

            for remove_start, remove_end in sorted(remove_ranges):
                # If removal is before current segment, skip
                if remove_end <= current_start:
                    continue

                # If removal is after current segment, we're done with this segment
                if remove_start >= keep_end:
                    break

                # If removal overlaps, split the segment
                if remove_start > current_start:
                    result.append((current_start, remove_start))

                current_start = max(current_start, remove_end)

            # Add remaining part
            if current_start < keep_end:
                result.append((current_start, keep_end))

        return result

    def _convert_to_shorts_format(self, clip: VideoFileClip) -> VideoFileClip:
        """Convert to 9:16 aspect ratio."""
        target_aspect = self.config["video"]["aspect_ratio"]

        if target_aspect == "9:16":
            target_width = self.config["video"]["resolution"]["width"]
            target_height = self.config["video"]["resolution"]["height"]

            self.logger.info(f"Converting to {target_width}x{target_height} (9:16)")

            # Calculate crop dimensions
            current_aspect = clip.w / clip.h
            target_aspect_value = target_width / target_height

            if current_aspect > target_aspect_value:
                # Video is wider - crop width
                new_width = int(clip.h * target_aspect_value)
                new_height = clip.h
                x_center = clip.w / 2
                y_center = clip.h / 2
            else:
                # Video is taller - crop height
                new_width = clip.w
                new_height = int(clip.w / target_aspect_value)
                x_center = clip.w / 2
                y_center = clip.h / 2

            # Crop to center
            clip = crop(
                clip,
                width=new_width,
                height=new_height,
                x_center=x_center,
                y_center=y_center
            )

            # Resize to target resolution
            clip = resize(clip, height=target_height)

        return clip

    def _adjust_duration(self, clip: VideoFileClip) -> VideoFileClip:
        """Adjust video to target duration."""
        target_duration = self.config["video"]["target_duration"]
        max_duration = self.config["video"]["max_duration"]
        min_duration = self.config["video"]["min_duration"]

        current_duration = clip.duration

        if current_duration > max_duration:
            self.logger.info(f"Trimming from {current_duration:.1f}s to {max_duration}s")
            # Take the best middle part
            start_time = (current_duration - max_duration) / 2
            clip = clip.subclip(start_time, start_time + max_duration)

        elif current_duration < min_duration:
            self.logger.warning(f"Video too short: {current_duration:.1f}s (min: {min_duration}s)")
            # Could loop or slow down here if needed

        elif current_duration > target_duration:
            # Try to speed up slightly
            if self.config["editing"]["speed_up_boring_parts"]:
                speed = current_duration / target_duration
                if 1.0 < speed <= self.config["editing"]["speed_multiplier"]:
                    self.logger.info(f"Speeding up by {speed:.2f}x")
                    clip = clip.fx(vfx.speedx, speed)

        return clip

    def _add_transitions(self, clip: VideoFileClip) -> VideoFileClip:
        """Add fade transitions."""
        fade_duration = self.config["editing"]["transition_duration"]

        # Add fade in at start
        clip = clip.fadein(fade_duration)

        # Add fade out at end
        clip = clip.fadeout(fade_duration)

        return clip

    def _normalize_audio(self, clip: VideoFileClip) -> VideoFileClip:
        """Normalize audio levels."""
        if clip.audio:
            try:
                # Try to use audio_normalize if available
                from moviepy.audio.fx.audio_normalize import audio_normalize
                clip = clip.fx(audio_normalize)
            except (ImportError, AttributeError):
                # If not available, skip normalization
                self.logger.debug("Audio normalization not available, skipping")

        return clip

    def _add_subtitles_to_clip(self, clip: VideoFileClip, video_path: Path, output_path: Path = None) -> VideoFileClip:
        """Add subtitles to clip using transcription and optionally export SRT."""
        try:
            from .transcriber import Transcriber

            transcriber = Transcriber(self.config)

            # Transcribe
            segments = transcriber.transcribe_video(video_path)

            if segments:
                # Export SRT file if requested or if it's an output path
                if output_path and self.config.get("ai", {}).get("export_srt", False):
                    srt_path = transcriber.create_srt_file(segments, output_path)
                    print(f"[OK] SRT file saved: {srt_path.name}")

                # Add subtitles to video
                clip = transcriber.add_subtitles(clip, segments)

            return clip

        except Exception as e:
            self.logger.error(f"Failed to add subtitles: {e}")
            print(f"[Warning] Subtitle generation failed: {e}")
            return clip

    def _add_narration_to_clip(self, clip: VideoFileClip, video_path: Path) -> VideoFileClip:
        """Add AI narration to clip with duration matching."""
        try:
            from .narrator import Narrator
            from moviepy.editor import AudioFileClip

            # Generate Korean narration based on content
            narrator = Narrator(self.config)
            script = narrator.generate_narration_script(
                video_path,
                transcription=None  # Will transcribe internally
            )

            # Generate Korean speech
            temp_audio = video_path.parent / f"{video_path.stem}_narration.mp3"
            audio_path = narrator.generate_speech(script, temp_audio)

            # === CHECK DURATION COMPATIBILITY ===
            narration_audio = AudioFileClip(str(audio_path))
            video_duration = clip.duration
            narration_duration = narration_audio.duration
            narration_audio.close()

            duration_diff = abs(video_duration - narration_duration)

            # If narration is significantly shorter, adjust video to match
            if narration_duration < video_duration * 0.6:  # Less than 60% of video
                self.logger.info(f"Narration too short ({narration_duration:.1f}s vs {video_duration:.1f}s)")
                print(f"\n[Warning] 나레이션이 동영상보다 훨씬 짧습니다")
                print(f"   동영상: {video_duration:.1f}초")
                print(f"   나레이션: {narration_duration:.1f}초")
                print(f"   [Info] 동영상을 나레이션 길이에 맞춰 자릅니다")

                # Slow down video to match narration better
                target_video_duration = narration_duration * 1.1  # 10% buffer
                if target_video_duration < video_duration:
                    clip = clip.subclip(0, min(target_video_duration, video_duration))
                    print(f"   [OK] 동영상 길이 조정: {video_duration:.1f}초 → {clip.duration:.1f}초")

            # Add narration to video (with auto speed adjustment)
            clip = narrator.add_narration_to_video(clip, audio_path, mix_ratio=0.2)

            # Cleanup (with retry for Windows file locking)
            import time
            for attempt in range(3):
                try:
                    if audio_path.exists():
                        time.sleep(0.2)  # Wait a bit for file to be released
                        audio_path.unlink()
                        self.logger.debug(f"Cleaned up temp audio: {audio_path}")
                    break
                except PermissionError:
                    if attempt < 2:
                        time.sleep(0.5)
                    else:
                        self.logger.warning(f"Could not delete temp audio (will be cleaned up later): {audio_path}")

            return clip

        except Exception as e:
            self.logger.error(f"Failed to add narration: {e}")
            print(f"[Warning] Narration generation failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return clip

    def create_shorts_batch(
        self,
        video_path: Path,
        analysis: Dict[str, Any],
        num_shorts: int,
        output_dir: Path
    ) -> List[Path]:
        """
        Create multiple shorts from one long video.

        Args:
            video_path: Path to input video
            analysis: Analysis results
            num_shorts: Number of shorts to create
            output_dir: Output directory

        Returns:
            List of paths to created shorts
        """
        self.logger.info(f"Creating {num_shorts} shorts from {video_path.name}")

        from .analyzer import VideoAnalyzer
        analyzer = VideoAnalyzer(self.config)

        # Score scenes
        scored_scenes = analyzer.score_scenes(analysis["scenes"], video_path)

        # Take top N scenes
        top_scenes = scored_scenes[:num_shorts]

        output_paths = []
        clip = VideoFileClip(str(video_path))

        for i, scene in enumerate(top_scenes, 1):
            self.logger.info(f"Creating short {i}/{num_shorts}")

            # Extract scene
            scene_clip = clip.subclip(scene["start"], scene["end"])

            # Convert to shorts format
            if self.config["editing"]["auto_crop"]:
                scene_clip = self._convert_to_shorts_format(scene_clip)

            # Adjust duration
            scene_clip = self._adjust_duration(scene_clip)

            # Save
            output_path = output_dir / f"{video_path.stem}_short_{i:02d}.mp4"

            print(f"\n[Export] Exporting short {i}/{num_shorts}...")
            print(f"   Duration: {scene_clip.duration:.1f}s\n")

            scene_clip.write_videofile(
                str(output_path),
                codec=self.config["output"]["codec"],
                audio_codec=self.config["output"]["audio_codec"],
                bitrate=self.config["output"]["bitrate"],
                fps=self.config["video"]["fps"],
                logger='bar'
            )

            scene_clip.close()
            output_paths.append(output_path)

        clip.close()

        return output_paths
