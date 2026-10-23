"""Find legend swatch boxes of a scanned sheet in a column band and sample their colour.
usage: swatch_scan.py <jpg> <x0> <x1> <y0> <y1> [min_h max_h]
x0..x1 must lie INSIDE every box of the column (boxes may drift with scan skew). Border rows =
rows where > 50 % of x0..x1 is dark (L < 100); printed index glyphs darken only part of a row,
so they do not split a box. Boxes = runs between borders min_h..max_h px tall (gaps between
boxes are shorter). Colour = median of the interior's non-dark pixels.
Prints: y_top y_bottom y_centre #hex"""
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
img = sys.argv[1]
x0, x1, y0, y1 = (int(v) for v in sys.argv[2:6])
min_h, max_h = (int(sys.argv[6]), int(sys.argv[7])) if len(sys.argv) > 7 else (60, 130)
from jpg_to_polygons import load_rgb   # CMYK scans through their ICC profile, as the extraction sees them
im = load_rgb(img)[y0:y1, x0:x1].astype(int)
L = im.mean(axis=2)
border = (L < 100).mean(axis=1) > 0.5
ys = np.flatnonzero(border)
for a, b in zip(ys[:-1], ys[1:]):
    h = b - a
    if not (min_h <= h <= max_h):
        continue
    inner = im[a + 5:b - 4, 4:-4].reshape(-1, 3)
    inner = inner[inner.mean(axis=1) >= 100]
    med = np.median(inner, axis=0).astype(int)
    print(a + y0, b + y0, (a + b) // 2 + y0, '#%02x%02x%02x' % tuple(med))
