from dataclasses import replace
from pathlib import Path
import threading

import pytest

from config import Settings
from src.background_service import AutomationConfig, load_config, save_config, status, request_stop
from src.folder_watcher import FolderWatcher
from src.instance_lock import InstanceLock
from src.metadata_store import MetadataStore
from src.organizer import FolderConfigError, PlannedItem
from src import windows_folders
from tests.test_services import PYTHON_OCR, make_png


def test_config_roundtrip_and_rejects_nested_paths(tmp_path):
    config = AutomationConfig(tmp_path / "source", tmp_path / "output", tmp_path / "data" / "db")
    path = tmp_path / "automation.json"
    save_config(config, path)
    assert load_config(path) == config
    assert not config.source.exists() and not config.destination.exists()
    with pytest.raises(FolderConfigError):
        save_config(replace(config, destination=config.source / "out"), path)
    assert load_config(path) == config


def test_status_on_first_use_creates_nothing(tmp_path):
    runtime = tmp_path / "runtime"
    assert status(runtime) == {"active": False, "state": "stopped"}
    assert request_stop(runtime) is False
    assert not runtime.exists()


def test_lock_exclusion_and_stop_request(tmp_path):
    first = InstanceLock(tmp_path / "background.lock")
    second = InstanceLock(first.path)
    assert first.acquire()
    try:
        assert not second.acquire()
        assert status(tmp_path)["active"]
        assert request_stop(tmp_path)
        assert (tmp_path / "stop.request").exists()
    finally:
        first.release()
    assert second.acquire()
    second.release()
    assert not status(tmp_path)["active"]


def test_windows_screenshots_uses_redirected_known_folder(monkeypatch, tmp_path):
    redirected = tmp_path / "redirected" / "Screenshots"
    monkeypatch.setattr(windows_folders, "known_folder", lambda identifier: redirected)
    assert windows_folders.screenshots_folder() == redirected
    assert not redirected.exists()


def test_windows_screenshots_falls_back_to_actual_pictures(monkeypatch, tmp_path):
    def lookup(identifier):
        if identifier == windows_folders.SCREENSHOTS:
            raise OSError("not registered")
        return tmp_path / "redirected_pictures"
    monkeypatch.setattr(windows_folders, "known_folder", lookup)
    assert windows_folders.screenshots_folder() == tmp_path / "redirected_pictures" / "Screenshots"


def test_watchers_cannot_share_source_and_release_on_stop(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    first = FolderWatcher(source, tmp_path / "a", Settings())
    second = FolderWatcher(source, tmp_path / "b", Settings())
    first.start()
    try:
        with pytest.raises(RuntimeError, match="Another watcher"):
            second.start()
    finally:
        first.stop()
    second.start()
    second.stop()
    assert not second.is_running


def test_real_events_copy_and_store_without_approval(tmp_path, monkeypatch):
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: PYTHON_OCR)
    source = tmp_path / "source"
    source.mkdir()
    store = MetadataStore(tmp_path / "db.sqlite")
    results = []
    ready = threading.Event()
    def report(item):
        results.append(item)
        ready.set()
    watcher = FolderWatcher(source, tmp_path / "out", Settings(), dry_run=False,
                            on_result=report, store=store, stable_interval=0.01, stable_checks=2)
    watcher.start()
    try:
        shot = make_png(source / "Screenshot (1).png")
        assert ready.wait(10)
        assert results[0].status == "copied"
        assert results[0].new_name.startswith("Python_Exception_Handling_")
        assert store.count() == 1 and shot.exists()
        ready.clear()
        (source / "Screenshot (2).png").write_bytes(shot.read_bytes())
        assert ready.wait(10)
        assert results[-1].status == "skipped"
        assert store.count() == 1
    finally:
        watcher.stop()


def test_history_filesystem_error_does_not_kill_watcher_reporting(tmp_path, monkeypatch):
    store = MetadataStore(tmp_path / "db")
    def fail(item):
        raise OSError("read only")
    monkeypatch.setattr(store, "record", fail)
    results = []
    watcher = FolderWatcher(tmp_path / "src", tmp_path / "out", Settings(), dry_run=False,
                            store=store, on_result=results.append)
    item = PlannedItem(source=tmp_path / "shot.png", status="error", message="OCR problem")
    watcher._report(item)
    assert results == [item]
