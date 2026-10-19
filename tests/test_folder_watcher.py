from pathlib import Path

import pytest
from PIL import Image

from config import Settings
from src.folder_watcher import FolderWatcher, wait_until_stable
from src.models import OcrLine, OcrResult
from src.organizer import ConfirmationRequiredError, FolderConfigError

SETTINGS = Settings()

PYTHON_OCR = OcrResult(
    full_text=("Python Exception Handling \u2014 Using try and except blocks\n"
               "def divide a b\nprint result"),
    lines=[
        OcrLine("Python Exception Handling \u2014 Using try and except blocks", 92, 40, 80, 100),
        OcrLine("def divide a b", 90, 20, 400, 100),
        OcrLine("print result", 90, 20, 440, 100),
    ],
    mean_confidence=91.0,
    image_height=1000,
)


def make_png(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), "white").save(path)
    return path


# ---------- wait_until_stable ----------
def test_stable_file_is_ready(tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"data")
    assert wait_until_stable(path, interval=0, stable_checks=2, sleep=lambda s: None)


def test_growing_file_is_not_ready_until_it_stops(tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"x")
    calls = {"n": 0}

    def fake_sleep(_seconds):
        calls["n"] += 1
        if calls["n"] <= 3:  # file keeps growing for the first 3 waits
            with open(path, "ab") as handle:
                handle.write(b"y")

    assert wait_until_stable(
        path, interval=0, stable_checks=2, timeout=10, sleep=fake_sleep
    ) is True
    assert calls["n"] >= 5


def test_missing_file_returns_false(tmp_path):
    assert wait_until_stable(tmp_path / "nope.png", interval=0, sleep=lambda s: None) is False


def test_empty_file_times_out(tmp_path):
    path = tmp_path / "empty.png"
    path.write_bytes(b"")
    ticks = iter(range(1000))
    assert wait_until_stable(
        path, interval=0, timeout=5, sleep=lambda s: None, clock=lambda: next(ticks)
    ) is False


def test_should_stop_cancels_waiting(tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"data")
    assert wait_until_stable(
        path, interval=0, sleep=lambda s: None, should_stop=lambda: True
    ) is False


# ---------- FolderWatcher (no threads started) ----------
def test_submit_filters_and_deduplicates(tmp_path):
    source, dest = tmp_path / "src", tmp_path / "out"
    source.mkdir()
    watcher = FolderWatcher(source, dest, SETTINGS)

    shot = source / "Screenshot (1).png"
    assert watcher.submit(shot) is True
    assert watcher.submit(shot) is False                      # already pending
    assert watcher.submit(source / "holiday.png") is False    # name doesn't match
    assert watcher.submit(source / "notes.txt") is False      # not an image
    assert watcher.submit(dest / "Programming" / "Screenshot (9).png") is False

    loose = FolderWatcher(source, dest, SETTINGS, require_pattern=False)
    assert loose.submit(source / "holiday.png") is True


def test_unsafe_configurations_are_rejected(tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    with pytest.raises(FolderConfigError):
        FolderWatcher(source, source / "out", SETTINGS)
    with pytest.raises(ConfirmationRequiredError):
        FolderWatcher(source, tmp_path / "out", SETTINGS, mode="move", dry_run=False)


def test_process_copies_once_then_skips_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: PYTHON_OCR)
    source, dest = tmp_path / "src", tmp_path / "out"
    first = make_png(source / "Screenshot (1).png")
    second = make_png(source / "Screenshot (2).png")  # identical bytes

    results = []
    watcher = FolderWatcher(
        source, dest, SETTINGS, dry_run=False,
        on_result=results.append, stable_interval=0.0, stable_checks=1,
    )
    watcher._index = None  # start() was not called; plan builds its own index

    watcher._process(first)
    watcher._process(second)

    assert [item.status for item in results] == ["copied", "skipped"]
    assert len(list(dest.rglob("*.png"))) == 1
    assert first.exists() and second.exists()  # copy mode keeps originals
