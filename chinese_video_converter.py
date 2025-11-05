"""
중국어 영상을 한국어로 변환하는 스크립트

기능:
1. 중국어 자막/음성 추출
2. 중국어 → 한국어 번역
3. 한국어 TTS 생성
4. 영상 합성

사용법:
    python chinese_video_converter.py --input "video.mp4" --output-dir "output"
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
import subprocess
import asyncio
from typing import List, Dict, Optional
import tempfile
import shutil
import cv2
import numpy as np

# Windows에서 UTF-8 출력을 위해 stdout을 UTF-8로 재설정
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=sys.stdout,
    force=True
)
logger = logging.getLogger(__name__)

def should_stop(output_dir: Path) -> bool:
    """
    STOP 파일 존재 여부 확인 (영상 제작과 동일한 방식)

    Args:
        output_dir: 작업 디렉토리

    Returns:
        bool: STOP 파일 존재 여부
    """
    stop_file = Path(output_dir) / 'STOP'
    return stop_file.exists()

class CancelledException(Exception):
    """작업이 취소되었을 때 발생하는 예외"""
    pass

# OpenAI API (Whisper 및 TTS)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("⚠️ openai 모듈이 설치되지 않았습니다. pip install openai")

# Anthropic Claude API (번역)
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("⚠️ anthropic 모듈이 설치되지 않았습니다. pip install anthropic")

# Edge TTS (대체 옵션)
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("⚠️ edge-tts 모듈이 설치되지 않았습니다.")


def get_ffmpeg_path():
    """FFmpeg 경로 확인"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            return 'ffmpeg'
    except FileNotFoundError:
        pass

    # imageio-ffmpeg 시도
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass

    raise RuntimeError("FFmpeg를 찾을 수 없습니다. FFmpeg를 설치해주세요.")


