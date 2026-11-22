import sys, json, glob, collections, os, re
from lxml import etree
from common import *

def text(el): return re.sub(r"\s+", " ", "".join(el.itertext())).strip() if el is not None else ""

def scan(p, v):
    f = os.path.join(XML_DIR, f"{p}.{v}.xml")
    raw = open(f, "rb").read()
    end = raw.find(b"</front>")
    front_xml = raw[raw.find(b"<front"):end + 8] if end > 0 else b""
    art = re.search(rb'<article[^>]*article-type="([^"]+)"', raw[:5000])
    rec = {"p": p, "v": v, "article_type": art.group(1).decode() if art else None}
    try:
        fr = etree.fromstring(front_xml, etree.XMLParser(recover=True, huge_tree=True))
    except Exception as e:
        rec["parse_error"] = str(e); return rec
    rec["related"] = [r.get("related-article-type") for r in fr.iter("related-article")]
    doi = [a for a in fr.iter("article-id") if a.get("pub-id-type") == "doi"]
    rec["doi"] = text(doi[0]) if doi else None
    affs = {}
    for a in fr.iter("aff"):
        c = a.find(".//country")
        lab = a.find("label")
        t = text(a)
        if lab is not None and lab.text and t.startswith(lab.text.strip()): t = t[len(lab.text.strip()):].strip()
        affs[a.get("id") or f"_noid{len(affs)}"] = {"text": t, "country_tag": text(c) if c is not None else None}
    authors = []
    for c in fr.iter("contrib"):
        if c.get("contrib-type") not in (None, "author"): continue
        rids = [x.get("rid") for x in c.iter("xref") if x.get("ref-type") == "aff"]
        inner = [text(a) for a in c.iter("aff")]
        authors.append({"rids": rids, "inner_aff": inner, "corresp": c.get("corresp") == "yes", "collab": c.find(".//collab") is not None})
    rec["affs"] = affs; rec["authors"] = authors
    return rec

if sys.argv[1] == "scan":
    rel = load_release(); ids = sorted({r["pmcid"] for r in rel}); vers = first_version_files(XML_IDS)
    a, b = int(sys.argv[2]), int(sys.argv[3])
    with open(out(f"_xml_{a}.jsonl"), "w") as fo:
        for p in ids[a:b]:
            v = min(vers[p]); r = scan(p, v); r["n_versions_retained"] = len(vers[p])
            fo.write(json.dumps(r) + "\n")
elif sys.argv[1] == "summary":
    X = {}
    for f in glob.glob(out("_xml_*.jsonl")):
        for l in open(f):
            d = json.loads(l); X[d["p"]] = d
    json.dump(X, open(out("a3_xml_metadata.json"), "w"))
    rel = load_release()
    rec_type = collections.Counter(X[r["pmcid"]]["article_type"] for r in rel)
    no_doi_xml = sorted(p for p, d in X.items() if not d.get("doi"))
    rel_doi = {}
    for r in rel: rel_doi.setdefault(r["pmcid"], set()).add(r["doi"])
    mismatch = sorted(p for p, ds in rel_doi.items() if X[p].get("doi") and any(d and d.lower() != X[p]["doi"].lower() for d in ds))
    raw = list(csv.reader(open(RAW_TABLE), delimiter="\t"))[1:]
    raw_mis = [(r[8], r[7], X[r[8]]["doi"]) for r in raw if X[r[8]].get("doi") and r[7] not in ("", "NA") and r[7].lower() != X[r[8]]["doi"].lower()]
    res = {"papers": len(X), "papers_with_more_than_one_retained_version": sum(d["n_versions_retained"] > 1 for d in X.values()),
           "article_type_by_paper": dict(collections.Counter(d["article_type"] for d in X.values())),
           "article_type_by_record": dict(rec_type),
           "related_article_links": dict(collections.Counter(t for d in X.values() for t in d.get("related", []))),
           "papers_with_retraction_link": sorted(p for p, d in X.items() if any("retract" in (t or "") for t in d.get("related", []))),
           "papers_with_expression_of_concern": sorted(p for p, d in X.items() if "expression-of-concern" in d.get("related", [])),
           "papers_without_DOI_in_XML": no_doi_xml,
           "records_without_DOI_in_release": sum(1 for r in rel if r["doi"] in ("", "NA")),
           "release_records_whose_DOI_differs_from_XML": sum(1 for r in rel if r["doi"] and X[r["pmcid"]].get("doi") and r["doi"].lower() != X[r["pmcid"]]["doi"].lower()),
           "raw_extracted_DOIs_differing_from_XML(records)": len(raw_mis), "raw_mismatch_papers": len({m[0] for m in raw_mis})}
    print(json.dumps({k: v for k, v in res.items()}, indent=1)); json.dump(res, open(out("a3_identifiers_and_article_types.json"), "w"), indent=1)
    write_tsv(out("a3_raw_DOI_corrections.tsv"), ["pmcid", "extracted_doi", "doi_in_JATS_XML"], sorted(set(raw_mis)))
