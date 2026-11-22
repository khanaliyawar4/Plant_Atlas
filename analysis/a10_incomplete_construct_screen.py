import sys, json, random, re, glob, collections
from common import *
rel = load_release()
def toks(g): return [x.strip() for x in g.replace("::", "-").split("-") if x.strip()]
TERM = re.compile(r"terminator|\bt-?nos\b|\bnos-?t\b|\bnost\b|nopaline synthase|\bocs\b|octopine synthase|\bt35s\b|35s[\s-]*(poly ?a|terminator)|rbcs[\s-]?(e9|3'|terminator)|\bhsp ?terminator|poly ?\(?a\)? signal|polyadenylation", re.I)
PROM = re.compile(r"promoter|driven by|under (the )?control of|\bcamv ?35s\b|\b2x ?35s\b|\b35s\b|ubiquitin|\bubi1?\b|\bactin\b|\bu6\b|\bu3\b", re.I)
VECT = re.compile(r"\bp(bi|cambia|gwb|bin|green|cubi|hb|rcs|mdc|k7wg|k2gw|h7wg|ga|be|zp|ehee|kse|yl|rgeb|cr)\w*\d", re.I)
if sys.argv[1] == "sample":
    inc = []
    for i, r in enumerate(rel):
        g = (r["gene_construct"] or "").strip()
        if not g or g.upper() == "NA": continue
        t = toks(g); hp, ht = t[0].upper() != "NA", t[-1].upper() != "NA"
        if not (hp and ht): inc.append((i, "promoter only" if hp else "terminator only" if ht else "neither"))
    random.seed(20261026); s = random.sample(inc, 300)
    json.dump(s, open(out("a10_sample.json"), "w")); print(len(inc), "incomplete (rule A, construct present); sampled 300")
elif sys.argv[1] == "scan":
    sys.path.insert(0, EXTRACTOR); import yaml
    from src.article_io import SectionConfig, slice_body
    sc = SectionConfig.from_dict(yaml.safe_load(open(os.path.join(EXTRACTOR, "config", "default.yaml")))["sections"])
    vt, vx = first_version_files(TXT_IDS), first_version_files(XML_IDS)
    s = json.load(open(out("a10_sample.json"))); a, b = int(sys.argv[2]), int(sys.argv[3])
    with open(out(f"_a10_{a}.jsonl"), "w") as fo:
        for i, cat in s[a:b]:
            r = rel[i]; p = r["pmcid"]
            txt = open(os.path.join(TXT_DIR, f"{p}.{min(vt[p])}.txt"), encoding="utf-8", errors="replace").read()
            body = slice_body(txt, sc)
            xml = open(os.path.join(XML_DIR, f"{p}.{min(vx[p])}.xml"), encoding="utf-8", errors="replace").read()
            full = re.sub(r"<[^>]+>", " ", xml.split("<ref-list")[0])
            sup = " ".join(re.findall(r"<supplementary-material.*?</supplementary-material>", xml, re.S))
            def where(rx):
                if rx.search(body): return "in model input (body)"
                if rx.search(full): return "only outside model input (other XML text)"
                return "not in article XML text"
            fo.write(json.dumps({"i": i, "p": p, "cat": cat, "construct": r["gene_construct"],
                "terminator": where(TERM) if cat in ("promoter only", "neither") else None,
                "promoter": where(PROM) if cat in ("terminator only", "neither") else None,
                "vector_named_in_body": bool(VECT.search(body)), "has_supplementary_files": bool(sup)}) + "\n")
else:
    R = []
    for f in glob.glob(out("_a10_*.jsonl")):
        for l in open(f):
            try: R.append(json.loads(l))
            except Exception: pass
    R = {d["i"]: d for d in R}.values()
    res = {"screened_records": len(R), "by_category": dict(collections.Counter(d["cat"] for d in R))}
    for el in ("terminator", "promoter"):
        c = collections.Counter(d[el] for d in R if d[el]); res[f"missing_{el}"] = dict(c)
        nt = [d for d in R if d[el] == "not in article XML text"]
        res[f"missing_{el}_not_in_text_with_vector_named"] = sum(d["vector_named_in_body"] for d in nt)
        res[f"missing_{el}_not_in_text_with_supplementary_files"] = sum(d["has_supplementary_files"] for d in nt)
    print(json.dumps(res, indent=1)); json.dump(res, open(out("a10_incomplete_construct_screen.json"), "w"), indent=1)
    write_tsv(out("a10_incomplete_construct_screen.tsv"), ["pmcid", "category", "construct", "terminator_mention", "promoter_mention", "vector_named_in_body", "has_supplementary_files"],
              [[d["p"], d["cat"], d["construct"], d["terminator"] or "", d["promoter"] or "", d["vector_named_in_body"], d["has_supplementary_files"]] for d in R])
