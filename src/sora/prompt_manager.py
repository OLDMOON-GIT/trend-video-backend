"""Prompt management system for Sora Extend.

This module provides comprehensive prompt management functionality including:
- CRUD operations for prompts
- Template management
- Prompt validation
- Version control
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging


class PromptManager:
    """Manager for video prompts with CRUD operations.

    Supports both Sora2 video generation and Short-form story creation.
    """

    def __init__(self, prompts_dir: str = "prompts", templates_dir: str = "prompts/templates"):
        """
        Initialize prompt manager.

        Args:
            prompts_dir: Directory for user prompts
            templates_dir: Directory for prompt templates
        """
        self.prompts_dir = Path(prompts_dir)
        self.templates_dir = Path(templates_dir)
        self.logger = logging.getLogger("PromptManager")

        # Create directories if they don't exist
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Prompt manager initialized: {self.prompts_dir}")

    def list_prompts(self, include_templates: bool = False) -> List[Dict[str, Any]]:
        """
        List all available prompts.

        Args:
            include_templates: Whether to include template prompts

        Returns:
            List of prompt metadata dictionaries
        """
        prompts = []

        # List user prompts
        for file_path in self.prompts_dir.glob("*"):
            if file_path.is_file() and file_path.suffix in [".txt", ".json", ".yaml", ".yml"]:
                prompts.append(self._get_prompt_metadata(file_path))

        # List templates if requested
        if include_templates:
            for file_path in self.templates_dir.glob("*"):
                if file_path.is_file() and file_path.suffix in [".txt", ".json", ".yaml", ".yml"]:
                    metadata = self._get_prompt_metadata(file_path)
                    metadata["is_template"] = True
                    prompts.append(metadata)

        return sorted(prompts, key=lambda x: x["modified_at"], reverse=True)

    def get_prompt(self, name: str) -> Dict[str, Any]:
        """
        Get prompt by name.

        Args:
            name: Prompt name (without extension)

        Returns:
            Prompt data dictionary

        Raises:
            FileNotFoundError: If prompt doesn't exist
        """
        # Try different extensions
        for ext in [".txt", ".json", ".yaml", ".yml"]:
            file_path = self.prompts_dir / f"{name}{ext}"
            if file_path.exists():
                return self._load_prompt_file(file_path)

        # Try templates directory
        for ext in [".txt", ".json", ".yaml", ".yml"]:
            file_path = self.templates_dir / f"{name}{ext}"
            if file_path.exists():
                data = self._load_prompt_file(file_path)
                data["is_template"] = True
                return data

        raise FileNotFoundError(f"Prompt not found: {name}")

    def create_prompt(
        self,
        name: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None,
        format: str = "txt",
        project_type: str = "sora2"
    ) -> Path:
        """
        Create a new prompt.

        Args:
            name: Prompt name
            prompt: Prompt text
            metadata: Optional metadata (duration, size, model, etc.)
            format: File format (txt, json, yaml)
            project_type: Project type (sora2 or shortform)

        Returns:
            Path to created prompt file
        """
        if format not in ["txt", "json", "yaml"]:
            raise ValueError(f"Unsupported format: {format}")

        if project_type not in ["sora2", "shortform"]:
            raise ValueError(f"Unsupported project type: {project_type}")

        file_path = self.prompts_dir / f"{name}.{format}"

        if file_path.exists():
            raise FileExistsError(f"Prompt already exists: {name}")

        # Add project type to metadata
        if metadata is None:
            metadata = {}
        metadata["project_type"] = project_type

        # Prepare data
        if format == "txt":
            content = self._format_txt_prompt(prompt, metadata)
            file_path.write_text(content, encoding="utf-8")

        elif format == "json":
            data = {
                "prompt": prompt,
                "metadata": metadata or {},
                "created_at": datetime.now().isoformat()
            }
            file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        elif format == "yaml":
            data = {
                "prompt": prompt,
                "metadata": metadata or {},
                "created_at": datetime.now().isoformat()
            }
            file_path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        self.logger.info(f"Created prompt: {file_path}")
        return file_path

    def update_prompt(
        self,
        name: str,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Update an existing prompt.

        Args:
            name: Prompt name
            prompt: New prompt text (optional)
            metadata: New metadata (optional)

        Returns:
            Path to updated prompt file
        """
        # Find existing prompt
        existing_data = self.get_prompt(name)
        file_path = self._find_prompt_path(name)

        if not file_path:
            raise FileNotFoundError(f"Prompt not found: {name}")

        # Update data
        if prompt is not None:
            existing_data["prompt"] = prompt

        if metadata is not None:
            if "metadata" in existing_data:
                existing_data["metadata"].update(metadata)
            else:
                existing_data["metadata"] = metadata

        existing_data["modified_at"] = datetime.now().isoformat()

        # Save updated data
        if file_path.suffix == ".txt":
            content = self._format_txt_prompt(
                existing_data["prompt"],
                existing_data.get("metadata", {})
            )
            file_path.write_text(content, encoding="utf-8")

        elif file_path.suffix == ".json":
            file_path.write_text(json.dumps(existing_data, indent=2), encoding="utf-8")

        elif file_path.suffix in [".yaml", ".yml"]:
            file_path.write_text(yaml.dump(existing_data, default_flow_style=False), encoding="utf-8")

        self.logger.info(f"Updated prompt: {file_path}")
        return file_path

    def delete_prompt(self, name: str) -> bool:
        """
        Delete a prompt.

        Args:
            name: Prompt name

        Returns:
            True if deleted, False if not found
        """
        file_path = self._find_prompt_path(name)

        if file_path and file_path.exists():
            file_path.unlink()
            self.logger.info(f"Deleted prompt: {file_path}")
            return True

        return False

    def validate_prompt(self, prompt: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate a prompt and its metadata.

        Args:
            prompt: Prompt text
            metadata: Prompt metadata

        Returns:
            Validation result dictionary
        """
        issues = []
        warnings = []

        # Check prompt length
        if not prompt or len(prompt.strip()) == 0:
            issues.append("Prompt is empty")
        elif len(prompt) < 10:
            warnings.append("Prompt is very short (< 10 chars)")
        elif len(prompt) > 4000:
            warnings.append("Prompt is very long (> 4000 chars)")

        # Check metadata
        if metadata:
            project_type = metadata.get("project_type", "sora2")

            if project_type == "sora2":
                # Sora2 specific validation
                if "duration_per_segment" in metadata:
                    duration = metadata["duration_per_segment"]
                    if duration not in [4, 8, 12]:
                        issues.append(f"Invalid duration: {duration} (must be 4, 8, or 12)")

                if "size" in metadata:
                    size = metadata["size"]
                    valid_sizes = ["1920x1080", "1280x720", "1080x1920", "720x1280"]
                    if size not in valid_sizes:
                        warnings.append(f"Unusual size: {size} (common: {', '.join(valid_sizes)})")

                if "model" in metadata:
                    model = metadata["model"]
                    if model not in ["sora-2"]:
                        warnings.append(f"Unknown model: {model}")

            elif project_type == "shortform":
                # Short-form story specific validation
                if "target_chars" in metadata:
                    target = metadata["target_chars"]
                    if target < 100:
                        warnings.append("Target characters very low (< 100)")
                    elif target > 5000:
                        warnings.append("Target characters very high (> 5000)")

                if "story_type" in metadata:
                    story_type = metadata["story_type"]
                    valid_types = ["short", "long"]
                    if story_type not in valid_types:
                        warnings.append(f"Unknown story type: {story_type}")

                if "llm_provider" in metadata:
                    provider = metadata["llm_provider"]
                    valid_providers = ["openai", "groq", "ollama"]
                    if provider not in valid_providers:
                        warnings.append(f"Unknown LLM provider: {provider}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }

    def create_from_template(
        self,
        template_name: str,
        output_name: str,
        variables: Optional[Dict[str, str]] = None
    ) -> Path:
        """
        Create a new prompt from a template.

        Args:
            template_name: Name of the template
            output_name: Name for the new prompt
            variables: Variables to replace in template

        Returns:
            Path to created prompt file
        """
        # Load template
        template_data = self.get_prompt(template_name)

        if not template_data.get("is_template"):
            raise ValueError(f"Not a template: {template_name}")

        # Replace variables if provided
        prompt = template_data["prompt"]
        if variables:
            for key, value in variables.items():
                prompt = prompt.replace(f"{{{key}}}", value)

        # Create new prompt
        return self.create_prompt(
            name=output_name,
            prompt=prompt,
            metadata=template_data.get("metadata", {}),
            format="json"
        )

    def _get_prompt_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Get metadata for a prompt file."""
        stat = file_path.stat()

        # Try to read configuration from file
        config = {}
        try:
            data = self._load_prompt_file(file_path)
            config = data.get("metadata", {})
        except Exception:
            pass

        return {
            "name": file_path.stem,
            "path": str(file_path),
            "format": file_path.suffix[1:],
            "size_bytes": stat.st_size,
            "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "config": config
        }

    def _load_prompt_file(self, file_path: Path) -> Dict[str, Any]:
        """Load prompt file and return structured data."""
        if file_path.suffix == ".txt":
            content = file_path.read_text(encoding="utf-8")

            # Parse header metadata if present
            metadata = {}
            lines = content.split("\n")
            prompt_lines = []

            for line in lines:
                if ":" in line and len(line.split(":")) == 2:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()

                    # Try to parse as metadata
                    if key in ["duration_per_segment", "num_segments", "size", "model"]:
                        if key in ["duration_per_segment", "num_segments"]:
                            try:
                                metadata[key] = int(value)
                            except ValueError:
                                prompt_lines.append(line)
                        else:
                            metadata[key] = value
                    else:
                        prompt_lines.append(line)
                else:
                    prompt_lines.append(line)

            prompt = "\n".join(prompt_lines).strip()

            return {
                "prompt": prompt,
                "metadata": metadata
            }

        elif file_path.suffix == ".json":
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return data

        elif file_path.suffix in [".yaml", ".yml"]:
            data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
            return data

        else:
            raise ValueError(f"Unsupported file format: {file_path.suffix}")

    def _format_txt_prompt(self, prompt: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Format prompt as TXT with metadata header."""
        lines = []

        if metadata:
            if "duration_per_segment" in metadata:
                lines.append(f"duration_per_segment: {metadata['duration_per_segment']}")
            if "num_segments" in metadata:
                lines.append(f"num_segments: {metadata['num_segments']}")
            if "size" in metadata:
                lines.append(f"size: {metadata['size']}")
            if "model" in metadata:
                lines.append(f"model: {metadata['model']}")

            if lines:
                lines.append("")  # Blank line after metadata

        lines.append(prompt)

        return "\n".join(lines)

    def _find_prompt_path(self, name: str) -> Optional[Path]:
        """Find prompt file path by name."""
        for ext in [".txt", ".json", ".yaml", ".yml"]:
            file_path = self.prompts_dir / f"{name}{ext}"
            if file_path.exists():
                return file_path

        return None
