from datetime import date

from config import Settings
from src.filename_generator import build_filename, sanitize_stem, unique_path

SETTINGS = Settings()
DAY = date(2026, 10, 17)


def test_basic_filename():
    name = build_filename("Python Exception Handling", DAY, ".PNG", SETTINGS)
    assert name == "Python_Exception_Handling_2026-10-17.png"


def test_invalid_characters_removed():
    assert sanitize_stem('Python: Try/Except?') == "Python_Try_Except"


def test_reserved_windows_name_is_changed():
    assert sanitize_stem("CON") == "CON_file"


def test_neutral_fallback_when_no_title():
    assert build_filename(None, DAY, ".jpg", SETTINGS) == "Screenshot_2026-10-17.jpg"


def test_length_limit_and_clean_cut():
    name = build_filename("word " * 40, DAY, ".png", SETTINGS)
    assert len(name) <= SETTINGS.max_filename_length
    assert name.endswith("_2026-10-17.png")
    assert "__" not in name


def test_unique_path_adds_suffix(tmp_path):
    (tmp_path / "a.png").write_bytes(b"x")
    assert unique_path(tmp_path, "a.png").name == "a_02.png"
    assert unique_path(tmp_path, "a.png", {"a_02.png"}).name == "a_03.png"