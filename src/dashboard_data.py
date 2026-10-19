"""Dashboard adapters. No processing, watcher threads, or configuration writes."""
from __future__ import annotations

import base64
import io
from datetime import date, datetime, timedelta
from pathlib import Path
import os
import sqlite3
import subprocess
import sys

from PIL import Image, ImageOps, UnidentifiedImageError

from src.background_service import load_config
from src.metadata_store import MetadataStore, ScreenshotRecord

DONE = "('copied','moved')"


def _ro(path: Path):
    return sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=3)


def configuration(root: Path):
    try:
        return load_config(root / 'automation.json'), None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return None, f'Automation configuration unavailable: {exc}'


def metrics(path: Path) -> dict:
    """Aggregate the entire database, not just the gallery's latest records."""
    result = dict(total=0, today=0, categorized=0, uncategorized=0, errors=0, categories={})
    if not path.exists():
        return result
    with _ro(path) as db:
        rows = db.execute("SELECT category, COUNT(*) FROM screenshots WHERE status IN ('copied','moved') GROUP BY category").fetchall()
        for category, count in rows:
            name = category or 'Uncategorized'
            result['categories'][name] = result['categories'].get(name, 0) + count
        result['total'] = sum(count for _, count in rows)
        result['uncategorized'] = sum(count for category, count in rows if not category or category == 'Uncategorized')
        result['categorized'] = result['total'] - result['uncategorized']
        result['today'] = db.execute("SELECT COUNT(*) FROM screenshots WHERE status IN ('copied','moved') AND date(processed_at,'localtime')=?", (datetime.now().date().isoformat(),)).fetchone()[0]
        result['errors'] = db.execute("SELECT COUNT(*) FROM screenshots WHERE status='error'").fetchone()[0]
    return result


def daily_counts(path: Path, days: int = 30, uncategorized: bool = False) -> dict[date, int]:
    """Screenshots processed per local calendar day, oldest first, zero-filled."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    counts = {start + timedelta(days=i): 0 for i in range(days)}
    if not path.exists():
        return counts
    extra = " AND (category IS NULL OR category='Uncategorized')" if uncategorized else ''
    with _ro(path) as db:
        rows = db.execute(
            f"SELECT date(processed_at,'localtime') AS d, COUNT(*) FROM screenshots "
            f"WHERE status IN ('copied','moved') AND date(processed_at,'localtime')>=?{extra} GROUP BY d",
            (start.isoformat(),)).fetchall()
    for day, count in rows:
        try:
            key = date.fromisoformat(day)
        except (TypeError, ValueError):
            continue
        if key in counts:
            counts[key] = count
    return counts


def records(store: MetadataStore, query='', category=None, limit=60):
    if query.strip():
        return store.search(query, category=category, limit=limit)
    if not category:
        return store.recent(limit)
    if not store.db_path.exists():
        return []
    # Existing recent() has no category filter: filter before LIMIT, not after.
    with _ro(store.db_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute('SELECT * FROM screenshots WHERE category=? ORDER BY id DESC LIMIT ?', (category, limit)).fetchall()
    return [ScreenshotRecord(**dict(row)) for row in rows]


def preview(path: str | None, size=(900, 600)):
    """Decode a local image safely. No arbitrary file content or remote URLs served."""
    if not path:
        return None
    source = Path(path)
    if (not source.is_absolute() or str(source).startswith(('\\\\', '//'))
            or source.suffix.lower() not in {'.png', '.jpg', '.jpeg', '.webp'}):
        return None
    try:
        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original)
            image.thumbnail(size)
            return image.convert('RGB')
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return None


def thumb_b64(path: str | None, size=(128, 88)) -> str | None:
    """Small cropped JPEG as a data URI for the activity table."""
    image = preview(path, (640, 480))
    if image is None:
        return None
    buffer = io.BytesIO()
    ImageOps.fit(image, size).save(buffer, 'JPEG', quality=70)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def folder_size(folder: str | Path | None) -> int:
    """Total bytes under a folder (0 if missing)."""
    if not folder:
        return 0
    total = 0
    for root, _dirs, files in os.walk(folder):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def format_bytes(value: float) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if value < 1024 or unit == 'GB':
            return f'{value:.0f} {unit}' if unit == 'B' else f'{value:.1f} {unit}'
        value /= 1024


def relative_time(iso: str | None) -> str:
    """'2 min ago' for recent items, local date/time for older ones."""
    if not iso:
        return '—'
    try:
        moment = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    if moment.tzinfo is None:
        moment = moment.astimezone()  # naive -> assume local
    local = moment.astimezone()
    seconds = (datetime.now().astimezone() - local).total_seconds()
    if seconds < 60:
        return 'just now'
    if seconds < 3600:
        return f'{int(seconds // 60)} min ago'
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f'{hours} hour{"s" if hours != 1 else ""} ago'
    if seconds < 7 * 86400:
        days = int(seconds // 86400)
        return f'{days} day{"s" if days != 1 else ""} ago'
    return local.strftime('%b %d, %Y')


def control(root: Path, action: str):
    # 'scan' needs a matching command in background.py (see README notes).
    if action not in {'start', 'stop', 'scan'}:
        raise ValueError('Unsupported automation action')
    result = subprocess.run([sys.executable, str(root / 'background.py'), action],
                            cwd=root, capture_output=True, text=True, timeout=100,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def warnings(root: Path) -> list[str]:
    path = root / 'runtime' / 'automation.log'
    if not path.exists():
        return []
    with path.open('rb') as handle:
        handle.seek(max(0, path.stat().st_size - 32000))
        lines = handle.read().decode('utf-8', errors='replace').splitlines()
    return [line for line in lines if any(level in line for level in (' WARNING ', ' ERROR ', ' CRITICAL '))][-12:]


def startup_status(root: Path) -> str:
    if os.name != 'nt':
        return 'Windows startup is unavailable on this platform.'
    result = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(root / 'scripts' / 'Startup-Automation.ps1'), '-Action', 'Verify'],
                            capture_output=True, text=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        return 'Startup status could not be queried. Use Startup-Automation.ps1 -Action Verify locally.'
    return result.stdout.strip() or 'No startup status returned.'