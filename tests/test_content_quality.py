"""Synthetic regressions; no private screenshots or OCR text are stored here."""
from dataclasses import replace
from datetime import date

from PIL import Image
import pytest

from config import Settings
from src.categorizer import categorize
from src.filename_generator import build_filename
from src.models import OcrLine, OcrResult
from src.ocr_engine import extract_text
from src.text_analyzer import analyze_text, content_text


def result(*lines, width=1900):
    return OcrResult(full_text="\n".join(line.text for line in lines), lines=list(lines),
                     mean_confidence=90, image_height=900, image_width=width)


def test_chat_conversation_ignores_brand_icons_and_sidebar_topics():
    ocr = result(
        OcrLine("ChatGPT Q oO", 85, 26, 12, 20),
        OcrLine("Invoice meeting budget", 94, 30, 200, 20),
        OcrLine("Step 2 — Start the automation", 94, 25, 130, 750),
        OcrLine("This should launch the background organizer without needing Streamlit.", 94, 22, 330, 750),
        OcrLine("</> powershell", 90, 20, 470, 750),
        OcrLine("Step 3 — Check whether it is running", 92, 24, 380, 750),
    )
    title = analyze_text(ocr, Settings()).title
    assert title == "Start the automation"
    assert build_filename(title, date(2026, 10, 17), ".png", Settings()) == "Start_the_automation_2026-10-17.png"
    category = categorize(content_text(ocr), Settings())
    assert category.category == "Programming"
    assert "powershell" in category.reason
    assert "invoice" not in content_text(ocr).lower()


@pytest.mark.parametrize("text", ["ChatGPT Q oO", "Google", "YouTube", "New chat", "Ask ChatGPT", "oooo llll", "aaaa eeee", "Q oO x"])
def test_interface_labels_and_noisy_ocr_use_neutral_fallback(text):
    assert analyze_text(result(OcrLine(text, 95, 30, 20, 20)), Settings()).title is None


def test_clear_heading_and_tiny_readable_content():
    ocr = result(OcrLine("Python Exception Handling", 94, 14, 150, 700),
                 OcrLine("Use try and except blocks", 90, 10, 250, 700))
    assert analyze_text(ocr, Settings()).title == "Python Exception Handling"
    assert categorize(content_text(ocr), Settings()).category == "Programming"


def test_mixed_topics_remain_ambiguous():
    category = categorize("python javascript assignment lecture", Settings())
    assert category.category == "Uncategorized"
    assert "Ambiguous" in category.reason


def test_little_text_has_neutral_title_and_category():
    ocr = result(OcrLine("Hi", 90, 20, 100, 300))
    assert analyze_text(ocr, Settings()).title is None
    assert categorize(content_text(ocr), Settings()).category == "Uncategorized"


def test_layout_filter_does_not_crop_normal_left_aligned_document():
    ocr = result(OcrLine("University lecture assignment", 90, 30, 50, 20),
                 OcrLine("Python example", 90, 20, 100, 700),
                 OcrLine("Code explanation", 90, 20, 150, 700),
                 OcrLine("More details", 90, 20, 200, 700))
    assert "University" in content_text(ocr)
    assert categorize(content_text(ocr), Settings()).category == "Education"


def test_category_phrases_are_configurable():
    settings = replace(Settings(), categories={"Work": {"quarterly review": 4}, "Personal": {"recipe": 3}})
    assert categorize("Quarterly review", settings).category == "Work"
    assert categorize("quarterly unrelated review", settings).category == "Uncategorized"
    assert categorize("hello", replace(settings, categories={})).category == "Uncategorized"


def data(words, height=10):
    return {"text": words, "conf": [95]*len(words), "block_num": [1]*len(words),
            "par_num": [1]*len(words), "line_num": list(range(len(words))),
            "left": [20]*len(words), "top": list(range(20, 20+len(words)*20, 20)),
            "height": [height]*len(words)}


def test_small_text_on_wide_page_is_resized_and_retry_selected(tmp_path, monkeypatch):
    image = tmp_path / "web.png"
    Image.new("RGB", (1900, 900), "white").save(image)
    calls = []
    monkeypatch.setattr("src.ocr_engine.configure_tesseract", lambda settings: None)
    def fake_ocr(image, **kwargs):
        calls.append((image.size, kwargs))
        if image.width < 3000:
            return data(["Python", "Exception", "Handling"])
        return data(["Python", "Exception", "Handling", "try", "except", "blocks"], height=22)
    monkeypatch.setattr("src.ocr_engine.pytesseract.image_to_data", fake_ocr)
    ocr = extract_text(image, Settings())
    assert [size[0] for size, _ in calls] == [1900, 3800]
    assert "except" in ocr.full_text
    assert ocr.image_width == 3800
    assert 0 < calls[1][1]["timeout"] <= calls[0][1]["timeout"] <= 60


def test_sparse_fallback_is_used_without_replacing_better_ocr(tmp_path, monkeypatch):
    image = tmp_path / "sparse.png"
    Image.new("RGB", (1600, 900), "white").save(image)
    calls = []
    monkeypatch.setattr("src.ocr_engine.configure_tesseract", lambda settings: None)
    def fake_ocr(image, **kwargs):
        calls.append(kwargs["config"])
        return data(["Clear heading"] if len(calls) == 1 else [], height=30)
    monkeypatch.setattr("src.ocr_engine.pytesseract.image_to_data", fake_ocr)
    ocr = extract_text(image, Settings())
    assert calls == ["--psm 3", "--psm 11"]
    assert ocr.full_text == "Clear heading"
