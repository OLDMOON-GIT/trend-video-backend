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

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv가 없어도 계속 진행

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

# Google Cloud TTS (선택적)
try:
    from google.cloud import texttospeech
    GOOGLE_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_TTS_AVAILABLE = False
    logger_msg = "⚠️ google-cloud-texttospeech 패키지가 없습니다. pip install google-cloud-texttospeech"

# AWS Polly (선택적)
try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    AWS_POLLY_AVAILABLE = True
except ImportError:
    AWS_POLLY_AVAILABLE = False
    logger_msg = "⚠️ boto3 패키지가 없습니다. pip install boto3"
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips, VideoFileClip
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
import tempfile
from PIL import Image as PILImage
import numpy as np

# OpenCV 임포트 시도 (얼굴 감지용)
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    logger_msg = "⚠️ OpenCV가 없습니다. 얼굴 감지 없이 중앙 크롭만 수행합니다. 설치: pip install opencv-python"

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

# DALL-E (옵션)
try:
    from openai import OpenAI
    DALLE_AVAILABLE = True
except ImportError:
    DALLE_AVAILABLE = False
    logger.warning("[WARNING] openai module not found. DALL-E image generation disabled.")

# Anthropic Claude API (프롬프트 수정용)
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("[WARNING] anthropic module not found. Claude prompt refinement disabled.")


