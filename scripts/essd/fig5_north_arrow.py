#!/usr/bin/env python
"""North arrow on the Mackenzie detail of the A0 map (Fig. 5). The detail keeps the orientation of the sheet (EPSG:6931,
north towards the pole at the sheet centre); at its centre, 135 W, north points to the lower right at 45 degrees.
Draws on the arrow-free copy, so it can be re-run.
usage: fig5_north_arrow.py CLEAN.jpg OUT.jpg"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

SRC, OUT = sys.argv[1:3]
im = Image.open(SRC).convert('RGB')
W, H = im.size
d = ImageDraw.Draw(im)
INK = (63, 95, 120)                      # the tone of the sea labels
LON = -135.0                             # longitude at the centre of the detail
ang = math.radians(LON)
ux, uy = -math.sin(ang), math.cos(ang)   # north in map coordinates (y up), towards the pole at (0, 0)
ux, uy = ux, -uy                         # image coordinates (y down)
L, head = 0.055 * W, 0.014 * W
x0, y0 = 0.885 * W, 0.865 * H            # open sea in the lower right
x1, y1 = x0 + ux * L, y0 + uy * L
d.line([(x0, y0), (x1 - ux * head * 0.6, y1 - uy * head * 0.6)], fill=INK, width=max(3, round(W / 450)))
px, py = -uy, ux                         # perpendicular
d.polygon([(x1, y1), (x1 - ux * head + px * head * 0.45, y1 - uy * head + py * head * 0.45),
           (x1 - ux * head - px * head * 0.45, y1 - uy * head - py * head * 0.45)], fill=INK)
font = None
for f in ('pala.ttf', 'georgia.ttf'):
    p = os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts', f)
    if os.path.exists(p):
        font = ImageFont.truetype(p, round(0.024 * W))
        break
tx, ty = x1 + ux * 0.020 * W, y1 + uy * 0.020 * W
d.text((tx, ty), 'N', fill=INK, font=font, anchor='mm')
im.save(OUT, quality=92)
print(f'{OUT}: {W} x {H}, arrow {x0:.0f},{y0:.0f} -> {x1:.0f},{y1:.0f}')
