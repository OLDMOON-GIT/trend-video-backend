#!/usr/bin/env python3
"""
YouTube 업로드 CLI
프론트엔드에서 호출하는 명령행 인터페이스
"""
import argparse
import json
import sys
from pathlib import Path

from src.youtube.uploader import YouTubeUploader, VideoMetadata


def cmd_auth(args):
    """OAuth2 인증"""
    uploader = YouTubeUploader(
        credentials_path=Path(args.credentials),
        token_path=Path(args.token)
    )

    if uploader.authenticate():
        print(json.dumps({"success": True, "message": "인증 성공"}))
        return 0
    else:
        print(json.dumps({"success": False, "error": "인증 실패"}))
        return 1


def cmd_channel_info(args):
    """채널 정보 조회"""
    uploader = YouTubeUploader(
        credentials_path=Path(args.credentials),
        token_path=Path(args.token)
    )

    if not uploader.authenticate():
        print(json.dumps({"success": False, "error": "인증 실패"}))
        return 1

    channel_info = uploader.get_channel_info()
    if channel_info:
        print(json.dumps({"success": True, "channel": channel_info}))
        return 0
    else:
        print(json.dumps({"success": False, "error": "채널 정보 조회 실패"}))
        return 1


def cmd_upload(args):
    """비디오 업로드"""
    try:
        metadata_dict = json.loads(Path(args.metadata).read_text(encoding="utf-8"))
        metadata = VideoMetadata(
            title=metadata_dict["title"],
            description=metadata_dict.get("description", ""),
            tags=metadata_dict.get("tags", []),
            category_id=metadata_dict.get("category_id", "27"),
            privacy_status=metadata_dict.get("privacy_status", "unlisted"),
            publish_at=metadata_dict.get("publish_at"),
        )
    except Exception as e:
        print(json.dumps({"success": False, "error": f"메타데이터 로드 실패: {e}"}))
        return 1

    uploader = YouTubeUploader(
        credentials_path=Path(args.credentials),
        token_path=Path(args.token)
    )

    if not uploader.authenticate():
        print(json.dumps({"success": False, "error": "인증 실패"}))
        return 1

    result = uploader.upload_video(
        video_path=Path(args.video),
        metadata=metadata,
        thumbnail_path=Path(args.thumbnail) if args.thumbnail else None,
        captions_path=Path(args.captions) if args.captions else None,
        cancel_flag_path=Path(args.cancel_flag) if hasattr(args, 'cancel_flag') and args.cancel_flag else None,
    )

    if result.success:
        # 고정댓글 추가 (설명과 동일한 내용)
        comment_added = False
        if result.video_id and metadata.description:
            try:
                comment_added = uploader.add_pinned_comment(result.video_id, metadata.description)
                if comment_added:
                    print(f"[INFO] 고정댓글 추가 완료")
            except Exception as e:
                print(f"[WARN] 고정댓글 추가 실패 (업로드는 성공): {e}")

        print(json.dumps({
            "success": True,
            "video_id": result.video_id,
            "video_url": result.video_url,
            "comment_added": comment_added
        }))
        return 0
    else:
        print(json.dumps({"success": False, "error": result.error}))
        return 1


def main():
    parser = argparse.ArgumentParser(description="YouTube 업로드 CLI")
    parser.add_argument("--action", required=True, choices=["auth", "channel-info", "upload"])
    parser.add_argument("--credentials", default="config/youtube_client_secret.json")
    parser.add_argument("--token", default="config/youtube_token.json")
    parser.add_argument("--video", help="비디오 파일 경로")
    parser.add_argument("--metadata", help="메타데이터 JSON 파일")
    parser.add_argument("--thumbnail", help="썸네일 이미지")
    parser.add_argument("--captions", help="자막 파일")
    parser.add_argument("--cancel-flag", help="취소 플래그 파일 경로")
    args = parser.parse_args()

    if args.action == "auth":
        return cmd_auth(args)
    elif args.action == "channel-info":
        return cmd_channel_info(args)
    elif args.action == "upload":
        if not args.video or not args.metadata:
            print(json.dumps({"success": False, "error": "--video와 --metadata 필수"}))
            return 1
        return cmd_upload(args)


if __name__ == "__main__":
    sys.exit(main())
