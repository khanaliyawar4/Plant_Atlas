import json, re, collections
from common import *
C = {
 "China": ["China", "P.R. China", "PR China", "P. R. China", "People's Republic of China", "PRC", "P.R.China"],
 "USA": ["USA", "U.S.A.", "United States", "United States of America", "U.S."],
 "Japan": ["Japan"], "Germany": ["Germany", "Deutschland"], "South Korea": ["Korea", "South Korea", "Republic of Korea", "Korea, Republic of", "Rep. of Korea"],
 "United Kingdom": ["UK", "U.K.", "United Kingdom", "England", "Scotland", "Wales", "Northern Ireland", "Great Britain"],
 "India": ["India"], "France": ["France"], "Canada": ["Canada"], "Spain": ["Spain", "España"], "Italy": ["Italy", "Italia"],
 "Taiwan": ["Taiwan", "Taiwan, ROC", "Republic of China"], "Netherlands": ["Netherlands", "The Netherlands", "Holland"],
 "Australia": ["Australia"], "Brazil": ["Brazil", "Brasil"], "Switzerland": ["Switzerland"], "Sweden": ["Sweden"], "Belgium": ["Belgium"],
 "Israel": ["Israel"], "Denmark": ["Denmark"], "Austria": ["Austria"], "Poland": ["Poland"], "Czech Republic": ["Czech Republic", "Czechia"],
 "Finland": ["Finland"], "Norway": ["Norway"], "Mexico": ["Mexico", "México"], "Argentina": ["Argentina"], "Chile": ["Chile"],
 "Pakistan": ["Pakistan"], "Iran": ["Iran"], "Egypt": ["Egypt"], "Saudi Arabia": ["Saudi Arabia"], "Turkey": ["Turkey", "Türkiye"],
 "Russia": ["Russia", "Russian Federation"], "Singapore": ["Singapore"], "New Zealand": ["New Zealand"], "Ireland": ["Ireland"],
 "Portugal": ["Portugal"], "Greece": ["Greece"], "Hungary": ["Hungary"], "Slovakia": ["Slovakia", "Slovak Republic"],
 "Slovenia": ["Slovenia"], "Croatia": ["Croatia"], "Serbia": ["Serbia"], "Romania": ["Romania"], "Bulgaria": ["Bulgaria"],
 "Estonia": ["Estonia"], "Lithuania": ["Lithuania"], "Latvia": ["Latvia"], "Ukraine": ["Ukraine"], "Belarus": ["Belarus"],
 "Kazakhstan": ["Kazakhstan"], "Thailand": ["Thailand"], "Vietnam": ["Vietnam", "Viet Nam"], "Malaysia": ["Malaysia"],
 "Indonesia": ["Indonesia"], "Philippines": ["Philippines"], "Bangladesh": ["Bangladesh"], "Sri Lanka": ["Sri Lanka"], "Nepal": ["Nepal"],
 "South Africa": ["South Africa"], "Kenya": ["Kenya"], "Nigeria": ["Nigeria"], "Ethiopia": ["Ethiopia"], "Ghana": ["Ghana"],
 "Tunisia": ["Tunisia"], "Morocco": ["Morocco"], "Algeria": ["Algeria"], "Uganda": ["Uganda"], "Tanzania": ["Tanzania"],
 "Colombia": ["Colombia"], "Peru": ["Peru"], "Uruguay": ["Uruguay"], "Venezuela": ["Venezuela"], "Cuba": ["Cuba"], "Ecuador": ["Ecuador"],
 "Costa Rica": ["Costa Rica"], "Qatar": ["Qatar"], "United Arab Emirates": ["United Arab Emirates", "UAE"], "Jordan": ["Jordan"],
 "Lebanon": ["Lebanon"], "Iraq": ["Iraq"], "Oman": ["Oman"], "Kuwait": ["Kuwait"], "Luxembourg": ["Luxembourg"], "Iceland": ["Iceland"],
 "Cyprus": ["Cyprus"], "Malta": ["Malta"], "Hong Kong": ["Hong Kong"], "Macau": ["Macau", "Macao"], "Mongolia": ["Mongolia"],
 "Uzbekistan": ["Uzbekistan"], "Cameroon": ["Cameroon"], "Benin": ["Benin"], "Senegal": ["Senegal"], "Zimbabwe": ["Zimbabwe"],
 "Bosnia and Herzegovina": ["Bosnia and Herzegovina"], "North Macedonia": ["Macedonia"], "Armenia": ["Armenia"], "Georgia (country)": [],
}
pats = []
for canon, vs in C.items():
    for v in vs: pats.append((re.compile(r"(?<![A-Za-z])" + re.escape(v) + r"(?![A-Za-z])", re.I if len(v) > 3 else 0), canon))
