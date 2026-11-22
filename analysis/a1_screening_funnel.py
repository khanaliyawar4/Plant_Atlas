import csv, re, json, collections
from common import *
n = 0; keep = 0; reasons = collections.Counter(); acc_all = set(); acc_keep = collections.Counter()
with open(DECISIONS, newline="") as f:
    r = csv.reader(f); next(r)
    for row in r:
        n += 1; a = row[0].split(".")[0]; acc_all.add(a)
        if row[1] == "yes": keep += 1; acc_keep[a] += 1
        else: reasons[re.sub(r"[:(].*", "", row[2]).strip()] += 1
res = {"article_versions_screened": n, "versions_retained": keep, "retained_pct": round(100*keep/n, 3),
       "distinct_accessions_screened": len(acc_all), "distinct_accessions_retained": len(acc_keep),
       "accessions_with_more_than_one_retained_version": sum(1 for v in acc_keep.values() if v > 1),
       "rejections_by_first_failed_rule": dict(reasons.most_common())}
print(json.dumps(res, indent=1)); json.dump(res, open(out("a1_screening_funnel.json"), "w"), indent=1)
