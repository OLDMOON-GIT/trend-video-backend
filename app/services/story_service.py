"""Story generation service."""

import logging
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from openai import OpenAI
import os

from app.models.story import Story
from app.config import settings


logger = logging.getLogger(__name__)


class StoryService:
    """Service for story generation and management."""

    def __init__(self, db: Session):
        self.db = db
        self._init_llm_client()

    def _init_llm_client(self):
        """Initialize LLM client based on provider."""
        provider = settings.llm_provider

        if provider == "groq":
            if not settings.groq_api_key:
                raise ValueError("GROQ_API_KEY is required")
            self.client = OpenAI(
                api_key=settings.groq_api_key,
                base_url="https://api.groq.com/openai/v1"
            )
            self.model = settings.llm_model
        elif provider == "ollama":
            self.client = OpenAI(
                api_key="ollama",
                base_url="http://localhost:11434/v1"
            )
            self.model = settings.llm_model
        else:  # openai
            if not settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required")
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = "gpt-4o"

    def create_story(
        self,
        title: str,
        prompt: Optional[str] = None,
        genre: Optional[str] = None,
        story_data: Optional[Dict[str, Any]] = None,
        num_scenes: int = 0,
        script_length: int = 0,
        status: str = "pending"
    ) -> Story:
        """Create a new story record."""
        story = Story(
            title=title,
            prompt=prompt,
            genre=genre,
            story_data=story_data,
            num_scenes=num_scenes,
            script_length=script_length,
            status=status
        )
        self.db.add(story)
        self.db.commit()
        self.db.refresh(story)
        return story

    def get_story(self, story_id: int) -> Optional[Story]:
        """Get a story by ID."""
        return self.db.query(Story).filter(Story.id == story_id).first()

    def list_stories(self, skip: int = 0, limit: int = 20) -> List[Story]:
        """List stories with pagination."""
        return self.db.query(Story).offset(skip).limit(limit).all()

    def delete_story(self, story_id: int) -> bool:
        """Delete a story."""
        story = self.get_story(story_id)
        if not story:
            return False

        self.db.delete(story)
        self.db.commit()
        return True

    def generate_story_content(
        self,
        story_id: int,
        title: str,
        num_scenes: int,
        target_minutes: int,
        style: str
    ):
        """Generate story content using LLM."""
        try:
            logger.info(f"Generating story content for story_id={story_id}")

            # Load prompt template
            prompt = self._build_prompt(title, num_scenes, target_minutes, style)

            # Generate story using LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert story writer."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=8000
            )

            # Parse response
            story_text = response.choices[0].message.content

            # Try to parse as JSON
            import json
            try:
                # Remove markdown code blocks if present
                story_text = story_text.strip()
                if story_text.startswith("```json"):
                    story_text = story_text[7:]
                if story_text.startswith("```"):
                    story_text = story_text[3:]
                if story_text.endswith("```"):
                    story_text = story_text[:-3]

                story_data = json.loads(story_text.strip())
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse story JSON: {e}")
                story_data = {"raw_text": story_text}

            # Calculate metadata
            scenes = story_data.get("scenes", [])
            script_length = sum(len(scene.get("narration", "")) for scene in scenes)
            genre = story_data.get("genre", "Unknown")

            # Update story record
            story = self.get_story(story_id)
            if story:
                story.story_data = story_data
                story.genre = genre
                story.num_scenes = len(scenes)
                story.script_length = script_length
                story.status = "completed"
                self.db.commit()

            logger.info(f"Story generation completed for story_id={story_id}")

        except Exception as e:
            logger.error(f"Story generation failed for story_id={story_id}: {e}")
            story = self.get_story(story_id)
            if story:
                story.status = "failed"
                self.db.commit()

    def _build_prompt(
        self,
        title: str,
        num_scenes: int,
        target_minutes: int,
        style: str
    ) -> str:
        """Build prompt for story generation."""
        # Load from file if available
        from pathlib import Path
        prompt_file = Path(__file__).parent.parent.parent / "prompts" / "long_form_prompt.txt"

        if prompt_file.exists():
            with open(prompt_file, 'r', encoding='utf-8') as f:
                template = f.read()
        else:
            # Default template
            template = """Create a {num_scenes}-scene story titled "{title}".

Target duration: {target_minutes} minutes
Style: {style}

Generate a complete story with:
1. Title and genre
2. Main characters (protagonist, helper, antagonist)
3. {num_scenes} scenes with detailed narration

Output as JSON:
{{
  "title": "...",
  "genre": "...",
  "protagonist": {{"name": "...", "age": 0, "gender": "...", "occupation": "...", "personality": "..."}},
  "helper": {{"name": "...", "relationship": "...", "role": "..."}},
  "antagonist": {{"name": "...", "relationship": "...", "role": "..."}},
  "scenes": [
    {{"scene_number": 1, "title": "...", "narration": "..."}},
    ...
  ]
}}"""

        # Replace variables
        target_length = target_minutes * 60 * 11
        per_scene = target_length // num_scenes
        min_per_scene = max(int(per_scene * 0.8), 3200)

        prompt = template.format(
            title=title,
            num_scenes=num_scenes,
            target_minutes=target_minutes,
            style=style,
            min_per_scene=f"{min_per_scene:,}"
        )

        # Handle missing placeholders
        prompt = prompt.replace("{min_per_scene:,}", f"{min_per_scene:,}")

        return prompt
