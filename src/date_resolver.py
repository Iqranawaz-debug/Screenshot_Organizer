"""Decide which date to put in the filename, and record where it came from."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from PIL import Image

from src.models import DateInfo

EXIF_IFD_POINTER = 0x8769
TAG_DATETIME_ORIGINAL = 0x9003
TAG_DATETIME = 0x0132


def _parse_exif_date(value: object) -> date | None:
    try:
        return datetime.strptime(str(value).strip()[:19], "%Y:%m:%d %H:%M:%S").date()
    except ValueError:
        return None


def resolve_capture_date(path: Path) -> DateInfo:
    """EXIF original capture time > EXIF DateTime > file modified date.

    Text printed inside the screenshot is deliberately never used.
    """
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            original = None
            try:
                original = exif.get_ifd(EXIF_IFD_POINTER).get(TAG_DATETIME_ORIGINAL)
            except Exception:  # noqa: BLE001 - older/odd files may lack the IFD
                original = None
            parsed = _parse_exif_date(original) if original else None
            if parsed:
                return DateInfo(parsed, "exif_datetime_original")

            modified = exif.get(TAG_DATETIME)
            parsed = _parse_exif_date(modified) if modified else None
            if parsed:
                return DateInfo(parsed, "exif_datetime")
    except (OSError, ValueError, AttributeError):
        pass  # fall through to filesystem date

    mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
    return DateInfo(mtime, "file_modified")