import collections
import matplotlib.pyplot as plt
from fig_common import *

LABELS = [("drought", "Drought tolerance"), ("salt", "Salt / salinity tolerance"), ("cold", "Cold / freezing tolerance"),
          ("heat", "Heat tolerance"), ("disease", "Disease / pathogen resistance"), ("pest", "Pest / nematode resistance"),
          ("herbicide", "Herbicide resistance"), ("yield", "Yield / grain / biomass"), ("flowering", "Flowering / development"),
          ("pigment", "Pigment / colour"), ("oilseed", "Oil / seed quality"), ("nutrient", "Nutrient / metal homeostasis"),
          ("photo", "Photosynthesis"), ("repro", "Reproduction / fertility"), ("growth", "Growth / plant architecture"),
          ("root", "Root system"), ("germination", "Germination / dormancy"), ("senescence", "Senescence / stay-green")]
NAME = dict(LABELS)
rel = release()
tc = collections.Counter(); single = multi = 0
for r in rel:
    a = [t for t in r.get("_t") or [] if t in NAME]
    tc.update(a)
    if len(a) == 1:
        single += 1
    elif len(a) > 1:
        multi += 1
traited = single + multi
pairs = [(NAME[k], v) for k, v in sorted(tc.items(), key=lambda x: (-x[1], NAME[x[0]]))]

fig = plt.figure(figsize=(6.5, 5.2), constrained_layout=True)
gs = fig.add_gridspec(1, 2, width_ratios=[1.42, 1.18], wspace=0.34)
axA = fig.add_subplot(gs[0, 0])
labels = [l for l, _ in pairs]; vals = [v for _, v in pairs]; y = list(range(len(labels)))
axA.barh(y, vals, color=TEAL, edgecolor=TEAL_D, linewidth=0.6, height=0.72, zorder=3)
axA.set_yticks(y); axA.set_yticklabels(labels, fontsize=9); axA.invert_yaxis()
axA.xaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); axA.set_axisbelow(True)
mx = max(vals)
for yi, v in zip(y, vals):
    axA.text(v + mx * 0.012, yi, f"{v:,}", va="center", ha="left", fontsize=8.5, color=LBL, zorder=4)
axA.set_xlim(0, mx * 1.15); axA.set_xlabel("Number of records")
axB = fig.add_subplot(gs[0, 1])
xs = [0, 1.6]; vals2 = [single, multi]
axB.bar(xs, vals2, color=[TEAL, ORANGE], edgecolor=[TEAL_D, ORANGE_D], linewidth=0.6, width=0.66, zorder=3)
axB.set_xticks(xs); axB.set_xticklabels(["Single\ntrait", "Multiple\ntraits (≥2)"], fontsize=8.5); axB.set_xlim(-0.85, 2.45)
axB.yaxis.grid(True, color=GRID, linewidth=0.7, zorder=0); axB.set_axisbelow(True)
for x, v in zip(xs, vals2):
    axB.text(x, v + traited * 0.015, f"{v:,}\n{100 * v / traited:.1f}%", ha="center", va="bottom", fontsize=8.5, color=LBL, zorder=4)
axB.set_ylim(0, max(vals2) * 1.22); axB.set_ylabel("Number of records")
add_letters(fig, [([axA], [(axA, "A")]), ([axB], [(axB, "B")])], rect=(0, 0, 1, 0.962))
print(save(fig, "Figure5.png"))
print(pairs); print("single", single, "multi", multi, "traited", traited)
