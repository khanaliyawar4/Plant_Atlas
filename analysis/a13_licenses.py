import sys, re, json, glob, collections
from common import *
if sys.argv[1] == "scan":
    ids = sorted({r["pmcid"] for r in load_release()}); vx = first_version_files(XML_IDS); a, b = int(sys.argv[2]), int(sys.argv[3])
    with open(out(f"_lic_{a}.jsonl"), "w") as fo:
        for p in ids[a:b]:
            h = open(os.path.join(XML_DIR, f"{p}.{min(vx[p])}.xml"), encoding="utf-8", errors="replace").read(60000)
            m = re.search(r"<license\b[^>]*>.*?</license>", h, re.S); lic = m.group(0) if m else ""
            url = re.search(r'(?:xlink:href|specific-use)="([^"]*creativecommons[^"]*)"', lic) or re.search(r"(https?://creativecommons\.org/[^\s\"<]+)", lic)
            u = url.group(1).lower() if url else ""
            k = ("CC0" if "zero" in u or "publicdomain" in u else "CC BY-NC-ND" if "by-nc-nd" in u else "CC BY-NC-SA" if "by-nc-sa" in u else "CC BY-NC" if "by-nc" in u else "CC BY-SA" if "by-sa" in u else "CC BY-ND" if "by-nd" in u else "CC BY" if "/by/" in u or u.endswith("/by") else "other/none stated")
            fo.write(json.dumps({"p": p, "license": k}) + "\n")
else:
    L = {}
    for f in glob.glob(out("_lic_*.jsonl")):
        for l in open(f):
            try: d = json.loads(l); L[d["p"]] = d["license"]
            except Exception: pass
    c = collections.Counter(L.values()); print(len(L), c.most_common())
    write_tsv(out("a13_article_licenses.tsv"), ["pmcid", "license"], sorted(L.items()))
    json.dump({"articles": len(L), "licenses": dict(c)}, open(out("a13_licenses.json"), "w"), indent=1)
