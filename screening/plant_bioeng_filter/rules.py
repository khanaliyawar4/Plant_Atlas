from __future__ import annotations

import re
from typing import Iterable, Pattern

PLANT_TERMS: tuple[str, ...] = (
    "plant", "plants", "plantlet", "seedling", "seedlings",
    "leaf", "leaves", "root", "roots", "shoot", "shoots",
    "stem", "stems", "flower", "flowers", "fruit", "fruits",
    "seed", "seeds", "pollen", "stomata", "stomatal",
    "chloroplast", "chloroplasts", "thylakoid", "photosynthesis",
    "photosynthetic", "phytohormone", "phytohormones",
    "phloem", "xylem", "mesophyll", "cotyledon", "hypocotyl",
    "germination", "tuber", "rhizome",
    "angiosperm", "angiosperms", "gymnosperm", "gymnosperms",
    "monocot", "monocots", "dicot", "dicots", "eudicot", "eudicots",
    "bryophyte", "bryophytes", "moss", "mosses", "fern", "ferns",
    "arabidopsis", "thaliana",
    "nicotiana", "tobacco", "benthamiana",
    "oryza sativa", "rice",
    "zea mays", "maize", "corn",
    "triticum", "wheat",
    "hordeum vulgare", "barley",
    "glycine max", "soybean", "soybeans",
    "solanum lycopersicum", "tomato", "tomatoes",
    "solanum tuberosum", "potato", "potatoes",
    "medicago truncatula", "medicago",
    "brassica", "rapeseed", "canola",
    "sorghum bicolor", "sorghum",
    "gossypium", "cotton",
    "populus", "poplar",
    "marchantia", "physcomitrella", "physcomitrium",
    "chlamydomonas", "reinhardtii",
    "sugarcane", "saccharum",
    "cassava", "manihot",
    "grapevine", "vitis",
    "apple", "malus",
    "citrus",
    "banana", "musa",
    "switchgrass", "panicum virgatum",
    "miscanthus",
    "setaria", "setaria italica",
    "cannabis", "hemp",
)

NON_PLANT_BIAS_TERMS: tuple[str, ...] = (
    "patient", "patients", "clinical trial", "clinically",
    "mouse", "mice", "murine", "rat ", "rats ",
    "drosophila", "zebrafish", "c. elegans", "caenorhabditis",
    "saccharomyces cerevisiae", "yeast cells",
    "escherichia coli", "e. coli",
    "tumor", "tumour", "carcinoma", "glioma",
    "covid", "sars-cov", "influenza",
)

BIOENG_TERMS: tuple[str, ...] = (
    "crispr", "crispr/cas9", "crispr-cas9", "crispr-cas12",
    "cas9", "cas12a", "cpf1", "base editing", "prime editing",
    "talen", "talens", "zinc finger nuclease", "zfn",
    "guide rna", "sgrna", "grna",
    "transgenic", "transgene", "transgenes", "transformation",
    "agrobacterium", "agrobacterium-mediated",
    "biolistic", "particle bombardment", "gene gun",
    "floral dip", "transient expression",
    "knock-out", "knockout", "knock-in", "knockin", "knock-down", "knockdown",
    "overexpression", "over-expression", "overexpressing",
    "rnai", "rna interference", "amirna", "artificial microrna",
    "vigs", "virus-induced gene silencing",
    "synthetic biology", "synbio",
    "metabolic engineering", "metabolic pathway engineering",
    "pathway engineering", "biosynthetic pathway",
    "heterologous expression", "heterologous production",
    "chassis", "biofactory", "molecular farming",
    "plant-made", "plant-produced", "plant expression system",
    "genetic engineering", "genetically engineered",
    "genetically modified", "gmo",
    "genome engineering", "genome edited", "genome-edited",
    "trait engineering", "biofortification", "biofortified",
    "engineered plants", "engineered crop", "engineered crops",
    "engineered line", "engineered lines",
    "35s promoter", "camv35s", "camv 35s",
    "ubiquitin promoter", "nptii", "hygromycin resistance",
    "selectable marker", "expression cassette", "binary vector",
    "callus", "tissue culture", "in vitro regeneration",
    "protoplast", "protoplasts", "hairy root", "hairy roots",
)

NON_PRIMARY_HEADER_PATTERNS: tuple[Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\b(review article|review-article)\b",
        r"\bmini[- ]review\b",
        r"\bsystematic review\b",
        r"\bnarrative review\b",
        r"\bmeta[- ]analysis\b",
        r"\bperspective\b",
        r"\bopinion\b",
        r"\bcommentary\b",
        r"\beditorial\b",
        r"\bviewpoint\b",
        r"\bbook review\b",
        r"\bcorrection\b",
        r"\berratum\b",
        r"\bretraction\b",
        r"\bnews and views\b",
        r"\bnews\s*&\s*views\b",
        r"\bletter to the editor\b",
        r"\bcorrespondence\b",
        r"\bcase report\b",
        r"\bprotocol\b",
    )
)

PRIMARY_RESEARCH_SECTION_MARKERS: tuple[Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE | re.MULTILINE)
    for p in (
        r"^\s*materials?\s+and\s+methods\s*$",
        r"^\s*methods?\s*$",
        r"^\s*experimental\s+procedures?\s*$",
        r"^\s*results?\s*$",
        r"^\s*results?\s+and\s+discussion\s*$",
        r"^\s*discussion\s*$",
        r"^\s*conclusions?\s*$",
    )
)

REVIEW_BODY_PATTERNS: tuple[Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bin this review\b",
        r"\bthis review (summari[sz]es|covers|discusses|focuses|aims)\b",
        r"\bwe review\b",
        r"\bhere,? we (review|summari[sz]e the literature)\b",
        r"\bthis perspective\b",
        r"\bin this perspective\b",
        r"\bthis opinion\b",
        r"\bthis commentary\b",
        r"\bthis editorial\b",
    )
)

def _compile_word_set(terms: Iterable[str]) -> Pattern[str]:
    escaped = sorted({re.escape(t.lower()) for t in terms}, key=len, reverse=True)
    pattern = r"(?<![A-Za-z0-9])(?:" + "|".join(escaped) + r")(?![A-Za-z0-9])"
    return re.compile(pattern, re.IGNORECASE)

PLANT_RE: Pattern[str] = _compile_word_set(PLANT_TERMS)
NON_PLANT_BIAS_RE: Pattern[str] = _compile_word_set(NON_PLANT_BIAS_TERMS)
BIOENG_RE: Pattern[str] = _compile_word_set(BIOENG_TERMS)

__all__ = [
    "PLANT_TERMS",
    "NON_PLANT_BIAS_TERMS",
    "BIOENG_TERMS",
    "PLANT_RE",
    "NON_PLANT_BIAS_RE",
    "BIOENG_RE",
    "NON_PRIMARY_HEADER_PATTERNS",
    "PRIMARY_RESEARCH_SECTION_MARKERS",
    "REVIEW_BODY_PATTERNS",
]
