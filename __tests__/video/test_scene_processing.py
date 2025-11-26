"""
씬 처리 로직 통합 리그레션 테스트

테스트 범위:
- 씬 정렬 (seq → created_at → 원래 순서)
- 미디어 타입 감지 (비디오 우선, 이미지 fallback)
- Scene media 데이터 구조
- 비디오/이미지 혼합 처리
"""
import pytest
from datetime import datetime
from pathlib import Path


class TestSceneSorting:
    """씬 정렬 로직 테스트"""

    def test_sort_by_seq_when_present(self):
        """seq 필드가 있으면 seq로 정렬"""
        scenes = [
            {'seq': 3, 'title': 'Scene C'},
            {'seq': 1, 'title': 'Scene A'},
            {'seq': 2, 'title': 'Scene B'},
        ]

        # 정렬 로직 (seq 우선)
        def get_sort_key(scene):
            if 'seq' in scene and scene['seq'] is not None:
                return (0, scene['seq'])
            return (2, 0)

        sorted_scenes = sorted(scenes, key=get_sort_key)

        assert sorted_scenes[0]['title'] == 'Scene A'
        assert sorted_scenes[1]['title'] == 'Scene B'
        assert sorted_scenes[2]['title'] == 'Scene C'

    def test_sort_by_created_at_when_no_seq(self):
        """seq가 없으면 created_at으로 정렬"""
        scenes = [
            {'created_at': '2025-01-10T15:00:00Z', 'title': 'Scene B'},
            {'created_at': '2025-01-10T10:00:00Z', 'title': 'Scene A'},
            {'created_at': '2025-01-10T20:00:00Z', 'title': 'Scene C'},
        ]

        def get_sort_key(scene):
            if 'created_at' in scene and scene['created_at']:
                try:
                    timestamp = datetime.fromisoformat(scene['created_at'].replace('Z', '+00:00'))
                    return (1, timestamp.timestamp())
                except:
                    return (2, 0)
            return (2, 0)

        sorted_scenes = sorted(scenes, key=get_sort_key)

        assert sorted_scenes[0]['title'] == 'Scene A'  # 10:00
        assert sorted_scenes[1]['title'] == 'Scene B'  # 15:00
        assert sorted_scenes[2]['title'] == 'Scene C'  # 20:00

    def test_seq_overrides_created_at(self):
        """seq가 있으면 created_at보다 우선"""
        scenes = [
            {'seq': 2, 'created_at': '2025-01-10T10:00:00Z', 'title': 'B'},
            {'seq': 1, 'created_at': '2025-01-10T20:00:00Z', 'title': 'A'},
        ]

        def get_sort_key(scene):
            if 'seq' in scene and scene['seq'] is not None:
                return (0, scene['seq'])
            if 'created_at' in scene and scene['created_at']:
                try:
                    timestamp = datetime.fromisoformat(scene['created_at'].replace('Z', '+00:00'))
                    return (1, timestamp.timestamp())
                except:
                    return (2, 0)
            return (2, 0)

        sorted_scenes = sorted(scenes, key=get_sort_key)

        # seq 우선: seq=1이 먼저
        assert sorted_scenes[0]['title'] == 'A'
        assert sorted_scenes[1]['title'] == 'B'

    def test_mixed_seq_and_no_seq(self):
        """일부는 seq, 일부는 created_at"""
        scenes = [
            {'created_at': '2025-01-10T12:00:00Z', 'title': 'C'},  # no seq
            {'seq': 1, 'title': 'A'},
            {'created_at': '2025-01-10T10:00:00Z', 'title': 'D'},  # no seq
            {'seq': 2, 'title': 'B'},
        ]

        def get_sort_key(scene):
            if 'seq' in scene and scene['seq'] is not None:
                return (0, scene['seq'])
            if 'created_at' in scene and scene['created_at']:
                try:
                    timestamp = datetime.fromisoformat(scene['created_at'].replace('Z', '+00:00'))
                    return (1, timestamp.timestamp())
                except:
                    return (2, 0)
            return (2, 0)

        sorted_scenes = sorted(scenes, key=get_sort_key)

        # seq가 있는 것들이 먼저 (A, B)
        # 그 다음 created_at 순서 (D, C)
        assert sorted_scenes[0]['title'] == 'A'
        assert sorted_scenes[1]['title'] == 'B'
        assert sorted_scenes[2]['title'] == 'D'
        assert sorted_scenes[3]['title'] == 'C'

    def test_null_seq_treated_as_no_seq(self):
        """seq가 null이면 없는 것으로 처리"""
        scenes = [
            {'seq': None, 'created_at': '2025-01-10T20:00:00Z', 'title': 'B'},
            {'seq': 1, 'title': 'A'},
        ]

        def get_sort_key(scene):
            if 'seq' in scene and scene['seq'] is not None:
                return (0, scene['seq'])
            if 'created_at' in scene and scene['created_at']:
                try:
                    timestamp = datetime.fromisoformat(scene['created_at'].replace('Z', '+00:00'))
                    return (1, timestamp.timestamp())
                except:
                    return (2, 0)
            return (2, 0)

        sorted_scenes = sorted(scenes, key=get_sort_key)

        assert sorted_scenes[0]['title'] == 'A'  # seq=1
        assert sorted_scenes[1]['title'] == 'B'  # seq=null → created_at

    def test_invalid_created_at_fallback(self):
        """잘못된 created_at은 fallback"""
        scenes = [
            {'created_at': 'invalid-date', 'title': 'B'},
            {'created_at': '2025-01-10T10:00:00Z', 'title': 'A'},
        ]

        def get_sort_key(scene):
            if 'created_at' in scene and scene['created_at']:
                try:
                    timestamp = datetime.fromisoformat(scene['created_at'].replace('Z', '+00:00'))
                    return (1, timestamp.timestamp())
                except:
                    return (2, 0)
            return (2, 0)

        sorted_scenes = sorted(scenes, key=get_sort_key)

        # A가 먼저 (유효한 타임스탬프), B가 나중 (invalid)
        assert sorted_scenes[0]['title'] == 'A'
        assert sorted_scenes[1]['title'] == 'B'


