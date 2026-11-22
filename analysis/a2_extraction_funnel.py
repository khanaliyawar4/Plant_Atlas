import sys, json, collections, random, os, glob
from common import *

def per_article_status():
    st = {}; ev = collections.Counter(); prefilter = collections.Counter(); parse_err = set()
    for l in open(RUN_LOG):
        d = json.loads(l); k = d.get("kind"); p = d.get("pmcid")
        ev[k] += 1
        if not p: continue
        if k == "prefilter.skip":
            st[p] = "prefilter_skip"; prefilter[d["reason"].split("(")[0].strip()] += 1
        elif k == "gate.skip": st[p] = "gate_reject"
        elif k == "article.done": st[p] = "yielded_records"
        elif k == "extract.parse_error": parse_err.add(p)
        elif k in ("extract.empty", "extract.all_rejected_evidence", "extract.error") and st.get(p) != "yielded_records":
            st[p] = {"extract.empty": "gate_pass_no_rows_returned", "extract.all_rejected_evidence": "gate_pass_all_rows_failed_quote_check", "extract.error": "gate_pass_request_error"}[k]
    return st, ev, prefilter, parse_err

if sys.argv[1] == "log":
    st, ev, prefilter, parse_err = per_article_status()
    c = collections.Counter(st.values())
    gate_pass = sum(v for k, v in c.items() if k.startswith("gate_pass") or k == "yielded_records")
    dec = collections.Counter(); qlen = []; acc = []; rej = []
    for l in open(EVIDENCE_LOG):
        d = json.loads(l); reason = d["reason"]; key = reason.split(" (")[0]
        dec[(d["decision"], key)] += 1
        if d["decision"] == "accepted": qlen.append(len(d["evidence_quote"])); acc.append(d)
        else: rej.append(d)
    qlen.sort()
    progress = {l.strip() for l in open(RUN_PROGRESS) if l.strip()}
    res = {"accessions_processed(progress file)": len(progress),
           "accessions_in_log": len(st), "status_counts": dict(c),
           "gate_passed": gate_pass,
           "gate_pass_with_json_parse_failure": len(parse_err),
           "prefilter_reasons": dict(prefilter),
           "log_event_counts": dict(ev),
           "evidence_check": {f"{a}|{b}": n for (a, b), n in dec.items()},
           "candidate_rows": sum(dec.values()),
           "accepted_rows": sum(n for (a, _), n in dec.items() if a == "accepted"),
           "quote_length_chars": {"min": qlen[0], "median": qlen[len(qlen)//2], "max": qlen[-1]}}
    print(json.dumps(res, indent=1)); json.dump(res, open(out("a2_extraction_funnel.json"), "w"), indent=1)
    write_tsv(out("a2_article_status.tsv"), ["pmcid", "status"], sorted(st.items()))
    random.seed(20261026)
    strict = [d for d in acc if d["reason"] == "strict"]; chunk = [d for d in acc if d["reason"].startswith("chunked")]
    rows = []
    for lab, pool, n in (("accepted: continuous match", strict, 4), ("accepted: 2-of-3 segment fallback", chunk, 6), ("rejected", rej, 6)):
        for d in random.sample(pool, n):
            r = d["row"]
            rows.append([lab, d["reason"], r.get("pmcid"), r.get("plant_species"), str(r.get("genes"))[:120], r.get("gene_construct"), d["evidence_quote"]])
    write_tsv(out("a2_evidence_examples.tsv"), ["outcome", "diagnostic", "pmcid", "host", "genes", "construct", "evidence_quote"], rows)

elif sys.argv[1] == "trunc":
    sys.path.insert(0, EXTRACTOR)
    import yaml
    from src.article_io import SectionConfig, _first_match_offset
    cfg = yaml.safe_load(open(os.path.join(EXTRACTOR, "config", "default.yaml")))
    sc = SectionConfig.from_dict(cfg["sections"])
    st = dict(l.rstrip("\n").split("\t") for l in list(open(out("a2_article_status.tsv")))[1:])
    ids = sorted(p for p, s in st.items() if s not in ("prefilter_skip", "gate_reject"))
    vers = first_version_files()
    a, b = int(sys.argv[2]), int(sys.argv[3])
    with open(out(f"_trunc_{a}.jsonl"), "w") as fo:
        for p in ids[a:b]:
            v = min(vers.get(p, [1])); f = os.path.join(TXT_DIR, f"{p}.{v}.txt")
            if not os.path.exists(f): fo.write(json.dumps({"p": p, "missing": 1}) + "\n"); continue
            t = open(f, encoding="utf-8", errors="replace").read()
            s0 = _first_match_offset(sc.body_start, t); nohdr = s0 is None
            if s0 is None: s0 = len(t) // 2
            e0 = _first_match_offset(sc.body_end, t, start=s0 + 1) or len(t)
            fo.write(json.dumps({"p": p, "s": st[p], "len": len(t[s0:e0].strip()), "nohdr": nohdr, "cap": sc.max_chars}) + "\n")
    print(len(ids), a, b)

elif sys.argv[1] == "trunc_summary":
    recs = {}
    for f in glob.glob(out("_trunc_*.jsonl")):
        for l in open(f):
            try: d = json.loads(l); recs[d["p"]] = d
            except Exception: pass
    cap = next(d["cap"] for d in recs.values() if "cap" in d)
    ok = [d for d in recs.values() if "len" in d]
    res = {"gate_passed_articles_checked": len(ok), "unchecked(missing file)": sum("missing" in d for d in recs.values()),
           "body_cap_chars": cap,
           "bodies_over_cap": sum(d["len"] > cap for d in ok),
           "bodies_over_cap_among_record_yielding": sum(d["len"] > cap and d["s"] == "yielded_records" for d in ok),
           "bodies_over_50000": sum(d["len"] > 50000 for d in ok),
           "no_section_header_found(back-half fallback)": sum(d["nohdr"] for d in ok)}
    print(json.dumps(res, indent=1)); json.dump(res, open(out("a2_truncation.json"), "w"), indent=1)
