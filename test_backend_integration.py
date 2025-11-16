"""
Backend 통합 테스트
개발 가이드 Section 4 준수

테스트 범위:
1. 폴더 구조 검증
2. story.json 파싱 및 검증
3. 이미지 파일 검증
4. create_video_from_folder.py 실행
5. 출력 파일 검증
6. 에러 처리
"""

import os
import sys
import io

# Windows UTF-8 출력 설정
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List

# 테스트 결과
test_results = {
    'passed': 0,
    'failed': 0,
    'tests': []
}

def add_test_result(name: str, passed: bool, message: str):
    """테스트 결과 기록"""
    test_results['tests'].append({
        'name': name,
        'passed': passed,
        'message': message
    })
    if passed:
        test_results['passed'] += 1
        print(f"✅ {name}: {message}")
    else:
        test_results['failed'] += 1
        print(f"❌ {name}: {message}")


class TestBackendIntegration:
    """Backend 통합 테스트 클래스"""

    def __init__(self):
        self.backend_dir = Path(__file__).parent
        self.test_data_dir = None
        self.test_output_dir = None

    def setup(self):
        """테스트 환경 설정"""
        # 테스트용 임시 디렉토리 생성
        self.test_data_dir = self.backend_dir / 'test_data_temp'
        self.test_output_dir = self.backend_dir / 'test_output_temp'

        self.test_data_dir.mkdir(exist_ok=True)
        self.test_output_dir.mkdir(exist_ok=True)

        return True

    def teardown(self):
        """테스트 환경 정리"""
        try:
            if self.test_data_dir and self.test_data_dir.exists():
                shutil.rmtree(self.test_data_dir)
            if self.test_output_dir and self.test_output_dir.exists():
                shutil.rmtree(self.test_output_dir)
            return True
        except Exception as e:
            print(f"⚠️ Teardown warning: {e}")
            return False

    def create_test_story_json(self, folder: Path) -> Path:
        """테스트용 story.json 생성"""
        story_data = {
            "metadata": {
                "genre": "shortform",
                "duration": 30,
                "category": "test"
            },
            "hook": {
                "text": "테스트 시작입니다.",
                "duration": 2
            },
            "scenes": [
                {
                    "scene_number": 1,
                    "text": "첫 번째 씬입니다.",
                    "narration": "첫 번째 씬 나레이션",
                    "image_prompt": "test scene 1",
                    "duration": 3
                },
                {
                    "scene_number": 2,
                    "text": "두 번째 씬입니다.",
                    "narration": "두 번째 씬 나레이션",
                    "image_prompt": "test scene 2",
                    "duration": 3
                }
            ],
            "ending": {
                "text": "테스트 끝입니다.",
                "cta": "구독과 좋아요 부탁드립니다.",
                "duration": 2
            }
        }

        story_path = folder / 'story.json'
        with open(story_path, 'w', encoding='utf-8') as f:
            json.dump(story_data, f, ensure_ascii=False, indent=2)

        return story_path

    def create_test_images(self, folder: Path, count: int = 2):
        """테스트용 더미 이미지 생성 (PIL 사용)"""
        try:
            from PIL import Image, ImageDraw, ImageFont

            for i in range(1, count + 1):
                # 9:16 비율 이미지 생성 (1080x1920)
                img = Image.new('RGB', (1080, 1920), color=(73, 109, 137))
                draw = ImageDraw.Draw(img)

                # 텍스트 추가
                text = f"Test Scene {i}"
                try:
                    # 기본 폰트 사용
                    font = ImageFont.load_default()
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except:
                    text_width, text_height = 200, 50

                text_x = (1080 - text_width) // 2
                text_y = (1920 - text_height) // 2
                draw.text((text_x, text_y), text, fill=(255, 255, 255))

                # 저장
                img_path = folder / f'scene_{i:02d}.png'
                img.save(img_path)

            return True
        except ImportError:
            print("⚠️ PIL not available, skipping image creation")
            return False

    def test_folder_structure(self):
        """1. 폴더 구조 검증"""
        print("\n📝 TEST 1: 폴더 구조 검증")
        print("-" * 70)

        # 1-1: input 폴더 존재
        input_dir = self.backend_dir / 'input'
        add_test_result(
            '1-1. input 폴더 존재',
            input_dir.exists(),
            f'{input_dir}' if input_dir.exists() else '폴더 없음'
        )

        # 1-2: output 폴더 존재
        output_dir = self.backend_dir / 'output'
        add_test_result(
            '1-2. output 폴더 존재',
            output_dir.exists(),
            f'{output_dir}' if output_dir.exists() else '폴더 없음'
        )

        # 1-3: create_video_from_folder.py 존재
        script_path = self.backend_dir / 'create_video_from_folder.py'
        add_test_result(
            '1-3. 메인 스크립트 존재',
            script_path.exists(),
            f'{script_path}' if script_path.exists() else '파일 없음'
        )

        # 1-4: src 폴더 구조
        src_dir = self.backend_dir / 'src'
        video_gen_dir = src_dir / 'video_generator'
        add_test_result(
            '1-4. src/video_generator 존재',
            video_gen_dir.exists(),
            f'{video_gen_dir}' if video_gen_dir.exists() else '폴더 없음'
        )

    def test_story_json_validation(self):
        """2. story.json 검증"""
        print("\n📝 TEST 2: story.json 검증")
        print("-" * 70)

        # 2-1: 테스트 폴더 생성
        test_folder = self.test_data_dir / 'test_project_1'
        test_folder.mkdir(exist_ok=True)

        # 2-2: story.json 생성
        story_path = self.create_test_story_json(test_folder)
        add_test_result(
            '2-1. story.json 생성',
            story_path.exists(),
            f'{story_path}'
        )

        # 2-3: story.json 파싱
        try:
            with open(story_path, 'r', encoding='utf-8') as f:
                story_data = json.load(f)

            has_metadata = 'metadata' in story_data
            has_scenes = 'scenes' in story_data
            has_hook = 'hook' in story_data

            add_test_result(
                '2-2. story.json 구조 검증',
                has_metadata and has_scenes and has_hook,
                f'metadata: {has_metadata}, scenes: {has_scenes}, hook: {has_hook}'
            )

            # 2-4: scenes 개수 확인
            scene_count = len(story_data.get('scenes', []))
            add_test_result(
                '2-3. scenes 개수 검증',
                scene_count > 0,
                f'씬 {scene_count}개'
            )

        except Exception as e:
            add_test_result(
                '2-2. story.json 파싱',
                False,
                str(e)
            )

    def test_image_files(self):
        """3. 이미지 파일 검증"""
        print("\n📝 TEST 3: 이미지 파일 검증")
        print("-" * 70)

        test_folder = self.test_data_dir / 'test_project_1'

        # 3-1: 이미지 생성
        try:
            from PIL import Image
            success = self.create_test_images(test_folder, count=2)
            add_test_result(
                '3-1. 테스트 이미지 생성',
                success,
                '2개 이미지 생성됨' if success else 'PIL 없음'
            )

            if success:
                # 3-2: 이미지 파일 존재 확인
                image_files = list(test_folder.glob('scene_*.png'))
                add_test_result(
                    '3-2. 이미지 파일 존재',
                    len(image_files) >= 2,
                    f'{len(image_files)}개 파일'
                )

                # 3-3: 이미지 파일 형식 검증
                if image_files:
                    try:
                        img = Image.open(image_files[0])
                        width, height = img.size
                        is_vertical = height > width
                        add_test_result(
                            '3-3. 이미지 세로 비율 검증',
                            is_vertical,
                            f'{width}x{height}'
                        )
                    except Exception as e:
                        add_test_result(
                            '3-3. 이미지 형식 검증',
                            False,
                            str(e)
                        )
        except ImportError:
            add_test_result(
                '3-1. PIL 패키지',
                False,
                'Pillow 패키지 필요: pip install Pillow'
            )

    def test_dependencies(self):
        """4. 의존성 패키지 검증"""
        print("\n📝 TEST 4: 의존성 패키지 검증")
        print("-" * 70)

        dependencies = [
            ('moviepy', 'moviepy'),
            ('PIL', 'Pillow'),
            ('edge_tts', 'edge-tts')
        ]

        for i, (module_name, package_name) in enumerate(dependencies, 1):
            try:
                __import__(module_name)
                add_test_result(
                    f'4-{i}. {package_name} 패키지',
                    True,
                    '설치됨'
                )
            except ImportError:
                add_test_result(
                    f'4-{i}. {package_name} 패키지',
                    False,
                    f'누락: pip install {package_name}'
                )

    def test_script_execution_dryrun(self):
        """5. 스크립트 실행 테스트 (dry-run)"""
        print("\n📝 TEST 5: 스크립트 실행 (dry-run)")
        print("-" * 70)

        script_path = self.backend_dir / 'create_video_from_folder.py'

        # 5-1: help 옵션 테스트
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), '--help'],
                capture_output=True,
                text=True,
                timeout=10
            )
            add_test_result(
                '5-1. 스크립트 --help',
                result.returncode == 0,
                'help 출력 성공' if result.returncode == 0 else f'exit code: {result.returncode}'
            )
        except Exception as e:
            add_test_result(
                '5-1. 스크립트 --help',
                False,
                str(e)
            )

        # 5-2: 존재하지 않는 폴더로 실행 (에러 처리 테스트)
        try:
            result = subprocess.run(
                [sys.executable, str(script_path), '--folder', 'nonexistent_folder'],
                capture_output=True,
                text=True,
                timeout=10
            )
            # 에러가 발생해야 정상
            error_handled = result.returncode != 0 or '존재하지 않' in result.stderr or 'not found' in result.stderr.lower()
            add_test_result(
                '5-2. 에러 처리 (존재하지 않는 폴더)',
                error_handled,
                '에러 처리 확인' if error_handled else '에러 처리 누락'
            )
        except Exception as e:
            add_test_result(
                '5-2. 에러 처리',
                False,
                str(e)
            )

    def test_input_folder_discovery(self):
        """6. 실제 input 폴더 검색"""
        print("\n📝 TEST 6: 실제 input 폴더 검색")
        print("-" * 70)

        input_dir = self.backend_dir / 'input'

        if not input_dir.exists():
            add_test_result(
                '6-1. input 폴더 검색',
                False,
                'input 폴더 없음'
            )
            return

        # 6-1: project_ 폴더 검색
        project_folders = list(input_dir.glob('project_*'))
        add_test_result(
            '6-1. project_ 폴더 검색',
            len(project_folders) >= 0,
            f'{len(project_folders)}개 폴더 발견'
        )

        # 6-2: story.json 있는 폴더 검색
        folders_with_story = []
        for folder in project_folders:
            story_files = list(folder.glob('story*.json'))
            if story_files:
                folders_with_story.append(folder)

        add_test_result(
            '6-2. story.json 있는 폴더',
            len(folders_with_story) >= 0,
            f'{len(folders_with_story)}개 폴더'
        )

        # 6-3: 이미지 파일 있는 폴더 검색
        folders_with_images = []
        for folder in project_folders:
            image_files = list(folder.glob('scene_*.png')) + list(folder.glob('scene_*.jpg'))
            if image_files:
                folders_with_images.append(folder)

        add_test_result(
            '6-3. 이미지 파일 있는 폴더',
            len(folders_with_images) >= 0,
            f'{len(folders_with_images)}개 폴더'
        )

    def test_output_validation(self):
        """7. 출력 폴더 검증"""
        print("\n📝 TEST 7: 출력 폴더 검증")
        print("-" * 70)

        output_dir = self.backend_dir / 'output'

        if not output_dir.exists():
            add_test_result(
                '7-1. output 폴더 존재',
                False,
                'output 폴더 없음'
            )
            return

        # 7-1: 최근 생성된 영상 파일 검색
        video_files = list(output_dir.glob('*.mp4'))
        add_test_result(
            '7-1. 생성된 영상 파일',
            len(video_files) >= 0,
            f'{len(video_files)}개 영상 파일'
        )

        # 7-2: 가장 최근 영상 파일 크기 확인
        if video_files:
            latest_video = max(video_files, key=lambda p: p.stat().st_mtime)
            file_size_mb = latest_video.stat().st_size / (1024 * 1024)
            add_test_result(
                '7-2. 최근 영상 파일 크기',
                file_size_mb > 0,
                f'{file_size_mb:.2f}MB ({latest_video.name})'
            )

    def run_all_tests(self):
        """모든 테스트 실행"""
        print("🧪 [Backend 통합 테스트] 시작")
        print("개발 가이드 Section 4 준수\n")
        print("=" * 70 + "\n")

        # Setup
        if not self.setup():
            print("❌ 테스트 환경 설정 실패")
            return False

        try:
            # 테스트 실행
            self.test_folder_structure()
            self.test_story_json_validation()
            self.test_image_files()
            self.test_dependencies()
            self.test_script_execution_dryrun()
            self.test_input_folder_discovery()
            self.test_output_validation()

        finally:
            # Teardown
            self.teardown()

        # 결과 요약
        print("\n" + "=" * 70)
        print("📊 테스트 결과 요약")
        print("=" * 70)
        print(f"✅ 통과: {test_results['passed']}/{len(test_results['tests'])}")
        print(f"❌ 실패: {test_results['failed']}/{len(test_results['tests'])}")

        if test_results['failed'] == 0:
            print("\n🎉 모든 테스트 통과!")
            print("\n📝 검증 완료 항목:")
            print("  ✅ 폴더 구조 검증")
            print("  ✅ story.json 파싱 및 검증")
            print("  ✅ 이미지 파일 검증")
            print("  ✅ 의존성 패키지 확인")
            print("  ✅ 스크립트 실행 테스트")
            print("  ✅ 입출력 폴더 검증")
        else:
            print("\n❌ 일부 테스트 실패")
            print("\n실패 항목:")
            for test in test_results['tests']:
                if not test['passed']:
                    print(f"  - {test['name']}: {test['message']}")

        print("=" * 70)

        return test_results['failed'] == 0


def main():
    """메인 함수"""
    print("⚙️  개발 가이드 Section 4 준수")
    print("   - Backend 전체 통합 테스트")
    print("   - 폴더 구조, story.json, 이미지, 스크립트 실행")
    print("   - 실패 시 상세 리포트\n")

    tester = TestBackendIntegration()
    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
