import json, collections, re
from common import *
import importlib.util
spec = importlib.util.spec_from_file_location("a8src", os.path.join(os.path.dirname(os.path.abspath(__file__)), "a8_country.py"))
src = open(spec.origin, encoding="utf-8").read().split("X = json.load")[0]
ns = {}
exec(compile(src, "a8_country", "exec"), ns)
country_of = ns["country_of"]
X = json.load(open(out("a3_xml_metadata.json")))
rows = []; used = collections.Counter()
for p, d in sorted(X.items()):
    affs = d.get("affs", {}); auths = [a for a in d.get("authors", []) if not a["collab"]]
    a1 = auths[0] if auths else None; aff = None
    if a1 and a1["rids"]:
        for r in a1["rids"]:
            if r in affs: aff = affs[r]; break
    if aff is None and a1 and a1["inner_aff"]: aff = {"text": a1["inner_aff"][0], "country_tag": None}
    if aff is None and affs: aff = next(iter(affs.values()))
    if aff is None: used["none"] += 1; continue
    if not aff.get("country_tag"): used["string rule"] += 1; continue
    used["country element"] += 1
    tag = country_of(aff)
    txt = aff["text"]
    full = country_of({"text": txt, "country_tag": None})
    ct = aff["country_tag"].strip()
    i = txt.rfind(ct)
    stripped_txt = (txt[:i] + txt[i + len(ct):]) if i >= 0 else txt
    stripped = country_of({"text": stripped_txt, "country_tag": None})
    rows.append([p, ct, tag or "", full or "", stripped or "", txt[:300]])
n = len(rows)
agree_full = sum(1 for r in rows if r[2] and r[2] == r[3])
tag_resolved = sum(1 for r in rows if r[2])
st_res = [r for r in rows if r[4]]
agree_st = sum(1 for r in st_res if r[2] == r[4])
dis = [r for r in rows if r[2] != r[3]]
res = {"papers": len(X), "first_author_affiliation_source": dict(used),
       "validation_set(first-author affiliation has <country>)": n,
       "country_element_resolved": tag_resolved,
       "string_rule_on_full_affiliation_agrees_with_country_element": f"{agree_full}/{tag_resolved}",
       "string_rule_after_removing_country_element_text: resolved": f"{len(st_res)}/{n}",
       "string_rule_after_removing_country_element_text: agrees": f"{agree_st}/{len(st_res)}",
       "disagreements_full": [(r[0], r[1], r[2], r[3]) for r in dis][:40]}
print(json.dumps(res, indent=1))
json.dump(res, open(out("a8b_country_validation.json"), "w"), indent=1)
write_tsv(out("a8b_country_validation.tsv"), ["pmcid", "country_element", "country_from_element", "string_rule_full_text", "string_rule_without_element_text", "affiliation_text"], rows)
