"""Tesseract wrapper that returns structured, line-level OCR results."""
from __future__ import annotations

import logging
import shutil
import statistics
import time
import re
from pathlib import Path

import pytesseract
from PIL import Image
from pytesseract import Output

from config import Settings
from src.image_processor import load_image, preprocess_for_ocr
from src.models import OcrLine, OcrResult

logger = logging.getLogger(__name__)

DEFAULT_WINDOWS_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

TESSERACT_INSTALL_HELP = """\
Tesseract OCR was not found on this computer.

How to fix it (Windows):
  1. Download the installer from https://github.com/UB-Mannheim/tesseract/wiki
  2. Run it and keep the default folder: C:\\Program Files\\Tesseract-OCR
  3. Make sure the English language data is selected during install.
  4. Close and reopen VS Code, then run:  python main.py check

If you installed it somewhere else, set tesseract_cmd in config.py, e.g.
  tesseract_cmd: str | None = r"D:\\Tools\\Tesseract-OCR\\tesseract.exe"
"""


class TesseractNotAvailableError(RuntimeError):
    """Raised when the Tesseract executable cannot be found."""


def configure_tesseract(settings: Settings) -> None:
    """Point pytesseract at the executable (config > PATH > default folders)."""
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        return
    if shutil.which("tesseract"):
        return
    for candidate in DEFAULT_WINDOWS_PATHS:
        if Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return


def check_tesseract(settings: Settings) -> tuple[bool, str]:
    """Return (is_ready, human-readable message)."""
    configure_tesseract(settings)
    try:
        version = pytesseract.get_tesseract_version()
    except pytesseract.TesseractNotFoundError:
        return False, TESSERACT_INSTALL_HELP
    except Exception as exc:  # noqa: BLE001 - report any unexpected failure
        return False, f"Tesseract check failed: {exc}"

    message = f"Tesseract {version} found."
    try:
        languages = pytesseract.get_languages()
        if settings.ocr_language not in languages:
            return False, (
                f"{message}\nLanguage '{settings.ocr_language}' is not installed. "
                "Re-run the Tesseract installer and tick the English data."
            )
    except Exception:  # noqa: BLE001 - language listing is a nice-to-have
        pass
    return True, message


def _build_lines(data: dict, min_word_conf: float) -> tuple[list[OcrLine], list[float]]:
    """Group Tesseract word boxes into lines."""
    groups: dict[tuple[int, int, int], list[tuple[int, str, float, int, int]]] = {}
    for i, raw in enumerate(data["text"]):
        word = (raw or "").strip()
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < min_word_conf:  # also drops Tesseract's -1 "non-word" boxes
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append(
            (data["left"][i], word, conf, data["top"][i], data["height"][i])
        )

    lines: list[OcrLine] = []
    all_confidences: list[float] = []
    for words in groups.values():
        words.sort(key=lambda w: w[0])
        confidences = [w[2] for w in words]
        all_confidences.extend(confidences)
        lines.append(
            OcrLine(
                text=" ".join(w[1] for w in words),
                confidence=sum(confidences) / len(confidences),
                height=float(statistics.median(w[4] for w in words)),
                top=min(w[3] for w in words),
                left=words[0][0],
            )
        )
    lines.sort(key=lambda line: (line.top, line.left))
    return lines, all_confidences


def extract_text(path: Path, settings: Settings) -> OcrResult:
    """Run OCR on one image. Problems are returned in OcrResult.error.

    Only a missing Tesseract raises (TesseractNotAvailableError), because that
    affects every image and the user must fix it.
    """
    configure_tesseract(settings)

    try:
        image = load_image(path)
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        logger.warning("Cannot open image %s: %s", path, exc)
        return OcrResult(error=f"Could not open image: {exc}")

    started = time.monotonic()

    def attempt(processed: Image.Image, psm: int) -> OcrResult:
        remaining = settings.ocr_timeout - (time.monotonic() - started)
        if remaining <= 0:
            return OcrResult(error="OCR time budget exhausted.")
        try:
            data = pytesseract.image_to_data(
                processed, lang=settings.ocr_language, config=f"--psm {psm}",
                output_type=Output.DICT, timeout=remaining,
            )
        except pytesseract.TesseractNotFoundError as exc:
            raise TesseractNotAvailableError(TESSERACT_INSTALL_HELP) from exc
        except (pytesseract.TesseractError, RuntimeError) as exc:
            logger.warning("OCR attempt failed for %s: %s", path, exc)
            return OcrResult(error=f"OCR failed: {exc}")
        lines, confidences = _build_lines(data, settings.ocr_min_word_confidence)
        return OcrResult(
            full_text="\n".join(line.text for line in lines), lines=lines,
            mean_confidence=sum(confidences) / len(confidences) if confidences else 0,
            image_height=processed.height, image_width=processed.width,
            error=None if lines else "No readable text detected.",
        )

    def quality(result: OcrResult) -> float:
        # Reward confident word coverage, not raw OCR noise or a few easy UI labels.
        words = re.findall(r"[A-Za-z]{3,}", result.full_text)
        return result.mean_confidence * (len(words) ** 0.5) if result.ok else 0

    processed = preprocess_for_ocr(image, settings.ocr_min_width)
    best = attempt(processed, settings.ocr_psm)
    heights = [line.height for line in best.lines if line.confidence >= 60]
    if heights and statistics.median(heights) < settings.ocr_small_text_height:
        # Full-width desktop screenshots also contain tiny glyphs; width alone is insufficient.
        target = min(processed.width * settings.ocr_retry_scale,
                     image.width * 3, (12_000_000 * image.width / image.height) ** .5)
        if target > processed.width * 1.1:
            processed = preprocess_for_ocr(image, int(target))
            candidate = attempt(processed, settings.ocr_psm)
            if quality(candidate) > quality(best):
                best = candidate
    if not best.ok or best.mean_confidence < 60 or len(best.lines) < 3:
        if settings.ocr_fallback_psm != settings.ocr_psm:
            candidate = attempt(processed, settings.ocr_fallback_psm)
            if quality(candidate) > quality(best):
                best = candidate
    return best
