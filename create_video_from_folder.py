"""
폴더에 있는 story.json과 이미지들로 영상을 자동 생성하는 스크립트

사용법:
    python create_video_from_folder.py --folder "path/to/folder"

폴더 구조:
    folder/
        story.json (또는 story_metadata.json)
        scene_01_image.png
        scene_02_image.png
        ...
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
import warnings
from time import time
import signal

# 버전 호환성 경고 메시지 숨기기
warnings.filterwarnings("ignore", message="Model was trained with")
warnings.filterwarnings("ignore", message="Lightning automatically upgraded")
warnings.filterwarnings("ignore", message="torchaudio._backend")
warnings.filterwarnings("ignore", category=UserWarning, module="pyannote")
warnings.filterwarnings("ignore", category=UserWarning, module="speechbrain")
warnings.filterwarnings("ignore", category=UserWarning, module="pytorch_lightning")

# 로깅 레벨 조정 (pytorch_lightning INFO 메시지 숨기기)
import logging as base_logging
base_logging.getLogger("pytorch_lightning").setLevel(base_logging.WARNING)
from typing import Dict, List, Optional
import edge_tts
import asyncio
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, VideoFileClip
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import tempfile

# 로깅 설정 (먼저 설정)
# Windows에서 UTF-8 출력을 위해 stdout을 UTF-8로 재설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/video_from_folder.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global cancellation flag and child processes tracking
cancellation_requested = False
child_processes = []

def signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown"""
    global cancellation_requested, child_processes
    logger.info("🛑 취소 시그널 수신, 작업을 중단합니다...")
    cancellation_requested = True

    # 모든 자식 프로세스 강제 종료
    for proc in child_processes:
        try:
            if proc.poll() is None:  # 아직 실행 중
                logger.info(f"🛑 자식 프로세스 종료 중: PID {proc.pid}")
                proc.kill()  # SIGKILL
                proc.wait(timeout=2)
        except Exception as e:
            logger.error(f"❌ 프로세스 종료 실패: {e}")

    sys.exit(1)

# Google Image Search (옵션)
try:
    from google_image_search import GoogleImageSearcher, DailyLimitExceededError, GoogleImageSearchError
    GOOGLE_SEARCH_AVAILABLE = True
except ImportError:
    GOOGLE_SEARCH_AVAILABLE = False
    logger.warning("[WARNING] google_image_search module not found. Auto image search disabled.")

# DALL-E (옵션)
try:
    from openai import OpenAI
    DALLE_AVAILABLE = True
except ImportError:
    DALLE_AVAILABLE = False
    logger.warning("[WARNING] openai module not found. DALL-E image generation disabled.")


