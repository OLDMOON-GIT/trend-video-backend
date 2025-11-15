"""Main entry point for Sora Extend."""

import os
import sys
from pathlib import Path
from typing import List
from datetime import datetime
from dotenv import load_dotenv
from tqdm import tqdm

# Handle both package import and direct execution
if __name__ == "__main__" and __package__ is None:
    # Add parent directory to path for direct execution
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from src.utils import (
        setup_logging,
        load_config,
        check_ffmpeg,
        extract_last_frame,
        concatenate_videos_lossless,
        concatenate_videos_fallback,
        validate_duration,
        validate_size
    )
    from src.api_client import SoraAPIClient, PlannerClient
    from src.prompts import PLANNER_SYSTEM_INSTRUCTIONS
else:
    from .utils import (
        setup_logging,
        load_config,
        check_ffmpeg,
        extract_last_frame,
        concatenate_videos_lossless,
        concatenate_videos_fallback,
        validate_duration,
        validate_size
    )
    from .api_client import SoraAPIClient, PlannerClient
    from .prompts import PLANNER_SYSTEM_INSTRUCTIONS


class SoraExtend:
    """Main application class."""

    def __init__(self, config_path: str = "config/config.json", output_name: str = None):
        # Load environment variables
        load_dotenv()

        # Setup logging
        self.config = load_config(config_path)
        self.logger = setup_logging(
            log_file=self.config["logging"]["file"],
            level=self.config["logging"]["level"]
        )

        # Get API key
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")

        # Initialize clients
        self.sora_client = SoraAPIClient(
            api_key=self.api_key,
            base_url=self.config["api"]["base_url"],
            max_retries=self.config["api"]["max_retries"],
            timeout=self.config["api"]["timeout"]
        )

        planner_model = os.getenv("PLANNER_MODEL", "gpt-4o")
        self.planner_client = PlannerClient(
            api_key=self.api_key,
            model=planner_model
        )

        # Check FFmpeg
        if not check_ffmpeg():
            self.logger.warning("FFmpeg not found. Will fall back to MoviePy (slower).")
            self.use_ffmpeg = False
        else:
            self.logger.info("FFmpeg detected - will use lossless concatenation")
            self.use_ffmpeg = True

        # Create timestamped output directory
        base_output_dir = Path(self.config["output"]["directory"])
        if output_name:
            folder_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{output_name}"
        else:
            folder_name = datetime.now().strftime('%Y%m%d_%H%M%S')

        self.output_dir = base_output_dir / folder_name
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"Output directory: {self.output_dir}")

    def generate(
        self,
        base_prompt: str,
        seconds_per_segment: int = 8,
        num_generations: int = 3,
        size: str = "1280x720",
        model: str = "sora-2"
    ) -> Path:
        """
        Generate extended video.

        Args:
            base_prompt: Base video concept
            seconds_per_segment: Duration per segment (4, 8, or 12)
            num_generations: Number of segments to generate
            size: Video resolution
            model: Sora model name

        Returns:
            Path to final combined video
        """
        # Validate inputs
        validate_duration(seconds_per_segment, self.config["video"]["supported_durations"])
        validate_size(size, self.config["video"]["supported_sizes"])

        self.logger.info("=" * 80)
        self.logger.info("SORA EXTEND - Extended Video Generation")
        self.logger.info("=" * 80)
        self.logger.info(f"Base Prompt: {base_prompt}")
        self.logger.info(f"Segments: {num_generations} x {seconds_per_segment}s = {num_generations * seconds_per_segment}s total")
        self.logger.info(f"Size: {size}, Model: {model}")
        self.logger.info("=" * 80)

        # Step 1: Plan segments
        self.logger.info("\n[1/3] Planning video segments with AI...")
        segments = self.planner_client.plan_segments(
            base_prompt=base_prompt,
            seconds_per_segment=seconds_per_segment,
            num_generations=num_generations,
            system_instructions=PLANNER_SYSTEM_INSTRUCTIONS
        )

        self.logger.info(f"\n✓ Planned {len(segments)} segments:")
        for i, seg in enumerate(segments, 1):
            title = seg.get("title", f"Segment {i}")
            self.logger.info(f"  [{i:02d}] {title} ({seg['seconds']}s)")

        # Step 2: Generate videos
        self.logger.info(f"\n[2/3] Generating {len(segments)} video segments...")
        try:
            segment_paths = self._generate_segments(segments, size, model)
        except Exception as e:
            self.logger.error(f"Error during generation: {e}")
            # Check if any segments were generated
            segment_paths = []
            for i in range(1, len(segments) + 1):
                segment_filename = self.config["output"]["segment_format"].format(i)
                segment_path = self.output_dir / segment_filename
                if segment_path.exists():
                    segment_paths.append(segment_path)
                    self.logger.info(f"Found generated segment: {segment_path}")
                else:
                    break

            if not segment_paths:
                self.logger.error("No segments were generated successfully")
                raise

            self.logger.warning(f"Only {len(segment_paths)}/{len(segments)} segments completed. Continuing with partial video...")

        # Step 3: Concatenate available segments
        if len(segment_paths) == 1:
            self.logger.info("\n[3/3] Only one segment generated, skipping concatenation...")
            final_path = self.output_dir / self.config["output"]["final_filename"]
            import shutil
            shutil.copy(segment_paths[0], final_path)
        else:
            self.logger.info(f"\n[3/3] Combining {len(segment_paths)} segments...")
            final_path = self._concatenate_segments(segment_paths)

        actual_duration = len(segment_paths) * seconds_per_segment
        self.logger.info("\n" + "=" * 80)
        self.logger.info(f"✓ COMPLETED! Final video saved to: {final_path}")
        self.logger.info(f"  Segments generated: {len(segment_paths)}/{len(segments)}")
        self.logger.info(f"  Total duration: {actual_duration}s")
        self.logger.info(f"  File size: {final_path.stat().st_size / (1024*1024):.1f} MB")
        self.logger.info(f"  Output folder: {self.output_dir}")
        self.logger.info("=" * 80)

        return final_path

    def _generate_segments(
        self,
        segments: List[dict],
        size: str,
        model: str
    ) -> List[Path]:
        """Generate all video segments with continuity."""
        segment_paths = []
        input_reference = None

        for i, seg in enumerate(segments, 1):
            print(f"\n{'='*70}")
            print(f"Segment {i}/{len(segments)}")
            print(f"Prompt: {seg['prompt'][:80]}...")
            print(f"{'='*70}")

            # Try to generate this segment with retry on moderation errors
            max_moderation_retries = 2
            segment_generated = False

            for retry_attempt in range(max_moderation_retries + 1):
                try:
                    # Create video job
                    job = self.sora_client.create_video(
                        prompt=seg["prompt"],
                        size=size,
                        seconds=seg["seconds"],
                        model=model,
                        input_reference=input_reference
                    )

                    print(f"✓ Job created: {job['id']}")

                    # Poll until complete with progress bar
                    pbar = tqdm(
                        total=100,
                        desc=f"Generating {i}/{len(segments)}",
                        bar_format='{l_bar}{bar}| {n:.0f}% [{elapsed}<{remaining}]',
                        colour='green'
                    )

                    def update_progress(percent: float):
                        pbar.n = percent
                        pbar.refresh()

                    try:
                        completed_job = self.sora_client.poll_until_complete(
                            job,
                            poll_interval=float(os.getenv("POLL_INTERVAL_SEC", "2")),
                            progress_callback=update_progress
                        )
                    finally:
                        pbar.close()

                    # Download video
                    segment_filename = self.config["output"]["segment_format"].format(i)
                    segment_path = self.output_dir / segment_filename

                    print(f"⬇ Downloading video...")
                    self.sora_client.download_video(completed_job["id"], segment_path)

                    segment_paths.append(segment_path)
                    segment_generated = True
                    print(f"✓ Segment {i} complete: {segment_path.name}")

                    # Extract last frame for next segment's input reference
                    if i < len(segments):
                        frame_filename = self.config["output"]["frame_format"].format(i)
                        frame_path = self.output_dir / frame_filename

                        print(f"📸 Extracting last frame for continuity...")
                        input_reference = extract_last_frame(segment_path, frame_path)

                    break  # Success, exit retry loop

                except Exception as e:
                    error_msg = str(e).lower()

                    # Check if it's a moderation error
                    if "moderation" in error_msg and retry_attempt < max_moderation_retries:
                        print(f"⚠ Moderation error - regenerating prompt (attempt {retry_attempt + 1}/{max_moderation_retries})...")

                        try:
                            # Regenerate the prompt
                            new_prompt = self.planner_client.regenerate_prompt(
                                original_prompt=seg["prompt"],
                                context=f"Segment {i} of {len(segments)}",
                                system_instructions="You are a professional video prompt writer. Create safe, appropriate prompts for video generation."
                            )

                            print(f"✓ New prompt: {new_prompt[:80]}...")
                            seg["prompt"] = new_prompt

                        except Exception as regen_error:
                            print(f"✗ Failed to regenerate: {regen_error}")
                            raise e  # Raise original error

                    else:
                        # Not a moderation error or max retries exceeded
                        print(f"✗ Error: {e}")
                        raise

            if not segment_generated:
                raise RuntimeError(f"Failed to generate segment {i} after {max_moderation_retries + 1} attempts")

        return segment_paths

    def _concatenate_segments(self, segment_paths: List[Path]) -> Path:
        """Concatenate video segments."""
        final_path = self.output_dir / self.config["output"]["final_filename"]

        if self.use_ffmpeg:
            try:
                self.logger.info("Using FFmpeg lossless concatenation...")
                return concatenate_videos_lossless(segment_paths, final_path)
            except Exception as e:
                self.logger.warning(f"FFmpeg concat failed: {e}")
                self.logger.info("Falling back to MoviePy...")

        # Fallback to MoviePy
        return concatenate_videos_fallback(segment_paths, final_path)


