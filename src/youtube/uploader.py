#!/usr/bin/env python3
"""YouTube 업로드 모듈 - Google YouTube Data API v3"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


@dataclass
class VideoMetadata:
    """비디오 메타데이터"""
    title: str
    description: str
    tags: List[str]
    category_id: str = "27"  # Education
    privacy_status: str = "unlisted"
    publish_at: Optional[str] = None


@dataclass
class UploadResult:
    """업로드 결과"""
    success: bool
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None


class YouTubeUploader:
    """YouTube 업로더"""

    def __init__(self, credentials_path: Path, token_path: Path):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.youtube = None

    def authenticate(self) -> bool:
        """OAuth2 인증"""
        try:
            creds: Credentials | None = None

            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), SCOPES
                    )
                    # OAuth 완료 후 창을 닫고 opener 새로고침
                    success_html = '''
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <title>YouTube 연결 완료</title>
                        <style>
                            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #1e293b; color: white; }
                            .container { max-width: 500px; margin: 0 auto; }
                            h1 { color: #10b981; margin-bottom: 20px; }
                            p { font-size: 18px; margin: 20px 0; }
                            .spinner { border: 4px solid #374151; border-top: 4px solid #8b5cf6; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 20px auto; }
                            @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                        </style>
                    </head>
                    <body>
                        <div class="container">
                            <h1>✅ YouTube 채널 연결 성공!</h1>
                            <p>인증이 완료되었습니다.</p>
                            <div class="spinner"></div>
                            <p>이 창은 자동으로 닫힙니다...</p>
                        </div>
                        <script>
                            // opener가 있으면 (새 창으로 열린 경우) opener 새로고침 후 창 닫기
                            if (window.opener) {
                                window.opener.location.reload();
                                setTimeout(function() {
                                    window.close();
                                }, 1000);
                            } else {
                                // opener가 없으면 (직접 접근한 경우) 리디렉션
                                setTimeout(function() {
                                    window.location.href = 'http://localhost:3000/settings/youtube?success=true';
                                }, 2000);
                            }
                        </script>
                    </body>
                    </html>
                    '''
                    creds = flow.run_local_server(
                        port=0,
                        success_message=success_html,
                        open_browser=True
                    )

                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                self.token_path.write_text(creds.to_json(), encoding="utf-8")

            self.youtube = build("youtube", "v3", credentials=creds)
            return True

        except Exception as e:
            print(f"[ERROR] 인증 실패: {e}")
            return False

    def get_channel_info(self) -> dict | None:
        """연결된 채널 정보 조회"""
        try:
            if not self.youtube:
                return None

            request = self.youtube.channels().list(
                part="snippet,contentDetails,statistics",
                mine=True
            )
            response = request.execute()

            if not response.get("items"):
                return None

            channel = response["items"][0]
            return {
                "id": channel["id"],
                "title": channel["snippet"]["title"],
                "description": channel["snippet"]["description"],
                "customUrl": channel["snippet"].get("customUrl"),
                "thumbnails": channel["snippet"]["thumbnails"],
                "subscriberCount": channel["statistics"].get("subscriberCount", "0"),
                "videoCount": channel["statistics"].get("videoCount", "0"),
                "viewCount": channel["statistics"].get("viewCount", "0"),
            }
        except Exception as e:
            print(f"[ERROR] 채널 정보 조회 실패: {e}")
            return None

    def upload_video(
        self,
        video_path: Path,
        metadata: VideoMetadata,
        thumbnail_path: Optional[Path] = None,
        captions_path: Optional[Path] = None,
        progress_callback=None,
    ) -> UploadResult:
        """비디오 업로드"""
        try:
            if not self.youtube:
                return UploadResult(success=False, error="인증이 필요합니다")

            if not video_path.exists():
                return UploadResult(success=False, error=f"비디오 파일을 찾을 수 없습니다: {video_path}")

            # 비디오 업로드
            body = {
                "snippet": {
                    "title": metadata.title,
                    "description": metadata.description,
                    "tags": metadata.tags,
                    "categoryId": metadata.category_id,
                },
                "status": {
                    "privacyStatus": metadata.privacy_status,
                },
            }

            if metadata.publish_at:
                body["status"]["publishAt"] = metadata.publish_at

            media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            print(f"[INFO] 업로드 시작: {video_path}")
            response = None
            video_id = None

            try:
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        print(f"[INFO] 업로드 진행률: {progress}%")
                        if progress_callback:
                            progress_callback(progress)

                # 업로드 완료 - video_id 저장
                if response and "id" in response:
                    video_id = response["id"]
                    video_url = f"https://youtu.be/{video_id}"
                    print(f"[INFO] 업로드 완료: {video_url}")
                else:
                    raise Exception("업로드 완료되었으나 video_id를 받지 못했습니다")
            except KeyboardInterrupt:
                print("[WARN] 업로드 취소 요청 감지")
                # 업로드가 완료되어 video_id가 있으면 YouTube에서 삭제
                if video_id:
                    try:
                        print(f"[INFO] YouTube에서 비디오 삭제 중: {video_id}")
                        self.youtube.videos().delete(id=video_id).execute()
                        print(f"[INFO] YouTube 비디오 삭제 완료: {video_id}")
                    except Exception as delete_error:
                        print(f"[ERROR] YouTube 비디오 삭제 실패: {delete_error}")
                raise  # KeyboardInterrupt 다시 발생시켜서 상위로 전파

            # 썸네일 업로드 (재시도 로직 포함)
            if thumbnail_path and thumbnail_path.exists():
                import time
                max_retries = 5
                retry_delay = 3  # 3초 대기

                # YouTube가 비디오를 인식하도록 초기 대기
                print("[INFO] 썸네일 업로드 준비 중 (5초 대기)...")
                time.sleep(5)

                for attempt in range(max_retries):
                    try:
                        if attempt > 0:
                            print(f"[INFO] 썸네일 업로드 재시도 {attempt + 1}/{max_retries} (2초 후)...")
                            time.sleep(retry_delay)

                        media = MediaFileUpload(str(thumbnail_path))
                        self.youtube.thumbnails().set(
                            videoId=video_id,
                            media_body=media
                        ).execute()
                        print("[INFO] 썸네일 업로드 완료")
                        break
                    except Exception as e:
                        error_msg = str(e)
                        if "videoNotFound" in error_msg and attempt < max_retries - 1:
                            print(f"[WARN] 비디오 처리 중... 재시도 대기")
                        elif attempt < max_retries - 1:
                            print(f"[WARN] 썸네일 업로드 실패 (재시도 예정): {e}")
                        else:
                            print(f"[WARN] 썸네일 업로드 최종 실패: {e}")

            # 자막 업로드
            if captions_path and captions_path.exists():
                try:
                    caption_body = {
                        "snippet": {
                            "videoId": video_id,
                            "language": "ko",
                            "name": "Korean",
                            "isDraft": False,
                        }
                    }
                    media = MediaFileUpload(str(captions_path), mimetype="application/octet-stream")
                    self.youtube.captions().insert(
                        part="snippet",
                        body=caption_body,
                        media_body=media,
                        sync=True
                    ).execute()
                    print("[INFO] 자막 업로드 완료")
                except Exception as e:
                    print(f"[WARN] 자막 업로드 실패: {e}")

            return UploadResult(
                success=True,
                video_id=video_id,
                video_url=video_url
            )

        except HttpError as exc:
            error_msg = f"YouTube API 에러: {exc}"
            print(f"[ERROR] {error_msg}")
            return UploadResult(success=False, error=error_msg)

        except Exception as e:
            error_msg = f"업로드 실패: {e}"
            print(f"[ERROR] {error_msg}")
            return UploadResult(success=False, error=error_msg)
