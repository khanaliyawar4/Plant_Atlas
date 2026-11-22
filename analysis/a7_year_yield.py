import sys, random, re, json, glob, collections
from common import *
ids = [l.strip() for l in open(XML_IDS) if l.strip()]
first = {}
for i in sorted(ids, key=lambda s: (s.split(".")[0], int(s.split(".")[1]))): first.setdefault(i.split(".")[0], i)
acc = sorted(first); random.seed(20261023); samp = random.sample(acc, 6000)
if sys.argv[1] == "sample":
    a, b = int(sys.argv[2]), int(sys.argv[3]); yr = re.compile(r"<pub-date[^>]*>.*?<year>(\d{4})</year>", re.S)
    with open(out(f"_years_{a}.jsonl"), "w") as fo:
        for p in samp[a:b]:
            h = open(os.path.join(XML_DIR, first[p] + ".xml"), encoding="utf-8", errors="replace").read(40000)
            ys = [int(y) for y in yr.findall(h)]; fo.write(json.dumps({"p": p, "y": min(ys) if ys else None}) + "\n")
else:
    y = {}
    for f in glob.glob(out("_years_*.jsonl")):
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            if d.get("y"): y[d["p"]] = d["y"]
    N = len(acc); n = len(y)
    rel = load_release(); py = {}
    for r in rel: py.setdefault(r["pmcid"], r["_y"])
    contrib = collections.Counter(py.values())
    samp_y = collections.Counter(min(max(v, 2000), 2026) if v >= 2000 else "<2000" for v in y.values())
    rows = []
    for yy in range(2015, 2027):
        k = samp_y.get(yy, 0); est = round(k / n * N)
        rows.append([yy, k, est, contrib.get(yy, 0), f"{100*contrib.get(yy,0)/est:.1f}%" if est else ""])
    write_tsv(out("a7_year_yield.tsv"), ["publication_year", "sampled_retained_articles", "estimated_retained_articles(all)", "release_contributing_articles", "contributing/retained"], rows)
    res = {"retained_accessions": N, "sample_size_with_year": n, "seed": 20261023}
    print(json.dumps(res)); [print(r) for r in rows]; json.dump(res, open(out("a7_year_yield.json"), "w"))
