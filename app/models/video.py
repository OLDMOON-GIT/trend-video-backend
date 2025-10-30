"""Video model."""

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime

from app.database import Base


class Video(Base):
    """Video model for database."""

    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    story_id = Column(Integer, ForeignKey("stories.id"), nullable=True)
    title = Column(String(255), nullable=False)
    file_path = Column(String(500))
    duration = Column(Float)
    resolution = Column(String(50))  # e.g., "1080x1920"
    aspect_ratio = Column(String(10))  # e.g., "9:16"
    file_size = Column(Integer)  # in bytes
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    # story = relationship("Story", backref="videos")