def combine_existing_segments(folder_path: str, config_path: str = "config/config.json") -> int:
    """
    Combine existing segment videos in a folder.

    Args:
        folder_path: Path to folder containing video files with sequence numbers
        config_path: Path to config file

    Returns:
        Exit code
    """
    import re

    # Try to find matching folder if not exact path
    folder = Path(folder_path)

    if not folder.exists():
        # Try to find folders matching the pattern in output directory
        output_base = Path("output")
        if output_base.exists():
            matching_folders = []
            search_term = folder.name.lower()

            for candidate in output_base.iterdir():
                if candidate.is_dir() and search_term in candidate.name.lower():
                    matching_folders.append(candidate)

            if len(matching_folders) == 1:
                folder = matching_folders[0]
                print(f"Found matching folder: {folder}")
            elif len(matching_folders) > 1:
                print(f"Multiple folders match '{search_term}':")
                for i, f in enumerate(matching_folders, 1):
                    print(f"  [{i}] {f.name}")
                print("\nPlease specify the full folder path.")
                return 1
            else:
                print(f"Error: No folder found matching: {folder_path}")
                return 1
        else:
            print(f"Error: Folder not found: {folder}")
            return 1

    if not folder.is_dir():
        print(f"Error: Not a directory: {folder}")
        return 1

    # Find all video files with sequence numbers
    # Pattern: any filename with a number (e.g., segment_01.mp4, video_3.mp4, 001.mp4)
    video_pattern = re.compile(r'.*?(\d+).*?\.(mp4|avi|mov|mkv)$', re.IGNORECASE)
    segments = []

    for file in folder.iterdir():
        if file.is_file():
            match = video_pattern.match(file.name)
            if match:
                seq_num = int(match.group(1))
                segments.append((seq_num, file))

    if not segments:
        print(f"Error: No video files with sequence numbers found in {folder}")
        print("Expected files with numbers like: segment_01.mp4, video_3.mp4, 001.mp4, etc.")
        return 1

    # Sort by sequence number
    segments.sort(key=lambda x: x[0])
    segment_paths = [path for _, path in segments]

    print(f"\n{'='*70}")
    print(f"Combining existing segments")
    print(f"{'='*70}")
    print(f"Folder: {folder}")
    print(f"Found {len(segment_paths)} segments:")
    for seq, path in segments:
        size_mb = path.stat().st_size / (1024*1024)
        print(f"  [{seq:02d}] {path.name} ({size_mb:.1f} MB)")
    print(f"{'='*70}\n")

    # Load config
    config = load_config(config_path)

    # Check FFmpeg
    use_ffmpeg = check_ffmpeg()
    if use_ffmpeg:
        print("✓ Using FFmpeg lossless concatenation")
    else:
        print("⚠ FFmpeg not found, using MoviePy (slower)")

    # Output path
    output_path = folder / "combined.mp4"

    try:
        if use_ffmpeg:
            print("\n🎬 Combining videos with FFmpeg...")
            final_path = concatenate_videos_lossless(segment_paths, output_path)
        else:
            print("\n🎬 Combining videos with MoviePy...")
            final_path = concatenate_videos_fallback(segment_paths, output_path)

        print(f"\n{'='*70}")
        print(f"✓ SUCCESS!")
        print(f"{'='*70}")
        print(f"Combined video: {final_path}")
        print(f"File size: {final_path.stat().st_size / (1024*1024):.1f} MB")
        print(f"{'='*70}\n")

        return 0

    except Exception as e:
        print(f"\n{'='*70}")
        print(f"✗ ERROR")
        print(f"{'='*70}")
        print(f"Failed to combine videos: {e}")
        print(f"{'='*70}\n")
        return 1


