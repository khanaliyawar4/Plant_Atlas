import json, re, collections
from common import *
rel = load_release()
plaza = json.load(open(os.path.join(ATLAS, "data", "plaza_orthogroups.json")))
_re_sym = re.compile(r"^[A-Za-z][A-Za-z0-9][A-Za-z0-9._/-]{0,22}$"); NON = {"na","n/a","none","unknown","nd","null","-",""}
def is_sym(s): s = (s or "").strip(); return bool(s) and s.lower() not in NON and bool(_re_sym.match(s))
def split0(s):
    out, d, cur = [], 0, ""
    for ch in s:
        if ch == "(": d += 1
        elif ch == ")": d = max(0, d - 1)
        if ch == "," and d == 0: out.append(cur.strip()); cur = ""
        else: cur += ch
    if cur.strip(): out.append(cur.strip())
    return out
def lead_source(genes):
    e = split0(genes or "")
    if not e: return None
    m = re.search(r"\((.*)\)\s*$", e[0])
    if not m: return None
    parts = split0(m.group(1)); src = parts[-1] if len(parts) >= 2 else None
    if not src: return None
    w = re.sub(r"[^A-Za-z .]", " ", src).split()
    return " ".join(w[:2]).lower() if w else None
labels = collections.defaultdict(lambda: {"recs": 0, "sources": collections.Counter(), "hosts": set(), "gids": set(), "heterologous": 0})
for r, p in zip(rel, plaza):
    g = r.get("_g")
    if not is_sym(g): continue
    L = labels[g.lower()]; L["recs"] += 1
    s = lead_source(r["genes"]); host = (r.get("_csp") or "").lower()
    if s: L["sources"][s] += 1
    L["hosts"].add(host)
    if p.get("gene_id"): L["gids"].add(p["gene_id"])
    if s and host and not host.startswith(s.split()[0]): L["heterologous"] += 1
n = len(labels)
ent = set()
for k, L in labels.items():
    for s in L["sources"]: ent.add((k, s))
no_src = sum(1 for L in labels.values() if not L["sources"])
res = {"lead_symbol_labels": n,
       "labels_with_parsed_source_organism": n - no_src,
       "symbol_x_source_organism_entities": len(ent) + no_src,
       "labels_with_more_than_one_source_organism(possible homonyms or orthologues sharing a symbol)": sum(1 for L in labels.values() if len(L["sources"]) > 1),
       "labels_resolved_to_exactly_one_PLAZA_gene_model": sum(1 for L in labels.values() if len(L["gids"]) == 1),
       "labels_resolved_to_more_than_one_PLAZA_gene_model(ambiguous)": sum(1 for L in labels.values() if len(L["gids"]) > 1),
       "labels_not_resolved_in_PLAZA": sum(1 for L in labels.values() if not L["gids"]),
       "records_whose_lead_gene_source_differs_from_host(heterologous)": sum(L["heterologous"] for L in labels.values()),
       "note": "PLAZA lookup uses the HOST genome; for heterologous genes a host-genome match identifies a host homologue or a symbol collision, not the transgene itself."}
het_og = sum(1 for r, p in zip(rel, plaza) if p.get("og") and lead_source(r["genes"]) and (r.get("_csp") or "") and not (r.get("_csp") or "").lower().startswith(lead_source(r["genes"]).split()[0]))
res["orthogroup_records_with_heterologous_lead_gene"] = het_og
print(json.dumps(res, indent=1)); json.dump(res, open(out("a6_gene_identity.json"), "w"), indent=1)
write_tsv(out("a6_lead_symbol_labels.tsv"), ["lead_symbol(lower)", "records", "source_organisms", "host_species", "PLAZA_gene_models"],
          [[k, L["recs"], ";".join(f"{s}:{c}" for s, c in L["sources"].most_common()), ";".join(sorted(L["hosts"])), ";".join(sorted(L["gids"]))] for k, L in sorted(labels.items())])
