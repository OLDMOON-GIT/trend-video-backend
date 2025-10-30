"""Story model."""

from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from datetime import datetime

from app.database import Base


class Story(Base):
    """Story model for database."""

    __tablename__ = "stories"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    genre = Column(String(100))
    prompt = Column(Text)
    story_data = Column(JSON)  # Full story JSON
    script_length = Column(Integer, default=0)
    num_scenes = Column(Integer, default=0)
    evaluation_score = Column(Integer)
    status = Column(String(50), default="pending")  # pending, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
