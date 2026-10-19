"""Find screenshots in a folder you choose (never scans the whole computer)."""
from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import Path
from typing import Iterable

from config import Settings


def is_supported_image(path: Path, settings: Settings) -> bool:
    return path.suffix.lower() in settings.supported_extensions


def matches_screenshot_pattern(filename: str, patterns: Iterable[str]) -> bool:
    """Case-insensitive glob match, e.g. 'Screenshot (42).png' vs 'Screenshot*'."""
    name = filename.lower()
    return any(fnmatchcase(name, pattern.lower()) for pattern in patterns)


def is_inside(path: Path, folder: Path) -> bool:
    """True if `path` is `folder` or lives somewhere beneath it."""
    try:
        return path.resolve().is_relative_to(folder.resolve())
    except (OSError, ValueError):
        return False


def scan_folder(
    source: Path,
    settings: Settings,
    *,
    recursive: bool = False,
    require_pattern: bool = True,
    exclude_dirs: Iterable[Path] = (),
) -> list[Path]:
    """List candidate screenshots in `source`.

    require_pattern=False accepts every supported image regardless of its name.
    Anything inside `exclude_dirs` (e.g. the destination) is skipped so
    already-organized files are never processed again.
    """
    if not source.is_dir():
        raise NotADirectoryError(f"Source folder not found: {source}")

    excluded = [folder.resolve() for folder in exclude_dirs]
    entries = source.rglob("*") if recursive else source.iterdir()

    found: list[Path] = []
    for path in entries:
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        if not is_supported_image(path, settings):
            continue
        if require_pattern and not matches_screenshot_pattern(
            path.name, settings.screenshot_name_patterns
        ):
            continue
        resolved = path.resolve()
        if any(resolved.is_relative_to(folder) for folder in excluded):
            continue
        found.append(path)
    return sorted(found, key=lambda p: p.name.lower())


def validate_manual_selection(
    paths: Iterable[Path], settings: Settings
) -> tuple[list[Path], list[str]]:
    """Accept hand-picked images regardless of filename; report problems."""
    valid: list[Path] = []
    problems: list[str] = []
    for path in paths:
        if not path.is_file():
            problems.append(f"Not a file: {path}")
        elif not is_supported_image(path, settings):
            problems.append(f"Unsupported file type: {path.name}")
        else:
            valid.append(path)
    return valid, problems