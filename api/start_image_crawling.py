"""
이미지 크롤링 시작 API (통합 버전)
자동화 및 내 콘텐츠 모두 지원
"""

from flask import Flask, request, jsonify
import subprocess
import os
import sys
import json
import threading

app = Flask(__name__)

# 진행 중인 크롤링 추적
crawling_status = {}


def run_crawling_async(script_id, use_imagefx, source):
    """비동기로 크롤링 실행"""
    try:
        # 상태 업데이트
        crawling_status[script_id] = {
            'status': 'processing',
            'progress': 0,
            'message': '이미지 생성 시작...'
        }

        # 통합 크롤러 경로
        crawler_path = os.path.join(
            os.path.dirname(__file__), '..', '..',
            'scripts', 'utils', 'image_crawler_unified.py'
        )

        # 명령어 구성
        cmd = [
            sys.executable,
            crawler_path,
            '--script-id', script_id,
            '--source', source
        ]

        if use_imagefx:
            cmd.append('--use-imagefx')

        print(f"🚀 크롤링 시작: {' '.join(cmd)}")

        # 프로세스 실행
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

        if result.returncode == 0:
            crawling_status[script_id] = {
                'status': 'completed',
                'progress': 100,
                'message': '이미지 생성 완료!'
            }
            print(f"✅ 크롤링 성공: {script_id}")
        else:
            error_msg = result.stderr or '알 수 없는 오류'
            crawling_status[script_id] = {
                'status': 'failed',
                'progress': 0,
                'message': f'오류: {error_msg}'
            }
            print(f"❌ 크롤링 실패: {error_msg}")

    except Exception as e:
        crawling_status[script_id] = {
            'status': 'failed',
            'progress': 0,
            'message': str(e)
        }
        print(f"❌ 예외 발생: {e}")


@app.route('/api/start-image-crawling', methods=['POST'])
def start_image_crawling():
    """
    이미지 크롤링 시작 엔드포인트

    Request Body:
        {
            "scriptId": "abc123",
            "useImageFX": true/false,
            "source": "automation" | "my-content"
        }

    Response:
        {
            "success": true,
            "message": "이미지 크롤링이 시작되었습니다",
            "taskId": "abc123"
        }
    """
    try:
        data = request.json
        script_id = data.get('scriptId')
        use_imagefx = data.get('useImageFX', False)
        source = data.get('source', 'unknown')

        if not script_id:
            return jsonify({
                'success': False,
                'message': 'scriptId가 필요합니다'
            }), 400

        # 이미 진행 중인지 확인
        if script_id in crawling_status and crawling_status[script_id]['status'] == 'processing':
            return jsonify({
                'success': False,
                'message': '이미 진행 중입니다'
            }), 409

        # 비동기 실행
        thread = threading.Thread(
            target=run_crawling_async,
            args=(script_id, use_imagefx, source)
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'message': f'이미지 크롤링이 시작되었습니다 (모드: {"ImageFX+Whisk" if use_imagefx else "Whisk"})',
            'taskId': script_id
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@app.route('/api/image-crawling-status/<script_id>', methods=['GET'])
def get_crawling_status(script_id):
    """
    크롤링 상태 조회

    Response:
        {
            "status": "processing" | "completed" | "failed",
            "progress": 50,
            "message": "진행 중..."
        }
    """
    if script_id not in crawling_status:
        # 완료 파일 확인
        backend_path = os.path.join(os.path.dirname(__file__), '..', '..')
        possible_paths = [
            os.path.join(backend_path, 'input', f'project_{script_id}', 'images', 'crawling_complete.json'),
            os.path.join(backend_path, 'output', f'project_{script_id}', 'images', 'crawling_complete.json'),
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return jsonify({
                    'status': 'completed',
                    'progress': 100,
                    'message': '이미지 생성 완료'
                })

        return jsonify({
            'status': 'pending',
            'progress': 0,
            'message': '대기 중'
        })

    return jsonify(crawling_status[script_id])


@app.route('/api/image-crawling-modes', methods=['GET'])
def get_crawling_modes():
    """
    사용 가능한 크롤링 모드 조회

    Response:
        {
            "modes": [
                {
                    "id": "whisk",
                    "name": "Whisk만 사용",
                    "description": "Whisk만 사용하여 이미지 생성 (빠르고 간단)",
                    "icon": "✨",
                    "default": true
                },
                {
                    "id": "imagefx-whisk",
                    "name": "ImageFX + Whisk",
                    "description": "첫 이미지를 ImageFX로 생성하여 일관된 인물 이미지 사용",
                    "icon": "🎨",
                    "default": false
                }
            ]
        }
    """
    return jsonify({
        'modes': [
            {
                'id': 'whisk',
                'name': 'Whisk만 사용',
                'description': 'Whisk만 사용하여 이미지 생성 (빠르고 간단)',
                'icon': '✨',
                'default': True
            },
            {
                'id': 'imagefx-whisk',
                'name': 'ImageFX + Whisk',
                'description': '첫 이미지를 ImageFX로 생성하여 일관된 인물 이미지 사용',
                'icon': '🎨',
                'default': False
            }
        ]
    })


if __name__ == '__main__':
    app.run(debug=True, port=5002)