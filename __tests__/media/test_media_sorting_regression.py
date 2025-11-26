"""
미디어 정렬 로직 리그레션 테스트

이 테스트는 실제 사용자 불만 사례를 기반으로 작성되었습니다:
- 요구사항: 무조건 번호순 → 오래된순 (타입 무관)
- 파일 예시: 01.jpg, 02.jpg, 03.jpg, 04.mp4, 05.mp4
- 기대 결과: 번호 순서대로 1→2→3→4→5 (이미지/비디오 섞여있어도)
"""

import re
from pathlib import Path
from typing import Optional, Tuple
import pytest


def extract_sequence(filepath: Path) -> Tuple[Optional[int], float]:
    """
    파일명에서 시퀀스 번호 추출 (Frontend extractSequenceNumber와 동일한 로직)
    - 1.jpg, 02.png (숫자로 시작)
    - image_01.jpg, scene-02.png (_숫자 또는 -숫자)
    - Image_fx (47).jpg (괄호 안 숫자, 랜덤 ID 없을 때만)

    Returns: (sequence_number or None, mtime)
    """
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


def sort_media_files(files: list[Path]) -> list[Path]:
    """
    미디어 파일 정렬 (시퀀스 번호 우선 → 오래된순)
    """
    return sorted(files, key=lambda f: (
        extract_sequence(f)[0] is None,  # 시퀀스 없는 것을 뒤로
        extract_sequence(f)[0] if extract_sequence(f)[0] is not None else 0,  # 시퀀스 정렬
        extract_sequence(f)[1]  # 시간 정렬 (오래된순)
    ))


class TestExtractSequence:
    """시퀀스 번호 추출 테스트"""

    def test_숫자로_시작하는_파일명(self, tmp_path):
        """1.jpg, 02.jpg 같은 파일명"""
        files = [
            tmp_path / '1.jpg',
            tmp_path / '02.jpg',
            tmp_path / '03.jpg',
            tmp_path / '04.mp4',
            tmp_path / '05.mp4',
            tmp_path / '123.png',
        ]

        for f in files:
            f.touch()

        assert extract_sequence(files[0])[0] == 1
        assert extract_sequence(files[1])[0] == 2
        assert extract_sequence(files[2])[0] == 3
        assert extract_sequence(files[3])[0] == 4
        assert extract_sequence(files[4])[0] == 5
        assert extract_sequence(files[5])[0] == 123

    def test_언더스코어_또는_대시_패턴(self, tmp_path):
        """image_01.jpg, scene-02.png 같은 파일명"""
        files = [
            tmp_path / 'image_01.jpg',
            tmp_path / 'scene-02.png',
            tmp_path / 'video_123.mp4',
        ]

        for f in files:
            f.touch()

        assert extract_sequence(files[0])[0] == 1
        assert extract_sequence(files[1])[0] == 2
        assert extract_sequence(files[2])[0] == 123

    def test_괄호_패턴(self, tmp_path):
        """Image_fx (47).jpg 같은 파일명"""
        files = [
            tmp_path / 'Image_fx (47).jpg',
            tmp_path / 'Photo (12).png',
        ]

        for f in files:
            f.touch()

        assert extract_sequence(files[0])[0] == 47
        assert extract_sequence(files[1])[0] == 12

    def test_랜덤ID가_있으면_번호_추출_안함(self, tmp_path):
        """Whisk_2ea51d84758d256bf4b4235fccf6022c.png 같은 파일명"""
        files = [
            tmp_path / 'Whisk_2ea51d84758d256bf4b4235fccf6022c.png',
            tmp_path / 'Image_abc123def456 (5).jpg',
        ]

        for f in files:
            f.touch()

        assert extract_sequence(files[0])[0] is None
        assert extract_sequence(files[1])[0] is None

    def test_번호가_없는_파일(self, tmp_path):
        """random.jpg, photo.png 같은 파일명"""
        files = [
            tmp_path / 'random.jpg',
            tmp_path / 'photo.png',
        ]

        for f in files:
            f.touch()

        assert extract_sequence(files[0])[0] is None
        assert extract_sequence(files[1])[0] is None


