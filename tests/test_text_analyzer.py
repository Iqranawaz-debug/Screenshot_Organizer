from config import Settings
from src.models import OcrLine, OcrResult
from src.text_analyzer import (
    analyze_text, extract_keywords, is_noise, title_from_line,
)


def make_result(lines: list[OcrLine], image_height: int = 1000) -> OcrResult:
    return OcrResult(
        full_text="\n".join(line.text for line in lines),
        lines=lines,
        mean_confidence=sum(line.confidence for line in lines) / len(lines),
        image_height=image_height,
    )


def test_prominent_heading_wins_and_subtitle_is_dropped():
    lines = [
        OcrLine("10:45 AM", 90, 15, 10, 900),
        OcrLine("Python Exception Handling \u2014 Using try and except blocks", 92, 40, 80, 100),
        OcrLine("def divide(a, b):", 90, 20, 400, 100),
        OcrLine("return a / b", 90, 20, 440, 100),
    ]
    analysis = analyze_text(make_result(lines), Settings())
    assert analysis.source == "heading"
    assert analysis.title == "Python Exception Handling"


def test_short_tail_like_assignment_number_is_kept():
    lines = [OcrLine("Database Management Systems \u2014 Assignment 02", 93, 40, 60, 100)]
    analysis = analyze_text(make_result(lines), Settings())
    assert analysis.title == "Database Management Systems Assignment 02"


def test_all_caps_heading_is_title_cased():
    lines = [OcrLine("PYTHON LISTS AND TUPLES", 90, 40, 50, 100)]
    assert analyze_text(make_result(lines), Settings()).title == "Python Lists And Tuples"


def test_low_confidence_uses_fallback():
    lines = [OcrLine("Some Blurry Heading Text", 20, 40, 50, 100)]
    analysis = analyze_text(make_result(lines), Settings())
    assert analysis.title is None
    assert analysis.source == "fallback"


def test_ocr_error_uses_fallback():
    analysis = analyze_text(OcrResult(error="No readable text detected."), Settings())
    assert analysis.title is None


def test_noise_detection():
    assert is_noise("10:45 AM")
    assert is_noise("https://example.com/page")
    assert is_noise("File Edit View")
    assert not is_noise("Python Basics")


def test_title_truncation_and_trailing_stopwords():
    assert title_from_line("One Two Three Four Five Six Seven Eight", 6) == "One Two Three Four Five Six"
    assert title_from_line("Introduction to the Theory", 3) == "Introduction"


def test_keywords_require_repetition():
    text = "network packet network router packet network"
    assert extract_keywords(text) == ["network", "packet"]