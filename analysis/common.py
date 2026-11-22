import os, json, re, csv
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUTS = os.environ.get("PBA_INPUTS", os.path.join(REPO, "inputs"))
RES = os.environ.get("PBA_RESULTS", os.path.join(REPO, "results"))
PKG = os.environ.get("PBA_OUTPUTS", os.path.join(REPO, "outputs"))
ATLAS = os.environ.get("PBA_ATLAS", os.path.join(REPO, "atlas"))
EXTRACTOR = os.path.join(REPO, "extraction")
DATA_DIR = os.path.join(REPO, "data")
PORTAL_HTML = os.environ.get("PBA_PORTAL_HTML", os.path.join(ATLAS, "plant_bioeng_atlas.html"))
RAW_TABLE = os.path.join(ATLAS, "plant_bioeng_table.tsv")
PREVIOUS_COUNTRY = os.path.join(INPUTS, "submitted_figure1c_country_assignment.json")
RUN_LOG = os.path.join(INPUTS, "extraction", "extraction_run.jsonl")
EVIDENCE_LOG = os.path.join(INPUTS, "extraction", "plant_bioeng_table.tsv.evidence.jsonl")
RUN_PROGRESS = os.path.join(INPUTS, "extraction", "plant_bioeng_table.tsv.progress")
RUN_TABLE = os.path.join(INPUTS, "extraction", "plant_bioeng_table.tsv")
TXT_DIR = os.path.join(INPUTS, "corpus", "TXT_files")
XML_DIR = os.path.join(INPUTS, "corpus", "XML_files")
DECISIONS = os.path.join(INPUTS, "screening", "decisions_all.csv")
TXT_IDS = os.path.join(INPUTS, "screening", "txt_pmcids.txt")
XML_IDS = os.path.join(INPUTS, "screening", "xml_pmcids.txt")
for _d in ("02_Supplementary",):
    os.makedirs(os.path.join(PKG, _d), exist_ok=True)
COLS = ["plant_species","genes","modification_type","engineering_type","gene_construct",
        "phenotype","mechanism","doi","pmcid"]

def out(name): os.makedirs(RES, exist_ok=True); return os.path.join(RES, name)

def portal_payload(path=PORTAL_HTML):
    h = open(path, encoding="utf-8").read()
    m = re.search(r"META\s*=\s*(\{)", h); s = m.start(1); d = 0
    for j in range(s, len(h)):
        if h[j] == "{": d += 1
        elif h[j] == "}":
            d -= 1
            if d == 0: break
    meta = json.loads(h[s:j+1])
    i = h.index("const DATA=JSON.parse", 30000); a = i + len("const DATA=JSON.parse('"); k = a
    while True:
        k = h.index("'", k); n = 0; p = k - 1
        while h[p] == "\\": n += 1; p -= 1
        if n % 2 == 0: break
        k += 1
    data = json.loads(re.sub(r"\\(['\\\\])", lambda m: m.group(1), h[a:k]))
    return data, meta

def load_release():
    p = out("release_annotated.json")
    if os.path.exists(p): return json.load(open(p))
    data, _ = portal_payload(); json.dump(data, open(p, "w")); return data

def first_version_files(ids_path=TXT_IDS):
    v = {}
    for l in open(ids_path):
        l = l.strip()
        if l: a, n = l.split("."); v.setdefault(a, []).append(int(n))
    return v

def write_tsv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n"); w.writerow(header); w.writerows(rows)

MODGROUPS = [
 ("Gene editing (CRISPR / TALEN / ZFN)", r"crispr|\bcas9\b|\bcas12|\bcas13|base ?edit|prime ?edit|talen|zinc.?finger|genome ?edit|gene[- ]?edit|targeted mutagenesis"),
 ("Overexpression / ectopic expression", r"overexpress|over-express|over express|ectopic|constitutive express|gain-of-function"),
 ("Heterologous / foreign-gene expression", r"heterologous|foreign gene|exogenous|transgenic express|transformation"),
 ("Complementation", r"complementation|complement"),
 ("RNAi / silencing", r"\brnai\b|antisense|amirna|\bsirna\b|hairpin|silenc"),
 ("Knockout / knockdown", r"knock-?\s?out|knock-?\s?down"),
 ("Mutant / point mutation", r"mutant|mutagenesis|point mutation|substitution|allele"),
 ("Promoter / reporter / localisation", r"promoter|reporter|expression analysis|localization|localisation")]
_MG = [(lab, re.compile(rx, re.I)) for lab, rx in MODGROUPS]
def mod_group(m):
    for lab, rx in _MG:
        if rx.search(m or ""): return lab
    return "Other / unclassified"
