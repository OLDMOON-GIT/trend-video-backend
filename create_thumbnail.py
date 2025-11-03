#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail generation script
Scene 1 image as background with title and summary in 4 lines
"""

import argparse
import logging
from pathlib import Path
import json
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import textwrap

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _normalize_key(text: str) -> str:
    return ''.join(ch for ch in text.lower() if ch.isalnum())


def get_story_data(folder: Path) -> dict:
    """Extract data from story*.json file"""
    story_files = sorted(folder.glob('*story*.json')) or sorted(folder.glob('*.json'))

    if not story_files:
        raise FileNotFoundError(f"No story JSON found in {folder}")

    story_file = story_files[0]
    logger.info(f"Story file: {story_file.name}")

    with open(story_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    title = data.get("title")
    if not title and "metadata" in data:
        title = data["metadata"].get("title")
    if not title and "meta" in data:
        title = data["meta"].get("title")

    if not title:
        title = "No title"

    # 제목에서 큰따옴표만 제거 (쉼표는 유지)
    quote_chars = ['"', '"', '"']  # 큰따옴표만
    for quote in quote_chars:
        title = title.replace(quote, '')

    scenes = data.get("scenes", [])
    if not scenes:
        raise ValueError("No scene data")

    scene1 = scenes[0]

    content = scene1.get("content", "") or scene1.get("narration", "") or scene1.get("description", "") or ""
    content_clean = " ".join(content.split())
    scene_summary = content_clean[:100]

    return {
        "title": title,
        "scene_title": scene1.get("title", ""),
        "scene_content": content_clean,
        "scene_summary": scene_summary,
        "total_scenes": len(scenes)
    }


def find_scene1_image(folder: Path) -> Path:
    """Find scene 1 image"""
    image_extensions = ['.jpg', '.jpeg', '.png', '.webp']

    all_images = []
    for ext in image_extensions:
        all_images.extend(folder.glob(f"*{ext}"))
        all_images.extend(folder.glob(f"*{ext.upper()}"))

    if not all_images:
        raise FileNotFoundError(f"No images found: {folder}")

    all_images.sort(key=lambda x: x.stat().st_mtime)
    scene1_image = all_images[0]

    logger.info(f"Scene 1 image: {scene1_image.name}")
    return scene1_image





























def create_hooking_text(story_data: dict) -> dict:
    """Create four-line hooking text with title-first ordering."""
    title = (story_data.get("title") or "").strip()
    scene_summary = (story_data.get("scene_summary") or "").strip()
    scene_content = (story_data.get("scene_content") or "").strip()

    split_regex = re.compile(r"[.!?\n]+")

    def _clip(text: str, width: int) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        return textwrap.shorten(text, width=width, placeholder='...')

    def _add_lines(chunks: list[str], limit: int, max_lines: int, last_line_limit: int | None = None) -> list[str]:
        cleaned = [chunk.strip() for chunk in chunks if chunk.strip()]
        if not cleaned or max_lines <= 0:
            return []
        results: list[str] = []
        remaining = cleaned.copy()
        while remaining and len(results) < max_lines:
            chunk = remaining.pop(0)
            current_limit = last_line_limit if (last_line_limit is not None and len(results) == max_lines - 1) else limit
            wrapper = textwrap.TextWrapper(width=current_limit, break_long_words=True, break_on_hyphens=False)
            wrapped = wrapper.wrap(chunk)
            if not wrapped:
                continue
            for part in wrapped:
                if len(results) >= max_lines:
                    break
                results.append(part.strip())
        if remaining and results:
            remainder = ' '.join(remaining)
            current_limit = last_line_limit if last_line_limit is not None else limit
            results[-1] = _clip(results[-1] + ' ' + remainder, current_limit)
        return results

    lines: list[str] = []

    # ?쒕ぉ? ?꾩껜 ?쒖떆 (?꾩슂???щ윭 以꾨줈 ?섎닠??OK, ?섏?留??꾩껜 ???쒖떆)
    if title:
        # 각 줄마다 다른 글자 수: 1줄(5-6자), 2줄(5-6자), 3줄(8자), 4줄(12자...)
        # 단어 단위로 자연스럽게 끊되, 최소 글자 수 보장
        words = title.split()
        line_limits = [6, 6, 8, 12]  # 각 줄의 최대 글자 수
        line_minimums = [5, 5, 7, 0]  # 각 줄의 최소 글자 수

        current_line = ""
        line_index = 0

        for word in words:
            if line_index >= len(line_limits):
                break

            # 현재 줄이 비어있으면 단어 추가
            if not current_line:
                current_line = word
            # 단어를 추가했을 때 제한을 넘지 않으면 추가
            elif len(current_line + " " + word) <= line_limits[line_index]:
                current_line += " " + word
            else:
                # 최소 글자 수를 만족하는지 확인
                if len(current_line) < line_minimums[line_index]:
                    # 최소 글자 수를 만족할 때까지 단어 추가 (제한 초과해도)
                    current_line += " " + word
                else:
                    # 현재 줄을 저장하고 다음 줄로
                    lines.append(current_line)
                    current_line = word
                    line_index += 1

        # 마지막 줄 추가
        if current_line:
            # 4번째 줄(마지막)은 12자로 제한하고 ... 추가
            if len(lines) == 3:  # 4번째 줄
                if len(current_line) > 12:
                    current_line = current_line[:12] + "..."
                else:
                    current_line = current_line + "..."
            lines.append(current_line)
    else:
        lines.append("No title")

    # 제목이 25자 이상이면 제목만 표시, 짧으면 내용 추가
    if len(title) < 25:
        # 제목이 짧으면 내용 추가
        if len(lines) < 4:
            summary_text = (scene_summary or scene_content or "").strip()
            summary_text = " ".join(summary_text.split())
            summary_text = textwrap.shorten(summary_text, width=80, placeholder='...')
            summary_chunks = textwrap.wrap(summary_text, width=7)
            lines.extend(_add_lines(summary_chunks, 7, 4 - len(lines), last_line_limit=130))

        if len(lines) < 4:
            sentence_chunks = split_regex.split(scene_content)
            lines.extend(_add_lines(sentence_chunks, 7, 4 - len(lines), last_line_limit=130))

        fillers = [
            "다음 장면 보기",
            "바로 확인",
            "지금 신청",
            "속보 클릭"
        ]
        for filler in fillers:
            if len(lines) >= 4:
                break
            if filler not in lines:
                lines.append(filler)

    lines = lines[:4]

    MAX_LAST_LINE_CHARS = 12
    MIN_LAST_LINE_CHARS = 8
    MAX_LAST_LINE_GAP = 0.55

    if lines and len(title) < 25:
        last_line = lines[-1]
        used_tokens = set()
        for existing in lines:
            used_tokens.update(existing.split())

        candidate_tokens: list[str] = []
        for chunk in split_regex.split(scene_content):
            candidate_tokens.extend(chunk.split())

        if len(last_line) < MAX_LAST_LINE_CHARS:
            target_length = int(MAX_LAST_LINE_CHARS * 0.85)
            for token in candidate_tokens:
                if len(last_line) >= MAX_LAST_LINE_CHARS:
                    break
                if token in used_tokens:
                    continue
                candidate = (last_line + ' ' + token).strip() if last_line else token
                if len(candidate) > MAX_LAST_LINE_CHARS:
                    continue
                last_line = candidate
                used_tokens.add(token)
                if len(last_line) >= target_length:
                    break

        remaining_tokens = [token for token in candidate_tokens if token not in used_tokens]
        for token in remaining_tokens:
            if len(last_line) >= int(MAX_LAST_LINE_CHARS * 0.92):
                break
            candidate = (last_line + ' ' + token).strip()
            if len(candidate) > MAX_LAST_LINE_CHARS:
                break
            last_line = candidate
            used_tokens.add(token)

        ellipsis = ''
        if len(last_line) > MAX_LAST_LINE_CHARS:
            last_line = last_line[:MAX_LAST_LINE_CHARS].rstrip()
            ellipsis = '...'
        elif len(last_line) < int(MAX_LAST_LINE_CHARS * MAX_LAST_LINE_GAP):
            ellipsis = '...'
        elif remaining_tokens:
            ellipsis = '...'

        if ellipsis:
            last_line = last_line.rstrip('.').rstrip()
            if not last_line.endswith('...'):
                lines[-1] = f"{last_line}..."
            else:
                lines[-1] = last_line
        else:
            lines[-1] = last_line

    colors = [
        (255, 220, 0),      # ?몃???(Bright Golden Yellow) - 李멸퀬 ?대?吏 1踰?以?
        (120, 255, 60),     # ?곕몢??(Lime Green) - 李멸퀬 ?대?吏 2踰?以?
        (255, 255, 255),    # ?곗깋 (Pure White) - 李멸퀬 ?대?吏 3踰?以?
        (255, 40, 40),      # 鍮④컙??(Bright Red) - 李멸퀬 ?대?吏 4踰?以?
    ]

    colored_lines = []
    for idx, text_line in enumerate(lines):
        colored_lines.append({"text": text_line, "color": colors[idx % len(colors)]})

    return {
        "lines": colored_lines,
        "full_text": " / ".join(line["text"] for line in colored_lines)
    }


def get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """Load Korean font"""
    script_dir = Path(__file__).parent

    font_dir = script_dir / "fonts"
    font_candidates: list[str] = []

    if bold:
        local_bold = sorted(font_dir.glob('*Aggro*B*.ttf')) + sorted(font_dir.glob('SB*B*.ttf'))
        font_candidates.extend(str(p) for p in local_bold)
        font_candidates.extend([
            'C:/Windows/Fonts/SBAggroB.ttf',
            'C:/Windows/Fonts/SB 어그로 B.ttf',
            'C:/Windows/Fonts/Aggravo.ttf',
            'C:/Windows/Fonts/NanumGothicExtraBold.ttf',
            'C:/Windows/Fonts/NanumGothicBold.ttf',
            'C:/Windows/Fonts/malgunbd.ttf',
            '/usr/share/fonts/truetype/nanum/NanumGothicExtraBold.ttf',
            '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf',
        ])
    else:
        local_regular = sorted(font_dir.glob('*.ttf'))
        font_candidates.extend(str(p) for p in local_regular if 'Aggro' not in p.stem)
        font_candidates.extend([
            'C:/Windows/Fonts/NanumGothic.ttf',
            'C:/Windows/Fonts/malgun.ttf',
            '/usr/share/fonts/truetype/nanum/NanumGothic.ttf',
            '/System/Library/Fonts/AppleGothic.ttf',
        ])

    tried: set[str] = set()
    for font_path in font_candidates:
        if not font_path or font_path in tried:
            continue
        tried.add(font_path)
        try:
            candidate = Path(font_path)
            if candidate.exists():
                return ImageFont.truetype(str(candidate), size)
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue

    logger.warning('Korean font not found, falling back to default font')
    return ImageFont.load_default()


def create_thumbnail(image_path: Path, text_lines: list, output_path: Path):
    """Create thumbnail"""
    logger.info("Creating thumbnail...")

    # Load image and keep original aspect ratio
    img = Image.open(image_path)
    original_size = (img.width, img.height)
    logger.info(f"Original image size: {original_size[0]}x{original_size[1]}")

    # Apply effects without changing size
    draw = ImageDraw.Draw(img)

    # Font setup
    lines_config = text_lines["lines"]
    allowed_height = img.height * 0.90  # 嫄곗쓽 ?꾩껜 ?믪씠 ?ъ슜
    font_scale = 13.122  # 글자 크기 50% (26.244 * 0.5)
    base_font_ratio = 0.06
    max_font_size = max(int(img.height * base_font_ratio * font_scale), int(img.height * 0.02))  # ?명듃??硫붽? ?고듃 (960% of height, min 4800 = 3000*1.6)

    x_padding = int(img.width * 0.02)
    bottom_margin = int(img.height * 0.10)
    line_spacing_ratio = 0.12  # 以?媛꾧꺽 理쒖냼?쒖쑝濡?以꾩엫 (?명듃??硫붽? ?고듃 ?덉슜)

    for font_size in range(140, 47, -2):  # 시작 폰트 크기를 140으로 고정
        font = get_font(font_size, bold=True)
        line_spacing = max(int(font_size * line_spacing_ratio), 18)

        metrics = []
        content_height = 0
        max_line_width = 0

        for entry in lines_config:
            line_text = entry["text"]
            bbox = draw.textbbox((0, 0), line_text, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            metrics.append((width, height))
            content_height += height
            max_line_width = max(max_line_width, width)

        if len(lines_config) > 1:
            content_height += line_spacing * (len(lines_config) - 1)

        # ?붾㈃ ??쓽 95%瑜?梨꾩슦?꾨줉 議곗젙 (??苑?李④쾶)
        if content_height <= allowed_height and max_line_width + x_padding * 2 <= img.width * 0.95:
            break
    else:
        font = get_font(font_size, bold=True)
        line_spacing = max(int(font_size * line_spacing_ratio), 16)
        metrics = []
        content_height = 0
        for entry in lines_config:
            line_text = entry["text"]
            bbox = draw.textbbox((0, 0), line_text, font=font)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            metrics.append((width, height))
            content_height += height
        if len(lines_config) > 1:
            content_height += line_spacing * (len(lines_config) - 1)

    # ?띿뒪?몃? ?붾㈃ 以묎컙 ?꾩튂??諛곗튂 (?꾨줈 ????대룞)
    bottom_limit = img.height - int(bottom_margin * 0.3)  # ?섎떒 ?щ갚 ???以꾩엫

    # ?띿뒪???쒖옉 ?꾩튂瑜??붾㈃ 以묎컙(50%)?쇰줈 ?ㅼ젙
    target_ratio = 0.78
    y_offset = int(img.height * target_ratio)

    # 理쒖냼 ?꾩튂瑜?20%濡??ㅼ젙 (?곷떒 媛源뚯씠 諛곗튂 媛??
    top_limit = int(img.height * 0.20)
    if y_offset < top_limit:
        y_offset = top_limit

    # ?ㅼ떆 ?뺤씤: ?꾨옒濡??섏튂吏 ?딅룄濡?
    if y_offset + content_height > bottom_limit:
        y_offset = bottom_limit - content_height

    # 전체를 행간만큼 위로 올리기
    y_offset = y_offset - line_spacing

    outline_color = (0, 0, 0)
    outline_width = max(1, font_size // 24)

    for idx, ((width, height), entry) in enumerate(zip(metrics, lines_config)):
        line_text = entry["text"]
        color = tuple(entry["color"])
        x = x_padding
        if x + width > img.width - x_padding:
            x = max(int(img.width - width - x_padding), x_padding)

        if outline_width:
            for adj_x in range(-outline_width, outline_width + 1):
                for adj_y in range(-outline_width, outline_width + 1):
                    if adj_x == 0 and adj_y == 0:
                        continue
                    draw.text((x + adj_x, y_offset + adj_y), line_text, font=font, fill=outline_color)

        draw.text((x, y_offset), line_text, font=font, fill=color)

        if idx < len(metrics) - 1:
            y_offset += height + line_spacing
        else:
            y_offset += height

    img.save(output_path, quality=95)
    logger.info(f"Thumbnail saved: {output_path} ({img.width}x{img.height})")


def main():
    parser = argparse.ArgumentParser(description="Thumbnail generation")
    parser.add_argument("--folder", "-f", required=True, help="Input folder (e.g., input/folder)")
    parser.add_argument("--output", "-o", help="Output file (default: thumbnail.jpg)")

    args = parser.parse_args()

    script_dir = Path(__file__).parent
    raw_folder = args.folder.strip().strip('"').strip("'")
    if not raw_folder:
        logger.error("Folder path is empty after stripping quotes")
        return

    candidate = Path(raw_folder)
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
        if not candidate.exists():
            candidate_alt = (script_dir / raw_folder).resolve()
            if candidate_alt.exists():
                candidate = candidate_alt

    folder = candidate

    if not folder.exists():
        input_root = script_dir / "input"
        target_key = _normalize_key(Path(raw_folder).name or raw_folder)
        matches = []
        if input_root.exists():
            for child in input_root.iterdir():
                if child.is_dir() and _normalize_key(child.name) == target_key:
                    matches.append(child.resolve())
        if len(matches) == 1:
            folder = matches[0]
        elif len(matches) > 1:
            logger.info(f"Multiple folders matched {raw_folder!r}: {[c.name for c in matches]}")
            folder = matches[0]
        else:
            logger.error(f"Folder not found: {folder}")
            return

    folder = folder.resolve()

    if args.output:
        output_path = Path(args.output.strip().strip('"').strip("'"))
        if not output_path.is_absolute():
            output_path = (folder / output_path).resolve()
    else:
        output_path = folder / "thumbnail.jpg"

    try:
        story_data = get_story_data(folder)
        logger.info(f"Title: {story_data['title']}")
        logger.info(f"Scene 1 title: {story_data['scene_title']}")

        scene1_image = find_scene1_image(folder)

        text_lines = create_hooking_text(story_data)
        logger.info("Thumbnail text:")
        logger.info(f"   {text_lines['full_text']}")

        create_thumbnail(scene1_image, text_lines, output_path)

        logger.info(f"Complete! Thumbnail: {output_path}")
        print(f"\nThumbnail created: {output_path}")

    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()













