"""Story API endpoints."""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.schemas.story import (
    StoryGenerateRequest,
    StoryFromJSONRequest,
    StoryResponse,
    StoryCreate
)
from app.services.story_service import StoryService


router = APIRouter()


@router.post("/generate", response_model=StoryResponse)
async def generate_story(
    request: StoryGenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Generate a new story from a title/theme.

    This endpoint creates a story using AI and returns immediately.
    The actual story generation happens in the background.
    """
    service = StoryService(db)

    # Create story record
    story = service.create_story(
        title=request.title,
        prompt=f"Generate {request.num_scenes} scenes for: {request.title}",
        num_scenes=request.num_scenes
    )

    # Generate story in background
    background_tasks.add_task(
        service.generate_story_content,
        story.id,
        request.title,
        request.num_scenes,
        request.target_minutes,
        request.style
    )

    return story


@router.post("/from-json", response_model=StoryResponse)
async def create_story_from_json(
    request: StoryFromJSONRequest,
    db: Session = Depends(get_db)
):
    """
    Create a story from pre-generated JSON data.

    Use this endpoint if you already have the story structure
    and want to skip the generation step.
    """
    service = StoryService(db)

    # Extract story metadata
    story_data = request.story_data
    title = story_data.get("title", "Untitled")
    genre = story_data.get("genre", "Unknown")
    scenes = story_data.get("scenes", [])
    num_scenes = len(scenes)

    # Calculate total script length
    script_length = sum(len(scene.get("narration", "")) for scene in scenes)

    # Create story record
    story = service.create_story(
        title=title,
        genre=genre,
        story_data=story_data,
        num_scenes=num_scenes,
        script_length=script_length,
        status="completed"
    )

    return story


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(story_id: int, db: Session = Depends(get_db)):
    """Get a story by ID."""
    service = StoryService(db)
    story = service.get_story(story_id)

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    return story


@router.get("/", response_model=List[StoryResponse])
async def list_stories(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """List all stories with pagination."""
    service = StoryService(db)
    stories = service.list_stories(skip=skip, limit=limit)
    return stories


@router.delete("/{story_id}")
async def delete_story(story_id: int, db: Session = Depends(get_db)):
    """Delete a story."""
    service = StoryService(db)
    success = service.delete_story(story_id)

    if not success:
        raise HTTPException(status_code=404, detail="Story not found")

    return {"message": "Story deleted successfully"}
