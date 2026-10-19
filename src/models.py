"""Plain data containers shared across modules (no heavy imports)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float   # 0-100
    height: float       # median word height in pixels (proxy for font size)
    top: int            # y position in the processed image
    left: int


@dataclass
class OcrResult:
    full_text: str = ""
    lines: list[OcrLine] = field(default_factory=list)
    mean_confidence: float = 0.0
    image_height: int = 0
    error: str | None = None
    image_width: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.full_text.strip())


@dataclass(frozen=True)
class TitleCandidate:
    title: str
    score: float
    source_line: str


@dataclass
class TitleAnalysis:
    title: str | None                 # None means "use the neutral fallback"
    source: str                       # "heading", "keywords" or "fallback"
    reason: str
    candidates: list[TitleCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class DateInfo:
    value: date
    source: str    # "exif_datetime_original", "exif_datetime" or "file_modified"
