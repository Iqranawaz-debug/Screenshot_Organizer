from pathlib import Path

from config import Settings
from src.screenshot_detector import (
    matches_screenshot_pattern, scan_folder, validate_manual_selection,
)

SETTINGS = Settings()


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_pattern_matching_is_case_insensitive():
    patterns = SETTINGS.screenshot_name_patterns
    assert matches_screenshot_pattern("Screenshot (42).png", patterns)
    assert matches_screenshot_pattern("Screen Shot 2026-10-17 at 10.00.png", patterns)
    assert matches_screenshot_pattern("SNIP.PNG", patterns)
    assert not matches_screenshot_pattern("holiday.png", patterns)


def test_scan_respects_patterns_and_types(tmp_path):
    touch(tmp_path / "Screenshot (1).png")
    touch(tmp_path / "holiday.jpg")
    touch(tmp_path / "notes.txt")
    touch(tmp_path / "Screenshot (2).gif")

    names = [p.name for p in scan_folder(tmp_path, SETTINGS)]
    assert names == ["Screenshot (1).png"]

    names_all = [p.name for p in scan_folder(tmp_path, SETTINGS, require_pattern=False)]
    assert names_all == ["holiday.jpg", "Screenshot (1).png"]


def test_scan_skips_excluded_folders(tmp_path):
    touch(tmp_path / "Screenshot (1).png")
    touch(tmp_path / "out" / "Screenshot (3).png")
    found = scan_folder(tmp_path, SETTINGS, recursive=True, exclude_dirs=[tmp_path / "out"])
    assert [p.name for p in found] == ["Screenshot (1).png"]


def test_manual_selection_ignores_filename_but_not_type(tmp_path):
    good = touch(tmp_path / "random_name.webp")
    bad = touch(tmp_path / "doc.pdf")
    valid, problems = validate_manual_selection([good, bad, tmp_path / "missing.png"], SETTINGS)
    assert valid == [good]
    assert len(problems) == 2