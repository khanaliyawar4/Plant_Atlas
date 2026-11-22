import argparse
import collections
import csv
import math
import random

from openpyxl import load_workbook

FIELDS = ["score_" + f for f in ["host_species", "gene_symbols", "gene_origin_organism", "modification_type", "engineering_type",
          "construct_promoter", "construct_gene_part", "construct_terminator", "phenotype", "quantitative_values",
          "mechanism", "doi", "pmcid"]]
LABEL_COL = "is_plant_engineering_primary_research"


def sheet_rows(path, sheet):
    ws = load_workbook(path, data_only=True)[sheet]
    it = ws.iter_rows(values_only=True)
    head = next(it)
    return [dict(zip(head, r)) for r in it if r and r[0]]


def wilson(k, n, z=1.96):
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0.0, c - m), min(1.0, c + m)


def kappa(a, b):
    pairs = [(x, y) for x, y in zip(a, b) if x and y]
    n = len(pairs)
    if not n:
        return float("nan"), 0
    po = sum(x == y for x, y in pairs) / n
    ca = collections.Counter(x for x, _ in pairs)
    cb = collections.Counter(y for _, y in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return ((po - pe) / (1 - pe) if pe < 1 else 1.0), n


def fmt(p, lo, hi):
    return "nan" if p != p else f"{p:.3f} ({lo:.3f}-{hi:.3f})"


def records(ref, a, b, release_tsv):
    ra, rb = sheet_rows(a, "Records"), sheet_rows(b, "Records")
    print("RECORD FIELDS (reference: %s)" % ref)
    print("field\tn_scored\tstrict_accuracy (95% CI)\tlenient_accuracy (95% CI)\tkappa_A_vs_B\tn_pairs")
    for f in FIELDS:
        lab = [r.get(f) for r in ref_rows if r.get(f) and r.get(f) != "not applicable"]
        n = len(lab)
        strict = sum(1 for x in lab if x == "correct")
        lenient = sum(1 for x in lab if x in ("correct", "partly correct"))
        k, kn = kappa([r.get(f) for r in ra], [r.get(f) for r in rb])
        print(f"{f}\t{n}\t{fmt(*wilson(strict, n))}\t{fmt(*wilson(lenient, n))}\t{k:.2f}\t{kn}")
    print("\nWHOLE RECORD BY EVIDENCE TIER (no field incorrect; partly correct allowed)")
    for t in sorted({r["evidence_tier"] for r in ref_rows}):
        sub = [r for r in ref_rows if r["evidence_tier"] == t]
        scored = [r for r in sub if any(r.get(f) for f in FIELDS)]
        k = sum(1 for r in scored if not any(r.get(f) == "incorrect" for f in FIELDS))
        print(f"{t}\tn_scored={len(scored)}\t{fmt(*wilson(k, len(scored)))}")
    if release_tsv:
        per_article = collections.Counter(r["pmcid"] for r in csv.DictReader(open(release_tsv, encoding="utf-8"), delimiter="\t"))
        missed = {}
        for r in ref_rows:
            v = str(r.get("missed_constructs") or "").strip()
            if v.isdigit():
                missed[r["pmcid"]] = max(missed.get(r["pmcid"], 0), int(v))
        found = sum(per_article[p] for p in missed)
        miss = sum(missed.values())
        print(f"\nRECORD RECALL over {len(missed)} sampled articles with a missed-construct count: "
              f"{found} released records, {miss} missed constructs -> recall {fmt(*wilson(found, found + miss))}")


def decisions(ref, a, b, sheet, strata_tsv, boot, seed):
    sizes = {}; positive = set()
    for r in csv.DictReader(open(strata_tsv, encoding="utf-8"), delimiter="\t"):
        if r["sheet"] == sheet:
            sizes[r["stratum"]] = int(r["population_size"])
            if r["predicted_positive"] == "yes":
                positive.add(r["stratum"])
    key = "pipeline_decision" if sheet == "Gate" else "screen_decision"
    rr = sheet_rows(ref, sheet)
    k, kn = kappa([x.get(LABEL_COL) for x in sheet_rows(a, sheet)], [x.get(LABEL_COL) for x in sheet_rows(b, sheet)])
    by = collections.defaultdict(list)
    unclear = 0
    for x in rr:
        lab = x.get(LABEL_COL)
        if lab == "unclear":
            unclear += 1
            continue
        if lab in ("yes", "no"):
            by[x[key]].append(1 if lab == "yes" else 0)

    def estimate(groups):
        tp = sum(sizes[s] * (sum(v) / len(v)) for s, v in groups.items() if s in positive and v)
        fp = sum(sizes[s] * (1 - sum(v) / len(v)) for s, v in groups.items() if s in positive and v)
        fn = sum(sizes[s] * (sum(v) / len(v)) for s, v in groups.items() if s not in positive and v)
        pr = tp / (tp + fp) if tp + fp else float("nan")
        rc = tp / (tp + fn) if tp + fn else float("nan")
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else float("nan")
        return pr, rc, f1

    point = estimate(by)
    rng = random.Random(seed)
    sims = []
    for _ in range(boot):
        res = {s: [rng.choice(v) for _ in v] for s, v in by.items() if v}
        sims.append(estimate(res))

    def ci(i):
        vals = sorted(x[i] for x in sims if x[i] == x[i])
        if not vals:
            return float("nan"), float("nan")
        return vals[int(0.025 * (len(vals) - 1))], vals[int(0.975 * (len(vals) - 1))]

    print(f"\n{sheet.upper()} (stratum-weighted; n labelled = {sum(len(v) for v in by.values())}, unclear = {unclear}; kappa A vs B = {k:.2f}, n = {kn})")
    for s in sorted(by):
        v = by[s]
        print(f"  {s}\tn={len(v)}\tshare judged plant-engineering primary research={sum(v) / len(v):.3f}\tpopulation={sizes.get(s, 'missing')}")
    for i, name in enumerate(("precision", "recall", "F1")):
        lo, hi = ci(i)
        print(f"  {name}\t{point[i]:.3f} (bootstrap 95% CI {lo:.3f}-{hi:.3f})")


ap = argparse.ArgumentParser()
ap.add_argument("annotator_a")
ap.add_argument("annotator_b")
ap.add_argument("--reference", required=True)
ap.add_argument("--strata", default="strata_sizes.tsv")
ap.add_argument("--release-records", default="")
ap.add_argument("--bootstrap", type=int, default=2000)
ap.add_argument("--seed", type=int, default=20261026)
args = ap.parse_args()
ref_rows = sheet_rows(args.reference, "Records")
records(args.reference, args.annotator_a, args.annotator_b, args.release_records)
for sh in ("Gate", "Screen"):
    decisions(args.reference, args.annotator_a, args.annotator_b, sh, args.strata, args.bootstrap, args.seed)
