#!/usr/bin/env python3
"""
YouTube Video Management CLI
- Update video privacy (public/private/unlisted)
- Delete video
"""

import argparse
import json
import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def load_credentials(token_path: str):
    """토큰 파일에서 인증 정보 로드"""
    if not os.path.exists(token_path):
        raise FileNotFoundError(f"토큰 파일을 찾을 수 없습니다: {token_path}")

    with open(token_path, 'r') as f:
        token_data = json.load(f)

    credentials = Credentials(
        token=token_data.get('access_token'),
        refresh_token=token_data.get('refresh_token'),
        token_uri='https://oauth2.googleapis.com/token',
        client_id=token_data.get('client_id'),
        client_secret=token_data.get('client_secret'),
        scopes=['https://www.googleapis.com/auth/youtube']
    )

    return credentials

def get_youtube_service(token_path: str):
    """YouTube API 서비스 객체 생성"""
    credentials = load_credentials(token_path)
    return build('youtube', 'v3', credentials=credentials)

def update_privacy(youtube, video_id: str, privacy: str):
    """비디오 공개 설정 변경"""
    try:
        # 현재 비디오 정보 가져오기
        video_response = youtube.videos().list(
            part='status,snippet',
            id=video_id
        ).execute()

        if not video_response.get('items'):
            return {'success': False, 'error': f'비디오를 찾을 수 없습니다: {video_id}'}

        video = video_response['items'][0]
        old_privacy = video['status']['privacyStatus']

        # 공개 설정 업데이트
        update_response = youtube.videos().update(
            part='status',
            body={
                'id': video_id,
                'status': {
                    'privacyStatus': privacy,
                    'selfDeclaredMadeForKids': video['status'].get('selfDeclaredMadeForKids', False)
                }
            }
        ).execute()

        return {
            'success': True,
            'video_id': video_id,
            'old_privacy': old_privacy,
            'new_privacy': privacy,
            'title': video['snippet']['title']
        }

    except HttpError as e:
        error_content = json.loads(e.content.decode('utf-8'))
        return {
            'success': False,
            'error': error_content.get('error', {}).get('message', str(e))
        }

def delete_video(youtube, video_id: str):
    """비디오 삭제"""
    try:
        # 삭제 전 비디오 정보 가져오기 (제목 확인용)
        video_response = youtube.videos().list(
            part='snippet',
            id=video_id
        ).execute()

        title = 'Unknown'
        if video_response.get('items'):
            title = video_response['items'][0]['snippet']['title']

        # 비디오 삭제
        youtube.videos().delete(id=video_id).execute()

        return {
            'success': True,
            'video_id': video_id,
            'title': title,
            'message': '비디오가 삭제되었습니다'
        }

    except HttpError as e:
        error_content = json.loads(e.content.decode('utf-8'))
        return {
            'success': False,
            'error': error_content.get('error', {}).get('message', str(e))
        }

def get_video_info(youtube, video_id: str):
    """비디오 정보 조회"""
    try:
        video_response = youtube.videos().list(
            part='snippet,status,statistics',
            id=video_id
        ).execute()

        if not video_response.get('items'):
            return {'success': False, 'error': f'비디오를 찾을 수 없습니다: {video_id}'}

        video = video_response['items'][0]
        return {
            'success': True,
            'video_id': video_id,
            'title': video['snippet']['title'],
            'description': video['snippet']['description'][:200] + '...' if len(video['snippet']['description']) > 200 else video['snippet']['description'],
            'privacy': video['status']['privacyStatus'],
            'published_at': video['snippet']['publishedAt'],
            'view_count': video['statistics'].get('viewCount', 0),
            'like_count': video['statistics'].get('likeCount', 0),
            'comment_count': video['statistics'].get('commentCount', 0)
        }

    except HttpError as e:
        error_content = json.loads(e.content.decode('utf-8'))
        return {
            'success': False,
            'error': error_content.get('error', {}).get('message', str(e))
        }

def main():
    parser = argparse.ArgumentParser(description='YouTube Video Management CLI')
    parser.add_argument('--token', required=True, help='YouTube OAuth 토큰 파일 경로')
    parser.add_argument('--video-id', required=True, help='YouTube 비디오 ID')
    parser.add_argument('--action', required=True, choices=['update-privacy', 'delete', 'info'], help='수행할 작업')
    parser.add_argument('--privacy', choices=['public', 'private', 'unlisted'], help='공개 설정 (update-privacy 시 필수)')

    args = parser.parse_args()

    try:
        youtube = get_youtube_service(args.token)

        if args.action == 'update-privacy':
            if not args.privacy:
                print(json.dumps({'success': False, 'error': '--privacy 옵션이 필요합니다'}))
                sys.exit(1)
            result = update_privacy(youtube, args.video_id, args.privacy)

        elif args.action == 'delete':
            result = delete_video(youtube, args.video_id)

        elif args.action == 'info':
            result = get_video_info(youtube, args.video_id)

        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result.get('success') else 1)

    except FileNotFoundError as e:
        print(json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__':
    main()
