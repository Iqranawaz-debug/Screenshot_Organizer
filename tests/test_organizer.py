from pathlib import Path

import pytest
from PIL import Image

from config import Settings
from src.models import OcrLine, OcrResult
from src.organizer import (
    ConfirmationRequiredError, FolderConfigError, execute_plan,
    plan_screenshots, validate_folders,
)

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


@pytest.fixture(autouse=True)
def mock_ocr(monkeypatch):
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: PYTHON_OCR)

def make_png(path: Path, size: tuple[int, int] = (20, 20)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return path


def test_nested_or_identical_folders_are_rejected(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    with pytest.raises(FolderConfigError):
        validate_folders(src, src)
    with pytest.raises(FolderConfigError):
        validate_folders(src, src / "out")
    with pytest.raises(FolderConfigError):
        validate_folders(src / "inner", tmp_path)


def test_plan_builds_category_and_name(tmp_path):
    shot = make_png(tmp_path / "src" / "Screenshot (42).png")
    dest = tmp_path / "out"
    [item] = plan_screenshots([shot], dest, SETTINGS)

    assert item.status == "planned"
    assert item.category == "Programming"
    assert item.destination.parent == dest / "Programming"
    assert item.new_name == f"Python_Exception_Handling_{item.date_value.isoformat()}.png"


def test_dry_run_changes_nothing(tmp_path):
    shot = make_png(tmp_path / "src" / "Screenshot (42).png")
    dest = tmp_path / "out"
    items = plan_screenshots([shot], dest, SETTINGS)
    execute_plan(items)  # defaults: dry_run=True, mode="copy"
    assert not dest.exists()
    assert shot.exists()


def test_certification_category_preserves_content_filename(tmp_path, monkeypatch):
    result = OcrResult(
        full_text="Huawei Certification\nhas successfully completed the Huawei certification requirements\nDatacom",
        lines=[OcrLine("Huawei Certification", 95, 40, 100, 300),
               OcrLine("has successfully completed the Huawei certification requirements", 95, 20, 400, 300),
               OcrLine("Datacom", 95, 24, 500, 300)],
        mean_confidence=95, image_height=1000,
    )
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: result)
    shot = make_png(tmp_path / "src" / "Screenshot 2026-10-18 202130.png")
    # Capture dates come from EXIF/mtime, not text in the filename or today's clock.
    import os
    from datetime import datetime
    timestamp = datetime(2026, 10, 18, 20, 21, 30).timestamp()
    os.utime(shot, (timestamp, timestamp))
    [item] = plan_screenshots([shot], tmp_path / "out", SETTINGS)
    assert item.category == "Education"
    assert item.new_name == "Huawei_Certification_2026-10-18.png"
    assert "certification" in item.category_reason
    assert not (tmp_path / "out").exists()


def test_copy_keeps_original(tmp_path):
    shot = make_png(tmp_path / "src" / "Screenshot (42).png")
    items = plan_screenshots([shot], tmp_path / "out", SETTINGS)
    execute_plan(items, dry_run=False)
    assert items[0].status == "copied"
    assert items[0].destination.exists()
    assert shot.exists()


def test_move_requires_confirmation(tmp_path):
    shot = make_png(tmp_path / "src" / "Screenshot (42).png")
    items = plan_screenshots([shot], tmp_path / "out", SETTINGS)
    with pytest.raises(ConfirmationRequiredError):
        execute_plan(items, mode="move", dry_run=False)
    assert shot.exists()


def test_confirmed_move_relocates_file(tmp_path):
    shot = make_png(tmp_path / "src" / "Screenshot (42).png")
    items = plan_screenshots([shot], tmp_path / "out", SETTINGS)
    execute_plan(items, mode="move", dry_run=False, confirm_move=True)
    assert items[0].status == "moved"
    assert items[0].destination.exists()
    assert not shot.exists()


def test_existing_files_are_never_overwritten(tmp_path):
    shot = make_png(tmp_path / "src" / "Screenshot (42).png")
    items = plan_screenshots([shot], tmp_path / "out", SETTINGS)
    planned = items[0].destination
    planned.parent.mkdir(parents=True)
    planned.write_bytes(b"existing")  # appears after planning (race)

    execute_plan(items, dry_run=False)

    assert planned.read_bytes() == b"existing"
    assert items[0].destination.name.endswith("_02.png")
    assert items[0].destination.exists()


def test_same_title_different_files_get_unique_names(tmp_path):
    a = make_png(tmp_path / "src" / "Screenshot (1).png", (20, 20))
    b = make_png(tmp_path / "src" / "Screenshot (2).png", (21, 21))  # different bytes
    items = plan_screenshots([a, b], tmp_path / "out", SETTINGS)
    names = {item.destination.name for item in items}
    assert len(names) == 2
    assert any(name.endswith("_02.png") for name in names)


def test_files_already_in_destination_are_skipped(tmp_path):
    dest = tmp_path / "out"
    organized = make_png(dest / "Programming" / "Old_2026-10-01.png")
    [item] = plan_screenshots([organized], dest, SETTINGS)
    assert item.status == "skipped"

def test_rerunning_skips_duplicates_of_organized_files(tmp_path):
    shot = make_png(tmp_path / "src" / "Screenshot (42).png")
    dest = tmp_path / "out"
    execute_plan(plan_screenshots([shot], dest, SETTINGS), dry_run=False)

    [again] = plan_screenshots([shot], dest, SETTINGS)
    assert again.status == "skipped"
    assert "Duplicate" in again.message

    execute_plan([again], dry_run=False)
    assert len(list(dest.rglob("*.png"))) == 1


def test_identical_files_in_one_batch_are_deduplicated(tmp_path):
    a = make_png(tmp_path / "src" / "Screenshot (1).png")
    b = make_png(tmp_path / "src" / "Screenshot (2).png")  # same bytes as a
    items = plan_screenshots([a, b], tmp_path / "out", SETTINGS)
    assert [item.status for item in items] == ["planned", "skipped"]
