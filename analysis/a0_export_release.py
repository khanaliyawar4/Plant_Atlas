import json, collections
from common import *
data, meta = portal_payload()
json.dump(data, open(out("release_annotated.json"), "w"))
json.dump(meta, open(out("release_META.json"), "w"), indent=1)
rows = [[(r[c] if r[c] != "" else "NA") for c in COLS] for r in data]
write_tsv(out("PBA_release_records.tsv"), COLS, rows)
s = {"records": len(data), "papers": len({r["pmcid"] for r in data}),
     "genes_primary(META)": meta["genes_primary"], "species(META)": meta["species"],
     "engineering_type": collections.Counter(r["engineering_type"] or "NA" for r in data),
     "generated": meta["generated"]}
print(json.dumps(s, indent=1)); json.dump(s, open(out("a0_release_summary.json"), "w"), indent=1)
