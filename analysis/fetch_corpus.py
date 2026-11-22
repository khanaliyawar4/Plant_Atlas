import argparse
import concurrent.futures as cf
import os
import time
import urllib.error
import urllib.request

BASE = "https://pmc-oa-opendata.s3.amazonaws.com"


def fetch(version_id, kind, out_dir):
    dst = os.path.join(out_dir, f"{version_id}.{kind}")
    if os.path.exists(dst) and os.path.getsize(dst) > 0:
        return "present"
    url = f"{BASE}/{version_id}/{version_id}.{kind}"
    for attempt in range(4):
        try:
            data = urllib.request.urlopen(url, timeout=60).read()
            with open(dst, "wb") as f:
                f.write(data)
            return "downloaded"
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return "not in bucket"
            time.sleep(2 + 3 * attempt)
        except Exception:
            time.sleep(2 + 3 * attempt)
    return "failed"


ap = argparse.ArgumentParser(description="Download PMC Open Access texts and XML for a list of PMCID.version identifiers.")
ap.add_argument("id_list", help="file with one PMCID.version per line, e.g. inputs/screening/txt_pmcids.txt")
ap.add_argument("--out", default="inputs/corpus")
ap.add_argument("--kinds", default="txt,xml")
ap.add_argument("--workers", type=int, default=8)
args = ap.parse_args()
ids = [l.strip() for l in open(args.id_list) if l.strip()]
jobs = []
for kind in args.kinds.split(","):
    d = os.path.join(args.out, "TXT_files" if kind == "txt" else "XML_files")
    os.makedirs(d, exist_ok=True)
    jobs += [(i, kind, d) for i in ids]
status = {}
with cf.ThreadPoolExecutor(args.workers) as ex:
    for (i, kind, _), s in zip(jobs, ex.map(lambda j: fetch(*j), jobs)):
        status[s] = status.get(s, 0) + 1
        if s in ("not in bucket", "failed"):
            print(kind, i, s)
print(status)
