"""Optimize images before uploading to WordPress.

- Converts PNG/WebP to high-quality JPEG
- Strips ALL metadata (EXIF, IPTC, XMP) including AI generation info
- Renames files to random alphanumeric strings
"""

import os
import random
import string
from PIL import Image


def optimize_for_upload(image_path, output_dir=None, quality=90):
    """Optimize an image: compress to JPEG, strip metadata, random filename.

    Args:
        image_path: Path to the source image.
        output_dir: Directory for optimized file. Uses same dir if None.
        quality: JPEG quality 1-100 (90 = high quality, good compression).

    Returns:
        dict with 'success' (bool), 'path' (str) or 'error' (str).
    """
    try:
        if not os.path.isfile(image_path):
            return {"success": False, "error": f"File not found: {image_path}"}

        if output_dir is None:
            output_dir = os.path.dirname(image_path)
        os.makedirs(output_dir, exist_ok=True)

        img = Image.open(image_path)

        # Convert to RGB (drop alpha channel if present)
        if img.mode in ("RGBA", "P", "LA"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1] if "A" in img.mode else None)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Create a clean new image (strips ALL metadata: EXIF, IPTC, XMP, AI tags)
        clean_img = Image.new("RGB", img.size)
        clean_img.putdata(list(img.getdata()))

        # Random filename: only digits and lowercase letters
        random_name = _random_filename()
        out_path = os.path.join(output_dir, f"{random_name}.jpg")

        clean_img.save(out_path, "JPEG", quality=quality, optimize=True)

        original_size = os.path.getsize(image_path)
        new_size = os.path.getsize(out_path)

        return {
            "success": True,
            "path": out_path,
            "original_size": original_size,
            "new_size": new_size,
        }

    except Exception as e:
        return {"success": False, "error": f"Optimization failed: {e}"}


def _random_filename(length=16):
    """Generate a random filename from digits and lowercase letters."""
    chars = string.ascii_lowercase + string.digits
    return "".join(random.choice(chars) for _ in range(length))
