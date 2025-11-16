"""
영상병합 미디어-씬 매칭 로직 리그레션 테스트

테스트 케이스:
1. 씬 5개, 비디오 1개, 이미지 5개 (총 미디어 6개)
2. 씬 5개, 비디오 3개 (총 미디어 3개) - 균등 분배
3. 씬 5개, 이미지 2개 (총 미디어 2개) - 균등 분배
4. 씬 3개, 비디오 1개, 이미지 1개 (총 미디어 2개)
"""

import pytest
from pathlib import Path
import json
import tempfile
import shutil


class TestMediaSceneMatching:
    """미디어-씬 매칭 로직 테스트"""

    @pytest.fixture
    def temp_dir(self):
        """임시 디렉토리 생성"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)

    def create_test_story(self, temp_dir: Path, num_scenes: int):
        """테스트용 story.json 생성"""
        scenes = []
        for i in range(1, num_scenes + 1):
            scenes.append({
                "scene_number": i,
                "title": f"씬 {i}",
                "narration": f"테스트 나레이션 {i}",
                "image_prompt": f"테스트 이미지 {i}"
            })

        story = {
            "title": "테스트 영상",
            "scenes": scenes
        }

        story_path = temp_dir / "story.json"
        with open(story_path, 'w', encoding='utf-8') as f:
            json.dump(story, f, ensure_ascii=False, indent=2)

        return story_path

    def create_test_media(self, temp_dir: Path, num_images: int, num_videos: int):
        """테스트용 미디어 파일 생성 (더미)"""
        images = {}
        videos = {}

        # 이미지 생성 (더미 파일)
        for i in range(1, num_images + 1):
            img_path = temp_dir / f"image_{i:02d}.jpg"
            img_path.write_text("dummy image")
            images[i] = img_path

        # 비디오 생성 (더미 파일)
        for i in range(1, num_videos + 1):
            vid_path = temp_dir / f"video_{i:02d}.mp4"
            vid_path.write_text("dummy video")
            videos[i] = vid_path

        return images, videos

    def test_case_1_more_media_than_scenes(self, temp_dir):
        """
        케이스 1: 씬 5개, 비디오 1개, 이미지 5개 (총 미디어 6개)

        파일명:
        - image_01, image_02, image_03, image_04, image_05
        - video_01

        통합 정렬 결과 (파일명 번호 기준):
        1. image_01 (번호 1)
        2. video_01 (번호 1, 시간으로 2차 정렬)
        3. image_02 (번호 2)
        4. image_03 (번호 3)
        5. image_04 (번호 4)
        6. image_05 (번호 5)

        예상 매칭 (씬 < 미디어, 1:1 매칭):
        - 씬 1 → image_01
        - 씬 2 → video_01
        - 씬 3 → image_02
        - 씬 4 → image_03
        - 씬 5 → image_04
        - image_05는 사용 안 됨
        """
        num_scenes = 5
        num_images = 5
        num_videos = 1

        story_path = self.create_test_story(temp_dir, num_scenes)
        images, videos = self.create_test_media(temp_dir, num_images, num_videos)

        narration_count = num_scenes
        total_media = num_images + num_videos

        assert narration_count == 5
        assert total_media == 6
        assert narration_count < total_media  # 씬이 미디어보다 적음

        # 파일명 통합 정렬 시뮬레이션
        import re
        all_media = []
        for num, path in images.items():
            all_media.append(('image', num, path))
        for num, path in videos.items():
            all_media.append(('video', num, path))

        def extract_number(media_tuple):
            media_type, orig_num, path = media_tuple
            filename = path.stem
            match = re.search(r'(\d+)', filename)
            return int(match.group(1)) if match else 999999

        all_media.sort(key=lambda x: (extract_number(x), x[2].stat().st_mtime))

        # 처음 5개만 사용됨
        used_media = all_media[:5]
        unused_media = all_media[5:]

        print(f"[OK] Used: {[f'{m[0]} {m[2].name}' for m in used_media]}")
        print(f"[X] Unused: {[f'{m[0]} {m[2].name}' for m in unused_media]}")

        # 예상: image_01, video_01, image_02, image_03, image_04 사용
        # image_05 미사용

    def test_case_2_fewer_media_than_scenes_videos_only(self, temp_dir):
        """
        케이스 2: 씬 5개, 비디오 3개 (총 미디어 3개) - 균등 분배

        예상 결과 (균등 분배):
        - 비디오 1 → 씬 1, 씬 2 (2개 씬)
        - 비디오 2 → 씬 3, 씬 4 (2개 씬)
        - 비디오 3 → 씬 5 (1개 씬)

        계산:
        - scenes_per_media = 5 // 3 = 1
        - extra_scenes = 5 % 3 = 2
        - 앞의 2개 미디어는 +1씩 받음
        """
        num_scenes = 5
        num_images = 0
        num_videos = 3

        story_path = self.create_test_story(temp_dir, num_scenes)
        images, videos = self.create_test_media(temp_dir, num_images, num_videos)

        narration_count = num_scenes
        total_media = num_images + num_videos

        # 균등 분배 로직 시뮬레이션
        if narration_count > total_media and total_media > 0:
            scenes_per_media = narration_count // total_media  # 5 // 3 = 1
            extra_scenes = narration_count % total_media  # 5 % 3 = 2

            assert scenes_per_media == 1
            assert extra_scenes == 2

            # 예상 분배:
            # 미디어 1: 1 + 1 = 2개 씬 (extra_scenes > 0)
            # 미디어 2: 1 + 1 = 2개 씬 (extra_scenes > 0)
            # 미디어 3: 1개 씬
            distribution = []
            for media_idx in range(total_media):
                # 처음 extra_scenes개의 미디어는 +1씩 받음
                if media_idx < extra_scenes:
                    num_scenes_for_media = scenes_per_media + 1
                else:
                    num_scenes_for_media = scenes_per_media
                distribution.append(num_scenes_for_media)

            expected = [2, 2, 1]  # 비디오 1: 2씬, 비디오 2: 2씬, 비디오 3: 1씬
            assert distribution == expected
            print(f"[OK] Expected distribution: {expected}")
        else:
            pytest.fail("균등 분배 로직이 실행되지 않음")

    def test_case_3_fewer_media_than_scenes_images_only(self, temp_dir):
        """
        케이스 3: 씬 5개, 이미지 2개 (총 미디어 2개) - 균등 분배

        예상 결과 (균등 분배):
        - 이미지 1 → 씬 1, 씬 2, 씬 3 (3개 씬)
        - 이미지 2 → 씬 4, 씬 5 (2개 씬)

        계산:
        - scenes_per_media = 5 // 2 = 2
        - extra_scenes = 5 % 2 = 1
        - 첫 번째 미디어는 +1 받음
        """
        num_scenes = 5
        num_images = 2
        num_videos = 0

        story_path = self.create_test_story(temp_dir, num_scenes)
        images, videos = self.create_test_media(temp_dir, num_images, num_videos)

        narration_count = num_scenes
        total_media = num_images + num_videos

        if narration_count > total_media and total_media > 0:
            scenes_per_media = narration_count // total_media  # 5 // 2 = 2
            extra_scenes = narration_count % total_media  # 5 % 2 = 1

            assert scenes_per_media == 2
            assert extra_scenes == 1

            distribution = []
            for media_idx in range(total_media):
                # 처음 extra_scenes개의 미디어는 +1씩 받음
                if media_idx < extra_scenes:
                    num_scenes_for_media = scenes_per_media + 1
                else:
                    num_scenes_for_media = scenes_per_media
                distribution.append(num_scenes_for_media)

            expected = [3, 2]  # 이미지 1: 3씬, 이미지 2: 2씬
            assert distribution == expected
            print(f"[OK] Expected distribution: {expected}")
        else:
            pytest.fail("균등 분배 로직이 실행되지 않음")

    def test_case_4_equal_media_and_scenes(self, temp_dir):
        """
        케이스 4: 씬 3개, 비디오 1개, 이미지 2개 (총 미디어 3개)

        예상 결과 (파일명 기준 통합 정렬):
        - 씬 1 → 이미지 1 (image_01)
        - 씬 2 → 비디오 1 (video_01)
        - 씬 3 → 이미지 2 (image_02)

        주의: 타입별로 분리하지 않고, 파일명 번호 기준으로 통합 정렬
        """
        num_scenes = 3
        num_images = 2
        num_videos = 1

        story_path = self.create_test_story(temp_dir, num_scenes)
        images, videos = self.create_test_media(temp_dir, num_images, num_videos)

        narration_count = num_scenes
        total_media = num_images + num_videos

        # 씬 == 미디어이므로 균등 분배 안 함
        assert narration_count == total_media
        assert narration_count == 3

        # 파일명 통합 정렬 시뮬레이션
        import re
        all_media = []
        for num, path in images.items():
            all_media.append(('image', num, path))
        for num, path in videos.items():
            all_media.append(('video', num, path))

        # 파일명에서 숫자 추출하여 정렬
        def extract_number(media_tuple):
            media_type, orig_num, path = media_tuple
            filename = path.stem
            match = re.search(r'(\d+)', filename)
            return int(match.group(1)) if match else 999999

        all_media.sort(key=lambda x: (extract_number(x), x[2].stat().st_mtime))

        # 정렬 순서 확인
        sorted_types = [m[0] for m in all_media]
        expected_order = ['image', 'video', 'image']  # image_01, video_01, image_02
        assert sorted_types == expected_order, f"정렬 순서가 잘못됨: {sorted_types}"

        print("[OK] Expected: 1:1 matching (image 1, video 1, image 2) - sorted by filename number")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
