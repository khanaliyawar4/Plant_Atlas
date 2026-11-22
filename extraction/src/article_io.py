from __future__ import annotations

import re as _re_stdlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import regex as re

_FILENAME_RE = re.compile(r"^(PMC\d+)\.(\d+)\.txt$", re.IGNORECASE)

def parse_filename(path: Path) -> tuple[str, int] | None:
    m = _FILENAME_RE.match(path.name)
    if not m:
        return None
    return m.group(1).upper(), int(m.group(2))

_DOI_RE = re.compile(
    r"""(?xi)
    \b(?:doi[:\s]*|https?://(?:dx\.)?doi\.org/)
    (10\.\d{4,9}/[^\s"'<>)\]]+)
    """,
)

_ARTICLE_TYPE_RE = re.compile(
    r"""(?ix)
    ^[ \t]*
    (?:article\s+type|type\s+of\s+article|document\s+type)
    [ \t]*[:\-]\s*
    (?P<value>[^\n\r]{1,80})
    """,
    re.MULTILINE,
)

def extract_doi(text: str) -> str | None:
    m = _DOI_RE.search(text)
    if not m:
        return None
    doi = m.group(1).rstrip(".,;)")
    return doi

def extract_article_type(text: str) -> str | None:
    m = _ARTICLE_TYPE_RE.search(text[:4000])
    if not m:
        return None
    val = re.sub(r"\s+", " ", m.group("value")).strip().lower()
    return val or None

@dataclass
class SectionConfig:
    body_start: list[re.Pattern]
    body_end:   list[re.Pattern]
    max_chars:  int

    @classmethod
    def from_dict(cls, d: dict) -> "SectionConfig":
        flags = re.IGNORECASE | re.MULTILINE
        return cls(
            body_start=[re.compile(p, flags) for p in d["body_start_patterns"]],
            body_end=[re.compile(p, flags)   for p in d["body_end_patterns"]],
            max_chars=int(d["max_chars"]),
        )

def _first_match_offset(patterns: Iterable[re.Pattern], text: str, start: int = 0) -> int | None:
    best = None
    for p in patterns:
        m = p.search(text, pos=start)
        if m is not None:
            if best is None or m.start() < best:
                best = m.start()
    return best

def slice_body(text: str, cfg: SectionConfig) -> str:
    start_off = _first_match_offset(cfg.body_start, text)
    if start_off is None:
        start_off = len(text) // 2

    end_off = _first_match_offset(cfg.body_end, text, start=start_off + 1)
    if end_off is None:
        end_off = len(text)

    body = text[start_off:end_off].strip()
    if len(body) > cfg.max_chars:
        head = cfg.max_chars // 2
        tail = cfg.max_chars - head
        body = body[:head] + "\n\n[... body truncated for length ...]\n\n" + body[-tail:]
    return body

@dataclass
class Article:
    path: Path
    pmcid: str
    version: int
    doi: str | None
    article_type: str | None
    body: str
    full_text: str

def load_article(path: Path, section_cfg: SectionConfig) -> Article | None:
    parsed = parse_filename(path)
    if parsed is None:
        return None
    pmcid, version = parsed

    full_text = path.read_text(encoding="utf-8", errors="replace")

    return Article(
        path=path,
        pmcid=pmcid,
        version=version,
        doi=extract_doi(full_text),
        article_type=extract_article_type(full_text),
        body=slice_body(full_text, section_cfg),
        full_text=full_text,
    )

def iter_article_paths(input_dir: Path) -> Iterable[Path]:
    yield from sorted(p for p in input_dir.iterdir()
                      if p.is_file() and _FILENAME_RE.match(p.name))
