"""Persistent, copy-only automation independent of Streamlit."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import threading
import time

from config import PROJECT_ROOT, Settings
from src.folder_watcher import FolderWatcher
from src.instance_lock import InstanceLock, is_locked
from src.metadata_store import MetadataStore
from src.ocr_engine import check_tesseract
from src.organizer import validate_folders
from src.screenshot_detector import scan_folder
from src.windows_folders import screenshots_folder

CONFIG_PATH = PROJECT_ROOT / "automation.json"
RUNTIME_DIR = PROJECT_ROOT / "runtime"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AutomationConfig:
    source: Path
    destination: Path
    database: Path
    process_existing: bool = False

    def validate(self) -> None:
        validate_folders(self.source, self.destination)
        if self.source == Path(self.source.anchor):
            raise ValueError("Choose a Screenshots folder, not an entire drive.")
        if self.destination.exists() and not self.destination.is_dir():
            raise ValueError("Destination must be a folder.")


def save_config(config: AutomationConfig, path: Path = CONFIG_PATH) -> None:
    config.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    values = {"source": str(config.source.resolve()), "destination": str(config.destination.resolve()),
              "database": str(config.database.resolve()), "process_existing": config.process_existing}
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_config(path: Path = CONFIG_PATH) -> AutomationConfig:
    values = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(values.get("process_existing", False), bool):
        raise ValueError("process_existing must be true or false.")
    config = AutomationConfig(*(Path(values[key]) for key in ("source", "destination", "database")),
                              process_existing=values.get("process_existing", False))
    if not all(p.is_absolute() for p in (config.source, config.destination, config.database)):
        raise ValueError("Automation configuration paths must be absolute; run configure again.")
    config.validate()
    return config


def configure(source: Path | None, destination: Path | None, *,
              path: Path = CONFIG_PATH, process_existing: bool = False) -> AutomationConfig:
    defaults = Settings()
    config = AutomationConfig(source or screenshots_folder(), destination or defaults.default_destination,
                              defaults.database_path, process_existing)
    save_config(config, path)
    return config


def status(runtime: Path = RUNTIME_DIR) -> dict:
    running = is_locked(runtime / "background.lock")
    try:
        value = json.loads((runtime / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {}
    value["active"] = running
    if not running:
        value["state"] = "stopped"
    return value


def request_stop(runtime: Path = RUNTIME_DIR) -> bool:
    if not is_locked(runtime / "background.lock"):
        return False
    (runtime / "stop.request").touch()
    return True


def setup_logging(runtime: Path) -> None:
    runtime.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(runtime / "automation.log", maxBytes=2_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def run(config: AutomationConfig, runtime: Path = RUNTIME_DIR) -> int:
    """Run until a stop request or signal; never moves or deletes originals."""
    config.validate()
    lock = InstanceLock(runtime / "background.lock")
    if not lock.acquire():
        return 0  # an existing process already owns automation
    watcher = None
    stop = threading.Event()
    old_handlers = {}
    settings = replace(Settings(), database_path=config.database)
    completed: dict[str, tuple[int, int]] = {}
    result_lock = threading.Lock()

    def checkpoint() -> None:
        with result_lock:
            values = {"source": str(config.source), "completed": dict(completed)}
        temporary = runtime / "seen.tmp"
        temporary.write_text(json.dumps(values), encoding="utf-8")
        temporary.replace(runtime / "seen.json")

    def signature(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns

    def publish(state: str, error: str = "") -> None:
        values = {"state": state, "pid": os.getpid(), "source": str(config.source),
                  "destination": str(config.destination), "mode": "copy", "error": error,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        temporary = runtime / "status.tmp"
        temporary.write_text(json.dumps(values), encoding="utf-8")
        temporary.replace(runtime / "status.json")

    def on_result(item) -> None:
        if item.status == "copied" or (item.status == "skipped" and item.message.startswith("Duplicate")):
            try:
                with result_lock:
                    completed[str(item.source)] = signature(item.source)
            except OSError:
                pass

    try:
        setup_logging(runtime)
        (runtime / "stop.request").unlink(missing_ok=True)
        for sig in (signal.SIGINT, signal.SIGTERM):
            old_handlers[sig] = signal.signal(sig, lambda *_: stop.set())
        publish("starting")
        previous = None
        try:
            previous = json.loads((runtime / "seen.json").read_text(encoding="utf-8"))
            if previous.get("source") == str(config.source):
                completed.update({key: tuple(value) for key, value in previous["completed"].items()})
            else:
                previous = None
        except (OSError, ValueError, KeyError, TypeError):
            previous = None
        # Exclude the initial backlog only once; later restarts recover missed arrivals.
        if previous is None and not config.process_existing and config.source.is_dir():
            for path in scan_folder(config.source, settings, require_pattern=False):
                try:
                    completed[str(path)] = signature(path)
                except OSError:
                    pass
        checkpoint()
        last_reconcile = 0.0
        while not stop.is_set() and not (runtime / "stop.request").exists():
            if watcher is None:
                if not config.source.is_dir():
                    publish("waiting", "Screenshots folder does not exist yet; waiting for Windows to create it.")
                    stop.wait(2)
                    continue
                ok, message = check_tesseract(settings)
                if not ok:
                    publish("waiting", message)
                    stop.wait(5)
                    continue
                watcher = FolderWatcher(config.source, config.destination, settings, mode="copy",
                                        dry_run=False, require_pattern=False, on_result=on_result,
                                        store=MetadataStore(config.database))
                watcher.start()
                logger.info("Background automation started (copy only)")
            if not watcher.is_running or not config.source.is_dir():
                watcher.stop()
                watcher = None
                publish("waiting", "Source or observer unavailable; retrying.")
                stop.wait(5)
                continue
            # Recover missed events and retry locked/partially-written files every 30 seconds.
            if time.monotonic() - last_reconcile >= 30:
                for path in scan_folder(config.source, settings, require_pattern=False):
                    try:
                        with result_lock:
                            done = completed.get(str(path)) == signature(path)
                        if not done:
                            watcher.submit(path)
                    except OSError:
                        continue
                last_reconcile = time.monotonic()
                checkpoint()
            publish("running")
            stop.wait(2)
        publish("stopping")
        return 0
    except Exception as exc:
        logger.exception("Background automation failed")
        publish("error", str(exc))
        return 1
    finally:
        if watcher is not None:
            watcher.stop()
        try:
            checkpoint()
        except OSError:
            logger.exception("Could not save retry checkpoint")
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        lock.release()