TAG = {v.lower(): k for k, vs in C.items() for v in vs}
def country_of(aff):
    if aff is None: return None
    if aff.get("country_tag"):
        t = aff["country_tag"].strip().rstrip(".")
        if t.lower() in TAG: return TAG[t.lower()]
        hit = [(m.start(), c) for p, c in pats for m in p.finditer(t)]
        if hit: return max(hit)[1]
    hit = [(m.start(), c) for p, c in pats for m in p.finditer(aff["text"])]
    return max(hit)[1] if hit else None
X = json.load(open(out("a3_xml_metadata.json")))
rows = []; first = {}; corr = {}; multi = {}; how = collections.Counter()
for p, d in sorted(X.items()):
    affs = d.get("affs", {}); auths = [a for a in d.get("authors", []) if not a["collab"]]
    a1 = auths[0] if auths else None; aff = None
    if a1 and a1["rids"]:
        for r in a1["rids"]:
            if r in affs: aff = affs[r]; how["first author linked aff"] += 1; break
    if aff is None and a1 and a1["inner_aff"]: aff = {"text": a1["inner_aff"][0], "country_tag": None}; how["first author inline aff"] += 1
    if aff is None and affs: aff = next(iter(affs.values())); how["fallback: first aff of article"] += 1
    if aff is None: how["no affiliation"] += 1
    c = country_of(aff); first[p] = c
    allc = {country_of(a) for a in affs.values()} - {None}; multi[p] = len(allc) > 1
    ca = next((a for a in auths if a["corresp"]), None)
    cc = None
    if ca:
        for r in ca["rids"]:
            if r in affs: cc = country_of(affs[r]); break
    corr[p] = cc
    rows.append([p, c or "", cc or "", ";".join(sorted(allc)), (aff or {}).get("text", "")[:300]])
write_tsv(out("a8_country_by_paper.tsv"), ["pmcid", "first_author_country", "corresponding_author_country", "all_affiliation_countries", "first_author_affiliation_text"], rows)
res = {"papers": len(X), "resolved_first_author": sum(1 for v in first.values() if v),
       "unresolved": [p for p, v in first.items() if not v].__len__(), "how_affiliation_chosen": dict(how),
       "countries": len({v for v in first.values() if v}),
       "top_first_author": collections.Counter(v for v in first.values() if v).most_common(15),
       "multinational_papers(>1 country among affiliations)": sum(multi.values()),
       "corresponding_author_resolved": sum(1 for v in corr.values() if v),
       "first_vs_corresponding_agree(where both resolved)": None}
both = [(first[p], corr[p]) for p in X if first[p] and corr[p]]
res["first_vs_corresponding_agree(where both resolved)"] = f"{sum(a == b for a, b in both)}/{len(both)}"
old = json.load(open(PREVIOUS_COUNTRY))
norm = {"United States": "USA", "Korea": "South Korea", "UK": "United Kingdom"}
on = lambda x: country_of({"text": x, "country_tag": None}) or norm.get(x, x)
cmp_ = [(on(old[p]), first[p]) for p in old if old[p] and first.get(p)]
res["agreement_with_previous_country_file"] = f"{sum(a == b for a, b in cmp_)}/{len(cmp_)}"
res["previous_file_coverage"] = f"{len(old)} papers, {sum(1 for v in old.values() if v)} with country"
print(json.dumps(res, indent=1)); json.dump(res, open(out("a8_country_summary.json"), "w"), indent=1)
dis = [(p, old[p], first[p]) for p in old if old[p] and first.get(p) and on(old[p]) != first[p]]
import collections as _c
res2 = {"previous_file_top_raw_labels": _c.Counter(old.values()).most_common(8)}
print(res2)
write_tsv(out("a8_disagreements_with_previous_file.tsv"), ["pmcid", "previous", "new_rule"], dis)