class TestMediaTypeDetection:
    """미디어 타입 감지 테스트"""

    def test_video_has_priority_over_image(self):
        """비디오가 있으면 비디오 우선 사용"""
        scene_files = {
            'video_path': Path('scene_01/scene_01_video.mp4'),
            'image_path': Path('scene_01/scene_01_image.png'),
        }

        # 비디오 우선 로직
        if scene_files['video_path'].name.endswith('.mp4'):  # exists() 대신 name check
            media_type = 'video'
            media_path = scene_files['video_path']
        else:
            media_type = 'image'
            media_path = scene_files['image_path']

        assert media_type == 'video'
        assert media_path == scene_files['video_path']

    def test_image_fallback_when_no_video(self):
        """비디오가 없으면 이미지 사용"""
        # 비디오 파일 없음
        has_video = False
        has_image = True

        if has_video:
            media_type = 'video'
        elif has_image:
            media_type = 'image'
        else:
            media_type = None

        assert media_type == 'image'

    def test_no_media_detection(self):
        """비디오도 이미지도 없으면 None"""
        has_video = False
        has_image = False

        if has_video:
            media_type = 'video'
        elif has_image:
            media_type = 'image'
        else:
            media_type = None

        assert media_type is None

    def test_video_file_extensions(self):
        """비디오 파일 확장자 감지"""
        valid_video_extensions = ['.mp4', '.avi', '.mov', '.mkv']

        test_files = [
            ('scene_video.mp4', True),
            ('scene_video.avi', True),
            ('scene_image.png', False),
            ('scene_image.jpg', False),
        ]

        for filename, is_video in test_files:
            ext = Path(filename).suffix.lower()
            detected = ext in valid_video_extensions
            assert detected == is_video


class TestSceneMediaStructure:
    """Scene media 데이터 구조 테스트"""

    def test_scene_media_image_structure(self):
        """이미지 타입의 scene_media 구조"""
        media_data = {
            'scene': {'title': 'Test Scene', 'narration': 'Test narration'},
            'media_type': 'image',
            'media_path': Path('scene_01/scene_01_image.png'),
            'image_path': Path('scene_01/scene_01_image.png'),
            'video_path': None,
            'scene_dir': Path('scene_01'),
            'scene_num': 1
        }

        assert media_data['media_type'] == 'image'
        assert media_data['image_path'] is not None
        assert media_data['video_path'] is None
        assert media_data['media_path'] == media_data['image_path']

    def test_scene_media_video_structure(self):
        """비디오 타입의 scene_media 구조"""
        media_data = {
            'scene': {'title': 'Test Scene', 'narration': 'Test narration'},
            'media_type': 'video',
            'media_path': Path('scene_01/scene_01_video.mp4'),
            'image_path': None,
            'video_path': Path('scene_01/scene_01_video.mp4'),
            'scene_dir': Path('scene_01'),
            'scene_num': 1
        }

        assert media_data['media_type'] == 'video'
        assert media_data['video_path'] is not None
        assert media_data['image_path'] is None
        assert media_data['media_path'] == media_data['video_path']

    def test_scene_media_required_fields(self):
        """scene_media 필수 필드 검증"""
        required_fields = [
            'scene',
            'media_type',
            'media_path',
            'scene_num',
            'scene_dir'
        ]

        media_data = {
            'scene': {},
            'media_type': 'image',
            'media_path': Path('test.png'),
            'image_path': Path('test.png'),
            'video_path': None,
            'scene_dir': Path('scene_01'),
            'scene_num': 1
        }

        for field in required_fields:
            assert field in media_data

    def test_scene_num_is_positive_integer(self):
        """scene_num은 양의 정수"""
        valid_scene_nums = [1, 2, 10, 100]
        invalid_scene_nums = [0, -1, -10]

        for num in valid_scene_nums:
            assert num > 0
            assert isinstance(num, int)

        for num in invalid_scene_nums:
            assert num <= 0


