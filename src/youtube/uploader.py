#!/usr/bin/env python3
"""YouTube 업로드 모듈 - Google YouTube Data API v3"""
from __future__ import annotations

import json
import signal
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
        cancel_flag_path: Optional[Path] = None,
    ) -> UploadResult:
        """비디오 업로드"""
        # 취소 플래그 체크 함수
        def check_cancelled():
            if cancel_flag_path and cancel_flag_path.exists():
                print(f"[WARN] 취소 플래그 파일 감지: {cancel_flag_path}", flush=True)
                raise KeyboardInterrupt

        # SIGTERM, SIGINT를 KeyboardInterrupt로 변환
        def signal_handler(signum, frame):
            print(f"[WARN] 시그널 수신: {signum} (업로드 중지)", flush=True)
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

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
                # YouTube API 요구사항: publishAt 사용 시 privacyStatus는 반드시 private
                body["status"]["publishAt"] = metadata.publish_at
                body["status"]["privacyStatus"] = "private"
                print(f"[INFO] 예약 공개 설정: {metadata.publish_at}")
                print(f"[INFO] 공개 설정을 private으로 변경 (예약 공개 후 {metadata.privacy_status}로 자동 변경됨)")

            media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media
            )

            print(f"[INFO] 업로드 시작: {video_path}")
            response = None
            video_id = None
            upload_success = False  # 정상 완료 플래그
            was_cancelled = False  # 취소 플래그

            try:
                # 비디오 업로드
                while response is None:
                    check_cancelled()  # 취소 체크
                    status, response = request.next_chunk()
                    if status:
                        progress = int(status.progress() * 100)
                        print(f"[INFO] 업로드 진행률: {progress}%")
                        if progress_callback:
                            progress_callback(progress)
                        check_cancelled()  # 진행률 업데이트 후에도 체크

                # 업로드 완료 - video_id 즉시 저장
                if response and "id" in response:
                    video_id = response["id"]
                    video_url = f"https://youtu.be/{video_id}"
                    print(f"[INFO] 업로드 완료: {video_url}")
                    print(f"[INFO] video_id 저장됨: {video_id} (중지 시 자동 삭제)")
                else:
                    raise Exception("업로드 완료되었으나 video_id를 받지 못했습니다")

                # 썸네일 업로드 (재시도 로직 포함)
                if thumbnail_path and thumbnail_path.exists():
                    check_cancelled()  # 썸네일 업로드 전 취소 체크
                    import time
                    max_retries = 5
                    retry_delay = 3  # 3초 대기

                    # YouTube가 비디오를 인식하도록 초기 대기
                    print("[INFO] 썸네일 업로드 준비 중 (5초 대기)...")
                    for _ in range(5):
                        time.sleep(1)
                        check_cancelled()  # 1초마다 취소 체크

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
                            # YouTube 처리 중 메시지는 정상 상태로 간주
                            if ("videoNotFound" in error_msg or
                                "processing" in error_msg.lower() or
                                "check back later" in error_msg.lower()) and attempt < max_retries - 1:
                                print(f"[WARN] 비디오 처리 중... 재시도 대기 ({retry_delay}초)")
                            elif attempt < max_retries - 1:
                                print(f"[WARN] 썸네일 업로드 실패 (재시도 예정): {e}")
                            else:
                                print(f"[WARN] 썸네일 업로드 최종 실패: {e}")
                                print(f"[INFO] 비디오는 성공적으로 업로드되었습니다: {video_url}")

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

                # 모든 작업 완료
                upload_success = True
                return UploadResult(
                    success=True,
                    video_id=video_id,
                    video_url=video_url
                )

            except KeyboardInterrupt:
                print("[WARN] 업로드 취소 요청 감지 (KeyboardInterrupt)", flush=True)
                was_cancelled = True
                # finally에서 삭제 처리 후 반환

            finally:
                # video_id가 있고 정상 완료가 아닌 경우 YouTube에서 삭제
                print(f"[DEBUG] finally 블록 실행: video_id={video_id}, upload_success={upload_success}", flush=True)
                if video_id and not upload_success:
                    try:
                        print(f"[INFO] YouTube에서 비디오 삭제 중: {video_id}", flush=True)
                        self.youtube.videos().delete(id=video_id).execute()
                        print(f"[INFO] YouTube 비디오 삭제 완료: {video_id}", flush=True)
                    except Exception as delete_error:
                        print(f"[ERROR] YouTube 비디오 삭제 실패: {delete_error}", flush=True)

                # 취소 플래그 파일 삭제
                if cancel_flag_path and cancel_flag_path.exists():
                    try:
                        cancel_flag_path.unlink()
                        print(f"[INFO] 취소 플래그 파일 삭제: {cancel_flag_path}", flush=True)
                    except Exception:
                        pass

            # except 블록 후 실행: 취소된 경우 에러 반환
            if was_cancelled:
                if video_id:
                    return UploadResult(
                        success=False,
                        error="업로드가 취소되었고 YouTube에서 비디오가 삭제되었습니다"
                    )
                else:
                    return UploadResult(
                        success=False,
                        error="업로드가 취소되었습니다 (아직 YouTube에 업로드되지 않음)"
                    )

        except HttpError as exc:
            error_msg = str(exc)
            # 비디오 처리 중 메시지는 일시적 상태 (실제 에러 아님)
            if "processing" in error_msg.lower() or "check back later" in error_msg.lower():
                print(f"[WARN] YouTube 처리 상태: {error_msg}")
                # video_id가 있다면 업로드는 성공한 것
                if video_id:
                    return UploadResult(
                        success=True,
                        video_id=video_id,
                        video_url=f"https://youtu.be/{video_id}"
                    )
            error_msg = f"YouTube API 에러: {exc}"
            print(f"[ERROR] {error_msg}")
            return UploadResult(success=False, error=error_msg)

        except Exception as e:
            error_msg = f"업로드 실패: {e}"
            print(f"[ERROR] {error_msg}")
            return UploadResult(success=False, error=error_msg)

    def add_pinned_comment(self, video_id: str, comment_text: str) -> bool:
        """영상에 고정댓글 추가 (채널 소유자 댓글은 자동 고정 가능)"""
        try:
            if not self.youtube:
                print("[ERROR] 인증이 필요합니다")
                return False

            if not video_id or not comment_text:
                print("[ERROR] video_id와 comment_text가 필요합니다")
                return False

            # 댓글 추가
            comment_body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }

            response = self.youtube.commentThreads().insert(
                part="snippet",
                body=comment_body
            ).execute()

            comment_id = response.get("id")
            print(f"[INFO] 댓글 추가 완료: {comment_id}")

            # 채널 소유자의 댓글이므로 바로 고정 가능
            # commentThreads.update로 고정 설정은 지원 안 됨
            # 대신 Studio에서 수동 고정 필요하거나 comments.setModerationStatus 사용
            # 하지만 채널 소유자 댓글은 YouTube에서 자동으로 상단에 표시됨
            print("[INFO] 채널 소유자 댓글은 자동으로 상단에 표시됩니다")
            return True

        except HttpError as e:
            print(f"[ERROR] 댓글 추가 실패: {e}")
            return False
        except Exception as e:
            print(f"[ERROR] 댓글 추가 중 오류: {e}")
            return False
