import csv, json, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS = os.environ.get("PBA_RESULTS", os.path.join(REPO, "results"))
ATLAS = os.environ.get("PBA_ATLAS", os.path.join(REPO, "atlas"))
OUTDIR = os.environ.get("PBA_FIGURES", os.path.join(REPO, "outputs", "figures"))

TEAL = "#2b7a78"; TEAL_D = "#1f5d5b"; ORANGE = "#cf8a32"; ORANGE_D = "#a96a1f"
SLATE = "#475569"; SLATE_D = "#2f3a4a"; GREYB = "#9aa3ad"
INK = "#23272b"; GRID = "#e4e7ea"; LBL = "#3d444b"
POP = "Poplar (Populus spp.)"

plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Liberation Sans", "Arial", "Nimbus Sans"],
                     "font.size": 10, "mathtext.fontset": "custom", "mathtext.rm": "Liberation Sans",
                     "mathtext.it": "Liberation Sans:italic", "axes.edgecolor": "#5b6470", "axes.linewidth": 0.8,
                     "axes.spines.top": False, "axes.spines.right": False, "text.color": INK,
                     "axes.labelcolor": INK, "xtick.color": "#5b6470", "ytick.color": "#5b6470",
                     "xtick.major.size": 2.6, "ytick.major.size": 0, "xtick.major.width": 0.8,
                     "savefig.dpi": 600, "figure.dpi": 150})

def release():
    return json.load(open(os.path.join(RESULTS, "release_annotated.json"), encoding="utf-8"))

def row_annotations():
    return json.load(open(os.path.join(ATLAS, "data", "row_annotations.json"), encoding="utf-8"))

def species_fix():
    fix = {}
    with open(os.path.join(ATLAS, "data", "species_corrections.tsv"), encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            a = (r.get("raw_species") or "").strip(); b = (r.get("corrected_species") or "").strip()
            if a and b:
                fix[a.lower()] = b
    return fix

_FIX = None
AUTH = (r"(?:L|Merr|Carr|Roth|Suk|Michx|Heynh|Dode|Swing|Swingle|Thunb|Mill|DC|Lam|Pers|Hook|Benth|Hance|"
        r"Maxim|Bunge|Franch|Kom|Nakai|Rehd|Schott|Steud|Walp|Wall|Sm|Ker)\.")

def norm(s):
    global _FIX
    if _FIX is None:
        _FIX = species_fix()
    s = s.strip()
    s = _FIX.get(s.lower(), s)
    if re.match(r"populus\b", s, re.I):
        return POP
    s = re.sub(r"\([^)]*\)", " ", s); s = re.sub(r"'[^']*'", " ", s)
    s = s.replace("×", " "); s = re.sub(r"\s+[xX]\s+", " ", s)
    s = re.sub(r"\s+(var|subsp|ssp|cv|f|sp|spp)\.?(?:\s.*|$)", "", s, flags=re.I)
    s = re.sub(r"\s+" + AUTH + r".*$", "", s)
    t = [x for x in s.split() if x]
    if len(t) >= 2 and t[0][:1].isupper():
        g = {"Physcomitrella": "Physcomitrium"}.get(t[0], t[0])
        return f"{g} {t[1].rstrip('.,;')}"
    return " ".join(t) if t else s

def hosts(r):
    return {norm(x) for x in (r["plant_species"] or "").split(",") if x.strip() and x.strip().upper() != "NA"}

def add_letters(fig, groups, rect=(0.004, 0, 0.984, 0.962), dy=0.006):
    try:
        fig.get_layout_engine().set(rect=rect)
    except Exception:
        pass
    fig.canvas.draw(); r = fig.canvas.get_renderer()
    lx = lambda ax: ax.get_tightbbox(r).transformed(fig.transFigure.inverted()).x0
    for ref_axes, items in groups:
        x = max(0.001, min(lx(a) for a in ref_axes) - 0.006)
        for ax, L in items:
            fig.text(x, min(0.994, ax.get_position().y1 + dy), L, fontsize=12, fontweight="bold",
                     ha="left", va="bottom", color=INK)

def save(fig, name):
    os.makedirs(OUTDIR, exist_ok=True)
    p = os.path.join(OUTDIR, name)
    fig.savefig(p)
    return p
