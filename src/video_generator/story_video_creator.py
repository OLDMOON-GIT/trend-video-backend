"""Create narrated videos from text prompts with AI-generated images."""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from openai import OpenAI
from moviepy.editor import ImageClip, AudioFileClip, CompositeAudioClip
import requests
from PIL import Image
import io
from tqdm import tqdm


class StoryVideoCreator:
    """Create videos from text prompts with AI narration and images."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("AutoShortsEditor.StoryVideoCreator")
        self.client = None

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY required for story video creation")

        self.client = OpenAI(api_key=api_key)

    def _load_prompt_template(self, filename: str) -> str:
        """Load prompt template from file."""
        prompt_path = Path(__file__).parent.parent / "prompts" / filename

        if not prompt_path.exists():
            self.logger.warning(f"Prompt file not found: {prompt_path}, using default")
            return None

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            self.logger.error(f"Failed to load prompt template: {e}")
            return None

    def create_from_prompt(
        self,
        prompt: str,
        output_path: Path,
        duration: Optional[float] = None,
        aspect_ratio: str = "9:16",
        custom_image_prompt: Optional[str] = None
    ) -> Path:
        """
        Create a narrated video from a text prompt.

        Args:
            prompt: Story prompt or theme
            output_path: Output video path
            duration: Target duration in seconds (default: auto from narration)
            aspect_ratio: Video aspect ratio ("9:16", "16:9", "1:1")
            custom_image_prompt: Custom DALL-E prompt (overrides auto-generated)

        Returns:
            Path to created video
        """
        print(f"\n[Export] AI 스토리 비디오 생성 중...")
        print(f"   프롬프트: {prompt}")
        print(f"   화면비율: {aspect_ratio}\n")

        # Step 1: Generate story
        with tqdm(total=1, desc="📖 [1/4] 스토리 생성", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            story_script = self._generate_story(prompt, duration)
            pbar.update(1)

        print(f"\n생성된 스토리:")
        print(f"{'='*60}")
        print(story_script)
        print(f"{'='*60}\n")

        # Step 2: Generate opening scene image
        with tqdm(total=1, desc=" [2/4] 첫 장면 이미지 생성", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            image_path = self._generate_opening_image(
                prompt,
                story_script,
                aspect_ratio,
                custom_image_prompt
            )
            pbar.update(1)

        # Step 3: Generate narration audio
        with tqdm(total=1, desc="🎙 [3/4] 나레이션 생성", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            audio_path = self._generate_narration_audio(story_script)
            pbar.update(1)

        # Step 4: Create video from image + audio
        with tqdm(total=1, desc="[Export] [4/4] 비디오 생성", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            video_path = self._create_video(image_path, audio_path, output_path, aspect_ratio)
            pbar.update(1)

        # Cleanup temp files
        self._cleanup_temp_files(image_path, audio_path)

        print(f"\n 스토리 비디오 생성 완료!")
        print(f"   출력: {video_path}")

        return video_path

    def _generate_story(self, prompt: str, duration: Optional[float]) -> str:
        """
        Generate story script using GPT.

        Args:
            prompt: User's story prompt
            duration: Target duration (if specified)

        Returns:
            Story script for narration
        """
        # Calculate target length
        if duration:
            target_chars = int(duration * 2.8)  # ~2.8 chars/sec for Korean
        else:
            target_chars = 168  # ~60 seconds default

        # Load prompts from files
        system_template = self._load_prompt_template("short_story_system.txt")
        user_template = self._load_prompt_template("short_story_user.txt")

        # Use templates if available, otherwise fall back to defaults
        if system_template:
            system_prompt = system_template
        else:
            system_prompt = """당신은 창의적인 쇼츠 스토리 작가입니다.
짧고 강렬하며, 시청자의 관심을 사로잡는 한국어 스토리를 만듭니다.
영상으로 표현하기 좋은 시각적인 요소를 포함합니다."""

        if user_template:
            user_prompt = user_template.format(
                prompt=prompt,
                target_chars=target_chars
            )
        else:
            user_prompt = f"""주제: {prompt}

