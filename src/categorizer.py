"""Hybrid categories: weighted keywords + structural patterns + local meaning (text) + local vision (image).

Decision order (each tier only runs if the previous one did not decide):
  1. Decisive keyword evidence wins outright.
  2. Meaning of the OCR text (embeddings) + a keyword bonus.
  3. The screenshot itself (CLIP zero-shot) - covers dark themes, video frames, file explorers,
     and anything where OCR found little or no text.
  4. Usable (but not decisive) keyword evidence rescues the result.
  5. Only then -> Uncategorized.
"""
from __future__ import annotations

import logging
import math
import re
import unicodedata
from dataclasses import dataclass

from config import Settings
from src.content_filter import meaningful_line

logger = logging.getLogger(__name__)

WORD_RE = re.compile(r"[a-z0-9]+")
URL_RE = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
METADATA_RE = re.compile(
    r"^(?:certificate\s+(?:no\b|number\b|id\b)|"
    r"(?:valid\s+(?:through|until|from)|issued\s+on|issue\s+date|expiration\s+date)\b|"
    r"(?:validate|verify)\s+(?:this\s+)?certificate\b|validation\s+(?:url|link)\b)", re.I,
)
RECIPIENT_RE = re.compile(
    r"^(?:recipient(?:\s+name)?|candidate\s+name|student\s+name|name|"
    r"presented\s+to|awarded\s+to|this\s+is\s+to\s+certify\s+that)\s*(?::|$)", re.I,
)


def _category_text(text: str) -> str:
    """Remove identifiable administrative fields, without guessing unlabelled names."""
    lines: list[str] = []
    skip_recipient = False
    for line in unicodedata.normalize("NFKC", text).splitlines():
        line = meaningful_line(line) or ""
        if not line:
            continue
        if skip_recipient:
            skip_recipient = False
            continue
        recipient = RECIPIENT_RE.match(line)
        if recipient:
            skip_recipient = not line[recipient.end():].strip()
            continue
        if METADATA_RE.match(line):
            continue
        lines.append(URL_RE.sub("", line))
    return "\n".join(lines)


@dataclass(frozen=True)
class CategoryResult:
    category: str
    score: int
    matched: tuple[str, ...]
    reason: str
    confidence: float = 0.0      # 0..1, how sure the final decision is
    method: str = "rules"        # rules | semantic | semantic+keywords | image | image+keywords


def _rule_scores(text: str, settings: Settings):
    lowered = text.lower()
    normalized = " " + " ".join(WORD_RE.findall(lowered)) + " "
    scores: dict[str, int] = {}
    matches: dict[str, tuple[str, ...]] = {}
    for category, keywords in settings.categories.items():
        hits = {word: weight for word, weight in keywords.items()
                if " " + " ".join(WORD_RE.findall(word.lower())) + " " in normalized}
        for label, pattern, weight in settings.category_patterns.get(category, ()):
            if re.search(pattern, lowered, re.I | re.M):
                hits[label] = weight
        scores[category] = sum(hits.values())
        matches[category] = tuple(sorted(hits))
    return scores, matches


def _confidence(best: int, runner_up: int) -> float:
    if best <= 0:
        return 0.0
    return round(min(best / 8, 1) * 0.6 + ((best - runner_up) / best) * 0.4, 2)


def _rules(text: str, settings: Settings) -> CategoryResult:
    uncategorized = settings.uncategorized_name
    if not WORD_RE.search(text.lower()) or not settings.categories:
        return CategoryResult(uncategorized, 0, (), "No text available.")

    scores, matches = _rule_scores(text, settings)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_name, best_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0

    if best_score < settings.category_min_score:
        return CategoryResult(uncategorized, best_score, matches[best_name],
                              f"Weak evidence (best {best_name} {best_score}).",
                              _confidence(best_score, runner_up))
    if best_score - runner_up < settings.category_min_margin:
        return CategoryResult(uncategorized, best_score, matches[best_name],
                              f"Ambiguous ({best_name} {best_score} vs {ranked[1][0]} {runner_up}).",
                              _confidence(best_score, runner_up))
    return CategoryResult(best_name, best_score, matches[best_name],
                          f"Matched: {', '.join(matches[best_name])} (score {best_score}; runner-up {runner_up})",
                          _confidence(best_score, runner_up), "rules")


def semantic_scores(text: str, settings: Settings):
    """Meaning-based similarity to every real category, or None if the semantic layer is unavailable."""
    if not settings.semantic_enabled or not settings.category_descriptions:
        return None
    try:
        from src import semantic_classifier
        # "Uncategorized" is deliberately NOT a competing class: UI-heavy OCR always resembles it.
        descriptions = {name: desc for name, desc in settings.category_descriptions.items()
                        if name in settings.categories}
        return semantic_classifier.classify(text, descriptions)
    except Exception as exc:  # never let the optional layer break organizing
        logger.warning("Semantic layer skipped: %s", exc)
        return None


