import collections, csv, os
import matplotlib.pyplot as plt
from fig_common import *

rel = release()
year = {}
for r in rel:
    if r.get("_y"):
        year.setdefault(r["pmcid"], r["_y"])
fig1a = collections.Counter(year.values())

sp_p = collections.defaultdict(set)
for r in rel:
    for s in hosts(r):
        sp_p[s].add(r["pmcid"])
rank = sorted(((s, len(p)) for s, p in sp_p.items()), key=lambda x: (-x[1], x[0]))
cut = [i for i, (s, _) in enumerate(rank) if s == POP][0]
fig1b = rank[:cut + 6]

with open(os.path.join(RESULTS, "a8_country_by_paper.tsv"), encoding="utf-8") as f:
    ctry = collections.Counter(r["first_author_country"] for r in csv.DictReader(f, delimiter="\t") if r["first_author_country"])
fig1c = [("United Kingdom" if c == "UK" else c, n) for c, n in ctry.most_common(14)]

fig = plt.figure(figsize=(6.5, 5.2), constrained_layout=True)
gs = fig.add_gridspec(2, 2, height_ratios=[0.82, 1.25], hspace=0.10, wspace=0.20)
axA = fig.add_subplot(gs[0, :])
yrs = sorted(fig1a)
bars = axA.bar(yrs, [fig1a[y] for y in yrs], color=TEAL, edgecolor=TEAL_D, linewidth=0.5, width=0.78, zorder=3)
i26 = yrs.index(2026)
bars[i26].set_color("#9fc3c2"); bars[i26].set_hatch("////"); bars[i26].set_edgecolor(TEAL_D)
axA.yaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); axA.set_axisbelow(True)
axA.set_ylabel("Research articles"); axA.set_xticks([2000, 2005, 2010, 2015, 2020, 2025])
axA.set_xlim(1999.2, 2026.8); axA.margins(x=0)

def barh(ax, pairs, base, based, italic):
    labels = [s for s, _ in pairs]; vv = [v for _, v in pairs]; y = list(range(len(labels)))
    ax.barh(y, vv, color=base, edgecolor=based, linewidth=0.6, height=0.72, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels(["Populus" if s == POP else s for s in labels]); ax.invert_yaxis()
    if italic:
        for t in ax.get_yticklabels():
            t.set_fontstyle("italic")
    ax.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); ax.set_axisbelow(True)
    mx = max(vv)
    for yi, v in zip(y, vv):
        ax.text(v + mx * 0.012, yi, f"{v:,}", va="center", ha="left", fontsize=9, color=LBL, zorder=4)
    ax.set_xlim(0, mx * 1.14); ax.set_xlabel("Research articles")

axB = fig.add_subplot(gs[1, 0]); barh(axB, fig1b, TEAL, TEAL_D, True)
axC = fig.add_subplot(gs[1, 1]); barh(axC, fig1c, SLATE, SLATE_D, False)
add_letters(fig, [([axA, axB], [(axA, "A"), (axB, "B")]), ([axC], [(axC, "C")])])
print(save(fig, "Figure1.png"))
print("A", {y: fig1a[y] for y in yrs})
print("B", fig1b)
print("C", fig1c)
