"""Compose Figure 8 from the portal panels captured by figure8_capture.js.

Output: 6.35 in wide at 600 dpi (3,810 px), the column width used by the other manuscript figures,
with bold panel letters in the style of Figures 1-5 (Liberation Sans Bold, 12 pt).
Usage: python figure8_compose.py <panel_dir> <out.png>
"""
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

D, OUT = sys.argv[1], sys.argv[2]
DPI = 600
W = round(6.35 * DPI)            # 3810 px
ML = 140                         # left margin for panel letters
GAP_V, GAP_H = 70, 150           # vertical gap between rows, horizontal gap between D and E
INNER = W - ML
FRAME = "#c9d1d6"
LETTER = ImageFont.truetype("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", 100)  # 12 pt at 600 dpi


def load(name):
    return Image.open(f"{D}/{name}").convert("RGB")


def fit_w(im, w):
    return im.resize((w, round(im.height * w / im.width)), Image.LANCZOS)


def content_box(im, pad, thr=246):
    a = np.asarray(im.convert("L"))
    ys, xs = np.where(a < thr)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    return (max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y1 + pad))


A = fit_w(load("A_header.png"), INNER)
B = fit_w(load("B_browse.png"), INNER)
C = fit_w(load("C_record.png"), INNER)
half = (INNER - GAP_H) // 2
Dg = fit_w(load("D_gene.png"), half)
k = half / load("D_gene.png").width                     # same CSS scale for panel E as for panel D
E_full = load("E_graph_full.png")
E_full = E_full.crop((18, 18, E_full.width - 18, E_full.height - 18))   # drop the card's rounded border
Eg = E_full.crop(content_box(E_full, pad=60, thr=200))                # highlighted sub-graph only
leg = load("E_legend.png")
leg = leg.resize((round(leg.width * k), round(leg.height * k)), Image.LANCZOS)
target_h = max(Dg.height, 900) - leg.height - 24
s_e = min(half / Eg.width, target_h / Eg.height)
Eg = Eg.resize((round(Eg.width * s_e), round(Eg.height * s_e)), Image.LANCZOS)
leg_bg = Image.new("RGB", (half, leg.height + 24), "white")
leg_bg.paste(leg, (12, 12))
E = Image.new("RGB", (half, Eg.height + leg_bg.height), "white")
E.paste(Eg, ((half - Eg.width) // 2, 0))
E.paste(leg_bg, (0, Eg.height))
row4 = max(Dg.height, E.height)
H = A.height + B.height + C.height + row4 + 3 * GAP_V
fig = Image.new("RGB", (W, H), "white")
dr = ImageDraw.Draw(fig)


def put(im, x, y, letter=None, lx=None):
    fig.paste(im, (x, y))
    dr.rectangle((x - 1, y - 1, x + im.width, y + im.height), outline=FRAME, width=3)
    if letter:
        dr.text((lx if lx is not None else 0, y - 8), letter, font=LETTER, fill="#23272b")


y = 0
put(A, ML, y, "A"); y += A.height + GAP_V
put(B, ML, y, "B"); y += B.height
dr.line((ML, y, ML + INNER, y), fill="white", width=2)
put(C, ML, y, "C"); y += C.height + GAP_V
put(Dg, ML, y, "D")
put(E, ML + half + GAP_H, y, "E", lx=ML + half + GAP_H - 95)
fig.save(OUT, dpi=(DPI, DPI), optimize=True)
print(f"{W} x {H} px = {W / DPI:.2f} x {H / DPI:.2f} in at {DPI} dpi")
