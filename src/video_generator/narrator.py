"""AI narration generation."""

import logging
import os
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI
from moviepy.editor import VideoFileClip, CompositeAudioClip, AudioFileClip


class Narrator:
    """Generate AI narration for videos."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = logging.getLogger("AutoShortsEditor.Narrator")
        self.client = None

        # Initialize OpenAI client if API key exists
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
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

    def generate_narration_script(
        self,
        video_path: Path,
        transcription: str = None,
        use_gpt: bool = False
    ) -> str:
        """
        Generate Korean narration script (FREE or with GPT).

        주의: 영상 화면 분석을 메인으로, 오디오 인식은 참고만 사용합니다.
        (Whisper 오인식 문제로 인해 화면 분석을 우선합니다)

        Args:
            video_path: Path to video file
            transcription: Transcribed audio content from video
            use_gpt: Use GPT for script generation (costs money!)

        Returns:
            Korean narration script text
        """
        self.logger.info("Generating Korean narration script (Vision-first approach)")
        print(f"\n✍ 영상 내용 분석 및 나레이션 생성...")
        print(f"   📌 전략: 영상 화면 메인 + 음성 참고 (Whisper 오인식 방지)")

        # Get video info
        clip = VideoFileClip(str(video_path))
        duration = clip.duration
        clip.close()

        # === STEP 1: VISION ANALYSIS (PRIMARY) ===
        print(f"\n    [1단계] 영상 화면 분석 중 (메인 소스)...")
        vision_description = None
        try:
            vision_description = self._analyze_video_with_vision(video_path)
            if vision_description:
                print(f"   [OK] 영상 화면 분석 완료")
                print(f"   화면 내용: {vision_description[:150]}...")
                self.logger.info(f"Vision (primary): {vision_description[:200]}")
        except Exception as e:
            self.logger.error(f"Vision analysis failed: {e}")
            print(f"   ⚠ 영상 화면 분석 실패")

        # === STEP 2: AUDIO TRANSCRIPTION (REFERENCE ONLY) ===
        print(f"\n    [2단계] 음성 인식 중 (참고용)...")
        audio_transcription = None

        if not transcription:
            try:
                from .transcriber import Transcriber
                transcriber = Transcriber(self.config)
                segments = transcriber.transcribe_video(video_path)
                audio_transcription = " ".join([seg["text"] for seg in segments])

                if audio_transcription and audio_transcription.strip():
                    print(f"   [OK] 음성 인식 완료 (참고용)")
                    print(f"   인식 내용: '{audio_transcription[:100]}...'")
                    self.logger.info(f"Audio (reference): {audio_transcription[:200]}")

                    # Filter out CTA phrases from audio
                    cliche_phrases = ["구독", "좋아요", "알림", "눌러주세요", "부탁", "채널"]
                    if any(phrase in audio_transcription for phrase in cliche_phrases):
                        print(f"   ⚠ CTA 멘트 감지 → 음성 무시")
                        audio_transcription = None
                else:
                    print(f"   ⚠ 음성 내용 없음")
                    audio_transcription = None
            except Exception as e:
                self.logger.warning(f"Audio transcription failed (참고용이므로 무시): {e}")
                print(f"   ⚠ 음성 인식 실패 (무시)")
                audio_transcription = None
        else:
            audio_transcription = transcription

        # === STEP 3: VALIDATE ===
        if not vision_description and not audio_transcription:
            raise ValueError("영상 분석 실패: 화면 분석도 음성 인식도 모두 실패했습니다.")

        # === STEP 4: GENERATE SCRIPT ===
        print(f"\n   ✍ [3단계] 나레이션 스크립트 생성 중...")

        # Use GPT if API key available (BEST QUALITY!)
        if self.client:
            try:
                return self._generate_script_with_gpt(
                    vision_description=vision_description,
                    audio_transcription=audio_transcription,
                    duration=duration
                )
            except Exception as e:
                self.logger.error(f"GPT failed: {e}")
                print(f"   ⚠ GPT 실패, 템플릿으로 전환...")

        # Fallback to template (vision-first)
        primary_source = vision_description if vision_description else audio_transcription
        return self._generate_script_template_based(
            primary_source,
            duration,
            source="vision" if vision_description else "audio"
        )

    def _analyze_video_with_vision(self, video_path: Path) -> str:
        """
        Analyze video frames using FREE vision AI (BLIP).

        Args:
            video_path: Path to video file

        Returns:
            Description of video content
        """
        try:
            from transformers import BlipProcessor, BlipForConditionalGeneration
            from PIL import Image
            import numpy as np

            self.logger.info("Analyzing video with BLIP vision model (FREE)")

            # Load BLIP model (small, fast)
            processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

            # Extract key frames (more frames for better analysis)
            clip = VideoFileClip(str(video_path))
            duration = clip.duration

            # Sample more frames based on video length (every 2-3 seconds)
            num_frames = max(10, min(20, int(duration / 2)))  # 10-20 frames
            sample_times = [duration * (i / (num_frames - 1)) for i in range(num_frames)]

            print(f"   Analyzing {num_frames} frames...")

            descriptions = []

            for i, t in enumerate(sample_times):
                if t >= duration:
                    continue

                # Get frame
                frame = clip.get_frame(t)

                # Convert to PIL Image
                image = Image.fromarray(frame)

                # Generate caption
                inputs = processor(image, return_tensors="pt")
                outputs = model.generate(**inputs, max_new_tokens=50)
                caption = processor.decode(outputs[0], skip_special_tokens=True)

                descriptions.append(caption)
                self.logger.debug(f"Frame {i+1}/{num_frames} ({t:.1f}s): {caption}")

                # Show progress
                if (i + 1) % 5 == 0:
                    print(f"   Progress: {i+1}/{num_frames} frames analyzed...")

            clip.close()

            # Combine descriptions and translate to Korean
            if descriptions:
                # Analyze common themes
                all_text = " ".join(descriptions).lower()

                # Simple keyword-based Korean translation
                korean_elements = []

                # === FOOD & RESTAURANT ===
                if "food" in all_text or "dish" in all_text or "meal" in all_text:
                    korean_elements.append("음식이 담긴")
                if "plate" in all_text or "bowl" in all_text:
                    korean_elements.append("그릇에 담겨진")
                if "restaurant" in all_text or "dining" in all_text:
                    korean_elements.append("식당 분위기의")
                if "cooking" in all_text or "kitchen" in all_text:
                    korean_elements.append("주방에서 조리되는")
                if "meat" in all_text:
                    korean_elements.append("고기 요리")
                if "noodle" in all_text or "pasta" in all_text:
                    korean_elements.append("면 요리")
                if "vegetable" in all_text or "salad" in all_text:
                    korean_elements.append("채소가 들어간")
                if "sauce" in all_text:
                    korean_elements.append("소스가 뿌려진")
                if "grill" in all_text or "fried" in all_text:
                    korean_elements.append("구워진")

                # === ANIMALS ===
                if "cat" in all_text or "kitten" in all_text:
                    korean_elements.append("고양이가 등장하고")
                if "dog" in all_text or "puppy" in all_text:
                    korean_elements.append("강아지가 나타나며")
                if "bird" in all_text:
                    korean_elements.append("새가 있는")

                # === ACTIONS ===
                if "sitting" in all_text:
                    korean_elements.append("앉아있는 모습")
                if "looking" in all_text or "staring" in all_text:
                    korean_elements.append("무언가를 응시하는 장면")
                if "playing" in all_text:
                    korean_elements.append("신나게 노는 모습")
                if "sleeping" in all_text or "laying" in all_text:
                    korean_elements.append("편안하게 쉬는 장면")
                if "walking" in all_text or "running" in all_text:
                    korean_elements.append("움직이는 모습")
                if "eating" in all_text:
                    korean_elements.append("먹는 장면")
                if "drinking" in all_text:
                    korean_elements.append("마시는 장면")

                # === OBJECTS/PLACES ===
                if "chair" in all_text or "sofa" in all_text:
                    korean_elements.append("의자 위에서")
                if "table" in all_text:
                    korean_elements.append("테이블 위에")
                if "room" in all_text or "indoor" in all_text:
                    korean_elements.append("실내에서")
                if "outdoor" in all_text or "outside" in all_text:
                    korean_elements.append("야외에서")
                if "grass" in all_text or "garden" in all_text:
                    korean_elements.append("정원에서")
                if "toy" in all_text:
                    korean_elements.append("장난감과 함께")
                if "building" in all_text or "house" in all_text:
                    korean_elements.append("건물이 보이는")
                if "street" in all_text or "road" in all_text:
                    korean_elements.append("거리에서")

                # === PEOPLE ===
                if "person" in all_text or "man" in all_text or "woman" in all_text:
                    korean_elements.append("사람과 함께")
                if "child" in all_text or "kid" in all_text:
                    korean_elements.append("아이와 함께")
                if "hand" in all_text or "hands" in all_text:
                    korean_elements.append("손이 보이는")

                # === ATMOSPHERE ===
                if "light" in all_text or "bright" in all_text:
                    korean_elements.append("밝은 조명의")
                if "dark" in all_text or "night" in all_text:
                    korean_elements.append("어두운 분위기")
                if "colorful" in all_text or "color" in all_text:
                    korean_elements.append("다채로운 색감의")

                # Build result
                if korean_elements:
                    # Use more elements for richer description
                    result = ", ".join(korean_elements[:8])
                    self.logger.info(f"Korean interpretation: {result}")
                    return result
                else:
                    # Fallback - return raw descriptions for GPT to interpret
                    result = f"장면 설명: {', '.join(descriptions[:5])}"
                    self.logger.info(f"Using raw descriptions: {result}")
                    return result

            return None

        except ImportError:
            self.logger.warning("transformers not installed, vision analysis unavailable")
            print(f"   ⚠ transformers 라이브러리가 필요합니다")
            print(f"   설치: pip install --user transformers torch pillow")
            return None
        except Exception as e:
            self.logger.error(f"Vision analysis error: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def _generate_script_with_ollama(self, transcription: str, duration: float) -> str:
        """
        Generate creative narration using LOCAL Ollama LLM (FREE!).

        Args:
            transcription: Video description
            duration: Video duration in seconds

        Returns:
            Creative narration script
        """
        import requests

        self.logger.info("Generating script with LOCAL Ollama LLM (FREE)")
        print(f"   🤖 로컬 AI로 창의적인 나레이션 생성 중...")

        # Calculate exact target length
        target_chars = int(duration * 2.8)  # ~2.8 chars per second for Korean

        # Prepare Korean prompt for creative narration
        prompt = f"""You are a witty Korean shorts narrator. The video shows: {transcription}

