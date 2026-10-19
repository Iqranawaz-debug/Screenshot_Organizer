import shutil
from pathlib import Path

import pytest
from PIL import Image

from config import Settings
from src.metadata_store import MetadataStore
from src.models import OcrLine, OcrResult, TitleAnalysis
from src.organizer import ConfirmationRequiredError, FolderConfigError, PlannedItem
from src.services import WatcherController, apply_approved, build_plan, parse_path_lines

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


def test_parse_path_lines_ignores_blanks_and_quotes():
    text = '  "C:\\a\\one.png"  \n\n\'two.png\'\n   \nthree.png'
    assert parse_path_lines(text) == [Path("C:\\a\\one.png"), Path("two.png"), Path("three.png")]


def test_build_plan_touches_nothing(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "out"
    make_png(src / "Screenshot (1).png")
    items, warnings = build_plan(src, dest, SETTINGS)
    assert [i.status for i in items] == ["planned"]
    assert warnings == []
    assert not dest.exists()


def test_build_plan_passes_through_title_generator(tmp_path):
    calls = []

    class CustomGenerator:
        name = "custom"

        def generate(self, result, settings):
            calls.append((result, settings))
            return TitleAnalysis(title="Exception Handling", source="heading", reason="custom")

    source, destination = tmp_path / "src", tmp_path / "out"
    make_png(source / "Screenshot (1).png")
    items, warnings = build_plan(source, destination, SETTINGS, title_generator=CustomGenerator())
    assert calls == [(PYTHON_OCR, SETTINGS)]
    assert not warnings
    assert items[0].new_name.startswith("Exception_Handling_")
    assert items[0].title_reason == "custom"
    assert not destination.exists()


def test_build_plan_rejects_nested_folders(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    with pytest.raises(FolderConfigError):
        build_plan(src, src / "out", SETTINGS)


def test_build_plan_accepts_hand_picked_files_with_any_name(tmp_path):
    odd = make_png(tmp_path / "random_name.png")
    items, warnings = build_plan(None, tmp_path / "out", SETTINGS,
                                 extra_files=[odd, tmp_path / "missing.png"])
    assert len(items) == 1 and items[0].status == "planned"
    assert len(warnings) == 1


def test_apply_approved_copies_only_the_approved_items(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "out"
    make_png(src / "Screenshot (1).png", (20, 20))
    make_png(src / "Screenshot (2).png", (21, 21))
    items, _ = build_plan(src, dest, SETTINGS)
    assert [i.status for i in items] == ["planned", "planned"]

    outcome = apply_approved(items, [0], dest, SETTINGS)

    assert len(outcome.items) == 1
    assert items[0].status == "copied"
    assert items[1].status == "planned"          # never approved, never touched
    assert len(list(dest.rglob("*.png"))) == 1


def test_move_requires_confirmation(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "out"
    shot = make_png(src / "Screenshot (1).png")
    items, _ = build_plan(src, dest, SETTINGS)
    with pytest.raises(ConfirmationRequiredError):
        apply_approved(items, [0], dest, SETTINGS, mode="move")
    assert shot.exists() and not dest.exists()


def test_duplicates_that_appear_after_the_preview_are_skipped(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "out"
    shot = make_png(src / "Screenshot (1).png")
    items, _ = build_plan(src, dest, SETTINGS)

    (dest / "Other").mkdir(parents=True)
    shutil.copyfile(shot, dest / "Other" / "already_here.png")   # same bytes arrive late

    apply_approved(items, [0], dest, SETTINGS)

    assert items[0].status == "skipped"
    assert "Duplicate" in items[0].message
    assert len(list(dest.rglob("*.png"))) == 1


def test_apply_records_history(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "out"
    make_png(src / "Screenshot (1).png")
    store = MetadataStore(tmp_path / "data" / "t.db")
    items, _ = build_plan(src, dest, SETTINGS, store=store)

    outcome = apply_approved(items, [0], dest, SETTINGS, store=store)

    assert outcome.history_error is None
    assert store.count() == 1


def test_history_failure_is_reported_but_files_are_still_copied(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "out"
    make_png(src / "Screenshot (1).png")
    blocker = tmp_path / "afile"
    blocker.write_text("not a folder")
    store = MetadataStore(blocker / "db.sqlite")   # parent is a file -> cannot be created
    items, _ = build_plan(src, dest, SETTINGS)

    outcome = apply_approved(items, [0], dest, SETTINGS, store=store)

    assert items[0].status == "copied"
    assert outcome.history_error is not None


# ---------- WatcherController ----------
def test_recent_results_are_newest_first_and_capped():
    controller = WatcherController(SETTINGS, max_results=2)
    for name in ("a", "b", "c"):
        controller._add_result(PlannedItem(source=Path(f"{name}.png")))
    assert [i.original_name for i in controller.recent_results()] == ["c.png", "b.png"]


def test_controller_start_stop_and_guards(tmp_path):
    source, dest = tmp_path / "src", tmp_path / "out"
    source.mkdir()
    controller = WatcherController(SETTINGS)
    with pytest.raises(FolderConfigError):
        controller.start(source, source / "out")        # nested folders refused
    assert not controller.is_running

    controller.start(source, dest, dry_run=True)
    try:
        assert controller.is_running
        with pytest.raises(RuntimeError):
            controller.start(source, dest)              # already running
    finally:
        controller.stop()
    assert not controller.is_running
