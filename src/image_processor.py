"""Pillow helpers: load images safely and prepare them for OCR."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageStat

MAX_UPSCALE = 3.0
DARK_THEME_THRESHOLD = 110  # mean grayscale below this => likely dark mode


def load_image(path: Path) -> Image.Image:
    """Open an image fully into memory and apply EXIF orientation."""
    with Image.open(path) as img:
        img.load()
        return ImageOps.exif_transpose(img)


def _flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Composite transparent images onto white, otherwise just convert to RGB."""
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )
    if has_alpha:
        rgba = img.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return img.convert("RGB")


def preprocess_for_ocr(image: Image.Image, min_width: int = 1600) -> Image.Image:
    """Grayscale, invert dark themes, upscale small images, boost contrast."""
    gray = ImageOps.grayscale(_flatten_to_rgb(image))

    if ImageStat.Stat(gray).mean[0] < DARK_THEME_THRESHOLD:
        gray = ImageOps.invert(gray)

    if gray.width < min_width:
        scale = min(min_width / gray.width, MAX_UPSCALE)
        new_size = (round(gray.width * scale), round(gray.height * scale))
        gray = gray.resize(new_size, Image.Resampling.LANCZOS)

    return ImageOps.autocontrast(gray)