# plant_bioeng_filter

Fast, offline filter that scans a local PubMed Central (PMC) text dump and
selects **primary research articles reporting bioengineering work in
plants**. Non-research articles (reviews, perspectives, opinions,
editorials, etc.) and any article that does not report plant
bioengineering are skipped.

The tool is pure Python (standard library only) and runs as a parallel
process pool, so it scales to corpora of hundreds of thousands of
articles.

---

## 1. Expected input layout

Each PMC article is a folder named `PMC<id>.<version>/` containing a
plain-text file with the same stem:

```
./pmc/text/
├── PMC12855588.1/
│   └── PMC12855588.1.txt
├── PMC12855600.2/
│   └── PMC12855600.2.txt
└── ...
```

## 2. Output

Selected articles are placed in `./plant_bioengineering/` (configurable).
By default the script copies **just the `.txt` file** of each selected
article, naming the copy by its PMCID + version so the provenance is
preserved:

```
./plant_bioengineering/
├── PMC12855588.1.txt
├── PMC12855600.2.txt
├── ...
└── _decisions.csv      # per-article report (see below)
```

A **CSV decision report** is written by default to
`<output>/_decisions.csv`. It lists every article and the reason it was
kept or skipped (use `--report <path>` to relocate it, or `--report -` to
disable it). You can also switch to copying the full folder or to
symlinks via `--placement`.

## 3. Installation (in a virtual environment)

```bash
# 1. create and activate a venv
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. install the package
pip install --upgrade pip
pip install .
```

No third-party runtime dependencies are required — the package uses only
the Python standard library.

## 4. Running

After `pip install .` you have two equivalent entry points:

```bash
# console script
plant-bioeng-filter --pmc-root ./pmc/text \
                    --output  ./plant_bioengineering

# or as a module
python -m plant_bioeng_filter --pmc-root ./pmc/text \
                              --output  ./plant_bioengineering
```

Useful flags:

| Flag                       | Default                       | Purpose                                                   |
| -------------------------- | ----------------------------- | --------------------------------------------------------- |
| `--pmc-root`               | `./pmc/text`                  | Where the `PMC*.<v>/` folders live.                       |
| `--output`                 | `./plant_bioengineering`      | Destination for selected articles.                        |
| `--report`                 | `<output>/_decisions.csv`     | CSV with per-article decision; pass `-` to disable.       |
| `--placement`              | `copy-text`                   | `copy-text` / `copy-folder` / `symlink`.                  |
| `--workers`                | `CPU - 1`                     | Number of worker processes.                               |
| `--min-plant-hits`         | `2`                           | Required unique plant-vocabulary hits.                    |
| `--min-bioeng-hits`        | `2`                           | Required unique bioengineering-vocabulary hits.           |
| `--min-primary-sections`   | `2`                           | Required primary-research section headers.                |
| `--limit`                  | _(off)_                       | Process only first N articles (handy for trial runs).     |
| `--dry-run`                | _(off)_                       | Classify but don't copy/link anything to `--output`.      |
| `-v / --verbose`           | _(off)_                       | Log every article's decision.                             |

## 5. How the filter decides

The classifier applies four sequential checks per article. The first
failure wins, which makes the output of `--report` easy to read:

1. **Non-primary article type.** If the header region contains an
   explicit label such as `Review Article`, `Perspective`, `Editorial`,
   `Commentary`, `Case Report`, etc., or the body contains review
   language (`"in this review, we summarize..."`), the article is
   skipped.
2. **Primary-research structure.** The article must contain at least
   two of the canonical section headings: *Materials and Methods*,
   *Methods*, *Results*, *Discussion*, *Conclusions*…
3. **Plant content.** At least two distinct plant-vocabulary hits are
   required (model species, crops, plant anatomy/physiology). If the
   article is dominated by animal/clinical vocabulary and the plant
   signal is weak, it is dropped.
4. **Bioengineering content.** At least two distinct bioengineering
   terms are required (CRISPR, transgenic, *Agrobacterium*-mediated,
   metabolic engineering, etc.).

All vocabularies are defined in `plant_bioeng_filter/rules.py` and are
easy to extend — add a term and rerun.

## 6. Project layout

```
plant_bioeng_filter/
├── pyproject.toml
├── README.md
└── plant_bioeng_filter/
    ├── __init__.py
    ├── __main__.py
    ├── cli.py          # argparse entry point
    ├── classifier.py   # per-article decision logic
    ├── rules.py        # keyword/regex vocabularies
    └── scanner.py      # filesystem walk + parallel dispatch
```

## 7. Programmatic use

```python
from pathlib import Path
from plant_bioeng_filter import iter_articles, classify_all, place_article

articles = list(iter_articles(Path("./pmc/text")))
for article, decision in classify_all(articles, workers=4):
    if decision.keep:
        place_article(article, Path("./plant_bioengineering"), mode="copy-text")
```
