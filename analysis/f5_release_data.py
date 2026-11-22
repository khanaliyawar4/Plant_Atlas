import json, csv, hashlib, collections
from common import *
G = DATA_DIR; os.makedirs(G, exist_ok=True)
rel = load_release(); meta = json.load(open(out("release_META.json")))
tier = {int(r[0]): r[2] for r in list(csv.reader(open(out("a11_record_evidence_tier.tsv")), delimiter="\t"))[1:]}
lic = dict(list(csv.reader(open(out("a13_article_licenses.tsv")), delimiter="\t"))[1:])
X = json.load(open(out("a3_xml_metadata.json")))
ctry = {r[0]: r[1] for r in list(csv.reader(open(out("a8_country_by_paper.tsv")), delimiter="\t"))[1:]}
run_rows = list(csv.reader(open(RUN_TABLE), delimiter="\t"))[1:]
acc = [d for d in map(json.loads, open(EVIDENCE_LOG)) if d["decision"] == "accepted"]
by_p = collections.defaultdict(list)
for a, r in zip(acc, run_rows): by_p[r[8]].append((r, a))
used = set(); quote = {}
for i, r in enumerate(rel):
    v = [r[c] if r[c] != "" else "NA" for c in COLS]; best = None; bs = -1
    for k, (rr, a) in enumerate(by_p.get(r["pmcid"], [])):
        if (r["pmcid"], k) in used: continue
        s = sum(1 for j in range(7) if v[j] == rr[j])
        if s > bs: bs, best = s, (k, a)
    if best and bs >= 4: used.add((r["pmcid"], best[0])); quote[i] = best[1]["evidence_quote"]
AGRO = ["drought","salt","cold","heat","disease","pest","herbicide","yield","flowering","pigment","oilseed","nutrient","photo","repro","growth","root","germination","senescence","tool","farming"]
hdr = ["record_id"] + COLS + ["publication_year", "host_canonical", "lead_gene_symbol", "modification_group", "trait_classes", "TO_terms_direct", "TO_terms_inferred", "PO_terms", "plaza5_orthogroup", "planttfdb_family", "gene_family", "effect_direction"]
rows = []
for i, r in enumerate(rel):
    rows.append([f"PBA1.1-{i+1:05d}"] + [r[c] if r[c] != "" else "NA" for c in COLS] + [r.get("_y") or "", r.get("_csp") or "", r.get("_g") or "", mod_group(r["modification_type"]),
                 ";".join(t for t in r.get("_t", []) if t in AGRO), ";".join(r.get("_to", [])), ";".join(r.get("_toa", [])), ";".join(r.get("_po", [])),
                 r.get("_og") or "", r.get("_tf") or "", r.get("_fam") or "", r.get("_eff") or ""])
write_tsv(os.path.join(G, "PBA_v1.1_records.tsv"), hdr, rows)
OPEN = {"CC BY", "CC0"}
q = [[f"PBA1.1-{i+1:05d}", rel[i]["pmcid"], tier[i], lic[rel[i]["pmcid"]], (quote[i] if lic[rel[i]["pmcid"]] in OPEN else "WITHHELD (article license; retrieve from the PMCID)")] for i in sorted(quote)]
write_tsv(os.path.join(G, "PBA_v1.1_evidence_quotes.tsv"), ["record_id", "pmcid", "evidence_check", "article_license", "evidence_quote"], q)
JATS_NOTE = {"correction-forward": "correction", "expression-of-concern": "expression of concern", "retraction-forward": "retraction", "addended-article": "addendum"}
CR_NOTE = {"correction": "correction", "erratum": "erratum", "expression_of_concern": "expression of concern", "addendum": "addendum", "retraction": "retraction", "withdrawal": "withdrawal", "removal": "removal", "partial_retraction": "partial retraction"}
notes = collections.defaultdict(set)
for p, d in X.items():
    for t in d.get("related") or []:
        if t in JATS_NOTE: notes[p].add(JATS_NOTE[t])
for r in csv.DictReader(open(out("a14_retraction_check.tsv"), encoding="utf-8"), delimiter="\t"):
    for t in filter(None, r["crossref_update_types"].split(";")):
        if t in CR_NOTE: notes[r["pmcid"]].add(CR_NOTE[t])
    for h in filter(None, r["retraction_watch"].split(" | ")):
        notes[r["pmcid"]].add(h.split(" (")[0].lower())
n = collections.Counter(r["pmcid"] for r in rel); yr = {}
for r in rel: yr.setdefault(r["pmcid"], r.get("_y"))
write_tsv(os.path.join(G, "PBA_v1.1_articles.tsv"), ["pmcid", "version_used", "doi_jats", "publication_year", "article_type", "license", "first_author_country", "records", "post_publication_notices"],
          [[p, X[p]["v"], X[p].get("doi") or "NA", yr[p] or "", X[p]["article_type"], lic[p], ctry.get(p, ""), n[p], "; ".join(sorted(notes.get(p, ())))] for p in sorted(n)])
print("articles with notices", sum(1 for p in n if notes.get(p)), collections.Counter(x for p in n for x in notes.get(p, ())))
sha = {f: hashlib.sha256(open(os.path.join(G, f), "rb").read()).hexdigest() for f in ("PBA_v1.1_records.tsv", "PBA_v1.1_evidence_quotes.tsv", "PBA_v1.1_articles.tsv")}
with open(os.path.join(G, "RELEASE.md"), "w") as fo:
    fo.write(f"""# Plant Bioengineering Atlas - data release v1.1

| | |
|---|---|
| Source snapshot | PMC OA Subset, accessed 29 May 2026 |

Files
- `PBA_v1.1_records.tsv` - one row per extracted record: the nine extracted fields plus derived annotations.
- `PBA_v1.1_evidence_quotes.tsv` - available supporting quotations for release records. Quotations are reproduced for CC BY and CC0 articles; for other licenses only the record/PMCID link is given.
- `PBA_v1.1_articles.tsv` - per-article metadata: version used, DOI from JATS, year, article type, license, first-author country and post-publication notices (correction, erratum, addendum, expression of concern or retraction) from the JATS front matter, Crossref and Retraction Watch, checked 27 October 2026.

"NA" = not stated in the article body or not extracted.

SHA-256
""" + "".join(f"- `{k}` {v}\n" for k, v in sha.items()) + "\nLicense: data CC BY 4.0 (quotations remain under their article licenses); code MIT.\n")
print(len(rows), len(q), sum(1 for x in q if not x[4].startswith("WITHHELD")))
