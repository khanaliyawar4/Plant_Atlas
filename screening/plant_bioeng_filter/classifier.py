from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .rules import (
    BIOENG_RE,
    NON_PLANT_BIAS_RE,
    NON_PRIMARY_HEADER_PATTERNS,
    PLANT_RE,
    PRIMARY_RESEARCH_SECTION_MARKERS,
    REVIEW_BODY_PATTERNS,
)

DEFAULT_MIN_PLANT_HITS = 2
DEFAULT_MIN_BIOENG_HITS = 2
DEFAULT_MIN_PRIMARY_SECTIONS = 2
HEADER_REGION_CHARS = 4000

@dataclass
class Decision:

    pmcid: str
    keep: bool
    reasons: List[str] = field(default_factory=list)
    plant_hits: int = 0
    bioeng_hits: int = 0
    non_plant_bias_hits: int = 0
    primary_section_hits: int = 0
    non_primary_header_match: Optional[str] = None
    review_body_match: Optional[str] = None
    word_count: int = 0

    def as_row(self) -> dict:
        return {
            "pmcid": self.pmcid,
            "keep": "yes" if self.keep else "no",
            "reasons": "; ".join(self.reasons),
            "plant_hits": self.plant_hits,
            "bioeng_hits": self.bioeng_hits,
            "non_plant_bias_hits": self.non_plant_bias_hits,
            "primary_section_hits": self.primary_section_hits,
            "non_primary_header_match": self.non_primary_header_match or "",
            "review_body_match": self.review_body_match or "",
            "word_count": self.word_count,
        }

def _count_unique_matches(regex, text: str) -> int:
    seen = set()
    for m in regex.finditer(text):
        seen.add(m.group(0).lower())
    return len(seen)

def _find_first(patterns, text: str) -> Optional[str]:
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(0).strip()
    return None

def classify_text(
    pmcid: str,
    text: str,
    *,
    min_plant_hits: int = DEFAULT_MIN_PLANT_HITS,
    min_bioeng_hits: int = DEFAULT_MIN_BIOENG_HITS,
    min_primary_sections: int = DEFAULT_MIN_PRIMARY_SECTIONS,
) -> Decision:

    decision = Decision(pmcid=pmcid, keep=False)
    decision.word_count = len(text.split())

    if decision.word_count < 500:
        decision.reasons.append("text too short (<500 words)")
        return decision

    header = text[:HEADER_REGION_CHARS]

    non_primary = _find_first(NON_PRIMARY_HEADER_PATTERNS, header)
    if non_primary:
        decision.non_primary_header_match = non_primary
        decision.reasons.append(f"non-primary article type in header: '{non_primary}'")
        return decision

    review_body = _find_first(REVIEW_BODY_PATTERNS, text)
    if review_body:
        decision.review_body_match = review_body
        decision.reasons.append(f"review/perspective body language: '{review_body}'")
        return decision

    primary_section_hits = sum(
        1 for p in PRIMARY_RESEARCH_SECTION_MARKERS if p.search(text)
    )
    decision.primary_section_hits = primary_section_hits
    if primary_section_hits < min_primary_sections:
        decision.reasons.append(
            f"missing primary-research sections ({primary_section_hits} found, "
            f"need >= {min_primary_sections})"
        )
        return decision

    plant_hits = _count_unique_matches(PLANT_RE, text)
    decision.plant_hits = plant_hits
    if plant_hits < min_plant_hits:
        decision.reasons.append(
            f"insufficient plant vocabulary ({plant_hits} unique hits, "
            f"need >= {min_plant_hits})"
        )
        return decision

    non_plant_bias_hits = _count_unique_matches(NON_PLANT_BIAS_RE, text)
    decision.non_plant_bias_hits = non_plant_bias_hits
    if non_plant_bias_hits >= 3 and non_plant_bias_hits > plant_hits:
        decision.reasons.append(
            f"non-plant study system dominates ({non_plant_bias_hits} non-plant "
            f"terms vs {plant_hits} plant terms)"
        )
        return decision

    bioeng_hits = _count_unique_matches(BIOENG_RE, text)
    decision.bioeng_hits = bioeng_hits
    if bioeng_hits < min_bioeng_hits:
        decision.reasons.append(
            f"insufficient bioengineering vocabulary ({bioeng_hits} unique hits, "
            f"need >= {min_bioeng_hits})"
        )
        return decision

    decision.keep = True
    decision.reasons.append(
        f"primary research with plant ({plant_hits}) and bioengineering "
        f"({bioeng_hits}) signals"
    )
    return decision

__all__ = ["Decision", "classify_text"]
