import json, random, collections, csv
from common import *
rel = load_release()
run_rows = list(csv.reader(open(RUN_TABLE), delimiter="\t"))[1:]
acc = [json.loads(l) for l in open(EVIDENCE_LOG)]
acc = [d for d in acc if d["decision"] == "accepted"]
assert len(acc) == len(run_rows)
assert all(a["row"]["pmcid"] == r[8] for a, r in zip(acc, run_rows))
by_p = collections.defaultdict(list)
for a, r in zip(acc, run_rows): by_p[r[8]].append((r, a))
def sim(x, y): return sum(1 for i in (0, 1, 2, 3, 4, 5, 6) if x[i] == y[i])
tier = []; used = set()
for r in rel:
    v = [r[c] if r[c] != "" else "NA" for c in COLS]; best = None; bs = -1
    for k, (rr, a) in enumerate(by_p.get(r["pmcid"], [])):
        if (r["pmcid"], k) in used: continue
        s = sim(v, rr)
        if s > bs: bs, best = s, (k, a)
    if best and bs >= 4:
        used.add((r["pmcid"], best[0])); tier.append(("continuous" if best[1]["reason"] == "strict" else "segment-fallback", best[1]["evidence_quote"]))
    else: tier.append(("unmatched evidence", ""))
c = collections.Counter(t for t, _ in tier)
res = {"records": len(rel), "evidence_tier": dict(c)}
print(json.dumps(res, indent=1)); json.dump(res, open(out("a11_evidence_tier.json"), "w"), indent=1)
write_tsv(out("a11_record_evidence_tier.tsv"), ["row", "pmcid", "evidence_tier"], [[i, r["pmcid"], t] for i, (r, (t, _)) in enumerate(zip(rel, tier))])
random.seed(20261026)
def hg(sp): return sp if sp in ("Arabidopsis thaliana", "Oryza sativa") else "other host"
def per(y): return "<=2018" if (y or 0) <= 2018 else ">=2019"
strata = collections.defaultdict(list)
for i, (r, (t, q)) in enumerate(zip(rel, tier)):
    if t == "unmatched evidence": continue
    strata[(t, hg(r.get("_csp")), per(r.get("_y")))].append(i)
quota = {"continuous": 240, "segment-fallback": 160}
pick = []
for t, q in quota.items():
    keys = [k for k in strata if k[0] == t]; tot = sum(len(strata[k]) for k in keys)
    for k in keys:
        n = max(1, round(q * len(strata[k]) / tot)); pick += [(i, k) for i in random.sample(strata[k], min(n, len(strata[k])))]
fields = ["host_species", "gene_symbols_and_origin", "modification_type", "engineering_type", "construct_promoter", "construct_gene_part", "construct_terminator", "phenotype", "quantitative_values", "mechanism", "doi", "pmcid"]
rec_rows = []
for n, (i, k) in enumerate(sorted(pick, key=lambda x: x[0])):
    r = rel[i]
    rec_rows.append([f"R{n+1:03d}", i, r["pmcid"], r["doi"], k[0], k[1], k[2], r["plant_species"], r["genes"], r["modification_type"], r["engineering_type"], r["gene_construct"], r["phenotype"], r["mechanism"], tier[i][1]])
write_tsv(out("a11_validation_record_sample.tsv"), ["id", "release_row", "pmcid", "doi", "evidence_tier", "host_group", "period", "plant_species", "genes", "modification_type", "engineering_type", "gene_construct", "phenotype", "mechanism", "evidence_quote"], rec_rows)
st = dict(l.rstrip("\n").split("\t") for l in list(open(out("a2_article_status.tsv")))[1:])
gp = [p for p, s in st.items() if s not in ("prefilter_skip", "gate_reject")]; gr = [p for p, s in st.items() if s == "gate_reject"]
art = [("gate passed", p) for p in random.sample(sorted(gp), 100)] + [("gate rejected", p) for p in random.sample(sorted(gr), 100)]
write_tsv(out("a11_validation_gate_sample.tsv"), ["id", "pipeline_decision", "pmcid"], [[f"A{n+1:03d}", d, p] for n, (d, p) in enumerate(art)])
rej = collections.defaultdict(list); seen = collections.Counter()
with open(DECISIONS, newline="") as f:
    rd = csv.reader(f); next(rd)
    for row in rd:
        if row[1] == "yes": continue
        k = re.sub(r"[:(].*", "", row[2]).strip()
        seen[k] += 1
        if len(rej[k]) < 30: rej[k].append(row[0])
        else:
            j = random.randrange(seen[k])
            if j < 30: rej[k][j] = row[0]
scr = []
for k in sorted(rej): scr += [(k, p) for p in sorted(rej[k])]
keep = [l.strip() for l in open(TXT_IDS) if l.strip()]
scr += [("retained by screen", p) for p in random.sample(keep, 90)]
write_tsv(out("a11_validation_screen_sample.tsv"), ["id", "screen_decision", "pmcid_version", "s3_text_key_hint"],
          [[f"S{n+1:03d}", d, p, f"s3://pmc-oa-opendata/{p}/{p}.txt"] for n, (d, p) in enumerate(scr)])
print("records", len(rec_rows), "gate", len(art), "screen", len(scr))
