"""Optional local semantic classifier (embedding similarity). Fully offline after the first model download.

Install:  pip install fastembed
Enable:   Settings.semantic_enabled = True in config.py
If the package or model is unavailable, classify() returns None and the rule-based result is used.

The OCR text is scored two ways and blended: as a whole, and as small chunks of lines. Chunking stops one
useful region (e.g. a video title) from being drowned out by dozens of UI labels around it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MAX_CHARS = 1500          # the model reads ~512 tokens; more text adds noise and time
MIN_CHARS = 20
CHUNK_CHARS = 280         # size of one line-window
MAX_CHUNKS = 8            # cap on embedding work per screenshot


@dataclass(frozen=True)
class SemanticResult:
    category: str
    similarity: float
    margin: float                                   # lead over the runner-up
    scores: tuple[tuple[str, float], ...]           # every category, best first


@lru_cache(maxsize=1)
def _model():
    try:
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=MODEL_NAME)
    except Exception as exc:  # package missing, offline on first run, corrupt cache...
        logger.warning("Semantic classification unavailable: %s", exc)
        return None


def _embed(model, texts):
    import numpy as np
    vectors = np.array(list(model.embed(texts)), dtype=float)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


@lru_cache(maxsize=4)
def _prototype_matrix(prototypes: tuple[tuple[str, str], ...]):
    model = _model()
    if model is None:
        return None
    return [owner for owner, _ in prototypes], _embed(model, [text for _, text in prototypes])


def _chunks(text: str) -> list[str]:
    """Group OCR lines into small windows so one useful region isn't diluted by UI noise."""
    chunks: list[str] = []
    current = ""
    for line in (l.strip() for l in text.splitlines()):
        if len(line) < 3:
            continue
        if current and len(current) + len(line) + 1 > CHUNK_CHARS:
            chunks.append(current)
            current = line
        else:
            current = f"{current} {line}".strip()
    if current:
        chunks.append(current)
    return chunks[:MAX_CHUNKS]


def classify(text: str, descriptions: dict[str, list[str]]) -> SemanticResult | None:
    """Per-category similarity = 50% whole text + 50% mean of the two best-matching chunks."""
    import numpy as np

    text = text.strip()[: MAX_CHARS * 2]
    flat = " ".join(text.split())
    if len(flat) < MIN_CHARS or not descriptions:
        return None

    prototypes = tuple((name, sentence) for name, sentences in sorted(descriptions.items())
                       for sentence in ([sentences] if isinstance(sentences, str) else sentences))
    prepared = _prototype_matrix(prototypes)
    if prepared is None:
        return None
    owners, matrix = prepared

    pieces = [flat[:MAX_CHARS]] + _chunks(text)
    try:
        sims = _embed(_model(), pieces) @ matrix.T          # pieces x prototypes
    except Exception as exc:
        logger.warning("Semantic classification failed: %s", exc)
        return None

    # Best example sentence per category, for each piece of text.
    cats = sorted(set(owners))
    per_piece = np.full((len(pieces), len(cats)), -1.0)
    for j, owner in enumerate(owners):
        k = cats.index(owner)
        per_piece[:, k] = np.maximum(per_piece[:, k], sims[:, j])

    whole = per_piece[0]
    local = per_piece[1:] if len(pieces) > 1 else per_piece
    top = np.sort(local, axis=0)[-2:].mean(axis=0)          # two best-matching chunks
    final = 0.5 * whole + 0.5 * top

    ranked = sorted(zip(cats, final.tolist()), key=lambda pair: pair[1], reverse=True)
    margin = ranked[0][1] - ranked[1][1] if len(ranked) > 1 else ranked[0][1]
    return SemanticResult(ranked[0][0], round(ranked[0][1], 3), round(margin, 3),
                          tuple((n, round(v, 3)) for n, v in ranked))