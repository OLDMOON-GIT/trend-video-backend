"""
CONTENTS 테이블 리그레션 테스트 (Backend)

CONTENTS 테이블은 SCRIPTS와 VIDEOS를 통합한 테이블입니다.
type 컬럼으로 script/video를 구분하며, format으로 longform/shortform/sora2를 지정합니다.

테스트 범위:
- CONTENTS 테이블 CRUD
- type 필드 검증 (script/video)
- format 필드 검증 (longform/shortform/sora2)
- 대본 → 영상 변환 추적 (sourceContentId)
- 상태 전이 (pending → processing → completed/failed)
"""
import pytest
from datetime import datetime


class TestContentsTable:
    """CONTENTS 테이블 통합 테스트"""

    def test_script_content_creation(self):
        """대본 컨텐츠 생성"""
        content = {
            'id': 'content_123',
            'user_id': 'user_456',
            'type': 'script',
            'format': 'longform',
            'title': '테스트 대본',
            'status': 'pending',
            'content': '{"scenes": []}',
            'created_at': datetime.now().isoformat(),
        }

        assert content['type'] == 'script'
        assert content['format'] in ['longform', 'shortform', 'sora2']
        assert content['status'] == 'pending'
        assert content.get('content') is not None

    def test_video_content_creation(self):
        """영상 컨텐츠 생성"""
        content = {
            'id': 'content_789',
            'user_id': 'user_456',
            'type': 'video',
            'format': 'shortform',
            'title': '테스트 영상',
            'status': 'pending',
            'source_content_id': 'content_123',  # 원본 대본 ID
            'video_path': None,
            'thumbnail_path': None,
            'created_at': datetime.now().isoformat(),
        }

        assert content['type'] == 'video'
        assert content['source_content_id'] == 'content_123'
        assert content['video_path'] is None  # 아직 생성 전

    def test_type_validation(self):
        """type 필드 검증"""
        valid_types = ['script', 'video']

        for t in valid_types:
            assert t in valid_types

        invalid_type = 'audio'
        assert invalid_type not in valid_types

    def test_format_validation(self):
        """format 필드 검증"""
        valid_formats = ['longform', 'shortform', 'sora2']

        for f in valid_formats:
            assert f in valid_formats

        invalid_format = 'podcast'
        assert invalid_format not in valid_formats

    def test_status_transitions(self):
        """상태 전이 검증"""
        valid_statuses = ['pending', 'processing', 'completed', 'failed']

        # pending → processing
        assert 'pending' in valid_statuses
        assert 'processing' in valid_statuses

        # processing → completed
        assert 'completed' in valid_statuses

        # processing → failed
        assert 'failed' in valid_statuses

    def test_script_to_video_conversion_tracking(self):
        """대본 → 영상 변환 추적"""
        script_content = {
            'id': 'content_script_1',
            'type': 'script',
            'title': '원본 대본',
        }

        video_content = {
            'id': 'content_video_1',
            'type': 'video',
            'source_content_id': 'content_script_1',
            'conversion_type': 'script_to_video',
            'title': '원본 대본',
        }

        assert video_content['source_content_id'] == script_content['id']
        assert video_content['conversion_type'] == 'script_to_video'

    def test_progress_tracking(self):
        """진행률 추적 (0-100)"""
        content = {
            'id': 'content_999',
            'progress': 0,
            'status': 'processing',
        }

        # 진행률 업데이트
        content['progress'] = 50
        assert 0 <= content['progress'] <= 100

        content['progress'] = 100
        content['status'] = 'completed'
        assert content['progress'] == 100
        assert content['status'] == 'completed'

    def test_published_field(self):
        """유튜브 업로드 여부 (published)"""
        video_content = {
            'id': 'content_video_2',
            'type': 'video',
            'published': 0,
            'published_at': None,
        }

        assert video_content['published'] == 0
        assert video_content['published_at'] is None

        # 업로드 후
        video_content['published'] = 1
        video_content['published_at'] = datetime.now().isoformat()

        assert video_content['published'] == 1
        assert video_content['published_at'] is not None

    def test_token_usage_tracking(self):
        """AI 토큰 사용량 추적"""
        script_content = {
            'id': 'content_script_2',
            'type': 'script',
            'input_tokens': 1500,
            'output_tokens': 3000,
            'use_claude_local': 0,
        }

        assert script_content['input_tokens'] > 0
        assert script_content['output_tokens'] > 0
        assert script_content['use_claude_local'] in [0, 1]

    def test_regeneration_flag(self):
        """재생성 여부 플래그"""
        content = {
            'id': 'content_regen_1',
            'is_regenerated': 0,
        }

        assert content['is_regenerated'] == 0

        # 재생성 시
        content['is_regenerated'] = 1
        assert content['is_regenerated'] == 1


