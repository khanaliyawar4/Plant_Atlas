import json, collections, re
from common import *
rel = load_release()
classify = mod_group
AGRO = ["drought","salt","cold","heat","disease","pest","herbicide","yield","flowering","pigment","oilseed","nutrient","photo","repro","growth","root","germination","senescence"]
NR = len(rel); NA = len({r["pmcid"] for r in rel})
def shares(keyf, label):
    rc = collections.Counter(); ac = collections.defaultdict(set)
    for r in rel:
        for k in keyf(r): rc[k] += 1; ac[k].add(r["pmcid"])
    rows = []
    for k, n in rc.most_common():
        rows.append([label, k, n, f"{100*n/NR:.1f}", len(ac[k]), f"{100*len(ac[k])/NA:.1f}"])
    return rows
rows = []
rows += shares(lambda r: [classify(r["modification_type"] or "")], "modification class")
rows += shares(lambda r: [t for t in r.get("_t", []) if t in AGRO], "trait class")
def hosts_named(r):  # every host named in the record, as in Figure 1B; Populus species form one genus-level group
    out = []
    for s in r.get("_cs") or []:
        s = "Populus" if s.startswith("Populus") else s
        if s not in out: out.append(s)
    return out
rows += shares(hosts_named, "host species")[:15]
rows += shares(lambda r: [r["_tf"]] if r.get("_tf") else [], "TF family")[:10]
write_tsv(out("a9_record_vs_article_shares.tsv"), ["dimension", "category", "records", "% of 14,358 records", "articles", "% of 6,452 articles"], rows)
def rank(v):
    o = sorted(range(len(v)), key=lambda i: -v[i]); r = [0]*len(v); i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and v[o[j+1]] == v[o[i]]: j += 1
        for k in range(i, j+1): r[o[k]] = (i + j) / 2
        i = j + 1
    return r
def spearman(a, b):
    ra, rb = rank(a), rank(b); n = len(a); ma = sum(ra)/n; mb = sum(rb)/n
    cov = sum((x-ma)*(y-mb) for x, y in zip(ra, rb)); va = sum((x-ma)**2 for x in ra); vb = sum((y-mb)**2 for y in rb)
    return cov / (va*vb) ** 0.5
res = {}
for dim in ("modification class", "trait class", "host species", "TF family"):
    rr = [x for x in rows if x[0] == dim]; res[f"spearman_record_vs_article_{dim}"] = round(spearman([x[2] for x in rr], [x[4] for x in rr]), 3)
er = collections.Counter(); ea = collections.defaultdict(set)
for r in rel:
    g = r.get("_g")
    if not g: continue
    for t in r.get("_t", []):
        if t in AGRO: er[(g, t)] += 1; ea[(g, t)].add(r["pmcid"])
w_r = [er[e] for e in er]; w_a = [len(ea[e]) for e in er]
res["gene_trait_edges"] = len(er)
res["edges_where_record_weight_exceeds_article_weight"] = sum(1 for a, b in zip(w_r, w_a) if a > b)
res["edges_supported_by_>=2_records_but_1_article"] = sum(1 for a, b in zip(w_r, w_a) if a >= 2 and b == 1)
res["edges_supported_by_>=2_articles"] = sum(1 for b in w_a if b >= 2)
res["spearman_edge_record_vs_article_weight"] = round(spearman(w_r, w_a), 3)
print(json.dumps(res, indent=1)); json.dump(res, open(out("a9_sensitivity_summary.json"), "w"), indent=1)
for x in rows[:9]: print(x)
