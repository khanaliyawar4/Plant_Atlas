import collections, os, re
import matplotlib.pyplot as plt
from fig_common import *

RULE = os.environ.get("PBA_COMPLETENESS_RULE", "unit")
rel = release()

def fields(tu):
    return [x.strip() for x in tu.replace("::", "-").split("-") if x.strip()]

def flags_unit(c):
    hp = ht = True
    for tu in c.split("---"):
        f = fields(tu)
        if len(f) < 2:
            hp = ht = False
            continue
        if f[0].upper() == "NA":
            hp = False
        if len(f) < 3 or f[-1].upper() == "NA":
            ht = False
    return hp, ht

def flags_slot(c):
    return (not re.search(r"^\s*NA\s*-", c, re.I), not re.search(r"-\s*NA\s*$", c, re.I))

def flags(c):
    c = (c or "").strip()
    if c.lower() in {"", "na", "n/a", "none", "not reported", "nr"}:
        return False, False
    return flags_unit(c) if RULE == "unit" else flags_slot(c)

cnt = collections.Counter()
for r in rel:
    hp, ht = flags(r["gene_construct"])
    cnt["complete" if hp and ht else "promoter only" if hp else "terminator only" if ht else "neither"] += 1
comp, ponly, tonly, neither = cnt["complete"], cnt["promoter only"], cnt["terminator only"], cnt["neither"]
et = collections.Counter((r["engineering_type"] or "").strip() for r in rel)
single = et.get("single-gene engineering", 0); multi = et.get("multi-gene engineering", 0)

fig = plt.figure(figsize=(6.5, 5.2), constrained_layout=True)
gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.0], hspace=0.30)
axA = fig.add_subplot(gs[0, 0])
incomplete = ponly + tonly + neither; tot = comp + incomplete
axA.barh(1, comp, color=TEAL, edgecolor=TEAL_D, linewidth=0.6, height=0.6, zorder=3)
left = 0
for seg, c, cd, lab in [(ponly, ORANGE, ORANGE_D, "promoter only"), (neither, GREYB, "#6f7882", "neither specified"),
                        (tonly, SLATE, SLATE_D, "terminator only")]:
    axA.barh(0, seg, left=left, color=c, edgecolor=cd, linewidth=0.6, height=0.6, zorder=3, label=lab)
    left += seg
axA.set_yticks([1, 0]); axA.set_yticklabels(["Complete", "Incomplete"]); axA.set_ylim(-0.7, 1.7)
axA.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); axA.set_axisbelow(True)
axA.text(comp + tot * 0.012, 1, f"{comp:,}  ({100 * comp / tot:.1f}%)", va="center", ha="left", fontsize=9, color=LBL)
axA.text(incomplete + tot * 0.012, 0, f"{incomplete:,}  ({100 * incomplete / tot:.1f}%)", va="center", ha="left", fontsize=9, color=LBL)
axA.set_xlim(0, tot * 1.18); axA.set_xlabel("Number of records")
axA.legend(loc="lower right", fontsize=8.3, frameon=False, handlelength=1.2, borderaxespad=0.3, labelspacing=0.3)
axB = fig.add_subplot(gs[1, 0])
tot2 = single + multi
axB.barh(1, single, color=TEAL, edgecolor=TEAL_D, linewidth=0.6, height=0.6, zorder=3)
axB.barh(0, multi, color=ORANGE, edgecolor=ORANGE_D, linewidth=0.6, height=0.6, zorder=3)
axB.set_yticks([1, 0]); axB.set_yticklabels(["Single-gene", "Multi-gene"]); axB.set_ylim(-0.7, 1.7)
axB.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); axB.set_axisbelow(True)
axB.text(single + tot2 * 0.013, 1, f"{single:,}  ({100 * single / tot2:.1f}%)", va="center", ha="left", fontsize=9, color=LBL)
axB.text(multi + tot2 * 0.013, 0, f"{multi:,}  ({100 * multi / tot2:.1f}%)", va="center", ha="left", fontsize=9, color=LBL)
axB.set_xlim(0, tot2 * 1.24); axB.set_xlabel("Number of records")
add_letters(fig, [([axA], [(axA, "A")]), ([axB], [(axB, "B")])], rect=(0, 0, 1, 0.962), dy=0.010)
print(save(fig, "Figure4.png"))
print("rule", RULE, dict(cnt), "single", single, "multi", multi, "other", {k: v for k, v in et.items() if k not in ("single-gene engineering", "multi-gene engineering")})
