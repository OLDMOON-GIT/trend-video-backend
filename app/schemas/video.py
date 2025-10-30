"""Video schemas."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class VideoCreateRequest(BaseModel):
    """Request to create a video."""
    story_id: Optional[int] = Field(None, description="Story ID to create video from")
    title: str = Field(..., description="Video title")
    aspect_ratio: str = Field(default="9:16", description="Video aspect ratio: 9:16, 16:9, or 1:1")
    voice: str = Field(default="ko-KR-SunHiNeural", description="TTS voice ID")
    add_subtitles: bool = Field(default=True, description="Add subtitles to video")


class VideoCreate(BaseModel):
    """Schema for creating a video record."""
    story_id: Optional[int] = None
    title: str
    aspect_ratio: str = "9:16"


class VideoResponse(BaseModel):
    """Video response schema."""
    id: int
    story_id: Optional[int] = None
    title: str
    file_path: Optional[str] = None
    duration: Optional[float] = None
    resolution: Optional[str] = None
    aspect_ratio: str
    file_size: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VideoStatusResponse(BaseModel):
    """Video status response."""
    video_id: int
    status: str
    progress: Optional[int] = Field(None, description="Progress percentage (0-100)")
    message: Optional[str] = None
    error: Optional[str] = None