def get_video_dimensions(video_path: Path) -> tuple:
    """비디오 해상도 가져오기 (width, height)"""
    try:
        ffmpeg = get_ffmpeg_path()
        ffprobe = ffmpeg.replace('ffmpeg', 'ffprobe')

        cmd = [
            ffprobe,
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            str(video_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            width, height = map(int, result.stdout.strip().split(','))
            return width, height
        return 1920, 1080  # 기본값

    except Exception as e:
        logger.warning(f"⚠️ 비디오 해상도 확인 실패: {e}, 기본값 사용 (1920x1080)")
        return 1920, 1080


def _remove_subtitle_vsr(input_video: Path, output_video: Path, x: int, y: int, w: int, h: int, output_dir: Path = None) -> bool:
    """
    video-subtitle-remover를 사용한 자막 제거 (가장 효과적)

    Args:
        input_video: 입력 비디오 경로
        output_video: 출력 비디오 경로
        x, y, w, h: 자막 영역
        output_dir: 작업 디렉토리 (STOP 파일 체크용)

    Returns:
        성공 여부
    """
    try:
        # STOP 체크
        if output_dir and should_stop(output_dir):
            raise CancelledException("VSR 자막 제거 시작 전 작업 취소됨")
        import sys
        vsr_dir = Path(__file__).parent / "video-subtitle-remover"
        backend_dir = vsr_dir / "backend"

        # 경로 추가
        if str(vsr_dir) not in sys.path:
            sys.path.insert(0, str(vsr_dir))
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        # video-subtitle-remover 임포트
        from backend.main import SubtitleRemover
        from backend import config

        logger.info(f"🎨 video-subtitle-remover (LAMA) 초기화 중...")

        # 자막 영역 설정 (ymin, ymax, xmin, xmax 형식 - 튜플)
        sub_area = (y, y+h, x, x+w)

        # SubtitleRemover 초기화
        remover = SubtitleRemover(
            vd_path=str(input_video),
            sub_area=sub_area
        )

        logger.info(f"✅ LAMA 모델 로딩 완료")
        logger.info(f"🎬 자막 제거 진행 중... (시간이 걸릴 수 있습니다)")

        # 자막 제거 실행
        remover.run()

        # 결과 파일 경로 (원본 파일명 + _no_sub)
        result_path = Path(str(input_video).replace('.mp4', '_no_sub.mp4'))

        if result_path.exists():
            # 결과 파일을 output_video로 복사
            shutil.copy2(result_path, output_video)
            logger.info(f"✅ LAMA-VSR 자막 제거 완료")
            # 임시 파일 삭제
            result_path.unlink()
            return True
        else:
            logger.error(f"❌ 결과 파일이 생성되지 않았습니다: {result_path}")
            return False

    except Exception as e:
        logger.error(f"❌ LAMA-VSR 자막 제거 실패: {e}")
        import traceback
        traceback.print_exc()
        return False


def _remove_watermark_lama(input_video: Path, output_video: Path, x: int, y: int, w: int, h: int, output_dir: Path = None) -> bool:
    """
    LAMA를 사용한 워터마크 제거 (video-subtitle-remover의 LAMA 모델 사용)

    Args:
        input_video: 입력 비디오 경로
        output_video: 출력 비디오 경로
        x, y, w, h: 워터마크 영역
        output_dir: 작업 디렉토리 (STOP 파일 체크용)

    Returns:
        성공 여부
    """
    try:
        # STOP 체크
        if output_dir and should_stop(output_dir):
            raise CancelledException("LAMA 워터마크 제거 시작 전 작업 취소됨")
        import sys
        vsr_dir = Path(__file__).parent / "video-subtitle-remover"
        backend_dir = vsr_dir / "backend"

        # 경로 추가
        if str(vsr_dir) not in sys.path:
            sys.path.insert(0, str(vsr_dir))
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        # LAMA 모델 경로 확인
        lama_model_dir = backend_dir / "models" / "big-lama"
        if not lama_model_dir.exists():
            logger.error(f"❌ LAMA 모델 디렉토리가 없습니다: {lama_model_dir}")
            return False

        # 모델 파일 확인
        model_files = list(lama_model_dir.glob("big-lama_*.pt"))
        if len(model_files) == 0:
            logger.error(f"❌ LAMA 모델 파일이 없습니다: {lama_model_dir}")
            return False

        logger.info(f"✅ LAMA 모델 파일 발견: {len(model_files)}개")

        # LAMA 인페인트 임포트
        from backend.inpaint.lama_inpaint import LamaInpaint
        import torch
        import cv2
        import numpy as np

        # 임시 디렉토리 생성
        temp_dir = Path(tempfile.mkdtemp())
        frames_dir = temp_dir / "frames"
        mask_dir = temp_dir / "masks"
        inpaint_dir = temp_dir / "inpainted"

        frames_dir.mkdir(exist_ok=True)
        mask_dir.mkdir(exist_ok=True)
        inpaint_dir.mkdir(exist_ok=True)

        try:
            ffmpeg = get_ffmpeg_path()

            # 1. 프레임 추출
            logger.info(f"🎞️ 프레임 추출 중...")
            cmd = [
                ffmpeg, '-i', str(input_video),
                '-vf', 'fps=30',  # 30fps로 고정
                str(frames_dir / 'frame_%06d.png')
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ 프레임 추출 실패: {result.stderr}")
                return False

            # 프레임 파일 목록
            frame_files = sorted(frames_dir.glob("frame_*.png"))
            total_frames = len(frame_files)
            logger.info(f"✅ {total_frames}개 프레임 추출 완료")

            # 2. 마스크 생성
            logger.info(f"🎨 마스크 생성 중...")
            first_frame = cv2.imread(str(frame_files[0]))
            mask = np.zeros(first_frame.shape[:2], dtype=np.uint8)
            mask[y:y+h, x:x+w] = 255

            # 모든 프레임에 동일한 마스크 적용
            for frame_file in frame_files:
                mask_file = mask_dir / frame_file.name
                cv2.imwrite(str(mask_file), mask)

            logger.info(f"✅ {total_frames}개 마스크 생성 완료")

            # 3. LAMA 인페인팅 초기화
            logger.info(f"🤖 LAMA 모델 로딩 중...")
            device = 'cuda' if torch.cuda.is_available() else 'cpu'
            logger.info(f"   디바이스: {device}")

            lama_inpaint = LamaInpaint(device=device)
            logger.info(f"✅ LAMA 모델 로딩 완료")

            # 4. 프레임별 인페인팅
            logger.info(f"🎨 LAMA 인페인팅 진행 중...")
            for i, frame_file in enumerate(frame_files, 1):
                # STOP 체크 (10프레임마다)
                if i % 10 == 0 and output_dir and should_stop(output_dir):
                    raise CancelledException(f"LAMA 인페인팅 중 작업 취소됨 ({i}/{total_frames} 프레임)")

                if i % 30 == 0 or i == total_frames:
                    logger.info(f"   처리 중: {i}/{total_frames} 프레임 ({i*100//total_frames}%)")

                frame = cv2.imread(str(frame_file))
                mask_file = mask_dir / frame_file.name
                mask_img = cv2.imread(str(mask_file), cv2.IMREAD_GRAYSCALE)

                # LAMA 인페인팅 수행
                result_frame = lama_inpaint.inpaint(frame, mask_img)

                # 결과 저장
                output_frame_file = inpaint_dir / frame_file.name
                cv2.imwrite(str(output_frame_file), result_frame)

            logger.info(f"✅ {total_frames}개 프레임 인페인팅 완료")

            # 5. 비디오 재조립
            logger.info(f"🎬 비디오 재조립 중...")
            cmd = [
                ffmpeg, '-framerate', '30',
                '-i', str(inpaint_dir / 'frame_%06d.png'),
                '-i', str(input_video),  # 오디오 소스
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '18',
                '-pix_fmt', 'yuv420p',
                '-c:a', 'copy',  # 오디오 복사
                '-map', '0:v:0',  # 비디오는 첫 번째 입력
                '-map', '1:a:0?',  # 오디오는 두 번째 입력 (있으면)
                '-y',
                str(output_video)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ 비디오 재조립 실패: {result.stderr}")
                return False

            logger.info(f"✅ LAMA 워터마크 제거 완료")
            return True

        finally:
            # 임시 파일 정리
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"❌ LAMA 워터마크 제거 실패: {e}")
        traceback.print_exc()
        return False


def _remove_watermark_sttn(input_video: Path, output_video: Path, x: int, y: int, w: int, h: int, output_dir: Path = None) -> bool:
    """
    STTN을 사용한 워터마크 제거 (video-subtitle-remover 사용)

    Args:
        input_video: 입력 비디오 경로
        output_video: 출력 비디오 경로
        x, y, w, h: 워터마크 영역
        output_dir: 작업 디렉토리 (STOP 파일 체크용)

    Returns:
        성공 여부
    """
    try:
        # STOP 체크
        if output_dir and should_stop(output_dir):
            raise CancelledException("STTN 워터마크 제거 시작 전 작업 취소됨")
        # video-subtitle-remover 경로
        vsr_dir = Path(__file__).parent / "video-subtitle-remover"
        if not vsr_dir.exists():
            logger.error(f"❌ video-subtitle-remover 디렉토리가 없습니다: {vsr_dir}")
            return False

        # 모델 파일 확인
        model_path = vsr_dir / "backend" / "models" / "sttn" / "infer_model.pth"
        if not model_path.exists():
            logger.error(f"❌ STTN 모델 파일이 없습니다: {model_path}")
            return False

        logger.info("🚀 STTN 알고리즘으로 워터마크 제거 시작...")

        # video-subtitle-remover의 main.py를 직접 호출
        backend_dir = vsr_dir / "backend"
        main_script = backend_dir / "main.py"

        if not main_script.exists():
            logger.error(f"❌ main.py가 없습니다: {main_script}")
            return False

        # Python 명령어 실행
        cmd = [
            sys.executable,
            str(main_script),
            '--input_video', str(input_video),
            '--output_video', str(output_video),
            '--x', str(x),
            '--y', str(y),
            '--w', str(w),
            '--h', str(h),
            '--use_sttn'
        ]

        logger.info(f"   실행: {' '.join(cmd)}")

        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(backend_dir))

        if result.returncode == 0:
            logger.info("✅ STTN 워터마크 제거 완료")
            return True
        else:
            logger.error(f"❌ STTN 실행 실패: {result.stderr}")
            return False

    except Exception as e:
        logger.error(f"❌ STTN 처리 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def _remove_watermark_e2fgvi(input_video: Path, output_video: Path, x: int, y: int, w: int, h: int, output_dir: Path = None) -> bool:
    """
    E2FGVI를 사용한 워터마크 제거 (속도와 품질의 균형)

    Args:
        input_video: 입력 비디오 경로
        output_video: 출력 비디오 경로
        x, y, w, h: 워터마크 영역
        output_dir: 작업 디렉토리 (STOP 파일 체크용)

    Returns:
        성공 여부
    """
    try:
        # STOP 체크
        if output_dir and should_stop(output_dir):
            raise CancelledException("E2FGVI 워터마크 제거 시작 전 작업 취소됨")
        # E2FGVI 경로
        erase_subtitles_dir = Path(__file__).parent / "EraseSubtitles"
        if not erase_subtitles_dir.exists():
            logger.error(f"❌ EraseSubtitles 디렉토리가 없습니다: {erase_subtitles_dir}")
            return False

        # 모델 파일 확인
        model_path = erase_subtitles_dir / "E2FGVI" / "release_model" / "E2FGVI-CVPR22.pth"
        if not model_path.exists():
            logger.error(f"❌ E2FGVI 모델 파일이 없습니다: {model_path}")
            logger.error(f"   다운로드: https://drive.google.com/file/d/1tNJMTJ2gmWdIXJoHVi5-H504uImUiJW9/view")
            return False

        # sys.path에 추가
        import sys
        if str(erase_subtitles_dir) not in sys.path:
            sys.path.insert(0, str(erase_subtitles_dir))

        # 임시 디렉토리 생성
        temp_dir = Path(tempfile.mkdtemp())
        frames_dir = temp_dir / "frames"
        masks_dir = temp_dir / "masks"
        frames_dir.mkdir(exist_ok=True)
        masks_dir.mkdir(exist_ok=True)

        try:
            # FFmpeg로 프레임 추출
            ffmpeg = get_ffmpeg_path()
            logger.info("🎬 프레임 추출 중...")

            extract_cmd = [
                ffmpeg, '-i', str(input_video),
                '-qscale:v', '2',
                str(frames_dir / '%d.jpg')
            ]

            result = subprocess.run(extract_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ 프레임 추출 실패: {result.stderr}")
                return False

            frame_files = sorted(frames_dir.glob('*.jpg'), key=lambda p: int(p.stem))
            if not frame_files:
                logger.error("❌ 추출된 프레임이 없습니다")
                return False

            logger.info(f"✅ {len(frame_files)}개 프레임 추출 완료")

            # 마스크 생성 (모든 프레임에 동일한 마스크)
            logger.info("🎨 마스크 생성 중...")
            first_frame = cv2.imread(str(frame_files[0]))
            height_vid, width_vid = first_frame.shape[:2]

            # 마스크 이미지 생성 (워터마크 영역을 흰색으로)
            mask = np.zeros((height_vid, width_vid), dtype=np.uint8)
            mask[y:y+h, x:x+w] = 255

            # 모든 프레임에 대해 동일한 마스크 저장
            for i in range(len(frame_files)):
                cv2.imwrite(str(masks_dir / f"{i}.png"), mask)

            logger.info(f"✅ {len(frame_files)}개 마스크 생성 완료")

            # E2FGVI inpaint 함수 import
            from inpaint import set_up_model, get_images_and_masks, preprocess_images_and_masks, inpaint

            logger.info("🤖 E2FGVI 모델 로드 중...")
            model, device = set_up_model()

            logger.info("🎨 E2FGVI 인페인팅 시작...")
            frames, masks = get_images_and_masks(str(frames_dir), str(masks_dir))
            f, binary_masks, imgs, m = preprocess_images_and_masks(frames, masks, device)
            video_length = len(frames)
            comp_frames = inpaint(f, binary_masks, imgs, m, video_length, model)

            # 결과 프레임 저장
            logger.info("💾 결과 프레임 저장 중...")
            output_frames_dir = temp_dir / "output_frames"
            output_frames_dir.mkdir(exist_ok=True)

            ind = -1
            for i in range(video_length):
                if i % 30 == 0:
                    ind += 1
                frame = comp_frames[ind][i % 30]
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                cv2.imwrite(str(output_frames_dir / f"{i:05d}.jpg"), frame_bgr)

            # FFmpeg로 비디오 재조립
            logger.info("🎬 비디오 재조립 중...")

            fps = get_video_fps(input_video)

            assemble_cmd = [
                ffmpeg, '-y',
                '-framerate', str(fps),
                '-i', str(output_frames_dir / '%05d.jpg'),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-crf', '18',
                str(output_video)
            ]

            result = subprocess.run(assemble_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"❌ 비디오 재조립 실패: {result.stderr}")
                return False

            logger.info(f"✅ E2FGVI 처리 완료: {output_video}")
            return True

        finally:
            # 임시 파일 정리
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"❌ E2FGVI 처리 중 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def _remove_watermark_propainter(input_video: Path, output_video: Path, x: int, y: int, w: int, h: int, output_dir: Path = None) -> bool:
    """
    ProPainter를 사용한 고품질 워터마크 제거

    Args:
        input_video: 입력 비디오 경로
        output_video: 출력 비디오 경로
        x, y, w, h: 워터마크 영역
        output_dir: 작업 디렉토리 (STOP 파일 체크용)

    Returns:
        성공 여부
    """
    try:
        # STOP 체크
        if output_dir and should_stop(output_dir):
            raise CancelledException("ProPainter 워터마크 제거 시작 전 작업 취소됨")
        # ProPainter 경로
        propainter_dir = Path(__file__).parent / "ProPainter"
        if not propainter_dir.exists():
            logger.error(f"❌ ProPainter 디렉토리가 없습니다: {propainter_dir}")
            return False

        # ProPainter는 sys.path에 추가해야 모듈을 import할 수 있음
        import sys
        if str(propainter_dir) not in sys.path:
            sys.path.insert(0, str(propainter_dir))

        # 임시 디렉토리 생성
        temp_dir = Path(tempfile.mkdtemp())
        mask_path = temp_dir / "mask.png"
        frames_dir = temp_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        try:
            # 1. 마스크 생성 (워터마크 영역을 흰색으로)
            logger.info(f"🎨 마스크 생성 중...")

            # 비디오에서 첫 프레임 읽어서 해상도 확인
            cap = cv2.VideoCapture(str(input_video))
            ret, first_frame = cap.read()
            cap.release()

            if not ret:
                logger.error("❌ 비디오 첫 프레임 읽기 실패")
                return False

            height_vid, width_vid = first_frame.shape[:2]

            # 마스크 이미지 생성 (전체 검은색, 워터마크 영역만 흰색)
            mask = np.zeros((height_vid, width_vid), dtype=np.uint8)
            mask[y:y+h, x:x+w] = 255
            cv2.imwrite(str(mask_path), mask)

            logger.info(f"✅ 마스크 생성 완료: {mask_path}")

            # 2. ProPainter 실행
            logger.info(f"🚀 ProPainter 실행 중... (시간이 걸릴 수 있습니다)")

            # ProPainter inference 스크립트 실행
            inference_script = propainter_dir / "inference_propainter.py"
            output_dir = temp_dir / "propainter_output"

            cmd = [
                sys.executable,
                str(inference_script),
                '--video', str(input_video),
                '--mask', str(mask_path),
                '--output', str(output_dir),
                '--fp16',  # 메모리 절약을 위해 fp16 사용
                '--width', str(width_vid),
                '--height', str(height_vid)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10분 타임아웃
                cwd=str(propainter_dir)
            )

            if result.returncode != 0:
                logger.error(f"❌ ProPainter 실행 실패: {result.stderr}")
                return False

            # 3. 결과 파일 찾기 및 복사
            # ProPainter는 결과를 output_dir에 저장
            result_files = list(output_dir.glob('*.mp4'))
            if not result_files:
                logger.error("❌ ProPainter 결과 파일을 찾을 수 없습니다")
                return False

            # 결과 파일 복사
            shutil.copy(result_files[0], output_video)
            logger.info(f"✅ ProPainter 워터마크 제거 완료")

            return True

        finally:
            # 임시 파일 정리
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"❌ ProPainter 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def remove_watermark_ai(input_video: Path, output_video: Path, watermark_region: tuple = None, quality_mode: str = 'lama-vsr', output_dir: Path = None) -> bool:
    """
    AI 기반 워터마크 제거

    Args:
        input_video: 입력 비디오 경로
        output_video: 출력 비디오 경로
        watermark_region: (x, y, w, h) 워터마크 영역, None이면 자동 감지 (하단 중국어 자막)
        quality_mode:
            - 'sttn' (기본값, 속도와 품질 균형, 빠름)
            - 'e2fgvi' (E2FGVI, 모델 필요)
            - 'fast' (OpenCV Telea, 가장 빠름)
            - 'high' (ProPainter, 가장 느림)
        output_dir: 작업 디렉토리 (STOP 파일 체크용)

    Returns:
        성공 여부
    """
    try:
        # STOP 체크
        if output_dir and should_stop(output_dir):
            raise CancelledException("워터마크 제거 시작 전 작업 취소됨")

        ffmpeg = get_ffmpeg_path()

        # 비디오 해상도 확인
        width, height = get_video_dimensions(input_video)
        logger.info(f"📐 비디오 해상도: {width}x{height}")

        # 워터마크 영역 결정
        if watermark_region is None:
            # 중국어 자막은 보통 화면 하단에 고정 위치
            subtitle_height = 150
            x = 0
            y = height - subtitle_height
            w = width
            h = subtitle_height
            logger.info(f"🤖 중국어 자막 영역 자동 감지")
            logger.info(f"   영역: x={x}, y={y}, w={w}, h={h} (하단 {subtitle_height}px)")
        else:
            x, y, w, h = watermark_region
            logger.info(f"🤖 워터마크 제거 중 (지정 영역: x={x}, y={y}, w={w}, h={h})")

        # 품질 모드에 따른 처리 방법 결정
        if quality_mode == 'lama-vsr':
            # video-subtitle-remover의 LAMA 사용 (가장 효과적인 자막 제거)
            logger.info(f"   방법: LAMA-VSR (AI 자막 제거 전용)")
            return _remove_subtitle_vsr(input_video, output_video, x, y, w, h, output_dir)

        elif quality_mode == 'lama':
            # LAMA (Big-LaMa) AI 인페인팅 (균형잡힌 속도와 품질)
            logger.info(f"   방법: LAMA (AI 인페인팅, 균형잡힌 성능)")
            return _remove_watermark_lama(input_video, output_video, x, y, w, h, output_dir)

        elif quality_mode == 'black':
            # 검은색으로 가리기 (가장 빠름, 1-2초)
            logger.info(f"   방법: 검은색 박스로 가리기 (초고속)")

            cmd = [
                ffmpeg, '-i', str(input_video),
                '-vf', f'drawbox=x={x}:y={y}:w={w}:h={h}:color=black:t=fill',
                '-c:a', 'copy',
                '-y',
                str(output_video)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logger.info(f"✅ 검은색 박스 처리 완료")
                return True
            else:
                logger.error(f"❌ FFmpeg 처리 실패: {result.stderr}")
                return False

        elif quality_mode == 'sttn':
            logger.info(f"   방법: STTN (Spatial-Temporal Transformer)")
            return _remove_watermark_sttn(input_video, output_video, x, y, w, h, output_dir)
        elif quality_mode == 'e2fgvi':
            logger.info(f"   방법: E2FGVI (Flow-Guided Video Inpainting)")
            return _remove_watermark_e2fgvi(input_video, output_video, x, y, w, h, output_dir)
        elif quality_mode == 'high':
            logger.info(f"   방법: ProPainter (고품질 AI 인페인팅)")
            return _remove_watermark_propainter(input_video, output_video, x, y, w, h, output_dir)
        else:  # fast
            logger.info(f"   방법: OpenCV Inpainting (Telea 알고리즘)")

        # 임시 디렉토리 생성
        temp_dir = Path(tempfile.mkdtemp())
        frames_dir = temp_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        try:
            # 1. 비디오에서 프레임 추출
            logger.info(f"🎞️ 비디오 프레임 추출 및 워터마크 제거 중...")
            cmd = [
                ffmpeg,
                '-i', str(input_video),
                '-qscale:v', '2',  # 고품질 유지
                str(frames_dir / 'frame_%05d.png')
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise Exception(f"프레임 추출 실패: {result.stderr}")

            # 2. 각 프레임에 인페인팅 적용
            frame_files = sorted(frames_dir.glob('frame_*.png'))
            total_frames = len(frame_files)

            # 마스크 생성 (워터마크 영역을 흰색으로)
            mask = np.zeros((height, width), dtype=np.uint8)
            mask[y:y+h, x:x+w] = 255

            for idx, frame_file in enumerate(frame_files):
                # STOP 체크 (10프레임마다)
                if idx % 10 == 0 and output_dir and should_stop(output_dir):
                    raise CancelledException(f"OpenCV 인페인팅 중 작업 취소됨 ({idx+1}/{total_frames} 프레임)")

                # 프레임 읽기
                frame = cv2.imread(str(frame_file))

                # 인페인팅 적용 (Telea 알고리즘, radius=3)
                inpainted = cv2.inpaint(frame, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

                # 결과 저장 (원본 파일 덮어쓰기)
                cv2.imwrite(str(frame_file), inpainted)

                # 진행률 출력 (30프레임마다)
                if (idx + 1) % 30 == 0 or (idx + 1) == total_frames:
                    progress = (idx + 1) / total_frames * 100
                    logger.info(f"   처리 중: {idx+1}/{total_frames} 프레임 ({progress:.1f}%)")

            logger.info(f"✅ 프레임 처리 완료: {total_frames}개 프레임")

            # 3. 프레임을 비디오로 재조립
            logger.info(f"🎬 비디오 재조립 중...")
            cmd = [
                ffmpeg,
                '-framerate', '30',  # 원본 프레임레이트
                '-i', str(frames_dir / 'frame_%05d.png'),
                '-i', str(input_video),  # 원본 비디오 (오디오용)
                '-map', '0:v',  # 새 비디오 스트림
                '-map', '1:a',  # 원본 오디오 스트림
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'copy',
                '-pix_fmt', 'yuv420p',
                '-y',
                str(output_video)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise Exception(f"비디오 재조립 실패: {result.stderr}")

            logger.info(f"✅ OpenCV Inpainting 워터마크 제거 완료")
            return True

        finally:
            # 임시 파일 정리
            shutil.rmtree(temp_dir, ignore_errors=True)

    except Exception as e:
        logger.error(f"❌ 워터마크 제거 오류: {e}")
        import traceback
        traceback.print_exc()
        # 오류 시 원본 복사
        try:
            shutil.copy(input_video, output_video)
        except:
            pass
        return True


def extract_audio(video_path: Path, output_audio: Path) -> bool:
    """비디오에서 오디오 추출"""
    try:
        ffmpeg = get_ffmpeg_path()
        logger.info(f"🎵 오디오 추출 중: {video_path.name}")

        cmd = [
            ffmpeg,
            '-i', str(video_path),
            '-vn',  # 비디오 스트림 제외
            '-acodec', 'pcm_s16le',  # WAV 포맷
            '-ar', '16000',  # 샘플링 레이트
            '-ac', '1',  # 모노
            '-y',  # 덮어쓰기
            str(output_audio)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"❌ 오디오 추출 실패: {result.stderr}")
            return False

        logger.info(f"✅ 오디오 추출 완료: {output_audio.name}")
        return True

    except Exception as e:
        logger.error(f"❌ 오디오 추출 오류: {e}")
        return False


def transcribe_audio_whisper(audio_path: Path, language: str = 'zh') -> Optional[List[Dict]]:
    """Whisper를 사용하여 오디오 전사 (타임스탬프 포함)"""
    try:
        import whisper
        logger.info(f"🎤 Whisper로 음성 인식 중 (언어: {language})...")

        # 모델 로드 (medium 추천, 정확도와 속도 균형)
        model = whisper.load_model("medium")

        # 전사
        result = model.transcribe(
            str(audio_path),
            language=language,
            task='transcribe',
            verbose=False
        )

        segments = []
        for segment in result['segments']:
            segments.append({
                'start': segment['start'],
                'end': segment['end'],
                'text': segment['text'].strip()
            })

        logger.info(f"✅ 음성 인식 완료: {len(segments)}개 세그먼트")
        return segments

    except ImportError:
        logger.error("❌ whisper 모듈이 설치되지 않았습니다. pip install openai-whisper")
        return None
    except Exception as e:
        logger.error(f"❌ 음성 인식 실패: {e}")
        return None


def transcribe_audio_openai(audio_path: Path) -> Optional[List[Dict]]:
    """OpenAI Whisper API를 사용하여 오디오 전사"""
    if not OPENAI_AVAILABLE:
        logger.error("❌ OpenAI 모듈이 없습니다.")
        return None

    try:
        client = OpenAI()
        logger.info(f"🎤 OpenAI Whisper API로 음성 인식 중...")

        with open(audio_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )

        segments = []
        if hasattr(transcript, 'segments'):
            for segment in transcript.segments:
                segments.append({
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip()
                })
        else:
            # 타임스탬프 없는 경우
            segments.append({
                'start': 0,
                'end': 0,
                'text': transcript.text
            })

        logger.info(f"✅ 음성 인식 완료: {len(segments)}개 세그먼트")
        return segments

    except Exception as e:
        logger.error(f"❌ OpenAI 음성 인식 실패: {e}")
        return None


def translate_segments_claude(segments: List[Dict], source_lang: str = 'zh', target_lang: str = 'ko') -> List[Dict]:
    """Claude API로 세그먼트 일괄 번역 (빠르고 저렴)"""
    if not ANTHROPIC_AVAILABLE:
        logger.error("❌ Anthropic 모듈이 없습니다.")
        return segments

    try:
        client = Anthropic()
        logger.info(f"🌐 Claude로 번역 중: {source_lang} → {target_lang} ({len(segments)}개 세그먼트)")

        # 전체 텍스트를 JSON 형태로 한 번에 보내기
        texts_to_translate = []
        for i, segment in enumerate(segments):
            texts_to_translate.append({
                'id': i,
                'text': segment['text']
            })

        # JSON 문자열로 변환
        import json
        batch_input = json.dumps(texts_to_translate, ensure_ascii=False, indent=2)

        # Claude API 호출 (한 번에 전체 번역)
        message = client.messages.create(
            model="claude-3-5-haiku-20241022",  # 가장 저렴하고 빠른 모델
            max_tokens=8000,
            temperature=0.3,
            messages=[
                {
                    "role": "user",
                    "content": f"""다음 JSON 배열의 모든 텍스트를 {source_lang}에서 {target_lang}로 번역해주세요.
같은 형식의 JSON으로 응답하되, text 필드만 번역된 내용으로 바꿔주세요.
자연스럽고 정확하게 번역하세요.

입력:
{batch_input}

출력 형식 예시:
[
  {{"id": 0, "text": "번역된 텍스트"}},
  {{"id": 1, "text": "번역된 텍스트"}},
  ...
]

JSON만 출력하고 다른 설명은 붙이지 마세요."""
                }
            ]
        )

        # 응답 파싱
        response_text = message.content[0].text.strip()

        # JSON 부분만 추출 (```json ... ``` 등 제거)
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        translated_data = json.loads(response_text)

        # 번역된 텍스트를 세그먼트에 매핑
        translated_segments = []
        for segment in segments:
            segment_id = segments.index(segment)
            translated_item = next((item for item in translated_data if item['id'] == segment_id), None)

            if translated_item:
                translated_text = translated_item['text']
            else:
                translated_text = segment['text']  # 실패 시 원문 유지

            translated_segments.append({
                'start': segment['start'],
                'end': segment['end'],
                'original': segment['text'],
                'translated': translated_text
            })

        logger.info(f"✅ 번역 완료: {len(translated_segments)}개 세그먼트")

        # 샘플 출력
        for i in range(min(3, len(translated_segments))):
            logger.info(f"  [{i+1}] {translated_segments[i]['original'][:40]}...")
            logger.info(f"      → {translated_segments[i]['translated'][:40]}...")

        return translated_segments

    except Exception as e:
        logger.error(f"❌ Claude 번역 실패: {e}")
        import traceback
        traceback.print_exc()
        return segments


def translate_segments_openai(segments: List[Dict], source_lang: str = 'zh', target_lang: str = 'ko') -> List[Dict]:
    """OpenAI API로 세그먼트 일괄 번역 (대체 옵션)"""
    if not OPENAI_AVAILABLE:
        logger.error("❌ OpenAI 모듈이 없습니다.")
        return segments

    try:
        client = OpenAI()
        logger.info(f"🌐 OpenAI로 번역 중: {source_lang} → {target_lang} ({len(segments)}개 세그먼트)")

        # 전체 텍스트를 한 번에 보내기
        import json
        texts_to_translate = []
        for i, segment in enumerate(segments):
            texts_to_translate.append({
                'id': i,
                'text': segment['text']
            })

        batch_input = json.dumps(texts_to_translate, ensure_ascii=False, indent=2)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"당신은 {source_lang}에서 {target_lang}로 번역하는 전문 번역가입니다."
                },
                {
                    "role": "user",
                    "content": f"""다음 JSON 배열의 모든 텍스트를 번역하고 같은 형식으로 응답하세요:
{batch_input}"""
                }
            ],
            temperature=0.3
        )

        response_text = response.choices[0].message.content.strip()

        # JSON 추출
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        translated_data = json.loads(response_text)

        translated_segments = []
        for segment in segments:
            segment_id = segments.index(segment)
            translated_item = next((item for item in translated_data if item['id'] == segment_id), None)

            translated_segments.append({
                'start': segment['start'],
                'end': segment['end'],
                'original': segment['text'],
                'translated': translated_item['text'] if translated_item else segment['text']
            })

        logger.info(f"✅ 번역 완료: {len(translated_segments)}개")
        return translated_segments

    except Exception as e:
        logger.error(f"❌ OpenAI 번역 실패: {e}")
        return segments


async def generate_tts_edge(text: str, output_path: Path, voice: str = 'ko-KR-SunHiNeural') -> bool:
    """Edge TTS로 음성 생성

    추천 한국어 음성:
    - ko-KR-SunHiNeural: 밝고 경쾌한 여성 음성 (기본)
    - ko-KR-JiMinNeural: 부드러운 여성 음성
    """
    if not EDGE_TTS_AVAILABLE:
        logger.error("❌ edge-tts 모듈이 없습니다.")
        return False

    try:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(output_path))
        return True
    except Exception as e:
        logger.error(f"❌ Edge TTS 생성 실패: {e}")
        return False


def generate_tts_openai(text: str, output_path: Path, voice: str = 'shimmer') -> bool:
    """OpenAI TTS로 음성 생성

    음성 옵션:
    - shimmer: 밝고 경쾌한 여성 음성 (추천)
    - nova: 활기찬 여성 음성
    - alloy: 중성적이고 부드러운 음성
    """
    if not OPENAI_AVAILABLE:
        logger.error("❌ OpenAI 모듈이 없습니다.")
        return False

    try:
        client = OpenAI()

        response = client.audio.speech.create(
            model="tts-1-hd",  # HD 품질 사용
            voice=voice,
            input=text,
            speed=1.0  # 속도 (0.25 ~ 4.0)
        )

        response.stream_to_file(str(output_path))
        return True

    except Exception as e:
        logger.error(f"❌ OpenAI TTS 생성 실패: {e}")
        return False


async def generate_audio_for_segments(segments: List[Dict], output_dir: Path, use_openai: bool = False) -> List[Dict]:
    """각 세그먼트에 대한 오디오 파일 생성 (실제 오디오 길이 반환)"""
    logger.info(f"🎤 TTS 생성 중: {len(segments)}개 세그먼트")

    audio_segments = []

    for i, segment in enumerate(segments, 1):
        audio_path = output_dir / f"segment_{i:03d}.mp3"
        text = segment.get('translated', segment.get('text', ''))

        if not text:
            logger.warning(f"⚠️ 세그먼트 {i}: 텍스트 없음")
            continue

        logger.info(f"  [{i}/{len(segments)}] TTS 생성: {text[:50]}...")

        success = False
        if EDGE_TTS_AVAILABLE:
            success = await generate_tts_edge(text, audio_path)
        elif use_openai and OPENAI_AVAILABLE:
            logger.warning(f"⚠️ Edge TTS 사용 불가, OpenAI TTS 사용 (유료)")
            success = generate_tts_openai(text, audio_path)

        if success and audio_path.exists():
            # 실제 오디오 길이 측정
            try:
                import subprocess
                ffmpeg = get_ffmpeg_path()
                result = subprocess.run(
                    [ffmpeg, '-i', str(audio_path)],
                    capture_output=True,
                    text=True
                )
                # FFmpeg stderr에서 Duration 추출
                duration_match = None
                for line in result.stderr.split('\n'):
                    if 'Duration:' in line:
                        import re
                        duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                        if duration_match:
                            h, m, s = duration_match.groups()
                            actual_duration = int(h) * 3600 + int(m) * 60 + float(s)
                            break

                if duration_match:
                    audio_segments.append({
                        'path': audio_path,
                        'text': text,
                        'original_start': segment['start'],
                        'original_end': segment['end'],
                        'actual_duration': actual_duration
                    })
                else:
                    # Duration을 못 찾으면 원본 길이 사용
                    audio_segments.append({
                        'path': audio_path,
                        'text': text,
                        'original_start': segment['start'],
                        'original_end': segment['end'],
                        'actual_duration': segment['end'] - segment['start']
                    })
            except Exception as e:
                logger.warning(f"⚠️ 오디오 길이 측정 실패 (원본 길이 사용): {e}")
                audio_segments.append({
                    'path': audio_path,
                    'text': text,
                    'original_start': segment['start'],
                    'original_end': segment['end'],
                    'actual_duration': segment['end'] - segment['start']
                })
        else:
            logger.error(f"❌ 세그먼트 {i} TTS 생성 실패")

    logger.info(f"✅ TTS 생성 완료: {len(audio_segments)}개 파일")
    return audio_segments


def merge_audio_segments(audio_segments: List[Dict], output_audio: Path) -> bool:
    """세그먼트 오디오를 순서대로 연결"""
    try:
        ffmpeg = get_ffmpeg_path()
        logger.info(f"🔊 오디오 세그먼트 병합 중...")

        if len(audio_segments) == 0:
            logger.error("❌ 병합할 오디오 파일이 없습니다.")
            return False

        # 파일 리스트 생성
        list_file = output_audio.parent / "audio_list.txt"
        with open(list_file, 'w', encoding='utf-8') as f:
            for seg in audio_segments:
                f.write(f"file '{seg['path'].absolute()}'\n")

        cmd = [
            ffmpeg,
            '-f', 'concat',
            '-safe', '0',
            '-i', str(list_file),
            '-c', 'copy',
            '-y',
            str(output_audio)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"❌ 오디오 병합 실패: {result.stderr}")
            return False

        logger.info(f"✅ 오디오 병합 완료: {output_audio.name}")

        # 정리
        list_file.unlink()

        return True

    except Exception as e:
        logger.error(f"❌ 오디오 병합 오류: {e}")
        return False


def create_simple_srt(full_text: str, audio_path: Path, output_srt: Path) -> bool:
    """전체 텍스트를 25자 단위로 분할하여 SRT 자막 생성"""
    try:
        logger.info(f"📝 SRT 자막 파일 생성 중: {output_srt.name}")

        # 오디오 길이 측정
        ffmpeg = get_ffmpeg_path()
        result = subprocess.run(
            [ffmpeg, '-i', str(audio_path)],
            capture_output=True,
            text=True
        )

        audio_duration = 0
        for line in result.stderr.split('\n'):
            if 'Duration:' in line:
                import re
                match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                if match:
                    h, m, s = match.groups()
                    audio_duration = int(h) * 3600 + int(m) * 60 + float(s)
                    break

        if audio_duration == 0:
            logger.error("❌ 오디오 길이를 측정할 수 없습니다")
            return False

        logger.info(f"⏱️ 오디오 길이: {audio_duration:.2f}초")

        # 텍스트를 25자 단위로 분할
        words = full_text.split()
        chunks = []
        current_chunk = ""

        for word in words:
            test_chunk = current_chunk + (" " if current_chunk else "") + word
            if len(test_chunk) <= 25:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = word

        if current_chunk:
            chunks.append(current_chunk)

        if not chunks:
            chunks = [full_text]

        # 자막 타이밍 계산 (오디오 길이를 청크 수로 나눔)
        time_per_chunk = audio_duration / len(chunks)

        with open(output_srt, 'w', encoding='utf-8') as f:
            for i, chunk in enumerate(chunks, 1):
                start_time = (i - 1) * time_per_chunk
                end_time = i * time_per_chunk

                start_srt = format_srt_time(start_time)
                end_srt = format_srt_time(end_time)

                f.write(f"{i}\n")
                f.write(f"{start_srt} --> {end_srt}\n")
                f.write(f"{chunk}\n")
                f.write("\n")

        logger.info(f"✅ SRT 자막 생성 완료: {len(chunks)}개 자막")
        return True

    except Exception as e:
        logger.error(f"❌ SRT 생성 실패: {e}")
        return False


def create_srt_subtitle(audio_segments: List[Dict], output_srt: Path) -> bool:
    """오디오 세그먼트의 실제 길이를 기반으로 SRT 자막 파일 생성"""
    try:
        logger.info(f"📝 SRT 자막 파일 생성 중 (실제 TTS 길이 기준): {output_srt.name}")

        with open(output_srt, 'w', encoding='utf-8') as f:
            current_time = 0.0

            for i, segment in enumerate(audio_segments, 1):
                text = segment['text']
                actual_duration = segment['actual_duration']

                if not text:
                    continue

                # 긴 텍스트 줄바꿈 처리 (25자 이상이면 줄바꿈)
                if len(text) > 25:
                    # 공백 기준으로 단어 분리
                    words = text.split()
                    lines = []
                    current_line = ""

                    for word in words:
                        test_line = current_line + (" " if current_line else "") + word
                        if len(test_line) <= 25:
                            current_line = test_line
                        else:
                            if current_line:
                                lines.append(current_line)
                            current_line = word

                    if current_line:
                        lines.append(current_line)

                    # 최대 2줄로 제한
                    if len(lines) > 2:
                        text = "\n".join(lines[:2])
                    else:
                        text = "\n".join(lines)

                # 실제 TTS 길이 기반으로 타임스탬프 생성
                start_time = current_time
                end_time = current_time + actual_duration

                # SRT 시간 형식 변환 (HH:MM:SS,mmm)
                start_srt = format_srt_time(start_time)
                end_srt = format_srt_time(end_time)

                # SRT 형식
                f.write(f"{i}\n")
                f.write(f"{start_srt} --> {end_srt}\n")
                f.write(f"{text}\n")
                f.write("\n")

                current_time = end_time

        logger.info(f"✅ SRT 자막 생성 완료: {len(audio_segments)}개 자막")
        return True

    except Exception as e:
        logger.error(f"❌ SRT 생성 실패: {e}")
        return False


def format_srt_time(seconds: float) -> str:
    """초를 SRT 시간 형식으로 변환 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def replace_video_audio_with_subtitle(
    video_path: Path,
    audio_path: Path,
    subtitle_path: Path,
    output_video: Path,
    burn_subtitle: bool = True
) -> bool:
    """비디오의 오디오를 교체하고 자막 추가

    주의: 원본 영상에 하드코딩된 중국어 자막은 제거할 수 없습니다.
    하드코딩된 자막은 영상 픽셀에 포함되어 있어 완전히 제거하려면
    OCR + 인페인팅 또는 영상 크롭이 필요합니다.

    현재는 한국어 자막을 더 크고 선명하게 추가하여 중국어 자막을 가리도록 합니다.
    """
    try:
        ffmpeg = get_ffmpeg_path()
        logger.info(f"🎞️ 영상 합성 중...")

        if burn_subtitle:
            # 자막을 비디오에 하드코딩 (burned-in)
            # Windows 경로 이스케이프 처리
            subtitle_path_escaped = str(subtitle_path).replace('\\', '/').replace(':', '\\:')

            # 자막 스타일 (적당한 크기, 하단에서 20px 위)
            subtitle_style = (
                "FontName=NanumGothic,"       # 나눔고딕
                "Fontsize=21,"                # 폰트 크기 (23 * 0.9 = 20.7 ≈ 21)
                "Bold=1,"                     # 볼드
                "PrimaryColour=&H00FFFFFF,"   # 흰색
                "OutlineColour=&H00000000,"   # 검은 테두리
                "BorderStyle=1,"              # 외곽선 스타일
                "Outline=2,"                  # 테두리
                "Shadow=1,"                   # 그림자
                "MarginV=20,"                 # 하단에서 20px 위
                "Alignment=2"                 # 하단 중앙
            )

            # 중국어 자막 위에 완전 불투명 검은 레이어 (화면 하단 150px)
            # 하단 150px를 완전히 검은색으로 덮음
            video_filter = (
                f"drawbox=x=0:y=ih-150:w=iw:h=150:color=black:t=fill,"  # 하단 150px 완전 불투명 검은 박스
                f"subtitles='{subtitle_path_escaped}':force_style='{subtitle_style}'"  # 한국어 자막
            )

            # 오디오 길이 측정
            result = subprocess.run(
                [ffmpeg, '-i', str(audio_path)],
                capture_output=True,
                text=True
            )
            audio_duration = 0
            for line in result.stderr.split('\n'):
                if 'Duration:' in line:
                    import re
                    match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', line)
                    if match:
                        h, m, s = match.groups()
                        audio_duration = int(h) * 3600 + int(m) * 60 + float(s)
                        break

            logger.info(f"🎵 오디오 길이: {audio_duration:.2f}초")

            # 영상을 오디오 길이에 맞추기 (loop 사용)
            cmd = [
                ffmpeg,
                '-stream_loop', '-1',  # 비디오 무한 반복
                '-i', str(video_path),
                '-i', str(audio_path),
                '-c:v', 'libx264',     # 비디오 재인코딩
                '-preset', 'medium',   # 인코딩 속도/품질 균형
                '-crf', '23',          # 품질 설정 (낮을수록 고품질)
                '-c:a', 'aac',         # 오디오 AAC 인코딩
                '-b:a', '192k',        # 오디오 비트레이트
                '-vf', video_filter,   # 비디오 필터 (중국어 자막 제거 + 한국어 자막 추가)
                '-map', '0:v:0',       # 첫 번째 입력의 비디오
                '-map', '1:a:0',       # 두 번째 입력의 오디오
                '-sn',                 # 원본 자막 스트림 제거 (소프트 자막만)
                '-shortest',           # 오디오 길이에 맞춤 (오디오가 끝나면 영상도 끝)
                '-y',
                str(output_video)
            ]
        else:
            # 소프트 자막 (별도 스트림으로 추가)
            cmd = [
                ffmpeg,
                '-i', str(video_path),
                '-i', str(audio_path),
                '-i', str(subtitle_path),
                '-c:v', 'copy',        # 비디오 스트림 복사
                '-c:a', 'aac',         # 오디오 AAC 인코딩
                '-c:s', 'mov_text',    # 자막 인코딩
                '-map', '0:v:0',       # 첫 번째 입력의 비디오
                '-map', '1:a:0',       # 두 번째 입력의 오디오
                '-map', '2:s:0',       # 세 번째 입력의 자막
                '-metadata:s:s:0', 'language=kor',
                '-shortest',
                '-y',
                str(output_video)
            ]

        logger.info(f"📹 FFmpeg 명령 실행 중...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"❌ 영상 합성 실패: {result.stderr}")
            return False

        logger.info(f"✅ 영상 합성 완료: {output_video.name}")
        return True

    except Exception as e:
        logger.error(f"❌ 영상 합성 오류: {e}")
        return False


async def convert_chinese_video(
    input_video: Path,
    output_dir: Path,
    title: str = None,
    use_openai_whisper: bool = False,
    use_openai_tts: bool = False,  # Edge TTS 사용 (무료)
    use_claude: bool = True
) -> Optional[Path]:
    """중국어 영상을 한국어로 변환하는 메인 함수"""

    logger.info("=" * 60)
    logger.info("🇨🇳 → 🇰🇷 중국어 영상 변환 시작")
    logger.info("=" * 60)
    logger.info(f"입력: {input_video.name}")
    logger.info(f"출력 폴더: {output_dir}")
    logger.info(f"📍 STOP 파일 경로: {output_dir / 'STOP'}")

    # 출력 디렉토리 생성
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = output_dir / "temp"
    temp_dir.mkdir(exist_ok=True)

    try:
        # 1. 중국어 자막 워터마크 제거
        logger.info("\n" + "=" * 60)
        logger.info("1️⃣ 단계 1: 중국어 자막 워터마크 제거")
        logger.info("=" * 60)

        # 취소 체크
        if should_stop(output_dir):
            raise CancelledException("워터마크 제거 전 작업 취소됨")

        # 워터마크 제거된 비디오 경로
        watermark_removed_video = temp_dir / "no_watermark.mp4"
        if not remove_watermark_ai(input_video, watermark_removed_video, output_dir=output_dir):
            logger.error("❌ 워터마크 제거 실패 (원본 사용)")
            watermark_removed_video = input_video

        # 이후 단계에서는 워터마크 제거된 비디오 사용
        working_video = watermark_removed_video

        # 취소 체크
        if should_stop(output_dir):
            raise CancelledException("워터마크 제거 후 작업 취소됨")

        # 2. 오디오 추출
        logger.info("\n" + "=" * 60)
        logger.info("2️⃣ 단계 2: 오디오 추출")
        logger.info("=" * 60)

        audio_path = temp_dir / "original_audio.wav"
        if not extract_audio(working_video, audio_path):
            logger.error("❌ 오디오 추출 실패")
            return None

        # 취소 체크
        if should_stop(output_dir):
            raise CancelledException("오디오 추출 후 작업 취소됨")

        # 3. 음성 인식 (중국어)
        logger.info("\n" + "=" * 60)
        logger.info("3️⃣ 단계 3: 중국어 음성 인식")
        logger.info("=" * 60)

        if use_openai_whisper:
            segments = transcribe_audio_openai(audio_path)
        else:
            segments = transcribe_audio_whisper(audio_path, language='zh')

        if not segments:
            logger.error("❌ 음성 인식 실패")
            return None

        # 자막 저장
        transcript_file = output_dir / "chinese_transcript.json"
        with open(transcript_file, 'w', encoding='utf-8') as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 중국어 자막 저장: {transcript_file.name}")

        # 취소 체크
        if should_stop(output_dir):
            raise CancelledException("음성 인식 후 작업 취소됨")

        # 4. 번역 (중국어 → 한국어)
        logger.info("\n" + "=" * 60)
        logger.info("4️⃣ 단계 4: 번역 (중국어 → 한국어)")
        logger.info("=" * 60)

        if use_claude and ANTHROPIC_AVAILABLE:
            translated_segments = translate_segments_claude(segments, source_lang='zh', target_lang='ko')
        elif OPENAI_AVAILABLE:
            translated_segments = translate_segments_openai(segments, source_lang='zh', target_lang='ko')
        else:
            logger.error("❌ 번역 API가 없습니다 (Claude 또는 OpenAI 필요)")
            return None

        # 번역 저장
        translation_file = output_dir / "korean_translation.json"
        with open(translation_file, 'w', encoding='utf-8') as f:
            json.dump(translated_segments, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 한국어 번역 저장: {translation_file.name}")

        # 취소 체크
        if should_stop(output_dir):
            raise CancelledException("번역 후 작업 취소됨")

        # 5. 전체 텍스트를 하나의 TTS로 생성
        logger.info("\n" + "=" * 60)
        logger.info("5️⃣ 단계 5: 한국어 음성 생성 (전체)")
        logger.info("=" * 60)

        # 번역된 텍스트 전체 합치기 (각 세그먼트 사이에 24개 줄바꿈 추가)
        newline_separator = '\n' * 24
        full_korean_text = newline_separator.join([seg.get('translated', '') for seg in translated_segments])
        logger.info(f"📝 한국어 텍스트 길이: {len(full_korean_text)}자")
        logger.info(f"📝 미리보기: {full_korean_text[:100]}...")
        logger.info(f"🫁 숨쉬는 포인트 추가 완료 (세그먼트 사이마다 24개 줄바꿈)")

        # 하나의 TTS 파일로 생성
        korean_audio_path = temp_dir / "korean_audio.mp3"

        if EDGE_TTS_AVAILABLE:
            logger.info("🎤 Edge TTS로 음성 생성 중...")
            success = await generate_tts_edge(full_korean_text, korean_audio_path)
        elif use_openai_tts and OPENAI_AVAILABLE:
            logger.warning("⚠️ Edge TTS 사용 불가, OpenAI TTS 사용 (유료)")
            success = generate_tts_openai(full_korean_text, korean_audio_path)
        else:
            logger.error("❌ TTS 모듈이 없습니다")
            return None

        if not success or not korean_audio_path.exists():
            logger.error("❌ TTS 생성 실패")
            return None

        logger.info(f"✅ TTS 생성 완료: {korean_audio_path.name}")

        # 취소 체크
        if should_stop(output_dir):
            raise CancelledException("TTS 생성 후 작업 취소됨")

        # 6. 간단한 자막 생성 (전체 텍스트를 25자 단위로 분할)
        logger.info("\n" + "=" * 60)
        logger.info("6️⃣ 단계 6: 한국어 자막 생성")
        logger.info("=" * 60)

        subtitle_path = output_dir / "korean_subtitle.srt"
        if not create_simple_srt(full_korean_text, korean_audio_path, subtitle_path):
            logger.error("❌ 자막 생성 실패")
            return None

        # 7. 영상 합성 (한국어 자막 + 오디오)
        logger.info("\n" + "=" * 60)
        logger.info("7️⃣ 단계 7: 영상 합성")
        logger.info("=" * 60)

        # 출력 파일명 결정 (제목이 있으면 제목 사용)
        if title:
            # 안전한 파일명으로 변환 (특수문자 제거)
            import re
            safe_title = re.sub(r'[<>:"/\\|?*]', '', title)
            safe_title = safe_title.strip()[:100]  # 최대 100자
            output_filename = f"{safe_title}.mp4"
            logger.info(f"📝 제목 사용: {title} → {output_filename}")
        else:
            output_filename = f"converted_{input_video.stem}.mp4"

        # 워터마크 제거된 비디오 사용
        output_video = output_dir / output_filename
        if not replace_video_audio_with_subtitle(
            working_video,  # 워터마크 제거된 비디오 사용
            korean_audio_path,
            subtitle_path,
            output_video,
            burn_subtitle=True  # 자막을 비디오에 하드코딩
        ):
            logger.error("❌ 영상 합성 실패")
            return None

        # 임시 파일 정리
        logger.info("\n🧹 임시 파일 정리 중...")
        shutil.rmtree(temp_dir, ignore_errors=True)

        logger.info("\n" + "=" * 60)
        logger.info("✅ 변환 완료!")
        logger.info("=" * 60)
        logger.info(f"출력 파일: {output_video}")

        return output_video

    except CancelledException as e:
        logger.warning(f"\n🛑 작업이 취소되었습니다: {e}")
        # 임시 파일 정리
        if 'temp_dir' in locals():
            shutil.rmtree(temp_dir, ignore_errors=True)
        return None

    except Exception as e:
        logger.error(f"\n❌ 변환 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description='중국어 영상을 한국어로 변환')
    parser.add_argument('--input', type=str, required=True, help='입력 비디오 파일 경로')
    parser.add_argument('--output-dir', type=str, required=True, help='출력 디렉토리')
    parser.add_argument('--title', type=str, help='상품 제목 (파일명으로 사용)')
    parser.add_argument('--use-openai-whisper', action='store_true', help='OpenAI Whisper API 사용 (기본: 로컬 whisper)')
    parser.add_argument('--use-edge-tts', action='store_true', help='Edge TTS 사용 (기본: OpenAI TTS)')
    parser.add_argument('--use-openai-translate', action='store_true', help='OpenAI로 번역 (기본: Claude)')

    args = parser.parse_args()

    input_video = Path(args.input)
    output_dir = Path(args.output_dir)

    if not input_video.exists():
        logger.error(f"❌ 입력 파일이 존재하지 않습니다: {input_video}")
        return

    # 필요한 패키지 확인
    logger.info("\n📦 필요한 패키지:")
    logger.info("  - openai-whisper (음성 인식)")
    logger.info("  - anthropic (번역 - 저렴)")
    logger.info("  - openai (TTS)")
    logger.info("  - edge-tts (TTS 대체)")
    logger.info("\n설치: pip install openai-whisper anthropic openai edge-tts\n")

    # 비동기 실행
    result = asyncio.run(convert_chinese_video(
        input_video,
        output_dir,
        title=args.title,
        use_openai_whisper=args.use_openai_whisper,
        use_openai_tts=not args.use_edge_tts,
        use_claude=not args.use_openai_translate
    ))

    if result:
        logger.info(f"\n✅ 성공: {result}")
    else:
        logger.error("\n❌ 변환 실패")
        sys.exit(1)


if __name__ == '__main__':
    main()
