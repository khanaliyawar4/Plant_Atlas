import sys, re, json, glob, collections
from common import *
rel = load_release()
COMMON = {"oryza": ["rice"], "nicotiana": ["tobacco"], "solanum lycopersicum": ["tomato"], "solanum tuberosum": ["potato"],
          "zea": ["maize", "corn"], "triticum": ["wheat"], "glycine": ["soybean", "soya"], "hordeum": ["barley"], "gossypium": ["cotton"],
          "populus": ["poplar", "aspen"], "malus": ["apple"], "brassica napus": ["rapeseed", "canola", "oilseed rape"], "vitis": ["grape"],
          "citrus": ["citrus", "orange"], "medicago sativa": ["alfalfa"], "sorghum": ["sorghum"], "manihot": ["cassava"], "musa": ["banana"],
          "fragaria": ["strawberry"], "cucumis sativus": ["cucumber"], "lycopersicon": ["tomato"], "saccharum": ["sugarcane"], "pyrus": ["pear"],
          "capsicum": ["pepper"], "camellia": ["tea"], "panicum": ["switchgrass"], "setaria": ["foxtail millet", "setaria"], "petunia": ["petunia"]}
NUM = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s?(%|-?\s?fold)", re.I)
def norm(t): return re.sub(r"\s+", " ", t).lower()
if sys.argv[1] == "scan":
    vt = first_version_files(TXT_IDS); a, b = int(sys.argv[2]), int(sys.argv[3])
    ids = sorted({r["pmcid"] for r in rel})[a:b]; by = collections.defaultdict(list)
    for i, r in enumerate(rel): by[r["pmcid"]].append(i)
    with open(out(f"_a12_{a}.jsonl"), "w") as fo:
        for p in ids:
            t = norm(open(os.path.join(TXT_DIR, f"{p}.{min(vt[p])}.txt"), encoding="utf-8", errors="replace").read())
            for i in by[p]:
                r = rel[i]; g = (r.get("_g") or "").strip(); gs = None
                if g and g.upper() != "NA":
                    v = {g.lower()}
                    m = re.match(r"^([A-Z][a-z]{1,2})([A-Z0-9].+)$", g)
                    if m: v.add(m.group(2).lower())
                    gs = "exact" if g.lower() in t else "prefix-stripped" if any(x in t for x in v) else "absent"
                sp = (r.get("_csp") or "").lower(); ss = None
                if sp:
                    gen = sp.split()[0]
                    if sp in t: ss = "binomial"
                    elif re.search(r"\b" + re.escape(gen[0]) + r"\. ?" + re.escape(sp.split()[1] if len(sp.split()) > 1 else "zzz"), t): ss = "abbreviated binomial"
                    elif gen in t: ss = "genus"
                    elif any(c in t for k, cs in COMMON.items() if sp.startswith(k) for c in cs): ss = "common name"
                    else: ss = "absent"
                nums = [m.group(0) for m in NUM.finditer(r["phenotype"] or "")]
                nok = sum(1 for n in nums if re.sub(r"\s", "", n.lower()) in t.replace(" ", ""))
                fo.write(json.dumps({"i": i, "gene": gs, "species": ss, "nums": len(nums), "nums_found": nok}) + "\n")
else:
    R = {}
    for f in glob.glob(out("_a12_*.jsonl")):
        for l in open(f):
            try: d = json.loads(l); R[d["i"]] = d
            except Exception: pass
    g = collections.Counter(d["gene"] for d in R.values() if d["gene"]); s = collections.Counter(d["species"] for d in R.values() if d["species"])
    res = {"records_checked": len(R), "lead_gene_symbol": dict(g), "host_taxon": dict(s),
           "numeric_effect_sizes_in_phenotype": sum(d["nums"] for d in R.values()),
           "numeric_effect_sizes_found_in_source": sum(d["nums_found"] for d in R.values())}
    print(json.dumps(res, indent=1)); json.dump(res, open(out("a12_source_grounding.json"), "w"), indent=1)
