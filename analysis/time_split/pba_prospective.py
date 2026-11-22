"""Time-split test of hypothesis generation from the Plant Bioengineering Atlas graph.

Two stages, run as separate jobs:

  predict   builds the graph from records published up to a cutoff year, scores every
            candidate link with pre-specified rules and baselines, and writes the
            rankings together with a manifest of SHA-256 hashes. Records published after
            the cutoff are discarded while the file is read and are never used.
  evaluate  verifies the manifest, then reads the later records and measures how many
            of the ranked candidates were reported for the first time after the cutoff.

Task A, cross-species transfer: gene family F reported for trait class T in at least one
host by the cutoff; candidate = (F, T, H) for an eligible host H in which F was not yet
reported for T.
Task B, gene-trait association: PLAZA 5.0 orthogroup O reported by the cutoff; candidate =
(O, T) for an agronomic trait class T not yet reported for O.

Parameters are defined in CONFIG.
"""
import argparse
import csv
import datetime
import hashlib
import json
import math
import os
import random
import sys
from collections import defaultdict

import numpy as np

CONFIG = {
    "agronomic_traits": ["drought", "salt", "cold", "heat", "disease", "pest", "herbicide", "yield", "flowering",
                         "pigment", "oilseed", "nutrient", "photo", "repro", "growth", "root", "germination",
                         "senescence"],
    "min_host_articles": 10,      # Task A: a host is eligible if it has >= this many articles by the cutoff
    "inner_window": 5,            # learned scores: features from <= cutoff-5, labels from (cutoff-5, cutoff]
    "l2": 1.0,                    # ridge penalty of the logistic regressions (standardised features)
    "k_values": [20, 50, 100, 200],
    "bootstrap": 1000,
    "seed": 20261109,
    "last_year": 2026,
}