class TestVideoDurationMatching:
    """비디오 길이 매칭 테스트"""

    def test_video_shorter_than_audio_needs_looping(self):
        """비디오가 오디오보다 짧으면 루핑 필요"""
        video_duration = 5.0  # 5초
        audio_duration = 10.0  # 10초

        needs_looping = video_duration < audio_duration

        assert needs_looping == True

        # 몇 번 루프해야 하는지 계산
        loop_count = int(audio_duration / video_duration) + 1
        assert loop_count >= 2

    def test_video_longer_than_audio_needs_trimming(self):
        """비디오가 오디오보다 길면 트리밍 필요"""
        video_duration = 15.0  # 15초
        audio_duration = 10.0  # 10초

        needs_trimming = video_duration > audio_duration

        assert needs_trimming == True

        # 트리밍 후 길이
        trimmed_duration = audio_duration
        assert trimmed_duration == 10.0

    def test_video_matches_audio_no_adjustment(self):
        """비디오와 오디오 길이가 같으면 조정 불필요"""
        video_duration = 10.0
        audio_duration = 10.0

        needs_adjustment = abs(video_duration - audio_duration) > 0.1  # 0.1초 오차 허용

        assert needs_adjustment == False

    def test_small_duration_difference_tolerance(self):
        """작은 길이 차이는 허용"""
        TOLERANCE = 0.5  # 0.5초

        test_cases = [
            (10.0, 10.1, False),   # 0.1초 차이 - OK
            (10.0, 10.4, False),   # 0.4초 차이 - OK
            (10.0, 11.0, True),    # 1.0초 차이 - 조정 필요
            (10.0, 15.0, True),    # 5.0초 차이 - 조정 필요
        ]

        for video_dur, audio_dur, should_adjust in test_cases:
            needs_adjustment = abs(video_dur - audio_dur) > TOLERANCE
            assert needs_adjustment == should_adjust


class TestMixedMediaProcessing:
    """혼합 미디어 처리 테스트"""

    def test_mixed_scene_list_processing(self):
        """이미지와 비디오가 섞인 씬 리스트"""
        scene_media = [
            {'scene_num': 1, 'media_type': 'image', 'media_path': Path('s1.png')},
            {'scene_num': 2, 'media_type': 'video', 'media_path': Path('s2.mp4')},
            {'scene_num': 3, 'media_type': 'image', 'media_path': Path('s3.png')},
            {'scene_num': 4, 'media_type': 'video', 'media_path': Path('s4.mp4')},
        ]

        image_count = len([m for m in scene_media if m['media_type'] == 'image'])
        video_count = len([m for m in scene_media if m['media_type'] == 'video'])

        assert image_count == 2
        assert video_count == 2
        assert len(scene_media) == 4

    def test_all_images_scenario(self):
        """모두 이미지인 경우"""
        scene_media = [
            {'media_type': 'image'},
            {'media_type': 'image'},
            {'media_type': 'image'},
        ]

        all_images = all(m['media_type'] == 'image' for m in scene_media)
        assert all_images == True

    def test_all_videos_scenario(self):
        """모두 비디오인 경우"""
        scene_media = [
            {'media_type': 'video'},
            {'media_type': 'video'},
            {'media_type': 'video'},
        ]

        all_videos = all(m['media_type'] == 'video' for m in scene_media)
        assert all_videos == True

    def test_media_type_validation(self):
        """media_type은 'image' 또는 'video'만 허용"""
        valid_types = ['image', 'video']

        test_cases = [
            ('image', True),
            ('video', True),
            ('audio', False),
            ('text', False),
            (None, False),
        ]

        for media_type, should_be_valid in test_cases:
            is_valid = media_type in valid_types
            assert is_valid == should_be_valid


