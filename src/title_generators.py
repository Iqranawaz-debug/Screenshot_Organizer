"""Pluggable title generation. Version 1 ships only the rule-based generator."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from config import Settings
from src.models import OcrResult, TitleAnalysis
from src.text_analyzer import analyze_text


@runtime_checkable
class TitleGenerator(Protocol):
    """Anything that turns OCR output into a TitleAnalysis.

    A future LLM-based generator implements `generate` and must obey the same
    contract: only use words supported by the OCR text, and return
    TitleAnalysis(title=None, source="fallback", ...) when unsure.
    """

    name: str

    def generate(self, result: OcrResult, settings: Settings) -> TitleAnalysis: ...


class RuleBasedTitleGenerator:
    """The default generator: wraps the rule-based analyzer from Phase 2."""

    name = "rule_based"

    def generate(self, result: OcrResult, settings: Settings) -> TitleAnalysis:
        return analyze_text(result, settings)


DEFAULT_TITLE_GENERATOR: TitleGenerator = RuleBasedTitleGenerator()
