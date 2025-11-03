"""
간단한 비디오 병합 스크립트
여러 씬 비디오를 하나로 연결합니다.
"""
import sys
import subprocess
from pathlib import Path
import logging
import re

# 로깅 설정 - UTF-8 인코딩 지원
import io
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    stream=io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace'),
    force=True
)
logger = logging.getLogger(__name__)


def get_ffmpeg_path():
    """FFmpeg 경로 확인"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode == 0:
            return 'ffmpeg'
    except FileNotFoundError:
        pass

    # imageio-ffmpeg 시도
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        pass

    return None


def extract_scene_number(filename: str) -> int:
    """파일명에서 씬 번호 추출 (scene_01.mp4 -> 1)"""
    match = re.search(r'scene_(\d+)', filename)
    if match:
        return int(match.group(1))
    return 0


def concatenate_videos(video_folder: Path, output_filename: str):
    """
    폴더 내의 씬 비디오들을 하나로 병합

    Args:
        video_folder: 씬 비디오가 있는 폴더
        output_filename: 출력 파일 이름
    """
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        logger.error("❌ FFmpeg를 찾을 수 없습니다.")
        sys.exit(1)

    # 씬 비디오 파일 찾기 (scene_01.mp4, scene_02.mp4 등)
    video_files = sorted(
        video_folder.glob('scene_*.mp4'),
        key=lambda p: extract_scene_number(p.name)
    )

    if not video_files:
        logger.error(f"❌ 씬 비디오를 찾을 수 없습니다: {video_folder}")
        sys.exit(1)

    logger.info(f"🔗 씬 병합 시작 (simple_concat)")
    logger.info(f"={'='*70}")
    logger.info(f"📹 {len(video_files)}개 씬 병합 중...")
    logger.info(f"   비디오 목록:")
    for i, path in enumerate(video_files, 1):
        logger.info(f"   {i}. {path.name}")

    # Concat 파일 생성
    output_path = video_folder / output_filename
    concat_file = output_path.with_suffix('.txt')

    with open(concat_file, 'w', encoding='utf-8') as f:
        for path in video_files:
            # Windows 경로를 Unix 스타일로 변환
            path_str = str(path.resolve()).replace('\\', '/')
            f.write(f"file '{path_str}'\n")

    try:
        # FFmpeg concat 명령 (재인코딩)
        cmd = [
            ffmpeg,
            '-y',  # 덮어쓰기
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c:v', 'libx264',  # 비디오 재인코딩
            '-preset', 'medium',
            '-crf', '18',  # 고품질
            '-c:a', 'aac',  # 오디오 재인코딩
            '-b:a', '192k',
            str(output_path)
        ]

        logger.info(f"🎬 FFmpeg 병합 실행 중...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600
        )

        if result.returncode != 0:
            logger.error(f"❌ FFmpeg stderr: {result.stderr}")
            raise RuntimeError(f"FFmpeg 실패:\n{result.stderr}")

        logger.info(f"✅ 씬 병합 완료: {output_path.name}")

    finally:
        if concat_file.exists():
            concat_file.unlink()

    if not output_path.exists():
        logger.error(f"❌ 출력 비디오가 생성되지 않았습니다: {output_path}")
        sys.exit(1)

    logger.info(f"📁 최종 파일: {output_path}")
    logger.info(f"{'='*70}")


def main():
    """메인 실행 함수"""
    if len(sys.argv) < 3:
        logger.error("사용법: python simple_concat.py <video_folder> <output_filename>")
        sys.exit(1)

    video_folder = Path(sys.argv[1])
    output_filename = sys.argv[2]

    if not video_folder.exists():
        logger.error(f"❌ 폴더를 찾을 수 없습니다: {video_folder}")
        sys.exit(1)

    try:
        concatenate_videos(video_folder, output_filename)
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
