"""Generate two fake screenshots in sample_images/ for testing."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent / "sample_images"


def get_font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def make_image(filename: str, heading: str, body: list[str]) -> None:
    image = Image.new("RGB", (1400, 720), "white")
    draw = ImageDraw.Draw(image)
    draw.text((60, 50), heading, font=get_font(40), fill="black")
    y = 180
    for line in body:
        draw.text((60, y), line, font=get_font(26), fill="black")
        y += 50
    OUT_DIR.mkdir(exist_ok=True)
    image.save(OUT_DIR / filename)


if __name__ == "__main__":
    make_image(
        "Screenshot (42).png",
        "Python Exception Handling \u2014 Using try and except blocks",
        ["try:", "    result = 10 / 0", "except ZeroDivisionError:",
         "    print('Cannot divide by zero')"],
    )
    make_image(
        "Screenshot (43).png",
        "Database Management Systems \u2014 Assignment 02",
        ["Normalize the schema to third normal form.",
         "Submit the ER diagram before the deadline."],
    )
    print(f"Created sample images in {OUT_DIR}")