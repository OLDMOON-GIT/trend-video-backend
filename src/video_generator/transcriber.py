"""Audio transcription and subtitle generation."""

import logging
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip


class Transcriber:
    """Transcribe audio and add subtitles."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("AutoShortsEditor.Transcriber")
        self._tokenizer_initialized = False
        self._morph_tokenizer = None
        self._face_detector = None
        self._face_detector_initialized = False


    def _ensure_tokenizer(self) -> None:
        if getattr(self, "_tokenizer_initialized", False):
            return
        self._tokenizer_initialized = True
        self._morph_tokenizer = None

        preferred = self.config.get("ai", {}).get("subtitle_style", {}).get("preferred_tokenizer")
        candidates: List[str] = []
        if isinstance(preferred, str):
            candidates.append(preferred)
        elif isinstance(preferred, (list, tuple)):
            candidates.extend(str(name) for name in preferred)

        candidates.append("kiwipiepy")

        tried = set()
        for name in candidates:
            name_lower = str(name).lower()
            if name_lower in tried:
                continue
            tried.add(name_lower)

            try:
                if name_lower == "kiwipiepy":
                    from kiwipiepy import Kiwi  # type: ignore
                    self._morph_tokenizer = Kiwi()
                    self.logger.info("Using Kiwi tokenizer for subtitle wrapping")
                    return
                if name_lower in {"mecab", "mecab-ko"}:
                    from konlpy.tag import Mecab  # type: ignore
                    self._morph_tokenizer = Mecab()
                    self.logger.info("Using Mecab tokenizer for subtitle wrapping")
                    return
            except Exception as exc:
                self.logger.debug("Tokenizer '%s' unavailable: %s", name_lower, exc)

        self.logger.debug("Falling back to regex-based subtitle tokenizer")


    def _tokenize_for_wrapping(self, text: str) -> List[str]:
        text = re.sub(r'\s+', ' ', (text or "")).strip()
        if not text:
            return []

        self._ensure_tokenizer()

        if self._morph_tokenizer:
            tokens: List[str] = []
            prev_end = 0
            try:
                for token in self._morph_tokenizer.tokenize(text):
                    if token.start > prev_end:
                        tokens.append(text[prev_end:token.start])
                    tokens.append(text[token.start:token.end])
                    prev_end = token.end
            except Exception as exc:
                self.logger.warning("Morphological tokenization failed, fallback to regex: %s", exc)
                self._morph_tokenizer = None
                return self._tokenize_for_wrapping(text)

            if prev_end < len(text):
                tokens.append(text[prev_end:])
            return tokens

        pattern = re.compile(r'(\s|[…,\.\?!\-~:;]+|[^\s…,\.\?!\-~:;]+)')
        return [tok for tok in pattern.findall(text) if tok]


    def _measure_text_width(self, draw, font, text: str) -> int:
        if not text:
            return 0
        bbox = draw.textbbox((0, 0), text, font=font)
        return max(0, bbox[2] - bbox[0])


    def _split_token_by_width(self, token: str, draw, font, max_width: int) -> List[str]:
        if not token:
            return []

        parts: List[str] = []
        buffer = ""

        for ch in token:
            candidate = buffer + ch
            width = self._measure_text_width(draw, font, candidate)

            if buffer and width > max_width:
                parts.append(buffer)
                buffer = ch
                if self._measure_text_width(draw, font, buffer) > max_width:
                    parts.append(ch)
                    buffer = ""
            elif not buffer and width > max_width:
                parts.append(ch)
                buffer = ""
            else:
                buffer = candidate

        if buffer:
            parts.append(buffer)

        return [part for part in parts if part]


    def _fit_text_to_width(self, text: str, draw, font, max_width: int, style: Dict[str, Any]) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        ellipsis = style.get("overflow_suffix", "…")
        if self._measure_text_width(draw, font, text) <= max_width:
            return text

        base = text if (not ellipsis or text.endswith(ellipsis)) else f"{text}{ellipsis}"

        while base:
            if self._measure_text_width(draw, font, base) <= max_width:
                return base
            base = base[:-1].rstrip()
            candidate = (f"{base}{ellipsis}".strip() if ellipsis else base)
            if candidate and self._measure_text_width(draw, font, candidate) <= max_width:
                return candidate

        return ellipsis.strip() if ellipsis else ""


    def _coerce_int(self, value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _clamp_float(self, value: Any, minimum: float, maximum: float, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = fallback
        return max(minimum, min(maximum, number))

    def _select_font(self, style: Dict[str, Any], font_size: int):
        from PIL import ImageFont

        font_candidates = []
        custom_font_path = style.get("font_path")
        if custom_font_path:
            font_candidates.append(custom_font_path)

        font_candidates.extend([
            "C:/Windows/Fonts/NanumGothic.ttf",
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/malgunbd.ttf",
            "C:/Windows/Fonts/gulim.ttc",
            "C:/Windows/Fonts/batang.ttc",
            "C:/Windows/Fonts/arial.ttf",
        ])

        for font_path in font_candidates:
            try:
                font = ImageFont.truetype(font_path, font_size)
                return font, font_path
            except Exception:
                continue

        return ImageFont.load_default(), "default"

    def _load_face_detector(self, style: Dict[str, Any]) -> None:
        if getattr(self, "_face_detector_initialized", False):
            return

        self._face_detector_initialized = True

        try:
            import cv2

            cascade_path = style.get("face_cascade_path")
            if cascade_path:
                cascade = cv2.CascadeClassifier(str(cascade_path))
            else:
                cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))

            if cascade.empty():
                raise ValueError("Failed to load cascade classifier")

            self._face_detector = cascade

        except Exception as exc:
            self._face_detector = None
            self.logger.debug("Face detector unavailable: %s", exc)

    def _detect_faces(self, frame, style: Dict[str, Any]):
        self._load_face_detector(style)
        if self._face_detector is None:
            return []

        try:
            import cv2

            gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            scale = self._clamp_float(style.get("face_scale_factor", 1.1), 1.05, 1.5, 1.1)
            neighbors = self._coerce_int(style.get("face_min_neighbors", 5), 5)
            min_size = self._coerce_int(style.get("face_min_size", 48), 48)

            faces = self._face_detector.detectMultiScale(
                gray,
                scaleFactor=scale,
                minNeighbors=neighbors,
                minSize=(min_size, min_size)
            )
            return faces

        except Exception as exc:
            self.logger.debug("Face detection failed: %s", exc)
            return []

    def _determine_subtitle_position(self, clip: VideoFileClip, segment: Dict[str, Any], style: Dict[str, Any], default_margin: int) -> Dict[str, Any]:
        position = str(style.get("position", "bottom")).lower()
        margin = max(0, self._coerce_int(style.get("margin", default_margin), default_margin))

        info: Dict[str, Any] = {
            "position": position,
            "margin": margin
        }

        if not style.get("smart_positioning", True):
            return info

        try:
            duration = getattr(clip, "duration", 0) or 0
            midpoint = segment["start"] + (segment["end"] - segment["start"]) * 0.5
            midpoint = max(0.0, min(midpoint, max(0.0, duration - 0.05)))
            frame = clip.get_frame(midpoint)
        except Exception as exc:
            self.logger.debug("Frame sampling for subtitle position failed: %s", exc)
            return info

        info["frame"] = frame

        faces = self._detect_faces(frame, style)
        if not faces:
            return info

        height, width = frame.shape[:2]
        top_ratio = self._clamp_float(style.get("position_zone_split_top", 0.35), 0.2, 0.5, 0.35)
        mid_ratio = self._clamp_float(style.get("position_zone_split_mid", 0.65), top_ratio + 0.05, 0.9, 0.65)

        top_border = int(height * top_ratio)
        mid_border = int(height * mid_ratio)

        zone_scores = {"top": 1.0, "middle": 1.0, "bottom": 1.0}

        for (x, y, w, h) in faces:
            area = float(w * h)
            cy = y + h / 2.0
            if cy < top_border:
                zone_scores["top"] += area
            elif cy < mid_border:
                zone_scores["middle"] += area
            else:
                zone_scores["bottom"] += area

        info["zone_scores"] = zone_scores

        zone_map = {"top": "top", "bottom": "bottom", "center": "middle", "middle": "middle"}
        priorities = style.get("position_priority", ["bottom", "top", "center"])
        current_zone = zone_map.get(position, "bottom")
        current_score = zone_scores.get(current_zone, float("inf"))

        for candidate in priorities:
            zone_key = zone_map.get(candidate, "bottom")
            score = zone_scores.get(zone_key, float("inf"))
            if score < current_score - 1:
                current_score = score
                position = candidate

        info["position"] = position

        total_area = sum(zone_scores.values())
        selected_zone = zone_map.get(position, "bottom")
        if total_area > 0:
            overlap_ratio = zone_scores.get(selected_zone, 0.0) / total_area
            threshold = self._clamp_float(style.get("face_overlap_threshold", 0.38), 0.1, 0.9, 0.38)
            if overlap_ratio > threshold:
                margin_extra = self._coerce_int(style.get("face_margin_extra", 60), 60)
                info["margin"] = margin + margin_extra

        return info

    def _estimate_region_brightness(self, frame, position: str, clip_width: int, clip_height: int, subtitle_height: int, margin: int) -> float:
        import numpy as np

        frame_height, frame_width = frame.shape[:2]
        if frame_height == 0 or frame_width == 0:
            return 0.0

        scale_y = frame_height / max(1, clip_height)
        scaled_margin = int(margin * scale_y)
        scaled_height = int(subtitle_height * scale_y)

        if position == "top":
            y_start = max(0, scaled_margin)
            y_end = min(frame_height, y_start + scaled_height)
        elif position == "center":
            y_start = max(0, frame_height // 2 - scaled_height // 2)
            y_end = min(frame_height, y_start + scaled_height)
        else:
            y_end = max(0, frame_height - scaled_margin)
            y_start = max(0, y_end - scaled_height)

        region = frame[y_start:y_end, :]
        if region.size == 0:
            region = frame

        luminance = 0.2126 * region[..., 0] + 0.7152 * region[..., 1] + 0.0722 * region[..., 2]
        return float(luminance.mean())

    def _compute_line_cost(self, width: int, max_width: int, text: str, style: Dict[str, Any], is_last: bool = False) -> float:
        if max_width <= 0:
            return 0.0

        target_ratio = self._clamp_float(style.get("ideal_width_ratio", 0.82), 0.3, 1.0, 0.82)
        target_width = max_width * target_ratio
        deviation = abs(width - target_width) / max(1.0, max_width)
        cost = deviation * deviation

        short_threshold = self._coerce_int(style.get("short_line_length", 4), 4)
        if len(text) <= short_threshold:
            cost += float(style.get("short_line_penalty", 0.6))

        if not is_last:
            if re.search(r'[.,!?…]$', text):
                cost *= float(style.get("punctuation_bonus", 0.72))
            else:
                cost += float(style.get("no_punct_penalty", 0.3))

        balance_penalty = float(style.get("balance_penalty", 0.12))
        cost += balance_penalty / max(1, len(text))

        return cost

    def _fallback_wrap_text(self, text: str, font, draw, max_width: int, style: Dict[str, Any]) -> List[str]:
        tokens = re.findall(r'\S+\s*', text)
        if not tokens:
            return [text.strip()]

        lines: List[str] = []
        max_lines = max(1, self._coerce_int(style.get("max_lines", 3), 3))
        current = ""

        for token in tokens:
            candidate = (current + token).strip() if current else token.strip()
            width = self._measure_text_width(draw, font, candidate)

            if not current:
                current = candidate
                continue

            if width <= max_width or len(lines) + 1 >= max_lines:
                current = candidate
            else:
                lines.append(current.strip())
                current = token.strip()
                if len(lines) + 1 >= max_lines:
                    break

        if current and len(lines) < max_lines:
            lines.append(current.strip())

        return [line for line in lines if line]
    def _wrap_subtitle_text(self, text: str, font, draw, max_width: int, style: Dict[str, Any]) -> List[str]:
        normalized = re.sub(r'\s+', ' ', (text or '')).strip()
        if not normalized:
            return []

        max_lines = max(1, self._coerce_int(style.get("max_lines", 3), 3))
        if max_lines == 1:
            width = self._measure_text_width(draw, font, normalized)
            if width <= max_width:
                return [normalized]
            fallback = self._fallback_wrap_text(normalized, font, draw, max_width, style)
            return fallback[:1] if fallback else [normalized]

        chars = list(normalized)
        n = len(chars)
        punctuation = style.get("preferred_breaks", ".,!?…·;:-–—~")
        break_points = set()

        for idx, ch in enumerate(chars, start=1):
            if ch == ' ' or ch in punctuation:
                break_points.add(idx)

        force_every = style.get("force_break_interval", 8)
        try:
            step = max(1, int(force_every))
        except (TypeError, ValueError):
            step = 8

        for idx in range(step, n, step):
            break_points.add(idx)

        break_points.add(n)
        ordered = sorted(pt for pt in break_points if 0 < pt <= n)
        if not ordered or ordered[-1] != n:
            ordered.append(n)

        positions = [0] + ordered
        m = len(positions)
        INF = float('inf')

        dp = [[INF] * (max_lines + 1) for _ in range(m)]
        nxt_idx = [[-1] * (max_lines + 1) for _ in range(m)]
        dp[m - 1][0] = 0.0

        for idx in range(m - 2, -1, -1):
            for lines_left in range(1, max_lines + 1):
                for nxt in range(idx + 1, m):
                    segment = ''.join(chars[positions[idx]:positions[nxt]]).strip()
                    if not segment:
                        continue

                    width = self._measure_text_width(draw, font, segment)
                    if width > max_width:
                        continue

                    tail_cost = dp[nxt][lines_left - 1]
                    if tail_cost == INF:
                        continue

                    line_cost = self._compute_line_cost(width, max_width, segment, style, is_last=(nxt == m - 1))
                    total = line_cost + tail_cost

                    if total < dp[idx][lines_left]:
                        dp[idx][lines_left] = total
                        nxt_idx[idx][lines_left] = nxt

        best_lines = None
        best_cost = INF

        for lines_used in range(1, max_lines + 1):
            cost = dp[0][lines_used]
            if cost < best_cost and nxt_idx[0][lines_used] != -1:
                best_cost = cost
                best_lines = lines_used

        if best_lines is None:
            return self._fallback_wrap_text(normalized, font, draw, max_width, style)

        lines: List[str] = []
        idx = 0
        lines_left = best_lines

        while lines_left > 0 and idx < m:
            nxt = nxt_idx[idx][lines_left]
            if nxt == -1:
                break
            segment = ''.join(chars[positions[idx]:positions[nxt]]).strip()
            lines.append(segment)
            idx = nxt
            lines_left -= 1

        if not lines:
            return self._fallback_wrap_text(normalized, font, draw, max_width, style)

        return lines


    def transcribe_video(self, video_path: Path) -> List[Dict[str, Any]]:
        """
        Transcribe video audio using Whisper.

        Args:
            video_path: Path to video file

        Returns:
            List of transcription segments with timestamps
        """
        temp_audio = None
        try:
            import whisper
            import numpy as np
            import wave

            self.logger.info(f"Transcribing audio from {video_path.name}")
            print(f"\n[Transcribe] Transcribing audio with Whisper...")

            # Extract audio to temp WAV file
            print(f"   Extracting audio to temp file...")
            clip = VideoFileClip(str(video_path))

            if not clip.audio:
                self.logger.warning("Video has no audio track")
                print(f"[Error] Video has no audio")
                clip.close()
                return []

            # Save audio as WAV (MoviePy can do this reliably)
            temp_audio = video_path.parent / f"{video_path.stem}_temp_audio.wav"
            clip.audio.write_audiofile(
                str(temp_audio),
                fps=16000,
                nbytes=2,
                codec='pcm_s16le',
                verbose=False,
                logger=None
            )
            clip.close()

            # Load WAV file as numpy array using wave module
            print(f"   Loading audio data...")
            with wave.open(str(temp_audio), 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                n_frames = wav_file.getnframes()
                audio_data = wav_file.readframes(n_frames)

                # Convert bytes to numpy array
                audio_array = np.frombuffer(audio_data, dtype=np.int16)

                # Convert to float32 and normalize to [-1, 1]
                audio_array = audio_array.astype(np.float32) / 32768.0

                # If stereo, convert to mono
                if wav_file.getnchannels() == 2:
                    audio_array = audio_array.reshape(-1, 2).mean(axis=1)

            self.logger.info(f"Audio loaded: {len(audio_array)} samples at {sample_rate}Hz")

            # Load Whisper model
            model_size = os.getenv("WHISPER_MODEL", "base")
            print(f"   Loading Whisper model: {model_size}")
            model = whisper.load_model(model_size)

            # Transcribe numpy array
            print(f"   Transcribing...")
            result = model.transcribe(
                audio_array,
                language="ko",
                verbose=False
            )

            segments = []
            for segment in result["segments"]:
                segments.append({
                    "start": segment["start"],
                    "end": segment["end"],
                    "text": segment["text"].strip()
                })

            print(f"[OK] Transcribed {len(segments)} segments")

            # Print actual content for debugging
            if segments:
                all_text = " ".join([seg["text"] for seg in segments])
                print(f"   인식된 내용: '{all_text[:150]}'")
                self.logger.info(f"Transcription complete: {len(segments)} segments - Content: {all_text[:200]}")
            else:
                self.logger.info(f"Transcription complete: {len(segments)} segments - No content")

            return segments

        except Exception as e:
            self.logger.error(f"Transcription failed: {e}")
            print(f"[Error] Transcription failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

        finally:
            # Cleanup temp file
            if temp_audio and temp_audio.exists():
                try:
                    temp_audio.unlink()
                    self.logger.debug(f"Cleaned up temp audio: {temp_audio}")
                except Exception as e:
                    self.logger.warning(f"Could not delete temp audio: {e}")

    def add_subtitles(
        self,
        clip: VideoFileClip,
        segments: List[Dict[str, Any]]
    ) -> VideoFileClip:
        """
        Add subtitles to video with smart positioning and adaptive styling.

        Args:
            clip: Video clip
            segments: Transcription segments

        Returns:
            Video clip with subtitles
        """
        if not segments:
            return clip

        print(f"\n Adding subtitles ({len(segments)} segments)...")

        base_style = self.config.get("ai", {}).get("subtitle_style", {})

        subtitle_clips = []

        for i, segment in enumerate(segments):
            try:
                text = segment.get("text", "").strip()
                if not text:
                    continue

                from PIL import Image, ImageDraw
                import numpy as np

                segment_style = dict(base_style)

                font_size = self._coerce_int(segment_style.get("font_size", 48), 48)
                stroke_width = self._coerce_int(segment_style.get("stroke_width", 3), 3)
                width_ratio = self._clamp_float(segment_style.get("width_ratio", 0.85), 0.3, 1.0, 0.85)
                img_width = max(100, int(clip.w * width_ratio))

                font, font_path = self._select_font(segment_style, font_size)
                if segment_style.get("debug_font", False):
                    print(f"   [Font] Using: {font_path}")

                temp_img = Image.new("RGBA", (img_width, max(512, font_size * 8)), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)

                max_text_width = None
                if segment_style.get("max_width_ratio") is not None:
                    ratio_val = self._clamp_float(segment_style.get("max_width_ratio", 0.92), 0.1, 1.0, 0.92)
                    max_text_width = max(40, int(img_width * ratio_val))

                horizontal_padding = max(0, self._coerce_int(segment_style.get("horizontal_padding", 40), 40))
                if max_text_width is None:
                    effective_padding = min(horizontal_padding, max(0, img_width - 40))
                    max_text_width = max(40, img_width - effective_padding)
                else:
                    effective_padding = min(horizontal_padding, max(0, img_width - max_text_width))

                lines = self._wrap_subtitle_text(text, font, temp_draw, max_text_width, segment_style)
                if not lines:
                    continue

                line_gap = max(0, self._coerce_int(segment_style.get("line_gap", 10), 10))
                padding_y = max(0, self._coerce_int(segment_style.get("vertical_padding", 40), 40))
                padding_top = padding_y // 2
                padding_bottom = padding_y - padding_top
                line_height = font_size + line_gap
                line_count = max(1, len(lines))
                text_height = line_count * line_height
                total_height = text_height + padding_top + padding_bottom

                position_info = self._determine_subtitle_position(
                    clip,
                    segment,
                    segment_style,
                    default_margin=self._coerce_int(segment_style.get("margin", 80), 80)
                )
                position = position_info["position"]
                margin = position_info["margin"]
                frame_for_analysis = position_info.get("frame")

                extra_padding = max(0, self._coerce_int(segment_style.get("background_extra_padding", 24), 24))
                background_height = total_height + extra_padding

                region_brightness = None
                if frame_for_analysis is not None and segment_style.get("adaptive_background", True):
                    region_brightness = self._estimate_region_brightness(
                        frame_for_analysis,
                        position,
                        clip.w,
                        clip.h,
                        background_height,
                        margin
                    )

                text_color = segment_style.get("color", "white")
                stroke_color_val = segment_style.get("stroke_color", "black")
                if region_brightness is not None and segment_style.get("adaptive_text_color", True):
                    bright_threshold = float(segment_style.get("bright_threshold", 190))
                    dark_threshold = float(segment_style.get("dark_threshold", 60))
                    if region_brightness > bright_threshold:
                        text_color = segment_style.get("bright_text_color", "black")
                        stroke_color_val = segment_style.get("bright_stroke_color", stroke_color_val)
                    elif region_brightness < dark_threshold:
                        text_color = segment_style.get("dark_text_color", text_color)
                        stroke_color_val = segment_style.get("dark_stroke_color", stroke_color_val)

                img = Image.new("RGBA", (img_width, total_height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                y = padding_top
                for line in lines:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_width = bbox[2] - bbox[0]
                    x = max((img_width - text_width) // 2, effective_padding // 2)

                    for adj_x in range(-stroke_width, stroke_width + 1):
                        for adj_y in range(-stroke_width, stroke_width + 1):
                            if adj_x == 0 and adj_y == 0:
                                continue
                            draw.text((x + adj_x, y + adj_y), line, font=font, fill=stroke_color_val)

                    draw.text((x, y), line, font=font, fill=text_color)
                    y += line_height

                from moviepy.editor import ImageClip

                img_array = np.array(img)
                txt_clip = ImageClip(img_array).set_duration(segment["end"] - segment["start"])

                subtitle_clip = txt_clip
                if segment_style.get("background", True):
                    from moviepy.editor import ColorClip

                    bg_color = segment_style.get("background_color", [0, 0, 0])
                    bg_opacity = float(segment_style.get("background_opacity", 0.7))
                    if region_brightness is not None:
                        bright_threshold = float(segment_style.get("bright_threshold", 190))
                        dark_threshold = float(segment_style.get("dark_threshold", 60))
                        if region_brightness > bright_threshold:
                            bg_opacity = min(1.0, bg_opacity + 0.25)
                        elif region_brightness < dark_threshold:
                            bg_opacity = max(0.35, bg_opacity - 0.2)

                    bg_clip = ColorClip(size=(img_width, background_height), color=bg_color)
                    bg_clip = bg_clip.set_opacity(bg_opacity).set_duration(segment["end"] - segment["start"])
                    txt_clip = txt_clip.set_position(("center", (background_height - total_height) // 2))
                    subtitle_clip = CompositeVideoClip([bg_clip, txt_clip], size=(img_width, background_height))

                subtitle_clip = subtitle_clip.set_start(segment["start"]).set_duration(segment["end"] - segment["start"])

                if position == "top":
                    y_pos = max(0, margin)
                elif position == "center":
                    y_pos = max(0, min((clip.h - subtitle_clip.h) // 2, clip.h - subtitle_clip.h))
                else:
                    y_pos = max(0, clip.h - subtitle_clip.h - margin)

                subtitle_clip = subtitle_clip.set_position(("center", y_pos))
                subtitle_clips.append(subtitle_clip)

            except Exception as e:
                self.logger.warning(f"Failed to create subtitle {i}: {e}")
                import traceback
                self.logger.warning(traceback.format_exc())
                continue

        if subtitle_clips:
            video = CompositeVideoClip([clip] + subtitle_clips)
            print(f"[OK] Subtitles added")
            return video

        return clip

        print(f"\n Adding subtitles ({len(segments)} segments)...")

        style = self.config["ai"]["subtitle_style"]

        subtitle_clips = []

        for i, segment in enumerate(segments):
            # Create text clip
            try:
                # Text content
                text = segment["text"]

                # Use PIL/Pillow to create text image (no ImageMagick needed)
                from PIL import Image, ImageDraw, ImageFont
                import numpy as np

                # Get style settings
                font_size = style.get("font_size", 48)
                text_color = style.get("color", "white")
                stroke_color_val = style.get("stroke_color", "black")
                stroke_width = style.get("stroke_width", 3)

                # Create image with text
                width_ratio = style.get("width_ratio", 0.85)
                try:
                    width_ratio = float(width_ratio)
                except (TypeError, ValueError):
                    width_ratio = 0.85
                width_ratio = max(0.3, min(width_ratio, 1.0))
                img_width = max(100, int(clip.w * width_ratio))

                # Try to load font, prioritize Korean fonts
                try:
                    # Check if custom font path is specified in config
                    custom_font_path = style.get("font_path")

                    # Korean-compatible fonts in order of preference
                    korean_fonts = []

                    # Add custom font path first if specified
                    if custom_font_path:
                        korean_fonts.append(custom_font_path)

                    # Add default Korean fonts as fallback
                    korean_fonts.extend([
                        "C:/Windows/Fonts/NanumGothic.ttf", # 나눔고딕
                        "C:/Windows/Fonts/malgun.ttf",      # 맑은 고딕 (Windows Vista+)
                        "C:/Windows/Fonts/malgunbd.ttf",    # 맑은 고딕 Bold
                        "C:/Windows/Fonts/gulim.ttc",       # 굴림
                        "C:/Windows/Fonts/batang.ttc",      # 바탕
                        "C:/Windows/Fonts/arial.ttf",       # Fallback
                    ])

                    font = None
                    for font_path in korean_fonts:
                        try:
                            font = ImageFont.truetype(font_path, font_size)
                            print(f"   [Font] Using: {font_path}")
                            break
                        except:
                            continue

                    if font is None:
                        # Last resort: try system default
                        raise Exception("No suitable font found")

                except Exception as e:
                    self.logger.error(f"Could not load Korean font: {e}")
                    print(f"   [Warning] Could not load Korean font, text may not display correctly")
                    font = ImageFont.load_default()

                # Calculate text size
                temp_img = Image.new('RGBA', (img_width, 500), (0, 0, 0, 0))
                temp_draw = ImageDraw.Draw(temp_img)

                # Word wrap text using tokenizer-aware layout (better Korean handling)
                max_width_ratio = style.get("max_width_ratio")
                max_text_width = None
                if max_width_ratio is not None:
                    try:
                        ratio_val = float(max_width_ratio)
                        ratio_val = max(0.1, min(ratio_val, 1.0))
                        max_text_width = max(40, int(img_width * ratio_val))
                    except (TypeError, ValueError):
                        max_text_width = None

                horizontal_padding = style.get("horizontal_padding", 40)
                try:
                    horizontal_padding = int(horizontal_padding)
                except (TypeError, ValueError):
                    horizontal_padding = 40
                horizontal_padding = max(0, horizontal_padding)

                if max_text_width is None:
                    effective_padding = min(horizontal_padding, max(0, img_width - 40))
                    max_text_width = max(40, img_width - effective_padding)
                else:
                    effective_padding = min(horizontal_padding, max(0, img_width - max_text_width))
                lines = self._wrap_subtitle_text(
                    text=text,
                    font=font,
                    draw=temp_draw,
                    max_width=max_text_width,
                    style=style
                )

                # Calculate text metrics
                line_gap_value = style.get("line_gap", 10)
                try:
                    line_gap = int(line_gap_value)
                except (TypeError, ValueError):
                    line_gap = 10
                line_gap = max(0, line_gap)

                padding_y_value = style.get("vertical_padding", 40)
                try:
                    padding_y = int(padding_y_value)
                except (TypeError, ValueError):
                    padding_y = 40
                padding_y = max(0, padding_y)
                padding_top = max(0, padding_y // 2)
                padding_bottom = max(0, padding_y - padding_top)
                line_height = font_size + line_gap
                line_count = max(1, len(lines))
                text_height = line_count * line_height
                total_height = text_height + padding_top + padding_bottom

                # Create image
                img = Image.new('RGBA', (img_width, total_height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                # Draw text with stroke
                y = padding_top
                for line in lines:
                    bbox = draw.textbbox((0, 0), line, font=font)
                    text_width = bbox[2] - bbox[0]
                    x = max((img_width - text_width) // 2, effective_padding // 2)

                    # Draw stroke
                    for adj_x in range(-stroke_width, stroke_width+1):
                        for adj_y in range(-stroke_width, stroke_width+1):
                            draw.text((x+adj_x, y+adj_y), line, font=font, fill=stroke_color_val)

                    # Draw main text
                    draw.text((x, y), line, font=font, fill=text_color)
                    y += line_height

                # Convert PIL image to MoviePy clip
                img_array = np.array(img)
                from moviepy.editor import ImageClip
                txt_clip = ImageClip(img_array).set_duration(segment["end"] - segment["start"])

                # Add semi-transparent background if enabled
                if style.get("background", True):
                    from moviepy.editor import ColorClip

                    # Create background box (slightly larger than text)
                    bg_width = img_width
                    extra_padding_value = style.get("background_extra_padding", 20)
                    try:
                        extra_padding = int(extra_padding_value)
                    except (TypeError, ValueError):
                        extra_padding = 20
                    extra_padding = max(0, extra_padding)
                    bg_height = total_height + extra_padding
                    bg_color = style.get("background_color", [0, 0, 0])
                    bg_opacity = style.get("background_opacity", 0.6)

                    bg_clip = ColorClip(
                        size=(bg_width, bg_height),
                        color=bg_color
                    ).set_opacity(bg_opacity).set_duration(segment["end"] - segment["start"])

                    # Center text on background
                    txt_clip = txt_clip.set_position(("center", "center"))

                    # Composite text on background
                    subtitle_clip = CompositeVideoClip([bg_clip, txt_clip], size=(bg_width, bg_height))
                else:
                    subtitle_clip = txt_clip

                # Position subtitle
                position = style.get("position", "bottom")
                margin = style.get("margin", 80)

                if position == "bottom":
                    subtitle_clip = subtitle_clip.set_position(("center", clip.h - subtitle_clip.h - margin))
                elif position == "top":
                    subtitle_clip = subtitle_clip.set_position(("center", margin))
                else:  # center
                    subtitle_clip = subtitle_clip.set_position("center")

                # Set timing
                subtitle_clip = subtitle_clip.set_start(segment["start"]).set_duration(
                    segment["end"] - segment["start"]
                )

                subtitle_clips.append(subtitle_clip)

            except Exception as e:
                self.logger.warning(f"Failed to create subtitle {i}: {e}")
                import traceback
                self.logger.warning(traceback.format_exc())
                continue

        if subtitle_clips:
            # Composite video with subtitles
            video = CompositeVideoClip([clip] + subtitle_clips)
            print(f"[OK] Subtitles added")
            return video

        return clip

    def create_srt_file(
        self,
        segments: List[Dict[str, Any]],
        output_path: Path
    ) -> Path:
        """
        Create SRT subtitle file.

        Args:
            segments: Transcription segments
            output_path: Output SRT file path

        Returns:
            Path to SRT file
        """
        srt_path = output_path.with_suffix('.srt')

        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, segment in enumerate(segments, 1):
                # Convert seconds to SRT time format
                start_time = self._seconds_to_srt_time(segment["start"])
                end_time = self._seconds_to_srt_time(segment["end"])

                f.write(f"{i}\n")
                f.write(f"{start_time} --> {end_time}\n")
                f.write(f"{segment['text']}\n")
                f.write("\n")

        self.logger.info(f"SRT file created: {srt_path}")
        return srt_path

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Convert seconds to SRT time format (HH:MM:SS,mmm)."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