def main():
    """Command-line entry point."""
    import argparse

    # Import PromptLoader here to avoid circular imports
    if __name__ == "__main__" and __package__ is None:
        from src.prompt_loader import PromptLoader
    else:
        from .prompt_loader import PromptLoader

    parser = argparse.ArgumentParser(
        description="Sora Extend - Generate extended videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Direct prompt
  python run.py "A futuristic car in a cyberpunk city"

  # From prompt file
  python run.py --prompt-file prompts/car_racing.txt

  # With overrides
  python run.py --prompt-file prompts/nature.txt --num-segments 5

  # List available prompts
  python run.py --list-prompts

  # Combine existing segments
  python run.py --combine-folder output/20250118_143022_cyberpunk_city
        """
    )

    # Prompt source (mutually exclusive)
    prompt_group = parser.add_mutually_exclusive_group(required=False)
    prompt_group.add_argument("prompt", nargs="?", help="Base video prompt (text)")
    prompt_group.add_argument("-f", "--prompt-file",
                             help="Path to prompt file (.txt, .json, .yaml)")
    prompt_group.add_argument("--list-prompts", action="store_true",
                             help="List available prompt files in prompts/ directory")
    prompt_group.add_argument("--combine-folder",
                             help="Combine existing segments in a folder (e.g., output/20250118_143022_cyberpunk_city)")

    # Video parameters
    parser.add_argument("-d", "--duration", type=int, choices=[4, 8, 12],
                        help="Duration per segment in seconds (default: from file or 8)")
    parser.add_argument("-n", "--num-segments", type=int,
                        help="Number of segments to generate (default: from file or 3)")
    parser.add_argument("-s", "--size",
                        help="Video size (default: from file or 1280x720)")
    parser.add_argument("-m", "--model",
                        help="Sora model name (default: from file or sora-2)")

    # Other options
    parser.add_argument("-c", "--config", default="config/config.json",
                        help="Config file path")
    parser.add_argument("--job-id", default=None,
                        help="Job ID for tracking")

    args = parser.parse_args()

    # Handle combine folder
    if args.combine_folder:
        return combine_existing_segments(args.combine_folder, args.config)

    # Handle list prompts
    if args.list_prompts:
        loader = PromptLoader()
        prompts = loader.list_prompts()
        if not prompts:
            print("No prompt files found in prompts/ directory")
            print("\nCreate a prompt file:")
            print("  prompts/my_prompt.txt  - Plain text prompt")
            print("  prompts/my_prompt.json - Structured JSON prompt")
            return 0

        print("Available prompt files:\n")
        for p in prompts:
            print(f"  {p}")
        print(f"\nTotal: {len(prompts)} files")
        print("\nUsage: python run.py --prompt-file prompts/example.txt")
        return 0

    # Determine prompt source
    if args.prompt_file:
        # Load from file
        loader = PromptLoader()
        try:
            prompt_data = loader.load(args.prompt_file)

            # Get configuration from file with CLI overrides
            cli_overrides = {
                "seconds_per_segment": args.duration,
                "num_generations": args.num_segments,
                "size": args.size,
                "model": args.model
            }

            config = loader.get_config(prompt_data, cli_overrides)

            print(f"Loaded prompt from: {args.prompt_file}")
            print(f"Configuration: {config['num_generations']} segments × {config['seconds_per_segment']}s")

        except Exception as e:
            print(f"Error loading prompt file: {e}")
            return 1

    elif args.prompt:
        # Use direct prompt
        config = {
            "base_prompt": args.prompt,
            "seconds_per_segment": args.duration or 8,
            "num_generations": args.num_segments or 3,
            "size": args.size or "1280x720",
            "model": args.model or "sora-2"
        }
    else:
        parser.print_help()
        print("\nError: Either provide a prompt or use --prompt-file")
        return 1

    try:
        # Extract output name from prompt file if available
        output_name = None
        if args.prompt_file:
            output_name = Path(args.prompt_file).stem

        app = SoraExtend(config_path=args.config, output_name=output_name)

        # Log Job ID if provided
        if args.job_id:
            print(f"\n{'='*70}")
            print(f"🆔 Job ID: {args.job_id}")
            print(f"{'='*70}\n")

        app.generate(
            base_prompt=config["base_prompt"],
            seconds_per_segment=config["seconds_per_segment"],
            num_generations=config["num_generations"],
            size=config["size"],
            model=config["model"]
        )

        # Log completion with Job ID
        if args.job_id:
            print(f"\n{'='*70}")
            print(f"✓ 완료!")
            print(f"🆔 Job ID: {args.job_id}")
            print(f"{'='*70}\n")

        return 0
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\n\nError: {e}")
        return 1


if __name__ == "__main__":
    main()
