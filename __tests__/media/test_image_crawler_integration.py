#!/usr/bin/env python3
"""
Image Crawler Integration Test
이미지 크롤러 (ImageFX + Whisk) 통합 테스트

테스트 항목:
1. JSON 파일 파싱 및 씬 추출
2. image_prompt 필드 사용 여부
3. 출력 폴더 자동 생성
4. 씬 개수와 이미지 개수 일치 검증
"""

import os
import sys
import json
import unittest
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestImageCrawlerIntegration(unittest.TestCase):
    """이미지 크롤러 통합 테스트"""

    @classmethod
    def setUpClass(cls):
        """테스트 클래스 설정"""
        cls.test_data_dir = Path(__file__).parent / "test_data"
        cls.test_output_dir = Path(__file__).parent / "output_test"
        cls.test_json_file = cls.test_data_dir / "test_shortform_5scenes.json"

    def test_01_test_json_file_exists(self):
        """테스트 JSON 파일이 존재하는지 확인"""
        self.assertTrue(
            self.test_json_file.exists(),
            f"테스트 JSON 파일이 없습니다: {self.test_json_file}"
        )

    def test_02_json_file_has_valid_scenes(self):
        """JSON 파일에 유효한 씬 데이터가 있는지 확인"""
        with open(self.test_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('scenes', data, "JSON에 'scenes' 키가 없습니다")
        self.assertEqual(len(data['scenes']), 5, "씬 개수가 5개여야 합니다")

    def test_03_scenes_have_image_prompt(self):
        """모든 씬에 image_prompt 필드가 있는지 확인"""
        with open(self.test_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for i, scene in enumerate(data['scenes']):
            self.assertIn(
                'image_prompt', scene,
                f"씬 {i}에 'image_prompt' 필드가 없습니다"
            )
            self.assertTrue(
                len(scene['image_prompt']) > 0,
                f"씬 {i}의 'image_prompt'가 비어있습니다"
            )

    def test_04_output_folder_exists(self):
        """출력 폴더가 존재하는지 확인"""
        self.assertTrue(
            self.test_output_dir.exists(),
            f"출력 폴더가 없습니다: {self.test_output_dir}"
        )

    def test_05_correct_number_of_images_generated(self):
        """생성된 이미지 개수가 씬 개수와 일치하는지 확인"""
        # JSON에서 씬 개수 확인
        with open(self.test_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        expected_count = len(data['scenes'])

        # 출력 폴더에서 PNG 파일 개수 확인
        png_files = list(self.test_output_dir.glob("*.png"))
        actual_count = len(png_files)

        self.assertEqual(
            actual_count, expected_count,
            f"이미지 개수 불일치: 예상 {expected_count}개, 실제 {actual_count}개"
        )

    def test_06_all_scene_images_exist(self):
        """모든 씬에 대한 이미지 파일이 존재하는지 확인"""
        with open(self.test_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for scene in data['scenes']:
            scene_id = scene.get('scene_id', '')
            if scene_id:
                expected_file = self.test_output_dir / f"{scene_id}.png"
                self.assertTrue(
                    expected_file.exists(),
                    f"씬 이미지 파일이 없습니다: {expected_file}"
                )

    def test_07_images_are_not_empty(self):
        """생성된 이미지 파일이 비어있지 않은지 확인"""
        png_files = list(self.test_output_dir.glob("*.png"))

        for png_file in png_files:
            file_size = png_file.stat().st_size
            self.assertGreater(
                file_size, 1000,  # 최소 1KB 이상
                f"이미지 파일이 너무 작습니다: {png_file} ({file_size} bytes)"
            )

    def test_08_metadata_validation(self):
        """JSON 메타데이터가 올바른지 확인"""
        with open(self.test_json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('metadata', data, "JSON에 'metadata' 키가 없습니다")

        metadata = data['metadata']
        self.assertIn('aspect_ratio', metadata, "metadata에 'aspect_ratio'가 없습니다")
        self.assertEqual(metadata['aspect_ratio'], "9:16 (portrait)", "aspect_ratio가 9:16이어야 합니다")


class TestImageCrawlerConfig(unittest.TestCase):
    """이미지 크롤러 설정 테스트"""

    def test_01_crawler_script_exists(self):
        """크롤러 스크립트가 존재하는지 확인"""
        crawler_path = Path(__file__).parent.parent / "src" / "image_crawler" / "image_crawler_working.py"
        self.assertTrue(
            crawler_path.exists(),
            f"크롤러 스크립트가 없습니다: {crawler_path}"
        )

    def test_02_crawler_has_imagefx_option(self):
        """크롤러가 --use-imagefx 옵션을 지원하는지 확인"""
        crawler_path = Path(__file__).parent.parent / "src" / "image_crawler" / "image_crawler_working.py"

        with open(crawler_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn(
            '--use-imagefx',
            content,
            "크롤러에 --use-imagefx 옵션이 없습니다"
        )


if __name__ == '__main__':
    # 테스트 실행
    unittest.main(verbosity=2)
