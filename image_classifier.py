"""Zero-shot screenshot classification straight from the pixels (CLIP). Fully offline after the first download.

Why this exists: OCR reads very little from dark themes, video frames, file explorers and image-heavy
pages, so the text layers have nothing to work with. CLIP compares the whole screenshot with short
prompts such as "a screenshot of a YouTube video page", so it can still recognise what it is looking at.

Install:  pip install fastembed          (same package as the text classifier)
Models:   Qdrant/clip-ViT-B-32-vision + Qdrant/clip-ViT-B-32-text, downloaded once (a few hundred MB).
If anything is unavailable, classify_image() returns None and the other layers decide.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_MODEL = "Qdrant/clip-ViT-B-32-vision"
TEXT_MODEL = "Qdrant/clip-ViT-B-32-text"
LOGIT_SCALE = 100.0   # CLIP's own temperature: turns tiny cosine gaps into usable probabilities


@dataclass(frozen=True)
class ImageResult:
    category: str
    probability: float                       # share of probability mass held by the winner (0..1)
    similarity: float                        # raw cosine similarity of the winner (typically 0.15-0.35)
    scores: tuple[tuple[str, float], ...]    # (category, probability), best first


@lru_cache(maxsize=1)
def _image_model():
    try:
        from fastembed import ImageEmbedding
        return ImageEmbedding(model_name=IMAGE_MODEL)
    except Exception as exc:
        logger.warning("Image classification unavailable: %s", exc)
        return None


@lru_cache(maxsize=1)
def _text_model():
    try:
        from fastembed import TextEmbedding
        return TextEmbedding(model_name=TEXT_MODEL)
    except Exception as exc:
        logger.warning("Image classification unavailable: %s", exc)
        return None


def _normalize(vectors):
    import numpy as np
    vectors = np.asarray(vectors, dtype=float)
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(norms, 1e-9)


@lru_cache(maxsize=4)
def _prompt_matrix(prompts: tuple[tuple[str, str], ...]):
    import numpy as np
    model = _text_model()
    if model is None:
        return None
    vectors = np.array(list(model.embed([text for _, text in prompts])), dtype=float)
    return [owner for owner, _ in prompts], _normalize(vectors)


def classify_image(path, descriptions: dict[str, list[str]]) -> ImageResult | None:
    """Probability of each category for this screenshot (best prompt per category, softmax across categories)."""
    import numpy as np

    path = Path(path)
    if not descriptions or not path.is_file():
        return None
    prompts = tuple((name, sentence) for name, sentences in sorted(descriptions.items())
                    for sentence in ([sentences] if isinstance(sentences, str) else sentences))
    prepared = _prompt_matrix(prompts)
    model = _image_model()
    if prepared is None or model is None:
        return None
    owners, matrix = prepared
    try:
        image_vector = _normalize(np.array(list(model.embed([str(path)])), dtype=float))[0]
        sims = matrix @ image_vector
    except Exception as exc:
        logger.warning("Image classification failed for %s: %s", path.name, exc)
        return None

    best: dict[str, float] = {}
    for owner, sim in zip(owners, sims):
        best[owner] = max(best.get(owner, -1.0), float(sim))
    top = max(best.values())
    exps = {name: math.exp(LOGIT_SCALE * (sim - top)) for name, sim in best.items()}
    total = sum(exps.values())
    ranked = sorted(((name, exps[name] / total) for name in best), key=lambda p: p[1], reverse=True)
    winner = ranked[0][0]
    return ImageResult(winner, round(ranked[0][1], 3), round(best[winner], 3),
                       tuple((n, round(p, 3)) for n, p in ranked))
