"""Create long-form story videos with multiple scenes."""

import logging
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from openai import OpenAI
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip, ImageClip
import requests
from PIL import Image, ImageOps
import io
from tqdm import tqdm
import time


class LongFormStoryCreator:
    """Create long-form story videos with multiple scenes and images."""

    def __init__(self, config: Dict[str, Any], job_id: Optional[str] = None):
        self.config = config
        self.job_id = job_id

        # DB 로깅 설정 (job_id가 있으면)
        if job_id:
            try:
                from src.utils import setup_db_logging
                self.logger = setup_db_logging(
                    job_id=job_id,
                    logger_name="AutoShortsEditor.LongFormCreator"
                )
                self.logger.info(f"LongFormCreator initialized with job_id: {job_id}")
            except Exception as e:
                # DB 로깅 실패해도 기본 로거 사용
                self.logger = logging.getLogger("AutoShortsEditor.LongFormCreator")
                self.logger.warning(f"Failed to setup DB logging: {e}")
        else:
            self.logger = logging.getLogger("AutoShortsEditor.LongFormCreator")

        self.client = None
        self.hf_api_key = None

        # Initialize LLM client based on provider
        self._initialize_llm_client()

        # Initialize Hugging Face API key (optional, for image generation)
        self.hf_api_key = os.getenv("HUGGINGFACE_API_KEY")
        if self.hf_api_key:
            self.logger.info("Hugging Face API key found - will use for image generation")

        # Initialize Replicate API token (optional, for cheap image generation)
        self.replicate_api_token = os.getenv("REPLICATE_API_TOKEN")
        if self.replicate_api_token:
            self.logger.info("Replicate API token found - will use for image generation")

        # Initialize Google Generative AI (optional, for Imagen 3)
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.google_genai = None
        if self.google_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.google_api_key)
                self.google_genai = genai
                self.logger.info("Google API key found - Imagen 3 available for image generation")
            except ImportError:
                self.logger.warning("google-generativeai not installed. Install with: pip install google-generativeai")

        # Get image generation provider from config
        self.image_provider = config.get("ai", {}).get("image_generation", {}).get("provider", "openai")

    def _initialize_llm_client(self):
        """Initialize LLM client based on configured provider."""
        llm_config = self.config.get("ai", {}).get("llm", {})
        provider = llm_config.get("provider", "openai")

        if provider == "groq":
            # Groq provider (FREE)
            api_key = os.getenv("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY required when using Groq provider. Get free API key at: https://console.groq.com")

            self.client = OpenAI(
                api_key=api_key,
                base_url="https://api.groq.com/openai/v1"
            )
            self.llm_provider = "groq"
            self.llm_model = llm_config.get("groq", {}).get("model", "llama-3.3-70b-versatile")
            self.vision_model = "gpt-4o"  # Groq doesn't have vision, fallback to OpenAI for image analysis

            # Check if OpenAI key is available for vision tasks
            self.openai_client = None
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                self.openai_client = OpenAI(api_key=openai_key)
                self.logger.info("OpenAI client also initialized for vision tasks")

            self.logger.info(f"Using Groq (FREE): {self.llm_model}")
            print(f"[LLM Provider] Groq (FREE) - Model: {self.llm_model}")

        elif provider == "ollama":
            # Ollama provider (LOCAL, FREE)
            ollama_config = llm_config.get("ollama", {})
            base_url = ollama_config.get("base_url", "http://localhost:11434/v1")

            self.client = OpenAI(
                api_key="ollama",  # Ollama doesn't need a real API key
                base_url=base_url
            )
            self.llm_provider = "ollama"
            self.llm_model = ollama_config.get("model", "llama3.2:3b")
            self.vision_model = "gpt-4o"  # Ollama doesn't have vision by default, fallback to OpenAI

            # Check if OpenAI key is available for vision tasks
            self.openai_client = None
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                self.openai_client = OpenAI(api_key=openai_key)
                self.logger.info("OpenAI client also initialized for vision tasks")

            self.logger.info(f"Using Ollama (LOCAL): {self.llm_model} at {base_url}")
            print(f"[LLM Provider] Ollama (LOCAL) - Model: {self.llm_model}")

        elif provider == "openai":
            # OpenAI provider (default)
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY required when using OpenAI provider")

            self.client = OpenAI(api_key=api_key)
            self.openai_client = self.client  # Same client for vision
            self.llm_provider = "openai"
            self.llm_model = llm_config.get("openai", {}).get("model", os.getenv("NARRATION_MODEL", "gpt-4o"))
            self.vision_model = "gpt-4o"

            self.logger.info(f"Using OpenAI: {self.llm_model}")
            print(f"[LLM Provider] OpenAI - Model: {self.llm_model}")

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}. Supported: openai, groq, ollama")

    def _save_last_project(self, project_dir: Path):
        """Save the last project directory for easy resume."""
        last_project_file = Path.cwd() / ".last_project.txt"
        try:
            with open(last_project_file, 'w', encoding='utf-8') as f:
                f.write(str(project_dir.resolve()))
            self.logger.info(f"Saved last project path: {project_dir}")
        except Exception as e:
            self.logger.warning(f"Could not save last project path: {e}")

    @staticmethod
    def get_last_project() -> Optional[Path]:
        """Get the last project directory."""
        last_project_file = Path.cwd() / ".last_project.txt"
        if last_project_file.exists():
            try:
                with open(last_project_file, 'r', encoding='utf-8') as f:
                    path_str = f.read().strip()
                    if path_str:
                        project_path = Path(path_str)
                        if project_path.exists():
                            return project_path
            except Exception:
                pass
        return None

    def _save_project_status(self, project_dir: Path, status: str, **kwargs):
        """Save project status for resume capability."""
        from datetime import datetime

        status_data = {
            'status': status,
            'last_updated': datetime.now().isoformat(),
            **kwargs
        }

        status_path = project_dir / "project_status.json"
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Project status saved: {status}")

        # Save as last project for easy resume
        self._save_last_project(project_dir)

    def resume_from_project(self, project_dir: Path, auto_confirm: bool = False) -> Dict[str, Any]:
        """Resume video creation from existing project folder.

        Args:
            project_dir: Path to the project directory
            auto_confirm: If True, skip all user confirmations and proceed automatically
        """

        # Save this as the last project
        self._save_last_project(project_dir)

        print(f"\n{'='*70}")
        print(f"[Resuming Project]")
        print(f"{'='*70}\n")

        # Load project status
        status_path = project_dir / "project_status.json"
        if status_path.exists():
            with open(status_path, 'r', encoding='utf-8') as f:
                status_data = json.load(f)
            print(f"[Status] Previous Status: {status_data['status']}")
            print(f"   Last Updated: {status_data['last_updated']}")
            print(f"   Next Step: {status_data.get('next_step', 'Unknown')}\n")
        else:
            print(f"[Warning] No project_status.json found, will detect status automatically\n")
            status_data = {}

        # Load story metadata
        metadata_path = project_dir / "story_metadata.json"
        if not metadata_path.exists():
            raise FileNotFoundError(f"No story_metadata.json found in {project_dir}")

        with open(metadata_path, 'r', encoding='utf-8') as f:
            story_data = json.load(f)

        print(f"Title: {story_data['title']}")
        print(f"Scenes: {len(story_data['scenes'])}")
        print(f"Script Length: {len(story_data.get('script', ''))} chars")

        # Check what's already done
        has_images = any((project_dir / f"scene_{i:02d}" / f"scene_{i:02d}_image.png").exists()
                        for i in range(1, len(story_data['scenes']) + 1))

        # Check if resuming from test mode
        is_test_mode = status_data.get('status') == 'test_complete'

        if has_images:
            if is_test_mode:
                print(f"\n[테스트 모드에서 재개] 이미지가 이미 존재합니다.")
                print(f"  상세 나레이션 생성 → TTS → 비디오 제작이 진행됩니다.\n")
            else:
                print(f"\n[OK] 이미지가 이미 존재합니다.")
                print(f"  사용자 확인부터 시작합니다...\n")

            # [통합] 씬 정렬 후 이미지+비디오 모두 체크
            sorted_scenes = self._sort_scenes(story_data['scenes'])

            scene_media = []
            for i, scene in enumerate(sorted_scenes, 1):
                scene_dir = project_dir / f"scene_{i:02d}"
                image_path = scene_dir / f"scene_{i:02d}_image.png"
                video_path = scene_dir / f"scene_{i:02d}_video.mp4"

                media_type = None
                media_path = None

                # 비디오 우선 (있으면 비디오 사용)
                if video_path.exists():
                    media_type = 'video'
                    media_path = video_path
                elif image_path.exists():
                    media_type = 'image'
                    media_path = image_path

                if media_path:
                    scene_media.append({
                        'scene': scene,
                        'media_type': media_type,
                        'media_path': media_path,
                        'image_path': image_path if media_type == 'image' else None,
                        'video_path': video_path if media_type == 'video' else None,
                        'scene_dir': scene_dir,
                        'scene_num': i
                    })

            print(f"생성된 미디어 목록:")
            for media_data in scene_media:
                media_icon = "🎬" if media_data['media_type'] == 'video' else "🖼️"
                print(f"  - Scene {media_data['scene_num']:02d}: {media_icon} {media_data['media_path'].name}")

            print(f"\n프로젝트 폴더: {project_dir}")

            if auto_confirm or is_test_mode:
                if is_test_mode:
                    print(f"\n[테스트 모드 자동 재개] 이미지 확인을 건너뛰고 상세 나레이션 생성을 시작합니다...")
                else:
                    print(f"\n[Auto-Confirm] 자동으로 계속 진행합니다...")
                user_input = 'y'
            else:
                print(f"\n이미지를 확인하시고 계속 진행하시겠습니까?")
                print(f"  - 계속하려면 'y' 또는 'yes' 입력")
                print(f"  - 중단하려면 'n' 또는 'no' 입력")
                user_input = input("\n 선택: ").strip().lower()

            if user_input not in ['y', 'yes']:
                print(f"\n중단되었습니다.")
                return {
                    'status': 'media_only',
                    'project_dir': str(project_dir),
                    'num_scenes': len(scene_media),
                    'script_length': len(story_data.get('script', '')),
                    'media': [str(media['media_path']) for media in scene_media]
                }

            # Continue from Step 2-B (narrations if needed)
            aspect_ratio = "16:9"  # Default
            target_minutes = 60
            num_scenes = len(sorted_scenes)

            # Continue with the rest of the process (from Step 2-B)
            return self._continue_from_media(project_dir, story_data, scene_media, aspect_ratio, target_minutes, is_test_mode=is_test_mode)

        else:
            print(f"\n[OK] 시나리오는 있지만 이미지가 없습니다.")
            print(f"  이미지 생성부터 시작합니다...\n")

            # Start from image generation
            # TODO: Implement image generation from existing scenario
            raise NotImplementedError("이미지 생성부터 재개하는 기능은 아직 구현되지 않았습니다.")

    def _sort_scenes(self, scenes: List[Dict]) -> List[Dict]:
        """
        씬을 정렬: seq가 있으면 seq 우선, 없으면 created_at 기준

        Args:
            scenes: 씬 리스트

        Returns:
            정렬된 씬 리스트
        """
        def get_sort_key(scene):
            # seq가 있으면 (0, seq) - 가장 우선
            if 'seq' in scene and scene['seq'] is not None:
                return (0, scene['seq'])
            # created_at이 있으면 (1, timestamp) - 그 다음
            elif 'created_at' in scene and scene['created_at']:
                try:
                    timestamp = datetime.fromisoformat(scene['created_at'].replace('Z', '+00:00'))
                    return (1, timestamp.timestamp())
                except:
                    return (2, 0)
            # 둘 다 없으면 원래 순서 유지
            else:
                return (2, 0)

        return sorted(scenes, key=get_sort_key)

    def _continue_from_media(self, project_dir: Path, story_data: Dict, scene_media: list, aspect_ratio: str, target_minutes: int, is_test_mode: bool = False) -> Dict[str, Any]:
        """Continue video creation from approved media (images and/or videos)."""
        from tqdm import tqdm
        import time

        num_scenes = len(story_data['scenes'])
        title = story_data['title']
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title[:50])

        # This is the same logic as Step 2-B and beyond in create_from_title
        # Copy the relevant code from create_from_title starting from Step 2-B

        if is_test_mode:
            print(f"\n[테스트 모드 재개] 상세 나레이션 생성을 시작합니다...\n")
            print(f"  테스트 모드에서는 구조 개요만 생성되었으므로,")
            print(f"  이제 60분 분량의 상세 나레이션을 생성합니다.\n")
        else:
            print(f"\n 이미지 승인! 상세 나레이션 생성을 시작합니다...\n")
        print(f"{'='*70}")

        # Step 2-B: Generate detailed narrations (and save immediately)
        # Check if narrations already exist
        has_narrations = all(
            scene.get('narration') and len(scene.get('narration', '')) > 100
            for scene in story_data['scenes']
        )

        if has_narrations:
            print(f"\n[OK] 나레이션이 이미 존재합니다. 비디오 생성으로 넘어갑니다...\n")
            total_script = "\n\n".join([scene['narration'] for scene in story_data['scenes']])
        else:
            print(f"\n[Step 2-B] Generating Detailed Narrations for {num_scenes} Scenes...\n")

            # Calculate target per scene
            target_length = int(target_minutes * 60 * 11)
            target_per_scene = int(target_length / num_scenes)
            min_per_scene = int(target_per_scene * 0.8)

            with tqdm(total=num_scenes, desc="나레이션 생성 진행", position=0) as pbar_narration:
                for media_data in scene_media:
                    i = media_data['scene_num']
                    scene = media_data['scene']

                    # Create scene directory for this scene's files
                    scene_dir = project_dir / f"scene_{i:02d}"
                    scene_dir.mkdir(parents=True, exist_ok=True)

                    # Update scene_dir in media_data for later use
                    media_data['scene_dir'] = scene_dir

                    print(f"\n[Scene {i}/{num_scenes}] {scene['title']} - 상세 나레이션 생성 중...")

                    # Generate detailed narration for this scene
                    self._generate_single_scene_narration(story_data, scene, i, target_per_scene, min_per_scene)

                    # Save immediately after generation
                    scene_script_path = scene_dir / f"scene_{i:02d}_narration.txt"
                    with open(scene_script_path, 'w', encoding='utf-8') as f:
                        f.write(f"씬 {i}: {scene['title']}\n")
                        f.write(f"{'='*60}\n\n")
                        f.write(scene['narration'])

                    print(f"   [OK] 저장: {scene_script_path.name} ({len(scene['narration'])} chars)")
                    pbar_narration.update(1)

            # Update full script in story_data
            total_script = "\n\n".join([scene['narration'] for scene in story_data['scenes']])
            story_data['script'] = total_script

            # Re-save story metadata with full narrations
            self._save_story_metadata(story_data, project_dir, is_structure_only=False)
            print(f"\n 전체 스크립트 업데이트 완료: {len(total_script)} chars\n")

        # Step 2-C: Create videos from approved media (images and/or videos)
        print(f"\n{'='*70}")
        print(f"[Step 2-C] Creating Videos for {num_scenes} Scenes... (병렬 처리)")
        print(f"{'='*70}")
        step_start = time.time()

        # Parallel video generation (handles both images and videos)
        scene_videos = self._create_scene_videos_parallel(
            scene_media,
            aspect_ratio,
            num_scenes
        )

        step_elapsed = time.time() - step_start
        print(f"\n[OK] Step 2-C 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}\n")

        # Step 3: Combine all scenes
        print(f"\n{'='*70}")
        print(f"[Step 3] Combining All Scenes...")
        print(f"{'='*70}")
        step_start = time.time()

        from tqdm import tqdm
        with tqdm(total=1, desc="최종 비디오 결합", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            final_video_name = f"{safe_title}_full.mp4"
            final_video_path = project_dir / final_video_name
            self._combine_scenes(scene_videos, final_video_path)
            pbar.update(1)

        step_elapsed = time.time() - step_start
        print(f"[OK] Step 3 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}\n")

        # Update project status
        self._save_project_status(
            project_dir,
            status='complete',
            num_scenes=num_scenes,
            next_step='완료'
        )

        return {
            'status': 'complete',
            'project_dir': str(project_dir),
            'final_video': str(final_video_path),
            'script_length': len(total_script),
            'num_scenes': num_scenes
        }

    def create_from_title(
        self,
        title: str,
        output_dir: Path,
        num_scenes: int = 12,
        aspect_ratio: str = "16:9",
        seed: int = 12345,
        target_minutes: int = 60,
        test_mode: bool = False,
        test_continue: bool = False,
        scenario_only: bool = False,
        test_scene: int = None
    ) -> Dict[str, Any]:
        """
        Create a long-form story video from a title.

        Args:
            title: Story title/theme
            output_dir: Output directory for project
            num_scenes: Number of scenes (default: 12)
            aspect_ratio: Video aspect ratio
            seed: Random seed for image consistency (default: 12345)
            target_minutes: Target video duration in minutes (default: 60)
            test_mode: If True, only generate scenario without creating videos

        Returns:
            Dictionary with project info
        """
        import time

        # Start total timer
        total_start_time = time.time()

        print(f"\n" + "="*70)
        print(f"[Long-Form Story {'Scenario Test' if test_mode else 'Video Creation'}]")
        print(f"="*70)
        print(f"   Title: {title}")
        print(f"   Scenes: {num_scenes}")
        print(f"   Target Duration: {target_minutes} minutes")
        print(f"   Aspect Ratio: {aspect_ratio}")
        print(f"   Seed: {seed}")
        if test_mode:
            print(f"   Mode: TEST (시나리오만 생성)")
        print(f"="*70 + "\n")

        # Create project directory
        safe_title = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = output_dir / f"{safe_title}_{timestamp}"
        project_dir.mkdir(parents=True, exist_ok=True)

        print(f"Project Folder: {project_dir}\n")

        # Step 1: Generate full story script (includes internal evaluation at Stage 1.5)
        print(f"\n{'='*70}")
        print(f"[Step 1] Generating & Evaluating Scenario...")
        print(f"{'='*70}")
        step_start = time.time()

        with tqdm(total=1, desc="시나리오 생성 및 평가", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            story_data = self._generate_full_story(title, num_scenes, seed, target_minutes)
            pbar.update(1)

        step_elapsed = time.time() - step_start
        print(f"[OK] Step 1 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}")
        print(f"  (Total Elapsed: {self._format_elapsed_time(time.time() - total_start_time)})\n")

        # Check if evaluation failed during generation
        if story_data.get('evaluation_failed', False):
            evaluation = story_data.get('evaluation')

            print(f"\n{'='*70}")
            print(f"[Scenario Structure Evaluation - FAILED]")
            print(f"{'='*70}")
            print(f"제목: {story_data['title']}")
            print(f"장르: {story_data['genre']}")
            print(f"로그라인: {story_data.get('logline', 'N/A')}")
            print(f"\n평가 결과:")
            for criterion, result in evaluation['criteria'].items():
                print(f"- {criterion}: {result['score']}/{result['max_score']} - {result['comment']}")
            print(f"\n총점: {evaluation['total_score']:.1f}/10.0")
            print(f"{'='*70}")

            # Show first scene outline
            if story_data['scenes']:
                first_scene = story_data['scenes'][0]
                print(f"\n[첫 번째 씬 개요]")
                print(f"제목: {first_scene.get('title', 'N/A')}")
                print(f"내용: {first_scene.get('narration', 'N/A')[:500]}...")
                print(f"{'='*70}\n")

            # Save story metadata
            self._save_story_metadata(story_data, project_dir)

            # Save evaluation report
            eval_path = project_dir / "evaluation_failed.json"
            with open(eval_path, 'w', encoding='utf-8') as f:
                json.dump(evaluation, f, ensure_ascii=False, indent=2)

            # Save evaluation input (what was sent to GPT for evaluation)
            eval_input_path = project_dir / "evaluation_input.txt"
            with open(eval_input_path, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write("평가 시 GPT에게 보낸 컨텍스트\n")
                f.write("=" * 70 + "\n\n")
                f.write(evaluation.get('evaluation_input', '평가 입력 정보 없음'))

            # Save first scene script separately
            first_scene_path = project_dir / "first_scene_outline.txt"
            if story_data['scenes']:
                with open(first_scene_path, 'w', encoding='utf-8') as f:
                    first_scene = story_data['scenes'][0]
                    f.write(f"씬 번호: {first_scene.get('scene_number', 1)}\n")
                    f.write(f"제목: {first_scene.get('title', 'N/A')}\n")
                    f.write(f"시간대: {first_scene.get('time_of_day', 'N/A')}\n")
                    f.write(f"장소: {first_scene.get('location', 'N/A')}\n")
                    f.write(f"분위기: {first_scene.get('mood', 'N/A')}\n")
                    f.write(f"\n{'=' * 70}\n")
                    f.write(f"나레이션 (개요)\n")
                    f.write(f"{'=' * 70}\n\n")
                    f.write(first_scene.get('narration', 'N/A'))

            print(f"\n 시나리오 구조 평가 실패 (총점: {evaluation['total_score']:.1f}/10.0)")
            print(f"    컨셉/구조가 재미없어서 상세 나레이션 생성 생략")
            print(f"    생성된 구조는 저장되었습니다:")
            print(f"      - {project_dir / 'story_metadata.json'}")
            print(f"      - {project_dir / 'full_script.txt'}")
            print(f"      - {first_scene_path}")
            print(f"      - {eval_input_path}")
            print(f"      - {eval_path}")
            print(f"    동영상 제작 중단\n")

            # Save project status
            self._save_project_status(
                project_dir,
                status='evaluation_failed',
                reason='quality_threshold_not_met',
                score=evaluation['total_score'],
                next_step='재생성 필요 (점수 미달)'
            )

            return {
                'status': 'failed',
                'reason': 'quality_threshold_not_met',
                'score': evaluation['total_score'],
                'project_dir': str(project_dir),
                'evaluation': evaluation
            }

        # Evaluation passed - story_data has structure with outlines (200-300 chars per scene)
        evaluation = story_data.get('evaluation')

        # Save story structure (구조만, 상세 나레이션 아직 없음)
        self._save_story_metadata(story_data, project_dir, is_structure_only=True)

        print(f"\n{'='*70}")
        print(f"[Story Structure Generated] (상세 나레이션 전)")
        print(f"{'='*70}")
        print(f"Title: {story_data['title']}")
        print(f"Structure Outlines: {len(story_data['script'])} chars (개요만)")
        print(f"Scenes: {len(story_data['scenes'])}")
        print(f"Evaluation Score: {evaluation['total_score']:.1f}/10.0")
        print(f"{'='*70}\n")

        # Save evaluation report
        eval_path = project_dir / "evaluation_passed.json"
        with open(eval_path, 'w', encoding='utf-8') as f:
            json.dump(evaluation, f, ensure_ascii=False, indent=2)

        # If scenario_only mode, generate detailed narrations and stop
        if scenario_only:
            print(f"\n{'='*70}")
            print(f"[Scenario Only Mode] 상세 나레이션 생성을 시작합니다...")
            print(f"{'='*70}")
            step_start = time.time()

            # Calculate target per scene
            target_length = int(target_minutes * 60 * 11)
            target_per_scene = int(target_length / num_scenes)
            min_per_scene = int(target_per_scene * 0.8)

            with tqdm(total=num_scenes, desc="나레이션 생성 진행", position=0) as pbar:
                for i, scene in enumerate(story_data['scenes'], 1):
                    scene_start = time.time()
                    print(f"\n[Scene {i}/{num_scenes}] {scene['title']} - 상세 나레이션 생성 중...")
                    self._generate_single_scene_narration(story_data, scene, i, target_per_scene, min_per_scene)

                    # Save immediately
                    scene_dir = project_dir / f"scene_{i:02d}"
                    scene_dir.mkdir(exist_ok=True)
                    scene_script_path = scene_dir / f"scene_{i:02d}_narration.txt"
                    with open(scene_script_path, 'w', encoding='utf-8') as f:
                        f.write(f"씬 {i}: {scene['title']}\n")
                        f.write(f"{'='*60}\n\n")
                        f.write(scene['narration'])

                    scene_elapsed = time.time() - scene_start
                    print(f"   [OK] 저장: {scene_script_path.name} ({len(scene['narration'])} chars)")
                    print(f"    Scene {i} 소요시간: {self._format_elapsed_time(scene_elapsed)}")
                    pbar.update(1)

            # Update full script
            total_script = "\n\n".join([scene['narration'] for scene in story_data['scenes']])
            story_data['script'] = total_script

            # Re-save story metadata with full narrations
            self._save_story_metadata(story_data, project_dir, is_structure_only=False)

            # Save combined narration file
            combined_narration_path = project_dir / "full_narration_combined.txt"
            with open(combined_narration_path, 'w', encoding='utf-8') as f:
                f.write(f"제목: {story_data['title']}\n")
                f.write(f"{'='*70}\n\n")
                for i, scene in enumerate(story_data['scenes'], 1):
                    f.write(f"[씬 {i}] {scene['title']}\n")
                    f.write(f"{'-'*70}\n")
                    f.write(f"{scene['narration']}\n\n")

            print(f"[OK] 전체 나레이션 파일 저장: {combined_narration_path.name}")

            step_elapsed = time.time() - step_start
            print(f"\n[OK] 상세 나레이션 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}")
            print(f"  (Total Elapsed: {self._format_elapsed_time(time.time() - total_start_time)})")
            print(f"\n 전체 스크립트 완료: {len(total_script)} chars\n")

            # Save project status
            self._save_project_status(
                project_dir,
                status='scenario_complete',
                script_length=len(total_script),
                num_scenes=len(story_data['scenes']),
                score=evaluation['total_score'],
                next_step='이미지 생성 (--resume 사용)'
            )

            return {
                'status': 'scenario_complete',
                'project_dir': str(project_dir),
                'script_length': len(total_script),
                'num_scenes': len(story_data['scenes']),
                'score': evaluation['total_score'],
                'evaluation': evaluation
            }

        print(f"\n 이미지 생성을 시작합니다...\n")

        # Step 2-A: Generate all images first
        print(f"\n{'='*70}")
        print(f"[Step 2-A] Generating Images for {num_scenes} Scenes...")
        print(f"{'='*70}")
        step_start = time.time()

        scene_images = []
        previous_image_path = None
        character_descriptions = []

        with tqdm(total=num_scenes, desc="이미지 생성 진행", position=0) as pbar_images:
            for i, scene in enumerate(story_data['scenes'], 1):
                scene_start = time.time()
                print(f"\n{'='*70}")
                print(f"Scene {i}/{num_scenes}: {scene['title']}")
                print(f"{'='*70}")

                scene_dir = project_dir / f"scene_{i:02d}"
                scene_dir.mkdir(exist_ok=True)

                # Generate image for scene (with reference to previous scene)
                with tqdm(total=1, desc=f"   이미지 생성", leave=False, position=1) as pbar:
                    image_path, char_desc = self._generate_scene_image(
                        scene,
                        story_data,
                        scene_dir,
                        aspect_ratio,
                        i,
                        previous_image_path,
                        character_descriptions
                    )
                    previous_image_path = image_path
                    if char_desc:
                        character_descriptions.append(char_desc)
                        # Print character description for first scene
                        if i == 1:
                            print(f"\n[캐릭터 분석 완료]")
                            print(f"{'='*70}")
                            print(char_desc)
                            print(f"{'='*70}")
                            print(f" 이 캐릭터 설명이 다음 씬들에 전달됩니다.\n")
                    pbar.update(1)

                scene_images.append({
                    'scene': scene,
                    'image_path': image_path,
                    'scene_dir': scene_dir,
                    'scene_num': i
                })

                scene_elapsed = time.time() - scene_start
                print(f"[OK] Image {i} Complete: {image_path.name}")
                print(f" Scene {i} 소요시간: {self._format_elapsed_time(scene_elapsed)}")
                pbar_images.update(1)

                # Create YouTube thumbnail from first scene
                if i == 1:
                    print(f"\n[Generating YouTube Thumbnail]")
                    try:
                        thumbnail_path = self._create_youtube_thumbnail(
                            image_path,
                            story_data['title'],
                            project_dir
                        )
                        print(f"[OK] Thumbnail created: {thumbnail_path.name}\n")
                    except Exception as e:
                        self.logger.warning(f"Failed to create thumbnail: {e}")
                        print(f"[Warning] Thumbnail creation failed: {e}\n")

        step_elapsed = time.time() - step_start
        print(f"\n[OK] Step 2-A 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}")
        print(f"  (Total Elapsed: {self._format_elapsed_time(time.time() - total_start_time)})")

        # Show all generated images and ask for confirmation
        print(f"\n{'='*70}")
        print(f"  모든 이미지 생성 완료!")
        print(f"{'='*70}")
        print(f"\n생성된 이미지 목록:")
        for img_data in scene_images:
            print(f"  - Scene {img_data['scene_num']:02d}: {img_data['image_path']}")

        print(f"\n프로젝트 폴더: {project_dir}")

        # Save status after images are generated
        self._save_project_status(
            project_dir,
            status='images_generated',
            num_scenes=len(scene_images),
            next_step='사용자 확인  나레이션  비디오'
        )

        # If test mode, stop here (after images are generated)
        if test_mode and not test_continue:
            print(f"\n{'='*70}")
            print(f"[테스트 모드] 시나리오 + 이미지 생성 완료!")
            print(f"{'='*70}")
            print(f"    상세 나레이션 및 동영상 제작은 생략합니다.\n")

            # Update status for test mode
            self._save_project_status(
                project_dir,
                status='test_complete',
                num_scenes=len(scene_images),
                next_step='--resume로 비디오 제작 가능'
            )

            return {
                'status': 'test_complete',
                'project_dir': str(project_dir),
                'script_length': len(story_data['script']),
                'num_scenes': len(story_data['scenes']),
                'score': evaluation['total_score'],
                'evaluation': evaluation,
                'images': [str(img['image_path']) for img in scene_images]
            }

        # test_continue mode: auto-proceed
        if test_continue:
            print(f"\n[Test-Continue 모드] 이미지 생성 완료! 자동으로 계속 진행합니다...")
            user_input = 'y'
        else:
            print(f"\n이미지를 확인하시고 계속 진행하시겠습니까?")
            print(f"  - 계속하려면 'y' 또는 'yes' 입력")
            print(f"  - 중단하려면 'n' 또는 'no' 입력")
            user_input = input("\n 선택: ").strip().lower()

        if user_input not in ['y', 'yes']:
            print(f"\n{'='*70}")
            print(f"[중단] 사용자가 이미지 확인 후 중단을 선택했습니다.")
            print(f"{'='*70}")
            print(f"\n생성된 파일:")
            print(f"  - 시나리오: {project_dir / 'full_script.json'}")
            print(f"  - 이미지: {len(scene_images)}개 (scene_XX 폴더)")
            print(f"\n이미지를 수정하고 다시 실행하려면:")
            print(f"  python run.py --long-form \"{title}\"")
            print(f"\n또는 계속하려면:")
            print(f"  python run.py --resume \"{project_dir}\"")
            print(f"\n{'='*70}\n")

            # Save status - stopped at user confirmation
            self._save_project_status(
                project_dir,
                status='images_pending_confirmation',
                num_scenes=len(scene_images),
                next_step='--resume로 계속 진행 가능'
            )

            return {
                'status': 'images_only',
                'project_dir': str(project_dir),
                'num_scenes': len(scene_images),
                'script_length': len(json.dumps(story_data, ensure_ascii=False)),
                'images': [str(img['image_path']) for img in scene_images]
            }

        print(f"\n{'='*70}")
        print(f" 이미지 승인! 상세 나레이션 생성을 시작합니다...")
        print(f"{'='*70}")

        # Step 2-B: Generate detailed narrations (and save immediately)
        print(f"\n{'='*70}")
        print(f"[Step 2-B] Generating Detailed Narrations for {num_scenes} Scenes...")
        print(f"{'='*70}")
        step_start = time.time()

        # Calculate target per scene (use target_minutes from arguments)
        target_length = int(target_minutes * 60 * 11)
        target_per_scene = int(target_length / num_scenes)
        min_per_scene = int(target_per_scene * 0.8)

        with tqdm(total=num_scenes, desc="나레이션 생성 진행", position=0) as pbar_narration:
            for img_data in scene_images:
                scene_start = time.time()
                i = img_data['scene_num']
                scene = img_data['scene']

                print(f"\n[Scene {i}/{num_scenes}] {scene['title']} - 상세 나레이션 생성 중...")

                # Generate detailed narration for this scene
                self._generate_single_scene_narration(story_data, scene, i, target_per_scene, min_per_scene)

                # Save immediately after generation
                scene_script_path = img_data['scene_dir'] / f"scene_{i:02d}_narration.txt"
                with open(scene_script_path, 'w', encoding='utf-8') as f:
                    f.write(f"씬 {i}: {scene['title']}\n")
                    f.write(f"{'='*60}\n\n")
                    f.write(scene['narration'])

                scene_elapsed = time.time() - scene_start
                print(f"   [OK] 저장: {scene_script_path.name} ({len(scene['narration'])} chars)")
                print(f"    Scene {i} 소요시간: {self._format_elapsed_time(scene_elapsed)}")
                pbar_narration.update(1)

        # Update full script in story_data
        total_script = "\n\n".join([scene['narration'] for scene in story_data['scenes']])
        story_data['script'] = total_script

        # Re-save story metadata with full narrations
        self._save_story_metadata(story_data, project_dir, is_structure_only=False)

        # Save combined narration file
        combined_narration_path = project_dir / "full_narration_combined.txt"
        with open(combined_narration_path, 'w', encoding='utf-8') as f:
            f.write(f"제목: {story_data['title']}\n")
            f.write(f"{'='*70}\n\n")
            for i, scene in enumerate(story_data['scenes'], 1):
                f.write(f"[씬 {i}] {scene['title']}\n")
                f.write(f"{'-'*70}\n")
                f.write(f"{scene['narration']}\n\n")

        print(f"[OK] 전체 나레이션 파일 저장: {combined_narration_path.name}")

        step_elapsed = time.time() - step_start
        print(f"\n[OK] Step 2-B 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}")
        print(f"  (Total Elapsed: {self._format_elapsed_time(time.time() - total_start_time)})")
        print(f"\n 전체 스크립트 업데이트 완료: {len(total_script)} chars\n")

        # Step 2-C: Create videos from approved images (PARALLEL PROCESSING)
        print(f"\n{'='*70}")
        if test_scene:
            print(f"[Step 2-C] Creating Video for Scene {test_scene} (테스트 모드)")
            # Filter to only the requested scene
            scene_images = [img for img in scene_images if img['scene_num'] == test_scene]
            if not scene_images:
                print(f"Error: Scene {test_scene} not found")
                return {'status': 'error', 'message': f'Scene {test_scene} not found'}
            num_scenes = 1
        else:
            print(f"[Step 2-C] Creating Videos for {num_scenes} Scenes... (병렬 처리)")
        print(f"{'='*70}")
        step_start = time.time()

        # Parallel video generation
        scene_videos = self._create_scene_videos_parallel(
            scene_images,
            aspect_ratio,
            num_scenes
        )

        step_elapsed = time.time() - step_start
        print(f"\n[OK] Step 2-C 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}")
        print(f"  (Total Elapsed: {self._format_elapsed_time(time.time() - total_start_time)})\n")

        # If test_scene mode, return early
        if test_scene:
            print(f"\n{'='*70}")
            print(f"[TEST SCENE COMPLETE] Scene {test_scene} Video Created!")
            print(f"{'='*70}")
            print(f"Video: {scene_videos[0]}")
            print(f"{'='*70}\n")
            return {
                'status': 'test_scene_complete',
                'project_dir': str(project_dir),
                'scene_video': str(scene_videos[0]),
                'scene_num': test_scene
            }

        # Step 3: Combine all scenes
        print(f"\n{'='*70}")
        print(f"[Step 3] Combining All Scenes...")
        print(f"{'='*70}")
        step_start = time.time()

        with tqdm(total=1, desc="최종 비디오 결합", bar_format='{l_bar}{bar}| {elapsed}') as pbar:
            final_video_path = self._combine_scenes(
                scene_videos,
                project_dir / f"{safe_title}_full.mp4"
            )
            pbar.update(1)

        step_elapsed = time.time() - step_start
        print(f"\n[OK] Step 3 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}")
        print(f"  (Total Elapsed: {self._format_elapsed_time(time.time() - total_start_time)})\n")

        # Create summary
        summary = {
            "title": story_data['title'],
            "project_dir": str(project_dir),
            "num_scenes": num_scenes,
            "scene_videos": [str(v) for v in scene_videos],
            "final_video": str(final_video_path),
            "script_length": len(story_data['script']),
            "character_bible": story_data.get('character_bible', {}),
            "created_at": timestamp
        }

        # Save summary
        summary_path = project_dir / "project_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

        # Save final project status
        self._save_project_status(
            project_dir,
            status='completed',
            final_video=str(final_video_path),
            script_length=len(story_data['script']),
            next_step='완료 (모든 단계 완료)'
        )

        # Calculate total time
        total_elapsed = time.time() - total_start_time

        print(f"\n{'='*70}")
        print(f"[COMPLETE] Long-Form Story Video Creation Done!")
        print(f"{'='*70}")
        print(f"Project Folder: {project_dir}")
        print(f"Final Video: {final_video_path.name}")
        print(f"Script Length: {len(story_data['script'])} chars")
        print(f"Estimated Duration: {self._estimate_duration(story_data['script']):.1f} min")
        print(f"\n  TOTAL ELAPSED TIME: {self._format_elapsed_time(total_elapsed)}")
        print(f"{'='*70}\n")

        return summary

    def create_from_json(
        self,
        story_data: Dict[str, Any],
        output_dir: Path,
        aspect_ratio: str = "16:9",
        seed: int = 12345,
        images_zip: str = None,
        images_dir: str = None
    ) -> Dict[str, Any]:
        """
        Create a long-form story video from pre-generated JSON script.
        Skips LLM API calls entirely - useful for manual ChatGPT workflow.

        Args:
            story_data: Pre-generated story JSON from ChatGPT
            output_dir: Output directory for project
            aspect_ratio: Video aspect ratio (default: 16:9)
            seed: Random seed for image consistency
            images_zip: Optional path to ZIP file containing scene images
            images_dir: Optional path to directory containing scene images

        Note:
            If neither images_zip nor images_dir is provided, images will be
            generated automatically using DALL-E 3 based on visual_description
            in the story JSON.

        Returns:
            Dictionary with project info
        """
        import time

        # Start total timer
        total_start_time = time.time()

        print(f"\n" + "="*70)
        print(f"[From-Script Mode: Video Creation from Pre-Generated JSON]")
        print(f"="*70)
        print(f"   Title: {story_data['title']}")
        print(f"   Scenes: {len(story_data['scenes'])}")
        print(f"   Aspect Ratio: {aspect_ratio}")
        print(f"   Seed: {seed}")
        print(f"="*70 + "\n")

        # Create project directory
        title = story_data['title']
        safe_title = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in title)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        project_dir = output_dir / f"{safe_title}_{timestamp}"
        project_dir.mkdir(parents=True, exist_ok=True)

        print(f"Project Folder: {project_dir}\n")

        # Save this as the last project
        self._save_last_project(project_dir)

        # Add script to story_data if not present
        if 'script' not in story_data:
            # Combine all narrations
            all_narrations = [scene.get('narration', '') for scene in story_data['scenes']]
            story_data['script'] = '\n\n'.join(all_narrations)

        # Save story metadata
        self._save_story_metadata(story_data, project_dir)

        # Save project status
        self._save_project_status(
            project_dir,
            status='from_script_started',
            next_step='이미지 생성 시작'
        )

        num_scenes = len(story_data['scenes'])

        # Step 1: Generate Images (Same as normal flow)
        print(f"\n{'='*70}")
        print(f"[Step 1] Generating Images...")
        print(f"{'='*70}")
        step_start = time.time()

        # Determine image dimensions based on aspect ratio
        if aspect_ratio == "16:9":
            width, height = 1024, 576
        elif aspect_ratio == "1:1":
            width, height = 1024, 1024
        else:  # 9:16
            width, height = 576, 1024

        # Create images directory
        images_dir = project_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        # Extract images from ZIP file if provided
        if images_zip:
            import zipfile

            zip_path = Path(images_zip)
            if zip_path.exists():
                print(f"   [*] ZIP 파일에서 이미지 추출 중...")
                print(f"   From: {zip_path.absolute()}")
                print(f"   To: {images_dir.absolute()}")

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Extract all files
                    zip_ref.extractall(images_dir)

                    # Count extracted images
                    extracted_files = list(images_dir.glob("scene_*_image.png"))
                    print(f"   [OK] {len(extracted_files)}개 이미지 추출 완료")
            else:
                self.logger.warning(f"Images ZIP file not found: {zip_path}")

        # Copy images from user-specified directory if provided
        if images_dir and not images_zip:
            import shutil

            user_images_dir = Path(images_dir)
            if user_images_dir.exists() and user_images_dir.is_dir():
                print(f"   [*] 이미지 디렉토리에서 복사 중...")
                print(f"   From: {user_images_dir.absolute()}")

                # Use the project images_dir variable for destination
                project_images_dir = project_dir / "images"
                print(f"   To: {project_images_dir.absolute()}")

                # Find all scene images in the user directory
                scene_images_found = list(user_images_dir.glob("scene_*_image.png"))

                if scene_images_found:
                    for src_path in scene_images_found:
                        dest_path = project_images_dir / src_path.name
                        shutil.copy2(src_path, dest_path)
                    print(f"   [OK] {len(scene_images_found)}개 이미지 복사 완료")
                else:
                    self.logger.warning(f"No scene images found in: {user_images_dir}")
            else:
                self.logger.warning(f"Images directory not found: {user_images_dir}")

        scene_images = []
        previous_image_path = None
        character_descriptions = []

        # Check if images already exist in project folder OR workspace root
        # (workspace root = where story.json is located for user-generated images)
        workspace_images_dir = Path.cwd() / "images"

        existing_images = []
        images_exist = True
        images_source = None

        # First check project folder
        for i in range(1, num_scenes + 1):
            expected_image_path = images_dir / f"scene_{i:02d}_image.png"
            if expected_image_path.exists():
                existing_images.append(expected_image_path)
            else:
                images_exist = False
                break

        if images_exist and len(existing_images) == num_scenes:
            images_source = images_dir
        else:
            # Check workspace root (for user-downloaded images from ChatGPT)
            existing_images = []
            images_exist = True
            for i in range(1, num_scenes + 1):
                expected_image_path = workspace_images_dir / f"scene_{i:02d}_image.png"
                if expected_image_path.exists():
                    existing_images.append(expected_image_path)
                else:
                    images_exist = False
                    break

            if images_exist and len(existing_images) == num_scenes:
                images_source = workspace_images_dir
                # Copy images to project folder
                print(f"   [*] 워크스페이스에서 이미지를 복사합니다...")
                print(f"   From: {workspace_images_dir.absolute()}")
                print(f"   To: {images_dir.absolute()}")
                for src_path in existing_images:
                    dest_path = images_dir / src_path.name
                    import shutil
                    shutil.copy2(src_path, dest_path)
                images_source = images_dir
                existing_images = [images_dir / f"scene_{i:02d}_image.png" for i in range(1, num_scenes + 1)]

        if images_exist and len(existing_images) == num_scenes:
            # All images exist - skip generation
            print(f"   [OK] 기존 이미지 발견! 이미지 생성을 건너뜁니다.")
            print(f"   위치: {images_dir.absolute()}")
            print(f"   총 {num_scenes}개 이미지")

            # Load existing images into scene_images
            for i, scene in enumerate(story_data['scenes'], 1):
                image_path = images_dir / f"scene_{i:02d}_image.png"
                scene_images.append({
                    'scene': scene,
                    'image_path': image_path,
                    'scene_dir': images_dir,
                    'scene_num': i
                })
        else:
            # Generate images
            print(f"   Using {self.image_provider.upper()} for image generation...")

            with tqdm(total=num_scenes, desc="이미지 생성 중", unit="scene") as pbar:
                for i, scene in enumerate(story_data['scenes'], 1):
                    # Use the proper scene image generation with consistency
                    # Pass images_dir instead of scene_dir for image storage
                    image_path, generated_character_descriptions = self._generate_scene_image(
                        scene=scene,
                        story_data=story_data,
                        scene_dir=images_dir,  # Save all images in one folder
                        aspect_ratio=aspect_ratio,
                        scene_num=i,
                        previous_image_path=previous_image_path,
                        character_descriptions=character_descriptions if i > 1 else None
                    )

                    # Accumulate character descriptions for consistency
                    if i == 1 and generated_character_descriptions:
                        character_descriptions = generated_character_descriptions

                    previous_image_path = image_path

                    scene_images.append({
                        'scene': scene,
                        'image_path': image_path,
                        'scene_dir': images_dir,
                        'scene_num': i
                    })

                    pbar.update(1)

        step_elapsed = time.time() - step_start
        print(f"\n[OK] Step 1 완료 - 소요시간: {self._format_elapsed_time(step_elapsed)}")
        print(f"  (Total Elapsed: {self._format_elapsed_time(time.time() - total_start_time)})")

        # Show image location and ask for confirmation
        print(f"\n{'='*70}")
        print(f"[*] 이미지 확인")
        print(f"{'='*70}")
        print(f"생성된 이미지: {images_dir.absolute()}")
        print(f"총 {num_scenes}개 이미지가 생성되었습니다.")
        print(f"\n이미지를 확인하신 후 계속 진행하시겠습니까?")

        # Ask user for confirmation
        while True:
            user_input = input("계속 진행 (y/yes) / 중단 (n/no): ").strip().lower()
            if user_input in ['y', 'yes', '계속']:
                print("\n[OK] 계속 진행합니다...\n")
                break
            elif user_input in ['n', 'no', '중단']:
                print("\n[STOP] 사용자가 중단했습니다.")
                print(f"프로젝트 폴더: {project_dir}")
                return {
                    'project_dir': str(project_dir),
                    'status': 'stopped_by_user',
                    'images_generated': num_scenes,
                    'images_dir': str(images_dir)
                }
            else:
                print("y 또는 n을 입력해주세요.")

        # Save status
        self._save_project_status(
            project_dir,
            status='images_generated',
            next_step='사용자 이미지 확인 대기'
        )

        # Convert scene_images to scene_media format (add media_type field)
        scene_media = []
        for img_data in scene_images:
            media_data = {
                'scene': img_data['scene'],
                'media_type': 'image',
                'media_path': img_data['image_path'],
                'image_path': img_data['image_path'],
                'video_path': None,
                'scene_dir': img_data['scene_dir'],
                'scene_num': img_data['scene_num']
            }
            scene_media.append(media_data)

        # Continue from Step 2 (same as normal flow)
        return self._continue_from_media(
            project_dir,
            story_data,
            scene_media,
            aspect_ratio,
            target_minutes=60,
            is_test_mode=False
        )

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

    def _generate_full_story(self, title: str, num_scenes: int, seed: int, target_minutes: int) -> Dict[str, Any]:
        """Generate full story with characters and scenes using TWO-STAGE approach for long content."""

        # Calculate target length based on duration
        # For long-form content: aim for 40,000+ characters for 60+ minutes
        # Target: ~11 chars/sec for detailed narration (slower than typical TTS)
        target_length = int(target_minutes * 60 * 11)  # chars (40,000+ for 60 min)
        target_per_scene = int(target_length / num_scenes)  # 씬당 목표 글자수
        min_per_scene = int(target_per_scene * 0.8)  # 최소 80%

        print(f"   Target total: {target_length} chars")
        print(f"   Target per scene: {target_per_scene} chars")
        print(f"   Minimum per scene: {min_per_scene} chars")

        # STAGE 1: Generate story structure and scene outlines
        print(f"\n   [Stage 1/3] Generating story structure...")
        story_structure = self._generate_story_structure(title, num_scenes, seed, target_minutes, target_length, min_per_scene)

        # STAGE 1.5: Evaluate structure BEFORE generating detailed narrations
        print(f"\n   [Stage 2/3] Evaluating story structure...")

        # Prepare evaluation with structure only (first scene outline)
        temp_script = story_structure['scenes'][0]['narration'] if story_structure['scenes'] else ""
        story_structure['script'] = temp_script  # Temporary for evaluation

        evaluation = self._evaluate_scenario(story_structure)

        print(f"\n   Evaluation Score: {evaluation['total_score']:.1f}/10.0")
        for criterion, result in evaluation['criteria'].items():
            print(f"   - {criterion}: {result['score']}/{result['max_score']}")

        # Check if structure passes evaluation
        if evaluation['total_score'] < 8.0:
            print(f"\n    Structure evaluation failed ({evaluation['total_score']:.1f}/10.0)")
            print(f"    Stopping before detailed narration generation")

            # Return early with structure only
            story_structure['script'] = "\n\n".join([scene['narration'] for scene in story_structure['scenes']])
            story_structure['evaluation'] = evaluation
            story_structure['evaluation_failed'] = True
            return story_structure

        print(f"\n    Structure passed evaluation!")
        print(f"    상세 나레이션은 이미지 승인 후 생성됩니다.")

        # Return structure with outlines only (detailed narration will be generated after image approval)
        # Calculate temporary script from outlines
        total_script = "\n\n".join([scene['narration'] for scene in story_structure['scenes']])
        story_structure['script'] = total_script

        print(f"\n   [OK] Story Structure Complete")
        print(f"   Title: {story_structure['title']}")
        print(f"   Structure Outlines: {len(total_script)} chars (개요)")
        print(f"   Scenes: {len(story_structure['scenes'])}")

        story_structure['evaluation'] = evaluation
        story_structure['evaluation_failed'] = False
        return story_structure

    def _generate_story_structure(self, title: str, num_scenes: int, seed: int, target_minutes: int, target_length: int, min_per_scene: int) -> Dict[str, Any]:
        """STAGE 1: Generate story structure, characters, and scene outlines."""

        # Load user's custom prompt file
        base_prompt = self._load_prompt_template("long_form_prompt.txt")

        if base_prompt:
            # Use custom prompt as system prompt
            system_prompt = base_prompt.strip()

            # Variable substitution
            system_prompt = system_prompt.replace("{title}", title)
            system_prompt = system_prompt.replace("{num_scenes}", str(num_scenes))
            system_prompt = system_prompt.replace("{min_per_scene:,}", f"{min_per_scene:,}")

            # Build user prompt for STRUCTURE ONLY (not full narration yet)
            user_prompt = f"""제목: {title}

위 제목으로 **감동적이고 몰입감 있는** 롱폼 사연 스토리를 만들어주세요.

[Warning] 필수 요구사항:
- **첫 번째 씬(scene_1)에 반드시 다음 순서로 작성:**
  1) 강력한 훅 (극적인 대사/상황으로 시작)
  2) 기본 상황 설명
  3) **구독/좋아요 CTA (필수!)**: "사연 시작 전에 무료로 할 수 있는 구독과 좋아요 부탁드립니다. 사연봉투를 찾아 주신 모든 분들께 건강과 행복이 가득하시길 바랍니다. 오늘의 사연 시작하겠습니다."
  4) 본격적인 사연 전개 시작

- 감동적이고 현실적인 스토리 전개
- 인물의 감정과 내면 심리 풍부하게 표현
- 시청자가 공감할 수 있는 갈등과 반전
- 따뜻한 메시지와 여운 있는 결말

 기본 정보:
- 총 러닝타임: 약 {target_minutes}분
- 총 글자 수 목표: {target_length}자
- 총 씬 수: {num_scenes}개
- 이미지 시드: {seed}

[Warning] 씬 개요 작성:
각 씬의 narration은 **200-300자 개요**로 작성하되,
**scene_1은 반드시 훅 + CTA를 포함하여 400-500자로 작성**하세요.
(상세한 대사/묘사는 나중에 생성됨)

 **절대 중요**: 반드시 정확히 **{num_scenes}개 씬**을 만드세요!
- scene_list에 {num_scenes}개 항목
- scenes 배열에 {num_scenes}개 객체
- 누락하거나 적게 만들지 마세요!

 출력 형식 (JSON):
{{{{
  "title": "다듬어진 제목",
  "logline": "한 문장 로그라인",
  "genre": "장르",
  "time_period": "시대적 배경 (예: 1960년대, 1980년대, 2000년대 초반, 현대 등)",
  "character_bible": {{{{
    "protagonist": {{{{"name": "풀네임", "age": 나이, "appearance": "외형", "personality": "성격", "inner_world": "내면", "speech_style": "말투", "props": "소품"}}}},
    "helper": {{{{"name": "풀네임", "age": 나이, "appearance": "외형", "personality": "성격", "inner_world": "내면", "speech_style": "말투", "props": "소품"}}}},
    "antagonist": {{{{"name": "풀네임", "age": 나이, "appearance": "외형", "personality": "성격", "inner_world": "내면", "speech_style": "말투", "props": "소품"}}}},
    "sub_characters": [{{{{"name": "풀네임", "description": "설명"}}}}, ...],
    "space_tokens": ["배경1 시각 요소", "배경2 시각 요소", ...],
    "symbolic_objects": ["오브제1", "오브제2", ...],
    "color_mood": {{{{"fear": "색상", "doubt": "색상", "truth": "색상", "revenge": "색상", "catharsis": "색상"}}}}
  }}}},
  "synopsis": {{{{
    "prologue": "프롤로그 내용",
    "act1": "1막 내용",
    "act2": "2막 내용",
    "act3": "3막 내용",
    "climax": "클라이맥스",
    "ending": "결말",
    "theme": "핵심 메시지"
  }}}},
  "scene_list": [
    {{{{"scene_number": 1, "title": "씬1 제목", "time_of_day": "시간대", "summary": "사건 요약"}}}}
    {{{{"scene_number": 2, "title": "씬2 제목", "time_of_day": "시간대", "summary": "사건 요약"}}}}
    ...
    {{{{"scene_number": {num_scenes}, "title": "씬{num_scenes} 제목", "time_of_day": "시간대", "summary": "사건 요약"}}}}
  ],
  "scenes": [
    {{{{
      "scene_number": 1,
      "title": "씬 제목",
      "time_of_day": "시간대",
      "location": "장소",
      "mood": "분위기",
      "key_events": "핵심 사건들",
      "character_actions": "등장인물 행동",
      "emotional_arc": "감정 변화",
      "visual_description": "영어로 된 DALL-E 프롬프트 (seed:{seed} 포함)",
      "narration": "이 씬의 간단한 개요 (200-300자 - 상세한 나레이션은 나중에 생성됨)"
    }}}},
    {{{{
      "scene_number": 2,
      ...
    }}}},
    ...
    {{{{
      "scene_number": {num_scenes},
      ...
    }}}}
  ],
  "youtube_metadata": {{{{
    "video_title": "SEO 최적화 제목",
    "description": "설명",
    "tags": ["태그1", "태그2", ...],
    "chapter_timeline": ["00:00 씬1", "05:30 씬2", ...],
    "thumbnail_text_options": ["문구1", "문구2"],
    "thumbnail_prompt": "영어 썸네일 프롬프트 (seed:{seed})"
  }}}}
}}}}

JSON만 출력하세요:"""
        else:
            # Fallback to defaults
            system_prompt = f"""너는 '유튜브 오디오북실화극사연 드라마'를 제작하는 시나리오 작가 겸 연출가이다.
입력된 제목을 기반으로, 총 러닝타임 약 {target_minutes}분(텍스트 분량 약 {target_length}자)의 장편 드라마 시나리오를 작성한다.
서사적 리얼리즘과 감정선을 중시하며, 시각적으로 표현하기 좋은 씬을 구성한다.
각 씬은 최소 {min_per_scene}자 이상의 상세한 묘사가 필요하다."""

            user_prompt = f"""제목: {title}

위 제목으로 정확히 {target_length}자 분량의 장편 스토리를 만들어주세요.

[Warning] 중요: 각 씬은 최소 {min_per_scene}자 이상 작성해야 합니다. 짧게 쓰지 마세요!

[구조 요구사항]
- 총 씬 수: {num_scenes}개 (프롤로그~에필로그 포함)
- 감정선: 공포의심진실 폭로복수카타르시스 순서로 전개
- 시드(seed): {seed} (이미지 일관성 유지용)

[필수 출력 요소]
1. 로그라인: 한 문장으로 주제와 감정 핵심만 요약 (스포일러 금지)

2. 캐릭터 바이블:
   - 주인공: 이름, 연령, 외형, 성격, 내면, 말투, 주요 소품
   - 조력자: 동일 형식
   - 대립자: 동일 형식
   - 서브 인물: 최대 2명
   - 공간 토큰: 주요 배경의 시각 요소 상세 묘사
   - 반복 오브제: 상징적 소품 3~5개
   - 컬러 무드: 감정별 색상 톤 (예: 공포=청회색, 복수=보라빛)

3. 시나리오 개요:
   - 프롤로그
   - 전개 1~3막 (각 막의 주요 사건/감정 곡선/전환점)
   - 클라이맥스 및 결말
   - 테마 (핵심 메시지)

4. 씬 리스트 ({num_scenes}개):
   - 각 씬: 번호, 제목, 시간대(새벽/낮/밤), 주요 사건 요약

5. 장편 시나리오 (총 {target_length}자):
   - [Warning] 필수: 각 씬당 최소 {min_per_scene}자 이상 작성
   - 내레이션, 대사, 상황, 심리 묘사를 매우 상세하게 포함
   - 대화문과 내면 독백을 풍부하게 교차
   - 리듬감과 긴장감을 유지하되, 충분한 길이 확보
   - 후반부 카타르시스 제공
   - 장면 묘사를 구체적이고 상세하게 작성
   - 인물의 감정과 행동을 세밀하게 표현

6. 씬별 이미지 생성 프롬프트:
   - 각 씬당 1개
   - 영어로 작성 (DALL-E용)
   - 16:9 시네마틱 스타일
   - 동일 시드 {seed} 유지
   - 캐릭터의 비주얼 일관성 유지
   - 예시: "Jung-sim (gray cardigan, silver-rimmed glasses) opening the door at dawn, raindrops, low-key lighting, blue-grey tone, cinematic 16:9, seed:{seed}"

7. 유튜브용 메타데이터:
   - 영상 제목: SEO 최적화된 긴 문장형
   - 설명: 줄거리 요약 + 감정 키워드
   - 태그: 8~12개
   - 챕터 타임라인: 씬 제목 기준
   - 썸네일 문구: 2안 (최대 10자)
   - 썸네일 프롬프트: 시네마틱 포스터 스타일 (영어, seed:{seed})

[작성 규칙]
- 모든 인물공간의 비주얼 토큰은 전 씬에서 일관 유지
- 생생하지만 절제된 문체 사용
- 과도한 폭력/혐오 묘사는 비유로 처리
- 내레이션은 짧은 문장으로 리듬감 있게
- 엔딩은 감정적 해소 또는 역전의 완결감 필수

 출력 형식 (JSON):
{{
  "title": "다듬어진 제목",
  "logline": "한 문장 로그라인",
  "genre": "장르",
  "character_bible": {{
    "protagonist": {{"name": "이름", "age": 나이, "appearance": "외형", "personality": "성격", "inner_world": "내면", "speech_style": "말투", "props": "소품"}},
    "helper": {{"name": "이름", "age": 나이, "appearance": "외형", "personality": "성격", "inner_world": "내면", "speech_style": "말투", "props": "소품"}},
    "antagonist": {{"name": "이름", "age": 나이, "appearance": "외형", "personality": "성격", "inner_world": "내면", "speech_style": "말투", "props": "소품"}},
    "sub_characters": [{{"name": "이름", "description": "설명"}}, ...],
    "space_tokens": ["배경1 시각 요소", "배경2 시각 요소", ...],
    "symbolic_objects": ["오브제1", "오브제2", ...],
    "color_mood": {{"fear": "색상", "doubt": "색상", "truth": "색상", "revenge": "색상", "catharsis": "색상"}}
  }},
  "synopsis": {{
    "prologue": "프롤로그 내용",
    "act1": "1막 내용",
    "act2": "2막 내용",
    "act3": "3막 내용",
    "climax": "클라이맥스",
    "ending": "결말",
    "theme": "핵심 메시지"
  }},
  "scene_list": [
    {{"scene_number": 1, "title": "씬 제목", "time_of_day": "시간대", "summary": "사건 요약"}},
    ...
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "title": "씬 제목",
      "time_of_day": "시간대",
      "visual_description": "영어로 된 DALL-E 프롬프트",
      "narration": "한국어 나레이션/대사 (최소 {min_per_scene}자 - 매우 상세하게 작성)"
    }},
    ...
  ],
  "youtube_metadata": {{
    "video_title": "SEO 최적화 제목",
    "description": "설명",
    "tags": ["태그1", "태그2", ...],
    "chapter_timeline": ["00:00 씬1", "05:30 씬2", ...],
    "thumbnail_text_options": ["문구1", "문구2"],
    "thumbnail_prompt": "영어 썸네일 프롬프트 (seed:{seed})"
  }}
}}

JSON만 출력하세요:"""

        try:
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.95,  # Higher for more creativity
                max_tokens=8000,  # Structure only, not full narration
                response_format={"type": "json_object"}
            )

            story_json = response.choices[0].message.content.strip()
            story_data = json.loads(story_json)

            print(f"   [OK] Story Structure Generated")
            print(f"   Title: {story_data['title']}")
            print(f"   Genre: {story_data['genre']}")
            print(f"   Scenes: {len(story_data['scenes'])}")

            # Display character info
            if 'character_bible' in story_data:
                bible = story_data['character_bible']
                print(f"   Protagonist: {bible.get('protagonist', {}).get('name', 'N/A')}")
                print(f"   Helper: {bible.get('helper', {}).get('name', 'N/A')}")
                print(f"   Antagonist: {bible.get('antagonist', {}).get('name', 'N/A')}")

            return story_data

        except Exception as e:
            self.logger.error(f"Story structure generation failed: {e}")
            raise

    def _generate_single_scene_narration(self, story_data: Dict[str, Any], scene: Dict[str, Any], scene_num: int, target_per_scene: int, min_per_scene: int):
        """Generate detailed narration for a single scene."""
        try:
            i = scene_num
            # Prepare context
            context = f"""# 전체 스토리 정보

제목: {story_data['title']}
장르: {story_data['genre']}
로그라인: {story_data.get('logline', '')}

## 등장인물
{json.dumps(story_data.get('character_bible', {}), ensure_ascii=False, indent=2)}

## 전체 시나리오 개요
{json.dumps(story_data.get('synopsis', {}), ensure_ascii=False, indent=2)}

## 이 씬 정보
씬 번호: {scene['scene_number']}/{len(story_data['scenes'])}
제목: {scene['title']}
시간대: {scene.get('time_of_day', 'N/A')}
장소: {scene.get('location', 'N/A')}
분위기: {scene.get('mood', 'N/A')}
핵심 사건: {scene.get('key_events', '')}
등장인물 행동: {scene.get('character_actions', '')}
감정 변화: {scene.get('emotional_arc', '')}
현재 개요: {scene['narration']}

## 전후 씬 (참고)"""

            # Add previous scene context
            if i > 1:
                prev_scene = story_data['scenes'][i-2]
                context += f"\n이전 씬: {prev_scene['title']}"

            # Add next scene context
            if i < len(story_data['scenes']):
                next_scene = story_data['scenes'][i]
                context += f"\n다음 씬: {next_scene['title']}"

            # Generate detailed narration (different for scene 1)
            if scene_num == 1:
                # Scene 1: Must include hook + CTA
                narration_prompt = f"""위 씬을 **{target_per_scene}자 이상의 매우 상세한 나레이션**으로 작성하세요.

[Warning] 첫 번째 씬 필수 구조:
1) **강력한 훅** (30초-1분): 가장 극적인 대사나 상황으로 시작
2) 기본 상황 설명 및 인물 소개
3) **구독/좋아요 CTA (필수!)**:
   "사연 시작 전에 무료로 할 수 있는 구독과 좋아요 부탁드립니다. 사연봉투를 찾아 주신 모든 분들께 건강과 행복이 가득하시길 바랍니다. 오늘의 사연 시작하겠습니다."
4) 본격적인 사연 전개 시작

[Warning] 일반 요구사항:
- 최소 {min_per_scene}자, 목표 {target_per_scene}자 (더 길어도 좋음!)
- 대사는 반드시 **풀네임** 사용 (이니셜/약칭 금지)
- 행동, 소리, 감정을 구체적으로 묘사
- 내면 독백과 대화를 풍부하게
- 장면의 시각적/청각적 요소 상세히 표현
- 감정 변화를 세밀하게 표현
- 구어체 말투 사용 ("~했습니다", "~했어요", "~했죠" 등)

JSON 형식으로 출력:
{{
  "narration": "상세한 나레이션 (최소 {min_per_scene}자, 반드시 CTA 포함)",
  "actual_length": 글자수
}}"""
            else:
                # Other scenes: Normal narration
                narration_prompt = f"""위 씬을 **{target_per_scene}자 이상의 매우 상세한 나레이션**으로 작성하세요.

[Warning] 필수 요구사항:
- 최소 {min_per_scene}자, 목표 {target_per_scene}자 (더 길어도 좋음!)
- 대사는 반드시 **풀네임** 사용 (이니셜/약칭 금지)
- 행동, 소리, 감정을 구체적으로 묘사
- 내면 독백과 대화를 풍부하게
- 장면의 시각적/청각적 요소 상세히 표현
- 감정 변화를 세밀하게 표현
- 구어체 말투 사용 ("~했습니다", "~했어요", "~했죠" 등)

JSON 형식으로 출력:
{{
  "narration": "상세한 나레이션 (최소 {min_per_scene}자)",
  "actual_length": 글자수
}}"""

            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "너는 유튜브 오디오북실화극사연 드라마 전문 시나리오 작가이다. 매우 상세하고 감정선이 풍부한 나레이션을 작성한다."},
                    {"role": "user", "content": context + "\n\n" + narration_prompt}
                ],
                temperature=0.85,
                max_tokens=6000,  # Allow long narration per scene
                response_format={"type": "json_object"}
            )

            narration_json = response.choices[0].message.content.strip()
            narration_data = json.loads(narration_json)

            # Update scene with detailed narration
            scene['narration'] = narration_data['narration']
            actual_length = len(narration_data['narration'])

            self.logger.info(f"Scene {i} detailed narration generated: {actual_length} chars")

        except Exception as e:
            self.logger.error(f"Failed to generate narration for scene {i}: {e}")
            # Keep the original outline as fallback

    def _evaluate_scenario(self, story_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate scenario quality using the evaluation criteria from the prompt.
        Returns evaluation results with scores and comments.
        """

        # Prepare scenario text for evaluation
        scenario_text = f"""# 시나리오 정보

제목: {story_data['title']}
장르: {story_data['genre']}
로그라인: {story_data.get('logline', 'N/A')}

## 캐릭터
{json.dumps(story_data.get('character_bible', {}), ensure_ascii=False, indent=2)}

## 시나리오 개요
{json.dumps(story_data.get('synopsis', {}), ensure_ascii=False, indent=2)}

## 씬 구조
총 {len(story_data['scenes'])}개 씬

{chr(10).join([f"씬 {i+1}: {scene['title']}" for i, scene in enumerate(story_data['scenes'])])}

## 전체 시나리오 (샘플 - 처음 3개 씬)
{chr(10).join([f"[씬 {i+1}] {scene['title']}{chr(10)}{scene['narration']}{chr(10)}" for i, scene in enumerate(story_data['scenes'][:3])])}

전체 스크립트 길이: {len(story_data['script'])} 자
"""

        # Load evaluation prompt from long_form_prompt.txt
        evaluation_system_prompt = """너는 시니어(60세+) 타겟 실화극사연드라마 전문 평가자이다.

**시니어 공감 + 충격적 재미**가 최우선이다. 진부한 감동물은 즉시 탈락.

## 평가 기준 (Senior Entertainment Engine)

| 항목 | 기준 | 배점 | 통과 기준 |
|------|------|------|----------|
|  컨셉 독창성 | 진부하지 않은 소재/해석 | 2.0 | **1.5 이상 필수** |
|  리듬 다이내믹 | 지루하지 않은 전개 | 1.5 | 1.0 이상 |
|  구조 완결성 | 12씬 완성도 | 0.5 | 0.3 이상 |
|  음색 분리도 | 캐릭터별 차별화 | 0.5 | 0.3 이상 |
|  감정 리얼리티 | 시니어 공감 + 카타르시스 | 2.0 | **1.5 이상 필수** |
|  반전 효과 | 예측 불가능하고 현실적 | 2.0 | **1.5 이상 필수** |
|  여운메시지성 | 인생 통찰 (교훈 강요 아님) | 1.5 | 1.0 이상 |

**평가 철학**
- **시니어가 공감 못하면 즉시 낮은 점수**
- 진부한 효도/감동 이야기  컨셉 1.0 이하
- 예측 가능한 전개  반전 1.0 이하
- 60세+ 공감 안 되거나 교훈 강요  감정 1.0 이하
- 핵심 3개 (컨셉감정반전) 평균 1.4점 이상이면 통과 가능
- 현실적이면서 충격적이어야 함
- **총 8.0 미만은 고루한 시나리오로 판단**

**판정**
- 8.0 이상   **합격**
- 8.0 미만   **폐기 - 재미 부족**

## 추가 체크사항
- [ ] 5막 감정 상승반전 존재
- [ ] 씬들의 감정 변화
- [ ] 무음 또는 감정 정점 표현
- [ ] 정보가 행동소리사물로 제시
- [ ] 대사 머리표 = 풀네임
- [ ] Reverse Hook 존재
- [ ] 여운 엔딩 ('빛소리숨' 중 하나)

JSON 형식으로 평가 결과를 출력하시오:
{
  "criteria": {
    "컨셉 독창성": {"score": 0.0, "max_score": 2.0, "comment": "평가 내용"},
    "리듬 다이내믹": {"score": 0.0, "max_score": 1.5, "comment": "평가 내용"},
    "구조 완결성": {"score": 0.0, "max_score": 0.5, "comment": "평가 내용"},
    "음색 분리도": {"score": 0.0, "max_score": 0.5, "comment": "평가 내용"},
    "감정 리얼리티": {"score": 0.0, "max_score": 2.0, "comment": "평가 내용"},
    "반전 효과": {"score": 0.0, "max_score": 2.0, "comment": "평가 내용"},
    "여운메시지성": {"score": 0.0, "max_score": 1.5, "comment": "평가 내용"}
  },
  "total_score": 0.0,
  "passed": false,
  "overall_comment": "종합 평가"
}
"""

        evaluation_user_prompt = f"""다음 시나리오를 평가해주세요:

{scenario_text}

위 평가 기준에 따라 각 항목별로 상세히 평가하고, JSON 형식으로 결과를 출력하세요."""

        try:
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": evaluation_system_prompt},
                    {"role": "user", "content": evaluation_user_prompt}
                ],
                temperature=0.3,  # Lower temperature for consistent evaluation
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            evaluation_json = response.choices[0].message.content.strip()
            evaluation = json.loads(evaluation_json)

            # Ensure total_score is calculated
            if 'total_score' not in evaluation or evaluation['total_score'] == 0:
                total = sum(criteria['score'] for criteria in evaluation['criteria'].values())
                evaluation['total_score'] = round(total, 1)

            # Ensure passed flag is set
            evaluation['passed'] = evaluation['total_score'] >= 8.0

            # Save the evaluation input for debugging
            evaluation['evaluation_input'] = f"""[System Prompt]
{evaluation_system_prompt}

[User Prompt]
{evaluation_user_prompt}"""

            self.logger.info(f"Scenario evaluation: {evaluation['total_score']}/10.0")

            return evaluation

        except Exception as e:
            self.logger.error(f"Scenario evaluation failed: {e}")
            # Return a default failing evaluation
            return {
                'criteria': {
                    '컨셉 독창성': {'score': 0.0, 'max_score': 2.0, 'comment': '평가 실패'},
                    '리듬 다이내믹': {'score': 0.0, 'max_score': 1.5, 'comment': '평가 실패'},
                    '구조 완결성': {'score': 0.0, 'max_score': 0.5, 'comment': '평가 실패'},
                    '음색 분리도': {'score': 0.0, 'max_score': 0.5, 'comment': '평가 실패'},
                    '감정 리얼리티': {'score': 0.0, 'max_score': 2.0, 'comment': '평가 실패'},
                    '반전 효과': {'score': 0.0, 'max_score': 2.0, 'comment': '평가 실패'},
                    '여운메시지성': {'score': 0.0, 'max_score': 1.5, 'comment': '평가 실패'}
                },
                'total_score': 0.0,
                'passed': False,
                'overall_comment': f'평가 중 오류 발생: {str(e)}',
                'error': str(e)
            }

    def _get_period_visual_details(self, time_period: str) -> str:
        """Get visual details for specific time period."""

        # Korean historical periods mapping
        period_map = {
            "1960": "1960s Korea: Traditional hanok houses, black-and-white TV era, simple clothing, hanbok for special occasions",
            "1970": "1970s Korea: Economic development era, vinyl records, bell-bottom pants, analog technology",
            "1980": "1980s Korea: Cassette tapes, colorful fashion, perms, boombox radios, arcade games",
            "1990": "1990s Korea: Beepers, early mobile phones, grunge fashion, CD players, internet cafes beginning",
            "2000": "2000s Korea: Flip phones, digital cameras, early smartphones, K-pop emergence, modern fashion",
            "2010": "2010s Korea: Smartphones everywhere, social media, contemporary fashion, modern technology",
            "현대": "Modern-day Korea: Latest smartphones, contemporary fashion, modern architecture, current technology",
            "현대": "Contemporary Korea 2020s: Latest technology, modern minimalist aesthetics, smart devices",
        }

        # Find matching period
        for key, description in period_map.items():
            if key in time_period:
                return description

        # Default to modern if not specified
        return "Modern-day Korea: Contemporary setting with current fashion and technology"

    def _sanitize_visual_description(self, description: str) -> str:
        """Remove potentially violating content from visual description."""
        import re

        # Remove violent/negative words that might trigger filters
        sensitive_words = [
            # Violence
            r'\b(폭력|폭행|구타|때리|치|죽|살해|학대|고문|피|상처|부상)\w*',
            r'\b(violence|attack|hit|kill|murder|abuse|torture|blood|wound|injury)\w*',
            # Sexual
            r'\b(성적|섹시|야한|노출|벗|nude|sexy|revealing)\w*',
            # Drugs
            r'\b(마약|약물|drug)\w*',
            # Weapons
            r'\b(총|칼|무기|weapon|gun|knife)\w*',
            # Death
            r'\b(시체|corpse|dead body)\w*',
            # Self-harm
            r'\b(자해|self-harm)\w*',
        ]

        sanitized = description
        for pattern in sensitive_words:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)

        # Replace negative emotions with neutral descriptions
        replacements = {
            r'\b무시\w*': '대화하는',
            r'\b증오\w*': '감정적인',
            r'\b분노\w*': '진지한',
            r'\b복수\w*': '결단하는',
            r'\b최후\w*': '마지막 장면',
            r'\bhate\w*': 'emotional',
            r'\banger\w*': 'serious',
            r'\brevenge\w*': 'determined',
        }

        for pattern, replacement in replacements.items():
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        # Clean up extra spaces
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()

        return sanitized

    def _generate_image_huggingface(self, prompt: str, width: int = 1024, height: int = 1024) -> Image.Image:
        """Generate image using Hugging Face Inference API."""
        if not self.hf_api_key:
            raise ValueError("HUGGINGFACE_API_KEY environment variable not set")

        config = self.config.get("ai", {}).get("image_generation", {}).get("huggingface", {})
        model = config.get("model", "stabilityai/stable-diffusion-xl-base-1.0")

        # Hugging Face Inference API endpoint
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        headers = {"Authorization": f"Bearer {self.hf_api_key}"}

        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": config.get("num_inference_steps", 30),
                "guidance_scale": config.get("guidance_scale", 7.5),
                "width": width,
                "height": height
            }
        }

        # Retry logic for model loading
        max_retries = 3
        retry_delay = 10

        for attempt in range(max_retries):
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=60)

                if response.status_code == 503:
                    # Model is loading
                    self.logger.info(f"Model is loading, waiting {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                    print(f"   [Info] Model loading, waiting {retry_delay}s...")
                    import time
                    time.sleep(retry_delay)
                    continue

                response.raise_for_status()

                # Return PIL Image
                img = Image.open(io.BytesIO(response.content))
                # Apply EXIF orientation to fix rotated images
                img = ImageOps.exif_transpose(img)
                return img

            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to generate image with Hugging Face: {e}")
                self.logger.warning(f"Attempt {attempt + 1} failed, retrying...")
                import time
                time.sleep(retry_delay)

        raise Exception("Failed to generate image after all retries")

    def _generate_image_replicate(self, prompt: str, width: int = 1024, height: int = 1024) -> Image.Image:
        """Generate image using Replicate API."""
        if not self.replicate_api_token:
            raise ValueError("REPLICATE_API_TOKEN environment variable not set")

        import replicate

        config = self.config.get("ai", {}).get("image_generation", {}).get("replicate", {})
        model_name = config.get("model", "black-forest-labs/flux-schnell")

        try:
            # Run the model
            output = replicate.run(
                model_name,
                input={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                    "num_outputs": 1,
                }
            )

            # Get the image URL from output
            if isinstance(output, list) and len(output) > 0:
                image_url = output[0]
            else:
                image_url = output

            # Download the image
            import requests
            response = requests.get(image_url)
            response.raise_for_status()

            # Return PIL Image
            img = Image.open(io.BytesIO(response.content))
            # Apply EXIF orientation to fix rotated images
            img = ImageOps.exif_transpose(img)
            return img

        except Exception as e:
            raise Exception(f"Failed to generate image with Replicate: {e}")

    def _generate_image_imagen3(self, prompt: str, width: int = 1024, height: int = 1024) -> Image.Image:
        """Generate image using Google Imagen 3."""
        if not self.google_genai:
            raise ValueError("Google Generative AI not initialized. Set GOOGLE_API_KEY environment variable.")

        try:
            # Imagen 3는 1:1 (1024x1024) 비율만 지원
            # 다른 비율이 요청되면 1024x1024로 생성하고 크롭/리사이즈
            target_width, target_height = width, height
            gen_size = "1024x1024"  # Imagen 3 기본 크기

            # Generate image using Imagen 3
            model = self.google_genai.GenerativeModel("imagen-3.0-generate-001")

            # Imagen 3 생성 (최대 2048자 프롬프트)
            if len(prompt) > 2048:
                prompt = prompt[:2045] + "..."

            print(f"   Generating with Imagen 3...")
            result = model.generate_images(
                prompt=prompt,
                number_of_images=1,
                safety_filter_level="block_only_high",  # 낮은 필터 레벨
                person_generation="allow_all",  # 사람 생성 허용
                aspect_ratio="1:1"  # 1024x1024
            )

            if not result.images:
                raise Exception("No images generated from Imagen 3")

            # Convert to PIL Image
            imagen_image = result.images[0]

            # Imagen 3 이미지는 PIL Image로 변환
            # imagen_image._pil_image 사용
            img = imagen_image._pil_image

            # 크기 조정이 필요한 경우
            if target_width != 1024 or target_height != 1024:
                # 종횡비 유지하며 리사이즈
                img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)

            return img

        except Exception as e:
            raise Exception(f"Failed to generate image with Imagen 3: {e}")

    def _generate_scene_image(
        self,
        scene: Dict[str, Any],
        story_data: Dict[str, Any],
        scene_dir: Path,
        aspect_ratio: str,
        scene_num: int,
        previous_image_path: Path = None,
        character_descriptions: List[str] = None
    ) -> tuple:
        """Generate image for a scene with visual consistency."""

        # Map aspect ratio to size
        size_map = {
            "9:16": "1024x1792",
            "16:9": "1792x1024",
            "1:1": "1024x1024"
        }
        dalle_size = size_map.get(aspect_ratio, "1792x1024")

        # Extract character consistency from previous scenes
        consistency_note = ""
        if scene_num == 1:
            # First scene: establish character visuals
            consistency_note = """
CRITICAL: Establish consistent character appearance for all following scenes.
Include detailed physical descriptions that can be referenced later."""
        elif character_descriptions:
            # Use accumulated character descriptions for consistency
            consistency_note = f"""
 ABSOLUTE CRITICAL - CHARACTER CONSISTENCY 
You MUST use these EXACT character descriptions from Scene 1:

{chr(10).join(character_descriptions)}

MANDATORY REQUIREMENTS:
- SAME EXACT faces, hair styles, clothing as described above
- SAME EXACT age appearance
- SAME EXACT body types
- DO NOT change any visual details
- These are the SAME PEOPLE appearing again
- Korean people (한국인) as established

This is Scene {scene_num} with the SAME CHARACTERS. Keep them IDENTICAL."""

        # Get visual description (fallback to image_prompt if not available)
        visual_desc = scene.get('visual_description', scene.get('image_prompt', ''))

        # Sanitize visual description for DALL-E content policy
        sanitized_visual = self._sanitize_visual_description(visual_desc)

        # Get time period from story data
        time_period = story_data.get('time_period', '현대')

        # Map time period to visual elements
        period_details = self._get_period_visual_details(time_period)

        # Get image style from config
        image_config = self.config.get("ai", {}).get("image_generation", {})
        image_style = image_config.get("style", "webtoon")

        # Define style specifications
        style_specs = {
            "webtoon": """
STYLE: Korean Webtoon (�툰) Art Style
- Clean, bold line art with clear outlines
- Vibrant, saturated colors typical of Korean webtoons
- Expressive eyes and facial features (manhwa style)
- Semi-realistic proportions with stylized details
- Dramatic lighting and shading for mood
- Digital painting aesthetic
- Similar to popular webtoons like "True Beauty", "Tower of God"
- Professional Korean digital comic art quality""",

            "anime": """
STYLE: High-Quality Anime Art Style
- Japanese anime/manga aesthetic
- Large expressive eyes, detailed hair
- Cel-shaded or soft-shaded coloring
- Dynamic angles and composition
- Anime studio quality (similar to Kyoto Animation, ufotable)""",

            "realistic": """
STYLE: Photorealistic
- Natural, realistic human features
- Photographic quality lighting
- Authentic skin textures and details
- Cinematic, film-like composition
- Like a movie still or professional photography""",

            "digital_art": """
STYLE: Semi-Realistic Digital Art
- Painterly digital illustration
- Blend of realism and artistic stylization
- Rich colors and professional digital painting techniques
- Concept art quality"""
        }

        style_instruction = style_specs.get(image_style, style_specs["webtoon"])

        # Create DALL-E prompt with consistency and style
        dalle_prompt = f"""{sanitized_visual}

{consistency_note}

CRITICAL REQUIREMENTS:
- All characters MUST be Korean people (한국인)
- TIME PERIOD: {time_period} - {period_details}
- Korean facial features, Korean names in the story
- Korean setting and cultural context
- Natural, relaxed facial expressions (NOT stiff or frozen)
- Authentic human emotions showing through faces
- Candid, lifelike poses (avoid artificial/posed looks)

{style_instruction}

CONSISTENCY: All scenes MUST use the EXACT SAME art style. Keep visual consistency across all images.
Genre aesthetic: {story_data['genre']}
Important: Create a visually striking scene with NATURAL, EXPRESSIVE faces that match the story mood and TIME PERIOD."""

        # Generate image using configured provider
        if self.image_provider == "replicate" and self.replicate_api_token:
            print(f"   Using Replicate for image generation...")
            # Parse size for Replicate
            width, height = map(int, dalle_size.split('x'))
            img = self._generate_image_replicate(dalle_prompt, width, height)

            image_path = scene_dir / f"scene_{scene_num:02d}_image.png"
            img.save(image_path)
        elif self.image_provider == "huggingface" and self.hf_api_key:
            print(f"   Using Hugging Face for image generation...")
            # Parse size for Hugging Face
            width, height = map(int, dalle_size.split('x'))
            img = self._generate_image_huggingface(dalle_prompt, width, height)

            image_path = scene_dir / f"scene_{scene_num:02d}_image.png"
            img.save(image_path)
        elif self.image_provider == "imagen3" and self.google_genai:
            print(f"   Using Google Imagen 3 for image generation...")
            # Parse size for Imagen 3
            width, height = map(int, dalle_size.split('x'))
            img = self._generate_image_imagen3(dalle_prompt, width, height)

            image_path = scene_dir / f"scene_{scene_num:02d}_image.png"
            img.save(image_path)
        else:
            # Use OpenAI DALL-E (original)
            print(f"   Using OpenAI DALL-E for image generation...")
            try:
                response = self.client.images.generate(
                    model="dall-e-3",
                    prompt=dalle_prompt,
                    size=dalle_size,
                    quality="standard",
                    n=1,
                )
            except Exception as e:
                # If content policy violation, try with more sanitized version
                if "content_policy_violation" in str(e):
                    self.logger.warning(f"Content policy violation on scene {scene_num}, retrying with generic prompt...")
                    print(f"   [Warning]  콘텐츠 정책 위반 감지, 프롬프트 수정 후 재시도...")

                    # Create generic safe prompt
                    generic_prompt = f"""A cinematic scene showing Korean people in {scene.get('location', 'indoor setting')}.

{consistency_note}

CRITICAL REQUIREMENTS:
- All characters MUST be Korean people (한국인)
- Natural, relaxed facial expressions
- Realistic, photorealistic style
- {scene.get('time_of_day', 'daytime')} lighting
- {scene.get('mood', 'neutral')} atmosphere

Style: Cinematic, high quality, natural lighting, professional Korean drama aesthetic."""

                    response = self.client.images.generate(
                        model="dall-e-3",
                        prompt=generic_prompt,
                        size=dalle_size,
                        quality="standard",
                        n=1,
                    )
                    print(f"   [OK] 재시도 성공")
                else:
                    raise

            image_url = response.data[0].url

            # Download and save
            img_response = requests.get(image_url)
            img = Image.open(io.BytesIO(img_response.content))

            image_path = scene_dir / f"scene_{scene_num:02d}_image.png"
            img.save(image_path)

        # If first scene, analyze and extract character descriptions
        char_description = None
        if scene_num == 1:
            char_description = self._extract_character_description(image_path, story_data)

        self.logger.info(f"Scene {scene_num} image generated with consistency")

        return image_path, char_description

    def _extract_character_description(self, image_path: Path, story_data: Dict[str, Any]) -> str:
        """Analyze first scene image and extract detailed character descriptions using GPT-4 Vision."""
        try:
            import base64

            # Read and encode image
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')

            # Get character names from story
            characters = []
            if 'character_bible' in story_data:
                bible = story_data['character_bible']
                if 'protagonist' in bible:
                    characters.append(bible['protagonist'].get('name', ''))
                if 'helper' in bible:
                    characters.append(bible['helper'].get('name', ''))
                if 'antagonist' in bible:
                    characters.append(bible['antagonist'].get('name', ''))

            # Use OpenAI client for vision (Groq doesn't support vision)
            vision_client = self.openai_client if self.openai_client else self.client

            response = vision_client.chat.completions.create(
                model=self.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"""이 이미지를 분석하고 보이는 모든 인물의 DETAILED 시각적 특징을 설명하세요.

스토리 속 캐릭터: {', '.join(characters)}

각 인물에 대해 EXTREMELY DETAILED하게 설명:
- 나이대와 성별
- 의상 (색상, 스타일, 소재를 매우 구체적으로)
- 머리카락 (색상, 스타일, 길이, 질감)
- 얼굴 특징 (눈, 코, 입 모양, 피부톤, 주름 등)
- 체격 (키, 체형)
- 액세서리 또는 특징적인 요소 (안경, 목걸이, 시계 등)
- 자세와 위치

출력 형식 (매우 상세하게):
{', '.join(characters) if characters else 'Character 1'}: 60대 후반 한국 여성. 회색 머리를 짧게 자른 보브컷. 주름진 얼굴에 날카로운 눈매. 검은색 한복 저고리에 회색 치마. 작은 체구. 손에 지팡이를 들고 있음...

이 설명이 다음 씬에서 EXACT하게 같은 캐릭터를 생성하는데 사용됩니다.
최대한 구체적으로 작성하세요! 의상 색상, 머리 스타일, 얼굴 특징을 매우 상세히!"""
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500
            )

            description = response.choices[0].message.content.strip()
            self.logger.info("Character descriptions extracted from first scene")
            return description

        except Exception as e:
            self.logger.warning(f"Failed to extract character description: {e}")
            return None

    def _create_scene_videos_parallel(
        self,
        scene_media: list,
        aspect_ratio: str,
        num_scenes: int
    ) -> list:
        """Create scene videos in parallel for much faster processing (handles both images and videos)."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time

        # Determine optimal number of workers (CPU cores - 1, max 3)
        import os
        max_workers = min(3, max(1, os.cpu_count() - 1))
        print(f"   병렬 작업 수: {max_workers} (CPU cores: {os.cpu_count()})")

        scene_videos = [None] * len(scene_media)  # Pre-allocate list
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_scene = {}
            for media_data in scene_media:
                future = executor.submit(
                    self._create_single_scene_video,
                    media_data,
                    aspect_ratio
                )
                future_to_scene[future] = media_data

            # Process completed tasks
            with tqdm(total=num_scenes, desc="비디오 제작 진행", position=0) as pbar:
                for future in as_completed(future_to_scene):
                    media_data = future_to_scene[future]
                    i = media_data['scene_num']

                    try:
                        scene_video, elapsed = future.result()
                        scene_videos[i - 1] = scene_video  # Store in correct position
                        completed += 1

                        print(f"\n[OK] Scene {i}/{num_scenes} Complete! ({self._format_elapsed_time(elapsed)})")
                        pbar.update(1)

                    except Exception as e:
                        self.logger.error(f"Scene {i} video creation failed: {e}")
                        print(f"\n[ERROR] Scene {i} failed: {e}")
                        pbar.update(1)

        print(f"\n[OK] 병렬 비디오 생성 완료: {completed}/{num_scenes} 성공")
        return scene_videos

    def _create_single_scene_video(
        self,
        media_data: dict,
        aspect_ratio: str
    ) -> tuple:
        """Create a single scene video (audio + video + subtitles). Used for parallel processing.

        Handles both images and videos:
        - For images: converts to video with audio and subtitles
        - For videos: adds audio and subtitles to existing video
        """
        import time

        start_time = time.time()

        i = media_data['scene_num']
        scene = media_data['scene']
        scene_dir = media_data['scene_dir']
        media_type = media_data['media_type']
        media_path = media_data['media_path']

        # Generate audio from narration (always needed)
        audio_path = self._generate_scene_narration(
            scene,
            scene_dir,
            i
        )

        # Create or process scene video based on media type
        if media_type == 'video':
            # Video already exists - just add audio and subtitles
            print(f"   🎬 Scene {i}: 비디오 발견! 오디오+자막 추가 중...")
            scene_video = self._add_audio_and_subtitles_to_video(
                media_path,
                audio_path,
                scene_dir / f"scene_{i:02d}.mp4",
                scene['narration']
            )
        else:
            # Image - convert to video with audio and subtitles
            print(f"   🖼️  Scene {i}: 이미지→비디오 변환 중...")
            image_path = media_data['image_path']
            scene_video = self._create_scene_video(
                image_path,
                audio_path,
                scene_dir / f"scene_{i:02d}.mp4",
                aspect_ratio,
                scene['narration']  # Pass narration for subtitles
            )

        # Save scene script
        scene_script_path = scene_dir / f"scene_{i:02d}_script.txt"
        with open(scene_script_path, 'w', encoding='utf-8') as f:
            f.write(f"씬 {i}: {scene['title']}\n")
            f.write(f"{'='*60}\n\n")
            f.write(scene['narration'])

        elapsed = time.time() - start_time
        return scene_video, elapsed

    def _generate_scene_narration(
        self,
        scene: Dict[str, Any],
        scene_dir: Path,
        scene_num: int
    ) -> Path:
        """Generate narration audio for a scene."""

        from .narrator import Narrator

        narrator = Narrator(self.config)
        narration_text = scene['narration']

        audio_path = scene_dir / f"scene_{scene_num:02d}_audio.mp3"
        narrator.generate_speech(narration_text, audio_path)

        # Get duration
        audio_clip = AudioFileClip(str(audio_path))
        duration = audio_clip.duration
        audio_clip.close()

        self.logger.info(f"Scene {scene_num} narration generated ({duration:.1f}s)")

        return audio_path

    def _create_scene_video(
        self,
        image_path: Path,
        audio_path: Path,
        output_path: Path,
        aspect_ratio: str,
        narration_text: str = None
    ) -> Path:
        """Create video from scene image and audio with optional subtitles."""

        try:
            # Load audio
            audio = AudioFileClip(str(audio_path))
            duration = audio.duration

            # Create image clip
            image_clip = ImageClip(str(image_path), duration=duration)

            # Determine resolution
            if aspect_ratio == "9:16":
                target_w, target_h = 1080, 1920
            elif aspect_ratio == "16:9":
                target_w, target_h = 1920, 1080
            else:
                target_w, target_h = 1080, 1080

            # Resize/crop image
            from moviepy.video.fx.all import crop, resize

            img_aspect = image_clip.w / image_clip.h
            target_aspect = target_w / target_h

            if abs(img_aspect - target_aspect) < 0.01:
                # Aspects match, just resize
                image_clip = resize(image_clip, height=target_h)
            elif img_aspect > target_aspect:
                # Crop width
                new_w = int(image_clip.h * target_aspect)
                image_clip = crop(image_clip, width=new_w, height=image_clip.h,
                                x_center=image_clip.w/2, y_center=image_clip.h/2)
                image_clip = resize(image_clip, height=target_h)
            else:
                # Crop height
                new_h = int(image_clip.w / target_aspect)
                image_clip = crop(image_clip, width=image_clip.w, height=new_h,
                                x_center=image_clip.w/2, y_center=image_clip.h/2)
                image_clip = resize(image_clip, width=target_w)

            # Set audio
            image_clip = image_clip.set_audio(audio)

            # Add fade
            if duration > 2:
                image_clip = image_clip.fadein(1).fadeout(1)

            # Add subtitles if narration text provided
            if narration_text and self.config.get("ai", {}).get("add_subtitles", True):
                print(f"   Adding subtitles...")
                # Transcribe audio directly using Whisper for accurate timing
                try:
                    import whisper
                    import wave
                    import numpy as np

                    # Load Whisper model
                    model_size = os.getenv("WHISPER_MODEL", "base")
                    print(f"      Loading Whisper model: {model_size}")
                    model = whisper.load_model(model_size)

                    # Load audio file
                    with wave.open(str(audio_path), 'rb') as wav_file:
                        sample_rate = wav_file.getframerate()
                        n_frames = wav_file.getnframes()
                        audio_data = wav_file.readframes(n_frames)

                        # Convert to numpy array
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)
                        audio_array = audio_array.astype(np.float32) / 32768.0

                        # Convert stereo to mono if needed
                        if wav_file.getnchannels() == 2:
                            audio_array = audio_array.reshape(-1, 2).mean(axis=1)

                    # Transcribe
                    print(f"      Transcribing audio for subtitle timing...")
                    result = model.transcribe(
                        audio_array,
                        language="ko",
                        verbose=False
                    )

                    segments = [
                        {
                            "start": seg["start"],
                            "end": seg["end"],
                            "text": seg["text"].strip()
                        }
                        for seg in result["segments"]
                    ]

                    print(f"      Transcribed {len(segments)} segments")

                    # Save segments as ASS file for later use
                    if segments:
                        self._save_ass_file(audio_path, segments)

                    # Add subtitles using Transcriber
                    if segments:
                        from .transcriber import Transcriber
                        transcriber = Transcriber(self.config)
                        image_clip = transcriber.add_subtitles(image_clip, segments)

                except Exception as e:
                    self.logger.warning(f"Failed to add subtitles with Whisper: {e}")
                    print(f"      [Warning] Subtitle generation failed: {e}")

            # Export
            image_clip.write_videofile(
                str(output_path),
                fps=self.config["video"]["fps"],
                codec=self.config["output"]["codec"],
                audio_codec=self.config["output"]["audio_codec"],
                bitrate=self.config["output"]["bitrate"],
                preset='medium',
                logger=None
            )

            image_clip.close()
            audio.close()

            return output_path

        except Exception as e:
            self.logger.error(f"Scene video creation failed: {e}")
            raise

    def _add_audio_and_subtitles_to_video(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
        narration_text: str = None
    ) -> Path:
        """Add audio and subtitles to an existing video file.

        Args:
            video_path: Path to existing video file
            audio_path: Path to audio file
            output_path: Path to save the processed video
            narration_text: Text for subtitle generation

        Returns:
            Path to the processed video
        """
        try:
            from moviepy.editor import VideoFileClip, AudioFileClip

            # Load existing video
            video_clip = VideoFileClip(str(video_path))

            # Load audio
            audio = AudioFileClip(str(audio_path))

            # Set audio on the video
            video_clip = video_clip.set_audio(audio)

            # Adjust video duration to match audio if needed
            if video_clip.duration < audio.duration:
                # Loop the video if it's shorter than audio
                print(f"      Video duration ({video_clip.duration:.1f}s) < Audio duration ({audio.duration:.1f}s) - looping video...")
                from moviepy.video.fx.all import loop
                video_clip = loop(video_clip, duration=audio.duration)
            elif video_clip.duration > audio.duration:
                # Trim video if it's longer than audio
                print(f"      Video duration ({video_clip.duration:.1f}s) > Audio duration ({audio.duration:.1f}s) - trimming video...")
                video_clip = video_clip.subclip(0, audio.duration)

            # Add subtitles if narration text provided
            if narration_text and self.config.get("ai", {}).get("add_subtitles", True):
                print(f"   Adding subtitles...")
                try:
                    import whisper
                    import wave
                    import numpy as np
                    import os

                    # Load Whisper model
                    model_size = os.getenv("WHISPER_MODEL", "base")
                    print(f"      Loading Whisper model: {model_size}")
                    model = whisper.load_model(model_size)

                    # Load audio file
                    with wave.open(str(audio_path), 'rb') as wav_file:
                        sample_rate = wav_file.getframerate()
                        n_frames = wav_file.getnframes()
                        audio_data = wav_file.readframes(n_frames)

                        # Convert to numpy array
                        audio_array = np.frombuffer(audio_data, dtype=np.int16)
                        audio_array = audio_array.astype(np.float32) / 32768.0

                        # Convert stereo to mono if needed
                        if wav_file.getnchannels() == 2:
                            audio_array = audio_array.reshape(-1, 2).mean(axis=1)

                    # Transcribe
                    print(f"      Transcribing audio for subtitle timing...")
                    result = model.transcribe(
                        audio_array,
                        language="ko",
                        verbose=False
                    )

                    segments = [
                        {
                            "start": seg["start"],
                            "end": seg["end"],
                            "text": seg["text"].strip()
                        }
                        for seg in result["segments"]
                    ]

                    print(f"      Transcribed {len(segments)} segments")

                    # Save segments as ASS file for later use
                    if segments:
                        self._save_ass_file(audio_path, segments)

                    # Add subtitles using Transcriber
                    if segments:
                        from .transcriber import Transcriber
                        transcriber = Transcriber(self.config)
                        video_clip = transcriber.add_subtitles(video_clip, segments)

                except Exception as e:
                    self.logger.warning(f"Failed to add subtitles with Whisper: {e}")
                    print(f"      [Warning] Subtitle generation failed: {e}")

            # Export
            video_clip.write_videofile(
                str(output_path),
                fps=self.config["video"]["fps"],
                codec=self.config["output"]["codec"],
                audio_codec=self.config["output"]["audio_codec"],
                bitrate=self.config["output"]["bitrate"],
                preset='medium',
                logger=None
            )

            video_clip.close()
            audio.close()

            return output_path

        except Exception as e:
            self.logger.error(f"Adding audio and subtitles to video failed: {e}")
            raise

    def _add_narration_subtitles(self, clip, narration_text: str, duration: float):
        """
        Add subtitles to video clip from narration text.

        Splits narration into chunks and displays them as timed subtitles.
        Uses PIL instead of ImageMagick for better compatibility.
        """
        from moviepy.editor import ImageClip, CompositeVideoClip
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np

        # Get subtitle style from config
        style = self.config.get("ai", {}).get("subtitle_style", {})

        # Split narration into sentences (by periods, exclamation marks, question marks)
        import re
        sentences = re.split(r'[.!?。]\s*', narration_text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return clip

        # Calculate time per sentence
        time_per_sentence = duration / len(sentences)

        subtitle_clips = []
        current_time = 0.0

        # Font settings
        font_size = style.get("font_size", 52)
        text_color = style.get("color", "white")
        stroke_color = style.get("stroke_color", "black")
        stroke_width = style.get("stroke_width", 3)

        # Try to load font
        try:
            # Try common Windows Korean fonts
            font_names = [
                "C:/Windows/Fonts/malgun.ttf",  # 맑은 고딕
                "C:/Windows/Fonts/gulim.ttc",    # 굴림
                "C:/Windows/Fonts/batang.ttc",   # 바탕
                "arial.ttf"
            ]
            font = None
            for font_name in font_names:
                try:
                    font = ImageFont.truetype(font_name, font_size)
                    break
                except:
                    continue

            if font is None:
                font = ImageFont.load_default()
        except:
            font = ImageFont.load_default()

        for sentence in sentences:
            if not sentence:
                continue

            try:
                # Create PIL image for text
                max_width = int(clip.w * 0.85)

                # Word wrap
                lines = self._wrap_text(sentence, font, max_width)

                # Calculate text size
                temp_img = Image.new('RGBA', (1, 1))
                temp_draw = ImageDraw.Draw(temp_img)

                line_heights = []
                max_line_width = 0
                for line in lines:
                    bbox = temp_draw.textbbox((0, 0), line, font=font)
                    line_width = bbox[2] - bbox[0]
                    line_height = bbox[3] - bbox[1]
                    line_heights.append(line_height)
                    max_line_width = max(max_line_width, line_width)

                total_height = sum(line_heights) + (len(lines) - 1) * 10  # 10px line spacing

                # Add padding for stroke and background
                padding = 20
                img_width = max_line_width + padding * 2 + stroke_width * 4
                img_height = total_height + padding * 2 + stroke_width * 4

                # Create image with transparent background
                img = Image.new('RGBA', (img_width, img_height), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                # Add semi-transparent background if enabled
                if style.get("background", True):
                    bg_color = tuple(style.get("background_color", [0, 0, 0]))
                    bg_opacity = int(style.get("background_opacity", 0.7) * 255)
                    draw.rectangle(
                        [(0, 0), (img_width, img_height)],
                        fill=bg_color + (bg_opacity,)
                    )

                # Draw text with stroke
                y_offset = padding + stroke_width * 2
                for i, line in enumerate(lines):
                    bbox = draw.textbbox((0, 0), line, font=font)
                    line_width = bbox[2] - bbox[0]
                    x = (img_width - line_width) // 2

                    # Draw stroke (outline)
                    if stroke_width > 0:
                        for adj_x in range(-stroke_width, stroke_width + 1):
                            for adj_y in range(-stroke_width, stroke_width + 1):
                                if adj_x != 0 or adj_y != 0:
                                    draw.text(
                                        (x + adj_x, y_offset + adj_y),
                                        line,
                                        font=font,
                                        fill=stroke_color
                                    )

                    # Draw main text
                    draw.text((x, y_offset), line, font=font, fill=text_color)
                    y_offset += line_heights[i] + 10

                # Convert PIL image to numpy array
                img_array = np.array(img)

                # Create ImageClip
                subtitle_clip = ImageClip(img_array, duration=time_per_sentence)

                # Position subtitle
                position = style.get("position", "bottom")
                margin = style.get("margin", 80)

                if position == "bottom":
                    subtitle_clip = subtitle_clip.set_position(("center", clip.h - img_height - margin))
                elif position == "top":
                    subtitle_clip = subtitle_clip.set_position(("center", margin))
                else:  # center
                    subtitle_clip = subtitle_clip.set_position("center")

                # Set timing
                subtitle_clip = subtitle_clip.set_start(current_time)
                subtitle_clips.append(subtitle_clip)

                current_time += time_per_sentence

            except Exception as e:
                self.logger.warning(f"Failed to create subtitle for '{sentence[:30]}...': {e}")
                import traceback
                self.logger.warning(traceback.format_exc())
                continue

        if subtitle_clips:
            # Composite video with subtitles
            video = CompositeVideoClip([clip] + subtitle_clips)
            self.logger.info(f"Added {len(subtitle_clips)} subtitle segments")
            return video

        return clip

    def _wrap_text(self, text: str, font, max_width: int):
        """Wrap text to fit within max_width."""
        from PIL import ImageDraw, Image

        temp_img = Image.new('RGB', (1, 1))
        draw = ImageDraw.Draw(temp_img)

        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        return lines if lines else [text]

    def _save_ass_file(self, audio_path: Path, segments: list):
        """Save Whisper transcription segments as ASS subtitle file."""
        ass_path = audio_path.with_suffix('.ass')

        def format_ass_timestamp(seconds: float) -> str:
            """Convert seconds to ASS timestamp format (h:mm:ss.cc)"""
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            centisecs = int((seconds % 1) * 100)
            return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

        try:
            with open(ass_path, 'w', encoding='utf-8') as f:
                # ASS header
                f.write("[Script Info]\n")
                f.write("ScriptType: v4.00+\n")
                f.write("PlayResX: 1920\n")
                f.write("PlayResY: 1080\n")
                f.write("\n")

                # Style definition
                f.write("[V4+ Styles]\n")
                f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
                f.write("Style: Default,NanumGothic,96,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,20,1\n")
                f.write("\n")

                # Events (subtitles)
                f.write("[Events]\n")
                f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

                for seg in segments:
                    start_time = format_ass_timestamp(seg["start"])
                    end_time = format_ass_timestamp(seg["end"])
                    text = seg["text"]
                    f.write(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n")

            print(f"      Saved ASS subtitle file: {ass_path.name}")
            self.logger.info(f"ASS subtitle file created: {ass_path}")

        except Exception as e:
            self.logger.warning(f"Failed to save ASS file: {e}")
            print(f"      [Warning] ASS file save failed: {e}")

    def _get_ffmpeg_path(self):
        """Get FFmpeg executable path from MoviePy/imageio-ffmpeg or system."""
        import shutil

        # Try system FFmpeg first
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            return ffmpeg_path, shutil.which('ffprobe')

        # Try imageio-ffmpeg (bundled with MoviePy)
        try:
            import imageio_ffmpeg
            ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
            # ffprobe is usually in the same directory
            ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe') if 'ffmpeg.exe' in ffmpeg_path else None
            return ffmpeg_path, ffprobe_path
        except:
            pass

        # Try moviepy's ffmpeg
        try:
            from moviepy.config import get_setting
            ffmpeg_path = get_setting("FFMPEG_BINARY")
            if ffmpeg_path and Path(ffmpeg_path).exists():
                return ffmpeg_path, None
        except:
            pass

        return None, None

    def _combine_scenes(self, scene_videos: List[Path], output_path: Path) -> Path:
        """
        Combine all scene videos into one using FFmpeg for much faster performance.

        FFmpeg is 10-100x faster than MoviePy for video concatenation.
        """
        import subprocess
        import tempfile

        # Get FFmpeg path
        ffmpeg_path, ffprobe_path = self._get_ffmpeg_path()

        if not ffmpeg_path:
            self.logger.warning("FFmpeg not found, using MoviePy (매우 느림)")
            print(f"   [Warning] FFmpeg를 찾을 수 없습니다. MoviePy 사용 (매우 느림)")
            print(f"    팁: imageio-ffmpeg 설치로 속도 향상 가능: pip install imageio-ffmpeg")
            return self._combine_scenes_moviepy(scene_videos, output_path)

        try:
            # Method 1: Try concat demuxer first (fastest - no re-encoding)
            # This works if all videos have identical parameters
            print(f"   시도 1: FFmpeg concat demuxer (재인코딩 없음, 가장 빠름)")

            # Create concat file list
            concat_file = output_path.parent / "concat_list.txt"
            with open(concat_file, 'w', encoding='utf-8') as f:
                for video_path in scene_videos:
                    # Use forward slashes for FFmpeg compatibility on Windows
                    video_path_str = str(video_path).replace('\\', '/')
                    f.write(f"file '{video_path_str}'\n")

            # Try concat demuxer (no re-encoding)
            cmd = [
                ffmpeg_path,
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',  # Copy streams without re-encoding
                '-y',  # Overwrite output
                str(output_path)
            ]

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Check if concat demuxer succeeded
            if result.returncode == 0 and output_path.exists():
                concat_file.unlink()  # Clean up

                # Get duration
                duration = self._get_video_duration_ffmpeg(output_path)
                print(f"   [OK] concat demuxer 성공 (재인코딩 없음)")
                print(f"[OK] Final Video: {output_path.name} (Total {duration/60:.1f} min)")
                return output_path

            # Method 2: Concat demuxer failed, try concat filter (re-encoding, slower but safer)
            print(f"   [Warning] concat demuxer 실패 (비디오 파라미터 불일치)")
            print(f"   시도 2: FFmpeg concat filter (재인코딩, 안전함)")

            # Build filter complex for concatenation
            filter_parts = []
            for i in range(len(scene_videos)):
                filter_parts.append(f"[{i}:v][{i}:a]")

            filter_complex = f"{''.join(filter_parts)}concat=n={len(scene_videos)}:v=1:a=1[outv][outa]"

            cmd = [
                ffmpeg_path,
                '-y'  # Overwrite output
            ]

            # Add all input files
            for video_path in scene_videos:
                cmd.extend(['-i', str(video_path)])

            # Add filter and output
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '[outv]',
                '-map', '[outa]',
                '-c:v', self.config["output"]["codec"],
                '-c:a', self.config["output"]["audio_codec"],
                '-b:v', self.config["output"]["bitrate"],
                '-preset', 'medium',
                str(output_path)
            ])

            # Show progress
            print(f"   FFmpeg 실행 중...")
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            if result.returncode != 0:
                self.logger.error(f"FFmpeg concat filter failed: {result.stderr}")
                raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")

            # Clean up concat file
            if concat_file.exists():
                concat_file.unlink()

            # Get duration
            duration = self._get_video_duration_ffmpeg(output_path)
            print(f"   [OK] concat filter 성공")
            print(f"[OK] Final Video: {output_path.name} (Total {duration/60:.1f} min)")

            return output_path

        except FileNotFoundError:
            # FFmpeg not found, fallback to MoviePy (very slow)
            self.logger.warning("FFmpeg not found, using MoviePy (매우 느림)")
            print(f"   [Warning] FFmpeg를 찾을 수 없습니다. MoviePy 사용 (매우 느림)")
            print(f"    팁: imageio-ffmpeg 설치로 속도 향상 가능: pip install imageio-ffmpeg")
            return self._combine_scenes_moviepy(scene_videos, output_path)

        except Exception as e:
            self.logger.error(f"Scene combination failed: {e}")
            # Try fallback to MoviePy
            print(f"   [Warning] FFmpeg 실패, MoviePy로 재시도...")
            return self._combine_scenes_moviepy(scene_videos, output_path)

    def _get_video_duration_ffmpeg(self, video_path: Path) -> float:
        """Get video duration using FFmpeg."""
        import subprocess
        import json

        ffmpeg_path, ffprobe_path = self._get_ffmpeg_path()

        if not ffprobe_path:
            # Fallback: try to get duration from moviepy
            try:
                from moviepy.editor import VideoFileClip
                clip = VideoFileClip(str(video_path))
                duration = clip.duration
                clip.close()
                return duration
            except:
                return 0.0

        try:
            cmd = [
                ffprobe_path,
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                str(video_path)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except:
            return 0.0

    def _combine_scenes_moviepy(self, scene_videos: List[Path], output_path: Path) -> Path:
        """Fallback method using MoviePy (slow but reliable)."""
        from moviepy.editor import VideoFileClip, concatenate_videoclips

        clips = []
        for video_path in tqdm(scene_videos, desc="   씬 로딩", leave=False):
            clip = VideoFileClip(str(video_path))
            clips.append(clip)

        final_clip = concatenate_videoclips(clips, method="compose")
        total_duration = final_clip.duration

        final_clip.write_videofile(
            str(output_path),
            fps=self.config["video"]["fps"],
            codec=self.config["output"]["codec"],
            audio_codec=self.config["output"]["audio_codec"],
            bitrate=self.config["output"]["bitrate"],
            preset='medium',
            logger='bar'
        )

        # Cleanup
        final_clip.close()
        for clip in clips:
            clip.close()

        print(f"[OK] Final Video: {output_path.name} (Total {total_duration/60:.1f} min)")
        return output_path

    def _save_story_metadata(self, story_data: Dict[str, Any], project_dir: Path, is_structure_only: bool = False):
        """Save story metadata and full script."""

        # Save full script
        if is_structure_only:
            script_path = project_dir / "full_structure_outlines.txt"
        else:
            script_path = project_dir / "full_script.txt"

        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(f"제목: {story_data['title']}\n")
            if 'logline' in story_data:
                f.write(f"로그라인: {story_data['logline']}\n")
            f.write(f"장르: {story_data['genre']}\n")
            f.write(f"{'='*70}\n\n")

            # Character Bible
            if 'character_bible' in story_data:
                bible = story_data['character_bible']
                f.write(f"[캐릭터 바이블]\n\n")

                if 'protagonist' in bible:
                    p = bible['protagonist']
                    f.write(f"주인공: {p.get('name', 'N/A')} ({p.get('age', 'N/A')}세)\n")
                    f.write(f"  외형: {p.get('appearance', 'N/A')}\n")
                    f.write(f"  성격: {p.get('personality', 'N/A')}\n")
                    f.write(f"  내면: {p.get('inner_world', 'N/A')}\n")
                    f.write(f"  말투: {p.get('speech_style', 'N/A')}\n")
                    f.write(f"  소품: {p.get('props', 'N/A')}\n\n")

                if 'helper' in bible:
                    h = bible['helper']
                    f.write(f"조력자: {h.get('name', 'N/A')} ({h.get('age', 'N/A')}세)\n")
                    f.write(f"  외형: {h.get('appearance', 'N/A')}\n")
                    f.write(f"  성격: {h.get('personality', 'N/A')}\n\n")

                if 'antagonist' in bible:
                    a = bible['antagonist']
                    f.write(f"대립자: {a.get('name', 'N/A')} ({a.get('age', 'N/A')}세)\n")
                    f.write(f"  외형: {a.get('appearance', 'N/A')}\n")
                    f.write(f"  성격: {a.get('personality', 'N/A')}\n\n")

                if 'symbolic_objects' in bible:
                    f.write(f"상징적 오브제: {', '.join(bible['symbolic_objects'])}\n\n")

                if 'color_mood' in bible:
                    f.write(f"컬러 무드:\n")
                    for emotion, color in bible['color_mood'].items():
                        f.write(f"  {emotion}: {color}\n")
                    f.write("\n")

                f.write(f"{'='*70}\n\n")

            # Synopsis
            if 'synopsis' in story_data:
                synopsis = story_data['synopsis']
                if isinstance(synopsis, dict):
                    f.write(f"[시나리오 개요]\n\n")
                    f.write(f"프롤로그: {synopsis.get('prologue', 'N/A')}\n\n")
                    f.write(f"1막: {synopsis.get('act1', 'N/A')}\n\n")
                    f.write(f"2막: {synopsis.get('act2', 'N/A')}\n\n")
                    f.write(f"3막: {synopsis.get('act3', 'N/A')}\n\n")
                    f.write(f"클라이맥스: {synopsis.get('climax', 'N/A')}\n\n")
                    f.write(f"결말: {synopsis.get('ending', 'N/A')}\n\n")
                    f.write(f"테마: {synopsis.get('theme', 'N/A')}\n\n")
                else:
                    f.write(f"시놉시스:\n{synopsis}\n\n")
                f.write(f"{'='*70}\n\n")

            # Scenes
            for i, scene in enumerate(story_data['scenes'], 1):
                f.write(f"씬 {i}: {scene['title']}")
                if 'time_of_day' in scene:
                    f.write(f" ({scene['time_of_day']})")
                f.write(f"\n{'-'*70}\n")
                f.write(f"{scene['narration']}\n\n")

            # YouTube Metadata
            if 'youtube_metadata' in story_data:
                yt = story_data['youtube_metadata']
                f.write(f"{'='*70}\n")
                f.write(f"[유튜브 메타데이터]\n\n")
                f.write(f"영상 제목: {yt.get('video_title', 'N/A')}\n\n")
                f.write(f"설명:\n{yt.get('description', 'N/A')}\n\n")
                f.write(f"태그: {', '.join(yt.get('tags', []))}\n\n")
                f.write(f"썸네일 문구: {', '.join(yt.get('thumbnail_text_options', []))}\n")

        # Save JSON metadata
        metadata_path = project_dir / "story_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(story_data, f, ensure_ascii=False, indent=2)

        # Save YouTube metadata separately
        if 'youtube_metadata' in story_data:
            youtube_path = project_dir / "youtube_metadata.json"
            with open(youtube_path, 'w', encoding='utf-8') as f:
                json.dump(story_data['youtube_metadata'], f, ensure_ascii=False, indent=2)
            print(f"   [OK] YouTube Metadata: {youtube_path.name}")

        print(f"   [OK] Script Saved: {script_path.name}")
        print(f"   [OK] Metadata Saved: {metadata_path.name}")

    def _estimate_duration(self, script: str) -> float:
        """Estimate video duration in minutes."""
        # Assuming ~2.8 chars per second for Korean TTS
        seconds = len(script) / 2.8
        return seconds / 60

    def _format_elapsed_time(self, seconds: float) -> str:
        """Format elapsed time in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}초"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}분 {secs}초"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours}시간 {minutes}분 {secs}초"

    def _create_youtube_thumbnail(
        self,
        image_path: Path,
        title: str,
        project_dir: Path
    ) -> Path:
        """Create YouTube thumbnail from first scene image."""
        from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
        import textwrap

        output_path = project_dir / "youtube_thumbnail.jpg"

        # Load and resize image to YouTube thumbnail size (1280x720)
        img = Image.open(image_path)
        img = img.convert('RGB')

        # Resize to 1280x720 (16:9)
        target_size = (1280, 720)

        # Calculate crop/resize
        img_ratio = img.width / img.height
        target_ratio = target_size[0] / target_size[1]

        if img_ratio > target_ratio:
            # Image is wider, crop width
            new_width = int(img.height * target_ratio)
            left = (img.width - new_width) // 2
            img = img.crop((left, 0, left + new_width, img.height))
        else:
            # Image is taller, crop height
            new_height = int(img.width / target_ratio)
            top = (img.height - new_height) // 2
            img = img.crop((0, top, img.width, top + new_height))

        img = img.resize(target_size, Image.Resampling.LANCZOS)

        # Enhance image slightly
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.2)
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.1)

        # Create drawing context
        draw = ImageDraw.Draw(img, 'RGBA')

        # Load Korean font
        font_size = 80
        font = None
        font_names = [
            "C:/Windows/Fonts/malgunbd.ttf",  # 맑은 고딕 Bold
            "C:/Windows/Fonts/malgun.ttf",
            "C:/Windows/Fonts/gulim.ttc",
        ]

        for font_name in font_names:
            try:
                font = ImageFont.truetype(font_name, font_size)
                break
            except:
                continue

        if font is None:
            font = ImageFont.load_default()

        # Remove quotes from title
        quote_chars = ['"', "'", '"', '"', ''', ''']
        for quote in quote_chars:
            title = title.replace(quote, '')

        # Wrap title text
        max_width = img.width - 100
        words = title.split()
        lines = []
        current_line = []

        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]

        if current_line:
            lines.append(' '.join(current_line))

        # Limit to 3 lines
        if len(lines) > 3:
            lines = lines[:3]
            lines[-1] += "..."

        # Calculate text dimensions
        line_heights = []
        max_line_width = 0

        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            line_height = bbox[3] - bbox[1]
            line_heights.append(line_height)
            max_line_width = max(max_line_width, line_width)

        line_spacing = 15
        total_text_height = sum(line_heights) + (len(lines) - 1) * line_spacing

        # Calculate background box
        padding = 40
        bg_width = max_line_width + padding * 2
        bg_height = total_text_height + padding * 2

        # Position at bottom
        bg_y = img.height - bg_height - 50
        bg_x = (img.width - bg_width) // 2

        # Draw semi-transparent background
        bg_overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_overlay)

        bg_alpha = int(0.75 * 255)
        bg_draw.rounded_rectangle(
            [(bg_x, bg_y), (bg_x + bg_width, bg_y + bg_height)],
            radius=20,
            fill=(0, 0, 0, bg_alpha)
        )

        img = Image.alpha_composite(img.convert('RGBA'), bg_overlay).convert('RGB')
        draw = ImageDraw.Draw(img, 'RGBA')

        # Draw text with glow and stroke
        y_offset = bg_y + padding
        stroke_width = 4

        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            line_width = bbox[2] - bbox[0]
            x = (img.width - line_width) // 2

            # Add glow effect
            glow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)

            for glow_offset in range(8, 0, -1):
                glow_alpha = int((8 - glow_offset) * 15)
                for gx in range(-glow_offset, glow_offset + 1):
                    for gy in range(-glow_offset, glow_offset + 1):
                        glow_draw.text(
                            (x + gx, y_offset + gy),
                            line,
                            font=font,
                            fill=(255, 255, 255, glow_alpha)
                        )

            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=3))
            img = Image.alpha_composite(img.convert('RGBA'), glow_layer).convert('RGB')
            draw = ImageDraw.Draw(img, 'RGBA')

            # Draw stroke
            for dx in range(-stroke_width, stroke_width + 1):
                for dy in range(-stroke_width, stroke_width + 1):
                    if dx != 0 or dy != 0:
                        draw.text(
                            (x + dx, y_offset + dy),
                            line,
                            font=font,
                            fill='black'
                        )

            # Draw main text
            draw.text((x, y_offset), line, font=font, fill='white')
            y_offset += line_heights[i] + line_spacing

        # Save thumbnail
        img.save(output_path, 'JPEG', quality=95)

        return output_path
