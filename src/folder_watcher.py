"""Real-time screenshot monitoring with watchdog.

Nothing runs at import time. Call FolderWatcher.start() / .stop() yourself.
Threading model:
  * watchdog's observer thread  -> tiny handler that only queues paths
  * one worker thread           -> waits for the file, plans, then applies
"""
from __future__ import annotations

import logging
import hashlib
import os
import queue
import sqlite3
import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import PROJECT_ROOT, Settings
from src.instance_lock import InstanceLock
import src.duplicate_detector
from src.metadata_store import MetadataStore
from src.organizer import (
    ConfirmationRequiredError, PlannedItem, execute_plan,
    plan_screenshots, validate_folders,
)
from src.screenshot_detector import (
    is_inside, is_supported_image, matches_screenshot_pattern,
)

logger = logging.getLogger(__name__)


def _is_readable(path: Path) -> bool:
    """A locked or still-open file usually fails a plain read."""
    try:
        with open(path, "rb") as handle:
            handle.read(1)
        return True
    except OSError:
        return False


def wait_until_stable(
    path: Path,
    *,
    interval: float = 0.5,
    stable_checks: int = 3,
    timeout: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    """Return True once the file stops changing and can be read.

    Returns False if the file disappears, stays empty/locked until `timeout`,
    or `should_stop()` becomes true.
    """
    deadline = clock() + timeout
    last_signature: tuple[int, int] | None = None
    stable_count = 0

    while clock() < deadline:
        if should_stop is not None and should_stop():
            return False
        try:
            stat = path.stat()
        except FileNotFoundError:
            return False
        except OSError:
            stat = None

        if stat is not None and stat.st_size > 0:
            signature = (stat.st_size, stat.st_mtime_ns)
            if signature == last_signature:
                stable_count += 1
            else:
                stable_count = 0
                last_signature = signature
            if stable_count >= stable_checks and _is_readable(path):
                return True
        else:
            stable_count = 0
            last_signature = None
        sleep(interval)
    return False


class _ScreenshotEventHandler(FileSystemEventHandler):
    """Keep this tiny: it runs on watchdog's thread."""

    def __init__(self, watcher: "FolderWatcher") -> None:
        super().__init__()
        self._watcher = watcher

    def on_created(self, event) -> None:
        if not event.is_directory:
            self._watcher.submit(Path(os.fsdecode(event.src_path)))

    def on_moved(self, event) -> None:
        if not event.is_directory:  # temp-name -> final-name renames land here
            self._watcher.submit(Path(os.fsdecode(event.dest_path)))


class FolderWatcher:
    def __init__(
        self,
        source: Path,
        destination: Path,
        settings: Settings,
        *,
        mode: str = "copy",
        dry_run: bool = True,
        confirm_move: bool = False,
        require_pattern: bool = True,
        on_result: Callable[[PlannedItem], None] | None = None,
        store: MetadataStore | None = None,
        stable_interval: float = 0.5,
        stable_checks: int = 3,
        stable_timeout: float = 30.0,
    ) -> None:
        validate_folders(source, destination)  # raises FolderConfigError
        if mode not in ("copy", "move"):
            raise ValueError("mode must be 'copy' or 'move'")
        if mode == "move" and not dry_run and not confirm_move:
            raise ConfirmationRequiredError(
                "Watching in move mode requires explicit confirmation."
            )

        self.source = source
        self.destination = destination
        self.settings = settings
        self.mode = mode
        self.dry_run = dry_run
        self.confirm_move = confirm_move
        self.require_pattern = require_pattern
        self._on_result = on_result
        self._store = store
        self._stable_interval = stable_interval
        self._stable_checks = stable_checks
        self._stable_timeout = stable_timeout

        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._observer: Observer | None = None
        self._worker: threading.Thread | None = None
        self._index: src.duplicate_detector.HashIndex | None = None
        source_key = hashlib.sha256(str(source.resolve()).lower().encode()).hexdigest()
        self._instance_lock = InstanceLock(PROJECT_ROOT / "runtime" / f"watcher-{source_key}.lock")

    # ---------- public control ----------
    @property
    def is_running(self) -> bool:
        return (self._observer is not None and self._observer.is_alive()
                and self._worker is not None and self._worker.is_alive())

    def start(self) -> None:
        if self.is_running:
            return
        if not self._instance_lock.acquire():
            raise RuntimeError("Another watcher already monitors this source folder. Stop it first.")
        try:
            self._start()
        except Exception:
            self.stop()
            raise

    def _start(self) -> None:
        if self.is_running:
            return
        if not self.source.is_dir():
            raise NotADirectoryError(f"Source folder not found: {self.source}")

        self._stop_event.clear()
        self._queue = queue.Queue()
        self._pending.clear()
        # Real runs share one hash index; dry runs rebuild it each time so a
        # file that was never actually copied is never treated as existing.
        self._index = None if self.dry_run else src.duplicate_detector.build_destination_index(
            self.destination,
            self.settings.supported_extensions,
            cache=self._store.hash_cache() if self._store is not None else None,
        )

        self._worker = threading.Thread(
            target=self._run, args=(self._queue,), name="screenshot-worker", daemon=True
        )
        self._worker.start()
        self._observer = Observer()
        self._observer.schedule(_ScreenshotEventHandler(self), str(self.source), recursive=False)
        self._observer.start()
        logger.info("Watcher started on %s (dry_run=%s, mode=%s)",
                    self.source, self.dry_run, self.mode)

    def stop(self) -> None:
        self._stop_event.set()
        if self._observer is not None and self._observer.is_alive():
            self._observer.stop()
            self._observer.join()
        self._queue.put(None)
        if self._worker is not None:
            self._worker.join()  # let an in-flight copy/history write finish
        self._observer = None
        self._worker = None
        with self._lock:
            self._pending.clear()
        self._instance_lock.release()
        logger.info("Watcher stopped")

    # ---------- event intake ----------
    def _is_candidate(self, path: Path) -> bool:
        if not is_supported_image(path, self.settings):
            return False
        if self.require_pattern and not matches_screenshot_pattern(
            path.name, self.settings.screenshot_name_patterns
        ):
            return False
        return not is_inside(path, self.destination)  # never re-process output

    def submit(self, path: Path) -> bool:
        """Queue a path unless it is irrelevant or already waiting/processing."""
        if not self._is_candidate(path):
            return False
        key = str(path.resolve()).lower()
        with self._lock:
            if key in self._pending:
                return False
            self._pending.add(key)
        self._queue.put(path)
        logger.info("Queued %s", path)
        return True

    # ---------- worker ----------
    def _run(self, work_queue: "queue.Queue[Path | None]") -> None:
        while True:
            path = work_queue.get()
            if path is None:
                break
            key = str(path.resolve()).lower()
            try:
                if not self._stop_event.is_set():
                    self._process(path)
            except Exception as exc:  # noqa: BLE001 - keep the watcher alive
                logger.exception("Failed to process %s", path)
                self._report(PlannedItem(source=path, status="error", message=str(exc)))
            finally:
                with self._lock:
                    self._pending.discard(key)

    def _process(self, path: Path) -> None:
        ready = wait_until_stable(
            path,
            interval=self._stable_interval,
            stable_checks=self._stable_checks,
            timeout=self._stable_timeout,
            should_stop=self._stop_event.is_set,
        )
        if not ready:
            self._report(PlannedItem(
                source=path, status="skipped",
                message="File vanished, stayed empty/locked, or the watcher stopped.",
            ))
            return

        items = plan_screenshots([path], self.destination, self.settings, index=self._index)
        execute_plan(
            items, mode=self.mode, dry_run=self.dry_run, confirm_move=self.confirm_move
        )
        for item in items:
            if item.status == "error" and item.file_hash and self._index is not None:
                self._index.discard(item.file_hash)  # failed copy must not block retries
            self._report(item)

    def _report(self, item: PlannedItem) -> None:
        logger.info("%s: %s %s", item.status, item.original_name, item.message)
        if self._store is not None and not self.dry_run:
            try:
                self._store.record(item)
            except (sqlite3.Error, OSError):
                logger.exception("Could not record %s in the database", item.original_name)
        if self._on_result is not None:
            try:
                self._on_result(item)
            except Exception:  # noqa: BLE001 - a bad callback must not stop the worker
                logger.exception("on_result callback failed")
