"""SQLite storage for processed-screenshot records, plus simple text search."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from src.organizer import PlannedItem

logger = logging.getLogger(__name__)

# Dry runs and skipped duplicates are deliberately NOT recorded.
RECORDED_STATUSES = frozenset({"copied", "moved", "error"})
SEARCH_COLUMNS = ("ocr_text", "title", "new_name", "original_name", "category")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS screenshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    processed_at     TEXT NOT NULL,
    original_name    TEXT NOT NULL,
    new_name         TEXT,
    source_path      TEXT NOT NULL,
    destination_path TEXT,
    ocr_text         TEXT,
    title            TEXT,
    title_source     TEXT,
    capture_date     TEXT,
    date_source      TEXT,
    category         TEXT,
    file_hash        TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL,
    message          TEXT,
    dest_size        INTEGER,
    dest_mtime_ns    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_screenshots_hash ON screenshots(file_hash);
CREATE INDEX IF NOT EXISTS idx_screenshots_status ON screenshots(status);
"""

INSERT_SQL = """
INSERT INTO screenshots (
    processed_at, original_name, new_name, source_path, destination_path,
    ocr_text, title, title_source, capture_date, date_source, category,
    file_hash, status, message, dest_size, dest_mtime_ns
) VALUES (
    :processed_at, :original_name, :new_name, :source_path, :destination_path,
    :ocr_text, :title, :title_source, :capture_date, :date_source, :category,
    :file_hash, :status, :message, :dest_size, :dest_mtime_ns
)
"""


@dataclass(frozen=True)
class ScreenshotRecord:
    id: int
    processed_at: str
    original_name: str
    new_name: str | None
    source_path: str
    destination_path: str | None
    ocr_text: str | None
    title: str | None
    title_source: str | None
    capture_date: str | None
    date_source: str | None
    category: str | None
    file_hash: str
    status: str
    message: str | None
    dest_size: int | None
    dest_mtime_ns: int | None


def _to_record(row: sqlite3.Row) -> ScreenshotRecord:
    return ScreenshotRecord(**{key: row[key] for key in row.keys()})


def _escape_like(term: str) -> str:
    """Make %, _ and \\ match literally inside a LIKE pattern."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def make_snippet(text: str | None, terms: Iterable[str], width: int = 70) -> str:
    """A short single-line excerpt around the first matching term."""
    if not text:
        return ""
    flat = " ".join(text.split())
    lowered = flat.lower()
    hits = [lowered.find(term.lower()) for term in terms if term]
    hits = [pos for pos in hits if pos >= 0]
    start = max(min(hits) - width // 3, 0) if hits else 0
    end = min(start + width, len(flat))
    snippet = flat[start:end].strip()
    return f"{'...' if start > 0 else ''}{snippet}{'...' if end < len(flat) else ''}"


class MetadataStore:
    """All database access lives here. Nothing is created until the first write."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    # ---------- internals ----------
    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """Short-lived connection: safe to use from any thread."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(SCHEMA_SQL)
            with conn:  # commit on success, roll back on error
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _row_values(item: PlannedItem) -> dict[str, object]:
        dest_size = dest_mtime_ns = None
        if item.status in ("copied", "moved") and item.destination is not None:
            try:
                stat = item.destination.stat()
                dest_size, dest_mtime_ns = stat.st_size, stat.st_mtime_ns
            except OSError:
                pass
        return {
            "processed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "original_name": item.original_name,
            "new_name": item.new_name or None,
            "source_path": str(item.source.resolve()),
            "destination_path": str(item.destination.resolve()) if item.destination else None,
            "ocr_text": item.ocr_text or None,
            "title": item.title,
            "title_source": item.title_source or None,
            "capture_date": item.date_value.isoformat() if item.date_value else None,
            "date_source": item.date_source or None,
            "category": item.category or None,
            "file_hash": item.file_hash or "",
            "status": item.status,
            "message": item.message or None,
            "dest_size": dest_size,
            "dest_mtime_ns": dest_mtime_ns,
        }

    # ---------- writing ----------
    def record_many(self, items: Iterable[PlannedItem]) -> list[int]:
        """Save every item with a recordable status; returns the new row ids."""
        rows = [self._row_values(i) for i in items if i.status in RECORDED_STATUSES]
        if not rows:
            return []
        ids: list[int] = []
        with self._session() as conn:
            for values in rows:
                ids.append(int(conn.execute(INSERT_SQL, values).lastrowid))
        return ids

    def record(self, item: PlannedItem) -> int | None:
        ids = self.record_many([item])
        return ids[0] if ids else None

    # ---------- reading ----------
    def count(self) -> int:
        if not self.db_path.exists():
            return 0
        with self._session() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0])

    def recent(self, limit: int = 20) -> list[ScreenshotRecord]:
        if not self.db_path.exists():
            return []
        with self._session() as conn:
            rows = conn.execute(
                "SELECT * FROM screenshots ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [_to_record(row) for row in rows]

    def search(
        self, query: str, *, category: str | None = None, limit: int = 50
    ) -> list[ScreenshotRecord]:
        """Every word in `query` must appear somewhere in the searchable columns."""
        terms = query.split()
        if not terms or not self.db_path.exists():
            return []

        clauses: list[str] = []
        params: list[object] = []
        for term in terms:
            like = f"%{_escape_like(term)}%"
            group = " OR ".join(f"{col} LIKE ? ESCAPE '\\'" for col in SEARCH_COLUMNS)
            clauses.append(f"({group})")
            params.extend([like] * len(SEARCH_COLUMNS))

        sql = "SELECT * FROM screenshots WHERE " + " AND ".join(clauses)
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._session() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_to_record(row) for row in rows]

    def hash_cache(self) -> dict[str, tuple[int, int, str]]:
        """str(destination path) -> (size, mtime_ns, sha256) for copied files."""
        if not self.db_path.exists():
            return {}
        with self._session() as conn:
            rows = conn.execute(
                "SELECT destination_path, dest_size, dest_mtime_ns, file_hash "
                "FROM screenshots "
                "WHERE status IN ('copied', 'moved') AND destination_path IS NOT NULL "
                "AND dest_size IS NOT NULL AND dest_mtime_ns IS NOT NULL "
                "AND file_hash <> '' ORDER BY id"
            ).fetchall()
        return {row[0]: (row[1], row[2], row[3]) for row in rows}
