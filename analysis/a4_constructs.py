import re, json, collections
from common import *
rel = load_release()
src = open(os.path.join(ATLAS, "annotate.py")).read(); ns = {"re": re}
exec(src[src.index("_TERM=["):src.index("_UP=re.compile")], ns)
def toks(g): return [x.strip() for x in g.replace("::", "-").split("-") if x.strip()]
def is_na(x): return x.upper() == "NA"
res = {}
A = collections.Counter(); B = collections.Counter(); A2 = collections.Counter()
for r in rel:
    g = (r["gene_construct"] or "").strip()
    if not g or is_na(g): A["no construct string"] += 1; B["no construct string"] += 1; continue
    t = toks(g); hp, ht = not is_na(t[0]), not is_na(t[-1])
    A["complete" if hp and ht else "promoter only" if hp else "terminator only" if ht else "neither"] += 1
    if hp and ht: A2[min(len(t), 3)] += 1
    hp = ht = True
    for tu in g.split("---"):
        f = toks(tu)
        if len(f) < 2: hp = ht = False; continue
        if is_na(f[0]): hp = False
        if len(f) < 3 or is_na(f[-1]): ht = False
    B["complete" if hp and ht else "promoter only" if hp else "terminator only" if ht else "neither/none"] += 1
res["rule_A_first_last_token"] = dict(A); res["rule_A_complete_by_token_count(1,2,>=3)"] = dict(A2)
res["rule_B_per_transcription_unit"] = dict(B)
P = collections.Counter(); T = collections.Counter(); both = 0
for r in rel:
    d = ns["parse_construct"](r["gene_construct"])
    for x in d["pro"]: P[x] += 1
    for x in d["ter"]: T[x] += 1
    both += bool(d["pro"] and d["ter"])
res["promoter_classes"] = dict(P.most_common()); res["terminator_classes"] = dict(T.most_common())
res["terminator_classes_with_zero_matches"] = [n for n, _ in ns["_TERM"] if n not in T]
res["records_with_promoter_and_terminator_class"] = both
ROOT = r"root[\s-]?(specific|preferential)|\brcc3\b|\btobrb7\b|\brb7\b|\bpyk10\b|\brold\b|\bscr\b|\bpscr\b|\bshr\b|\bpshr\b|\bwox5\b|\bpwox5\b|\bexpa7\b|\bpht1(;\d+)?\b|\bplt\d?\b|\blrp1\b|\bslreo\b"
hits = [r for r in rel if re.search(ROOT, r["gene_construct"] or "", re.I)]
def root_promoter(g):
    for tu in (g or "").split("---"):
        f = toks(tu)
        if f and re.search(ROOT, f[0], re.I): return f[0]
    return None
prom = [(r["pmcid"], r["gene_construct"], root_promoter(r["gene_construct"])) for r in rel if root_promoter(r["gene_construct"])]
res["root_promoter_extended_lexicon"] = {"records_with_root_term_anywhere_in_construct": len(hits),
    "records_with_root_promoter_in_promoter_slot": len(prom),
    "promoter_names": dict(collections.Counter(re.sub(r"[^A-Za-z0-9]", "", p[2]).lower() for p in prom).most_common())}
write_tsv(out("a4_root_promoter_records.tsv"), ["pmcid", "construct", "promoter_slot"], prom)
print(json.dumps(res, indent=1)); json.dump(res, open(out("a4_constructs.json"), "w"), indent=1)
