from __future__ import annotations

import logging
import os
import re
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from .classifier import Decision, classify_text

logger = logging.getLogger(__name__)

ARTICLE_DIR_RE = re.compile(r"^PMC\d+(?:\.\d+)?$", re.IGNORECASE)

@dataclass
class Article:

    pmcid: str
    folder: Path
    text_file: Path

def iter_articles(root: Path) -> Iterator[Article]:
    if not root.is_dir():
        raise FileNotFoundError(f"PMC root directory does not exist: {root}")

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if not ARTICLE_DIR_RE.match(entry.name):
            continue
        text_file = entry / f"{entry.name}.txt"
        if not text_file.is_file():
            txts = list(entry.glob("*.txt"))
            if len(txts) == 1:
                text_file = txts[0]
            else:
                logger.warning(
                    "Skipping %s: expected %s.txt, none found",
                    entry,
                    entry.name,
                )
                continue
        yield Article(pmcid=entry.name, folder=entry, text_file=text_file)

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def _classify_one(
    article_tuple: Tuple[str, str],
    min_plant_hits: int,
    min_bioeng_hits: int,
    min_primary_sections: int,
) -> Decision:
    pmcid, text_path = article_tuple
    try:
        text = _read_text(Path(text_path))
    except OSError as exc:
        decision = Decision(pmcid=pmcid, keep=False)
        decision.reasons.append(f"read error: {exc}")
        return decision

    return classify_text(
        pmcid,
        text,
        min_plant_hits=min_plant_hits,
        min_bioeng_hits=min_bioeng_hits,
        min_primary_sections=min_primary_sections,
    )

def classify_all(
    articles: List[Article],
    *,
    workers: Optional[int] = None,
    min_plant_hits: int = 2,
    min_bioeng_hits: int = 2,
    min_primary_sections: int = 2,
    progress_every: int = 200,
) -> Iterator[Tuple[Article, Decision]]:
    if workers is None:
        workers = max(1, (os.cpu_count() or 2) - 1)

    payloads = [(a.pmcid, str(a.text_file)) for a in articles]
    pmcid_to_article = {a.pmcid: a for a in articles}

    done = 0
    total = len(articles)
    if workers == 1 or total <= 1:
        for payload in payloads:
            decision = _classify_one(
                payload, min_plant_hits, min_bioeng_hits, min_primary_sections
            )
            done += 1
            if done % progress_every == 0 or done == total:
                logger.info("Classified %d / %d articles", done, total)
            yield pmcid_to_article[decision.pmcid], decision
        return

    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(
                _classify_one,
                payload,
                min_plant_hits,
                min_bioeng_hits,
                min_primary_sections,
            ): payload[0]
            for payload in payloads
        }
        for fut in as_completed(futures):
            decision = fut.result()
            done += 1
            if done % progress_every == 0 or done == total:
                logger.info("Classified %d / %d articles", done, total)
            yield pmcid_to_article[decision.pmcid], decision

def place_article(
    article: Article,
    output_dir: Path,
    *,
    mode: str = "copy-folder",
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    if mode == "copy-folder":
        dest = output_dir / article.folder.name
        if dest.exists():
            return dest
        shutil.copytree(article.folder, dest)
        return dest

    if mode == "copy-text":
        dest = output_dir / article.text_file.name
        if dest.exists():
            return dest
        shutil.copy2(article.text_file, dest)
        return dest

    if mode == "symlink":
        dest = output_dir / article.folder.name
        if dest.exists() or dest.is_symlink():
            return dest
        os.symlink(article.folder.resolve(), dest, target_is_directory=True)
        return dest

    raise ValueError(f"Unknown placement mode: {mode!r}")

__all__ = [
    "Article",
    "iter_articles",
    "classify_all",
    "place_article",
]
