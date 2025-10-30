"""Video API endpoints."""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
import os

from app.database import get_db
from app.schemas.video import (
    VideoCreateRequest,
    VideoResponse,
    VideoStatusResponse
)
from app.services.video_service import VideoService


router = APIRouter()


@router.post("/create", response_model=VideoResponse)
async def create_video(
    request: VideoCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Create a video from a story.

    This endpoint starts the video creation process and returns immediately.
    Use the /video/{video_id}/status endpoint to check progress.
    """
    service = VideoService(db)

    # Create video record
    video = service.create_video(
        story_id=request.story_id,
        title=request.title,
        aspect_ratio=request.aspect_ratio
    )

    # Start video generation in background
    background_tasks.add_task(
        service.generate_video,
        video.id,
        request.story_id,
        request.aspect_ratio,
        request.voice,
        request.add_subtitles
    )

    return video


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
async def get_video_status(video_id: int, db: Session = Depends(get_db)):
    """Get video creation status."""
    service = VideoService(db)
    video = service.get_video(video_id)

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    return VideoStatusResponse(
        video_id=video.id,
        status=video.status,
        message=f"Video is {video.status}",
        error=video.error_message
    )


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: int, db: Session = Depends(get_db)):
    """Get video details."""
    service = VideoService(db)
    video = service.get_video(video_id)

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    return video


@router.get("/{video_id}/download")
async def download_video(video_id: int, db: Session = Depends(get_db)):
    """Download video file."""
    service = VideoService(db)
    video = service.get_video(video_id)

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    if video.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"Video is not ready. Current status: {video.status}"
        )

    if not video.file_path or not os.path.exists(video.file_path):
        raise HTTPException(status_code=404, detail="Video file not found")

    return FileResponse(
        video.file_path,
        media_type="video/mp4",
        filename=f"{video.title}.mp4"
    )


@router.get("/", response_model=List[VideoResponse])
async def list_videos(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """List all videos with pagination."""
    service = VideoService(db)
    videos = service.list_videos(skip=skip, limit=limit)
    return videos


@router.delete("/{video_id}")
async def delete_video(video_id: int, db: Session = Depends(get_db)):
    """Delete a video."""
    service = VideoService(db)
    success = service.delete_video(video_id)

    if not success:
        raise HTTPException(status_code=404, detail="Video not found")

    return {"message": "Video deleted successfully"}
