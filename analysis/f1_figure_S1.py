import json, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from common import *
a1 = json.load(open(out("a1_screening_funnel.json")))
f = lambda n: f"{n:,}"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Liberation Sans", "Arial", "DejaVu Sans"], "font.size": 10})
fig = plt.figure(figsize=(6.5, 7.6)); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 100); ax.set_ylim(0, 117); ax.axis("off")
TEAL, SLATE, ORANGE, INK = "#2b7a78", "#475569", "#cf8a32", "#23272b"
def box(x, y, w, h, title, body, col):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2", fc="white", ec=col, lw=1.4))
    ax.text(x + 1.5, y + h - 2.2, title, fontsize=10.5, fontweight="bold", color=col, va="top")
    ax.text(x + 1.5, y + h - 6.6, body, fontsize=10, color=INK, va="top", linespacing=1.35)
def arrow(x, y1, y2): ax.annotate("", xy=(x, y2), xytext=(x, y1), arrowprops=dict(arrowstyle="-|>", color="#5b6470", lw=1.2))
def side(x, y, txt): ax.text(x, y, txt, fontsize=10, color=SLATE, va="center", linespacing=1.3)
box(3, 101, 60, 13, "PMC Open Access Subset", f"{f(a1['article_versions_screened'])} article versions\n({f(a1['distinct_accessions_screened'])} accessions)", SLATE)
arrow(33, 101, 95.5); side(66, 106, "Deterministic screen")
box(3, 82, 60, 13, "Retained by screening", f"{f(a1['versions_retained'])} versions = {f(a1['distinct_accessions_retained'])} accessions ({a1['retained_pct']:.2f}%)\n{f(a1['accessions_with_more_than_one_retained_version'])} accessions with >1 version; earliest version used", TEAL)
arrow(33, 82, 76.5)
box(3, 50, 60, 26, "Extraction step", "Regex pre-filter\nModel gate\nRecord extraction", TEAL)
side(66, 63, "Body preparation\nLength limit\nModel input")
arrow(33, 50, 44.5)
box(3, 25, 60, 19.5, "Evidence-quotation check", "Continuous match or segment fallback", ORANGE)
arrow(33, 25, 19.5)
box(3, 1.5, 60, 18, "Released dataset", "Structured plant-bioengineering records", SLATE)
side(66, 11, "Post-extraction quality control")
fig.savefig(os.path.join(PKG, "02_Supplementary", "Figure_S1_processing_flow.png"), dpi=600); print("ok")