YOUR TASK: Create a {target_chars}-character Korean narration that is ENTERTAINING, not descriptive.

 DON'T DO THIS (boring description):
"고양이가 앉아있는 모습, 집 안을 응시하는 장면입니다"

 DO THIS (creative interpretation):
"어? 이 녀석 표정 좀 보세요. 뭔가 심각하게 고민 중인데... 아마도 인간 관찰 일지 작성 중?"

RULES:
1. Pure Korean only (NO English!)
2. INTERPRET, don't describe - add personality and story
3. Use humor, curiosity, or storytelling
4. NO clichés: "귀여워요", "구독하세요", etc.
5. Exactly {target_chars} characters (±10)
6. Natural spoken style with personality

More examples:
- Sitting cat → "저 자세... 완전 회의 중인 사장님 포스인데요?"
- Looking around → "지금 뭔가 계획하는 눈빛이에요. 의심스러운데..."
- Resting → "이게 바로 프로 백수의 자세죠. 부럽네요"

NOW CREATE: {target_chars} chars Korean narration ONLY:"""

        try:
            # Call Ollama API
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:3b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.9,
                        "top_p": 0.95,
                        "num_predict": 200
                    }
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                script = result.get("response", "").strip()

                # Clean up script aggressively
                script = script.replace("나레이션:", "").strip()
                script = script.replace("```", "").strip()
                script = script.replace("Output:", "").strip()

                # Remove quotes if wrapped
                if script.startswith('"') and script.endswith('"'):
                    script = script[1:-1]
                if script.startswith("'") and script.endswith("'"):
                    script = script[1:-1]

                # Trim to target length if too long
                if len(script) > target_chars * 1.3:
                    script = script[:int(target_chars * 1.2)]
                    # Find last complete sentence
                    for punct in [".", "!", "?", "~"]:
                        last_idx = script.rfind(punct)
                        if last_idx > target_chars * 0.8:
                            script = script[:last_idx + 1]
                            break

                if script and len(script) > 20:
                    print(f"[OK] 창의적인 나레이션 생성 완료 ({len(script)}자 / 목표 {target_chars}자)")
                    print(f"   생성된 나레이션:")
                    print(f"   \"{script}\"")
                    self.logger.info(f"Generated creative Ollama script: {script[:200]}")
                    return script
                else:
                    raise ValueError("Ollama generated empty or too short script")

            else:
                raise ConnectionError(f"Ollama API returned status {response.status_code}")

        except requests.exceptions.ConnectionError:
            raise ConnectionError("Ollama not running. Install: https://ollama.com, then run: ollama pull llama3.2:3b")
        except Exception as e:
            self.logger.error(f"Ollama generation failed: {e}")
            raise

    def _generate_script_template_based(self, transcription: str, duration: float, source: str = "vision") -> str:
        """
        Generate CREATIVE narration script using advanced template system.

        Args:
            transcription: Original video transcription or vision description
            duration: Video duration in seconds
            source: "audio" or "vision"

        Returns:
            Creative narration script
        """
        self.logger.info(f"Generating script with CREATIVE template method ({source})")
        print(f"    창의적 템플릿으로 나레이션 생성 중... (소스: {source})")

        import random

        # Analyze content
        text = transcription.lower()
        target_chars = int(duration * 2.8)

        # Detect subject
        is_cat = "고양이" in transcription
        is_dog = "강아지" in transcription
        is_sitting = "앉아" in text or "sitting" in text
        is_looking = "응시" in text or "보" in text or "looking" in text
        is_resting = "쉬" in text or "편안" in text or "laying" in text or "sleeping" in text

        script_parts = []

        # === PART 1: Creative Hook ===
        if is_cat:
            hooks = [
                "잠깐만요, 이 표정 좀 보세요.",
                "어... 뭔가 수상한데요?",
                "이 녀석, 지금 뭘 하는 거죠?",
                "저 눈빛... 심상치 않은데요.",
                "혹시 이거 보셨어요?",
            ]
        elif is_dog:
            hooks = [
                "이거 실화인가요?",
                "잠깐, 뭔가 이상한데...",
                "어라? 이 친구 좀 보세요.",
                "지금 이 순간을 놓치지 마세요!",
            ]
        else:
            hooks = [
                "뭔가 특이한 장면이 포착됐습니다.",
                "자세히 보시면요...",
                "이거 보고 계셨나요?",
            ]

        script_parts.append(random.choice(hooks))

        # === PART 2: Creative Interpretation ===
        if is_cat:
            if is_sitting:
                interpretations = [
                    "저 자세... 완전 출근 전 나의 모습인데요?",
                    "이게 바로 프로 백수의 포스입니다.",
                    "지금 회의 중인 사장님 같은 포스네요.",
                    "분명히 뭔가 심각한 고민 중이에요. 저녁 메뉴?",
                    "저건 인생 고민하는 자세야... 나도 저래.",
                ]
            elif is_looking:
                interpretations = [
                    "뭔가 계획하는 눈빛... 의심스러운데요.",
                    "저 눈으로 인간 관찰 일지 작성 중인 듯.",
                    "지금 세계 정복 계획 세우는 중 아닌가요?",
                    "저건 완전히 뭔가 꾸미는 표정이에요.",
                ]
            elif is_resting:
                interpretations = [
                    "이게 진정한 삶의 지혜죠. 부러워요.",
                    "일하기 싫을 때 나의 모습이네요.",
                    "내 워라밸은 어디로 간 걸까요...",
                ]
            else:
                interpretations = [
                    "이 여유... 배우고 싶은데요.",
                    "저건 분명 뭔가 꾸미고 있어요.",
                ]
        elif is_dog:
            interpretations = [
                "이런 순수함은 어디서 나오는 걸까요?",
                "행복이 뭔지 저 친구가 알려주네요.",
                "저 에너지 좀 나눠주세요!",
            ]
        else:
            interpretations = [
                "평범해 보이지만 특별한 순간이에요.",
                "이런 게 진짜 일상의 행복 아닐까요?",
            ]

        script_parts.append(random.choice(interpretations))

        # === PART 3: Additional observations to reach target length ===
        observations = []

        if is_cat:
            observations = [
                "저 표정 진짜 심각한데요.",
                "뭔가 깊은 생각에 잠긴 듯.",
                "인간들은 이해 못 하는 고민이겠죠?",
                "저건 분명 계획이 있어 보여요.",
                "완전 프로 백수 인정합니다.",
                "저도 저 정도 여유는 갖고 싶네요.",
                "이 영상 계속 보게 되네요.",
            ]
        elif is_dog:
            observations = [
                "이 순수함 좀 보세요.",
                "진짜 천사 아닌가요?",
                "에너지가 넘치네요.",
                "행복이 뭔지 알려주는 듯.",
            ]
        else:
            observations = [
                "이런 순간들이 소중하죠.",
                "평범하지만 특별한 장면이에요.",
                "일상 속 작은 행복이네요.",
            ]

        # Add observations until reaching target length
        script_parts_text = " ".join(script_parts)
        current_length = len(script_parts_text)

        while current_length < target_chars * 0.9 and observations:
            obs = random.choice(observations)
            observations.remove(obs)
            script_parts.append(obs)
            current_length += len(obs) + 1

        # === PART 4: Natural Ending (NO CLICHÉ CTA) ===
        endings = [
            "여러분도 공감하시나요?",
            "이래서 못 말리죠.",
            "오늘도 평화롭네요.",
            "역시 예상을 벗어나지 않아요.",
            "뭔가 위로가 되는 장면이네요.",
            "이게 바로 힐링 아닐까요?",
        ]

        script_parts.append(random.choice(endings))

        # Combine
        script = " ".join(script_parts)

        # Final length check
        if len(script) > target_chars * 1.2:
            # Too long, trim to last sentence
            for punct in [".", "!", "?", "~"]:
                last_idx = script.rfind(punct, 0, int(target_chars * 1.1))
                if last_idx > target_chars * 0.7:
                    script = script[:last_idx + 1]
                    break

        print(f"[OK] 창의적인 나레이션 생성 완료 ({len(script)}자 / 목표 {target_chars}자)")
        print(f"   생성된 나레이션:")
        print(f"   \"{script}\"")
        self.logger.info(f"Generated creative template script: {script[:200]}")

        return script

    def _generate_script_with_gpt(
        self,
        vision_description: str = None,
        audio_transcription: str = None,
        duration: float = 60
    ) -> str:
        """
        Generate creative narration script using GPT-4 (COSTS ~$0.01-0.02).

        주의: vision_description을 메인으로, audio_transcription은 참고만 사용합니다.

        Args:
            vision_description: 영상 화면 분석 결과 (메인)
            audio_transcription: 음성 인식 결과 (참고용)
            duration: Video duration in seconds

        Returns:
            Creative narration script
        """
        self.logger.info("Using GPT-4 for creative narration (vision-first)")
        print(f"   🤖 GPT-4로 창의적인 나레이션 생성 중... (약 ₩13-26원)")

        target_chars = int(duration * 2.8)

        # Build context
        context_parts = []
        if vision_description:
            context_parts.append(f" 영상 화면 (메인): {vision_description}")
        if audio_transcription:
            context_parts.append(f" 음성 내용 (참고): {audio_transcription}")

        context = "\n".join(context_parts)

        # Load prompt template
        narration_template = self._load_prompt_template("narration_gpt.txt")

        if narration_template:
            prompt = narration_template.format(
                context=context,
                duration=duration,
                target_chars=target_chars
            )
        else:
            # Fallback to default
            prompt = f"""{context}

