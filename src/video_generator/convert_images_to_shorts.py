#!/usr/bin/env python3
"""
롱폼 이미지(16:9 가로)를 쇼츠 형태(9:16 세로)로 변환하는 스크립트

Usage:
    python convert_images_to_shorts.py --folder <folder_path>

설명:
    - 원본 폴더에서 16:9 비율의 이미지를 찾음
    - 중앙 부분을 9:16 비율로 크롭
    - shorts_images 폴더에 저장
"""

import os
import sys
import io
import argparse
from pathlib import Path
from PIL import Image
import logging
import numpy as np
from typing import Optional, Tuple

# Windows 콘솔 한글 깨짐 방지
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# OpenCV 임포트 시도
try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    print("⚠️ OpenCV가 없습니다. 얼굴 감지 없이 중앙 크롭만 수행합니다.")
    print("   설치: pip install opencv-python")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def detect_focus_area(image_path: Path) -> Optional[Tuple[int, int]]:
    """
    이미지에서 인물이나 주요 물체를 감지하여 중심 좌표 반환

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

        # 얼굴 감지 (여러 스케일, 최소 인접)
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


def is_landscape_image(image_path: Path) -> bool:
    """이미지가 가로(16:9 근처) 비율인지 확인"""
    try:
        with Image.open(image_path) as img:
            width, height = img.size
            ratio = width / height
            # 16:9 = 1.778, 허용 오차 ±10%
            target_ratio = 16 / 9
            return abs(ratio - target_ratio) < 0.2
    except Exception as e:
        logger.warning(f"이미지 확인 실패: {image_path} - {e}")
        return False


def convert_to_vertical(input_path: Path, output_path: Path) -> bool:
    """
    가로 이미지를 세로(9:16)로 크롭 변환
    얼굴이 감지되면 얼굴 중심으로 크롭

    Args:
        input_path: 원본 이미지 경로
        output_path: 출력 이미지 경로

    Returns:
        성공 여부
    """
    try:
        # 얼굴/물체 감지
        focus_point = detect_focus_area(input_path)

        with Image.open(input_path) as img:
            width, height = img.size
            logger.info(f"  원본 크기: {width}x{height}")

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
                    # 얼굴 y좌표를 중심으로 크롭 (위아래 여유 공간 확보)
                    center_y = focus_y
                    top = max(0, center_y - new_height // 2)
                    bottom = min(height, top + new_height)

                    # 경계 조정
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

                logger.info(f"  크롭 영역: ({left}, {top}) ~ ({right}, {bottom})")

                # 이미지 크롭
                img = img.crop((left, top, right, bottom))
            else:
                # 높이는 그대로, 너비를 크롭
                new_height = height

                # 얼굴이 감지되면 얼굴 중심으로, 아니면 중앙 크롭
                if focus_point:
                    focus_x, focus_y = focus_point
                    # 얼굴 x좌표를 중심으로 크롭
                    center_x = focus_x
                    left = max(0, center_x - new_width // 2)
                    right = min(width, left + new_width)

                    # 경계 조정
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

                logger.info(f"  크롭 영역: ({left}, {top}) ~ ({right}, {bottom})")

                # 이미지 크롭
                img = img.crop((left, top, right, bottom))

            # 표준 쇼츠 해상도로 리사이즈 (1080x1920)
            target_size = (1080, 1920)
            img = img.resize(target_size, Image.Resampling.LANCZOS)

            logger.info(f"  변환 완료: {target_size[0]}x{target_size[1]} (9:16)")

            # 저장
            img.save(output_path, quality=95)
            return True

    except Exception as e:
        logger.error(f"이미지 변환 실패: {input_path} - {e}")
        return False


def convert_folder_images(folder_path: Path) -> int:
    """
    폴더 내의 가로 이미지를 모두 세로로 변환

    Args:
        folder_path: 원본 폴더 경로

    Returns:
        변환된 이미지 개수
    """
    logger.info(f"📂 폴더 확인: {folder_path}")

    # shorts_images 폴더 생성
    shorts_folder = folder_path / 'shorts_images'
    shorts_folder.mkdir(exist_ok=True)
    logger.info(f"📁 출력 폴더: {shorts_folder}")

    # 이미지 파일 찾기
    image_extensions = {'.jpg', '.jpeg', '.png'}
    image_files = []

    for file in folder_path.iterdir():
        if file.is_file() and file.suffix.lower() in image_extensions:
            # 썸네일은 제외
            if 'thumbnail' not in file.name.lower():
                image_files.append(file)

    logger.info(f"🔍 발견된 이미지: {len(image_files)}개")

    # 가로 이미지 필터링
    landscape_images = []
    for img_file in image_files:
        if is_landscape_image(img_file):
            landscape_images.append(img_file)
            logger.info(f"  ✓ 가로 이미지: {img_file.name}")
        else:
            logger.info(f"  - 건너뜀 (세로 또는 정사각형): {img_file.name}")

    if not landscape_images:
        logger.warning("⚠️ 변환할 가로 이미지가 없습니다.")
        return 0

    logger.info(f"\n🎨 이미지 변환 시작... ({len(landscape_images)}개)")

    # 변환 수행
    converted_count = 0
    for img_file in landscape_images:
        output_file = shorts_folder / img_file.name
        logger.info(f"\n📷 변환 중: {img_file.name}")

        if convert_to_vertical(img_file, output_file):
            converted_count += 1
            logger.info(f"  ✅ 저장: {output_file.name}")
        else:
            logger.error(f"  ❌ 실패: {img_file.name}")

    logger.info(f"\n✅ 변환 완료: {converted_count}/{len(landscape_images)}개")
    return converted_count


def main():
    parser = argparse.ArgumentParser(description='롱폼 이미지를 쇼츠 형태로 변환')
    parser.add_argument('--folder', type=str, required=True, help='원본 폴더 경로')

    args = parser.parse_args()

    folder_path = Path(args.folder)

    if not folder_path.exists():
        logger.error(f"❌ 폴더가 존재하지 않습니다: {folder_path}")
        sys.exit(1)

    if not folder_path.is_dir():
        logger.error(f"❌ 폴더가 아닙니다: {folder_path}")
        sys.exit(1)

    logger.info("=" * 70)
    logger.info("🎬 롱폼 → 쇼츠 이미지 변환")
    logger.info("=" * 70)

    converted_count = convert_folder_images(folder_path)

    logger.info("=" * 70)
    if converted_count > 0:
        logger.info(f"✅ 성공: {converted_count}개 이미지 변환됨")
        logger.info(f"📂 저장 위치: {folder_path / 'shorts_images'}")
    else:
        logger.info("⚠️ 변환된 이미지가 없습니다")
    logger.info("=" * 70)

    sys.exit(0)


if __name__ == '__main__':
    main()