class VideoFromFolderCreator:
    """story.json과 이미지로 영상을 생성하는 클래스"""

    def __init__(self, folder_path: str, voice: str = "ko-KR-SoonBokNeural",
                 aspect_ratio: str = "16:9", add_subtitles: bool = False,
                 image_source: str = "none", is_admin: bool = False):
        """
        Args:
            folder_path: story.json과 이미지가 있는 폴더 경로
            voice: TTS 음성 (기본: ko-KR-SoonBokNeural)
            aspect_ratio: 비디오 비율 (기본: 16:9)
            add_subtitles: 자막 추가 여부 (기본: False)
            image_source: 이미지 소스 ("none", "google", "dalle")
            is_admin: 관리자 모드 (비용 로그 표시)
        """
        self.folder_path = Path(folder_path)
        self.voice = voice
        self.aspect_ratio = aspect_ratio
        self.add_subtitles = add_subtitles
        self.image_source = image_source.lower()
        self.is_admin = is_admin

        # 이미지 검색기 초기화
        self.image_searcher = None
        self.dalle_client = None

        if self.image_source == "google" and GOOGLE_SEARCH_AVAILABLE:
            try:
                self.image_searcher = GoogleImageSearcher()
                logger.info("✅ Google Image Search 활성화됨")
            except GoogleImageSearchError as e:
                logger.warning(f"⚠️ Google Image Search 초기화 실패: {e}")
                self.image_source = "none"

        elif self.image_source == "dalle":
            if not DALLE_AVAILABLE:
                logger.error("❌ openai 패키지가 설치되지 않았습니다. pip install openai")
                self.image_source = "none"
            else:
                import os
                api_key = os.getenv('OPENAI_API_KEY')
                if not api_key:
                    logger.error("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
                    self.image_source = "none"
                else:
                    self.dalle_client = OpenAI(api_key=api_key)
                    logger.info("✅ DALL-E 3 이미지 생성 활성화됨")

        # 비율 파싱
        if aspect_ratio == "9:16":
            self.width, self.height = 1080, 1920
        elif aspect_ratio == "16:9":
            self.width, self.height = 1920, 1080
        else:
            raise ValueError(f"지원하지 않는 비율: {aspect_ratio}")

        # story.json 로드
        self.story_data = self._load_story_json()

        # 썸네일 자동 생성
        self._create_thumbnail()

        # GPU 인코더 감지
        self.video_codec, self.codec_preset = self._detect_best_encoder()

        # Whisper 모델 캐싱 (한 번만 로드)
        self._whisper_model = None

    def _detect_best_encoder(self):
        """사용 가능한 최고의 비디오 인코더 감지"""
        try:
            # ffmpeg에서 사용 가능한 인코더 목록 확인
            result = subprocess.run(
                ['ffmpeg', '-encoders'],
                capture_output=True,
                text=True,
                timeout=5
            )
            encoders = result.stdout

            # NVIDIA GPU 인코더 (가장 빠름)
            if 'h264_nvenc' in encoders:
                # 드라이버 버전 체크
                try:
                    driver_check = subprocess.run(
                        ['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    driver_version = driver_check.stdout.strip()
                    driver_major = int(driver_version.split('.')[0])

                    if driver_major >= 570:
                        logger.info(f"✓ NVIDIA GPU 인코더 사용 (h264_nvenc, 드라이버 {driver_version})")
                        return 'h264_nvenc', 'p4'
                    else:
                        logger.warning(f"⚠️  NVIDIA 드라이버가 낮음 ({driver_version} < 570.0), CPU 인코더 사용")
                        logger.info("   드라이버 업데이트: https://www.nvidia.com/Download/index.aspx")
                except:
                    # 드라이버 체크 실패 시 GPU 시도 (폴백 있음)
                    logger.info("✓ NVIDIA GPU 인코더 감지 (h264_nvenc) - 드라이버 버전 확인 실패, 시도합니다")
                    return 'h264_nvenc', 'p4'

            # Intel QSV 인코더
            if 'h264_qsv' in encoders:
                logger.info("✓ Intel QSV GPU 인코더 사용 (h264_qsv)")
                return 'h264_qsv', 'fast'

            # AMD GPU 인코더
            if 'h264_amf' in encoders:
                logger.info("✓ AMD GPU 인코더 사용 (h264_amf)")
                return 'h264_amf', 'speed'

        except Exception as e:
            logger.warning(f"GPU 인코더 감지 실패: {e}")

        # 폴백: CPU 인코더
        logger.info("✗ GPU 인코더 없음. CPU 인코더 사용 (libx264)")
        return 'libx264', 'ultrafast'

    def _load_story_json(self) -> Dict:
        """story로 시작하는 JSON 파일 로드"""
        # 경로 정규화 (따옴표 제거)
        folder_str = str(self.folder_path).strip('"').strip("'")
        self.folder_path = Path(folder_str)

        logger.info(f"폴더 경로: {self.folder_path}")
        logger.info(f"폴더 존재 여부: {self.folder_path.exists()}")

        # story가 포함된 모든 JSON 파일 찾기
        story_files = list(self.folder_path.glob("*story*.json"))

        logger.info(f"찾은 *story*.json 파일: {[f.name for f in story_files]}")

        if story_files:
            # 파일이 여러 개면 첫 번째 사용
            json_path = story_files[0]
            logger.info(f"JSON 파일 로드: {json_path.name}")
            with open(json_path, 'r', encoding='utf-8') as f:
                json_text = f.read()

                # 마크다운 코드 블록 제거 (```json ... ``` 형식)
                json_text = re.sub(r'^```json\s*', '', json_text, flags=re.IGNORECASE)
                json_text = re.sub(r'\s*```\s*$', '', json_text)
                json_text = json_text.strip()

                # JSON 파싱 시도
                try:
                    return json.loads(json_text)
                except json.JSONDecodeError as e:
                    logger.warning(f"⚠️  JSON 파싱 실패, 자동 수정 시도 중... (원인: {e})")

                    # JSON 문자열 값 내부의 이스케이프되지 않은 따옴표 수정
                    # "text": "He said "hello"" -> "text": "He said \"hello\""
                    def fix_quotes(match):
                        key = match.group(1)
                        value = match.group(2)
                        # 값 내부의 이스케이프되지 않은 따옴표를 이스케이프 처리
                        # 이미 이스케이프된 따옴표(\")는 건드리지 않음
                        fixed_value = re.sub(r'(?<!\\)"', r'\\"', value)
                        return f'"{key}": "{fixed_value}"'

                    # "key": "value" 패턴을 찾아서 value 내부의 따옴표 수정
                    # 단, value 끝의 따옴표는 유지
                    json_text_fixed = re.sub(
                        r'"([^"]+)"\s*:\s*"((?:[^"\\]|\\.)*)(?<!\\)"',
                        fix_quotes,
                        json_text
                    )

                    try:
                        logger.info("✅ JSON 자동 수정 성공")
                        return json.loads(json_text_fixed)
                    except json.JSONDecodeError as e2:
                        logger.error(f"❌ JSON 자동 수정 실패: {e2}")
                        # 원본 에러 발생
                        raise e

        raise FileNotFoundError(f"{self.folder_path}에 'story'가 포함된 JSON 파일이 없습니다.")

    def _create_thumbnail(self):
        """씬 1 이미지로 썸네일 자동 생성"""
        try:
            logger.info("🖼️  썸네일 자동 생성 중...")

            # create_thumbnail.py를 subprocess로 실행
            import subprocess

            thumbnail_script = Path(__file__).parent / "create_thumbnail.py"

            if not thumbnail_script.exists():
                logger.warning(f"썸네일 스크립트를 찾을 수 없습니다: {thumbnail_script}")
                return

            result = subprocess.run(
                [sys.executable, str(thumbnail_script), "-f", str(self.folder_path)],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode == 0:
                logger.info("✅ 썸네일 생성 완료")
            else:
                logger.warning(f"썸네일 생성 실패: {result.stderr}")

        except Exception as e:
            logger.warning(f"썸네일 생성 중 오류 (무시하고 계속): {e}")

    def _find_images(self) -> Dict[int, Path]:
        """씬별 이미지 파일 찾기 (scene_XX 패턴 또는 시간순 자동 정렬)"""
        images = {}

        # 1. scene_XX_image 패턴 찾기
        for file in self.folder_path.glob("scene_*_image.*"):
            match = re.match(r"scene_(\d+)_image\.(png|jpg|jpeg)", file.name)
            if match:
                scene_num = int(match.group(1))
                images[scene_num] = file

        # images 서브폴더에서도 찾기
        images_folder = self.folder_path / "images"
        if images_folder.exists():
            for file in images_folder.glob("scene_*_image.*"):
                match = re.match(r"scene_(\d+)_image\.(png|jpg|jpeg)", file.name)
                if match:
                    scene_num = int(match.group(1))
                    if scene_num not in images:
                        images[scene_num] = file

        # 2. scene 패턴이 없으면 모든 이미지 파일 찾기
        if not images:
            logger.info("scene_XX 패턴 없음. 모든 이미지를 찾습니다.")

            # 모든 이미지 파일 찾기 (generated_videos 폴더 및 썸네일 제외, 중복 제거)
            all_images_set = set()
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG']:
                for img_file in self.folder_path.glob(ext):
                    # generated_videos 폴더 안의 파일과 썸네일은 제외
                    if 'generated_videos' not in str(img_file) and 'thumbnail' not in img_file.name.lower():
                        all_images_set.add(img_file)

            if images_folder and images_folder.exists():
                for ext in ['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG']:
                    for img_file in images_folder.glob(ext):
                        # 썸네일 제외
                        if 'thumbnail' not in img_file.name.lower():
                            all_images_set.add(img_file)

            # Set을 리스트로 변환하고 정렬
            # ⚠️ 중요: Frontend와 동일한 로직 사용!
            # 1. 명확한 시퀀스 패턴이 있으면 시퀀스로 정렬
            # 2. 없으면 파일 수정 시간으로 정렬 (오래된 것부터)
            def extract_sequence(filepath):
                """
                명확한 시퀀스 번호만 추출:
                - image_01, scene_1, img_5 등
                - image(1), scene(2) 등
                - (1), (2) 등
                - 파일명 전체가 숫자 (1.jpg, 2.png)

                Returns: (sequence_number or None, mtime)
                """
                import re
                name = filepath.stem  # 확장자 제외한 파일명

                # image_01, scene_1, img_5 패턴
                match = re.match(r'^(image|scene|img)[-_](\d+)$', name, re.IGNORECASE)
                if match:
                    return (int(match.group(2)), 0)

                # image(1), scene(2) 패턴
                match = re.match(r'^(image|scene|img)\((\d+)\)$', name, re.IGNORECASE)
                if match:
                    return (int(match.group(2)), 0)

                # (1), (2) 패턴
                match = re.match(r'^\((\d+)\)$', name)
                if match:
                    return (int(match.group(1)), 0)

                # 파일명 전체가 숫자 (1, 2, 3)
                match = re.match(r'^(\d+)$', name)
                if match:
                    return (int(match.group(1)), 0)

                # 시퀀스 번호 없음 - 파일 수정 시간 사용
                try:
                    mtime = filepath.stat().st_mtime
                except:
                    mtime = 0
                return (None, mtime)

            # 정렬: 시퀀스 번호가 있으면 우선, 없으면 시간 순서
            all_images_list = list(all_images_set)
            all_images = sorted(all_images_list, key=lambda f: (
                extract_sequence(f)[0] is None,  # 시퀀스 없는 것을 뒤로
                extract_sequence(f)[0] if extract_sequence(f)[0] is not None else 0,  # 시퀀스 정렬
                extract_sequence(f)[1]  # 시간 정렬
            ))

            # 씬 번호 자동 할당 및 로그 출력
            logger.info(f"\n📷 이미지 정렬 완료 (총 {len(all_images)}개):")
            for idx, img_path in enumerate(all_images, start=1):
                images[idx] = img_path
                seq_info = extract_sequence(img_path)
                if seq_info[0] is not None:
                    logger.info(f"  씬 {idx}: {img_path.name} (시퀀스: {seq_info[0]})")
                else:
                    import datetime
                    mtime_str = datetime.datetime.fromtimestamp(seq_info[1]).strftime('%Y-%m-%d %H:%M:%S')
                    logger.info(f"  씬 {idx}: {img_path.name} (시간: {mtime_str})")

        logger.info(f"이미지 {len(images)}개 발견")

        # 3. 자동 이미지 생성/다운로드 (활성화된 경우)
        if self.image_source in ["google", "dalle"]:
            images = self._download_missing_images(images)

        return images

    def _download_missing_images(self, images: Dict[int, Path]) -> Dict[int, Path]:
        """
        누락된 이미지를 Google Search 또는 DALL-E로 자동 생성

        Args:
            images: 기존 이미지 딕셔너리

        Returns:
            업데이트된 이미지 딕셔너리
        """
        scenes = self.story_data.get('scenes', [])

        if not scenes:
            logger.warning("⚠️ story.json에 scenes 정보가 없습니다.")
            return images

        logger.info(f"🔍 총 {len(scenes)}개 씬에 대해 이미지 확인 중...")

        missing_scenes = []
        for idx, scene in enumerate(scenes, start=1):
            if idx not in images:
                missing_scenes.append((idx, scene))

        if not missing_scenes:
            logger.info("✅ 모든 씬에 이미지가 있습니다.")
            return images

        source_name = "Google Image Search" if self.image_source == "google" else "DALL-E 3"
        logger.info(f"⚠️ {len(missing_scenes)}개 씬의 이미지가 누락되었습니다. {source_name}로 생성을 시작합니다...")

        # 비용 예측
        if self.image_source == "google":
            self.image_searcher.log_cost_estimate(len(missing_scenes))
        elif self.image_source == "dalle":
            self._log_dalle_cost_estimate(len(missing_scenes))

        try:
            success_count = 0
            fail_count = 0

            for scene_num, scene in missing_scenes:
                # image_prompt 추출 (imagefx_prompt도 지원)
                image_prompt = scene.get('image_prompt') or scene.get('imagefx_prompt', '')

                if not image_prompt:
                    logger.warning(f"⚠️ 씬 {scene_num}: image_prompt 또는 imagefx_prompt가 없습니다. 건너뜁니다.")
                    continue

                # 파일명 생성
                filename = f"scene_{scene_num:02d}_image.jpg"

                if self.image_source == "google":
                    # Google Image Search
                    logger.info(f"🔍 씬 {scene_num}: '{image_prompt}' 검색 중...")
                    downloaded_path = self.image_searcher.search_and_download(
                        query=image_prompt,
                        save_dir=self.folder_path,
                        filename=filename
                    )

                    if downloaded_path:
                        images[scene_num] = downloaded_path
                        success_count += 1
                        logger.info(f"✅ 씬 {scene_num}: 이미지 다운로드 완료")
                    else:
                        fail_count += 1
                        logger.error(f"❌ 씬 {scene_num}: 이미지 다운로드 실패")

                elif self.image_source == "dalle":
                    # DALL-E 3 Image Generation
                    logger.info(f"🎨 씬 {scene_num}: '{image_prompt}' DALL-E 생성 중...")
                    generated_path = self._generate_dalle_image(
                        prompt=image_prompt,
                        save_dir=self.folder_path,
                        filename=filename
                    )

                    if generated_path:
                        images[scene_num] = generated_path
                        success_count += 1
                        logger.info(f"✅ 씬 {scene_num}: 이미지 생성 완료")
                        logger.info(f"   → images[{scene_num}] = {generated_path}")
                    else:
                        fail_count += 1
                        logger.error(f"❌ 씬 {scene_num}: 이미지 생성 실패")

        except DailyLimitExceededError as e:
            logger.error(f"\n{'='*60}")
            logger.error(str(e))
            logger.error(f"{'='*60}\n")
            logger.error("⚠️ 일일 한도 초과로 자동 다운로드를 중단합니다.")
            logger.error("   - 남은 씬은 이미지를 직접 업로드하거나")
            logger.error("   - 내일 다시 시도해주세요.")

        except Exception as e:
            logger.error(f"❌ 이미지 자동 생성/다운로드 중 오류 발생: {e}")

        # 최종 비용 요약
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 이미지 생성/다운로드 완료 - 총 {len(images)}개 이미지 확보")
        logger.info(f"   ✅ 성공: {success_count}개, ❌ 실패: {fail_count}개")
        logger.info(f"   🔍 images 딕셔너리 내용:")
        for scene_num, img_path in sorted(images.items()):
            logger.info(f"      씬 {scene_num}: {img_path.name}")

        if self.image_source == "google" and self.image_searcher:
            logger.info(f"{self.image_searcher.get_cost_summary()}")
        elif self.image_source == "dalle":
            total_cost = success_count * 0.080  # HD quality
            logger.info(f"💰 총 비용: ${total_cost:.2f} (약 ₩{total_cost * 1300:.0f})")

        logger.info(f"{'='*60}\n")

        return images

    def _generate_dalle_image(self, prompt: str, save_dir: Path, filename: str) -> Optional[Path]:
        """
        DALL-E 3로 이미지 생성 및 저장

        Args:
            prompt: 이미지 생성 프롬프트
            save_dir: 저장 디렉토리
            filename: 저장 파일명

        Returns:
            생성된 이미지 경로 (실패 시 None)
        """
        if not self.dalle_client:
            logger.error("❌ DALL-E 클라이언트가 초기화되지 않았습니다.")
            return None

        # aspect_ratio에 따라 이미지 크기 결정
        if self.aspect_ratio == "9:16":
            image_size = "1024x1792"  # 세로형 (숏폼)
        else:  # 16:9 or other
            image_size = "1792x1024"  # 가로형 (롱폼)

        logger.info(f"🎨 DALL-E 이미지 생성 크기: {image_size} ({self.aspect_ratio})")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 재시도 시 프롬프트 수정
                if attempt == 0:
                    current_prompt = prompt
                elif attempt == 1:
                    # 첫 번째 재시도: 간단하고 안전한 버전
                    current_prompt = f"A calm and peaceful scene depicting: {prompt[:100]}"
                    logger.info(f"🔄 Content filter 우회를 위해 프롬프트 단순화 (시도 {attempt + 1}/{max_retries})")
                else:
                    # 두 번째 재시도: 매우 일반적인 설명
                    current_prompt = "A beautiful, peaceful landscape with soft lighting"
                    logger.info(f"🔄 매우 일반적인 프롬프트로 재시도 (시도 {attempt + 1}/{max_retries})")

                if attempt > 0:
                    logger.info(f"   수정된 프롬프트: {current_prompt}")

                # DALL-E 3 API 호출
                response = self.dalle_client.images.generate(
                    model="dall-e-3",
                    prompt=current_prompt,
                    size=image_size,
                    quality="hd",
                    n=1
                )

                # 생성된 이미지 URL 가져오기
                image_url = response.data[0].url

                # 이미지 다운로드
                import requests
                logger.info(f"📥 DALL-E 이미지 다운로드 중...")
                img_response = requests.get(image_url, timeout=30)
                img_response.raise_for_status()

                # 파일 저장
                save_path = save_dir / filename
                save_path.parent.mkdir(parents=True, exist_ok=True)

                with open(save_path, 'wb') as f:
                    f.write(img_response.content)

                logger.info(f"✅ DALL-E 이미지 저장 완료: {save_path.name}")
                if attempt > 0:
                    logger.info(f"   (재시도 {attempt}회 끝에 성공)")
                return save_path

            except Exception as e:
                error_str = str(e)

                # Content policy violation 체크
                if 'content_policy_violation' in error_str or 'content filters' in error_str:
                    logger.warning(f"⚠️ Content filter에 걸림 (시도 {attempt + 1}/{max_retries})")

                    if attempt < max_retries - 1:
                        logger.info("   → 프롬프트를 수정하여 재시도합니다...")
                        continue
                    else:
                        logger.error(f"❌ {max_retries}회 재시도 후에도 Content filter 통과 실패")
                        return None
                else:
                    # 다른 에러는 즉시 반환
                    logger.error(f"❌ DALL-E 이미지 생성 실패: {error_str}")
                    return None

        return None

    def _log_dalle_cost_estimate(self, num_images: int):
        """
        DALL-E 3 비용 예측 로그 출력 (관리자에게만 표시)

        Args:
            num_images: 생성할 이미지 개수
        """
        # 관리자가 아니면 로그 출력 안 함
        if not self.is_admin:
            return

        # DALL-E 3 pricing
        # - Standard quality (1024x1024): $0.040 per image
        # - HD quality (1024x1792 or 1792x1024): $0.080 per image

        # aspect_ratio에 따라 이미지 크기 결정
        # - 9:16 (숏폼) -> 1024x1792 (세로형)
        # - 16:9 (롱폼) -> 1792x1024 (가로형)
        DALLE_COST_PER_IMAGE_HD = 0.080
        DALLE_COST_PER_IMAGE_STANDARD = 0.040

        # HD quality 기준으로 계산
        estimated_cost_hd = num_images * DALLE_COST_PER_IMAGE_HD
        estimated_cost_standard = num_images * DALLE_COST_PER_IMAGE_STANDARD

        logger.info(f"\n{'='*60}")
        logger.info(f"💰 DALL-E 3 이미지 생성 비용 예측 (관리자 전용)")
        # 이미지 크기 표시
        if self.aspect_ratio == "9:16":
            image_size_str = "1024x1792 (세로형 숏폼)"
        else:
            image_size_str = "1792x1024 (가로형 롱폼)"

        logger.info(f"{'='*60}")
        logger.info(f"📊 생성 예정 이미지: {num_images}개")
        logger.info(f"📐 이미지 크기: {image_size_str}")
        logger.info(f"💵 예상 비용 (HD {image_size_str.split()[0]}):        ${estimated_cost_hd:.2f} (약 ₩{estimated_cost_hd * 1300:.0f})")
        logger.info(f"💵 예상 비용 (Standard 1024x1024): ${estimated_cost_standard:.2f} (약 ₩{estimated_cost_standard * 1300:.0f})")
        logger.info(f"ℹ️  HD quality 사용 권장 ({self.aspect_ratio} 비율에 적합)")
        logger.info(f"{'='*60}\n")

    def _clean_script_for_tts(self, script: str) -> str:
        """TTS용 텍스트 정리 (백슬래시, 에러 메시지, 숫자 변환)"""
        import re

        cleaned = script

        # Remove all backslashes
        cleaned = cleaned.replace('\\', '')

        # Remove error messages
        cleaned = re.sub(r'\[Request interrupted by user\]', '', cleaned)
        cleaned = re.sub(r'\[.*?interrupted.*?\]', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[.*?error.*?\]', '', cleaned, flags=re.IGNORECASE)

        # Remove markdown
        cleaned = cleaned.replace('```', '')

        # Fix quotes
        cleaned = cleaned.replace('""', '"').replace("''", "'")

        # Convert numbers to Korean
        cleaned = self._convert_numbers_to_korean(cleaned)

        # Clean spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned

    def _convert_numbers_to_korean(self, text: str) -> str:
        """숫자를 한글로 변환 (3번 -> 세 번, 010-1234-5678 -> 공 일 공 ...)"""
        import re

        # 전화번호 패턴 처리 (010-1234-5678, 02-123-4567 등)
        def convert_phone_number(match):
            """전화번호를 한 글자씩 읽기"""
            phone = match.group(0)
            digits = re.sub(r'[^\d]', '', phone)
            digit_names = ['공', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
            result = ' '.join([digit_names[int(d)] for d in digits])
            return result

        # 전화번호 패턴 (010-xxxx-xxxx, 02-xxx-xxxx 등)
        phone_pattern = r'0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}'
        text = re.sub(phone_pattern, convert_phone_number, text)

        # 비밀번호/코드 패턴 처리
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
            if sino:
                ones = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구']
                tens = ['', '십', '이십', '삼십', '사십', '오십', '육십', '칠십', '팔십', '구십']

                if num == 0: return '영'
                if num < 10: return ones[num]
                elif num < 100:
                    return tens[num // 10] + (' ' + ones[num % 10] if num % 10 else '')
                elif num < 1000:
                    result = ('백' if num // 100 == 1 else ones[num // 100] + '백')
                    if num % 100: result += ' ' + num_to_korean(num % 100, sino=True)
                    return result
                elif num < 10000:
                    result = ('천' if num // 1000 == 1 else ones[num // 1000] + '천')
                    if num % 1000: result += ' ' + num_to_korean(num % 1000, sino=True)
                    return result
                elif num < 100000000:
                    result = num_to_korean(num // 10000, sino=True) + '만'
                    if num % 10000: result += ' ' + num_to_korean(num % 10000, sino=True)
                    return result
                else:
                    return str(num)
            else:
                native = ['', '하나', '둘', '셋', '넷', '다섯', '여섯', '일곱', '여덟', '아홉', '열']
                if num < 1 or num > 99: return num_to_korean(num, sino=True)
                if num <= 10: return native[num]
                elif num < 20: return '열' + (' ' + native[num - 10] if num > 10 else '')
                elif num < 100:
                    tens_native = ['', '', '스무', '서른', '마흔', '쉰', '예순', '일흔', '여든', '아흔']
                    result = tens_native[num // 10]
                    if num % 10: result += ' ' + native[num % 10]
                    return result
                else:
                    return num_to_korean(num, sino=True)

        def replace_number(match):
            num_str, unit = match.group(1), match.group(2) if match.group(2) else ''
            try:
                num = int(num_str)
                native_units = ['번', '번째', '개', '명', '마리', '살', '시']
                use_native = any(unit.startswith(u) for u in native_units) and num <= 99
                korean_num = num_to_korean(num, sino=not use_native)

                # 받침 탈락 처리: 셋→세, 넷→네, 스물→스무
                if unit and use_native:
                    if korean_num == '셋':
                        korean_num = '세'
                    elif korean_num == '넷':
                        korean_num = '네'
                    elif korean_num.startswith('셋 '):
                        korean_num = '세 ' + korean_num[2:]
                    elif korean_num.startswith('넷 '):
                        korean_num = '네 ' + korean_num[2:]

                return korean_num + (' ' + unit if unit else '')
            except ValueError:
                return match.group(0)

        pattern = r'(\d+)(번째|번|분|초|개|명|마리|살|시|등|위|년|월|일|회|차|층|대|권|장|곡|편|화|기|원|달러|킬로|미터|센티|그램|리터)?'
        return re.sub(pattern, replace_number, text)

    def _clean_narration(self, text: str) -> str:
        """나레이션 텍스트 정리 (명령어 및 불필요한 부분 제거)"""
        # 1. TTS용 텍스트 정리 (백슬래시, 에러 메시지, 숫자 변환)
        text = self._clean_script_for_tts(text)

        # 2. 대괄호 마커를 줄바꿈으로 변환

        # [무음 N초] → 숫자만큼 줄바꿈
        def replace_mute(match):
            num_str = match.group(1)
            if num_str:
                num = int(float(num_str))
                return '\n' * num
            return '\n'  # [무음] → 1회
        text = re.sub(r'\[무음\s*(\d+(?:\.\d+)?)?초?\]', replace_mute, text)

        # [침묵 N초] → N회 줄바꿈, 기본 3회
        def replace_silence(match):
            num_str = match.group(1)
            if num_str:
                num = int(float(num_str))
                return '\n' * num
            return '\n' * 3  # [침묵] → 3회
        text = re.sub(r'\[침묵\s*(\d+(?:\.\d+)?)?초?\]', replace_silence, text)

        # [pause N초] → N회 줄바꿈
        def replace_pause(match):
            num_str = match.group(1)
            if num_str:
                num = int(float(num_str))
                return '\n' * num
            return '\n'
        text = re.sub(r'\[pause\s*(\d+(?:\.\d+)?)?초?\]', replace_pause, text)

        # [회상] → 3회 줄바꿈
        text = re.sub(r'\[회상\]', '\n\n\n', text)

        # 나머지 대괄호는 모두 제거 (공간, 행동, 내면 등)
        text = re.sub(r'\[([^\]]+)\]', '', text)

        # 대화 부분 제거는 하지 않음 - 서사적 텍스트는 대화를 포함함
        # 주석 처리: text = re.sub(r'[가-힣]+:\s*"[^"]*"', '', text)
        # 주석 처리: text = re.sub(r'[가-힣]+:\s*[^\n/]+(?=/|$)', '', text)

        # / 구분자 제거
        text = text.replace(' / ', ' ')

        # 중복 공백 정리 (줄바꿈은 유지)
        text = re.sub(r' +', ' ', text)
        text = text.strip()

        return text

    def _add_natural_pauses(self, text: str) -> str:
        """구두점 뒤에 줄바꿈을 추가하여 자연스러운 쉼 효과"""
        import re

        # 먼저 연속된 구두점 조합 처리 (중복 줄바꿈 방지)
        # ." → ."\n (한 번만)
        text = text.replace('."', '."\n')
        # ?" → ?"\n (한 번만)
        text = text.replace('?"', '?"\n')
        # !" → !"\n (한 번만)
        text = text.replace('!"', '!"\n')

        # ... 뒤에 줄바꿈 추가 (가장 긴 쉼)
        text = text.replace('...', '...\n')

        # 남은 " 뒤에 줄바꿈 추가 (이미 처리된 것은 제외)
        text = re.sub(r'"(?!\n)', '"\n', text)

        # ? 뒤에 줄바꿈 추가 (이미 처리된 것은 제외)
        text = re.sub(r'\?(?!\n)', '?\n', text)

        # ! 뒤에 줄바꿈 추가 (이미 처리된 것은 제외)
        text = re.sub(r'!(?!\n)', '!\n', text)

        # , 뒤에 줄바꿈 추가 (짧은 쉼)
        text = text.replace(',', ',\n')

        # . 뒤에 줄바꿈 추가 (단, 숫자 뒤나 이미 처리된 것은 제외)
        text = re.sub(r'\.(?!\d)(?!\n)', '.\n', text)

        return text

    async def _generate_tts(self, text: str, output_path: Path) -> tuple:
        """Edge TTS로 음성 생성 + 단어별 타임스탬프 추출"""
        logger.info(f"TTS 생성 중: {output_path.name}")

        # 텍스트 정리
        clean_text = self._clean_narration(text)

        if not clean_text:
            logger.warning("텍스트가 비어있어 기본 메시지 사용")
            clean_text = "무음"

        # 구두점에 쉼표 추가 (자연스러운 쉼표 효과)
        tts_text = self._add_natural_pauses(clean_text)

        # Edge TTS로 생성하면서 타임스탬프 수집
        # rate: -15%로 설정하여 약간 천천히 말하게 함
        communicate = edge_tts.Communicate(tts_text, self.voice, rate='-15%')

        word_timings = []
        sentence_timings = []
        audio_data = b""
        chunk_types_seen = set()

        async for chunk in communicate.stream():
            chunk_type = chunk.get("type", "unknown")
            chunk_types_seen.add(chunk_type)

            if chunk_type == "audio":
                audio_data += chunk["data"]
            elif chunk_type == "WordBoundary":
                # 단어별 타임스탬프 저장 (이상적)
                word_timings.append({
                    "word": chunk["text"],
                    "start": chunk["offset"] / 10_000_000.0,
                    "end": (chunk["offset"] + chunk["duration"]) / 10_000_000.0
                })
            elif chunk_type == "SentenceBoundary":
                # 문장별 타임스탬프 저장 (폴백용)
                sentence_timings.append({
                    "text": chunk.get("text", ""),
                    "start": chunk["offset"] / 10_000_000.0,
                    "end": (chunk["offset"] + chunk["duration"]) / 10_000_000.0 if "duration" in chunk else None
                })

        # WordBoundary가 없으면 SentenceBoundary 사용
        if not word_timings and sentence_timings:
            logger.info(f"WordBoundary 없음, SentenceBoundary 사용: {len(sentence_timings)}개 문장")
            # 각 문장을 단어로 분할
            for sent in sentence_timings:
                text = sent["text"].strip()
                if not text:
                    continue
                words = text.split()
                if not words:
                    continue

                # 문장 시간을 단어 개수로 균등 분배
                sent_duration = (sent["end"] - sent["start"]) if sent["end"] else 1.0
                time_per_word = sent_duration / len(words)

                for i, word in enumerate(words):
                    word_start = sent["start"] + (i * time_per_word)
                    word_end = word_start + time_per_word
                    word_timings.append({
                        "word": word,
                        "start": word_start,
                        "end": word_end
                    })

        if not word_timings:
            logger.warning(f"타임스탬프 없음! Chunk types: {chunk_types_seen}")

        # 오디오 파일 저장
        with open(output_path, "wb") as f:
            f.write(audio_data)

        # 오디오 길이 가져오기
        try:
            audio_clip = AudioFileClip(str(output_path))
            duration = audio_clip.duration
            audio_clip.close()
        except Exception as e:
            logger.warning(f"오디오 길이 측정 실패, 기본값 1초 사용: {e}")
            duration = 1.0

        if word_timings:
            logger.info(f"TTS 생성 완료: {duration:.2f}초, 단어 {len(word_timings)}개 (타임스탬프 있음)")
        else:
            logger.warning(f"TTS 생성 완료: {duration:.2f}초, 타임스탬프 없음 (대본 기반으로 폴백 예정)")

        return duration, word_timings

    def _create_scene_video(self, scene_num: int, image_path: Path,
                           audio_path: Path, output_path: Path) -> Optional[Path]:
        """씬 비디오 생성 (이미지 + 오디오) - FFmpeg 직접 사용"""
        try:
            logger.info(f"씬 {scene_num} 비디오 생성 중...")

            # FFmpeg 명령어로 이미지 + 오디오 결합 (초고속)
            # -loop 1: 이미지 반복
            # -i: 입력 파일
            # -shortest: 오디오 길이만큼만
            # -c:v: 비디오 코덱 (GPU 가속)
            # -c:a: 오디오 코덱
            # -pix_fmt yuv420p: 호환성
            # -vf scale: 리스케일 + 레터박스

            cmd = [
                'ffmpeg',
                '-loop', '1',  # 이미지 반복
                '-i', str(image_path.resolve()),  # 입력 이미지 (절대 경로)
                '-i', str(audio_path.resolve()),  # 입력 오디오 (절대 경로)
                '-vf', f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black",  # 리스케일 + 레터박스
                '-c:v', self.video_codec,  # GPU 가속 코덱
                '-preset', self.codec_preset,  # 프리셋
                '-c:a', 'aac',  # 오디오 코덱
                '-shortest',  # 오디오 길이만큼
                '-pix_fmt', 'yuv420p',  # 호환성
                '-y',  # 덮어쓰기
                str(output_path.resolve())  # 출력 경로 (절대 경로)
            ]

            # FFmpeg 실행 (UTF-8 인코딩)
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')

            logger.info(f"씬 {scene_num} 비디오 생성 완료: {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            # GPU 인코더 실패 시 CPU 폴백
            if 'h264_nvenc' in str(e.stderr) or 'nvenc' in str(e.stderr):
                logger.warning(f"씬 {scene_num} GPU 인코더 실패, CPU 인코더로 재시도...")

                # CPU 인코더로 재시도
                cmd_cpu = [
                    'ffmpeg',
                    '-loop', '1',
                    '-i', str(image_path.resolve()),
                    '-i', str(audio_path.resolve()),
                    '-vf', f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black",
                    '-c:v', 'libx264',  # CPU 인코더
                    '-preset', 'ultrafast',
                    '-c:a', 'aac',
                    '-shortest',
                    '-pix_fmt', 'yuv420p',
                    '-y',
                    str(output_path.resolve())
                ]

                try:
                    result = subprocess.run(cmd_cpu, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                    logger.info(f"씬 {scene_num} 비디오 생성 완료 (CPU): {output_path}")
                    return output_path
                except subprocess.CalledProcessError as e2:
                    logger.error(f"씬 {scene_num} CPU 인코더도 실패: {e2.stderr}")
                    return None
            else:
                logger.error(f"씬 {scene_num} FFmpeg 실행 실패: {e.stderr}")
                return None
        except Exception as e:
            logger.error(f"씨 {scene_num} 비디오 생성 실패: {e}")
            return None

    def _create_scene_video_with_subtitles(self, scene_num: int, image_path: Path,
                                           audio_path: Path, output_path: Path,
                                           narration: str, audio_duration: float,
                                           word_timings: list = None) -> Optional[Path]:
        """씬 비디오 생성 (이미지 + 오디오 + 자막 포함) - FFmpeg 직접 사용"""
        try:
            logger.info(f"씬 {scene_num} 비디오 + 자막 생성 중...")

            # Edge TTS 타임스탬프로 ASS 자막 파일 생성 (또는 대본 기반 폴백)
            srt_path = audio_path.with_suffix('.srt')
            ass_path = self._create_srt_with_timings(word_timings or [], srt_path, narration, audio_duration, max_chars_per_line=22)

            # FFmpeg ass 필터에는 파일명만 전달 (같은 디렉토리에 있음)
            ass_filename = ass_path.name
            logger.info(f"DEBUG 씬 {scene_num}: ass_filename = {ass_filename}")

            # FFmpeg 명령어: 이미지 + 오디오 + 자막을 한번에 처리 (ass 필터 사용)
            cmd = [
                'ffmpeg',
                '-loop', '1',
                '-i', str(image_path.resolve()),
                '-i', str(audio_path.resolve()),
                '-vf', f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,ass={ass_filename}",
                '-c:v', self.video_codec,
                '-preset', self.codec_preset,
                '-c:a', 'aac',
                '-shortest',
                '-pix_fmt', 'yuv420p',
                '-y',
                str(output_path.resolve())
            ]

            logger.info(f"DEBUG 씬 {scene_num}: FFmpeg 명령어 = {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore', cwd=str(output_path.parent))
            if result.stderr and 'error' in result.stderr.lower():
                logger.warning(f"FFmpeg 경고 (씬 {scene_num}): {result.stderr[:500]}")
            logger.info(f"씬 {scene_num} 비디오 + 자막 생성 완료: {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            # GPU 인코더 실패 시 CPU 폴백 (stderr 확인 불가하므로 파일 크기로 판단)
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.warning(f"씬 {scene_num} GPU 인코더 실패, CPU 인코더로 재시도...")

                # ASS 자막 파일 경로 (이미 생성됨)
                srt_path = audio_path.with_suffix('.srt')
                ass_path = srt_path.with_suffix('.ass')
                # FFmpeg ass 필터에는 파일명만 전달
                ass_filename = ass_path.name

                cmd_cpu = [
                    'ffmpeg',
                    '-loop', '1',
                    '-i', str(image_path.resolve()),
                    '-i', str(audio_path.resolve()),
                    '-vf', f"scale={self.width}:{self.height}:force_original_aspect_ratio=decrease,pad={self.width}:{self.height}:(ow-iw)/2:(oh-ih)/2:black,ass={ass_filename}",
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-c:a', 'aac',
                    '-shortest',
                    '-pix_fmt', 'yuv420p',
                    '-y',
                    str(output_path.resolve())
                ]

                try:
                    result_cpu = subprocess.run(cmd_cpu, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore', cwd=str(output_path.parent))
                    if result_cpu.stderr and 'error' in result_cpu.stderr.lower():
                        logger.warning(f"FFmpeg CPU 경고 (씬 {scene_num}): {result_cpu.stderr[:500]}")
                    logger.info(f"씬 {scene_num} CPU 인코더로 성공")
                    return output_path
                except subprocess.CalledProcessError as e2:
                    logger.error(f"씬 {scene_num} CPU 인코더도 실패: {e2.stderr if hasattr(e2, 'stderr') else str(e2)}")
                    return None
            else:
                logger.error(f"씬 {scene_num} FFmpeg 실행 실패")
                return None
        except Exception as e:
            logger.error(f"씬 {scene_num} 비디오 + 자막 생성 실패: {e}")
            return None

    def _create_scene_video_old_moviepy(self, scene_num: int, image_path: Path,
                           audio_path: Path, output_path: Path) -> Optional[Path]:
        """씬 비디오 생성 (이미지 + 오디오) - MoviePy 버전 (느림, 백업용)"""
        try:
            logger.info(f"씬 {scene_num} 비디오 생성 중...")

            # 오디오 클립 생성 및 길이 가져오기
            audio_clip = AudioFileClip(str(audio_path))
            duration = audio_clip.duration

            # 이미지 클립 생성
            img_clip = ImageClip(str(image_path), duration=duration)

            # 원본 이미지 크기
            orig_w, orig_h = img_clip.size
            logger.info(f"원본 이미지 크기: {orig_w}x{orig_h}, 목표 크기: {self.width}x{self.height}")

            # 비율 유지하면서 화면에 맞추기 (크롭 없이, 레터박스로)
            target_ratio = self.width / self.height
            img_ratio = orig_w / orig_h

            if img_ratio > target_ratio:
                # 이미지가 더 넓음 - 너비를 화면에 맞추고 위아래 검은 여백
                img_clip = img_clip.resize(width=self.width)
            else:
                # 이미지가 더 높음 - 높이를 화면에 맞추고 좌우 검은 여백
                img_clip = img_clip.resize(height=self.height)

            # 중앙 정렬 (검은 배경에 이미지 배치)
            from moviepy.editor import ColorClip, CompositeVideoClip
            bg = ColorClip(size=(self.width, self.height), color=(0, 0, 0), duration=duration)
            img_clip = CompositeVideoClip([bg, img_clip.set_position('center')], size=(self.width, self.height))

            # 비디오 + 오디오 결합
            video = img_clip.set_audio(audio_clip)

            # 저장 (GPU 가속 인코딩)
            video.write_videofile(
                str(output_path),
                fps=24,
                codec=self.video_codec,  # GPU 인코더 또는 CPU
                audio_codec='aac',
                preset=self.codec_preset,  # 인코더에 맞는 프리셋
                threads=4,  # 멀티스레딩 활성화
                logger=None
            )

            # 메모리 정리
            img_clip.close()
            audio_clip.close()
            video.close()

            logger.info(f"씬 {scene_num} 비디오 생성 완료: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"씬 {scene_num} 비디오 생성 실패: {e}")
            return None

    def _combine_videos(self, video_paths: List[Path], output_path: Path, start_time: float) -> Optional[Path]:
        """여러 씬 비디오를 하나로 결합 - simple_concat.py 호출"""
        import sys

        video_folder = output_path.parent

        logger.info(f"비디오 결합 시작: {len(video_paths)}개 씬")

        # simple_concat.py를 새로운 Python 프로세스로 실행
        script_path = Path(__file__).parent / "simple_concat.py"
        cmd = [
            sys.executable,  # 현재 Python 실행 파일
            str(script_path),
            str(video_folder),
            output_path.name
        ]

        logger.info(f"simple_concat.py 실행: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')

        if result.stdout:
            logger.info(f"simple_concat.py 출력:\n{result.stdout}")

        if result.stderr:
            logger.warning(f"simple_concat.py 에러:\n{result.stderr}")

        if result.returncode != 0:
            logger.error(f"simple_concat.py 실패 (종료 코드: {result.returncode})")
            if result.stderr:
                logger.error(f"에러 메시지:\n{result.stderr}")
            return None

        # 총 수행 시간
        elapsed_time = time() - start_time
        minutes = int(elapsed_time // 60)
        seconds = int(elapsed_time % 60)
        logger.info(f"비디오 결합 완료: {output_path}")
        logger.info(f"총 수행 시간: {minutes}분 {seconds}초")

        return output_path

    def _backup_previous_videos(self):
        """기존 generated_videos 폴더를 backup으로 이동 (파일 사용 중이면 건너뛰기)"""
        import shutil
        from datetime import datetime

        output_folder = self.folder_path / "generated_videos"

        # generated_videos 폴더가 있고, 내용이 있으면 백업
        if output_folder.exists() and any(output_folder.iterdir()):
            try:
                # backup 폴더 생성
                backup_root = self.folder_path / "backup"
                backup_root.mkdir(exist_ok=True)

                # 백업 폴더명: backup/YYYYMMDD_HHMMSS
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_folder = backup_root / timestamp

                # 이동
                logger.info(f"기존 generated_videos를 백업합니다: {backup_folder.name}")
                shutil.move(str(output_folder), str(backup_folder))
                logger.info(f"백업 완료: {backup_folder}")
            except PermissionError as e:
                # 파일이 사용 중이면 백업을 건너뛰고 기존 폴더 유지
                logger.warning(f"⚠️  백업 실패 (파일 사용 중)")
                logger.warning(f"   기존 generated_videos 폴더를 유지하고 계속 진행합니다.")
                logger.warning(f"   💡 비디오 플레이어나 탐색기를 닫으면 백업이 가능합니다.")
                # 폴더는 그대로 두고 내용물만 삭제 시도
                try:
                    for item in output_folder.iterdir():
                        try:
                            if item.is_file():
                                item.unlink()
                            elif item.is_dir():
                                shutil.rmtree(item)
                        except PermissionError:
                            logger.warning(f"   파일 삭제 실패 (사용 중): {item.name}")
                            continue
                except Exception as cleanup_error:
                    logger.warning(f"   폴더 정리 중 오류 무시하고 계속")
                    pass

    async def create_all_videos(self, combine: bool = True) -> Optional[Path]:
        """모든 씬의 비디오 생성 및 결합"""
        start_time = time()

        # 기존 generated_videos 폴더 백업
        self._backup_previous_videos()

        # 이미지 찾기
        images = self._find_images()

        if not images:
            logger.error("이미지를 찾을 수 없습니다.")
            return None

        # scenes 가져오기
        scenes = self.story_data.get("scenes", [])

        if not scenes:
            logger.error("story.json에 scenes가 없습니다.")
            return None

        # 기존 generated_videos 폴더 백업 건너뜀 (파일 덮어쓰기 허용)

        # 출력 폴더 생성 (백업 후 새로 생성)
        output_folder = self.folder_path / "generated_videos"
        output_folder.mkdir(exist_ok=True)

        # 1단계: TTS 생성 (병렬 처리)
        logger.info("=" * 70)
        logger.info("1단계: TTS 음성 생성 (병렬 처리)")
        logger.info("=" * 70)

        tts_tasks = []
        scene_data_list = []

        for scene in scenes:
            # scene_number가 없으면 scene_id에서 추출
            scene_num = scene.get("scene_number")
            if scene_num is None:
                scene_id = scene.get("scene_id", "")
                # scene_01_main, scene_02_main 등에서 번호 추출
                import re
                match = re.search(r'scene_(\d+)', scene_id)
                if match:
                    scene_num = int(match.group(1))
                else:
                    logger.warning(f"씬 ID '{scene_id}'에서 번호를 추출할 수 없습니다. 건너뜀.")
                    continue

            narration = scene.get("narration") or scene.get("content", "")

            # scene_num이 0이거나 이미지가 없으면 건너뜀
            if scene_num == 0:
                logger.info(f"씬 {scene_num} (인트로/폭탄씬): 이미지 없이 건너뜀.")
                continue

            if scene_num not in images:
                logger.warning(f"씬 {scene_num}의 이미지가 없습니다. 건너뜀.")
                continue

            # 나레이션 텍스트 저장
            narration_txt_path = output_folder / f"scene_{scene_num:02d}_narration.txt"
            clean_narration = self._clean_narration(narration)
            with open(narration_txt_path, 'w', encoding='utf-8') as f:
                f.write(clean_narration)

            # TTS 태스크 생성
            audio_path = output_folder / f"scene_{scene_num:02d}_audio.mp3"
            tts_tasks.append(self._generate_tts(narration, audio_path))

            scene_data_list.append({
                'scene_num': scene_num,
                'image_path': images[scene_num],
                'audio_path': audio_path,
                'clean_narration': clean_narration
            })

        # TTS 병렬 생성 (8개씩 제한) - 타임스탬프도 함께 받음!
        logger.info(f"⚡ TTS 병렬 생성: 최대 8개씩 동시 처리 (타임스탬프 포함)")

        tts_results = []
        batch_size = 8
        for i in range(0, len(tts_tasks), batch_size):
            batch = tts_tasks[i:i+batch_size]
            batch_results = await asyncio.gather(*batch)
            tts_results.extend(batch_results)
            logger.info(f"TTS 배치 완료: {i+1}~{min(i+len(batch), len(tts_tasks))}/{len(tts_tasks)}")

        logger.info(f"TTS 생성 완료: {len(tts_tasks)}개")

        # 오디오 길이와 타임스탬프를 scene_data에 저장
        for i, scene_data in enumerate(scene_data_list):
            duration, word_timings = tts_results[i]
            scene_data['audio_duration'] = duration
            scene_data['word_timings'] = word_timings  # Edge TTS 타임스탬프!

        # 2단계: 건너뜀 (Whisper 대신 대본 사용)
        # Whisper 음성 인식 없이 대본을 직접 사용하므로 훨씬 빠름!

        # 3단계: 비디오 생성 + 자막 추가 (병렬 처리)
        logger.info("=" * 70)
        logger.info("3단계: 비디오 생성 및 자막 추가")
        logger.info("=" * 70)

        # 인코더 정보 표시
        encoder_type = "GPU 가속" if self.video_codec != 'libx264' else "CPU"
        logger.info(f"🎬 비디오 인코더: {self.video_codec} ({encoder_type})")
        logger.info(f"📊 총 {len(scene_data_list)}개 씬 처리 예정")

        # 시스템에 무리 안 가도록 워커 수 제한 (CPU 코어의 75%, 최소 2, 최대 4)
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(2, min(4, (cpu_count * 3) // 4))
        logger.info(f"⚡ 병렬 처리: {max_workers}개 워커 (CPU 코어: {cpu_count}개)")
        logger.info("=" * 70)

        scene_videos = []
        all_narrations = []

        # 병렬 처리 함수
        def process_scene(idx, scene_data):
            scene_num = scene_data['scene_num']
            image_path = scene_data['image_path']
            audio_path = scene_data['audio_path']
            clean_narration = scene_data['clean_narration']

            progress = f"[{idx}/{len(scene_data_list)}]"
            logger.info(f"\n{progress} 씬 {scene_num} 처리 중...")

            # 비디오 생성 (자막 포함)
            video_path = output_folder / f"scene_{scene_num:02d}.mp4"
            logger.info(f"{progress} 씬 {scene_num} 비디오 생성 중... ({encoder_type})")

            # 자막 추가 여부에 따라 다르게 처리
            if self.add_subtitles:
                audio_duration = scene_data.get('audio_duration', 1.0)
                word_timings = scene_data.get('word_timings', [])  # Edge TTS 타임스탬프
                result = self._create_scene_video_with_subtitles(
                    scene_num, image_path, audio_path, video_path,
                    clean_narration, audio_duration, word_timings
                )
            else:
                result = self._create_scene_video(scene_num, image_path, audio_path, video_path)

            if result:
                logger.info(f"{progress} ✅ 씬 {scene_num} 완료!")
                return (scene_num, result, clean_narration)
            return None

        # 병렬 실행
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_scene, idx, scene_data): idx
                      for idx, scene_data in enumerate(scene_data_list, 1)}

            for future in as_completed(futures):
                result = future.result()
                if result:
                    scene_num, video_path, narration = result
                    scene_videos.append((scene_num, video_path))
                    all_narrations.append(narration)

        # 씬 번호 순서로 정렬
        scene_videos.sort(key=lambda x: x[0])
        scene_videos = [path for _, path in scene_videos]

        if not scene_videos:
            logger.error("생성된 씬 비디오가 없습니다.")
            return None

        # 전체 나레이션 저장
        full_narration_path = output_folder / "full_narration.txt"
        with open(full_narration_path, 'w', encoding='utf-8') as f:
            f.write('\n\n'.join(all_narrations))
        logger.info(f"전체 나레이션 저장: {full_narration_path}")

        # 결합
        if combine and len(scene_videos) > 1:
            # title이 최상위에 있거나 metadata 안에 있을 수 있음
            title = self.story_data.get("title")
            if not title and "metadata" in self.story_data:
                title = self.story_data["metadata"].get("title")
            if not title:
                title = "video"

            # 파일명으로 사용 가능하도록 특수문자 제거
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '_', '-', '.')).strip()
            safe_title = safe_title.replace(' ', '_')
            final_path = output_folder / f"{safe_title}.mp4"
            logger.info(f"📝 최종 영상 제목: {title} → {safe_title}.mp4")
            return self._combine_videos(scene_videos, final_path, start_time)
        elif scene_videos:
            logger.info(f"씬 비디오 {len(scene_videos)}개 생성 완료 (결합 안 함)")
            return scene_videos[0]

        return None

    async def _generate_word_timestamps_async(self, audio_path: Path) -> list:
        """Whisper로 음성 분석하여 단어별 타임스탬프 생성 (async 버전)"""
        import concurrent.futures

        def _run_whisper(audio_path_str):
            try:
                import whisper

                logger.info(f"Whisper 분석 중: {Path(audio_path_str).name}")

                # Whisper 모델 로드 (base 모델: 빠르고 충분히 정확함)
                model = whisper.load_model("base")

                # 음성 인식 실행 (세그먼트 단위로 타임스탬프 추출)
                result = model.transcribe(
                    audio_path_str,
                    language="ko",
                    verbose=False,
                    fp16=False  # CPU에서 FP16 경고 방지
                )

                # 세그먼트별 타임스탬프를 단어 단위로 변환
                word_segments = []
                for segment in result.get("segments", []):
                    # 세그먼트 텍스트를 단어로 분리
                    text = segment.get("text", "").strip()
                    words = text.split()

                    if not words:
                        continue

                    # 세그먼트 시간을 단어 개수로 나눠서 근사치 계산
                    start_time = segment.get("start", 0)
                    end_time = segment.get("end", 0)
                    duration = end_time - start_time
                    time_per_word = duration / len(words) if words else 0

                    for i, word in enumerate(words):
                        word_start = start_time + (i * time_per_word)
                        word_end = start_time + ((i + 1) * time_per_word)
                        word_segments.append({
                            "word": word.strip(),
                            "start": word_start,
                            "end": word_end
                        })

                logger.info(f"Whisper 완료: {Path(audio_path_str).name} - {len(word_segments)}개 단어")
                return word_segments

            except Exception as e:
                logger.error(f"Whisper 분석 실패 ({Path(audio_path_str).name}): {e}")
                import traceback
                logger.error(traceback.format_exc())
                # 자막 생성 실패 시 예외를 발생시켜 영상 제작 중단
                raise RuntimeError(f"자막 생성 실패: {Path(audio_path_str).name} - {e}")

        # ThreadPoolExecutor로 병렬 실행
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            return await loop.run_in_executor(executor, _run_whisper, str(audio_path))

    def _generate_word_timestamps(self, audio_path: Path) -> list:
        """Whisper로 음성 분석하여 세그먼트별 타임스탬프 생성 (동기 버전)"""
        try:
            import whisper

            logger.info(f"Whisper로 음성 분석 중: {audio_path.name}")

            # Whisper 모델 로드 (base 모델: 빠르고 충분히 정확함)
            model = whisper.load_model("base")

            # 음성 인식 실행
            result = model.transcribe(
                str(audio_path),
                language="ko",
                verbose=False,
                fp16=False  # CPU에서 FP16 경고 방지
            )

            # 세그먼트별 타임스탬프 추출 후 단어로 분할
            word_segments = []

            if not result or "segments" not in result:
                logger.warning("Whisper가 세그먼트를 반환하지 않음")
                return []

            for segment in result.get("segments", []):
                text = segment.get("text", "").strip()
                start_time = segment.get("start", 0.0)
                end_time = segment.get("end", 0.0)

                if not text:
                    continue

                # 세그먼트 텍스트를 단어로 분할
                words = text.split()
                if not words:
                    continue

                # 각 단어에 균등하게 시간 분배
                duration_per_word = (end_time - start_time) / len(words)

                for i, word in enumerate(words):
                    word_start = start_time + (i * duration_per_word)
                    word_end = word_start + duration_per_word

                    word_segments.append({
                        "word": word.strip(),
                        "start": word_start,
                        "end": word_end
                    })

            logger.info(f"단어 {len(word_segments)}개의 타임스탬프 추출 완료")
            return word_segments

        except Exception as e:
            logger.error(f"Whisper 분석 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # 자막 생성 실패 시 예외를 발생시켜 영상 제작 중단
            raise RuntimeError(f"자막 생성 실패 (Fallback): {audio_path.name} - {e}")

    def _create_srt_with_timings(self, word_timings: list, srt_path: Path, narration: str, audio_duration: float, max_chars_per_line: int = 22):
        """Edge TTS 타임스탬프 또는 대본 기반 ASS 자막 생성"""
        try:
            # Edge TTS에서 받은 단어별 타임스탬프 사용
            word_segments = word_timings

            if not word_segments:
                logger.warning("타임스탬프가 비어있음 → 대본 기반 자막으로 폴백")
                return self._create_srt_from_script(narration, audio_duration, srt_path, max_chars_per_line)

            logger.info(f"Edge TTS 타임스탬프로 자막 생성 중... ({len(word_segments)}개 단어)")

            # 단어들을 max_chars_per_line에 맞춰 그룹화
            subtitles = []
            current_text = ""
            current_start = None
            current_end = None

            MIN_REMAINING_CHARS = 5

            for i, word_info in enumerate(word_segments):
                word = word_info["word"]
                start = word_info["start"]
                end = word_info["end"]

                # 빈 단어는 건너뛰기
                if not word.strip():
                    continue

                # 첫 단어면 시작 시간 설정
                if current_start is None:
                    current_start = start

                # 다음 텍스트 계산
                next_text = current_text + (" " if current_text else "") + word

                # 남은 단어들 계산
                remaining_words = word_segments[i+1:]
                remaining_text = " ".join([w["word"] for w in remaining_words]) if remaining_words else ""

                # 스마트 줄바꿈 로직
                if len(next_text) > max_chars_per_line and current_text:
                    # 남은 글자가 너무 적으면 현재 라인에 포함
                    if len(remaining_text) > 0 and len(remaining_text) < MIN_REMAINING_CHARS:
                        current_text = next_text + (" " + remaining_text if remaining_text else "")
                        # 남은 모든 단어의 끝 시간 찾기
                        if remaining_words:
                            current_end = remaining_words[-1]["end"]
                        else:
                            current_end = end

                        subtitles.append({
                            "start": current_start,
                            "end": current_end,
                            "text": current_text.strip()
                        })
                        break  # 모든 단어 처리 완료
                    else:
                        # 정상적으로 줄바꿈
                        subtitles.append({
                            "start": current_start,
                            "end": end,
                            "text": current_text.strip()
                        })
                        current_text = word
                        current_start = start
                        current_end = end
                else:
                    current_text = next_text
                    current_end = end

            # 남은 텍스트 처리
            if current_text:
                subtitles.append({
                    "start": current_start,
                    "end": current_end,
                    "text": current_text.strip()
                })

            # 자막이 겹치지 않도록 시간 조정
            for i in range(len(subtitles) - 1):
                current_sub = subtitles[i]
                next_sub = subtitles[i + 1]

                # 현재 자막이 다음 자막과 겹치면 현재 자막 종료 시간을 다음 자막 시작 전으로 조정
                if current_sub["end"] > next_sub["start"]:
                    # 0.05초 간격 두기
                    current_sub["end"] = max(current_sub["start"] + 0.1, next_sub["start"] - 0.05)

            # ASS 파일 작성
            ass_path = srt_path.with_suffix('.ass')

            with open(ass_path, 'w', encoding='utf-8') as f:
                # ASS 헤더
                f.write("[Script Info]\n")
                f.write("ScriptType: v4.00+\n")
                f.write("PlayResX: 1920\n")
                f.write("PlayResY: 1080\n\n")

                # 스타일 정의 - NanumGothic 96pt, 맨 하단
                f.write("[V4+ Styles]\n")
                f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
                f.write("Style: Default,NanumGothic,96,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,20,1\n\n")

                # 이벤트 (자막) - audio_duration을 초과하는 자막 필터링
                f.write("[Events]\n")
                f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

                filtered_subtitles = []
                for sub in subtitles:
                    # audio_duration을 초과하는 자막은 제외
                    if sub["start"] < audio_duration:
                        # 끝 시간이 duration을 초과하면 duration으로 잘라냄
                        end_time_adjusted = min(sub["end"], audio_duration)
                        filtered_subtitles.append({
                            "start": sub["start"],
                            "end": end_time_adjusted,
                            "text": sub["text"]
                        })

                for sub in filtered_subtitles:
                    start_time = self._format_ass_timestamp(sub["start"])
                    end_time = self._format_ass_timestamp(sub["end"])
                    text = sub["text"].replace('\n', '\\N')
                    f.write(f"Dialogue: 0,{start_time},{end_time},Default,,0,0,0,,{text}\n")

            logger.info(f"Edge TTS 타임스탬프 기반 ASS 자막 완료: {len(filtered_subtitles)}개 라인 (duration: {audio_duration:.2f}초)")
            return ass_path

        except Exception as e:
            logger.error(f"자막 생성 실패: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise RuntimeError(f"자막 생성 실패: {e}")

    def _create_srt_from_script(self, narration: str, audio_duration: float, srt_path: Path, max_chars_per_line: int = 22):
        """대본을 기반으로 SRT 자막 생성 (Whisper 없이)"""
        if not narration or not narration.strip():
            raise RuntimeError("자막 생성 실패: 대본이 비어있습니다.")

        # 대본을 문장으로 분리 (마침표, 느낌표, 물음표 기준)
        import re
        sentences = re.split(r'([.!?。！？])', narration)

        # 분리된 구두점을 앞 문장에 붙이기
        combined_sentences = []
        for i in range(0, len(sentences)-1, 2):
            if i+1 < len(sentences):
                combined_sentences.append((sentences[i] + sentences[i+1]).strip())

        # 마지막 문장 처리
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            combined_sentences.append(sentences[-1].strip())

        # 문장이 없으면 전체 텍스트를 하나의 문장으로
        if not combined_sentences:
            combined_sentences = [narration.strip()]

        # 전체 글자 수 계산 (공백 포함)
        total_text = " ".join(combined_sentences)
        total_chars = len(total_text)
        time_per_char = audio_duration / total_chars if total_chars > 0 else 0

        # 각 문장을 22자 단위로 분할 (글자 수 기반 타이밍)
        subtitles = []
        current_time = 0.0

        MIN_REMAINING_CHARS = 5  # 남은 글자가 이보다 적으면 현재 라인에 포함

        for sentence in combined_sentences:
            # 문장을 단어로 분리
            words = sentence.split()
            if not words:
                continue

            current_text = ""
            for i, word in enumerate(words):
                next_text = current_text + (" " if current_text else "") + word

                # 다음 단어까지 포함하면 얼마나 남는지 계산
                remaining_words = words[i+1:]
                remaining_text = " ".join(remaining_words) if remaining_words else ""

                # 스마트 줄바꿈 로직
                if len(next_text) > max_chars_per_line and current_text:
                    # 남은 글자가 너무 적으면 (1-2글자) 현재 라인에 포함
                    if len(remaining_text) > 0 and len(remaining_text) < MIN_REMAINING_CHARS:
                        # 현재 단어를 포함하고 줄바꿈 (다음 단어들도 함께)
                        current_text = next_text + (" " + remaining_text if remaining_text else "")
                        duration = len(current_text) * time_per_char
                        end_time = current_time + duration
                        subtitles.append({
                            "start": current_time,
                            "end": end_time,
                            "text": current_text.strip()
                        })
                        current_text = ""
                        current_time = end_time
                        break  # 이 문장 끝
                    else:
                        # 정상적으로 줄바꿈
                        duration = len(current_text) * time_per_char
                        end_time = current_time + duration
                        subtitles.append({
                            "start": current_time,
                            "end": end_time,
                            "text": current_text.strip()
                        })
                        current_text = word
                        current_time = end_time
                else:
                    current_text = next_text

            # 남은 텍스트 처리
            if current_text:
                duration = len(current_text) * time_per_char
                end_time = current_time + duration
                subtitles.append({
                    "start": current_time,
                    "end": end_time,
                    "text": current_text.strip()
                })
                current_time = end_time

        # ASS 파일 작성 (스타일 포함)
        ass_path = srt_path.with_suffix('.ass')

        with open(ass_path, 'w', encoding='utf-8') as f:
            # ASS 헤더
            f.write("[Script Info]\n")
            f.write("ScriptType: v4.00+\n")
            f.write("PlayResX: 1920\n")
            f.write("PlayResY: 1080\n\n")

            # 스타일 정의
            f.write("[V4+ Styles]\n")
            f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            f.write("Style: Default,NanumGothic,96,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,2,2,10,10,20,1\n\n")

            # 이벤트 (자막)
            f.write("[Events]\n")
            f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

            for sub in subtitles:
                start = self._format_ass_timestamp(sub["start"])
                end = self._format_ass_timestamp(sub["end"])
                text = sub['text'].replace('\n', '\\N')
                f.write(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")

        logger.info(f"대본 기반 ASS 생성 완료: {len(subtitles)}개 구간")

        # SRT 경로를 ASS 경로로 업데이트 (호출자가 사용할 수 있도록)
        if srt_path != ass_path:
            # srt_path 변수를 업데이트할 수 없으므로 ass_path 반환
            pass

        return ass_path

    def _create_srt_from_timestamps(self, word_segments: list, srt_path: Path, max_chars_per_line: int = 22):
        """단어별 타임스탬프로 SRT 자막 파일 생성 (적절한 길이로 그룹화)"""
        if not word_segments:
            raise RuntimeError("자막 생성 실패: 단어 타임스탬프가 없습니다.")

        subtitles = []
        current_text = ""
        start_time = None
        min_remaining_chars = 5  # 남은 글자가 이보다 적으면 현재 라인에 포함

        for i, segment in enumerate(word_segments):
            word = segment["word"]

            # 첫 단어면 시작 시간 기록
            if not current_text:
                start_time = segment["start"]

            # 다음 단어를 추가했을 때의 길이 확인 (띄어쓰기 포함)
            next_text = current_text + (" " if current_text else "") + word
            is_last_word = (i == len(word_segments) - 1)

            # 마지막 단어이거나, 다음 단어까지 추가해도 적절한 길이면 추가
            if is_last_word:
                current_text = next_text
                subtitles.append({
                    "start": start_time,
                    "end": segment["end"],
                    "text": current_text.strip()
                })
            elif len(next_text) >= max_chars_per_line:
                # 현재까지의 텍스트만으로 자막 생성
                if current_text:
                    subtitles.append({
                        "start": start_time,
                        "end": word_segments[i-1]["end"] if i > 0 else segment["end"],
                        "text": current_text.strip()
                    })
                    current_text = word
                    start_time = segment["start"]
                else:
                    # 단어 하나가 max_chars_per_line보다 긴 경우
                    current_text = next_text
            else:
                # 다음 단어 추가
                current_text = next_text

                # 다음다음 단어를 미리 확인 (남은 글자 수 예측)
                if i + 1 < len(word_segments):
                    peek_text = current_text + " " + word_segments[i + 1]["word"]
                    # 다음 단어를 추가하면 max를 넘고, 남은 글자가 너무 적을 것 같으면 지금 끊기
                    if len(peek_text) > max_chars_per_line and len(peek_text) - max_chars_per_line < min_remaining_chars:
                        # 지금 자막 생성
                        subtitles.append({
                            "start": start_time,
                            "end": segment["end"],
                            "text": current_text.strip()
                        })
                        current_text = ""

        # SRT 파일 작성
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles, 1):
                start = self._format_timestamp(sub["start"])
                end = self._format_timestamp(sub["end"])
                f.write(f"{i}\n")
                f.write(f"{start} --> {end}\n")
                f.write(f"{sub['text']}\n\n")

        logger.info(f"SRT 자막 생성 완료: {len(subtitles)}개 구간")
        return True

    def _format_timestamp(self, seconds: float) -> str:
        """초를 SRT 타임스탬프 형식으로 변환 (00:00:00,000)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    def _format_ass_timestamp(self, seconds: float) -> str:
        """초를 ASS 타임스탬프 형식으로 변환 (0:00:00.00)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"

    def _add_subtitles_with_segments(self, video_path: Path, audio_path: Path, output_path: Path, word_segments: list):
        """미리 분석된 Whisper 타임스탬프로 자막 추가 (병렬 처리용)"""
        import subprocess

        # 자막 스타일 (나눔고딕, 큰 글씨) - _add_subtitles_from_script와 동일하게
        subtitle_style = (
            "FontName=NanumGothic,"  # 나눔고딕
            "Fontsize=32,"  # 20 -> 32 (더 큼)
            "Bold=1,"  # 볼드
            "PrimaryColour=&H00FFFFFF,"  # 흰색
            "OutlineColour=&H00000000,"  # 검은 테두리
            "BorderStyle=1,"
            "Outline=3,"  # 더 두꺼운 테두리
            "Shadow=2,"  # 더 진한 그림자
            "MarginV=20,"  # 맨 하단
            "Alignment=2"  # 하단 중앙
        )

        # SRT 파일 생성
        srt_path = audio_path.with_suffix('.srt')

        # 미리 분석된 Whisper 타임스탬프로 정확한 자막 생성
        # word_segments가 없으면 _create_srt_from_timestamps에서 예외 발생
        self._create_srt_from_timestamps(word_segments, srt_path, max_chars_per_line=22)

        # FFmpeg 명령어
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vf', f"subtitles={str(srt_path)}:force_style='{subtitle_style}'",
            '-c:a', 'copy',
            '-y',
            str(output_path)
        ]

        subprocess.run(cmd, check=True, capture_output=True)

    def _add_subtitles_from_script(self, video_path: Path, audio_path: Path, output_path: Path, narration: str, audio_duration: float):
        """대본을 기반으로 자막 추가 (Whisper 없이)"""
        import subprocess

        # SRT 파일 경로 (실제로는 ASS 파일이 생성됨)
        srt_path = audio_path.with_suffix('.srt')

        # 대본 기반 ASS 자막 생성 (스타일 포함)
        ass_path = self._create_srt_from_script(narration, audio_duration, srt_path, max_chars_per_line=22)

        # FFmpeg ass 필터에는 파일명만 전달
        ass_filename = ass_path.name

        # FFmpeg 명령어 (ASS 파일은 이미 스타일이 포함되어 있으므로 force_style 불필요)
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-vf', f"ass={ass_filename}",
            '-c:a', 'copy',
            '-y',
            str(output_path)
        ]

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore', cwd=str(audio_path.parent))
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg 자막 추가 실패: {e.stderr}")
            raise

    def _add_subtitles(self, video_path: Path, audio_path: Path, output_path: Path):
        """Whisper로 음성 분석 후 정확한 타이밍의 자막 추가 (동기 버전 - 호환성용)"""
        # Whisper로 단어별 타임스탬프 추출
        word_segments = self._generate_word_timestamps(audio_path)
        # 추출된 타임스탬프로 자막 추가
        self._add_subtitles_with_segments(video_path, audio_path, output_path, word_segments)


def main():
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    parser = argparse.ArgumentParser(description="story.json과 이미지로 영상 생성")
    parser.add_argument("--folder", "-f", required=True, help="story.json과 이미지가 있는 폴더 경로")
    parser.add_argument("--voice", "-v", default="ko-KR-SoonBokNeural",
                       help="TTS 음성 (기본: ko-KR-SoonBokNeural)")
    parser.add_argument("--aspect-ratio", "-a", default="9:16", choices=["9:16", "16:9"],
                       help="비디오 비율 (기본: 9:16)")
    parser.add_argument("--combine", action="store_true",
                       help="씬별 비디오를 하나로 결합 (기본: 결합 안 함)")
    parser.add_argument("--add-subtitles", "-s", action="store_true", default=True,
                       help="자막 추가 (기본: 추가함, --no-subtitles로 끄기)")
    parser.add_argument("--no-subtitles", action="store_false", dest="add_subtitles",
                       help="자막 추가 안 함")
    parser.add_argument("--image-source", "-i", default="none", choices=["none", "google", "dalle"],
                       help="이미지 소스 (기본: none - 수동 업로드, google - Google Image Search, dalle - DALL-E 3)")
    parser.add_argument("--is-admin", action="store_true",
                       help="관리자 모드 (비용 로그 표시)")

    args = parser.parse_args()

    # 로그 폴더 생성
    os.makedirs("logs", exist_ok=True)

    print("=" * 70)
    print("VideoFromFolder Creator")
    print("=" * 70)
    print(f"폴더: {args.folder}")
    print(f"음성: {args.voice}")
    print(f"비율: {args.aspect_ratio}")
    print(f"자막: {'추가' if args.add_subtitles else '추가 안 함'}")
    print(f"이미지 소스: {args.image_source}")
    print("=" * 70)

    # 크리에이터 생성
    creator = VideoFromFolderCreator(
        folder_path=args.folder,
        voice=args.voice,
        aspect_ratio=args.aspect_ratio,
        add_subtitles=args.add_subtitles,
        image_source=args.image_source,
        is_admin=args.is_admin
    )

    # 비디오 생성
    result = asyncio.run(creator.create_all_videos(combine=args.combine))

    if result:
        print("=" * 70)
        print("✓ 성공!")
        print("=" * 70)
        print(f"출력: {result}")
        print("=" * 70)

        # simple_concat 병합 로직 추가
        if not args.combine:
            print("\n" + "=" * 70)
            print("🔗 씬 병합 시작 (simple_concat)")
            print("=" * 70)

            # generated_videos 폴더 경로
            generated_videos_folder = Path(args.folder) / "generated_videos"

            if generated_videos_folder.exists():
                # story.json에서 제목 추출
                story_path = Path(args.folder) / "story.json"
                story_metadata_path = Path(args.folder) / "story_metadata.json"

                title = "output_video"
                if story_metadata_path.exists():
                    try:
                        with open(story_metadata_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            title = metadata.get('title', 'output_video')
                    except Exception as e:
                        logger.warning(f"story_metadata.json 읽기 실패: {e}")
                elif story_path.exists():
                    try:
                        with open(story_path, 'r', encoding='utf-8') as f:
                            story = json.load(f)
                            title = story.get('title', 'output_video')
                    except Exception as e:
                        logger.warning(f"story.json 읽기 실패: {e}")

                # 안전한 파일명으로 변환
                safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
                output_filename = f"{safe_title}.mp4"

                print("\n" + "=" * 70)
                print("ℹ️ 개별 씬 파일 생성 완료")
                print("=" * 70)
                print(f"📁 폴더: {generated_videos_folder}")
                print("=" * 70)
                print(f"📝 예상 파일명: {output_filename}")

                # simple_concat.py 호출
                try:
                    script_path = Path(__file__).parent / "simple_concat.py"
                    cmd = [
                        sys.executable,
                        str(script_path),
                        str(generated_videos_folder),
                        output_filename
                    ]

                    concat_result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='ignore',
                        timeout=600
                    )

                    if concat_result.stdout:
                        print(concat_result.stdout)

                    if concat_result.returncode == 0:
                        final_video_path = generated_videos_folder / output_filename
                        if final_video_path.exists():
                            print("\n" + "=" * 70)
                            print("✓ 최종 영상 생성 완료!")
                            print("=" * 70)
                            print(f"📹 파일: {final_video_path}")
                            print("=" * 70)
                        else:
                            raise FileNotFoundError(f"생성된 영상 파일을 찾을 수 없습니다.")
                    else:
                        raise RuntimeError(f"simple_concat.py 실패: {concat_result.stderr}")

                except Exception as e:
                    logger.error(f"❌ 영상 파일 확인 실패: {e}")
                    sys.exit(1)
            else:
                logger.warning(f"generated_videos 폴더를 찾을 수 없습니다: {generated_videos_folder}")
    else:
        print("✗ 실패!")
        sys.exit(1)


if __name__ == "__main__":
    main()