영상 길이: {duration:.0f}초 (목표: {target_chars}자)

위 영상을 바탕으로 {duration:.0f}초에 맞는 창의적이고 재미있는 한국어 나레이션을 작성하세요.

⚠ 중요:
- 영상 화면 분석()을 메인으로 사용하세요
- 음성 내용()은 참고만 하세요 (Whisper 오인식 가능성 있음)
- 음성과 화면이 다르면 화면을 우선하세요

 필수 조건:
1. 순수 한국어만 사용 (영어/외국어 금지)
2. 식상한 표현 금지 ("귀여워요", "구독해주세요" 등)
3. 영상 화면을 재미있게 해석하고 스토리텔링
4. 정확히 {target_chars}자 (±10자)
5. 자연스러운 구어체

 구조:
- 시작: 호기심 유발 (1-2문장)
- 중간: 재미있는 해석/관찰 (2-3문장)
- 끝: 자연스러운 마무리 (CTA 금지)

 금지:
- 단순 설명 ("음식이 있습니다")
- 영상과 무관한 일반적 멘트
- "구독", "좋아요", "알림" 같은 CTA
- 음성 내용을 그대로 따라 읽기

예시 스타일:
"잠깐, 이 비주얼 좀 보세요. 벌써부터 침샘 자극되는데요? 이게 바로 진짜 맛집의 포스죠. 저 색감, 저 질감... 화면으로 봐도 맛이 느껴지네요."