위 주제로 {target_chars}자 분량의 짧은 스토리 나레이션을 작성하세요.

 요구사항:
1. 순수 한국어만 사용
2. 자연스러운 구어체 (말하는 톤)
3. 시각적으로 상상 가능한 첫 장면 묘사 포함
4. 흥미진진하고 몰입감 있는 전개
5. 정확히 {target_chars}자 (±20자)
6. 완결된 짧은 이야기 또는 인상적인 한 장면

 구조:
- 시작: 강렬한 오프닝 (첫 장면 묘사)
- 중간: 흥미로운 전개 또는 관찰
- 끝: 인상적인 마무리 (여운 남기기)

 금지:
- 단순 설명이나 교훈
- "구독", "좋아요" 같은 CTA
- 지나치게 추상적인 내용

예시 스타일:
"깊은 밤, 달빛만이 비추는 숲 속. 한 소년이 빛나는 나비를 쫓고 있습니다. 나비는 점점 더 깊은 곳으로... 그리고 소년이 다다른 곳은 아무도 몰랐던 비밀의 정원이었습니다."

스토리만 출력:"""

        try:
            response = self.client.chat.completions.create(
                model=os.getenv("NARRATION_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.9,
                max_tokens=500
            )

            story = response.choices[0].message.content.strip()
            story = story.replace('"', '').replace("'", '').strip()

            print(f"[OK] 스토리 생성 완료 ({len(story)}자 / 목표 {target_chars}자)")
            self.logger.info(f"Generated story: {story[:200]}")

            return story

        except Exception as e:
            self.logger.error(f"Story generation failed: {e}")
            raise

    def _generate_opening_image(
        self,
        prompt: str,
        story: str,
        aspect_ratio: str,
        custom_prompt: Optional[str] = None
    ) -> Path:
        """
        Generate opening scene image using DALL-E.

        Args:
            prompt: Original user prompt
            story: Generated story text
            aspect_ratio: Video aspect ratio
            custom_prompt: Custom DALL-E prompt (optional)

        Returns:
            Path to generated image
        """
        # Map aspect ratio to DALL-E size
        size_map = {
            "9:16": "1024x1792",   # Vertical (shorts)
            "16:9": "1792x1024",   # Horizontal (landscape)
            "1:1": "1024x1024"     # Square
        }
        dalle_size = size_map.get(aspect_ratio, "1024x1792")

        # Orientation hint for prompt
        orientation_hints = {
            "9:16": "vertical composition suitable for mobile shorts",
            "16:9": "horizontal cinematic composition",
            "1:1": "centered square composition"
        }
        orientation = orientation_hints.get(aspect_ratio, "vertical composition")

        # Use custom prompt if provided, otherwise generate
        if custom_prompt:
            dalle_prompt = custom_prompt
        else:
            # Extract visual description from story (first 150 chars)
            visual_hint = story[:150]

            # Load prompt template
            image_template = self._load_prompt_template("image_dalle.txt")

            if image_template:
                dalle_prompt = image_template.format(
                    prompt=prompt,
                    visual_hint=visual_hint,
                    orientation=orientation
                )
            else:
                # Create DALL-E prompt (fallback)
                dalle_prompt = f"""Create a stunning, cinematic scene for a Korean short video.

Theme: {prompt}
Scene: {visual_hint}

Style Requirements:
- Cinematic lighting and dramatic atmosphere
- Rich, vibrant colors with depth
- High quality, detailed composition
- {orientation}
- Photorealistic style with artistic touches
- Professional cinematography look
- Korean aesthetic where relevant

