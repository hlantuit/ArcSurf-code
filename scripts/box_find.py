"""Find legend swatch boxes anywhere in a region of a scanned sheet (matrix legends: age columns
x genesis rows, where boxes have no column order). A box = connected component of dark outline
pixels (L < 90) whose bounding box is w_min..w_max x h_min..h_max px; colour = median of the
interior's non-dark pixels (8 px in from the outline). Split boxes (a|b) come out as one wide box:
sample their halves with legend_from_centres.py xoff.
usage: box_find.py <jpg> x0,y0,x1,y1 [w_min w_max h_min h_max]
Prints: cx cy w h #hex  (full-res px, sorted by x then y)"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None
x0, y0, x1, y1 = (int(v) for v in sys.argv[2].split(','))
wmin, wmax, hmin, hmax = (int(v) for v in sys.argv[3:7]) if len(sys.argv) > 6 else (120, 380, 50, 110)
im = np.asarray(Image.open(sys.argv[1]).convert('RGB').crop((x0, y0, x1, y1))).astype(int)
dark = im.mean(axis=2) < 90
lab, n = ndi.label(dark, structure=np.ones((3, 3), bool))
out = []
for k, sl in enumerate(ndi.find_objects(lab), start=1):
    h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
    if not (wmin <= w <= wmax and hmin <= h <= hmax):
        continue
    comp = lab[sl] == k
    if comp.mean() > 0.5:                       # a filled dark blob, not an outline
        continue
    inner = im[sl[0].start + 8:sl[0].stop - 8, sl[1].start + 8:sl[1].stop - 8].reshape(-1, 3)
    inner = inner[inner.mean(axis=1) >= 55]
    if not len(inner):
        continue
    med = np.median(inner, axis=0).astype(int)
    cx, cy = x0 + (sl[1].start + sl[1].stop) // 2, y0 + (sl[0].start + sl[0].stop) // 2
    out.append((cx, cy, w, h, '#%02x%02x%02x' % tuple(med)))
for r in sorted(out):
    print(*r)
print(len(out), 'boxes', file=sys.stderr)
