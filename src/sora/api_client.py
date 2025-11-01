"""OpenAI API client with retry logic and error handling."""

import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import requests
from openai import OpenAI, APIError, APIConnectionError, RateLimitError

from .utils import guess_mime_type


class SoraAPIClient:
    """Client for interacting with OpenAI Sora API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        max_retries: int = 3,
        timeout: int = 300
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.max_retries = max_retries
        self.timeout = timeout
        self.logger = logging.getLogger("SoraExtend.API")

        self.client = OpenAI(api_key=api_key)
        self.headers_auth = {"Authorization": f"Bearer {api_key}"}

    def create_video(
        self,
        prompt: str,
        size: str,
        seconds: int,
        model: str,
        input_reference: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Create a video generation job.

        Args:
            prompt: Video generation prompt
            size: Video size (e.g., "1280x720")
            seconds: Duration in seconds (4, 8, or 12)
            model: Model name (e.g., "sora-2")
            input_reference: Optional reference image for continuity

        Returns:
            Job dictionary with 'id' and 'status'
        """
        for attempt in range(self.max_retries):
            try:
                files = {
                    "model": (None, model),
                    "prompt": (None, prompt),
                    "seconds": (None, str(seconds)),
                }

                if size:
                    files["size"] = (None, size)

                if input_reference is not None and input_reference.exists():
                    mime = guess_mime_type(input_reference)
                    files["input_reference"] = (
                        input_reference.name,
                        open(input_reference, "rb"),
                        mime
                    )

                self.logger.debug(f"Creating video job (attempt {attempt + 1}/{self.max_retries})")

                response = requests.post(
                    f"{self.base_url}/videos",
                    headers=self.headers_auth,
                    files=files,
                    timeout=self.timeout
                )

                if response.status_code >= 400:
                    error_msg = self._format_error(response)
                    if response.status_code == 429 and attempt < self.max_retries - 1:
                        # Rate limit - wait and retry
                        wait_time = 2 ** attempt
                        self.logger.warning(f"Rate limited. Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    raise RuntimeError(f"API error: {error_msg}")

                return response.json()

            except requests.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    self.logger.warning(f"Request failed: {e}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"Failed to create video after {self.max_retries} attempts: {e}")

        raise RuntimeError("Max retries exceeded")

    def retrieve_video(self, video_id: str) -> Dict[str, Any]:
        """
        Retrieve video job status.

        Args:
            video_id: Video job ID

        Returns:
            Job dictionary with current status
        """
        try:
            response = requests.get(
                f"{self.base_url}/videos/{video_id}",
                headers=self.headers_auth,
                timeout=60
            )

            if response.status_code >= 400:
                raise RuntimeError(f"Failed to retrieve video: {self._format_error(response)}")

            return response.json()

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to retrieve video status: {e}")

    def download_video(
        self,
        video_id: str,
        output_path: Path,
        variant: str = "video"
    ) -> Path:
        """
        Download generated video.

        Args:
            video_id: Video job ID
            output_path: Output file path
            variant: Content variant ("video" or "thumbnail")

        Returns:
            Path to downloaded file
        """
        try:
            with requests.get(
                f"{self.base_url}/videos/{video_id}/content",
                headers=self.headers_auth,
                params={"variant": variant},
                stream=True,
                timeout=600
            ) as response:
                if response.status_code >= 400:
                    raise RuntimeError(f"Download failed: {self._format_error(response)}")

                output_path.parent.mkdir(parents=True, exist_ok=True)

                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

            if not output_path.exists():
                raise RuntimeError(f"Download completed but file not found: {output_path}")

            return output_path

        except requests.RequestException as e:
            raise RuntimeError(f"Failed to download video: {e}")

    def poll_until_complete(
        self,
        job: Dict[str, Any],
        poll_interval: float = 2.0,
        progress_callback: Optional[callable] = None,
        max_wait_time: int = 600  # 10 minutes max
    ) -> Dict[str, Any]:
        """
        Poll job until completion.

        Args:
            job: Initial job dictionary
            poll_interval: Seconds between polls
            progress_callback: Optional callback(percent: float)
            max_wait_time: Maximum wait time in seconds (default 600 = 10 min)

        Returns:
            Completed job dictionary
        """
        video_id = job["id"]
        self.logger.info(f"Polling job {video_id} (max wait: {max_wait_time}s)...")

        poll_count = 0
        last_status = None
        last_progress = None
        stuck_at_99_count = 0
        start_time = time.time()

        while job.get("status") in ("queued", "in_progress"):
            # Check total timeout
            elapsed = time.time() - start_time
            if elapsed > max_wait_time:
                self.logger.error(f"Timeout after {elapsed:.0f}s (max: {max_wait_time}s)")
                raise RuntimeError(f"Video generation timed out after {elapsed:.0f}s")

            time.sleep(poll_interval)
            poll_count += 1

            try:
                job = self.retrieve_video(video_id)
                current_status = job.get("status")
                current_progress = float(job.get("progress", 0) or 0)

                # Detect stuck at 99%
                if current_progress >= 99.0 and current_status == "in_progress":
                    stuck_at_99_count += 1
                    if stuck_at_99_count > 30:  # 30 polls = 60s at 2s interval
                        self.logger.error(f"Job stuck at 99% for {stuck_at_99_count * poll_interval:.0f}s")
                        raise RuntimeError(f"Video generation stuck at 99% - likely failed on server side")
                else:
                    stuck_at_99_count = 0

                # Log only on significant changes to avoid cluttering progress bar
                if (current_status != last_status or
                    (poll_count % 20 == 0)):  # Log every 20 polls (40s) instead of 10
                    # Use tqdm.write to print above progress bar
                    if progress_callback:
                        import tqdm
                        tqdm.tqdm.write(
                            f"  → Poll #{poll_count}: {current_status}, "
                            f"{current_progress:.0f}%, {elapsed:.0f}s elapsed"
                        )
                    last_status = current_status
                    last_progress = current_progress

            except RuntimeError:
                raise  # Re-raise timeout and stuck errors
            except Exception as e:
                self.logger.warning(f"Poll #{poll_count} failed: {e}. Retrying...")
                continue

            if progress_callback:
                progress = float(job.get("progress", 0) or 0)
                progress_callback(progress)

        final_status = job.get("status")
        total_time = time.time() - start_time
        self.logger.info(f"Job {video_id} finished with status: {final_status} after {poll_count} polls ({total_time:.0f}s)")

        if final_status != "completed":
            error = job.get("error", {})
            error_msg = error.get("message", f"Job {video_id} failed")
            self.logger.error(f"Job failed: {error_msg}")
            self.logger.error(f"Full job data: {job}")
            raise RuntimeError(f"Video generation failed: {error_msg}")

        self.logger.info(f"Job {video_id} completed successfully")
        return job

    def _format_error(self, response: requests.Response) -> str:
        """Format error response for logging."""
        request_id = response.headers.get("x-request-id", "unknown")
        try:
            body = response.json()
        except Exception:
            body = response.text

        return f"HTTP {response.status_code} (request-id: {request_id})\n{body}"


class PlannerClient:
    """Client for AI planner using OpenAI Responses API."""

    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.logger = logging.getLogger("SoraExtend.Planner")

    def plan_segments(
        self,
        base_prompt: str,
        seconds_per_segment: int,
        num_generations: int,
        system_instructions: str
    ) -> list:
        """
        Generate segment prompts using AI planner.

        Args:
            base_prompt: Base video concept
            seconds_per_segment: Duration per segment
            num_generations: Number of segments
            system_instructions: System prompt for planner

        Returns:
            List of segment dictionaries
        """
        user_input = f"""
BASE PROMPT: {base_prompt}

GENERATION LENGTH (seconds): {seconds_per_segment}
TOTAL GENERATIONS: {num_generations}

Return exactly {num_generations} segments in JSON format.
""".strip()

        self.logger.info(f"Planning {num_generations} segments with {self.model}...")

        try:
            # Try using chat completion (more widely available than Responses API)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instructions},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )

            text = response.choices[0].message.content

        except Exception as e:
            self.logger.error(f"Planning failed: {e}")
            raise RuntimeError(f"AI planner failed: {e}")

        # Parse JSON response
        import json
        import re

        # Extract JSON from response
        match = re.search(r'\{[\s\S]*\}', text)
        if not match:
            raise ValueError("Planner did not return valid JSON")

        data = json.loads(match.group(0))
        segments = data.get("segments", [])

        if len(segments) != num_generations:
            self.logger.warning(f"Expected {num_generations} segments, got {len(segments)}")
            segments = segments[:num_generations]

        # Force correct duration
        for seg in segments:
            seg["seconds"] = int(seconds_per_segment)

        self.logger.info(f"Generated {len(segments)} segment prompts")
        return segments

    def regenerate_prompt(
        self,
        original_prompt: str,
        context: str,
        system_instructions: str
    ) -> str:
        """
        Regenerate a single prompt to avoid moderation issues.

        Args:
            original_prompt: The original prompt that failed
            context: Context about what went wrong
            system_instructions: System prompt for planner

        Returns:
            New regenerated prompt
        """
        user_input = f"""
The following video generation prompt was BLOCKED by content moderation:

ORIGINAL PROMPT: {original_prompt}

CRITICAL: Rewrite this prompt to avoid moderation rejection. Remove ALL of the following:
- Violence, weapons, fighting, blood, gore, injuries
- Sexual/suggestive content, revealing clothing, intimate scenes
- Real people (celebrities, politicians, public figures)
- Copyrighted characters, brands, logos, trademarks
- Illegal activities, drugs, alcohol, smoking, dangerous stunts
- Hate speech, discrimination, political content, controversial symbols
- Realistic depictions that could be mistaken for real news/events

INSTEAD:
- Focus on technical/artistic aspects (lighting, camera movement, composition)
- Use positive, professional, documentary-style language
- Emphasize beauty, innovation, creativity
- Make clearly fictional/artistic if showing people
- Focus on nature, architecture, technology, abstract concepts
- Use words like: "beautiful", "elegant", "innovative", "artistic", "cinematic"

Maintain the CORE VISUAL CONCEPT but make it 100% safe and appropriate.

Return ONLY the rewritten prompt text, nothing else.
""".strip()

        self.logger.info("Regenerating prompt to avoid moderation issues...")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional video prompt writer specializing in creating safe, appropriate content that passes moderation systems."},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.7,
            )

            new_prompt = response.choices[0].message.content.strip()
            self.logger.info(f"Generated new prompt: {new_prompt[:100]}...")
            return new_prompt

        except Exception as e:
            self.logger.error(f"Prompt regeneration failed: {e}")
            raise RuntimeError(f"Failed to regenerate prompt: {e}")