class TestMediaSorting:
    """미디어 정렬 테스트"""

    def test_실제_사용자_케이스_01_to_05(self, tmp_path):
        """
        실제 케이스: 01.jpg, 02.jpg, 03.jpg, 04.mp4, 05.mp4
        기대 결과: 번호순 정렬 (타입 무관)
        """
        import time

        # 파일 생성 (역순으로 생성하여 mtime이 섞이도록)
        files = [
            tmp_path / '05.mp4',
            tmp_path / '01.jpg',
            tmp_path / '03.jpg',
            tmp_path / '04.mp4',
            tmp_path / '02.jpg',
        ]

        for f in files:
            f.touch()
            time.sleep(0.01)  # mtime이 다르도록

        sorted_files = sort_media_files(files)
        sorted_names = [f.name for f in sorted_files]

        assert sorted_names == [
            '01.jpg',
            '02.jpg',
            '03.jpg',
            '04.mp4',
            '05.mp4',
        ]

    def test_모두_같은_시간에_업로드된_경우(self, tmp_path):
        """
        실제 케이스: 모든 파일이 같은 시간에 생성됨
        기대 결과: 번호순 정렬만으로 결정
        """
        # 모두 동시에 생성 (mtime 동일)
        files = [
            tmp_path / '04.mp4',
            tmp_path / '02.jpg',
            tmp_path / '05.mp4',
            tmp_path / '01.jpg',
            tmp_path / '03.jpg',
        ]

        for f in files:
            f.write_bytes(b'')  # 동시 생성

        sorted_files = sort_media_files(files)
        sorted_names = [f.name for f in sorted_files]

        assert sorted_names == [
            '01.jpg',
            '02.jpg',
            '03.jpg',
            '04.mp4',
            '05.mp4',
        ]

    def test_image_video_prefix_파일명(self, tmp_path):
        """
        구버전 케이스: image_01.jpg, video_01.mp4
        기대 결과: 같은 번호면 lastModified로 정렬
        """
        import time

        files = [
            tmp_path / 'image_01.jpg',    # 번호 1, 첫 번째 생성 (가장 오래됨)
            tmp_path / 'video_01.mp4',    # 번호 1, 두 번째 생성
            tmp_path / 'image_02.jpg',    # 번호 2, 세 번째 생성
            tmp_path / 'video_02.mp4',    # 번호 2, 네 번째 생성
            tmp_path / 'image_03.jpg',    # 번호 3, 다섯 번째 생성
        ]

        for f in files:
            f.touch()
            time.sleep(0.01)

        sorted_files = sort_media_files(files)
        sorted_names = [f.name for f in sorted_files]

        # 번호순 정렬 → 같은 번호면 mtime 순 (오래된순)
        assert sorted_names == [
            'image_01.jpg',   # 번호 1, mtime 가장 오래됨
            'video_01.mp4',   # 번호 1, mtime 두 번째
            'image_02.jpg',   # 번호 2, mtime 세 번째
            'video_02.mp4',   # 번호 2, mtime 네 번째
            'image_03.jpg',   # 번호 3
        ]

    def test_번호_섞인_경우(self, tmp_path):
        """
        번호가 크게 섞인 경우: 1, 2, 10, 20
        기대 결과: 숫자 크기로 정렬 (1 < 2 < 10 < 20)
        """
        import time

        files = [
            tmp_path / '10.jpg',
            tmp_path / '2.mp4',
            tmp_path / '1.jpg',
            tmp_path / '20.mp4',
        ]

        for f in files:
            f.touch()
            time.sleep(0.01)

        sorted_files = sort_media_files(files)
        sorted_names = [f.name for f in sorted_files]

        assert sorted_names == [
            '1.jpg',   # 1
            '2.mp4',   # 2
            '10.jpg',  # 10
            '20.mp4',  # 20
        ]


class TestEdgeCases:
    """에지 케이스 테스트"""

    def test_번호_없는_파일_lastModified_정렬(self, tmp_path):
        """번호가 없으면 오래된순"""
        import time

        files = [
            tmp_path / 'photo3.jpg',
            tmp_path / 'photo1.jpg',
            tmp_path / 'photo2.jpg',
        ]

        for f in files:
            f.touch()
            time.sleep(0.01)

        sorted_files = sort_media_files(files)
        sorted_names = [f.name for f in sorted_files]

        # mtime 순 (생성 순서)
        assert sorted_names == [
            'photo3.jpg',
            'photo1.jpg',
            'photo2.jpg',
        ]

    def test_번호_있는_파일이_우선(self, tmp_path):
        """번호 있는 파일 > 번호 없는 파일"""
        import time

        files = [
            tmp_path / 'random.jpg',  # 가장 먼저 생성, 번호 없음
            tmp_path / '02.mp4',
            tmp_path / '01.jpg',
        ]

        for f in files:
            f.touch()
            time.sleep(0.01)

        sorted_files = sort_media_files(files)
        sorted_names = [f.name for f in sorted_files]

        assert sorted_names == [
            '01.jpg',     # 번호 1 (우선)
            '02.mp4',     # 번호 2
            'random.jpg',  # 번호 없음 (뒤로)
        ]

    def test_제로_패딩_vs_비패딩(self, tmp_path):
        """01 vs 1 - 숫자 크기로 정렬"""
        import time

        files = [
            tmp_path / '10.jpg',
            tmp_path / '02.jpg',
            tmp_path / '1.jpg',
        ]

        for f in files:
            f.touch()
            time.sleep(0.01)

        sorted_files = sort_media_files(files)
        sorted_names = [f.name for f in sorted_files]

        assert sorted_names == [
            '1.jpg',   # 1
            '02.jpg',  # 2
            '10.jpg',  # 10
        ]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
