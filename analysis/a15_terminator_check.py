"""Check named terminators against source text and write correction candidates."""
import re, csv, json, hashlib, collections
from xml.etree import ElementTree as ET
from common import *
csv.field_size_limit(10**9)
TABLE = os.environ.get("PBA_TABLE", RAW_TABLE)
FIXES = os.path.join(os.path.dirname(TABLE), "data", "terminator_corrections.tsv")
SLOT = {"NOS terminator": r"\bnos[\s-]?t\b|\btnos\b|\bnost\b|nopaline.*?termin|nos termin",
        "OCS terminator": r"\bocs[\s-]?t\b|\bocst\b|octopine.*?termin",
        "35S terminator": r"\bt35s\b|35s[\s-]?termin|camv.*?termin"}
Q = r"3\s*['′’`]"; PA = r"poly\s?\(?a"
TEXT = {"NOS terminator": rf"\bnos\s*[-–]?\s*({Q}|ter\b|term|{PA}|t\b)|\bt[-_ ]?nos\b|\bnost\b|nos[-\s]{{0,2}}(gene\s)?terminat|terminat\w*\s(of\s)?(the\s)?(\w+\s){{0,3}}nos\b|nopaline[\s-]synthase(\s\(?nos\)?)?(\sgene)?\s{{0,2}}[,(]?\s?(\w+\s){{0,3}}(terminat|{PA}|{Q})|(terminat\w*|{PA}\)?\w*|{Q}\s?\w*)\s(\w+\s){{0,5}}nopaline[\s-]synthase",
        "OCS terminator": rf"\bocs\s*[-–]?\s*({Q}|ter\b|term|{PA}|t\b)|\bt[-_ ]?ocs\b|\bocst\b|octopine[\s-]synthase(\s\(?ocs\)?)?(\sgene)?\s{{0,2}}[,(]?\s?(\w+\s){{0,3}}(terminat|{PA}|{Q})|(terminat\w*|{PA}\)?\w*|{Q}\s?\w*)\s(\w+\s){{0,5}}octopine[\s-]synthase|terminat\w*\s(of\s)?(the\s)?(\w+\s){{0,3}}ocs\b",
        "35S terminator": rf"35s\s*[-–]?\s*({Q}|ter\b|term|{PA}|t\b)|\bt[-_ ]?35s\b|terminat\w*\s(of\s)?(the\s)?(\w+\s){{0,3}}(camv\s?)?35s|camv\s(35s\s)?(terminat|{PA})"}
SLOT = {k: re.compile(v, re.I) for k, v in SLOT.items()}; TEXT = {k: re.compile(v, re.I) for k, v in TEXT.items()}
sha = lambda r: hashlib.sha1("\x1f".join((r.get(c) or "").strip() for c in COLS).encode("utf-8")).hexdigest()[:12]
xml = {}
for fn in os.listdir(XML_DIR):
    if fn.endswith(".xml"): xml.setdefault(fn.split(".")[0], []).append(fn)
_text = {}
def article_text(p):
    if p not in _text:
        f = sorted(xml.get(p, []))
        _text[p] = " ".join(" ".join(ET.parse(os.path.join(XML_DIR, f[0])).getroot().itertext()).split()) if f else None
    return _text[p]
rows = list(csv.DictReader(open(TABLE, encoding="utf-8"), delimiter="\t"))
out_rows = []; n = collections.Counter()
for r in rows:
    g = (r.get("gene_construct") or "").strip(); p = (r.get("pmcid") or "").strip(); units = []; hit = set()
    for u in g.split("---"):
        f = [x for x in u.replace("::", "-").split("-") if x.strip()]
        m = re.match(r"^(.*-)([^-]*)$", u, re.S)
        if len(f) >= 3 and m:
            tok = m.group(2).strip()
            for k, rx in SLOT.items():
                if rx.search(tok):
                    t = article_text(p); n[k, "terminator slots with this name"] += 1
                    if t is not None and not TEXT[k].search(t):
                        u = m.group(1) + m.group(2).replace(tok, "NA"); hit.add(k)
                    break
        units.append(u)
    if hit:
        out_rows.append([sha(r), p, g, "---".join(units), "; ".join(sorted(hit)), "terminator not named in the article text (body, tables, figure legends); set to NA"])
        for k in hit: n[k, "records corrected"] += 1
write_tsv(FIXES, ["row_sha1", "pmcid", "construct_before", "construct_after", "terminator", "reason"], out_rows)
res = {"records_corrected": len(out_rows), "articles_read": sum(v is not None for v in _text.values()), "by_class": {f"{k}: {w}": v for (k, w), v in sorted(n.items())}}
print(json.dumps(res, indent=1)); json.dump(res, open(out("a15_terminator_check.json"), "w"), indent=1)
