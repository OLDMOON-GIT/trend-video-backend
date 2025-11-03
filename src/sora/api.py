"""REST API for Sora Extend prompt management and video generation."""

import os
import sys
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import logging

# Handle imports
if __name__ == "__main__" and __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    # Add AutoShortsEditor to path for short-form story generation
    autoshorts_path = Path(__file__).resolve().parent.parent.parent / "AutoShortsEditor"
    if autoshorts_path.exists():
        sys.path.insert(0, str(autoshorts_path))

    from src.prompt_manager import PromptManager
    from src.main import SoraExtend
    from src.utils import setup_logging
else:
    from .prompt_manager import PromptManager
    from .main import SoraExtend
    from .utils import setup_logging

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for frontend

# Setup logging
logger = setup_logging("logs/api.log", "INFO")

# Initialize prompt manager
prompt_manager = PromptManager()

# Store active generation tasks (in production, use Redis or database)
active_tasks = {}


@app.route("/", methods=["GET"])
def index():
    """API root endpoint."""
    return jsonify({
        "name": "Sora Extend API",
        "version": "1.0.0",
        "endpoints": {
            "prompts": "/api/prompts",
            "generate": "/api/generate",
            "health": "/health"
        }
    })


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"})


# ============================================================================
# Prompt Management Endpoints
# ============================================================================

@app.route("/api/prompts", methods=["GET"])
def list_prompts():
    """List all prompts."""
    try:
        include_templates = request.args.get("include_templates", "false").lower() == "true"
        prompts = prompt_manager.list_prompts(include_templates=include_templates)

        return jsonify({
            "success": True,
            "prompts": prompts,
            "count": len(prompts)
        })

    except Exception as e:
        logger.error(f"Error listing prompts: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/prompts/<name>", methods=["GET"])
def get_prompt(name):
    """Get a specific prompt by name."""
    try:
        prompt_data = prompt_manager.get_prompt(name)

        return jsonify({
            "success": True,
            "prompt": prompt_data
        })

    except FileNotFoundError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404

    except Exception as e:
        logger.error(f"Error getting prompt {name}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/prompts", methods=["POST"])
def create_prompt():
    """Create a new prompt."""
    try:
        data = request.get_json()

        # Validate required fields
        if "name" not in data or "prompt" not in data:
            return jsonify({
                "success": False,
                "error": "Missing required fields: name, prompt"
            }), 400

        name = data["name"]
        prompt = data["prompt"]
        metadata = data.get("metadata", {})
        format = data.get("format", "txt")
        project_type = data.get("project_type", "sora2")

        # Validate prompt
        validation = prompt_manager.validate_prompt(prompt, metadata)
        if not validation["valid"]:
            return jsonify({
                "success": False,
                "error": "Prompt validation failed",
                "issues": validation["issues"]
            }), 400

        # Create prompt
        file_path = prompt_manager.create_prompt(name, prompt, metadata, format, project_type)

        return jsonify({
            "success": True,
            "message": f"Prompt created: {name}",
            "path": str(file_path),
            "validation": validation,
            "project_type": project_type
        }), 201

    except FileExistsError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 409

    except Exception as e:
        logger.error(f"Error creating prompt: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/prompts/<name>", methods=["PUT"])
def update_prompt(name):
    """Update an existing prompt."""
    try:
        data = request.get_json()

        prompt = data.get("prompt")
        metadata = data.get("metadata")

        # Validate if prompt is being updated
        if prompt:
            validation = prompt_manager.validate_prompt(prompt, metadata)
            if not validation["valid"]:
                return jsonify({
                    "success": False,
                    "error": "Prompt validation failed",
                    "issues": validation["issues"]
                }), 400

        # Update prompt
        file_path = prompt_manager.update_prompt(name, prompt, metadata)

        return jsonify({
            "success": True,
            "message": f"Prompt updated: {name}",
            "path": str(file_path)
        })

    except FileNotFoundError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404

    except Exception as e:
        logger.error(f"Error updating prompt {name}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/prompts/<name>", methods=["DELETE"])
