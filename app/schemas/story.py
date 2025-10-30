"""Story schemas."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class Character(BaseModel):
    """Character schema."""
    name: str
    age: Optional[int] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    personality: Optional[str] = None
    relationship: Optional[str] = None
    secret: Optional[str] = None
    role: Optional[str] = None


class Scene(BaseModel):
    """Scene schema."""
    scene_number: int
    title: str
    narration: str
    visual_description: Optional[str] = None


class StoryData(BaseModel):
    """Complete story data schema."""
    title: str
    genre: str
    protagonist: Character
    helper: Optional[Character] = None
    antagonist: Optional[Character] = None
    scenes: List[Scene]


class StoryGenerateRequest(BaseModel):
    """Request to generate a story."""
    title: str = Field(..., description="Story title or theme")
    num_scenes: int = Field(default=12, ge=1, le=50, description="Number of scenes")
    target_minutes: int = Field(default=60, ge=1, le=120, description="Target duration in minutes")
    style: str = Field(default="general", description="Story style: general or senior")


class StoryFromJSONRequest(BaseModel):
    """Request to create story from JSON."""
    story_data: Dict[str, Any] = Field(..., description="Complete story JSON data")


class StoryCreate(BaseModel):
    """Schema for creating a story."""
    title: str
    genre: Optional[str] = None
    prompt: Optional[str] = None
    story_data: Optional[Dict[str, Any]] = None
    num_scenes: int = 0
    script_length: int = 0


class StoryResponse(BaseModel):
    """Story response schema."""
    id: int
    title: str
    genre: Optional[str] = None
    num_scenes: int
    script_length: int
    evaluation_score: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
