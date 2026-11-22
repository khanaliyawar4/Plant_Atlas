import csv, json, os, sys, time, collections, urllib.request, urllib.parse, urllib.error
import concurrent.futures as cf

ARTICLES = sys.argv[1]
WORK = sys.argv[2]
os.makedirs(WORK, exist_ok=True)
RW_URL = "https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv"
IDCONV = "https://pmc.ncbi.nlm.nih.gov/tools/idconv/api/v1/articles/?format=json&tool=pba_retraction_check&ids="

def fetch_json(url):
    for k in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pba-retraction-check/1.0"})
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 + 3 * k)
        except Exception:
            time.sleep(2 + 3 * k)
    raise RuntimeError(url)

arts = list(csv.DictReader(open(ARTICLES, encoding="utf-8"), delimiter="\t"))

ic_path = os.path.join(WORK, "idconv.json")
if os.path.exists(ic_path):
    ic = json.load(open(ic_path))
else:
    ic = {}
    ids = [a["pmcid"] for a in arts]
    for i in range(0, len(ids), 200):
        j = fetch_json(IDCONV + ",".join(ids[i:i + 200])) or {}
        for r in j.get("records", []):
            ic[r.get("pmcid")] = (r.get("pmid", ""), r.get("doi", ""))
        time.sleep(0.4)
    json.dump(ic, open(ic_path, "w"))

rw_path = os.path.join(WORK, "retraction_watch.csv")
if not os.path.exists(rw_path):
    urllib.request.urlretrieve(RW_URL, rw_path)
rw = list(csv.DictReader(open(rw_path, encoding="utf-8", errors="replace")))

doi_of = {}
for a in arts:
    d = (a["doi_jats"] or "").strip()
    if d.upper() in ("", "NA"):
        d = ic.get(a["pmcid"], ("", ""))[1] or ""
    doi_of[a["pmcid"]] = d
by_doi = {d.lower(): p for p, d in doi_of.items() if d}
by_pmid = {v[0]: k for k, v in ic.items() if v[0]}
rw_hits = collections.defaultdict(list)
for r in rw:
    d = (r["OriginalPaperDOI"] or "").strip().lower()
    p = (r["OriginalPaperPubMedID"] or "").strip()
    k = by_doi.get(d) or by_pmid.get(p)
    if k:
        rw_hits[k].append(f'{r["RetractionNature"]} ({r["RetractionDate"].split()[0]}; RW {r["Record ID"]})')

cr_path = os.path.join(WORK, "cr.jsonl")
done = {}
if os.path.exists(cr_path):
    for line in open(cr_path):
        j = json.loads(line)
        done[j["pmcid"]] = j

def crossref(item):
    p, d = item
    m = fetch_json("https://api.crossref.org/works/" + urllib.parse.quote(d, safe="/"))
    if m is None:
        return {"pmcid": p, "doi": d, "status": 404, "updated_by": []}
    return {"pmcid": p, "doi": d, "status": 200, "updated_by": m["message"].get("updated-by", [])}

done = {p: r for p, r in done.items() if r["doi"] == doi_of.get(p)}
todo = [(p, d) for p, d in doi_of.items() if d and p not in done]
with open(cr_path, "a") as f, cf.ThreadPoolExecutor(6) as ex:
    for r in ex.map(crossref, todo):
        done[r["pmcid"]] = r
        f.write(json.dumps(r) + "\n")

RETRACT = {"retraction", "withdrawal", "removal", "partial_retraction"}
rows = []
counts = collections.Counter()
for a in arts:
    p = a["pmcid"]
    cr = done.get(p) if doi_of[p] else None
    cr = cr or {"status": "no DOI", "updated_by": []}
    types = sorted({u["type"] for u in cr["updated_by"]})
    for t in types:
        counts["crossref:" + t] += 1
    if rw_hits.get(p):
        counts["retraction_watch_entries"] += 1
    flag = "retracted" if (set(types) & RETRACT or any(h.lower().startswith("retraction") for h in rw_hits.get(p, []))) else ""
    if flag:
        counts["retracted"] += 1
    rows.append([p, doi_of[p], ic.get(p, ("", ""))[0], cr["status"], ";".join(types), " | ".join(rw_hits.get(p, [])), flag])

summary = {
    "articles": len(arts),
    "with_doi": sum(1 for p in doi_of.values() if p),
    "crossref_found": sum(1 for r in rows if r[3] == 200),
    "crossref_not_found": [r[0] + " " + r[1] for r in rows if r[3] == 404],
    "with_pmid": sum(1 for v in ic.values() if v[0]),
    "retraction_watch_rows": len(rw),
    "counts": dict(counts),
    "retracted_articles": [r[0] for r in rows if r[6]],
    "flagged_articles": {r[0]: (r[4] + " " + r[5]).strip() for r in rows if r[4].replace("new_version", "").strip(";") or r[5]},
    "checked_on": time.strftime("%Y-%m-%d"),
}
with open(os.path.join(WORK, "a14_retraction_check.tsv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter="\t", lineterminator="\n")
    w.writerow(["pmcid", "doi", "pmid", "crossref_status", "crossref_update_types", "retraction_watch", "retracted"])
    w.writerows(rows)
json.dump(summary, open(os.path.join(WORK, "a14_retraction_check.json"), "w"), indent=1)
print(json.dumps({k: v for k, v in summary.items() if k != "flagged_articles"}, indent=1))
print(len(summary["flagged_articles"]))
