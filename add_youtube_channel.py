#!/usr/bin/env python3
"""
YouTube 채널을 수동으로 DB에 추가하는 스크립트
OAuth 플로우가 완료된 후, 토큰 파일을 이용해 채널 정보를 DB에 저장
"""
import json
import sys
from pathlib import Path

# YouTube CLI import
from src.youtube.uploader import YouTubeUploader

def main():
    if len(sys.argv) < 3:
        print("사용법: python add_youtube_channel.py <user_id> <temp_token_filename>")
        print("예시: python add_youtube_channel.py b5d1f064-60b9-45ab-9bcd-d36948196459 youtube_token_temp_123.json")
        sys.exit(1)

    user_id = sys.argv[1]
    temp_token_file = sys.argv[2]

    # 경로 설정
    config_dir = Path("config")
    credentials_path = config_dir / "youtube_client_secret.json"
    temp_token_path = config_dir / temp_token_file

    if not credentials_path.exists():
        print(f"[ERROR] Credentials 파일이 없습니다: {credentials_path}")
        sys.exit(1)

    if not temp_token_path.exists():
        print(f"[ERROR] 토큰 파일이 없습니다: {temp_token_path}")
        sys.exit(1)

    # YouTube uploader로 채널 정보 가져오기
    uploader = YouTubeUploader(credentials_path, temp_token_path)

    if not uploader.authenticate():
        print("[ERROR] 인증 실패")
        sys.exit(1)

    channel_info = uploader.get_channel_info()

    if not channel_info:
        print("[ERROR] 채널 정보 조회 실패")
        sys.exit(1)

    print(f"[OK] 채널 정보 조회 성공:")
    print(f"  - 채널 ID: {channel_info['id']}")
    print(f"  - 채널 이름: {channel_info['title']}")
    print(f"  - 구독자 수: {channel_info.get('subscriber_count', 0):,}명")

    # 최종 토큰 파일 경로
    channel_id = channel_info['id']
    final_token_filename = f"youtube_token_{user_id}_{channel_id}.json"
    final_token_path = config_dir / final_token_filename

    # 토큰 파일 이동
    temp_token_path.rename(final_token_path)
    print(f"[OK] 토큰 파일 이동: {temp_token_file} → {final_token_filename}")

    # DB에 채널 정보 추가
    frontend_data_dir = Path("../trend-video-frontend/data")
    channels_file = frontend_data_dir / "youtube_channels.json"

    # 기존 채널 목록 읽기
    if channels_file.exists():
        with open(channels_file, 'r', encoding='utf-8') as f:
            channels = json.load(f)
    else:
        channels = []

    # 중복 확인
    existing = [ch for ch in channels if ch['userId'] == user_id and ch['channelId'] == channel_id]
    if existing:
        print(f"[WARNING]  이미 연결된 채널입니다")
        sys.exit(0)

    # 새 채널 추가
    import uuid
    from datetime import datetime

    new_channel = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "channelId": channel_id,
        "channelTitle": channel_info['title'],
        "thumbnailUrl": channel_info.get('thumbnail_url'),
        "subscriberCount": channel_info.get('subscriber_count', 0),
        "description": channel_info.get('description', ''),
        "tokenFile": final_token_filename,
        "isDefault": len([ch for ch in channels if ch['userId'] == user_id]) == 0,  # 첫 채널이면 기본
        "createdAt": datetime.now().isoformat(),
        "updatedAt": datetime.now().isoformat()
    }

    channels.append(new_channel)

    # DB 저장
    with open(channels_file, 'w', encoding='utf-8') as f:
        json.dump(channels, f, indent=2, ensure_ascii=False)

    print(f"[OK] DB에 채널 정보 저장 완료!")
    if new_channel['isDefault']:
        print(f"   (기본 채널로 설정됨)")

    print(f"\n[SUCCESS] 완료! 이제 웹사이트를 새로고침하면 채널이 표시됩니다.")

if __name__ == "__main__":
    main()