TASK_A_FEATURES = ["hosts_FT", "articles_FT", "articles_F", "articles_HT", "articles_H", "articles_FH", "families_HT"]
TASK_A_POPULARITY = ["articles_F", "articles_HT", "articles_H"]
TASK_B_FEATURES = ["cooc_max", "cooc_sum", "family_share", "articles_O", "articles_T", "traits_O"]
TASK_B_POPULARITY = ["articles_O", "articles_T", "traits_O"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def clean(x):
    x = (x or "").strip()
    return "" if x.upper() in ("", "NA", "NONE") else x


def load(path, max_year=None, min_year=None):
    """Read records; rows outside [min_year, max_year] are dropped as the file is read."""
    ag = set(CONFIG["agronomic_traits"])
    rows, seen_max = [], 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            y = int(r["publication_year"])
            if (max_year is not None and y > max_year) or (min_year is not None and y < min_year):
                continue
            seen_max = max(seen_max, y)
            traits = sorted({t for t in (r["trait_classes"] or "").split(";") if t in ag})
            rows.append({
                "record_id": r["record_id"], "pmcid": r["pmcid"], "year": y, "host": clean(r["host_canonical"]),
                "family": clean(r["gene_family"]).upper(), "orthogroup": clean(r["plaza5_orthogroup"]),
                "traits": traits,
            })
    return rows, seen_max


# ---------------------------------------------------------------- Task A: cross-species transfer
def index_a(rows):
    I = {k: defaultdict(set) for k in ("FTH", "FT_hosts", "FT", "F", "HT", "H", "FH", "HT_fams")}
    for r in rows:
        F, H = r["family"], r["host"]
        if H:
            I["H"][H].add(r["pmcid"])
        for T in r["traits"]:
            if H:
                I["HT"][(H, T)].add(r["pmcid"])
        if not F or not H:
            continue
        I["F"][F].add(r["pmcid"])
        I["FH"][(F, H)].add(r["pmcid"])
        for T in r["traits"]:
            I["FTH"][(F, T, H)].add(r["pmcid"])
            I["FT_hosts"][(F, T)].add(H)
            I["FT"][(F, T)].add(r["pmcid"])
            I["HT_fams"][(H, T)].add(F)
    return I


def candidates_a(I):
    hosts = sorted(h for h, a in I["H"].items() if len(a) >= CONFIG["min_host_articles"])
    out = []
    for (F, T) in sorted(I["FT_hosts"]):
        for H in hosts:
            if (F, T, H) in I["FTH"]:
                continue
            out.append({"key": f"{F}|{T}|{H}", "cluster": F, "F": F, "T": T, "H": H,
                        "hosts_FT": len(I["FT_hosts"][(F, T)]), "articles_FT": len(I["FT"][(F, T)]),
                        "articles_F": len(I["F"][F]), "articles_HT": len(I["HT"].get((H, T), ())),
                        "articles_H": len(I["H"][H]), "articles_FH": len(I["FH"].get((F, H), ())),
                        "families_HT": len(I["HT_fams"].get((H, T), ()))})
    return out


def positives_a(rows):
    pos = defaultdict(set)
    for r in rows:
        if r["family"] and r["host"]:
            for T in r["traits"]:
                pos[f"{r['family']}|{T}|{r['host']}"].add(r["pmcid"])
    return pos


# ---------------------------------------------------------------- Task B: gene-trait association
def index_b(rows):
    traits_O, art_O, art_T, fam_O = defaultdict(set), defaultdict(set), defaultdict(set), defaultdict(lambda: defaultdict(int))
    for r in rows:
        for T in r["traits"]:
            art_T[T].add(r["pmcid"])
        O = r["orthogroup"]
        if not O:
            continue
        art_O[O].add(r["pmcid"])
        traits_O[O].update(r["traits"])
        if r["family"]:
            fam_O[O][r["family"]] += 1
    fam = {O: max(c.items(), key=lambda kv: (kv[1], kv[0]))[0] for O, c in fam_O.items()}
    n_T = defaultdict(int)
    co = defaultdict(int)
    for O, ts in traits_O.items():
        for a in ts:
            n_T[a] += 1
            for b in ts:
                if a != b:
                    co[(a, b)] += 1
    fam_members = defaultdict(set)
    for O, f in fam.items():
        fam_members[f].add(O)
    return {"traits_O": traits_O, "art_O": art_O, "art_T": art_T, "fam": fam, "n_T": n_T, "co": co,
            "fam_members": fam_members}


def candidates_b(I):
    out = []
    for O in sorted(I["art_O"]):
        have = I["traits_O"][O]
        f = I["fam"].get(O)
        others = (I["fam_members"][f] - {O}) if f else set()
        for T in CONFIG["agronomic_traits"]:
            if T in have:
                continue
            cond = [I["co"].get((a, T), 0) / I["n_T"][a] for a in have if I["n_T"][a]]
            share = (sum(1 for o in others if T in I["traits_O"][o]) / len(others)) if others else 0.0
            out.append({"key": f"{O}|{T}", "cluster": O, "O": O, "T": T, "family": f or "",
                        "cooc_max": max(cond) if cond else 0.0, "cooc_sum": sum(cond), "family_share": share,
                        "articles_O": len(I["art_O"][O]), "articles_T": len(I["art_T"].get(T, ())),
                        "traits_O": len(have)})
    return out


def positives_b(rows):
    pos = defaultdict(set)
    for r in rows:
        if r["orthogroup"]:
            for T in r["traits"]:
                pos[f"{r['orthogroup']}|{T}"].add(r["pmcid"])
    return pos


TASKS = {
    "A_transfer": {"index": index_a, "cand": candidates_a, "pos": positives_a,
                   "features": TASK_A_FEATURES, "popularity": TASK_A_POPULARITY},
    "B_gene_trait": {"index": index_b, "cand": candidates_b, "pos": positives_b,
                     "features": TASK_B_FEATURES, "popularity": TASK_B_POPULARITY},
}


# ---------------------------------------------------------------- scoring
def design(cands, feats):
    X = np.array([[c[f] for f in feats] for c in cands], dtype=float)
    for j, f in enumerate(feats):
        if f.startswith(("articles", "hosts", "families", "traits")):
            X[:, j] = np.log1p(X[:, j])
    return X


def fit_logistic(X, y, l2):
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    P = np.eye(Z.shape[1]) * l2
    P[0, 0] = 0.0
    for _ in range(100):
        p = 1 / (1 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) + P @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + P
        step = np.linalg.solve(H, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return {"mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist()}


def apply_logistic(m, X):
    Z = np.hstack([np.ones((len(X), 1)), (X - np.array(m["mu"])) / np.array(m["sd"])])
    return Z @ np.array(m["w"])


def tiebreak(key):
    return int(hashlib.sha256((str(CONFIG["seed"]) + key).encode()).hexdigest()[:12], 16) / 16 ** 12


def score(task, cands, inner_model, inner_pop_model):
    T = TASKS[task]
    X = design(cands, T["features"])
    Xp = design(cands, T["popularity"])
    learned = apply_logistic(inner_model, X)
    learned_pop = apply_logistic(inner_pop_model, Xp)
    for i, c in enumerate(cands):
        tb = tiebreak(c["key"]) * 1e-9
        if task == "A_transfer":
            c["s_graph_rule"] = c["hosts_FT"] + 1e-3 * math.log1p(c["articles_FT"]) + 1e-6 * math.log1p(c["articles_HT"]) + tb
            c["s_popularity"] = math.log1p(c["articles_F"]) + math.log1p(c["articles_HT"]) + tb
        else:
            c["s_graph_rule"] = c["cooc_max"] + 1e-3 * c["family_share"] + tb
            c["s_popularity"] = math.log1p(c["articles_O"]) + math.log1p(c["articles_T"]) + tb
        c["s_graph_learned"] = float(learned[i]) + tb
        c["s_popularity_learned"] = float(learned_pop[i]) + tb
        c["s_random"] = tiebreak("random" + c["key"])
    return cands


METHODS = ["s_graph_rule", "s_graph_learned", "s_popularity", "s_popularity_learned", "s_random"]


def build(task, rows_upto, cutoff):
    """Candidates and scores using only rows published <= cutoff."""
    T = TASKS[task]
    w = CONFIG["inner_window"]
    inner_rows = [r for r in rows_upto if r["year"] <= cutoff - w]
    inner_c = T["cand"](T["index"](inner_rows))
    inner_pos = T["pos"]([r for r in rows_upto if cutoff - w < r["year"] <= cutoff])
    y = np.array([1.0 if c["key"] in inner_pos else 0.0 for c in inner_c])
    m = fit_logistic(design(inner_c, T["features"]), y, CONFIG["l2"])
    mp = fit_logistic(design(inner_c, T["popularity"]), y, CONFIG["l2"])
    cands = score(task, T["cand"](T["index"](rows_upto)), m, mp)
    info = {"inner_candidates": len(inner_c), "inner_positives": int(y.sum()),
            "learned_weights": dict(zip(["intercept"] + T["features"], m["w"])),
            "popularity_weights": dict(zip(["intercept"] + T["popularity"], mp["w"]))}
    return cands, info


def write_rankings(path, cands):
    cols = list(cands[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(cands)


def read_rankings(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for r in rows:
        for m in METHODS:
            r[m] = float(r[m])
    return rows


# ---------------------------------------------------------------- metrics
def auroc(s, y):
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s))
    ss = s[order]
    i = 0
    while i < len(ss):
        j = i
        while j + 1 < len(ss) and ss[j + 1] == ss[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    npos = y.sum()
    nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    return float((ranks[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def avg_precision(s, y):
    o = np.argsort(-s, kind="mergesort")
    yy = y[o]
    if yy.sum() == 0:
        return float("nan")
    hits = np.cumsum(yy)
    return float((hits[yy == 1] / (np.nonzero(yy == 1)[0] + 1)).sum() / yy.sum())


def at_k(s, y, k):
    o = np.argsort(-s, kind="mergesort")[:k]
    tp = y[o].sum()
    return float(tp / k), float(tp / y.sum()) if y.sum() else float("nan"), int(tp)


def metrics(s, y):
    out = {"AUROC": auroc(s, y), "AUPRC": avg_precision(s, y)}
    for k in CONFIG["k_values"]:
        p, r, tp = at_k(s, y, k)
        out[f"P@{k}"], out[f"R@{k}"], out[f"hits@{k}"] = p, r, tp
    return out


def bootstrap(cands, y, clusters, rng):
    """Cluster bootstrap (resampling gene families or orthogroups); returns CI per method and paired differences."""
    by = defaultdict(list)
    for i, c in enumerate(clusters):
        by[c].append(i)
    keys = sorted(by)
    S = {m: np.array([c[m] for c in cands]) for m in METHODS}
    stats = defaultdict(list)
    pairs = [("s_graph_learned", "s_popularity_learned"), ("s_graph_rule", "s_popularity"),
             ("s_graph_learned", "s_random"), ("s_graph_rule", "s_random")]
    for _ in range(CONFIG["bootstrap"]):
        pick = rng.choice(len(keys), len(keys), replace=True)
        idx = np.concatenate([by[keys[p]] for p in pick])
        yb = y[idx]
        if yb.sum() == 0:
            continue
        val = {}
        for m in METHODS:
            sb = S[m][idx]
            val[m] = (auroc(sb, yb), avg_precision(sb, yb), at_k(sb, yb, 50)[0])
            stats[(m, "AUROC")].append(val[m][0])
            stats[(m, "AUPRC")].append(val[m][1])
            stats[(m, "P@50")].append(val[m][2])
        for a, b in pairs:
            stats[(f"{a}-{b}", "AUROC")].append(val[a][0] - val[b][0])
            stats[(f"{a}-{b}", "AUPRC")].append(val[a][1] - val[b][1])
    return {f"{k[0]}|{k[1]}": [float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5))] for k, v in stats.items()}


# ---------------------------------------------------------------- stages
def stage_predict(a):
    script = os.path.abspath(__file__)
    os.makedirs(a.out, exist_ok=True)
    rows, seen = load(a.data, max_year=a.cutoff)
    assert seen <= a.cutoff, "a record after the cutoff was loaded"
    man = {"stage": "predict", "cutoff": a.cutoff,
           "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "script_sha256": sha256(script), "data_sha256": sha256(a.data), "records_loaded": len(rows),
           "max_year_loaded": seen, "config": CONFIG, "tasks": {}}
    for task in TASKS:
        cands, info = build(task, rows, a.cutoff)
        p = os.path.join(a.out, f"rankings_{task}.tsv")
        write_rankings(p, cands)
        info.update({"candidates": len(cands), "rankings_file": os.path.basename(p), "rankings_sha256": sha256(p)})
        man["tasks"][task] = info
        print(task, "candidates", len(cands), "inner positives", info["inner_positives"], flush=True)
    json.dump(man, open(os.path.join(a.out, "manifest_predict.json"), "w"), indent=1)
    print("frozen", a.out)


def stage_evaluate(a):
    man = json.load(open(os.path.join(a.out, "manifest_predict.json")))
    assert sha256(os.path.abspath(__file__)) == man["script_sha256"], "analysis code changed; regenerate predictions"
    for task, info in man["tasks"].items():
        got = sha256(os.path.join(a.out, info["rankings_file"]))
        assert got == info["rankings_sha256"], f"rankings changed after freezing: {task}"
    assert sha256(a.data) == man["data_sha256"], "data file differs from the one used for predictions"
    cutoff = man["cutoff"]
    later, _ = load(a.data, min_year=cutoff + 1)
    test = later
    rng = np.random.default_rng(CONFIG["seed"])
    res = {"stage": "evaluate", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "script_sha256": sha256(os.path.abspath(__file__)), "predict_manifest": man, "test_years":
           [min(r["year"] for r in test), max(r["year"] for r in test)], "test_records": len(test), "tasks": {}}
    for task, info in man["tasks"].items():
        T = TASKS[task]
        cands = read_rankings(os.path.join(a.out, info["rankings_file"]))
        pos = T["pos"](test)
        keep = cands
        cand_keys = {c["key"] for c in cands}
        all_new = set(pos)
        # new events in the test window that were not candidates (outside the graph at the cutoff)
        rows_cut, _ = load(a.data, max_year=cutoff)
        known = set(T["pos"](rows_cut))
        new_events = {k for k in all_new if k not in known}
        out = {"candidates": len(keep),
               "new_events_in_test": len(new_events), "new_events_that_were_candidates": len(new_events & cand_keys)}
        for label, minart in (("primary_>=1_article", 1), ("sensitivity_>=2_articles", 2)):
            y = np.array([1.0 if len(pos.get(c["key"], ())) >= minart else 0.0 for c in keep])
            out[label] = {"positives": int(y.sum()), "prevalence": float(y.mean()),
                          "methods": {m: metrics(np.array([c[m] for c in keep]), y) for m in METHODS}}
            if minart == 1:
                out[label]["bootstrap_95ci"] = bootstrap(keep, y, [c["cluster"] for c in keep], rng)
                top = sorted(keep, key=lambda c: -c["s_graph_learned"])[:50]
                out[label]["top50_graph_learned"] = [
                    {"rank": i + 1, "key": c["key"], "confirmed": bool(len(pos.get(c["key"], ()))),
                     "confirming_pmcids": sorted(pos.get(c["key"], ()))[:5]} for i, c in enumerate(top)]
        res["tasks"][task] = out
        print(task, json.dumps({k: v for k, v in out.items() if not isinstance(v, dict)}), flush=True)
        for label in ("primary_>=1_article", "sensitivity_>=2_articles"):
            for m, v in out[label]["methods"].items():
                print(f"  {label:26s} {m:22s} AUROC {v['AUROC']:.3f} AUPRC {v['AUPRC']:.4f} P@50 {v['P@50']:.2f} hits@100 {v['hits@100']}")
    json.dump(res, open(os.path.join(a.out, "evaluation.json"), "w"), indent=1)


def stage_forward(a):
    """Rank untested candidates on the full release (prospective list for future checking)."""
    os.makedirs(a.out, exist_ok=True)
    rows, seen = load(a.data)
    man = {"stage": "forward", "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
           "script_sha256": sha256(os.path.abspath(__file__)), "data_sha256": sha256(a.data),
           "max_year_loaded": seen, "config": CONFIG, "tasks": {}}
    for task in TASKS:
        cands, info = build(task, rows, CONFIG["last_year"])
        T = TASKS[task]
        support = T["pos"](rows)
        top = sorted(cands, key=lambda c: -c["s_graph_learned"])[: a.top]
        p = os.path.join(a.out, f"forward_{task}_top{a.top}.tsv")
        with open(p, "w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            if task == "A_transfer":
                w.writerow(["rank", "gene_family", "trait_class", "candidate_host", "hosts_with_evidence", "articles_family_trait",
                            "articles_family_in_candidate_host", "articles_candidate_host_trait", "learned_score", "supporting_pmcids"])
                for i, c in enumerate(top):
                    sup = sorted({x for k, v in support.items() if k.startswith(f"{c['F']}|{c['T']}|") for x in v})
                    w.writerow([i + 1, c["F"], c["T"], c["H"], c["hosts_FT"], c["articles_FT"], c["articles_FH"],
                                c["articles_HT"], round(c["s_graph_learned"], 4), ";".join(sup[:10])])
            else:
                w.writerow(["rank", "orthogroup", "trait_class", "gene_family", "traits_already_reported", "articles_orthogroup",
                            "cooccurrence_max", "family_share", "learned_score", "supporting_pmcids"])
                for i, c in enumerate(top):
                    sup = sorted({x for k, v in support.items() if k.startswith(c["O"] + "|") for x in v})
                    w.writerow([i + 1, c["O"], c["T"], c["family"], c["traits_O"], c["articles_O"], round(c["cooc_max"], 4),
                                round(c["family_share"], 4), round(c["s_graph_learned"], 4), ";".join(sup[:10])])
        info.update({"candidates": len(cands), "file": os.path.basename(p), "sha256": sha256(p)})
        man["tasks"][task] = info
        print(task, "forward candidates", len(cands), flush=True)
    json.dump(man, open(os.path.join(a.out, "manifest_forward.json"), "w"), indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["predict", "evaluate", "forward"])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cutoff", type=int, default=2022)
    ap.add_argument("--top", type=int, default=50)
    a = ap.parse_args()
    {"predict": stage_predict, "evaluate": stage_evaluate, "forward": stage_forward}[a.stage](a)
