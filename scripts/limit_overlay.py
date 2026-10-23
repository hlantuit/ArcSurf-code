"""Crops along a mapping limit (<img>.limit.csv from mapping_limit.py) with the curve (red) and the
curve + margin (blue) drawn, for visual checking. usage: limit_overlay.py <img> <out.png> [margin=40] [a b]   (a, b: also draw the line x = a + b*y in green)"""
import sys

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
im = Image.open(sys.argv[1]).convert('RGB')
margin = int(sys.argv[3]) if len(sys.argv) > 3 else 40
lim = np.loadtxt(sys.argv[1] + '.limit.csv', delimiter=',', skiprows=1)
ab = (float(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else None
ys = np.linspace(lim[0, 0] + 150, lim[-1, 0] - 150, 6)
tiles = []
for yc in ys:
    xc = float(np.interp(yc, lim[:, 0], lim[:, 1]))
    box = (int(xc - 400), int(yc - 300), int(xc + 400), int(yc + 300))
    t = im.crop(box)
    d = ImageDraw.Draw(t)
    for k in range(len(lim) - 1):
        (ya, xa), (yb_, xb) = lim[k, :2], lim[k + 1, :2]
        d.line([(xa - box[0], ya - box[1]), (xb - box[0], yb_ - box[1])], fill=(255, 0, 0), width=3)
        d.line([(xa + margin - box[0], ya - box[1]), (xb + margin - box[0], yb_ - box[1])], fill=(0, 0, 255), width=2)
    if ab:
        d.line([(ab[0] + ab[1] * box[1] - box[0], 0), (ab[0] + ab[1] * box[3] - box[0], box[3] - box[1])], fill=(0, 160, 0), width=3)
        d.line([(ab[0] + ab[1] * box[1] + margin - box[0], 0), (ab[0] + ab[1] * box[3] + margin - box[0], box[3] - box[1])],
               fill=(255, 0, 255), width=2)
    d.text((10, 10), f'y={yc:.0f} x={xc:.0f}', fill=(0, 0, 0))
    tiles.append(t.resize((400, 300)))
out = Image.new('RGB', (1200, 600), 'white')
for k, t in enumerate(tiles):
    out.paste(t, ((k % 3) * 400, (k // 3) * 300))
out.save(sys.argv[2])
