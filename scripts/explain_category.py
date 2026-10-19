"""Show why screenshots get their category, to tune keywords and thresholds.

Usage (from the project root):
    python scripts/explain_category.py "C:/path/shot1.png" "C:/path/shot2.png"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import Settings
from src.categorizer import _category_text, _rule_scores, categorize, image_scores, semantic_scores
from src.ocr_engine import extract_text
from src.text_analyzer import content_text


def main(paths):
    settings = Settings()
    for raw in paths:
        path = Path(raw)
        text = content_text(extract_text(path, settings))
        cleaned = _category_text(text)
        scores, matches = _rule_scores(cleaned, settings)
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:4]
        result = categorize(text, settings, image_path=path)
        print(f"\n=== {path.name}")
        print(f"OCR chars: {len(text)}")
        print(f"OCR preview: {' | '.join(cleaned.splitlines()[:6])[:200]!r}")
        for name, score in ranked:
            print(f"  {name:14} {score:3}  {', '.join(matches[name][:8])}")
        semantic = semantic_scores(cleaned, settings)
        if semantic:
            print("  meaning: " + ", ".join(f"{n} {v:.2f}" for n, v in semantic.scores[:5]))
        else:
            print("  meaning: unavailable (text too short? fastembed missing? semantic_enabled False?)")
        image = image_scores(path, settings)
        if image:
            print("  image:   " + ", ".join(f"{n} {p:.2f}" for n, p in image.scores[:5])
                  + f"  (best cosine {image.similarity:.2f})")
        else:
            print("  image:   unavailable (image_enabled False? CLIP models not downloaded?)")
        print(f"  -> {result.category} (confidence {result.confidence}, {result.method})")
        print(f"     {result.reason}")


if __name__ == "__main__":
    main(sys.argv[1:]) if len(sys.argv) > 1 else print(__doc__)