나레이션만 출력:"""

        try:
            response = self.client.chat.completions.create(
                model=os.getenv("NARRATION_MODEL", "gpt-4o-mini"),
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 창의적이고 유머러스한 쇼츠 영상 나레이터입니다. 영상 화면을 보고 재미있게 해석하며, 자연스러운 한국어로 시청자와 소통합니다. 음성 인식 결과는 참고만 하고 (오인식 가능), 화면 내용을 메인으로 사용합니다."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,
                max_tokens=300
            )

            script = response.choices[0].message.content.strip()

            # Clean up
            script = script.replace('"', '').replace("'", '').strip()

            print(f"[OK] 창의적인 나레이션 생성 완료 ({len(script)}자 / 목표 {target_chars}자)")
            print(f"   생성된 나레이션:")
            print(f"   \"{script}\"")
            self.logger.info(f"Generated GPT script (vision-first): {script[:200]}")

            return script

        except Exception as e:
            self.logger.error(f"GPT script generation failed: {e}")
            raise

    def _clean_script_for_tts(self, script: str) -> str:
        """
        Clean script text to remove problematic characters for TTS.

        Removes:
        - Backslash escape sequences (\", \\, etc.)
        - [Request interrupted by user] and similar patterns
        - Extra quotes
        - Multiple spaces

        Converts:
        - Numbers to Korean (3번 -> 세 번, 10분 -> 십 분)

        Args:
            script: Raw script text

        Returns:
            Cleaned script text safe for TTS
        """
        import re

        cleaned = script

        # 이스케이프 시퀀스를 먼저 처리 (백슬래시만 제거하면 \n이 n으로 남음)
        cleaned = cleaned.replace('\\n', ' ')  # 줄바꿈 -> 공백
        cleaned = cleaned.replace('\\t', ' ')  # 탭 -> 공백
        cleaned = cleaned.replace('\\r', '')   # 캐리지 리턴 제거
        cleaned = cleaned.replace('\\"', '"')  # 이스케이프된 따옴표
        cleaned = cleaned.replace("\\'", "'")  # 이스케이프된 작은따옴표
        cleaned = cleaned.replace('\\\\', '')  # 이중 백슬래시
        # 남은 백슬래시 제거 (TTS가 "백슬래시"로 읽음)
        cleaned = cleaned.replace('\\', '')

        # Remove common error/interrupt messages
        cleaned = re.sub(r'\[Request interrupted by user\]', '', cleaned)
        cleaned = re.sub(r'\[.*?interrupted.*?\]', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[.*?error.*?\]', '', cleaned, flags=re.IGNORECASE)

        # Remove markdown code block markers
        cleaned = cleaned.replace('```', '')

        # Fix double quotes
        cleaned = cleaned.replace('""', '"')
        cleaned = cleaned.replace("''", "'")

        # Convert numbers to Korean for better TTS pronunciation
        cleaned = self._convert_numbers_to_korean(cleaned)

        # Clean up multiple spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned

    def _add_emotion_tags(self, text: str, enable_emotion: bool = True) -> str:
        """
        Add SSML emotion tags to text based on punctuation and keywords.

        Args:
            text: Clean text
            enable_emotion: Whether to add emotion tags (default: True)

        Returns:
            Text with SSML emotion tags
        """
        if not enable_emotion:
            return text

        import re

        # 문장 단위로 분리
        sentences = re.split(r'([.!?\n])', text)
        result = []

        for i, sentence in enumerate(sentences):
            if not sentence.strip() or sentence in '.!?\n':
                result.append(sentence)
                continue

            sentence_lower = sentence.lower()

            # 감정 키워드 감지
            # 긴장/충격 (pitch up, rate faster)
            if any(kw in sentence_lower for kw in ['놀랍', '충격', '깜짝', '어', '아', '헉', '앗']):
                result.append(f'<prosody pitch="+15%" rate="1.15">{sentence}</prosody>')

            # 슬픔/우울 (pitch down, rate slower)
            elif any(kw in sentence_lower for kw in ['슬프', '눈물', '울', '죽', '떠났', '미안', '안타까운']):
                result.append(f'<prosody pitch="-10%" rate="0.90">{sentence}</prosody>')

            # 분노/강조 (pitch up, rate faster, louder)
            elif any(kw in sentence_lower for kw in ['화', '분노', '미쳤', '싫', '안 돼', '절대']) or sentence.endswith('!'):
                result.append(f'<prosody pitch="+10%" rate="1.10" volume="+10%">{sentence}</prosody>')

            # 속삭임/비밀 (pitch down, rate slower, quieter)
            elif any(kw in sentence_lower for kw in ['속삭', '조용', '비밀', '쉿', '몰래']):
                result.append(f'<prosody pitch="-5%" rate="0.85" volume="-15%">{sentence}</prosody>')

            # 질문 (pitch up at end)
            elif sentence.strip().endswith('?'):
                result.append(f'<prosody pitch="+8%">{sentence}</prosody>')

            # 기본 (변경 없음)
            else:
                result.append(sentence)

        # 느린 장면 전환에 약간의 pause 추가
        result_text = ''.join(result)
        result_text = result_text.replace('.\n', '.<break time="300ms"/>\n')
        result_text = result_text.replace('!\n', '!<break time="400ms"/>\n')
        result_text = result_text.replace('?\n', '?<break time="350ms"/>\n')

        return result_text

    def _convert_numbers_to_korean(self, text: str) -> str:
        """
        Convert numbers in text to Korean pronunciation.

        Examples:
        - "3번" -> "세 번"
        - "10분" -> "십 분"
        - "2023년" -> "이천이십삼 년"
        - "1등" -> "일 등"
        - "010-1234-5678" -> "공 일 공 일 이 삼 사 오 육 칠 팔"

        Args:
            text: Text containing numbers

        Returns:
            Text with numbers converted to Korean
        """
        import re

        # 전화번호 패턴 처리 (010-1234-5678, 02-123-4567 등)
        def convert_phone_number(match):
            """전화번호를 한 글자씩 읽기"""
            phone = match.group(0)
            # 숫자만 추출
            digits = re.sub(r'[^\d]', '', phone)
            # 각 숫자를 한글로 변환
            digit_names = ['공', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
            result = ' '.join([digit_names[int(d)] for d in digits])
            return result

        # 전화번호 패턴 (010-xxxx-xxxx, 02-xxx-xxxx, 031-xxx-xxxx 등)
        # 0으로 시작하는 전화번호 형식
        phone_pattern = r'0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}'
        text = re.sub(phone_pattern, convert_phone_number, text)

        # 비밀번호/코드 패턴 처리 (4자리 이상 연속 숫자)
        # 예: "비밀번호는 1234입니다" -> "비밀번호는 일 이 삼 사입니다"
        def convert_code(match):
            """연속된 숫자를 한 글자씩 읽기"""
            prefix = match.group(1) if match.group(1) else ''
            code = match.group(2)
            digit_names = ['공', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
            result = ' '.join([digit_names[int(d)] for d in code])
            return prefix + result

        # 비밀번호, 암호, 코드 등의 키워드 뒤에 오는 숫자
        code_pattern = r'(비밀번호는?|암호는?|코드는?|번호는?)\s*(\d{4,})'
        text = re.sub(code_pattern, convert_code, text)

        def num_to_korean(num: int, sino: bool = True) -> str:
            """
            Convert number to Korean.

            Args:
                num: Number to convert
                sino: If True, use Sino-Korean (일이삼), if False use Native Korean (하나둘셋)
            """
            if sino:
                # Sino-Korean (한자어 숫자)
                ones = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
                tens = ['', '십', '이십', '삼십', '사십', '오십', '육십', '칠십', '팔십', '구십']

                if num == 0:
                    return '영'

                if num < 10:
                    return ones[num]
                elif num < 100:
                    ten_digit = num // 10
                    one_digit = num % 10
                    result = tens[ten_digit]
                    if one_digit > 0:
                        result += ' ' + ones[one_digit]
                    return result
                elif num < 1000:
                    hundred_digit = num // 100
                    remainder = num % 100
                    # "일백" -> "백" (1은 생략)
                    if hundred_digit == 1:
                        result = '백'
                    else:
                        result = ones[hundred_digit] + '백'
                    if remainder > 0:
                        result += ' ' + num_to_korean(remainder, sino=True)
                    return result
                elif num < 10000:
                    thousand_digit = num // 1000
                    remainder = num % 1000
                    # "일천" -> "천" (1은 생략)
                    if thousand_digit == 1:
                        result = '천'
                    else:
                        result = ones[thousand_digit] + '천'
                    if remainder > 0:
                        result += ' ' + num_to_korean(remainder, sino=True)
                    return result
                elif num < 100000000:  # 1억 미만 (만 단위)
                    man_digit = num // 10000
                    remainder = num % 10000
                    result = num_to_korean(man_digit, sino=True) + '만'
                    if remainder > 0:
                        result += ' ' + num_to_korean(remainder, sino=True)
                    return result
                elif num < 1000000000000:  # 1조 미만 (억 단위)
                    eok_digit = num // 100000000
                    remainder = num % 100000000
                    result = num_to_korean(eok_digit, sino=True) + '억'
                    if remainder > 0:
                        result += ' ' + num_to_korean(remainder, sino=True)
                    return result
                else:
                    # For very large numbers, just return as is
                    return str(num)
            else:
                # Native Korean (고유어 숫자) - for counting things
                native = ['', '하나', '둘', '셋', '넷', '다섯', '여섯', '일곱', '여덟', '아홉', '열']

                if num < 1 or num > 99:
                    # Use Sino-Korean for numbers outside native range
                    return num_to_korean(num, sino=True)

                if num <= 10:
                    return native[num]
                elif num < 20:
                    return '열' + (' ' + native[num - 10] if num > 10 else '')
                elif num < 100:
                    ten_digit = num // 10
                    one_digit = num % 10
                    # 20대 숫자는 단위에 따라 다르게 처리
                    # "스물" (기본) vs "스무" (받침으로 끝나는 단위 앞: 개, 명, 마리)
                    # "살"은 받침이 없으므로 "스물"을 사용해야 함
                    tens_native = ['', '', '스물', '서른', '마흔', '쉰', '예순', '일흔', '여든', '아흔']
                    result = tens_native[ten_digit]
                    if one_digit > 0:
                        result += ' ' + native[one_digit]
                    return result
                else:
                    return num_to_korean(num, sino=True)

        def replace_number(match):
            """Replace matched number with Korean."""
            full_match = match.group(0)
            num_str = match.group(1)
            unit = match.group(2) if match.group(2) else ''

            try:
                num = int(num_str)

                # Decide whether to use Sino or Native Korean based on unit
                # Native Korean (고유어) units: 번, 개, 명, 마리, 살, 시
                # Sino Korean (한자어) units: 분, 초, 년, 월, 일, 등, 위, 회, 차
                native_units = ['번', '번째', '개', '명', '마리', '살', '시']
                sino_units = ['분', '초', '년', '월', '일', '등', '위', '회', '차', '층', '대', '권', '장', '곡', '편', '화', '기']

                # Determine reading style
                use_native = False
                if unit:
                    # Check if unit requires native Korean
                    if any(unit.startswith(u) for u in native_units) and num <= 99:
                        use_native = True
                    # For 10 with 번, use native "열"
                    elif num == 10 and unit.startswith('번'):
                        use_native = True

                korean_num = num_to_korean(num, sino=not use_native)

                # 받침 탈락 처리: 셋→세, 넷→네
                if unit and use_native:
                    if korean_num == '셋':
                        korean_num = '세'
                    elif korean_num == '넷':
                        korean_num = '네'
                    elif korean_num.startswith('셋 '):
                        korean_num = '세 ' + korean_num[2:]
                    elif korean_num.startswith('넷 '):
                        korean_num = '네 ' + korean_num[2:]

                    # 스물 → 스무 변환 (받침으로 끝나는 단위 앞에서만)
                    # 받침으로 끝나는 단위: 개, 명, 마리
                    # 받침이 없는 단위: 살, 번, 시, 번째
                    batchim_units = ['개', '명', '마리']
                    if any(unit.startswith(u) for u in batchim_units):
                        # "스물 셋" -> "스무 세" (공백 있음)
                        if korean_num.startswith('스물 '):
                            korean_num = '스무 ' + korean_num[3:]
                        # "스물셋" -> "스무세" (공백 없음, 실제로는 발생 안함)
                        elif korean_num.startswith('스물'):
                            korean_num = '스무' + korean_num[2:]
                        # "스물" 단독
                        elif korean_num == '스물':
                            korean_num = '스무'

                # Add space between number and unit for better pronunciation
                if unit:
                    return korean_num + ' ' + unit
                else:
                    return korean_num

            except ValueError:
                return full_match

        # Pattern: number followed by optional unit (번, 분, 초, 개, 명, 등, 위, 년, 월, 일, etc.)
        # Match numbers with common units
        pattern = r'(\d+)(번째|번|분|초|개|명|마리|살|시|등|위|년|월|일|회|차|층|대|권|장|곡|편|화|기|원|달러|킬로|미터|센티|그램|리터)?'

        result = re.sub(pattern, replace_number, text)

        return result

    def _process_control_commands(self, text: str) -> tuple:
        """
        Process control commands in narration text like [무음 3초], [침묵], etc.
        Returns (cleaned_text, pauses) where pauses is list of (position_in_chars, duration).
        """
        import re

        # Patterns: [무음 3초], [침묵 2초], [pause 3초], [무음], [침묵]
        pattern = r'\[(무음|침묵|pause)\s*(\d+(?:\.\d+)?)?초?\]'

        pauses = []
        cleaned_segments = []
        last_end = 0

        for match in re.finditer(pattern, text):
            # Add text before this command
            segment = text[last_end:match.start()].strip()
            if segment:
                cleaned_segments.append(segment)

            # Extract pause duration
            duration_str = match.group(2)
            if duration_str:
                duration = float(duration_str)
            else:
                # Set different defaults based on command type
                command_type = match.group(1)
                if command_type == '무음':
                    duration = 2.0  # 무음: 2 seconds
                elif command_type == '침묵':
                    duration = 3.0  # 침묵: 3 seconds
                elif command_type == 'pause':
                    duration = 2.0  # pause: 2 seconds
                else:
                    duration = 1.0  # Fallback

            # Record pause (position is the length so far)
            pauses.append({
                'position': len(' '.join(cleaned_segments)),
                'duration': duration
            })

            last_end = match.end()

        # Add remaining text
        remaining = text[last_end:].strip()
        if remaining:
            cleaned_segments.append(remaining)

        cleaned_text = ' '.join(cleaned_segments)

        return cleaned_text, pauses

    def generate_speech(
        self,
        script: str,
        output_path: Path,
        use_free_tts: bool = True
    ) -> Path:
        """
        Generate speech audio from script using FREE TTS.
        Handles control commands like [무음 3초] automatically.

        Args:
            script: Narration script (may contain control commands)
            output_path: Output audio file path
            use_free_tts: Use free TTS (edge-tts) instead of OpenAI

        Returns:
            Path to generated audio file
        """
        # First clean the script (remove backslashes, error messages, convert numbers)
        script = self._clean_script_for_tts(script)

        # Add emotion tags (optional - controlled by environment variable)
        enable_emotion = os.getenv("TTS_ENABLE_EMOTION", "true").lower() == "true"
        script = self._add_emotion_tags(script, enable_emotion=enable_emotion)

        # Then process control commands
        cleaned_script, pauses = self._process_control_commands(script)

        if pauses:
            print(f"   [Control] Detected {len(pauses)} pause commands")
            for i, pause in enumerate(pauses, 1):
                print(f"     {i}. Pause {pause['duration']}초 at position ~{pause['position']}")

        audio_path = output_path.with_suffix('.mp3')

        if use_free_tts:
            # Use FREE Microsoft Edge TTS (HIGH QUALITY)
            return self._generate_speech_edge_tts(cleaned_script, audio_path, pauses)
        else:
            # Use OpenAI TTS (PAID)
            return self._generate_speech_openai(cleaned_script, audio_path, pauses)

    def _insert_pauses_into_audio(self, audio_path: Path, script: str, pauses: list) -> Path:
        """
        Insert silence at specified pause positions in audio file.

        Args:
            audio_path: Path to audio file to modify
            script: The cleaned script text (without control commands)
            pauses: List of pause dicts with 'position' (char index) and 'duration' (seconds)

        Returns:
            Path to modified audio file
        """
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_nonsilent

            self.logger.info(f"Inserting {len(pauses)} pauses into audio")
            print(f"   [Pause] Inserting {len(pauses)} silence segments...")

            # Load audio
            audio = AudioSegment.from_file(str(audio_path))
            audio_duration_ms = len(audio)

            # Calculate time per character (approximate)
            if len(script) == 0:
                self.logger.warning("Script is empty, cannot calculate pause positions")
                return audio_path

            ms_per_char = audio_duration_ms / len(script)

            # Sort pauses by position
            sorted_pauses = sorted(pauses, key=lambda p: p['position'])

            # Build segments
            segments = []
            last_pos_ms = 0

            for i, pause in enumerate(sorted_pauses):
                # Calculate time position in audio
                time_ms = int(pause['position'] * ms_per_char)

                # Ensure position is within audio bounds
                time_ms = max(0, min(time_ms, audio_duration_ms))

                # Add audio segment before pause
                if time_ms > last_pos_ms:
                    segments.append(audio[last_pos_ms:time_ms])

                # Add silence
                silence_ms = int(pause['duration'] * 1000)
                segments.append(AudioSegment.silent(duration=silence_ms))

                print(f"     {i+1}. Inserted {pause['duration']}초 silence at {time_ms/1000:.1f}s")

                last_pos_ms = time_ms

            # Add remaining audio
            if last_pos_ms < audio_duration_ms:
                segments.append(audio[last_pos_ms:])

            # Combine all segments
            final_audio = sum(segments) if segments else audio

            # Export back to same file
            final_audio.export(str(audio_path), format="mp3")

            new_duration = len(final_audio) / 1000
            print(f"   [OK] Audio with pauses: {new_duration:.1f}s (original: {audio_duration_ms/1000:.1f}s)")
            self.logger.info(f"Pauses inserted, new duration: {new_duration:.1f}s")

            return audio_path

        except ImportError:
            self.logger.warning("pydub not installed, skipping pause insertion")
            print(f"   [Warning] pydub not installed, pauses will be ignored")
            print(f"   Install with: pip install pydub")
            return audio_path
        except Exception as e:
            self.logger.error(f"Failed to insert pauses: {e}")
            print(f"   [Warning] Failed to insert pauses: {e}")
            return audio_path

    def _generate_speech_edge_tts(self, script: str, audio_path: Path, pauses: list = None) -> Path:
        """Generate speech using FREE Microsoft Edge TTS with pause support."""
        try:
            import asyncio
            import edge_tts

            self.logger.info("Generating speech with FREE Edge TTS")
            print(f"\n[TTS] Generating Korean narration audio (FREE)...")

            # Script is already cleaned by generate_speech()
            # Korean voices
            # ko-KR-SoonBokNeural (Female, warm, default)
            # ko-KR-SunHiNeural (Female, natural)
            # ko-KR-InJoonNeural (Male, natural)
            voice = os.getenv("TTS_VOICE", "ko-KR-SoonBokNeural")

            async def generate():
                communicate = edge_tts.Communicate(script, voice)
                await communicate.save(str(audio_path))

            # Run async function
            asyncio.run(generate())

            # If pauses exist, insert silence
            if pauses:
                self._insert_pauses_into_audio(audio_path, script, pauses)

            print(f"[OK] Free TTS narration generated")
            self.logger.info(f"Speech generated: {audio_path}")

            return audio_path

        except Exception as e:
            self.logger.error(f"Edge TTS failed: {e}")
            # Fallback to gTTS
            return self._generate_speech_gtts(script, audio_path, pauses)

    def _generate_speech_gtts(self, script: str, audio_path: Path, pauses: list = None) -> Path:
        """Generate speech using FREE Google TTS (backup) with pause support."""
        try:
            from gtts import gTTS

            self.logger.info("Generating speech with FREE Google TTS")
            print(f"\n[TTS] Generating Korean narration audio (Google TTS)...")

            # Script is already cleaned by generate_speech()
            tts = gTTS(text=script, lang='ko', slow=False)
            tts.save(str(audio_path))

            # If pauses exist, insert silence
            if pauses:
                self._insert_pauses_into_audio(audio_path, script, pauses)

            print(f"[OK] Free TTS narration generated")
            return audio_path

        except Exception as e:
            self.logger.error(f"gTTS failed: {e}")
            raise

    def _generate_speech_openai(self, script: str, audio_path: Path, pauses: list = None) -> Path:
        """Generate speech using OpenAI TTS (PAID) with pause support."""
        if not self.client:
            raise ValueError("OpenAI API key not found")

        self.logger.info("Generating speech with OpenAI TTS (PAID)")
        print(f"\n[TTS] Generating narration audio with OpenAI TTS...")

        try:
            # Script is already cleaned by generate_speech()
            voice = os.getenv("TTS_VOICE", "alloy")

            response = self.client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=script,
                speed=1.0
            )

            response.stream_to_file(str(audio_path))

            # If pauses exist, insert silence
            if pauses:
                self._insert_pauses_into_audio(audio_path, script, pauses)

            print(f"[OK] Narration audio generated")
            return audio_path

        except Exception as e:
            self.logger.error(f"OpenAI TTS failed: {e}")
            raise

    def add_narration_to_video(
        self,
        clip: VideoFileClip,
        narration_audio_path: Path,
        mix_ratio: float = 0.3
    ) -> VideoFileClip:
        """
        Add narration audio to video with duration matching.

        Args:
            clip: Video clip
            narration_audio_path: Path to narration audio
            mix_ratio: Original audio volume ratio (0-1)

        Returns:
            Video with narration
        """
        print(f"\n🔊 나레이션 믹싱 중...")

        try:
            # Load narration audio
            narration = AudioFileClip(str(narration_audio_path))

            video_duration = clip.duration
            narration_duration = narration.duration

            print(f"   동영상 길이: {video_duration:.1f}초")
            print(f"   나레이션 길이: {narration_duration:.1f}초")

            # Calculate duration difference
            duration_diff = abs(video_duration - narration_duration)
            diff_percent = (duration_diff / video_duration) * 100

            # === STRATEGY: Match narration to video duration ===
            if duration_diff > 1.0:  # More than 1 second difference
                print(f"   ⚠ 길이 차이: {duration_diff:.1f}초 ({diff_percent:.1f}%)")

                if narration_duration > video_duration:
                    # Narration too long - speed up
                    speed_factor = narration_duration / video_duration
                    if speed_factor <= 1.5:  # Max 1.5x speed (still natural)
                        print(f"    나레이션 속도 조절: {speed_factor:.2f}x")
                        try:
                            # Try MoviePy 2.x method
                            from moviepy.audio.fx.audio_speed import audio_speedx
                            narration = audio_speedx(narration, factor=speed_factor)
                        except ImportError:
                            # Fallback to MoviePy 1.x method
                            try:
                                narration = narration.fx(lambda clip: clip.speedx(speed_factor))
                            except:
                                # If all fails, just trim
                                print(f"   ⚠ 속도 조절 실패, 자르기로 대체")
                                narration = narration.subclip(0, video_duration)
                        print(f"   [OK] 나레이션 길이 조정: {narration.duration:.1f}초")
                    else:
                        # Too fast, just trim
                        print(f"   ✂ 나레이션 자르기 (속도 조절 불가)")
                        narration = narration.subclip(0, video_duration)

                elif narration_duration < video_duration:
                    # Narration too short - slow down
                    speed_factor = narration_duration / video_duration
                    if speed_factor >= 0.7:  # Min 0.7x speed (still natural)
                        print(f"   🐢 나레이션 속도 조절: {speed_factor:.2f}x (느리게)")
                        try:
                            # Try MoviePy 2.x method
                            from moviepy.audio.fx.audio_speed import audio_speedx
                            narration = audio_speedx(narration, factor=speed_factor)
                        except ImportError:
                            # Fallback to MoviePy 1.x method
                            try:
                                narration = narration.fx(lambda clip: clip.speedx(speed_factor))
                            except:
                                # If all fails, keep original
                                print(f"   ⚠ 속도 조절 실패")
                        print(f"   [OK] 나레이션 길이 조정: {narration.duration:.1f}초")
                    else:
                        # Too slow would sound unnatural, adjust video instead
                        print(f"   ⚠ 나레이션이 너무 짧음 ({narration_duration:.1f}초)")
                        print(f"    동영상 길이를 나레이션에 맞춤")
                        # Will be handled by caller (editor.py)
            else:
                print(f"   [OK] 길이 차이 무시 가능 ({duration_diff:.1f}초)")

            # Final adjustment - ensure narration doesn't exceed video
            if narration.duration > clip.duration:
                narration = narration.subclip(0, clip.duration)

            if clip.audio:
                # Mix with original audio (reduce original volume)
                from moviepy.audio.fx.all import volumex
                original_audio = clip.audio.fx(volumex, mix_ratio)
                mixed_audio = CompositeAudioClip([original_audio, narration])
                clip = clip.set_audio(mixed_audio)
            else:
                # Just set narration as audio
                clip = clip.set_audio(narration)

            print(f"[OK] 나레이션 믹싱 완료")
            return clip

        except Exception as e:
            self.logger.error(f"Failed to add narration: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return clip

    def create_narrated_video(
        self,
        video_path: Path,
        output_path: Path,
        video_description: str = None
    ) -> Path:
        """
        Create video with AI narration.

        Args:
            video_path: Input video path
            output_path: Output video path
            video_description: Optional video description

        Returns:
            Path to narrated video
        """
        # Generate script
        script = self.generate_narration_script(video_path, video_description)

        # Generate speech
        audio_path = self.generate_speech(script, output_path)

        # Add to video
        clip = VideoFileClip(str(video_path))
        clip = self.add_narration_to_video(clip, audio_path)

        # Export
        print(f"\n[Export] Exporting narrated video...")
        clip.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            logger='bar'
        )

        clip.close()

        # Cleanup temp audio
        audio_path.unlink(missing_ok=True)

        return output_path
