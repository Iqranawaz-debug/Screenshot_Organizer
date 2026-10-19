"""Rule-based topic detection: clean OCR output and pick a heading."""
from __future__ import annotations

import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import replace

from config import Settings
from src.models import OcrLine, OcrResult, TitleAnalysis, TitleCandidate
from src.content_filter import meaningful_line

SEPARATOR_RE = re.compile(r"\s*[—–|•]\s*|\s+-\s+|:\s+")
JUNK_RE = re.compile(r"[^\w\s\-&'.]")
WHITESPACE_RE = re.compile(r"\s+")

NOISE_PATTERNS = (
    re.compile(r"^\d{1,2}:\d{2}(:\d{2})?\s*(am|pm)?$"),     # clock times
    re.compile(r"^\d{1,3}\s*%$"),                            # battery / progress
    re.compile(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$"),          # bare dates
    re.compile(r"(https?://|www\.)"),                        # URLs
)

UI_WORDS = frozenset(
    "file edit view selection go run terminal help window insert format tools "
    "home share search type here to new open save close minimize maximize back "
    "forward reload settings menu ok cancel".split()
)

SITE_NAMES = frozenset({"chatgpt", "google", "youtube"})
UI_LABELS = frozenset({
    "new chat", "search chats", "ask chatgpt", "share", "library", "plugins",
    "explore", "pinned", "projects", "recents", "no projects", "add credits",
    "upgrade", "plus", "medium", "sign in", "log in", "subscribe", "settings",
    "copy code", "run", "powershell", "json",
})


def content_lines(result: OcrResult) -> list[OcrLine]:
    """Exclude a left navigation rail only when a branded page and separated content exist."""
    width = result.image_width
    branded_sidebar = width > 0 and any(
        line.left < width * .2 and line.top < result.image_height * .1
        and set(re.findall(r"[a-z]+", line.text.lower())) & SITE_NAMES
        for line in result.lines
    )
    separated_content = width > 0 and (
        sum(line.left >= width * .3 for line in result.lines) >= 3
        or category_interface_hint(result) == "AI Chat"
    )
    return [replace(line, text=text) for line in result.lines
            if not (branded_sidebar and separated_content and line.left < width * .2)
            if (text := meaningful_line(line.text)) is not None]


def content_text(result: OcrResult) -> str:
    # Language labels in code blocks are valid category evidence, but not titles.
    return "\n".join(line.text for line in content_lines(result)
                     if line.confidence >= 50 and
                     (not is_noise(line.text) or
                      " ".join(re.findall(r"[a-z]+", line.text.lower())) in {"powershell", "json"}))


def category_interface_hint(result: OcrResult) -> str | None:
    """Recognize ChatGPT UI independently of title/sidebar filtering.

    Require both a header in the brand position and the central composer label;
    mentions in prose, filenames and history rows are not sufficient.
    """
    if result.image_width <= 0 or result.image_height <= 0:
        return None
    reliable = [line for line in result.lines if line.confidence >= 50]
    def label(line):
        return " ".join(re.findall(r"[a-z]+", line.text.lower()))
    header = any(label(line) == "chatgpt"
                 and line.left < result.image_width * .2
                 and line.top < result.image_height * .1 for line in reliable)
    composer = any(label(line) in {"ask chatgpt", "message chatgpt"}
                   and line.left >= result.image_width * .3 for line in reliable)
    return "AI Chat" if header and composer else None

TRAILING_STOPWORDS = frozenset(
    "a an the of to and or in on for with by at from so".split()
)

KEYWORD_STOPWORDS = frozenset(
    "this that with from have been were will would there their about which "
    "when what your into than then them they also more some such only other "
    "http https www com".split()
) | TRAILING_STOPWORDS


def is_noise(text: str) -> bool:
    """True for interface clutter that should never become a title."""
    lowered = text.lower().strip()
    if meaningful_line(text) is None:
        return True
    if not lowered:
        return True
    if any(pattern.search(lowered) for pattern in NOISE_PATTERNS):
        return True
    words = re.findall(r"[a-z0-9']+", lowered)
    normalized = " ".join(words)
    if normalized in UI_LABELS:
        return True
    if set(words) & SITE_NAMES:
        specific = [w for w in words if len(w) >= 3 and w not in SITE_NAMES
                    and w not in UI_WORDS and w not in {"ask", "chat", "new"}]
        if len(specific) < 2:
            return True
    if not words or all(word in UI_WORDS for word in words):
        return True
    letters = sum(ch.isalpha() for ch in text)
    non_space = len(text.replace(" ", ""))
    if letters < 3 or letters / max(non_space, 1) < 0.6:
        return True
    return False


def clean_segment(text: str) -> str:
    """Remove special characters and normalise spacing."""
    text = unicodedata.normalize("NFKC", text).replace("_", " ")
    text = JUNK_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip(" -.'&")


def _looks_like_words(title: str) -> bool:
    """Cheap garbage filter: most tokens should contain a vowel or a digit."""
    words = title.split()
    if not words:
        return False
    acronyms = {"sql", "api", "css", "html", "http", "ai", "ml", "ui", "ux"}
    good = sum(1 for w in words if (len(w) >= 3 and re.search(r"[aeiouy]", w.lower())
                                   and not re.fullmatch(r"(.)\1{2,}", w.lower()))
               or w.lower() in acronyms or w.lower() in {"a", "i", "to", "of", "in", "on", "by", "is", "we", "do", "it", "so"}
               or w.isdigit())
    return good / len(words) >= 0.75 and any(len(w) >= 3 and w.isalpha() for w in words)


def title_from_line(line_text: str, max_words: int) -> str | None:
    """Turn one OCR line into a concise title, or None if unusable."""
    raw = unicodedata.normalize("NFKC", line_text)
    raw = re.sub(r"^\d+[.)]\s+", "", raw)
    raw = re.sub(r"^step\s+\d+\s*[—–:.-]\s*", "", raw, flags=re.I)
    segments = [clean_segment(part) for part in SEPARATOR_RE.split(raw)]
    segments = [seg for seg in segments if seg]
    if not segments:
        return None

    primary = segments[0]
    rest = segments[1:]
    if len(primary.split()) < 2 and rest:      # "Python — Lists" -> "Python Lists"
        primary = f"{primary} {rest[0]}"
        rest = rest[1:]

    title = primary
    if rest and len(rest[0].split()) <= 3 and not is_noise(rest[0]):
        title = f"{title} {rest[0]}"            # keep short tails like "Assignment 02"

    if title.isupper():
        title = title.title()

    words = title.split()[:max_words]
    while len(words) > 1 and words[-1].lower() in TRAILING_STOPWORDS:
        words.pop()
    return " ".join(words) if words else None


def score_candidates(
    lines: list[OcrLine], image_height: int, settings: Settings
) -> list[TitleCandidate]:
    """Score every usable line; larger, higher, clearer text scores more."""
    heights = [line.height for line in lines if line.height > 0]
    median_height = statistics.median(heights) if heights else 1.0

    candidates: list[TitleCandidate] = []
    for line in lines:
        if line.confidence < settings.min_line_confidence or is_noise(line.text):
            continue
        title = title_from_line(line.text, settings.max_title_words)
        if not title or is_noise(title) or not _looks_like_words(title):
            continue

        word_count = len(title.split())
        score = 2.0 * min(line.height / median_height, 2.0)  # cap large UI/icon artifacts
        if len(line.text.split()) > max(settings.max_title_words + 2, 8):
            score -= 0.8  # prefer concise headings over prose truncated into a title
        if re.match(r"^(this|your|you|it|there|we)\b", line.text, re.I):
            score -= 0.6
        if re.match(r"^[a-z]", line.text) and line.text.endswith(('.', ',')):
            score -= 1.2  # wrapped prose fragments are weaker than standalone headings
        if image_height > 0:
            relative_top = line.top / image_height
            if relative_top < 0.35:                          # near the top
                score += 1.0 - relative_top / 0.35
        if 2 <= word_count <= 8:
            score += 1.0
        elif word_count == 1:
            score -= 0.5
        score += line.confidence / 100.0
        candidates.append(TitleCandidate(title, round(score, 2), line.text))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def extract_keywords(text: str, limit: int = 3, min_count: int = 2) -> list[str]:
    """Repeated meaningful words, used only when no heading is found."""
    words = re.findall(r"[A-Za-z]{4,}", text.lower())
    counts = Counter(w for w in words if w not in KEYWORD_STOPWORDS | UI_WORDS | SITE_NAMES
                     and not is_noise(w) and _looks_like_words(w))
    return [w for w, count in counts.most_common() if count >= min_count][:limit]


def _fallback(reason: str, candidates: list[TitleCandidate] | None = None) -> TitleAnalysis:
    return TitleAnalysis(None, "fallback", reason, candidates or [])


def analyze_text(result: OcrResult, settings: Settings | None = None) -> TitleAnalysis:
    """Decide the best title for an OCR result, or request the neutral fallback."""
    settings = settings or Settings()

    if result.error:
        return _fallback(result.error)
    if not result.lines:
        return _fallback("No text lines available.")

    text_chars = sum(ch.isalnum() for ch in result.full_text)
    if text_chars < settings.min_text_chars:
        return _fallback("Too little text to describe the screenshot.")
    if result.mean_confidence < settings.min_mean_confidence:
        return _fallback(f"OCR confidence too low ({result.mean_confidence:.0f}).")

    lines = content_lines(result)
    candidates = score_candidates(lines, result.image_height, settings)
    if candidates and candidates[0].score >= settings.min_title_score:
        best = candidates[0]
        return TitleAnalysis(
            best.title, "heading", f"Prominent heading (score {best.score})", candidates
        )

    keywords = extract_keywords("\n".join(line.text for line in lines
                                         if line.confidence >= settings.min_line_confidence
                                         and not is_noise(line.text)))
    if keywords:
        title = " ".join(word.capitalize() for word in keywords)
        return TitleAnalysis(title, "keywords", "Repeated keywords", candidates)

    return _fallback("No reliable heading or keywords found.", candidates)
