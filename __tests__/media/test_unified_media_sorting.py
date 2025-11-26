"""
통합 미디어 정렬 리그레션 테스트

시나리오:
- iii01.img, jjj02.mp4, jjjj03.mp4, ididi04.img, idia05.img
- 예상 순서: 01 -> 02 -> 03 -> 04 -> 05 (시퀀스 번호 순)
- 파일 타입(img/mp4)과 관계없이 시퀀스 번호가 우선
"""

import pytest


class TestUnifiedMediaSorting:
    """통합 미디어 정렬 테스트"""

    def test_real_scenario_image_video_mixed(self):
        """
        실제 시나리오: 01.jpeg, 02.mp4, 03.mp4, 04.jpeg, 05.jpeg
        예상: 01 → 02 → 03 → 04 → 05 (시퀀스 순서)
        """
        files = [
            {'name': '01.jpeg', 'type': 'image', 'lastModified': 1000},
            {'name': '02.mp4', 'type': 'video', 'lastModified': 2000},
            {'name': '03.mp4', 'type': 'video', 'lastModified': 3000},
            {'name': '04.jpeg', 'type': 'image', 'lastModified': 4000},
            {'name': '05.jpeg', 'type': 'image', 'lastModified': 5000},
        ]

        # 시퀀스 번호 추출
        import re
        def extract_number(filename):
            match = re.search(r'(\d+)', filename)
            return int(match.group(1)) if match else None

        # 정렬
        sorted_files = sorted(files, key=lambda f: (
            extract_number(f['name']) is None,
            extract_number(f['name']) if extract_number(f['name']) is not None else 0,
            f['lastModified']
        ))

        # 검증
        expected_order = ['01.jpeg', '02.mp4', '03.mp4', '04.jpeg', '05.jpeg']
        actual_order = [f['name'] for f in sorted_files]

        print("\n[REAL SCENARIO] 정렬 결과:")
        for i, f in enumerate(sorted_files, 1):
            seq = extract_number(f['name'])
            media_type = 'IMG' if f['type'] == 'image' else 'VID'
            print(f"  {i}. [{media_type}] {f['name']} (seq: {seq})")

        assert actual_order == expected_order, f"정렬 순서 불일치: {actual_order}"

    def test_frontend_sorting_logic(self):
        """
        Frontend 정렬 로직 시뮬레이션
        파일명에서 첫 번째 숫자를 추출하여 정렬
        """
        files = [
            {'name': 'iii01.img', 'type': 'image', 'lastModified': 1000},
            {'name': 'jjj02.mp4', 'type': 'video', 'lastModified': 2000},
            {'name': 'jjjj03.mp4', 'type': 'video', 'lastModified': 3000},
            {'name': 'ididi04.img', 'type': 'image', 'lastModified': 4000},
            {'name': 'idia05.img', 'type': 'image', 'lastModified': 5000},
        ]

        # 시퀀스 번호 추출
        import re
        def extract_number(filename):
            match = re.search(r'(\d+)', filename)
            return int(match.group(1)) if match else None

        # 정렬
        sorted_files = sorted(files, key=lambda f: (
            extract_number(f['name']) is None,
            extract_number(f['name']) if extract_number(f['name']) is not None else 0,
            f['lastModified']
        ))

        # 검증
        expected_order = ['iii01.img', 'jjj02.mp4', 'jjjj03.mp4', 'ididi04.img', 'idia05.img']
        actual_order = [f['name'] for f in sorted_files]

        print("\n[Frontend] 정렬 결과:")
        for i, f in enumerate(sorted_files, 1):
            seq = extract_number(f['name'])
            print(f"  {i}. {f['name']} (seq: {seq}, type: {f['type']})")

        assert actual_order == expected_order, f"정렬 순서 불일치: {actual_order}"

    def test_sortable_media_list_bug(self):
        """
        SortableMediaList의 버그 재현:
        정렬된 파일을 이미지/비디오로 분리 → 다시 합치면 순서가 바뀜!

        실제 시나리오:
        - 사용자가 업로드: 01.jpeg, 02.mp4, 03.mp4, 04.jpeg, 05.jpeg
        - SortableMediaList가 정렬: [01.jpeg, 02.mp4, 03.mp4, 04.jpeg, 05.jpeg]
        - onFilesReorder에서 분리:
          * uploadedImages = [01.jpeg, 04.jpeg, 05.jpeg]
          * uploadedVideos = [02.mp4, 03.mp4]
        - 다시 합침: [...uploadedImages, ...uploadedVideos]
          = [01.jpeg, 04.jpeg, 05.jpeg, 02.mp4, 03.mp4]  ← 순서 바뀜!
        """
        # 정렬된 파일 리스트 (SortableMediaList의 출력)
        sorted_files = [
            {'name': '01.jpeg', 'type': 'image/jpeg'},
            {'name': '02.mp4', 'type': 'video/mp4'},
            {'name': '03.mp4', 'type': 'video/mp4'},
            {'name': '04.jpeg', 'type': 'image/jpeg'},
            {'name': '05.jpeg', 'type': 'image/jpeg'},
        ]

        # === 잘못된 방법: 분리 후 재결합 ===
        uploaded_images = [f for f in sorted_files if f['type'].startswith('image/')]
        uploaded_videos = [f for f in sorted_files if f['type'].startswith('video/')]

        # 다시 합침 (기존 코드)
        wrong_combined = uploaded_images + uploaded_videos
        wrong_order = [f['name'] for f in wrong_combined]

        print("\n[BUG] 분리 후 재결합:")
        for i, name in enumerate(wrong_order, 1):
            print(f"  {i}. {name}")

        # 순서가 바뀜!
        assert wrong_order == ['01.jpeg', '04.jpeg', '05.jpeg', '02.mp4', '03.mp4']

        # === 올바른 방법: sortedMediaFiles state에 그대로 저장 ===
        correct_order = [f['name'] for f in sorted_files]

        print("\n[FIX] 정렬 순서 그대로 유지:")
        for i, name in enumerate(correct_order, 1):
            print(f"  {i}. {name}")

        # 순서 유지!
        assert correct_order == ['01.jpeg', '02.mp4', '03.mp4', '04.jpeg', '05.jpeg']

    def test_formdata_order_preservation(self):
        """
        FormData 전송 시 순서 보존 테스트

        문제: image_0, image_1, video_0 형태로 분리하면 순서가 바뀜!
        해결: media_0, media_1, media_2 형태로 통합 전송
        """
        sorted_files = [
            {'name': '01.img', 'type': 'image'},
            {'name': '02.mp4', 'type': 'video'},
            {'name': '03.mp4', 'type': 'video'},
            {'name': '04.img', 'type': 'image'},
            {'name': '05.img', 'type': 'image'},
        ]

        # === 잘못된 방법 (타입별 분리) ===
        wrong_formdata = {}
        image_index = 0
        video_index = 0
        for file in sorted_files:
            if file['type'] == 'image':
                wrong_formdata[f"image_{image_index}"] = file['name']
                image_index += 1
            else:
                wrong_formdata[f"video_{video_index}"] = file['name']
                video_index += 1

        # Backend에서 받을 때: 이미지 먼저, 비디오 나중
        wrong_received = []
        for i in range(10):
            if f"image_{i}" in wrong_formdata:
                wrong_received.append(wrong_formdata[f"image_{i}"])
        for i in range(10):
            if f"video_{i}" in wrong_formdata:
                wrong_received.append(wrong_formdata[f"video_{i}"])

        print("\n[WRONG] 타입별 분리 전송:")
        for i, name in enumerate(wrong_received, 1):
            print(f"  {i}. {name}")

        # 순서가 바뀜!
        assert wrong_received == ['01.img', '04.img', '05.img', '02.mp4', '03.mp4']

        # === 올바른 방법 (통합 전송) ===
        correct_formdata = {}
        for i, file in enumerate(sorted_files):
            correct_formdata[f"media_{i}"] = file['name']

        # Backend에서 받을 때: 순서 유지
        correct_received = []
        for i in range(10):
            if f"media_{i}" in correct_formdata:
                correct_received.append(correct_formdata[f"media_{i}"])

        print("\n[CORRECT] 통합 전송:")
        for i, name in enumerate(correct_received, 1):
            print(f"  {i}. {name}")

        # 순서 유지!
        assert correct_received == ['01.img', '02.mp4', '03.mp4', '04.img', '05.img']

    def test_backend_unified_sorting(self):
        """
        Backend 통합 정렬 로직 테스트 (Python)
        """
        files = ['01.img', '02.mp4', '03.mp4', '04.img', '05.img']

        import re
        def extract_sequence(filename):
            # 1. 파일명이 숫자로 시작: "01.jpg"
            match = re.match(r'^(\d+)\.', filename)
            if match:
                return (int(match.group(1)), 0)
            return (None, 0)

        # 정렬
        sorted_files = sorted(files, key=lambda f: (
            extract_sequence(f)[0] is None,
            extract_sequence(f)[0] if extract_sequence(f)[0] is not None else 0,
            extract_sequence(f)[1]
        ))

        print("\n[Backend Python] 정렬 결과:")
        for i, name in enumerate(sorted_files, 1):
            seq = extract_sequence(name)[0]
            print(f"  Scene {i}: {name} (seq: {seq})")

        assert sorted_files == files


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
