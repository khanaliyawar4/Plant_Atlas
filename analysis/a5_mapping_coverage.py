import json, collections, re, glob
from common import *
rel = load_release()
plaza = json.load(open(os.path.join(ATLAS, "data", "plaza_orthogroups.json")))
assert len(plaza) == len(rel)
AGRO = {"drought","salt","cold","heat","disease","pest","herbicide","yield","flowering","pigment","oilseed","nutrient","photo","repro","growth","root","germination","senescence"}
REPORTER = re.compile(r"^(e?gfp|s?gfp|yfp|eyfp|cfp|rfp|mcherry|gus|uida|luc|luciferase|nptii|npt2|hpt|hph|bar|pat|cas9|cas12a?|dcas9|venus|tdtomato)$", re.I)

classify = mod_group
def host_group(sp):
    if sp == "Arabidopsis thaliana": return "Arabidopsis thaliana"
    if sp == "Oryza sativa": return "Oryza sativa"
    if sp in ("Nicotiana benthamiana", "Nicotiana tabacum"): return "Nicotiana benthamiana / N. tabacum"
    return "Other hosts"
def period(y):
    if not y: return "year unknown"
    return "2000-2010" if y <= 2010 else "2011-2018" if y <= 2018 else "2019-2026"
def status(r, p):
    if r.get("_og"): return "orthogroup assigned"
    g = r.get("_g") or ""
    if not g or REPORTER.match(re.sub(r"[^A-Za-z0-9]", "", g)): return "no lead gene / reporter-marker-tool gene"
    if not p.get("code"): return "host species not in PLAZA 5.0"
    return "host in PLAZA 5.0, symbol/ID not resolved"
strata = collections.defaultdict(lambda: collections.Counter())
reasons = collections.Counter()
for r, p in zip(rel, plaza):
    agro = any(t in AGRO for t in r.get("_t", []))
    st = status(r, p); reasons[st] += 1
    keys = [("All records", "all"), ("Host group", host_group(r.get("_csp") or "")), ("Publication period", period(r.get("_y"))), ("Modification class", classify(r["modification_type"] or ""))]
    for dim, k in keys:
        c = strata[(dim, k)]; c["n"] += 1; c["trait_class(TO-anchored)"] += agro
        c["direct_TO_term"] += bool(r.get("_to")); c["PO_term"] += bool(r.get("_po"))
        c["orthogroup"] += bool(r.get("_og")); c["TF_family"] += bool(r.get("_tf"))
        c[st] += 1
cols = ["n", "trait_class(TO-anchored)", "direct_TO_term", "PO_term", "orthogroup", "TF_family", "no lead gene / reporter-marker-tool gene", "host species not in PLAZA 5.0", "host in PLAZA 5.0, symbol/ID not resolved"]
rows = []
for (dim, k), c in sorted(strata.items(), key=lambda x: (["All records","Host group","Publication period","Modification class"].index(x[0][0]), -x[1]["n"])):
    rows.append([dim, k] + [f'{c[x]}' if x == "n" else f'{c[x]} ({100*c[x]/c["n"]:.1f}%)' for x in cols])
write_tsv(out("a5_mapping_coverage.tsv"), ["dimension", "stratum"] + cols, rows)
vers = {}
for f in glob.glob(os.path.join(ATLAS, "data", "resources", "ontologies", "*.obo")):
    head = open(f).read(3000); m = re.search(r"data-version:\s*(\S+)", head)
    vers[os.path.basename(f)] = m.group(1) if m else None
_res = os.path.join(ATLAS, "data", "resources")
if os.path.isdir(os.path.join(_res, "plaza")):
    vers["PLAZA"] = sorted(os.listdir(os.path.join(_res, "plaza")))
if os.path.isdir(os.path.join(_res, "planttfdb")):
    vers["PlantTFDB species lists"] = len(os.listdir(os.path.join(_res, "planttfdb")))
res = {"orthogroup_status": dict(reasons), "resource_versions": vers}
print(json.dumps(res, indent=1)); json.dump(res, open(out("a5_mapping_summary.json"), "w"), indent=1)
for r in rows[:12]: print(r)
