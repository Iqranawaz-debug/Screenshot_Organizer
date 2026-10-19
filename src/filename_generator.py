"""Build safe, Windows-compatible filenames from titles and dates."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from config import Settings

INVALID_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def sanitize_stem(title: str, fallback: str = "Screenshot") -> str:
    """Return a filename-safe stem: words joined by underscores."""
    text = INVALID_CHARS_RE.sub(" ", title)
    text = re.sub(r"[^\w\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    if not text:
        text = fallback
    if text.upper() in WINDOWS_RESERVED:
        text = f"{text}_file"
    return text


def build_filename(
    title: str | None, capture_date: date, extension: str, settings: Settings
) -> str:
    """Create Title_YYYY-MM-DD.ext, trimmed to the configured maximum length."""
    ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
    suffix = f"_{capture_date.isoformat()}{ext}"

    stem = sanitize_stem(title or settings.fallback_title, settings.fallback_title)
    max_stem = max(settings.max_filename_length - len(suffix), 10)

    if len(stem) > max_stem:
        truncated = stem[:max_stem]
        # Avoid cutting a word in half when a word boundary is available.
        if stem[max_stem] != "_" and "_" in truncated:
            truncated = truncated[: truncated.rfind("_")]
        stem = truncated.strip("_-") or settings.fallback_title

    return f"{stem}{suffix}"


def unique_path(directory: Path, filename: str, reserved: set[str] | None = None) -> Path:
    """Return a path that does not exist yet, adding _02, _03... on collisions.

    `reserved` holds names already planned in this batch but not yet created.
    Comparison is case-insensitive because Windows filenames are.
    """
    taken = {name.lower() for name in (reserved or set())}
    candidate = directory / filename
    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 2
    while candidate.exists() or candidate.name.lower() in taken:
        candidate = directory / f"{stem}_{counter:02d}{suffix}"
        counter += 1
    return candidate