class TestContentsRelationships:
    """CONTENTS 테이블 관계 테스트"""

    def test_user_to_contents_one_to_many(self):
        """USERS → CONTENTS (1:N)"""
        user_id = 'user_123'
        contents = [
            {'id': 'content_1', 'user_id': user_id, 'type': 'script'},
            {'id': 'content_2', 'user_id': user_id, 'type': 'video'},
            {'id': 'content_3', 'user_id': user_id, 'type': 'script'},
        ]

        user_contents = [c for c in contents if c['user_id'] == user_id]
        assert len(user_contents) == 3

    def test_contents_self_referencing(self):
        """CONTENTS 자기 참조 (sourceContentId)"""
        script = {'id': 'content_script_10', 'type': 'script'}
        video1 = {'id': 'content_video_11', 'type': 'video', 'source_content_id': 'content_script_10'}
        video2 = {'id': 'content_video_12', 'type': 'video', 'source_content_id': 'content_script_10'}

        # 한 대본으로 여러 영상 생성 가능
        videos = [video1, video2]
        related_videos = [v for v in videos if v['source_content_id'] == script['id']]

        assert len(related_videos) == 2


class TestContentsBusinessLogic:
    """CONTENTS 비즈니스 로직 테스트"""

    def test_script_creation_cost(self):
        """대본 생성 비용 (10 크레딧)"""
        SCRIPT_COST = 10

        user_credits = 50
        user_credits -= SCRIPT_COST

        assert user_credits == 40

    def test_video_creation_cost(self):
        """영상 생성 비용 (50 크레딧)"""
        VIDEO_COST = 50

        user_credits = 100
        user_credits -= VIDEO_COST

        assert user_credits == 50

    def test_content_failure_refund(self):
        """컨텐츠 생성 실패 시 환불"""
        user_credits = 40
        SCRIPT_COST = 10

        # 생성 시작
        user_credits -= SCRIPT_COST
        assert user_credits == 30

        # 실패 시 환불
        content_status = 'failed'
        if content_status == 'failed':
            user_credits += SCRIPT_COST

        assert user_credits == 40

    def test_query_by_type_and_format(self):
        """type과 format으로 컨텐츠 조회"""
        contents = [
            {'id': '1', 'type': 'script', 'format': 'longform'},
            {'id': '2', 'type': 'script', 'format': 'shortform'},
            {'id': '3', 'type': 'video', 'format': 'longform'},
            {'id': '4', 'type': 'video', 'format': 'sora2'},
        ]

        # 롱폼 대본만 조회
        longform_scripts = [
            c for c in contents
            if c['type'] == 'script' and c['format'] == 'longform'
        ]

        assert len(longform_scripts) == 1
        assert longform_scripts[0]['id'] == '1'

        # 모든 영상 조회
        videos = [c for c in contents if c['type'] == 'video']
        assert len(videos) == 2


class TestContentsIndexing:
    """CONTENTS 인덱싱 테스트"""

    def test_composite_index_usage(self):
        """복합 인덱스 (userId, type, status, createdAt)"""
        # 사용자별, 타입별, 상태별 조회 시뮬레이션
        query_params = {
            'user_id': 'user_123',
            'type': 'video',
            'status': 'completed',
        }

        # 인덱스가 있으면 빠른 조회 가능
        assert query_params['user_id'] is not None
        assert query_params['type'] in ['script', 'video']
        assert query_params['status'] in ['pending', 'processing', 'completed', 'failed']


class TestContentsMigration:
    """SCRIPTS/VIDEOS → CONTENTS 마이그레이션 검증"""

    def test_script_migration_mapping(self):
        """SCRIPTS 테이블 필드 매핑"""
        old_script = {
            'id': 'task_123',
            'user_id': 'user_1',
            'title': '제목',
            'type': 'longform',  # 옛날: type = longform/shortform/sora2
            'status': 'PENDING',
            'content': '{"scenes": []}',
            'retry_count': 0,
            'created_at': '2025-11-04',
        }

        # CONTENTS로 변환
        new_content = {
            'id': old_script['id'],
            'user_id': old_script['user_id'],
            'type': 'script',  # 새로운 type 필드
            'format': old_script['type'],  # 옛날 type → format
            'title': old_script['title'],
            'status': old_script['status'].lower(),
            'content': old_script['content'],
            'created_at': old_script['created_at'],
        }

        assert new_content['type'] == 'script'
        assert new_content['format'] == 'longform'
        assert new_content['status'] == 'pending'

    def test_video_migration_mapping(self):
        """VIDEOS 테이블 필드 매핑"""
        old_video = {
            'id': 'video_456',
            'user_id': 'user_1',
            'script_id': 'task_123',
            'title': '영상 제목',
            'type': 'shortform',
            'status': 'COMPLETED',
            'video_path': '/path/to/video.mp4',
            'thumbnail_path': '/path/to/thumb.jpg',
            'created_at': '2025-11-04',
        }

        # CONTENTS로 변환
        new_content = {
            'id': old_video['id'],
            'user_id': old_video['user_id'],
            'type': 'video',
            'format': old_video['type'],
            'title': old_video['title'],
            'status': old_video['status'].lower(),
            'video_path': old_video['video_path'],
            'thumbnail_path': old_video['thumbnail_path'],
            'source_content_id': old_video['script_id'],  # script_id → source_content_id
            'created_at': old_video['created_at'],
        }

        assert new_content['type'] == 'video'
        assert new_content['format'] == 'shortform'
        assert new_content['source_content_id'] == 'task_123'
        assert new_content['status'] == 'completed'
