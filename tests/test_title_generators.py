from PIL import Image

from config import Settings
from src.models import OcrLine, OcrResult, TitleAnalysis
from src.organizer import plan_screenshots
from src.title_generators import (
    DEFAULT_TITLE_GENERATOR, RuleBasedTitleGenerator, TitleGenerator,
)

SETTINGS = Settings()

OCR = OcrResult(
    full_text="Python Exception Handling\nprint result def",
    lines=[OcrLine("Python Exception Handling", 92, 40, 50, 100)],
    mean_confidence=92.0,
    image_height=1000,
)


def make_png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), "white").save(path)
    return path


def test_default_generator_is_rule_based_and_matches_the_protocol():
    assert isinstance(DEFAULT_TITLE_GENERATOR, RuleBasedTitleGenerator)
    assert isinstance(DEFAULT_TITLE_GENERATOR, TitleGenerator)
    assert DEFAULT_TITLE_GENERATOR.generate(OCR, SETTINGS).title == "Python Exception Handling"


def test_a_custom_generator_decides_the_filename(tmp_path, monkeypatch):
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: OCR)

    class FakeGenerator:
        name = "fake"

        def generate(self, result, settings):
            return TitleAnalysis(title="Custom Title", source="heading", reason="fake")

    shot = make_png(tmp_path / "src" / "Screenshot (1).png")
    [item] = plan_screenshots([shot], tmp_path / "out", SETTINGS, title_generator=FakeGenerator())
    assert item.new_name.startswith("Custom_Title_")


def test_a_generator_that_is_unsure_gets_the_neutral_filename(tmp_path, monkeypatch):
    monkeypatch.setattr("src.organizer.extract_text", lambda path, settings: OCR)

    class UnsureGenerator:
        name = "unsure"

        def generate(self, result, settings):
            return TitleAnalysis(title=None, source="fallback", reason="not sure")

    shot = make_png(tmp_path / "src" / "Screenshot (1).png")
    [item] = plan_screenshots([shot], tmp_path / "out", SETTINGS, title_generator=UnsureGenerator())
    assert item.new_name.startswith("Screenshot_")
