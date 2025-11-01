"""Prompt file loader with support for multiple formats."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional


class PromptLoader:
    """Load and parse prompt files in various formats."""

    def __init__(self):
        self.logger = logging.getLogger("SoraExtend.PromptLoader")

    def load(self, file_path: str | Path) -> Dict[str, Any]:
        """
        Load prompt from file.

        Supported formats:
        - .txt: Plain text prompt
        - .json: JSON with structured prompt data
        - .yaml/.yml: YAML format (if PyYAML installed)

        Args:
            file_path: Path to prompt file

        Returns:
            Dictionary with prompt configuration
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {file_path}")

        self.logger.info(f"Loading prompt from: {file_path}")

        suffix = file_path.suffix.lower()

        if suffix == ".txt":
            return self._load_txt(file_path)
        elif suffix == ".json":
            return self._load_json(file_path)
        elif suffix in (".yaml", ".yml"):
            return self._load_yaml(file_path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    def _load_txt(self, file_path: Path) -> Dict[str, Any]:
        """
        Load plain text prompt file with optional configuration.

        Format:
            duration_per_segment: 12
            num_segments: 3
            size: 1280x720
            model: sora-2

            Your prompt text here...
            Can be multiple lines and free-form.
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        if not content:
            raise ValueError(f"Empty prompt file: {file_path}")

        # Parse configuration and prompt
        data = {"source_file": str(file_path)}
        lines = content.split('\n')
        prompt_lines = []
        config_section = True

        for line in lines:
            # Check if line contains configuration (key: value format)
            if config_section and ':' in line and not line.strip().startswith('#'):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip().lower()
                    value = parts[1].strip()

                    # Parse known configuration keys
                    if key == "duration_per_segment" or key == "duration":
                        try:
                            data["duration_per_segment"] = int(value)
                            continue
                        except ValueError:
                            pass
                    elif key == "num_segments" or key == "segments":
                        try:
                            data["num_segments"] = int(value)
                            continue
                        except ValueError:
                            pass
                    elif key == "size" or key == "resolution":
                        data["size"] = value
                        continue
                    elif key == "model":
                        data["model"] = value
                        continue

            # Empty line marks end of config section
            if config_section and line.strip() == "":
                config_section = False
                continue

            # After empty line or no config detected, rest is prompt
            if not config_section or not ':' in line:
                config_section = False
                prompt_lines.append(line)

        # Join prompt lines
        prompt = '\n'.join(prompt_lines).strip()

        if not prompt:
            raise ValueError(f"No prompt text found in file: {file_path}")

        data["base_prompt"] = prompt

        config_info = []
        if "duration_per_segment" in data:
            config_info.append(f"duration={data['duration_per_segment']}s")
        if "num_segments" in data:
            config_info.append(f"segments={data['num_segments']}")

        log_msg = f"Loaded text prompt ({len(prompt)} chars)"
        if config_info:
            log_msg += f" with config: {', '.join(config_info)}"

        self.logger.info(log_msg)

        return data

    def _load_json(self, file_path: Path) -> Dict[str, Any]:
        """Load JSON prompt file."""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate required fields
        if not isinstance(data, dict):
            raise ValueError("JSON file must contain an object")

        # Build full prompt from components
        if "base_prompt" in data:
            prompt = data["base_prompt"]

            # Add style if specified
            if "style" in data:
                prompt += f". Style: {data['style']}"

            # Add camera if specified
            if "camera" in data:
                prompt += f". Camera: {data['camera']}"

            # Add mood if specified
            if "mood" in data:
                prompt += f". Mood: {data['mood']}"

            # Add additional details if specified
            if "additional_details" in data:
                prompt += f". {data['additional_details']}"

            data["base_prompt"] = prompt

        elif "prompt" in data:
            data["base_prompt"] = data["prompt"]
        else:
            raise ValueError("JSON file must contain 'base_prompt' or 'prompt' field")

        data["source_file"] = str(file_path)

        self.logger.info(f"Loaded JSON prompt with {len(data)} fields")

        return data

    def _load_yaml(self, file_path: Path) -> Dict[str, Any]:
        """Load YAML prompt file."""
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML not installed. Install with: pip install pyyaml"
            )

        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError("YAML file must contain an object")

        # Same processing as JSON
        if "base_prompt" not in data and "prompt" in data:
            data["base_prompt"] = data["prompt"]

        if "base_prompt" not in data:
            raise ValueError("YAML file must contain 'base_prompt' or 'prompt' field")

        data["source_file"] = str(file_path)

        self.logger.info(f"Loaded YAML prompt with {len(data)} fields")

        return data

    def get_config(
        self,
        prompt_data: Dict[str, Any],
        cli_overrides: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract generation configuration from prompt data.

        Priority: CLI args > prompt file > defaults

        Args:
            prompt_data: Data from prompt file
            cli_overrides: Command-line argument overrides

        Returns:
            Configuration dictionary
        """
        config = {
            "base_prompt": prompt_data.get("base_prompt"),
            "seconds_per_segment": prompt_data.get("duration_per_segment", 8),
            "num_generations": prompt_data.get("num_segments", 3),
            "size": prompt_data.get("size", "1280x720"),
            "model": prompt_data.get("model", "sora-2")
        }

        # Apply CLI overrides
        if cli_overrides:
            for key, value in cli_overrides.items():
                if value is not None:
                    config[key] = value

        # Handle video_config section if present
        if "video_config" in prompt_data:
            vc = prompt_data["video_config"]
            if "duration_per_segment" in vc:
                config["seconds_per_segment"] = vc["duration_per_segment"]
            if "num_segments" in vc:
                config["num_generations"] = vc["num_segments"]
            if "size" in vc:
                config["size"] = vc["size"]

        return config

    def list_prompts(self, prompts_dir: str | Path = "prompts") -> list:
        """
        List all available prompt files.

        Args:
            prompts_dir: Directory containing prompt files

        Returns:
            List of prompt file paths
        """
        prompts_dir = Path(prompts_dir)

        if not prompts_dir.exists():
            return []

        files = []
        for pattern in ("*.txt", "*.json", "*.yaml", "*.yml"):
            files.extend(prompts_dir.glob(pattern))

        return sorted(files)
