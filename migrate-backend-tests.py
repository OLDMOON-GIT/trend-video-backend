#!/usr/bin/env python3
"""
Backend 테스트 파일을 __tests__ 디렉토리로 이동
tests/ 폴더의 test_*.py 파일들을 카테고리별로 분류하여 이동
"""

import os
import shutil
from pathlib import Path

# 프로젝트 루트
ROOT_DIR = Path(__file__).parent
TESTS_DIR = ROOT_DIR / 'tests'
TARGET_DIR = ROOT_DIR / '__tests__'

# 카테고리별 파일 매핑
FILE_MAPPINGS = {
    # API 테스트
    'tests/test_api_security.py': '__tests__/api/test_api_security.py',

    # 데이터베이스 테스트
    'tests/test_contents_table.py': '__tests__/database/test_contents_table.py',
    'tests/test_erd_tables.py': '__tests__/database/test_erd_tables.py',
    'tests/test_data_integrity.py': '__tests__/database/test_data_integrity.py',

    # 미디어/이미지 테스트
    'tests/test_image_crawler_integration.py': '__tests__/media/test_image_crawler_integration.py',
    'tests/test_media_scene_matching.py': '__tests__/media/test_media_scene_matching.py',
    'tests/test_media_sorting_regression.py': '__tests__/media/test_media_sorting_regression.py',
    'tests/test_unified_media_sorting.py': '__tests__/media/test_unified_media_sorting.py',

    # 비디오/씬 테스트
    'tests/test_scene_processing.py': '__tests__/video/test_scene_processing.py',
    'tests/test_video_generation.py': '__tests__/video/test_video_generation.py',

    # 회귀 테스트
    'tests/test_regression.py': '__tests__/regression/test_regression.py',
}

def move_file(source_rel, target_rel):
    """파일을 이동"""
    source = ROOT_DIR / source_rel
    target = ROOT_DIR / target_rel

    if not source.exists():
        return {'success': False, 'reason': '파일 없음'}

    # 타겟 디렉토리 생성
    target.parent.mkdir(parents=True, exist_ok=True)

    # 파일 이동
    shutil.move(str(source), str(target))
    return {'success': True}

def main():
    print('Backend test file migration started...\n')

    moved_count = 0
    skipped_count = 0

    # Categories
    categories = {
        'API Tests': [],
        'Database Tests': [],
        'Media/Image Tests': [],
        'Video/Scene Tests': [],
        'Regression Tests': [],
    }

    # Categorize files
    for source, target in FILE_MAPPINGS.items():
        if '/api/' in target:
            categories['API Tests'].append((source, target))
        elif '/database/' in target:
            categories['Database Tests'].append((source, target))
        elif '/media/' in target:
            categories['Media/Image Tests'].append((source, target))
        elif '/video/' in target:
            categories['Video/Scene Tests'].append((source, target))
        elif '/regression/' in target:
            categories['Regression Tests'].append((source, target))

    # Move files by category
    for category, files in categories.items():
        if not files:
            continue

        print(f'[{category}]:')
        for source, target in files:
            result = move_file(source, target)
            if result['success']:
                print(f'  OK: {source} -> {target}')
                moved_count += 1
            else:
                print(f'  SKIP: {source} ({result["reason"]})')
                skipped_count += 1
        print()

    # Create __init__.py files
    print('Creating __init__.py files:')
    init_dirs = [
        '__tests__',
        '__tests__/api',
        '__tests__/database',
        '__tests__/media',
        '__tests__/video',
        '__tests__/regression',
    ]

    for dir_path in init_dirs:
        init_file = ROOT_DIR / dir_path / '__init__.py'
        init_file.parent.mkdir(parents=True, exist_ok=True)
        if not init_file.exists():
            init_file.write_text('# Test module\n')
            print(f'  OK: {dir_path}/__init__.py')
    print()

    # Handle test data directories
    print('Copying test data directories:')
    for dir_name in ['test_data', 'test_output', 'output_test']:
        source_dir = TESTS_DIR / dir_name
        if source_dir.exists():
            target_dir = TARGET_DIR / dir_name
            if not target_dir.exists():
                shutil.copytree(source_dir, target_dir)
                print(f'  OK: {dir_name}/ copied')
    print()

    # Results
    print('=' * 60)
    print('Backend test migration completed!\n')
    print(f'Results:')
    print(f'   Moved: {moved_count} files')
    print(f'   Skipped: {skipped_count} files')
    print()
    print('Next steps:')
    print('   1. git status')
    print('   2. Run pytest to verify tests')
    print('   3. git add . && git commit')

if __name__ == '__main__':
    main()
