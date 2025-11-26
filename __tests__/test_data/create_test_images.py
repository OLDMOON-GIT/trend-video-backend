"""
Test image generation script for regression tests
"""
from PIL import Image, ImageDraw, ImageFont
import os

def create_test_image(filename, text, color):
    """Create a simple colored test image with text"""
    img = Image.new('RGB', (512, 512), color=color)
    draw = ImageDraw.Draw(img)

    # Draw text in the center
    try:
        # Try to use a system font
        font = ImageFont.truetype("arial.ttf", 40)
    except:
        # Fall back to default font
        font = ImageFont.load_default()

    # Get text bbox and center it
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (512 - text_width) // 2
    y = (512 - text_height) // 2

    draw.text((x, y), text, fill='white', font=font)
    img.save(filename)
    print(f"[OK] Created: {filename}")

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))

# Create test images
print("Creating test images...")

# Longform test images (2 scenes)
create_test_image(os.path.join(script_dir, 'longform_01.jpg'), 'Scene 1', (100, 150, 200))
create_test_image(os.path.join(script_dir, 'longform_02.jpg'), 'Scene 2', (200, 100, 150))

# Shortform test images (2 scenes)
create_test_image(os.path.join(script_dir, 'shortform_01.jpg'), 'Scene 1', (150, 200, 100))
create_test_image(os.path.join(script_dir, 'shortform_02.jpg'), 'Scene 2', (200, 150, 100))

print("\nTest images created successfully!")
print(f"Location: {script_dir}")
