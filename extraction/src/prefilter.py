from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import regex as re

from .article_io import Article

class PrefilterResult(NamedTuple):
    keep: bool
    reason: str

@dataclass
class Prefilter:
    skip_article_types:  list[re.Pattern]
    plant_terms:         list[re.Pattern]
    engineering_terms:   list[re.Pattern]

    @classmethod
    def from_config(cls, cfg: dict) -> "Prefilter":
        type_flags = re.IGNORECASE
        word_flags = re.IGNORECASE
        return cls(
            skip_article_types=[
                re.compile(rf"\b{p}\b", type_flags) for p in cfg["skip_article_types"]
            ],
            plant_terms=[
                re.compile(rf"\b{p}", word_flags) for p in cfg["require_plant_terms"]
            ],
            engineering_terms=[
                re.compile(rf"\b{p}", word_flags) for p in cfg["require_engineering_terms"]
            ],
        )

    def _is_blocked_article_type(self, article_type: str | None) -> str | None:
        if not article_type:
            return None
        for p in self.skip_article_types:
            if p.search(article_type):
                return f"article_type='{article_type}' matched skip pattern '{p.pattern}'"
        return None

    def _hits(self, patterns: list[re.Pattern], text: str) -> int:
        return sum(1 for p in patterns if p.search(text))

    def check(self, article: Article) -> PrefilterResult:
        reason = self._is_blocked_article_type(article.article_type)
        if reason:
            return PrefilterResult(keep=False, reason=reason)

        haystack = article.full_text
        if self._hits(self.plant_terms, haystack) == 0:
            return PrefilterResult(keep=False, reason="no plant-system terms found in full text")
        if self._hits(self.engineering_terms, haystack) == 0:
            return PrefilterResult(keep=False, reason="no genetic-engineering terms found in full text")

        if len(article.body.strip()) < 500:
            return PrefilterResult(keep=False, reason=f"body too short ({len(article.body)} chars)")

        return PrefilterResult(keep=True, reason="passed prefilter")