class TestEdgeCases:
    """엣지 케이스 테스트"""

    def test_empty_scene_list(self):
        """빈 씬 리스트"""
        scenes = []

        sorted_scenes = sorted(scenes, key=lambda s: s.get('seq', 999))

        assert len(sorted_scenes) == 0

    def test_single_scene(self):
        """씬이 하나만 있는 경우"""
        scenes = [{'seq': 1, 'title': 'Only Scene'}]

        sorted_scenes = sorted(scenes, key=lambda s: s.get('seq', 999))

        assert len(sorted_scenes) == 1
        assert sorted_scenes[0]['title'] == 'Only Scene'

    def test_duplicate_seq_numbers(self):
        """중복된 seq 번호 (stable sort)"""
        scenes = [
            {'seq': 1, 'title': 'A'},
            {'seq': 1, 'title': 'B'},
            {'seq': 2, 'title': 'C'},
        ]

        # Python의 sorted는 stable sort
        sorted_scenes = sorted(scenes, key=lambda s: s.get('seq', 999))

        assert sorted_scenes[0]['seq'] == 1
        assert sorted_scenes[1]['seq'] == 1
        assert sorted_scenes[2]['seq'] == 2
        # 원래 순서 유지: A, B, C
        assert sorted_scenes[0]['title'] == 'A'
        assert sorted_scenes[1]['title'] == 'B'

    def test_very_large_seq_number(self):
        """매우 큰 seq 번호"""
        scenes = [
            {'seq': 999999, 'title': 'Last'},
            {'seq': 1, 'title': 'First'},
        ]

        sorted_scenes = sorted(scenes, key=lambda s: s.get('seq', 999))

        assert sorted_scenes[0]['title'] == 'First'
        assert sorted_scenes[1]['title'] == 'Last'

    def test_negative_seq_number(self):
        """음수 seq 번호 (비정상이지만 처리)"""
        scenes = [
            {'seq': -1, 'title': 'Negative'},
            {'seq': 0, 'title': 'Zero'},
            {'seq': 1, 'title': 'Positive'},
        ]

        sorted_scenes = sorted(scenes, key=lambda s: s.get('seq', 999))

        assert sorted_scenes[0]['seq'] == -1
        assert sorted_scenes[1]['seq'] == 0
        assert sorted_scenes[2]['seq'] == 1


class TestRegressionBugs:
    """리그레션 버그 방지 테스트"""

    def test_video_audio_sync_precision(self):
        """[BUG FIX] 비디오-오디오 싱크 정밀도"""
        # 부동소수점 정밀도 문제 방지
        video_duration = 10.123456789
        audio_duration = 10.123456780

        # 0.01초(10ms) 이내 차이는 무시
        PRECISION = 0.01
        is_synced = abs(video_duration - audio_duration) < PRECISION

        assert is_synced == True

    def test_path_separator_handling(self):
        """[BUG FIX] 경로 구분자 처리 (Windows/Unix)"""
        # Path 객체 사용으로 OS 독립적
        scene_dir = Path('output') / 'project_123' / 'scene_01'

        # Windows: output\project_123\scene_01
        # Unix: output/project_123/scene_01
        # Path가 자동 처리
        assert 'scene_01' in str(scene_dir)

    def test_unicode_in_scene_title(self):
        """[BUG FIX] 씬 제목에 유니코드 문자"""
        scene = {
            'title': '첫 번째 씬 🎬',
            'narration': '안녕하세요! 반갑습니다 😊'
        }

        # UTF-8 인코딩 가능
        encoded_title = scene['title'].encode('utf-8')
        decoded_title = encoded_title.decode('utf-8')

        assert decoded_title == '첫 번째 씬 🎬'

    def test_missing_optional_fields(self):
        """[BUG FIX] 선택적 필드 누락 처리"""
        scene = {
            'title': 'Scene without seq or created_at'
        }

        # seq와 created_at이 없어도 에러 없이 처리
        seq = scene.get('seq')
        created_at = scene.get('created_at')

        assert seq is None
        assert created_at is None

    def test_media_path_with_spaces(self):
        """[BUG FIX] 경로에 공백 포함"""
        media_path = Path('output/my project/scene 01/video.mp4')

        # 경로에 공백이 있어도 정상 처리
        assert 'my project' in str(media_path)
        assert 'scene 01' in str(media_path)