def image_scores(image_path, settings: Settings):
    """Vision-based probability for every real category, or None if disabled/unavailable/no image given."""
    if image_path is None or not settings.image_enabled or not settings.image_descriptions:
        return None
    try:
        from src import image_classifier
        descriptions = {name: desc for name, desc in settings.image_descriptions.items()
                        if name in settings.categories}
        return image_classifier.classify_image(image_path, descriptions)
    except Exception as exc:  # never let the optional layer break organizing
        logger.warning("Image layer skipped: %s", exc)
        return None


def categorize(text: str, settings: Settings, image_path=None, *, interface_hint=None) -> CategoryResult:
    """Decide using keywords, text meaning and (optionally) the screenshot image.

    `image_path` is optional so existing callers keep working; pass it to enable the vision tier.
    """
    text = _category_text(text)
    uncategorized = settings.uncategorized_name
    rule_points, rule_hits = _rule_scores(text, settings)

    ranked_rules = sorted(rule_points.values(), reverse=True) or [0]
    r_best = ranked_rules[0]
    r_runner = ranked_rules[1] if len(ranked_rules) > 1 else 0
    lead = r_best - r_runner
    rules_decisive = (r_best >= settings.rules_decisive_score
                      and lead >= settings.rules_decisive_margin)
    rules_usable = (r_best >= settings.category_min_score
                    and lead >= settings.category_min_margin)

    # Tier 1: strong, unambiguous keyword evidence.
    if rules_decisive:
        return _rules(text, settings)

    # A visually corroborated app identity is useful when content is weak. It is
    # passed separately so navigation labels never become titles or topic keywords.
    if interface_hint == "AI Chat" and interface_hint in settings.categories:
        if rules_usable:
            return _rules(text, settings)
        return CategoryResult(
            interface_hint, 0, (),
            "ChatGPT header and central composer detected; no clear content category.",
            method="interface",
        )

    # Tier 2: meaning of the text + keyword bonus.
    unsure: CategoryResult | None = None
    semantic = semantic_scores(text, settings)
    if semantic is not None:
        sims = dict(semantic.scores)
        combined = {
            name: sim + min(rule_points.get(name, 0), settings.keyword_bonus_cap) * settings.keyword_bonus_per_point
            for name, sim in sims.items()
        }
        ranked = sorted(combined.items(), key=lambda kv: kv[1], reverse=True)
        best, best_value = ranked[0]
        runner, runner_value = ranked[1] if len(ranked) > 1 else (None, best_value - 1.0)
        margin = best_value - runner_value

        # Relative confidence: softmax over combined scores (robust to the model's compressed range).
        temperature = settings.semantic_temperature
        exps = {name: math.exp((value - best_value) / temperature) for name, value in combined.items()}
        prob = exps[best] / sum(exps.values())

        summary = (f"Meaning: {best} {sims[best]:.2f}"
                   + (f" vs {runner} {sims[runner]:.2f}" if runner else "")
                   + (f"; keywords: {', '.join(rule_hits[best][:5])}" if rule_points.get(best) else "")
                   + f"; p={prob:.2f}")

        if (sims[best] >= settings.semantic_min_similarity
                and margin >= settings.semantic_min_margin
                and prob >= settings.semantic_min_prob):
            return CategoryResult(best, rule_points.get(best, 0), rule_hits.get(best, ()), summary,
                                  round(prob, 2),
                                  "semantic+keywords" if rule_points.get(best) else "semantic")
        unsure = CategoryResult(uncategorized, rule_points.get(best, 0), rule_hits.get(best, ()),
                                f"Not clearly any category ({summary}).", round(prob, 2), "semantic")

    # Tier 3: look at the screenshot itself (dark themes, videos, file explorers, little OCR text).
    image = image_scores(image_path, settings)
    if image is not None:
        runner_name, runner_prob = image.scores[1] if len(image.scores) > 1 else ("", 0.0)
        image_note = (f"Image: {image.category} p={image.probability:.2f}"
                      + (f" vs {runner_name} {runner_prob:.2f}" if runner_name else ""))
        keyword_note = (f"; keywords: {', '.join(rule_hits[image.category][:5])}"
                        if rule_points.get(image.category) else "")
        if (image.probability >= settings.image_min_prob
                and image.similarity >= settings.image_min_similarity):
            return CategoryResult(image.category, rule_points.get(image.category, 0),
                                  rule_hits.get(image.category, ()), image_note + keyword_note,
                                  round(image.probability, 2),
                                  "image+keywords" if rule_points.get(image.category) else "image")
        if unsure is not None:
            unsure = CategoryResult(unsure.category, unsure.score, unsure.matched,
                                    f"{unsure.reason.rstrip('.)')}; {image_note}).",
                                    unsure.confidence, unsure.method)
        else:
            unsure = CategoryResult(uncategorized, 0, (), f"Image not decisive ({image_note}).",
                                    round(image.probability, 2), "image")

    # Tier 4: usable keyword evidence rescues the result.
    if rules_usable:
        rescued = _rules(text, settings)
        if rescued.category != uncategorized:
            return rescued

    # Tier 5: genuinely unclear.
    return unsure if unsure is not None else _rules(text, settings)