def delete_prompt(name):
    """Delete a prompt."""
    try:
        success = prompt_manager.delete_prompt(name)

        if success:
            return jsonify({
                "success": True,
                "message": f"Prompt deleted: {name}"
            })
        else:
            return jsonify({
                "success": False,
                "error": f"Prompt not found: {name}"
            }), 404

    except Exception as e:
        logger.error(f"Error deleting prompt {name}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/prompts/validate", methods=["POST"])
def validate_prompt():
    """Validate a prompt before creating/updating."""
    try:
        data = request.get_json()

        if "prompt" not in data:
            return jsonify({
                "success": False,
                "error": "Missing required field: prompt"
            }), 400

        prompt = data["prompt"]
        metadata = data.get("metadata")

        validation = prompt_manager.validate_prompt(prompt, metadata)

        return jsonify({
            "success": True,
            "validation": validation
        })

    except Exception as e:
        logger.error(f"Error validating prompt: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# Template Management Endpoints
# ============================================================================

@app.route("/api/templates", methods=["GET"])
def list_templates():
    """List all template prompts."""
    try:
        # Get only templates
        all_prompts = prompt_manager.list_prompts(include_templates=True)
        templates = [p for p in all_prompts if p.get("is_template", False)]

        return jsonify({
            "success": True,
            "templates": templates,
            "count": len(templates)
        })

    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/templates/<template_name>/instantiate", methods=["POST"])
def instantiate_template(template_name):
    """Create a new prompt from a template."""
    try:
        data = request.get_json()

        if "name" not in data:
            return jsonify({
                "success": False,
                "error": "Missing required field: name"
            }), 400

        output_name = data["name"]
        variables = data.get("variables", {})

        file_path = prompt_manager.create_from_template(
            template_name,
            output_name,
            variables
        )

        return jsonify({
            "success": True,
            "message": f"Prompt created from template: {output_name}",
            "path": str(file_path)
        }), 201

    except FileNotFoundError as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404

    except Exception as e:
        logger.error(f"Error instantiating template {template_name}: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# Video Merging Endpoints
# ============================================================================

@app.route("/api/merge/scenes", methods=["POST"])
def merge_scenes_api():
    """Merge scene videos from a folder (scene_1.mp4 to scene_N.mp4)."""
    try:
        data = request.get_json()

        # Get folder path
        if "folder" not in data:
            return jsonify({
                "success": False,
                "error": "Missing required field: folder"
            }), 400

        folder_path = Path(data["folder"])

        if not folder_path.exists():
            return jsonify({
                "success": False,
                "error": f"Folder not found: {folder_path}"
            }), 404

        # Get optional parameters
        output_name = data.get("output_name")

        # Import quick_merge from project root
        project_root = Path(__file__).resolve().parent.parent.parent
        sys.path.insert(0, str(project_root))
        from quick_merge import quick_merge

        # Merge videos using existing logic
        logger.info(f"Merging scenes from folder: {folder_path}")
        output_path = quick_merge(folder_path, output_name)

        return jsonify({
            "success": True,
            "message": "Videos merged successfully",
            "output_path": str(output_path),
            "folder": str(folder_path)
        })

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 404

    except Exception as e:
        logger.error(f"Error merging videos: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ============================================================================
# Video Generation Endpoints
# ============================================================================

@app.route("/api/generate", methods=["POST"])
def generate_video():
    """Generate a video from a prompt."""
    try:
        data = request.get_json()

        # Get prompt (either direct text or from saved prompt)
        if "prompt" in data:
            base_prompt = data["prompt"]
            config_data = {}
        elif "prompt_name" in data:
            prompt_data = prompt_manager.get_prompt(data["prompt_name"])
            base_prompt = prompt_data["prompt"]
            config_data = prompt_data.get("metadata", {})
        else:
            return jsonify({
                "success": False,
                "error": "Missing required field: prompt or prompt_name"
            }), 400

        # Get generation parameters (with defaults)
        seconds_per_segment = data.get("duration_per_segment") or config_data.get("duration_per_segment", 8)
        num_generations = data.get("num_segments") or config_data.get("num_segments", 3)
        size = data.get("size") or config_data.get("size", "1280x720")
        model = data.get("model") or config_data.get("model", "sora-2")
        output_name = data.get("output_name")

        # Initialize SoraExtend
        app_instance = SoraExtend(output_name=output_name)

        # Generate video (this will take a while)
        logger.info(f"Starting video generation: {base_prompt[:50]}...")

        final_path = app_instance.generate(
            base_prompt=base_prompt,
            seconds_per_segment=seconds_per_segment,
            num_generations=num_generations,
            size=size,
            model=model
        )

        return jsonify({
            "success": True,
            "message": "Video generated successfully",
            "output_path": str(final_path),
            "output_dir": str(app_instance.output_dir)
        })

    except Exception as e:
        logger.error(f"Error generating video: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/generate/shortform", methods=["POST"])
def generate_shortform():
    """Generate a short-form story video from a prompt."""
    try:
        data = request.get_json()

        # Get prompt (either direct text or from saved prompt)
        if "prompt" in data:
            base_prompt = data["prompt"]
            config_data = {}
        elif "prompt_name" in data:
            prompt_data = prompt_manager.get_prompt(data["prompt_name"])
            base_prompt = prompt_data["prompt"]
            config_data = prompt_data.get("metadata", {})
        else:
            return jsonify({
                "success": False,
                "error": "Missing required field: prompt or prompt_name"
            }), 400

        # Get generation parameters
        story_type = data.get("story_type") or config_data.get("story_type", "short")
        target_chars = data.get("target_chars") or config_data.get("target_chars", 1000)
        llm_provider = data.get("llm_provider") or config_data.get("llm_provider", "openai")
        image_provider = data.get("image_provider") or config_data.get("image_provider", "openai")
        output_name = data.get("output_name")

        try:
            # Import AutoShortsEditor modules
            from src.story_video_creator import StoryVideoCreator
            from src.long_form_creator import LongFormStoryCreator
            import json

            # Load AutoShortsEditor config
            config_path = Path(__file__).resolve().parent.parent.parent / "AutoShortsEditor" / "config" / "config.json"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    autoshorts_config = json.load(f)
            else:
                # Default config
                autoshorts_config = {
                    "ai": {
                        "llm": {"provider": llm_provider},
                        "image_generation": {"provider": image_provider}
                    },
                    "output": {"directory": "output"}
                }

            logger.info(f"Starting short-form story generation: {base_prompt[:50]}...")

            if story_type == "short":
                # Short story (60 seconds)
                creator = StoryVideoCreator(autoshorts_config)
                output_path = creator.create_from_prompt(
                    prompt=base_prompt,
                    target_chars=target_chars,
                    output_name=output_name
                )
            else:
                # Long form story
                creator = LongFormStoryCreator(autoshorts_config)
                output_path = creator.create_from_title(
                    title=base_prompt,
                    seed=None,
                    target_duration=target_chars  # Use as duration in seconds
                )

            return jsonify({
                "success": True,
                "message": "Short-form story generated successfully",
                "output_path": str(output_path),
                "story_type": story_type
            })

        except ImportError as e:
            logger.error(f"AutoShortsEditor not found: {e}")
            return jsonify({
                "success": False,
                "error": "AutoShortsEditor is not available. Please ensure it's installed in the parent directory."
            }), 500

    except Exception as e:
        logger.error(f"Error generating short-form story: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/api/generate/status/<task_id>", methods=["GET"])
def get_generation_status(task_id):
    """Get the status of a video generation task."""
    # This is a placeholder for async task tracking
    # In production, use Celery or similar task queue
    task = active_tasks.get(task_id)

    if not task:
        return jsonify({
            "success": False,
            "error": f"Task not found: {task_id}"
        }), 404

    return jsonify({
        "success": True,
        "task": task
    })


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Start the API server."""
    port = int(os.getenv("API_PORT", 5000))
    debug = os.getenv("API_DEBUG", "false").lower() == "true"

    logger.info(f"Starting Sora Extend API on port {port}")
    logger.info(f"Debug mode: {debug}")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug
    )


if __name__ == "__main__":
    main()
