from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

from .scanner import classify_all, iter_articles, place_article

REPORT_FIELDS = [
    "pmcid",
    "keep",
    "reasons",
    "plant_hits",
    "bioeng_hits",
    "non_plant_bias_hits",
    "primary_section_hits",
    "non_primary_header_match",
    "review_body_match",
    "word_count",
]

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="plant_bioeng_filter",
        description=(
            "Filter a local PMC text dump down to primary research articles "
            "that report plant bioengineering. Selected articles are placed "
            "in an output folder (default: ./plant_bioengineering)."
        ),
    )
    p.add_argument(
        "--pmc-root",
        type=Path,
        default=Path("./pmc/text"),
        help="Directory containing PMC<id>.<ver>/ subfolders (default: ./pmc/text)",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("./plant_bioengineering"),
        help="Where to place kept articles (default: ./plant_bioengineering)",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=None,
        help=(
            "Path to a CSV report of every article's decision. "
            "Defaults to '<output>/_decisions.csv'. "
            "Pass '--report -' to disable the report."
        ),
    )
    p.add_argument(
        "--placement",
        choices=("copy-folder", "copy-text", "symlink"),
        default="copy-text",
        help="How to place each kept article in --output (default: copy-text)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes (default: CPU count - 1).",
    )
    p.add_argument(
        "--min-plant-hits",
        type=int,
        default=2,
        help="Minimum unique plant-vocabulary hits required (default: 2).",
    )
    p.add_argument(
        "--min-bioeng-hits",
        type=int,
        default=2,
        help="Minimum unique bioengineering-vocabulary hits required (default: 2).",
    )
    p.add_argument(
        "--min-primary-sections",
        type=int,
        default=2,
        help="Minimum primary-research section headers required (default: 2).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N articles (useful for testing).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify but do not copy/symlink anything to --output.",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging.",
    )
    return p

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    log = logging.getLogger("plant_bioeng_filter")

    if not args.pmc_root.exists():
        log.error("PMC root directory does not exist: %s", args.pmc_root)
        return 2

    articles = list(iter_articles(args.pmc_root))
    if args.limit is not None:
        articles = articles[: args.limit]
    if not articles:
        log.error("No articles found under %s", args.pmc_root)
        return 2
    log.info("Found %d articles under %s", len(articles), args.pmc_root)

    report_writer = None
    report_fh = None
    report_path: Path | None
    if args.report is None:
        report_path = args.output / "_decisions.csv"
    elif str(args.report) == "-":
        report_path = None
    else:
        report_path = args.report

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_fh = report_path.open("w", newline="", encoding="utf-8")
        report_writer = csv.DictWriter(report_fh, fieldnames=REPORT_FIELDS)
        report_writer.writeheader()

    kept = 0
    skipped = 0
    try:
        for article, decision in classify_all(
            articles,
            workers=args.workers,
            min_plant_hits=args.min_plant_hits,
            min_bioeng_hits=args.min_bioeng_hits,
            min_primary_sections=args.min_primary_sections,
        ):
            if report_writer is not None:
                report_writer.writerow(decision.as_row())

            if decision.keep:
                kept += 1
                if not args.dry_run:
                    try:
                        place_article(article, args.output, mode=args.placement)
                    except OSError as exc:
                        log.error("Failed to place %s: %s", article.pmcid, exc)
                log.debug("KEEP %s: %s", article.pmcid, "; ".join(decision.reasons))
            else:
                skipped += 1
                log.debug("SKIP %s: %s", article.pmcid, "; ".join(decision.reasons))
    finally:
        if report_fh is not None:
            report_fh.close()

    log.info(
        "Done. Kept %d / %d (%.2f%%); skipped %d.",
        kept,
        len(articles),
        100.0 * kept / max(1, len(articles)),
        skipped,
    )
    if not args.dry_run:
        log.info("Selected articles are in: %s", args.output.resolve())
    if report_path is not None:
        log.info("Per-article report written to: %s", report_path.resolve())
    return 0

if __name__ == "__main__":
    sys.exit(main())
