"""Logic behind the dashboard, kept free of Streamlit so it can be tested."""
from __future__ import annotations

import logging
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from config import Settings
from src.duplicate_detector import build_destination_index
from src.folder_watcher import FolderWatcher
from src.metadata_store import MetadataStore
from src.organizer import (
    ConfirmationRequiredError, PlannedItem, execute_plan,
    plan_screenshots, validate_folders,
)
from src.screenshot_detector import scan_folder, validate_manual_selection
from src.title_generators import TitleGenerator

logger = logging.getLogger(__name__)


def parse_path_lines(text: str) -> list[Path]:
    """One path per line; blank lines ignored; surrounding quotes stripped."""
    paths: list[Path] = []
    for line in text.splitlines():
        cleaned = line.strip().strip('"').strip("'")
        if cleaned:
            paths.append(Path(cleaned))
    return paths


def build_plan(
    source: Path | None,
    destination: Path,
    settings: Settings,
    *,
    extra_files: Iterable[Path] = (),
    include_all_images: bool = False,
    recursive: bool = False,
    store: MetadataStore | None = None,
    title_generator: TitleGenerator | None = None,
) -> tuple[list[PlannedItem], list[str]]:
    """Scan, OCR and plan. Touches nothing on disk. Returns (items, warnings).

    Raises FolderConfigError (unsafe/nested folders) or NotADirectoryError
    (missing source). Raises TesseractNotAvailableError if Tesseract is missing.
    """
    warnings: list[str] = []
    sources: list[Path] = []

    valid_extra, problems = validate_manual_selection(extra_files, settings)
    warnings.extend(problems)
    sources.extend(valid_extra)

    if source is not None:
        validate_folders(source, destination)
        sources.extend(scan_folder(
            source, settings,
            recursive=recursive,
            require_pattern=not include_all_images,
            exclude_dirs=[destination],
        ))

    unique: dict[str, Path] = {}
    for path in sources:
        unique.setdefault(str(path.resolve()).lower(), path)

    cache = store.hash_cache() if store is not None else None
    index = build_destination_index(destination, settings.supported_extensions, cache=cache)
    items = plan_screenshots(
        list(unique.values()), destination, settings, index=index, title_generator=title_generator
    )
    return items, warnings


@dataclass
class ApplyOutcome:
    items: list[PlannedItem]
    history_error: str | None = None


def apply_approved(
    items: list[PlannedItem],
    approved: Iterable[int],
    destination: Path,
    settings: Settings,
    *,
    mode: str = "copy",
    confirm_move: bool = False,
    store: MetadataStore | None = None,
) -> ApplyOutcome:
    """Copy (or, with confirmation, move) ONLY the approved items.

    `approved` holds positions in `items`. Unapproved items are left untouched
    (status stays "planned"). Duplicates that appeared since the preview are skipped.
    """
    if mode == "move" and not confirm_move:
        raise ConfirmationRequiredError("Moving files requires explicit confirmation.")

    positions = sorted({i for i in approved if 0 <= i < len(items)})
    selected = [items[i] for i in positions if items[i].status == "planned"]

    cache = store.hash_cache() if store is not None else None
    index = build_destination_index(destination, settings.supported_extensions, cache=cache)
    runnable: list[PlannedItem] = []
    for item in selected:
        existing = index.find(item.file_hash) if item.file_hash else None
        if existing is not None:
            item.status = "skipped"
            item.message = f"Duplicate of {existing} (appeared after the preview)"
        else:
            runnable.append(item)

    execute_plan(runnable, mode=mode, dry_run=False, confirm_move=confirm_move)

    history_error: str | None = None
    if store is not None:
        try:
            store.record_many(selected)
        except (sqlite3.Error, OSError) as exc:
            logger.exception("Could not save history")
            history_error = str(exc)
    return ApplyOutcome(items=selected, history_error=history_error)


class WatcherController:
    """Owns at most one FolderWatcher and keeps recent results for the UI.

    Always copy mode. Safe to call from Streamlit reruns because results are
    guarded by a lock (the watcher's worker thread appends to them).
    """

    def __init__(self, settings: Settings, store: MetadataStore | None = None,
                 max_results: int = 200) -> None:
        self._settings = settings
        self._store = store
        self._results: deque[PlannedItem] = deque(maxlen=max_results)
        self._lock = threading.Lock()
        self._watcher: FolderWatcher | None = None
        self.source: Path | None = None
        self.destination: Path | None = None
        self.dry_run: bool = True

    @property
    def is_running(self) -> bool:
        return self._watcher is not None and self._watcher.is_running

    def start(self, source: Path, destination: Path, *,
              dry_run: bool = True, include_all_images: bool = False) -> None:
        """Raises RuntimeError if already running, FolderConfigError/NotADirectoryError if unsafe."""
        if self.is_running:
            raise RuntimeError("The watcher is already running.")
        watcher = FolderWatcher(
            source, destination, self._settings,
            mode="copy", dry_run=dry_run,
            require_pattern=not include_all_images,
            on_result=self._add_result, store=self._store,
        )
        watcher.start()
        with self._lock:
            self._results.clear()
        self._watcher = watcher
        self.source, self.destination, self.dry_run = source, destination, dry_run

    def stop(self) -> None:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None

    def _add_result(self, item: PlannedItem) -> None:
        with self._lock:
            self._results.appendleft(item)

    def recent_results(self) -> list[PlannedItem]:
        """Newest first."""
        with self._lock:
            return list(self._results)
