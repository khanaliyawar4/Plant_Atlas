import collections, re
import matplotlib.pyplot as plt, matplotlib.ticker as mticker
from fig_common import *

rel = release()
ra = row_annotations()
NONGENE = re.compile(r"^(NA|N/A|none|unknown|n\.a\.|nd|null|-)$", re.I)
PARTWORD = re.compile(r"\b(promoter|terminator|intron|exon|enhancer|transposase|integrase|cassette|vector|plasmid|"
                      r"construct|arm|linker|epitope|antibody|nanobody|antigen|glycoprotein|capsid|peptide|domain|"
                      r"marker|reporter|element|sequence|region|fragment|library)\b", re.I)

def is_gene_symbol(g):
    g = (g or "").strip()
    if not g or NONGENE.search(g) or PARTWORD.search(g):
        return False
    if g.count("::") >= 2 or len(g.split()) > 3:
        return False
    return bool(re.search(r"[A-Za-z]", g))

spg = collections.defaultdict(set)
for r in rel:
    cs = (r.get("_cs") or [])[:1]
    if cs and is_gene_symbol(r.get("_g")):
        spg[POP if cs[0].startswith("Populus") else cs[0]].add(r["_g"])
spc = {s: len(g) for s, g in spg.items()}

REP = re.compile(r"(gfp|gus|yfp|cfp|rfp|dsred|mcherry|tdtomato|venus|luc|cas9|cas12|grna|sgrna|talen)", re.I)
TOOLS = set("uida nptii npt2 neo hpt hptii hph bar pat pmi aada ccdb pds p19 rola rolb rolc iaam iaah gateway ruby".split())
gsp = collections.defaultdict(set)
for r, a in zip(rel, ra):
    g = (r.get("_g") or "").strip().lower()
    if g and g != "na" and not (a.get("rep") or REP.search(g) or g in TOOLS):
        for s in hosts(r):
            gsp[g].add(s)

MODEL = ["Arabidopsis thaliana", "Nicotiana benthamiana", "Nicotiana tabacum", "Physcomitrium patens",
         "Marchantia polymorpha", "Chlamydomonas reinhardtii", "Brachypodium distachyon"]
CROP = ["Oryza sativa", "Triticum aestivum", "Zea mays", "Glycine max", POP, "Solanum lycopersicum",
        "Solanum tuberosum", "Gossypium hirsutum", "Hordeum vulgare", "Brassica napus", "Vitis vinifera",
        "Malus domestica", "Capsicum annuum", "Medicago truncatula"]
GD = {"cry1ac": "Cry1Ac", "cry1ab": "Cry1Ab", "npr1": "NPR1", "comt": "COMT", "chs": "CHS", "psy1": "PSY1",
      "rps4": "RPS4", "wrky40": "WRKY40", "lc": "Lc", "nfp": "NFP", "myb75": "MYB75", "bri1": "BRI1", "ap2": "AP2",
      "ahas": "AHAS"}
mod = sorted(((s, spc.get(s, 0)) for s in MODEL), key=lambda x: -x[1])
crp = sorted(((s, spc.get(s, 0)) for s in CROP), key=lambda x: -x[1])
top = sorted(((g, len(s)) for g, s in gsp.items()), key=lambda x: (-x[1], x[0]))[:12]
XLAB = "Number of distinct genes engineered in the species"

def sppanel(ax, pairs, bar, bard):
    labels = [s for s, _ in pairs]; vv = [v for _, v in pairs]; y = list(range(len(labels))); mx = max(vv)
    ax.barh(y, vv, color=bar, edgecolor=bard, linewidth=0.6, height=0.74, zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([r"$\mathit{Poplar}$ spp" if s == POP else s for s in labels], fontsize=10, fontstyle="italic")
    ax.invert_yaxis()
    for t, s in zip(ax.get_yticklabels(), labels):
        if s == POP:
            t.set_fontstyle("normal")
    ax.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); ax.set_axisbelow(True)
    for yi, v in zip(y, vv):
        ax.text(v + mx * 0.014, yi, f"{v:,}", va="center", ha="left", fontsize=9, color=LBL, zorder=4)
    ax.set_xlim(0, mx * 1.16)
    ax.xaxis.set_major_locator(mticker.MaxNLocator(nbins=6, integer=True))
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v)}"))
    ax.xaxis.set_minor_locator(mticker.NullLocator()); ax.tick_params(axis="x", labelsize=9)
    ax.set_xlabel(XLAB, fontsize=10)

fig = plt.figure(figsize=(6.5, 7.9), constrained_layout=True)
gs = fig.add_gridspec(3, 1, height_ratios=[7, 14, 12], hspace=0.16)
axA = fig.add_subplot(gs[0]); sppanel(axA, mod, TEAL, TEAL_D)
axB = fig.add_subplot(gs[1]); sppanel(axB, crp, ORANGE, ORANGE_D)
axC = fig.add_subplot(gs[2])
labels = [GD.get(g, g.upper()) for g, _ in top]; vv = [v for _, v in top]; y = list(range(len(labels)))
axC.barh(y, vv, color=SLATE, edgecolor=SLATE_D, linewidth=0.6, height=0.66, zorder=3)
axC.set_yticks(y); axC.set_yticklabels(labels, fontsize=10); axC.invert_yaxis()
for t in axC.get_yticklabels():
    t.set_fontstyle("italic")
axC.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); axC.set_axisbelow(True)
axC.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
for yi, v in zip(y, vv):
    axC.text(v + 0.09, yi, str(v), va="center", ha="left", fontsize=9, color=LBL, zorder=4)
axC.set_xlim(0, max(vv) * 1.12)
axC.set_xlabel("Number of plant species in which the gene was engineered", fontsize=10)
axC.tick_params(axis="x", labelsize=9)
add_letters(fig, [([axA, axB, axC], [(axA, "A"), (axB, "B"), (axC, "C")])], rect=(0.004, 0, 0.99, 0.975), dy=0.004)
print(save(fig, "Figure3.png"))
print("A", mod); print("B", crp); print("C", [(GD.get(g, g.upper()), v) for g, v in top])
print("C next", sorted(((g, len(s)) for g, s in gsp.items()), key=lambda x: (-x[1], x[0]))[12:18])