Important: Create a visually striking opening scene that captures attention immediately."""

        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=dalle_prompt,
                size=dalle_size,
                quality="standard",
                n=1,
            )

            image_url = response.data[0].url

            # Download image
            img_response = requests.get(image_url)
            img = Image.open(io.BytesIO(img_response.content))

            # Save to temp file
            temp_image = Path("temp_story_image.png")
            img.save(temp_image)

            self.logger.info(f"Image generated: {temp_image} ({dalle_size})")

            return temp_image

        except Exception as e:
            self.logger.error(f"Image generation failed: {e}")
            raise

    def _generate_narration_audio(self, script: str) -> Path:
        """
        Generate narration audio using Edge TTS.

        Args:
            script: Story script

        Returns:
            Path to audio file
        """
        from .narrator import Narrator

        narrator = Narrator(self.config)

        temp_audio = Path("temp_story_audio.mp3")
        audio_path = narrator.generate_speech(script, temp_audio)

        self.logger.info(f"Audio generated: {audio_path}")

        return audio_path

    def _create_video(
        self,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        aspect_ratio: str
    ) -> Path:
        """
        Create video from image and audio.

        Args:
            image_path: Path to image
            audio_path: Path to audio
            output_path: Output video path
            aspect_ratio: Video aspect ratio

        Returns:
            Path to created video
        """
        try:
            # Load audio to get duration
            audio = AudioFileClip(str(audio_path))
            duration = audio.duration

            # Create image clip with audio duration
            image_clip = ImageClip(str(image_path), duration=duration)

            # Determine target resolution based on aspect ratio
            if aspect_ratio == "9:16":
                target_width = 1080
                target_height = 1920
            elif aspect_ratio == "16:9":
                target_width = 1920
                target_height = 1080
            elif aspect_ratio == "1:1":
                target_width = 1080
                target_height = 1080
            else:
                target_width = 1080
                target_height = 1920

            # Calculate crop/resize
            img_aspect = image_clip.w / image_clip.h
            target_aspect = target_width / target_height

            if img_aspect > target_aspect:
                # Image is wider - crop width
                new_height = image_clip.h
                new_width = int(new_height * target_aspect)
                x_center = image_clip.w / 2
                y_center = image_clip.h / 2

                from moviepy.video.fx.all import crop, resize
                image_clip = crop(
                    image_clip,
                    width=new_width,
                    height=new_height,
                    x_center=x_center,
                    y_center=y_center
                )
                image_clip = resize(image_clip, height=target_height)
            else:
                # Image is taller - crop height
                new_width = image_clip.w
                new_height = int(new_width / target_aspect)
                x_center = image_clip.w / 2
                y_center = image_clip.h / 2

                from moviepy.video.fx.all import crop, resize
                image_clip = crop(
                    image_clip,
                    width=new_width,
                    height=new_height,
                    x_center=x_center,
                    y_center=y_center
                )
                image_clip = resize(image_clip, width=target_width)

            # Set audio
            image_clip = image_clip.set_audio(audio)

            # Add fade in/out
            if duration > 2:
                image_clip = image_clip.fadein(0.5).fadeout(0.5)

            # Export
            output_path.parent.mkdir(parents=True, exist_ok=True)

            image_clip.write_videofile(
                str(output_path),
                fps=self.config["video"]["fps"],
                codec=self.config["output"]["codec"],
                audio_codec=self.config["output"]["audio_codec"],
                bitrate=self.config["output"]["bitrate"],
                preset='medium',
                logger='bar'
            )

            image_clip.close()
            audio.close()

            return output_path

        except Exception as e:
            self.logger.error(f"Video creation failed: {e}")
            raise

    def _cleanup_temp_files(self, image_path: Path, audio_path: Path):
        """Clean up temporary files."""
        import time

        for path in [image_path, audio_path]:
            if path and path.exists():
                for attempt in range(3):
                    try:
                        time.sleep(0.2)
                        path.unlink()
                        self.logger.debug(f"Cleaned up: {path}")
                        break
                    except PermissionError:
                        if attempt < 2:
                            time.sleep(0.5)
                        else:
                            self.logger.warning(f"Could not delete: {path}")
