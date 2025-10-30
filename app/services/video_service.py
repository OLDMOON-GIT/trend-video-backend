"""Video generation service."""

import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from pathlib import Path
import os

from app.models.video import Video
from app.models.story import Story
from app.config import settings


logger = logging.getLogger(__name__)


class VideoService:
    """Service for video generation and management."""

    def __init__(self, db: Session):
        self.db = db

    def create_video(
        self,
        title: str,
        story_id: Optional[int] = None,
        aspect_ratio: str = "9:16",
        status: str = "pending"
    ) -> Video:
        """Create a new video record."""
        video = Video(
            story_id=story_id,
            title=title,
            aspect_ratio=aspect_ratio,
            status=status
        )
        self.db.add(video)
        self.db.commit()
        self.db.refresh(video)
        return video

    def get_video(self, video_id: int) -> Optional[Video]:
        """Get a video by ID."""
        return self.db.query(Video).filter(Video.id == video_id).first()

    def list_videos(self, skip: int = 0, limit: int = 20) -> List[Video]:
        """List videos with pagination."""
        return self.db.query(Video).offset(skip).limit(limit).all()

    def delete_video(self, video_id: int) -> bool:
        """Delete a video and its file."""
        video = self.get_video(video_id)
        if not video:
            return False

        # Delete video file if exists
        if video.file_path and os.path.exists(video.file_path):
            try:
                os.remove(video.file_path)
            except Exception as e:
                logger.warning(f"Failed to delete video file: {e}")

        self.db.delete(video)
        self.db.commit()
        return True

    def generate_video(
        self,
        video_id: int,
        story_id: Optional[int],
        aspect_ratio: str,
        voice: str,
        add_subtitles: bool
    ):
        """
        Generate video from story.

        This is a placeholder implementation.
        Actual implementation would use AutoShortsEditor logic.
        """
        try:
            logger.info(f"Starting video generation for video_id={video_id}")

            # Update status
            video = self.get_video(video_id)
            if not video:
                logger.error(f"Video not found: {video_id}")
                return

            video.status = "processing"
            self.db.commit()

            # Get story data
            if story_id:
                story = self.db.query(Story).filter(Story.id == story_id).first()
                if not story or not story.story_data:
                    raise ValueError(f"Story not found or has no data: {story_id}")

                story_data = story.story_data
            else:
                raise ValueError("Story ID is required")

            # TODO: Implement actual video generation
            # This would integrate with the AutoShortsEditor code:
            # 1. Generate images for each scene
            # 2. Generate audio narration
            # 3. Create video clips
            # 4. Add subtitles if requested
            # 5. Combine into final video

            # For now, just mark as completed
            output_path = Path(settings.output_path) / f"video_{video_id}.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Placeholder: In real implementation, create actual video
            # output_path.touch()

            # Update video record
            video.file_path = str(output_path)
            video.status = "completed"
            video.resolution = "1080x1920" if aspect_ratio == "9:16" else "1920x1080"
            # video.file_size = output_path.stat().st_size if output_path.exists() else 0
            self.db.commit()

            logger.info(f"Video generation completed for video_id={video_id}")

        except Exception as e:
            logger.error(f"Video generation failed for video_id={video_id}: {e}")
            video = self.get_video(video_id)
            if video:
                video.status = "failed"
                video.error_message = str(e)
                self.db.commit()