class VideoFromFolderCreator:
    """story.json과 이미지로 영상을 생성하는 클래스"""

    def __init__(self, folder_path: str, voice: str = "ko-KR-SoonBokNeural",
                 aspect_ratio: str = "16:9", add_subtitles: bool = False,
                 image_source: str = "none", image_provider: str = "openai", is_admin: bool = False):
        """
        Args:
            folder_path: story.json과 이미지가 있는 폴더 경로
            voice: TTS 음성 (기본: ko-KR-SoonBokNeural)
            aspect_ratio: 비디오 비율 (기본: 16:9)
            add_subtitles: 자막 추가 여부 (기본: False)
            image_source: 이미지 소스 ("none", "dalle", "imagen3")
            image_provider: 이미지 생성 제공자 ("openai", "imagen3")
            is_admin: 관리자 모드 (비용 로그 표시)
        """
        self.folder_path = Path(folder_path)

        # TTS 제공자 결정
        self.voice = voice
        if voice.startswith('google-'):
            self.tts_provider = 'google'
            if not GOOGLE_TTS_AVAILABLE:
                logger.warning(f"⚠️ Google Cloud TTS 패키지가 없습니다. Edge TTS로 대체합니다.")
                self.tts_provider = 'edge'
                self.voice = "ko-KR-SoonBokNeural"
        elif voice.startswith('aws-'):
            self.tts_provider = 'aws'
            if not AWS_POLLY_AVAILABLE:
                logger.warning(f"⚠️ AWS Polly 패키지가 없습니다. Edge TTS로 대체합니다.")
                self.tts_provider = 'edge'
                self.voice = "ko-KR-SoonBokNeural"
        else:
            self.tts_provider = 'edge'

        self.aspect_ratio = aspect_ratio
        self.add_subtitles = add_subtitles
        self.image_source = image_source.lower()
        self.image_provider = image_provider.lower()
        self.is_admin = is_admin

        # 이미지 생성 클라이언트 초기화
        self.dalle_client = None
        self.imagen_client = None
        self.imagen_model = None
        self.imagen_api_key = None
        self.anthropic_client = None

        if self.image_source == "dalle":
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

                    # Anthropic Claude 클라이언트 초기화 (프롬프트 수정용)
                    if ANTHROPIC_AVAILABLE:
                        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
                        if anthropic_key:
                            self.anthropic_client = Anthropic(api_key=anthropic_key)
                            logger.info("✅ Claude API 활성화됨 (프롬프트 자동 수정)")
                        else:
                            logger.warning("⚠️ ANTHROPIC_API_KEY 환경변수가 없습니다. 프롬프트 자동 수정 비활성화")

        elif self.image_source == "imagen3":
            # Imagen 3 초기화 (Vertex AI 사용)
            import os

            # Google Cloud 프로젝트 설정
            project_id = os.getenv('GOOGLE_CLOUD_PROJECT', '66255489700')
            location = os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1')

            try:
                from vertexai.preview.vision_models import ImageGenerationModel
                import vertexai

                # Vertex AI 초기화
                vertexai.init(project=project_id, location=location)

                # Imagen 3 모델 로드
                self.imagen_model = ImageGenerationModel.from_pretrained("imagegeneration@006")
                self.imagen_client = None
                self.imagen_api_key = None

                logger.info(f"✅ Google Imagen 3 이미지 생성 활성화됨 (Vertex AI)")
                logger.info(f"ℹ️  프로젝트: {project_id}, 리전: {location}")

                # Anthropic Claude 클라이언트 초기화 (프롬프트 수정용)
                if ANTHROPIC_AVAILABLE:
                    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
                    if anthropic_key:
                        self.anthropic_client = Anthropic(api_key=anthropic_key)
                        logger.info("✅ Claude API 활성화됨 (프롬프트 자동 수정)")
                    else:
                        logger.warning("⚠️ ANTHROPIC_API_KEY 환경변수가 없습니다. 프롬프트 자동 수정 비활성화")
            except ImportError:
                logger.error("❌ Vertex AI SDK가 설치되지 않았습니다. pip install google-cloud-aiplatform")
                self.image_source = "none"
            except Exception as e:
                logger.error(f"❌ Vertex AI 초기화 실패: {e}")
                logger.error("💡 Application Default Credentials를 설정하거나 GOOGLE_APPLICATION_CREDENTIALS 환경변수를 설정하세요.")
                self.image_source = "none"

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
        """글씨 쓴 유튜브용 썸네일 제작 (항상 실행)"""
        try:
            logger.info("🖼️  썸네일 제작 중... (글씨 쓰기)")

            # create_thumbnail.py를 subprocess로 실행
            # - 업로드된 thumbnail.* 파일이 있으면 그걸 사용
            # - 없으면 첫 번째 씬 이미지 사용
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
                logger.info("✅ 썸네일 생성 완료 (글씨 쓴 버전)")
                if result.stdout:
                    logger.info(f"썸네일 출력: {result.stdout[:200]}")
            else:
                logger.error(f"썸네일 생성 실패 (return code: {result.returncode})")
                if result.stderr:
                    logger.error(f"썸네일 에러: {result.stderr}")
                if result.stdout:
                    logger.error(f"썸네일 출력: {result.stdout}")

        except Exception as e:
            logger.error(f"썸네일 생성 중 예외 발생: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _detect_focus_area(self, image_path: Path) -> Optional[tuple]:
        """
        이미지에서 인물이나 주요 물체를 감지하여 중심 좌표 반환
        OpenCV Haar Cascade로 얼굴 감지

        Returns:
            (center_x, center_y) 또는 None (감지 실패 시)
        """
        if not OPENCV_AVAILABLE:
            return None

        try:
            # 이미지 로드
            img = cv2.imread(str(image_path))
            if img is None:
                return None

            # 그레이스케일 변환
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # Haar Cascade로 얼굴 감지
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            face_cascade = cv2.CascadeClassifier(cascade_path)

            # 얼굴 감지
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )

            if len(faces) > 0:
                # 가장 큰 얼굴을 주요 인물로 선택
                largest_face = max(faces, key=lambda f: f[2] * f[3])
                x, y, w, h = largest_face

                # 얼굴 중심 좌표
                center_x = x + w // 2
                center_y = y + h // 2

                logger.info(f"  ✅ 얼굴 감지됨: ({center_x}, {center_y}), 크기: {w}x{h}")
                return (center_x, center_y)

            logger.info(f"  ℹ️ 얼굴 미감지 (중앙 크롭 사용)")
            return None

        except Exception as e:
            logger.warning(f"  ⚠️ 얼굴 감지 실패: {e}")
            return None

    def _smart_crop_to_vertical(self, input_path: Path, output_path: Path) -> bool:
        """
        가로 이미지(16:9)를 세로(9:16)로 스마트 크롭 변환
        얼굴이 감지되면 얼굴 중심으로 크롭, 아니면 중앙 크롭

        Args:
            input_path: 원본 이미지 경로
            output_path: 출력 이미지 경로

        Returns:
            성공 여부
        """
        try:
            # 얼굴/물체 감지
            focus_point = self._detect_focus_area(input_path)

            with PILImage.open(input_path) as img:
                width, height = img.size
                logger.info(f"  🎨 스마트 크롭: 원본 {width}x{height}")

                # 목표 비율: 9:16 (세로)
                target_ratio = 9 / 16

                # 현재 높이를 기준으로 9:16 비율의 너비 계산
                new_width = int(height * target_ratio)

                if new_width > width:
                    # 높이를 기준으로 계산한 너비가 원본보다 크면, 너비를 기준으로 재계산
                    new_height = int(width / target_ratio)
                    new_width = width

                    # 얼굴이 감지되면 얼굴 중심으로, 아니면 상단 크롭
                    if focus_point:
                        focus_x, focus_y = focus_point
                        center_y = focus_y
                        top = max(0, center_y - new_height // 2)
                        bottom = min(height, top + new_height)

                        if bottom > height:
                            bottom = height
                            top = bottom - new_height
                        if top < 0:
                            top = 0
                            bottom = new_height

                        logger.info(f"  ✨ 얼굴 중심 크롭: y={center_y}")
                    else:
                        # 상단 부분을 우선적으로 크롭
                        top = 0
                        bottom = new_height

                    left = 0
                    right = width
                else:
                    # 높이는 그대로, 너비를 크롭
                    new_height = height

                    # 얼굴이 감지되면 얼굴 중심으로, 아니면 중앙 크롭
                    if focus_point:
                        focus_x, focus_y = focus_point
                        center_x = focus_x
                        left = max(0, center_x - new_width // 2)
                        right = min(width, left + new_width)

                        if right > width:
                            right = width
                            left = right - new_width
                        if left < 0:
                            left = 0
                            right = new_width

                        logger.info(f"  ✨ 얼굴 중심 크롭: x={center_x}")
                    else:
                        # 중앙 크롭
                        left = (width - new_width) // 2
                        right = left + new_width

                    top = 0
                    bottom = height

                logger.info(f"  ✂️ 크롭 영역: ({left}, {top}) ~ ({right}, {bottom})")

                # 이미지 크롭
                img = img.crop((left, top, right, bottom))

                # 표준 쇼츠 해상도로 리사이즈 (1080x1920)
                target_size = (1080, 1920)
                img = img.resize(target_size, PILImage.Resampling.LANCZOS)

                logger.info(f"  ✅ 스마트 크롭 완료: {target_size[0]}x{target_size[1]} (9:16)")

                # 저장
                img.save(output_path, quality=95)
                return True

        except Exception as e:
            logger.error(f"스마트 크롭 실패: {input_path} - {e}")
            return False

    def _find_all_media_files(self):
        """
        모든 이미지와 비디오 파일을 찾아서 정렬 없이 반환
        Returns: (image_paths, video_paths)
        """
        # 이미지 파일 찾기
        all_images_set = set()
        for ext in ['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG']:
            for img_file in self.folder_path.glob(ext):
                if 'generated_videos' not in str(img_file) and 'thumbnail' not in img_file.name.lower():
                    all_images_set.add(img_file)

        images_folder = self.folder_path / "images"
        if images_folder.exists():
            for ext in ['*.png', '*.jpg', '*.jpeg', '*.PNG', '*.JPG', '*.JPEG']:
                for img_file in images_folder.glob(ext):
                    if 'thumbnail' not in img_file.name.lower():
                        all_images_set.add(img_file)

        # 비디오 파일 찾기
        all_videos_set = set()
        for ext in ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.MP4', '*.MOV', '*.AVI', '*.MKV']:
            for vid_file in self.folder_path.glob(ext):
                if 'generated_videos' not in str(vid_file):
                    all_videos_set.add(vid_file)

        videos_folder = self.folder_path / "videos"
        if videos_folder.exists():
            for ext in ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.MP4', '*.MOV', '*.AVI', '*.MKV']:
                for vid_file in videos_folder.glob(ext):
                    all_videos_set.add(vid_file)

        return list(all_images_set), list(all_videos_set)

    def _find_images_with_scene_numbers(self) -> Dict[int, Path]:
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
                파일명에서 시퀀스 번호 추출 (Frontend extractSequenceNumber와 동일한 로직)
                - 1.jpg, 02.png (숫자로 시작)
                - image_01.jpg, scene-02.png (_숫자 또는 -숫자)
                - Image_fx (47).jpg (괄호 안 숫자, 랜덤 ID 없을 때만)

                Returns: (sequence_number or None, mtime)
                """
                import re
                filename = filepath.name

                # 파일 수정 시간 (항상 가져오기)
                try:
                    mtime = filepath.stat().st_mtime
                except:
                    mtime = 0

                # 1. 파일명이 숫자로 시작: "1.jpg", "02.png"
                match = re.match(r'^(\d+)\.', filename)
                if match:
                    return (int(match.group(1)), mtime)

                # 2. _숫자. 또는 -숫자. 패턴: "image_01.jpg", "scene-02.png"
                match = re.search(r'[_-](\d{1,3})\.', filename)
                if match:
                    return (int(match.group(1)), mtime)

                # 3. (숫자) 패턴: "Image_fx (47).jpg"
                # 단, 랜덤 ID가 없을 때만 (8자 이상의 영숫자 조합이 없을 때)
                match = re.search(r'\((\d+)\)', filename)
                if match and not re.search(r'[_-]\w{8,}', filename):
                    return (int(match.group(1)), mtime)

                # 시퀀스 번호 없음 - 파일 수정 시간 사용
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
        if self.image_source in ["google", "dalle", "imagen3"]:
            images = self._download_missing_images(images)

        return images

    def _find_videos(self) -> Dict[int, Path]:
        """씬별 비디오 파일 찾기 (이미지와 동일한 정렬 로직)"""
        videos = {}

        logger.info("비디오 파일을 찾습니다.")

        # 모든 비디오 파일 찾기 (generated_videos 폴더 제외, 중복 제거)
        all_videos_set = set()
        for ext in ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.MP4', '*.MOV', '*.AVI', '*.MKV']:
            for vid_file in self.folder_path.glob(ext):
                # generated_videos 폴더 안의 파일은 제외
                if 'generated_videos' not in str(vid_file):
                    all_videos_set.add(vid_file)

        # videos 서브폴더에서도 찾기
        videos_folder = self.folder_path / "videos"
        if videos_folder and videos_folder.exists():
            for ext in ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.MP4', '*.MOV', '*.AVI', '*.MKV']:
                for vid_file in videos_folder.glob(ext):
                    all_videos_set.add(vid_file)

        # 정렬 로직 (이미지와 동일)
        def extract_sequence(filepath):
            """
            파일명에서 시퀀스 번호 추출 (Frontend extractSequenceNumber와 동일한 로직)
            - 1.mp4, 02.mp4 (숫자로 시작)
            - video_01.mp4, scene-02.mp4 (_숫자 또는 -숫자)
            - Video_fx (47).mp4 (괄호 안 숫자, 랜덤 ID 없을 때만)

            Returns: (sequence_number or None, mtime)
            """
            import re
            filename = filepath.name

            # 파일 수정 시간 (항상 가져오기)
            try:
                mtime = filepath.stat().st_mtime
            except:
                mtime = 0

            # 1. 파일명이 숫자로 시작: "1.mp4", "02.mp4"
            match = re.match(r'^(\d+)\.', filename)
            if match:
                return (int(match.group(1)), mtime)

            # 2. _숫자. 또는 -숫자. 패턴: "video_01.mp4", "scene-02.mp4"
            match = re.search(r'[_-](\d{1,3})\.', filename)
            if match:
                return (int(match.group(1)), mtime)

            # 3. (숫자) 패턴: "Video_fx (47).mp4"
            # 단, 랜덤 ID가 없을 때만 (8자 이상의 영숫자 조합이 없을 때)
            match = re.search(r'\((\d+)\)', filename)
            if match and not re.search(r'[_-]\w{8,}', filename):
                return (int(match.group(1)), mtime)

            # 시퀀스 번호 없음 - 파일 수정 시간 사용
            return (None, mtime)

        # 정렬: 시퀀스 번호가 있으면 우선, 없으면 시간 순서
        all_videos_list = list(all_videos_set)
        all_videos = sorted(all_videos_list, key=lambda f: (
            extract_sequence(f)[0] is None,  # 시퀀스 없는 것을 뒤로
            extract_sequence(f)[0] if extract_sequence(f)[0] is not None else 0,  # 시퀀스 정렬
            extract_sequence(f)[1]  # 시간 정렬
        ))

        # 씬 번호 자동 할당 및 로그 출력
        logger.info(f"\n🎬 비디오 정렬 완료 (총 {len(all_videos)}개):")
        for idx, vid_path in enumerate(all_videos, start=1):
            videos[idx] = vid_path
            seq_info = extract_sequence(vid_path)
            if seq_info[0] is not None:
                logger.info(f"  씬 {idx}: {vid_path.name} (시퀀스: {seq_info[0]})")
            else:
                import datetime
                mtime_str = datetime.datetime.fromtimestamp(seq_info[1]).strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"  씬 {idx}: {vid_path.name} (시간: {mtime_str})")

        logger.info(f"비디오 {len(videos)}개 발견")

        return videos

    def _download_missing_images(self, images: Dict[int, Path]) -> Dict[int, Path]:
        """
        누락된 이미지를 DALL-E 또는 Imagen3으로 자동 생성

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

        source_name = "DALL-E 3" if self.image_source == "dalle" else "Imagen 3"
        logger.info(f"⚠️ {len(missing_scenes)}개 씬의 이미지가 누락되었습니다. {source_name}로 생성을 시작합니다...")

        # 비용 예측
        if self.image_source == "dalle":
            self._log_dalle_cost_estimate(len(missing_scenes))

        try:
            success_count = 0
            fail_count = 0

            # 병렬 처리를 위한 헬퍼 함수
            def generate_single_image(scene_data):
                scene_num, scene = scene_data

                # 취소 플래그 파일 체크
                cancel_file = self.folder_path / '.cancel'
                if cancel_file.exists():
                    logger.warning("🛑 취소 플래그 감지됨. 이미지 생성을 중단합니다.")
                    return (scene_num, None, "cancelled")

                # image_prompt 추출 (imagefx_prompt도 지원)
                image_prompt = scene.get('image_prompt') or scene.get('imagefx_prompt', '')
                sora_prompt = scene.get('sora_prompt', '')

                if not image_prompt:
                    # 상품 콘텐츠(product-*.*)는 sora_prompt가 있으면 image_prompt 없어도 괜찮음
                    version = self.story_data.get('version', '')
                    is_product = version.startswith('product-') or 'product' in version.lower()

                    if is_product and sora_prompt:
                        # Sora로 비디오 생성할 거니까 이미지는 안 만들어도 됨
                        logger.info(f"ℹ️ 씬 {scene_num}: 상품 콘텐츠, sora_prompt 있음 → 이미지 생성 스킵")
                        return (scene_num, None, "sora_only")

                    logger.warning(f"⚠️ 씬 {scene_num}: image_prompt 또는 imagefx_prompt가 없습니다. 건너뜁니다.")
                    return (scene_num, None, "no_prompt")

                # 파일명 생성
                filename = f"scene_{scene_num:02d}_image.jpg"

                try:
                    if self.image_source == "dalle":
                        # DALL-E 3 Image Generation
                        logger.info(f"🎨 씬 {scene_num}: '{image_prompt}' DALL-E 3 생성 중...")
                        generated_path = self._generate_dalle_image(
                            prompt=image_prompt,
                            save_dir=self.folder_path,
                            filename=filename
                        )

                        if generated_path:
                            logger.info(f"✅ 씬 {scene_num}: 이미지 생성 완료")
                            logger.info(f"   → images[{scene_num}] = {generated_path}")
                            return (scene_num, generated_path, "success")
                        else:
                            logger.error(f"❌ 씬 {scene_num}: 이미지 생성 실패")
                            return (scene_num, None, "failed")

                    elif self.image_source == "imagen3":
                        # Google Imagen 3 Image Generation
                        logger.info(f"🖼️ 씬 {scene_num}: '{image_prompt}' Imagen 3 생성 중...")
                        generated_path = self._generate_imagen3_image(
                            prompt=image_prompt,
                            save_dir=self.folder_path,
                            filename=filename
                        )

                        if generated_path:
                            logger.info(f"✅ 씬 {scene_num}: 이미지 생성 완료")
                            logger.info(f"   → images[{scene_num}] = {generated_path}")
                            return (scene_num, generated_path, "success")
                        else:
                            logger.error(f"❌ 씬 {scene_num}: 이미지 생성 실패")
                            return (scene_num, None, "failed")
                except Exception as e:
                    logger.error(f"❌ 씬 {scene_num}: 이미지 생성 중 예외 발생: {e}")
                    return (scene_num, None, "error")

                return (scene_num, None, "unknown")

            # 병렬 처리 실행 (최대 3개 동시 처리)
            from concurrent.futures import ThreadPoolExecutor, as_completed
            max_workers = 3  # OpenAI API rate limit 고려

            logger.info(f"🚀 {len(missing_scenes)}개 이미지를 최대 {max_workers}개씩 병렬 생성합니다...")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 모든 씬에 대해 작업 제출
                future_to_scene = {
                    executor.submit(generate_single_image, scene_data): scene_data[0]
                    for scene_data in missing_scenes
                }

                # 완료된 작업 처리
                for future in as_completed(future_to_scene):
                    scene_num = future_to_scene[future]
                    try:
                        scene_num, generated_path, status = future.result()

                        if status == "success" and generated_path:
                            images[scene_num] = generated_path
                            success_count += 1
                        elif status == "cancelled":
                            raise KeyboardInterrupt("User cancelled the operation")
                        elif status in ["failed", "error", "no_prompt"]:
                            fail_count += 1
                    except Exception as e:
                        logger.error(f"❌ 씬 {scene_num}: 작업 처리 중 예외: {e}")
                        fail_count += 1

        except Exception as e:
            logger.error(f"❌ 이미지 자동 생성/다운로드 중 오류 발생: {e}")

        # 최종 비용 요약
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 이미지 생성/다운로드 완료 - 총 {len(images)}개 이미지 확보")
        logger.info(f"   ✅ 성공: {success_count}개, ❌ 실패: {fail_count}개")
        logger.info(f"   🔍 images 딕셔너리 내용:")
        for scene_num, img_path in sorted(images.items()):
            logger.info(f"      씬 {scene_num}: {img_path.name}")

        if self.image_source == "dalle":
            total_cost = success_count * 0.080  # HD quality
            logger.info(f"💰 총 비용: ${total_cost:.2f} (약 ₩{total_cost * 1300:.0f})")

        logger.info(f"{'='*60}\n")

        return images

    def _refine_prompt_with_claude(self, original_prompt: str, error_message: str, model_name: str) -> Optional[str]:
        """
        Claude를 호출해서 프롬프트를 수정하여 content filter를 통과할 수 있도록 함

        Args:
            original_prompt: 원본 프롬프트
            error_message: 에러 메시지
            model_name: 사용 중인 이미지 생성 모델 이름 (DALL-E 3, Imagen 3 등)

        Returns:
            수정된 프롬프트 (실패 시 None)
        """
        if not self.anthropic_client:
            logger.warning("⚠️ Claude API를 사용할 수 없습니다. 프롬프트 수정을 건너뜁니다.")
            return None

        try:
            logger.info(f"🤖 Claude를 호출하여 프롬프트 수정 중...")

            system_prompt = f"""You are an expert at refining image generation prompts to pass content filters for {model_name}.
Your goal is to modify the given prompt to avoid content policy violations while maintaining the core visual intent and quality.

Guidelines:
- Remove any potentially sensitive, violent, or inappropriate content
- Keep photorealistic, professional photography style keywords
- Maintain the aspect ratio, composition, and lighting instructions
- Preserve Korean cultural context if present
- Keep "NO TEXT" instruction at the end
- Make minimal changes necessary to pass content filters"""

            user_prompt = f"""The following image generation prompt was rejected by {model_name}'s content filter:

Error: {error_message}

Original prompt:
{original_prompt}

Please rewrite this prompt to pass the content filter while maintaining the visual quality and intent.
Return ONLY the refined prompt without any explanation or additional text."""

            response = self.anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=500,
                temperature=0.3,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

            refined_prompt = response.content[0].text.strip()
            logger.info(f"✅ Claude가 프롬프트를 수정했습니다")
            logger.info(f"   수정된 프롬프트: {refined_prompt[:150]}...")

            return refined_prompt

        except Exception as e:
            logger.error(f"❌ Claude 프롬프트 수정 실패: {e}")
            return None

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
        # 취소 플래그 체크 (DALL-E 시작 전)
        cancel_file = self.folder_path / '.cancel'
        if cancel_file.exists():
            logger.warning("🛑 취소 플래그 감지됨. DALL-E 이미지 생성을 시작하지 않습니다.")
            raise KeyboardInterrupt("User cancelled the operation")

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
        current_prompt = prompt
        last_error_message = ""

        for attempt in range(max_retries):
            try:
                # 재시도 시 Claude를 호출하여 프롬프트 수정
                if attempt == 0:
                    current_prompt = prompt
                    logger.info(f"🎨 첫 번째 시도: 원본 프롬프트 사용")
                else:
                    # Claude를 호출해서 프롬프트 수정
                    logger.info(f"🔄 Content filter 우회를 위해 Claude로 프롬프트 수정 (시도 {attempt + 1}/{max_retries})")
                    refined_prompt = self._refine_prompt_with_claude(
                        original_prompt=current_prompt,
                        error_message=last_error_message,
                        model_name="DALL-E 3"
                    )

                    if refined_prompt:
                        current_prompt = refined_prompt
                        logger.info(f"   수정된 프롬프트: {current_prompt[:150]}...")
                    else:
                        # Claude 호출 실패 시 간단한 폴백 사용
                        if attempt == 1:
                            current_prompt = f"A calm and peaceful scene depicting: {prompt[:100]}"
                        else:
                            current_prompt = "A beautiful, peaceful landscape with soft lighting"
                        logger.warning(f"   ⚠️ Claude 수정 실패, 폴백 프롬프트 사용: {current_prompt}")

                # 취소 플래그 체크 (DALL-E API 호출 직전)
                cancel_file = self.folder_path / '.cancel'
                if cancel_file.exists():
                    logger.warning("🛑 취소 플래그 감지됨. DALL-E API 호출을 중단합니다.")
                    raise KeyboardInterrupt("User cancelled the operation")

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

                # 취소 플래그 체크 (이미지 다운로드 전)
                cancel_file = self.folder_path / '.cancel'
                if cancel_file.exists():
                    logger.warning("🛑 취소 플래그 감지됨. DALL-E 이미지 다운로드를 중단합니다.")
                    raise KeyboardInterrupt("User cancelled the operation")

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
                last_error_message = error_str  # 에러 메시지 저장 (Claude에게 전달용)

                # Content policy violation 체크
                if 'content_policy_violation' in error_str or 'content filters' in error_str:
                    logger.warning(f"⚠️ Content filter에 걸림 (시도 {attempt + 1}/{max_retries})")
                    logger.info(f"   에러: {error_str}")

                    if attempt < max_retries - 1:
                        logger.info("   → Claude를 통해 프롬프트를 수정하여 재시도합니다...")
                        continue
                    else:
                        logger.error(f"❌ {max_retries}회 재시도 후에도 Content filter 통과 실패")
                        logger.error(f"   최종 프롬프트: {current_prompt}")
                        return None
                else:
                    # 다른 에러도 재시도 (네트워크 오류 등)
                    logger.warning(f"⚠️ DALL-E 이미지 생성 오류 (시도 {attempt + 1}/{max_retries}): {error_str}")
                    return None

        return None

    def _generate_imagen3_image(self, prompt: str, save_dir: Path, filename: str) -> Optional[Path]:
        """
        Google Imagen 3로 이미지 생성 및 저장 (Vertex AI)

        Args:
            prompt: 이미지 생성 프롬프트
            save_dir: 저장 디렉토리
            filename: 저장 파일명

        Returns:
            생성된 이미지 경로 (실패 시 None)
        """
        # 취소 플래그 체크
        cancel_file = self.folder_path / '.cancel'
        if cancel_file.exists():
            logger.warning("🛑 취소 플래그 감지됨. Imagen 3 이미지 생성을 시작하지 않습니다.")
            raise KeyboardInterrupt("User cancelled the operation")

        if not self.imagen_model:
            logger.error("❌ Imagen 3 모델이 초기화되지 않았습니다.")
            return None

        logger.info(f"🖼️ Imagen 3 이미지 생성 중 (Vertex AI)...")

        max_retries = 3
        current_prompt = prompt
        last_error_message = ""

        for attempt in range(max_retries):
            try:
                from PIL import Image
                import io

                # 재시도 시 Claude를 호출하여 프롬프트 수정
                if attempt == 0:
                    current_prompt = prompt
                    logger.info(f"🖼️ 첫 번째 시도: 원본 프롬프트 사용")
                else:
                    # Claude를 호출해서 프롬프트 수정
                    logger.info(f"🔄 Content filter 우회를 위해 Claude로 프롬프트 수정 (시도 {attempt + 1}/{max_retries})")
                    refined_prompt = self._refine_prompt_with_claude(
                        original_prompt=current_prompt,
                        error_message=last_error_message,
                        model_name="Google Imagen 3"
                    )

                    if refined_prompt:
                        current_prompt = refined_prompt
                        logger.info(f"   수정된 프롬프트: {current_prompt[:150]}...")
                    else:
                        # Claude 호출 실패 시 간단한 폴백 사용
                        if attempt == 1:
                            current_prompt = f"A calm and peaceful scene depicting: {prompt[:100]}"
                        else:
                            current_prompt = "A beautiful, peaceful landscape with soft lighting"
                        logger.warning(f"   ⚠️ Claude 수정 실패, 폴백 프롬프트 사용: {current_prompt}")

                # 프롬프트 길이 제한 (2048자)
                if len(current_prompt) > 2048:
                    current_prompt = current_prompt[:2045] + "..."
                    logger.warning(f"⚠️ 프롬프트가 2048자를 초과하여 잘렸습니다.")

                # 취소 플래그 체크 (API 호출 직전)
                cancel_file = self.folder_path / '.cancel'
                if cancel_file.exists():
                    logger.warning("🛑 취소 플래그 감지됨. Imagen 3 API 호출을 중단합니다.")
                    raise KeyboardInterrupt("User cancelled the operation")

                # Imagen 3 이미지 생성 (Vertex AI)
                logger.info(f"📡 Vertex AI Imagen 3 API 호출 중...")

                # 이미지 생성 - 올바른 메서드 사용
                images = self.imagen_model.generate_images(
                    prompt=current_prompt,
                    number_of_images=1,
                    aspect_ratio="1:1",  # 1:1, 9:16, 16:9, 4:3, 3:4 지원
                    safety_filter_level="block_only_high",
                    person_generation="allow_adult",
                )

                if not images:
                    raise Exception("응답에 이미지가 없습니다")

                # 첫 번째 이미지 가져오기
                generated_image = images[0]

                # PIL Image로 변환
                img = generated_image._pil_image
                logger.info(f"✅ 이미지 수신 완료: {img.size}")

                # aspect_ratio에 맞춰 리사이즈
                if self.aspect_ratio == "9:16":
                    target_size = (1080, 1920)
                else:  # 16:9
                    target_size = (1920, 1080)

                if img.size != target_size:
                    img = img.resize(target_size, Image.Resampling.LANCZOS)
                    logger.info(f"📏 이미지 리사이즈: {img.size} → {target_size[0]}x{target_size[1]}")

                # 파일 저장
                save_path = save_dir / filename
                save_path.parent.mkdir(parents=True, exist_ok=True)

                img.save(save_path)

                logger.info(f"✅ Imagen 3 이미지 저장 완료: {save_path.name}")
                if attempt > 0:
                    logger.info(f"   (재시도 {attempt}회 끝에 성공)")
                return save_path

            except Exception as e:
                error_str = str(e)
                last_error_message = error_str  # 에러 메시지 저장 (Claude에게 전달용)

                logger.warning(f"⚠️ Imagen 3 이미지 생성 오류 (시도 {attempt + 1}/{max_retries}): {error_str}")

                if attempt < max_retries - 1:
                    logger.info("   → Claude를 통해 프롬프트를 수정하여 재시도합니다...")
                    continue
                else:
                    logger.error(f"❌ {max_retries}회 재시도 후에도 이미지 생성 실패")
                    logger.error(f"   최종 프롬프트: {current_prompt}")
                    import traceback
                    logger.error(traceback.format_exc())
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

        # Remove markdown formatting symbols (한글 "별표"는 유지됨)
        cleaned = cleaned.replace('```', '')  # 코드블록
        cleaned = cleaned.replace('**', '')  # 볼드 기호
        cleaned = cleaned.replace('__', '')  # 볼드 기호
        cleaned = cleaned.replace('*', '')  # 이탤릭 기호
        cleaned = cleaned.replace('`', '')  # 코드 기호
        cleaned = re.sub(r'^#+\s+', '', cleaned, flags=re.MULTILINE)  # # 헤딩
        cleaned = re.sub(r'^>\s+', '', cleaned, flags=re.MULTILINE)  # > 인용
        cleaned = re.sub(r'^\s*[-]\s+', '', cleaned, flags=re.MULTILINE)  # - 리스트 (별표는 위에서 제거됨)
        cleaned = re.sub(r'^\s*\d+\.\s+', '', cleaned, flags=re.MULTILINE)  # 1. 리스트

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
        """TTS 생성 (제공자별로 라우팅)"""
        if self.tts_provider == 'google':
            return await self._generate_google_tts(text, output_path)
        elif self.tts_provider == 'aws':
            return await self._generate_aws_polly(text, output_path)
        else:
            return await self._generate_edge_tts(text, output_path)

    async def _generate_edge_tts(self, text: str, output_path: Path) -> tuple:
        """Edge TTS로 음성 생성 + 단어별 타임스탬프 추출"""
        logger.info(f"Edge TTS 생성 중: {output_path.name}")

        # 텍스트 정리
        clean_text = self._clean_narration(text)

        if not clean_text:
            logger.warning("텍스트가 비어있어 기본 메시지 사용")
            clean_text = "무음"

        # 구두점에 쉼표 추가 (자연스러운 쉼표 효과)
        tts_text = self._add_natural_pauses(clean_text)

        # ============================================================
        # 긴 텍스트 처리: 5000자 이상이면 조각으로 나눔
        # ============================================================
        MAX_CHUNK_SIZE = 5000  # Edge TTS 안정적 처리 길이

        if len(tts_text) > MAX_CHUNK_SIZE:
            logger.warning(f"텍스트가 길어서 조각으로 나눔: {len(tts_text)}자 -> {MAX_CHUNK_SIZE}자씩")
            return await self._generate_edge_tts_chunked(tts_text, output_path)

        # ============================================================
        # 일반 처리 (5000자 이하)
        # ============================================================

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

                # 문장 시간을 단어 길이(글자 수)에 비례해서 분배
                # 예: "할아버지"(4글자) + "의"(1글자) = 5글자
                # → "할아버지" 80%, "의" 20% 시간 할당
                sent_duration = (sent["end"] - sent["start"]) if sent["end"] else 1.0
                total_chars = sum(len(w) for w in words)
                if total_chars == 0:
                    total_chars = len(words)  # 폴백

                current_time = sent["start"]
                for word in words:
                    word_chars = len(word)
                    # 글자 수에 비례해서 시간 할당
                    word_duration = sent_duration * (word_chars / total_chars)
                    # 최소 시간 보장 (너무 짧으면 안 보임)
                    if word_duration < 0.2:
                        word_duration = 0.2

                    word_start = current_time
                    word_end = current_time + word_duration
                    current_time = word_end

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

    async def _generate_edge_tts_chunked(self, text: str, output_path: Path) -> tuple:
        """긴 텍스트를 조각으로 나눠 Edge TTS 생성 후 병합"""
        logger.info(f"[CHUNKED TTS] 긴 텍스트 조각 처리 시작: {len(text)}자")

        # 문장 단위로 나눔 (마침표, 느낌표, 물음표 기준)
        import re
        sentences = re.split(r'([.!?]\s+)', text)

        # 분리자도 포함하여 재조합
        full_sentences = []
        for i in range(0, len(sentences)-1, 2):
            if i+1 < len(sentences):
                full_sentences.append(sentences[i] + sentences[i+1])
            else:
                full_sentences.append(sentences[i])
        if len(sentences) % 2 == 1:
            full_sentences.append(sentences[-1])

        # 5000자씩 청크로 묶기
        MAX_CHUNK_SIZE = 5000
        chunks = []
        current_chunk = ""

        for sentence in full_sentences:
            if len(current_chunk) + len(sentence) <= MAX_CHUNK_SIZE:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence

        if current_chunk:
            chunks.append(current_chunk)

        logger.info(f"[CHUNKED TTS] {len(chunks)}개 청크로 분할 완료")

        # 각 청크에 대해 TTS 생성
        all_audio_data = []
        all_word_timings = []
        cumulative_time = 0.0

        for idx, chunk in enumerate(chunks):
            logger.info(f"[CHUNKED TTS] 청크 {idx+1}/{len(chunks)} 처리 중... ({len(chunk)}자)")

            # Edge TTS 생성
            communicate = edge_tts.Communicate(chunk, self.voice, rate='-15%')

            word_timings = []
            audio_data = b""

            async for chunk_data in communicate.stream():
                chunk_type = chunk_data.get("type", "unknown")

                if chunk_type == "audio":
                    audio_data += chunk_data["data"]
                elif chunk_type == "WordBoundary":
                    # 단어별 타임스탬프 저장 (누적 시간 추가)
                    word_timings.append({
                        "word": chunk_data["text"],
                        "start": chunk_data["offset"] / 10_000_000.0 + cumulative_time,
                        "end": (chunk_data["offset"] + chunk_data["duration"]) / 10_000_000.0 + cumulative_time
                    })

            # 임시 파일에 오디오 저장
            temp_path = output_path.parent / f"temp_chunk_{idx}.mp3"
            with open(temp_path, "wb") as f:
                f.write(audio_data)

            # 오디오 길이 측정
            try:
                audio_clip = AudioFileClip(str(temp_path))
                chunk_duration = audio_clip.duration
                audio_clip.close()
            except Exception as e:
                logger.warning(f"청크 {idx} 길이 측정 실패: {e}")
                chunk_duration = 1.0

            all_audio_data.append(audio_data)
            all_word_timings.extend(word_timings)
            cumulative_time += chunk_duration

            logger.info(f"[CHUNKED TTS] 청크 {idx+1} 완료: {chunk_duration:.2f}초, 단어 {len(word_timings)}개")

        # 모든 오디오 조각을 하나의 파일로 병합
        logger.info(f"[CHUNKED TTS] {len(all_audio_data)}개 오디오 청크 병합 중...")

        # 임시 파일들을 ffmpeg로 병합
        temp_list_path = output_path.parent / "temp_concat_list.txt"
        with open(temp_list_path, "w", encoding="utf-8") as f:
            for idx in range(len(chunks)):
                temp_chunk_path = output_path.parent / f"temp_chunk_{idx}.mp3"
                # Windows 경로를 유닉스 스타일로 변환 (ffmpeg 호환)
                unix_path = str(temp_chunk_path).replace('\\', '/')
                f.write(f"file '{unix_path}'\n")

        # ffmpeg로 병합
        import subprocess
        ffmpeg_cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
            '-i', str(temp_list_path),
            '-c', 'copy',
            str(output_path)
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
            logger.info(f"[CHUNKED TTS] 병합 완료: {output_path.name}")
        except subprocess.CalledProcessError as e:
            logger.error(f"[CHUNKED TTS] ffmpeg 병합 실패: {e.stderr.decode()}")
            # 폴백: 첫 번째 청크만 사용
            with open(output_path, "wb") as f:
                f.write(all_audio_data[0])
            logger.warning("[CHUNKED TTS] 폴백: 첫 번째 청크만 저장")

        # 임시 파일 삭제
        for idx in range(len(chunks)):
            temp_chunk_path = output_path.parent / f"temp_chunk_{idx}.mp3"
            try:
                temp_chunk_path.unlink()
            except:
                pass
        try:
            temp_list_path.unlink()
        except:
            pass

        # 최종 오디오 길이 측정
        try:
            audio_clip = AudioFileClip(str(output_path))
            total_duration = audio_clip.duration
            audio_clip.close()
        except Exception as e:
            logger.warning(f"최종 오디오 길이 측정 실패: {e}")
            total_duration = cumulative_time

        logger.info(f"[CHUNKED TTS] 전체 완료: {total_duration:.2f}초, 총 단어 {len(all_word_timings)}개")

        return total_duration, all_word_timings

    async def _generate_google_tts(self, text: str, output_path: Path) -> tuple:
        """Google Cloud TTS로 음성 생성 + 단어별 타임스탬프 추출"""
        logger.info(f"Google Cloud TTS 생성 중: {output_path.name}")

        # 텍스트 정리
        clean_text = self._clean_narration(text)

        if not clean_text:
            logger.warning("텍스트가 비어있어 기본 메시지 사용")
            clean_text = "무음"

        try:
            # Google Cloud TTS 클라이언트 초기화
            client = texttospeech.TextToSpeechClient()

            # 음성 매핑 (google-ko-KR-Neural2-A -> ko-KR-Neural2-A)
            voice_name = self.voice.replace('google-', '')

            # TTS 요청 설정
            synthesis_input = texttospeech.SynthesisInput(text=clean_text)
            voice = texttospeech.VoiceSelectionParams(
                language_code="ko-KR",
                name=voice_name
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=0.85,  # Edge TTS의 -15%와 유사
                effects_profile_id=['small-bluetooth-speaker-class-device']
            )

            # TTS 생성 (word-level timestamps 포함)
            response = client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config,
                enable_time_pointing=[texttospeech.SynthesisInput.TimepointType.SSML_MARK]
            )

            # 오디오 파일 저장
            with open(output_path, "wb") as f:
                f.write(response.audio_content)

            # 타임스탬프 추출 (Google TTS timepoints)
            word_timings = []
            if hasattr(response, 'timepoints') and response.timepoints:
                for i, timepoint in enumerate(response.timepoints):
                    word_timings.append({
                        "word": timepoint.mark_name,
                        "start": timepoint.time_seconds,
                        "end": response.timepoints[i + 1].time_seconds if i + 1 < len(response.timepoints) else timepoint.time_seconds + 0.5
                    })

            # 오디오 길이 가져오기
            try:
                audio_clip = AudioFileClip(str(output_path))
                duration = audio_clip.duration
                audio_clip.close()
            except Exception as e:
                logger.warning(f"오디오 길이 측정 실패, 기본값 1초 사용: {e}")
                duration = 1.0

            # 타임스탬프가 없으면 텍스트 기반으로 생성
            if not word_timings:
                logger.warning("Google TTS에서 타임스탬프를 받지 못했습니다. 텍스트 기반 폴백 사용")
                words = clean_text.split()
                time_per_word = duration / len(words) if words else duration
                for i, word in enumerate(words):
                    word_timings.append({
                        "word": word,
                        "start": i * time_per_word,
                        "end": (i + 1) * time_per_word
                    })

            logger.info(f"Google TTS 생성 완료: {duration:.2f}초, 단어 {len(word_timings)}개")
            return duration, word_timings

        except Exception as e:
            logger.error(f"Google Cloud TTS 실패: {e}")
            logger.warning("Edge TTS로 대체합니다.")
            # Edge TTS로 폴백
            self.tts_provider = 'edge'
            self.voice = "ko-KR-SoonBokNeural"
            return await self._generate_edge_tts(text, output_path)

    async def _generate_aws_polly(self, text: str, output_path: Path) -> tuple:
        """AWS Polly로 음성 생성 + 단어별 타임스탬프 추출"""
        logger.info(f"AWS Polly 생성 중: {output_path.name}")

        # 텍스트 정리
        clean_text = self._clean_narration(text)

        if not clean_text:
            logger.warning("텍스트가 비어있어 기본 메시지 사용")
            clean_text = "무음"

        try:
            # AWS Polly 클라이언트 초기화
            polly_client = boto3.client('polly', region_name='us-east-1')

            # 음성 매핑 (aws-Seoyeon -> Seoyeon)
            voice_id = self.voice.replace('aws-', '')

            # Speech marks 요청 (타임스탬프용)
            marks_response = polly_client.synthesize_speech(
                Text=clean_text,
                OutputFormat='json',
                VoiceId=voice_id,
                Engine='neural',
                SpeechMarkTypes=['word'],
                LanguageCode='ko-KR'
            )

            # 오디오 요청
            audio_response = polly_client.synthesize_speech(
                Text=clean_text,
                OutputFormat='mp3',
                VoiceId=voice_id,
                Engine='neural',
                LanguageCode='ko-KR'
            )

            # 오디오 파일 저장
            with open(output_path, "wb") as f:
                f.write(audio_response['AudioStream'].read())

            # 타임스탬프 추출
            word_timings = []
            marks_data = marks_response['AudioStream'].read().decode('utf-8')
            for line in marks_data.strip().split('\n'):
                if line:
                    mark = json.loads(line)
                    if mark['type'] == 'word':
                        word_timings.append({
                            "word": mark['value'],
                            "start": mark['time'] / 1000.0,  # ms -> s
                            "end": mark['time'] / 1000.0 + 0.3  # 임시 duration
                        })

            # 오디오 길이 가져오기
            try:
                audio_clip = AudioFileClip(str(output_path))
                duration = audio_clip.duration
                audio_clip.close()
            except Exception as e:
                logger.warning(f"오디오 길이 측정 실패, 기본값 1초 사용: {e}")
                duration = 1.0

            # end 시간 조정 (다음 단어 시작 시간 또는 duration 기준)
            for i in range(len(word_timings) - 1):
                word_timings[i]['end'] = word_timings[i + 1]['start']
            if word_timings:
                word_timings[-1]['end'] = duration

            logger.info(f"AWS Polly 생성 완료: {duration:.2f}초, 단어 {len(word_timings)}개")
            return duration, word_timings

        except (BotoCoreError, ClientError) as e:
            logger.error(f"AWS Polly 실패: {e}")
            logger.warning("Edge TTS로 대체합니다.")
            # Edge TTS로 폴백
            self.tts_provider = 'edge'
            self.voice = "ko-KR-SoonBokNeural"
            return await self._generate_edge_tts(text, output_path)
        except Exception as e:
            logger.error(f"AWS Polly 예상치 못한 오류: {e}")
            logger.warning("Edge TTS로 대체합니다.")
            # Edge TTS로 폴백
            self.tts_provider = 'edge'
            self.voice = "ko-KR-SoonBokNeural"
            return await self._generate_edge_tts(text, output_path)

    def _get_video_duration(self, video_path: Path) -> float:
        """FFprobe로 비디오 길이 확인"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                str(video_path.resolve())
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"⚠️ 비디오 길이 확인 실패: {e}")
            return 0.0

    def _combine_video_audio(self, scene_num: int, video_path: Path,
                            audio_path: Path, output_path: Path) -> Optional[Path]:
        """비디오 파일에 오디오 결합 - FFmpeg 직접 사용 (자막 없음)"""
        try:
            logger.info(f"씬 {scene_num} 비디오에 오디오 결합 중...")

            # FFmpeg 명령어로 비디오 + 오디오 결합
            # 자막이 없으므로 -c:v copy 사용 (빠름)
            cmd = [
                'ffmpeg',
                '-y',
                '-i', str(video_path.resolve()),  # 입력 비디오
                '-i', str(audio_path.resolve()),  # 입력 오디오
                '-c:v', 'copy',  # 비디오 재인코딩 없이 복사 (빠름)
                '-c:a', 'aac',  # 오디오 AAC 인코딩
                '-map', '0:v:0',  # 첫 번째 입력의 비디오
                '-map', '1:a:0',  # 두 번째 입력의 오디오
                '-y',  # 덮어쓰기
                str(output_path.resolve())  # 출력 경로
            ]

            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            logger.info(f"씬 {scene_num} 비디오+오디오 결합 완료: {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            logger.error(f"씬 {scene_num} 비디오+오디오 결합 실패: {e.stderr}")
            return None
        except Exception as e:
            logger.error(f"씬 {scene_num} 비디오+오디오 결합 실패: {e}")
            return None

    def _combine_video_audio_with_subtitles(self, scene_num: int, video_path: Path,
                                           audio_path: Path, output_path: Path,
                                           narration: str, audio_duration: float,
                                           word_timings: list = None) -> Optional[Path]:
        """비디오 파일에 오디오와 자막 결합 - FFmpeg 직접 사용 (영상병합 방식)"""
        try:
            logger.info(f"씬 {scene_num} 비디오에 오디오+자막 결합 중...")

            # 비디오 길이 확인
            video_duration = self._get_video_duration(video_path)
            logger.info(f"⏱️ 비디오 길이: {video_duration:.2f}초, 오디오 길이: {audio_duration:.2f}초")

            # Edge TTS 타임스탬프로 ASS 자막 파일 생성 (또는 대본 기반 폴백)
            srt_path = audio_path.with_suffix('.srt')
            ass_path = self._create_srt_with_timings(word_timings or [], srt_path, narration, audio_duration, max_chars_per_line=22)

            # FFmpeg ass 필터에 절대 경로 전달 (Windows 경로를 Unix 스타일로 변환 + 콜론 이스케이프)
            ass_absolute_path = str(ass_path.resolve()).replace('\\', '/').replace(':', '\\\\:')

            # 비디오와 오디오 길이 비교하여 필터 준비 (영상병합 방식)
            video_filter_parts = []
            audio_filter = None

            if video_duration < audio_duration:
                # 비디오가 짧으면: 마지막 프레임을 freeze하여 오디오 길이에 맞춤
                freeze_duration = audio_duration - video_duration
                video_filter_parts.append(f"tpad=stop_mode=clone:stop_duration={freeze_duration:.3f}")
                logger.info(f"⚠️ 비디오가 TTS보다 짧습니다. 마지막 프레임을 {freeze_duration:.2f}초 freeze합니다.")
            elif audio_duration < video_duration:
                # 오디오가 짧으면: 무음 추가하여 비디오 길이에 맞춤
                audio_filter = f"apad=whole_dur={video_duration:.3f}"
                logger.info(f"⚠️ TTS가 비디오보다 짧습니다. 무음을 추가하여 비디오 길이에 맞춥니다.")

            # 자막 필터 추가
            video_filter_parts.append(f"ass={ass_absolute_path}")
            vf_combined = ",".join(video_filter_parts)

            # FFmpeg 명령어로 비디오 + 오디오 + 자막 결합
            cmd = [
                'ffmpeg',
                '-y',
                '-i', str(video_path.resolve()),  # 입력 비디오
                '-i', str(audio_path.resolve()),  # 입력 오디오
                '-vf', vf_combined,  # 비디오 필터 (tpad + ass)
                '-c:v', self.video_codec,  # 비디오 재인코딩 (자막 때문에)
                '-preset', self.codec_preset,
                '-c:a', 'aac',  # 오디오 AAC 인코딩
                '-map', '0:v:0',  # 첫 번째 입력의 비디오
                '-map', '1:a:0',  # 두 번째 입력의 오디오
                '-pix_fmt', 'yuv420p',  # 호환성
            ]

            # 오디오 필터 추가 (패딩이 필요한 경우)
            if audio_filter:
                cmd.extend(['-af', audio_filter])

            cmd.extend([
                '-y',  # 덮어쓰기
                str(output_path.resolve())  # 출력 경로
            ])

            result = subprocess.run(cmd, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
            logger.info(f"씬 {scene_num} 비디오+오디오+자막 결합 완료: {output_path}")

            # 자막 파일 삭제
            if ass_path.exists():
                ass_path.unlink()
            if srt_path.exists():
                srt_path.unlink()

            return output_path

        except subprocess.CalledProcessError as e:
            # GPU 인코더 실패 시 CPU 폴백
            if 'h264_nvenc' in str(e.stderr) or 'nvenc' in str(e.stderr):
                logger.warning(f"씬 {scene_num} GPU 인코더 실패, CPU 인코더로 재시도...")
                try:
                    cmd_cpu = [
                        'ffmpeg',
                        '-y',
                        '-i', str(video_path.resolve()),
                        '-i', str(audio_path.resolve()),
                        '-vf', vf_combined,  # 비디오 필터 (tpad + ass)
                        '-c:v', 'libx264',  # CPU 인코더
                        '-preset', 'ultrafast',
                        '-c:a', 'aac',
                        '-map', '0:v:0',
                        '-map', '1:a:0',
                        '-pix_fmt', 'yuv420p',
                    ]

                    if audio_filter:
                        cmd_cpu.extend(['-af', audio_filter])

                    cmd_cpu.extend(['-y', str(output_path.resolve())])

                    result = subprocess.run(cmd_cpu, check=True, capture_output=True, text=True, encoding='utf-8', errors='ignore')
                    logger.info(f"씬 {scene_num} 비디오+오디오+자막 결합 완료 (CPU): {output_path}")

                    if ass_path.exists():
                        ass_path.unlink()
                    if srt_path.exists():
                        srt_path.unlink()

                    return output_path
                except subprocess.CalledProcessError as e2:
                    logger.error(f"씬 {scene_num} CPU 인코더도 실패: {e2.stderr}")
                    return None
            else:
                logger.error(f"씬 {scene_num} 비디오+오디오+자막 결합 실패: {e.stderr}")
                return None
        except Exception as e:
            logger.error(f"씬 {scene_num} 비디오+오디오+자막 결합 실패: {e}")
            return None

    def _create_scene_video(self, scene_num: int, image_path: Path,
                           audio_path: Path, output_path: Path) -> Optional[Path]:
        """씬 비디오 생성 (이미지 + 오디오) - FFmpeg 직접 사용"""
        try:
            logger.info(f"씬 {scene_num} 비디오 생성 중...")

            # ============================================================
            # 숏폼 영상인 경우 16:9 이미지를 9:16으로 스마트 크롭
            # ============================================================
            processed_image_path = image_path
            temp_image_file = None

            if self.aspect_ratio == "9:16":
                try:
                    # 이미지 비율 체크
                    with PILImage.open(image_path) as img:
                        width, height = img.size
                        img_ratio = width / height

                        # 16:9 비율 (가로 영상)인지 확인 (허용 오차 ±10%)
                        target_landscape_ratio = 16 / 9  # 1.778
                        is_landscape = abs(img_ratio - target_landscape_ratio) < 0.2

                        if is_landscape:
                            logger.info(f"  🎨 씬 {scene_num}: 롱폼 이미지 감지 ({width}x{height}, 비율: {img_ratio:.3f})")
                            logger.info(f"  ✂️ 스마트 크롭 적용 중 (얼굴/물체 중심)...")

                            # 임시 파일 생성
                            temp_image_file = image_path.parent / f"temp_cropped_scene_{scene_num}.jpg"

                            # 스마트 크롭 적용
                            if self._smart_crop_to_vertical(image_path, temp_image_file):
                                processed_image_path = temp_image_file
                                logger.info(f"  ✅ 스마트 크롭 완료: {temp_image_file.name}")
                            else:
                                logger.warning(f"  ⚠️ 스마트 크롭 실패, 원본 이미지 사용 (레터박스 적용)")
                except Exception as e:
                    logger.warning(f"  ⚠️ 이미지 비율 체크 실패: {e}, 원본 이미지 사용")

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
        """여러 씬 비디오를 하나로 결합 - FFmpeg concat demuxer 사용"""
        import tempfile

        # generated_videos 폴더에서 씬 비디오 찾기
        video_folder = output_path.parent / "generated_videos"
        logger.info(f"비디오 결합 시작: {len(video_paths)}개 씬")
        logger.info(f"씬 비디오 검색 경로: {video_folder}")

        # scene_XX.mp4 파일 찾기
        scene_videos = sorted(video_folder.glob("scene_*.mp4"))
        if not scene_videos:
            logger.error(f"씬 비디오 파일을 찾을 수 없습니다 (경로: {video_folder})")
            return None

        logger.info(f"발견된 씬 비디오: {len(scene_videos)}개")

        # concat list 파일 생성 (임시 파일)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
            concat_file = f.name
            for video in scene_videos:
                # FFmpeg concat demuxer 형식: file 'path'
                # Windows 경로를 위해 forward slash로 변환하고 이스케이프
                video_path_str = str(video.absolute()).replace('\\', '/')
                f.write(f"file '{video_path_str}'\n")

        try:
            # FFmpeg concat demuxer로 병합
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',  # 재인코딩 없이 복사
                '-y',  # 덮어쓰기
                str(output_path)
            ]

            logger.info(f"FFmpeg 실행: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )

            if result.returncode != 0:
                logger.error(f"FFmpeg 실패 (종료 코드: {result.returncode})")
                if result.stderr:
                    logger.error(f"에러 메시지:\n{result.stderr}")
                return None

            if not output_path.exists():
                logger.error(f"병합된 비디오 파일이 생성되지 않았습니다: {output_path}")
                return None

            # 총 수행 시간
            elapsed_time = time() - start_time
            minutes = int(elapsed_time // 60)
            seconds = int(elapsed_time % 60)
            logger.info(f"비디오 결합 완료: {output_path}")
            logger.info(f"총 수행 시간: {minutes}분 {seconds}초")

            return output_path

        finally:
            # 임시 concat 파일 삭제
            try:
                Path(concat_file).unlink()
            except Exception as e:
                logger.warning(f"임시 파일 삭제 실패: {e}")

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

        # 기존 generated_videos 폴더 백업 (비활성화 - backup 폴더 생성 방지)
        # self._backup_previous_videos()

        # 이미지와 비디오 파일 찾기 (자동 생성 포함)
        images_dict = self._find_images_with_scene_numbers()  # 이미지 자동 생성 포함
        videos_dict = self._find_videos()  # 비디오 파일 찾기

        # dict를 씬 번호 순서로 정렬하여 list로 변환
        image_paths = [images_dict[k] for k in sorted(images_dict.keys())]
        video_paths = [videos_dict[k] for k in sorted(videos_dict.keys())]

        if not image_paths and not video_paths:
            logger.error("이미지 또는 비디오를 찾을 수 없습니다. 최소 1개 이상의 미디어 파일이 필요합니다.")
            return None

        # 이미지와 비디오를 통합 정렬 (타입 구분 없이)
        logger.info(f"📊 통합 정렬 시작: 이미지 {len(image_paths)}개, 비디오 {len(video_paths)}개")

        # 모든 미디어 파일을 하나의 리스트로 합치기
        all_media_files = []
        for path in image_paths:
            all_media_files.append(('image', path))
        for path in video_paths:
            all_media_files.append(('video', path))

        # 통합 정렬 함수
        def extract_sequence_unified(media_tuple):
            """시퀀스 번호 추출 (타입 관계없이)"""
            media_type, filepath = media_tuple
            import re
            name = filepath.stem

            # 패턴 매칭 (image_01, video_02, scene_03, clip_01 등)
            match = re.match(r'^(image|video|scene|clip|img)[-_](\d+)$', name, re.IGNORECASE)
            if match:
                return (int(match.group(2)), 0)

            match = re.match(r'^(image|video|scene|clip|img)\((\d+)\)$', name, re.IGNORECASE)
            if match:
                return (int(match.group(2)), 0)

            match = re.match(r'^\((\d+)\)$', name)
            if match:
                return (int(match.group(1)), 0)

            match = re.match(r'^(\d+)$', name)
            if match:
                return (int(match.group(1)), 0)

            # 파일명 어디든 숫자가 있으면 추출 (영상01, 한글01, abc123 등)
            match = re.search(r'(\d+)', name)
            if match:
                return (int(match.group(1)), 0)

            # 숫자가 없으면 파일 시간
            try:
                mtime = filepath.stat().st_mtime
            except:
                mtime = 0
            return (None, mtime)

        # 정렬: 시퀀스 번호 우선, 없으면 시간 순
        all_media_files.sort(key=lambda f: (
            extract_sequence_unified(f)[0] is None,
            extract_sequence_unified(f)[0] if extract_sequence_unified(f)[0] is not None else 0,
            extract_sequence_unified(f)[1]
        ))

        # 씬 번호 재할당
        images = {}
        videos = {}
        logger.info(f"\n🎯 통합 정렬 결과 (총 {len(all_media_files)}개):")
        for idx, (media_type, filepath) in enumerate(all_media_files, start=1):
            if media_type == 'image':
                images[idx] = filepath
            else:
                videos[idx] = filepath

            seq_info = extract_sequence_unified((media_type, filepath))
            if seq_info[0] is not None:
                logger.info(f"  씬 {idx}: {filepath.name} ({media_type.upper()}, 시퀀스: {seq_info[0]})")
            else:
                import datetime
                mtime_str = datetime.datetime.fromtimestamp(seq_info[1]).strftime('%Y-%m-%d %H:%M:%S')
                logger.info(f"  씬 {idx}: {filepath.name} ({media_type.upper()}, 시간: {mtime_str})")

        logger.info(f"✅ 최종: 이미지 {len(images)}개, 비디오 {len(videos)}개")

        # scenes 가져오기
        scenes = self.story_data.get("scenes", [])

        if not scenes:
            logger.error("story.json에 scenes가 없습니다.")
            return None

        # 나레이션이 있는 씬 개수 계산 (scene_num > 0)
        narration_count = 0
        for scene in scenes:
            scene_num = scene.get("scene_number")
            if scene_num is None:
                scene_id = scene.get("scene_id", "")
                import re
                match = re.search(r'scene_(\d+)', scene_id)
                if match:
                    scene_num = int(match.group(1))
            if scene_num and scene_num > 0:
                narration_count += 1

        # 미디어 개수 (이미지 + 비디오)
        total_media = len(images) + len(videos)

        logger.info(f"📝 나레이션 씬 개수: {narration_count}개")
        logger.info(f"🎬 총 미디어 개수: {total_media}개")

        # 나레이션이 미디어보다 많으면 미디어를 균등 분배
        if narration_count > total_media and total_media > 0:
            logger.info(f"⚠️ 나레이션({narration_count})이 미디어({total_media})보다 많습니다.")
            logger.info(f"📊 미디어를 균등 분배하여 각 씬에 할당합니다.")

            # 미디어 리스트 생성 (이미 통합 정렬된 순서대로)
            # images와 videos의 키를 합쳐서 정렬하면 통합 정렬된 순서가 유지됨
            all_media = []
            all_keys = sorted(set(images.keys()) | set(videos.keys()))

            for idx in all_keys:
                if idx in images:
                    all_media.append(('image', idx, images[idx]))
                elif idx in videos:
                    all_media.append(('video', idx, videos[idx]))

            # 각 미디어가 처리할 씬 개수 계산 (균등 분배)
            scenes_per_media = narration_count // total_media  # 기본 개수
            extra_scenes = narration_count % total_media  # 나머지 (일부 미디어에 +1)

            new_images = {}
            new_videos = {}
            current_scene = 1

            for media_idx, (media_type, orig_num, media_path) in enumerate(all_media):
                # 이 미디어가 처리할 씬 개수 (나머지는 뒤에 할당)
                # 예: 대본3개/영상2개 → 영상1(1개), 영상2(2개)
                remaining_media = total_media - media_idx
                if remaining_media > extra_scenes:
                    num_scenes = scenes_per_media
                else:
                    num_scenes = scenes_per_media + 1

                logger.info(f"  {media_type.upper()} {media_path.name} → {num_scenes}개 씬 처리")

                for _ in range(num_scenes):
                    if current_scene > narration_count:
                        break

                    # 원본 미디어 파일을 씬에 할당 (항상 원본 사용!)
                    if media_type == 'image':
                        new_images[current_scene] = media_path  # 원본 경로
                    else:
                        new_videos[current_scene] = media_path  # 원본 경로

                    logger.info(f"    씬 {current_scene}: {media_path.name} (원본)")
                    current_scene += 1

            images = new_images
            videos = new_videos
            logger.info(f"✅ 균등 분배 완료: 이미지 {len(images)}개, 비디오 {len(videos)}개")

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

        # 마지막으로 사용한 미디어 추적 (영상병합 방식)
        last_media_path = None
        last_media_type = None

        for scene in scenes:
            # 취소 플래그 파일 체크
            cancel_file = self.folder_path / '.cancel'
            if cancel_file.exists():
                logger.warning("🛑 취소 플래그 감지됨. 영상 생성을 중단합니다.")
                raise KeyboardInterrupt("User cancelled the operation")

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

            # scene_num이 0이면 건너뜀 (인트로/폭탄씬)
            if scene_num == 0:
                logger.info(f"씬 {scene_num} (인트로/폭탄씬): 건너뜀.")
                continue

            # 이미지 또는 비디오가 있는지 확인
            has_image = scene_num in images
            has_video = scene_num in videos

            # 미디어가 없으면 건너뜀 (순환 할당으로 인해 대부분 있을 것)
            if not has_image and not has_video:
                logger.warning(f"씬 {scene_num}: 미디어 파일이 없습니다. 건너뜀.")
                continue

            # 미디어 타입 결정 (비디오 우선)
            media_type = 'video' if has_video else 'image'
            media_path = videos[scene_num] if has_video else images[scene_num]
            logger.info(f"씬 {scene_num}: {media_type.upper()} 사용 - {media_path.name}")

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
                'media_path': media_path,
                'media_type': media_type,
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

        # 시스템에 무리 안 가도록 워커 수 제한 (CPU 코어의 75%, 최소 2, 최대 3)
        cpu_count = multiprocessing.cpu_count()
        max_workers = max(2, min(3, (cpu_count * 3) // 4))
        logger.info(f"⚡ 병렬 처리: {max_workers}개 워커 (CPU 코어: {cpu_count}개)")
        logger.info("=" * 70)

        scene_videos = []
        all_narrations = []

        # 병렬 처리 함수
        def process_scene(idx, scene_data):
            scene_num = scene_data['scene_num']
            media_path = scene_data['media_path']
            media_type = scene_data['media_type']
            audio_path = scene_data['audio_path']
            clean_narration = scene_data['clean_narration']

            progress = f"[{idx}/{len(scene_data_list)}]"
            logger.info(f"\n{progress} 씬 {scene_num} 처리 중... ({media_type.upper()})")

            # 비디오 생성 (자막 포함)
            video_path = output_folder / f"scene_{scene_num:02d}.mp4"

            # 비디오 파일이 이미 있으면 그대로 사용하거나 오디오와 결합
            if media_type == 'video':
                logger.info(f"{progress} 씬 {scene_num}: 비디오 파일에 오디오 결합 중...")
                # 비디오에 오디오를 결합 (자막은 선택사항)
                if self.add_subtitles:
                    audio_duration = scene_data.get('audio_duration', 1.0)
                    word_timings = scene_data.get('word_timings', [])
                    result = self._combine_video_audio_with_subtitles(
                        scene_num, media_path, audio_path, video_path,
                        clean_narration, audio_duration, word_timings
                    )
                else:
                    result = self._combine_video_audio(scene_num, media_path, audio_path, video_path)
            else:
                # 이미지에서 비디오 생성
                logger.info(f"{progress} 씬 {scene_num} 비디오 생성 중... ({encoder_type})")
                if self.add_subtitles:
                    audio_duration = scene_data.get('audio_duration', 1.0)
                    word_timings = scene_data.get('word_timings', [])  # Edge TTS 타임스탬프
                    result = self._create_scene_video_with_subtitles(
                        scene_num, media_path, audio_path, video_path,
                        clean_narration, audio_duration, word_timings
                    )
                else:
                    result = self._create_scene_video(scene_num, media_path, audio_path, video_path)

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
            # 최종 영상을 프로젝트 루트에 저장 (영상병합과 같은 위치)
            final_path = self.folder_path / f"{safe_title}.mp4"
            logger.info(f"📝 최종 영상 제목: {title} → {safe_title}.mp4")
            logger.info(f"📂 최종 영상 위치: {final_path}")
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
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
                        # 정상적으로 줄바꿈 - 현재 라인의 끝 시간은 current_end (이전 단어의 끝)
                        subtitles.append({
                            "start": current_start,
                            "end": current_end,  # 수정: end 대신 current_end 사용
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

            # 자막이 겹치지 않도록 시간 조정 (영상병합 방식)
            for i in range(len(subtitles) - 1):
                current_sub = subtitles[i]
                next_sub = subtitles[i + 1]

                # 현재 자막이 다음 자막과 겹치거나 간격이 너무 좁으면 조정
                if current_sub["end"] >= next_sub["start"]:
                    # 다음 자막 시작 직전으로 조정 (0.05초 간격)
                    gap = 0.05
                    adjusted_end = next_sub["start"] - gap
                    # 최소 표시 시간 보장 (0.3초)
                    min_duration = 0.3
                    if adjusted_end - current_sub["start"] < min_duration:
                        # 현재 자막이 너무 짧아지면 다음 자막 시작을 뒤로 밀기
                        current_sub["end"] = current_sub["start"] + min_duration
                        next_sub["start"] = current_sub["end"] + gap
                    else:
                        current_sub["end"] = adjusted_end

            # 마지막 자막이 오디오 길이를 초과하지 않도록 조정
            if subtitles and subtitles[-1]["end"] > audio_duration:
                subtitles[-1]["end"] = audio_duration

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
    parser.add_argument("--add-subtitles", "-s", action="store_true", default=True,
                       help="자막 추가 (기본: 추가함, --no-subtitles로 끄기)")
    parser.add_argument("--no-subtitles", action="store_false", dest="add_subtitles",
                       help="자막 추가 안 함")
    parser.add_argument("--image-source", "-i", default="none", choices=["none", "dalle", "imagen3"],
                       help="이미지 소스 (기본: none - 수동 업로드, dalle - DALL-E 3, imagen3 - Google Imagen 3)")
    parser.add_argument("--image-provider", default="openai", choices=["openai", "imagen3"],
                       help="이미지 생성 제공자 (기본: openai - DALL-E 3, imagen3 - Google Imagen 3)")
    parser.add_argument("--is-admin", action="store_true",
                       help="관리자 모드 (비용 로그 표시)")
    parser.add_argument("--job-id", default=None,
                       help="Job ID (추적용)")

    args = parser.parse_args()

    # DB 로깅 설정 (JOB_ID가 있으면)
    job_id = args.job_id or os.environ.get('JOB_ID')
    if job_id:
        try:
            from src.utils import auto_setup_db_logging
            global logger
            logger = auto_setup_db_logging()
            logger.info(f"DB 로깅 활성화됨 - Job ID: {job_id}")
        except Exception as e:
            logger.warning(f"DB 로깅 설정 실패: {e}")

    # 로그 폴더 생성
    os.makedirs("logs", exist_ok=True)

    print("=" * 70)
    print("VideoFromFolder Creator")
    print("=" * 70)
    if args.job_id:
        print(f"🆔 Job ID: {args.job_id}")
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
        image_provider=args.image_provider,
        is_admin=args.is_admin
    )

    # 비디오 생성 (항상 병합)
    result = asyncio.run(creator.create_all_videos(combine=True))

    if result:
        print("=" * 70)
        print("✓ 성공!")
        print("=" * 70)
        if args.job_id:
            print(f"🆔 Job ID: {args.job_id}")
        print(f"출력: {result}")
        print("=" * 70)
    else:
        print("✗ 실패!")
        if args.job_id:
            print(f"🆔 Job ID: {args.job_id}")
        sys.exit(1)


if __name__ == "__main__":
    main()
