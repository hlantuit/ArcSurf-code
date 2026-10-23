"""Detect FILLED legend swatches (matrix legends: boxes are coloured rectangles, outlines may be
faint) in a region of a scanned sheet and write a numbered overlay to transcribe them by eye.
A swatch = connected component of non-paper pixels (max-min channel > sat_min or mean < 225),
after an opening that removes text strokes, whose bbox is w_min..w_max x h_min..h_max px and which
fills > 80 % of its bbox. Colour = median of the component's interior (eroded 6 px), dark pixels
(< 70, glyphs) dropped. Split boxes (a|b) come out as one wide box or as two halves.
usage: swatch_overlay.py <jpg> x0,y0,x1,y1 <out_prefix> [w_min w_max h_min h_max] [scale]
Writes <out_prefix>.csv (n,x,y,w,h,fill) and <out_prefix>_<k>.png overlay tiles (numbers in red)."""
import sys

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None
x0, y0, x1, y1 = (int(v) for v in sys.argv[2].split(','))
out = sys.argv[3]
wmin, wmax, hmin, hmax = (int(v) for v in sys.argv[4:8]) if len(sys.argv) > 7 else (60, 260, 35, 110)
sc = float(sys.argv[8]) if len(sys.argv) > 8 else 0.75
img = Image.open(sys.argv[1]).convert('RGB').crop((x0, y0, x1, y1))
im = np.asarray(img).astype(int)
sat = im.max(axis=2) - im.min(axis=2)
m = (sat > 28) | (im.mean(axis=2) < 200)
m = ndi.binary_opening(m, structure=np.ones((9, 9), bool))
lab, n = ndi.label(m)
rows = []
for k, sl in enumerate(ndi.find_objects(lab), start=1):
    h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
    if not (wmin <= w <= wmax and hmin <= h <= hmax):
        continue
    comp = lab[sl] == k
    if comp.mean() < 0.8:
        continue
    inner = ndi.binary_erosion(comp, iterations=6)
    px = im[sl][inner]
    px = px[px.mean(axis=1) >= 70]
    if len(px) < 30:
        continue
    med = np.median(px, axis=0).astype(int)
    rows.append(dict(x=x0 + (sl[1].start + sl[1].stop) // 2, y=y0 + (sl[0].start + sl[0].stop) // 2, w=w, h=h,
                     fill='#%02x%02x%02x' % tuple(med)))
t = pd.DataFrame(rows).sort_values(['y', 'x']).reset_index(drop=True)
t.insert(0, 'n', range(len(t)))
t.to_csv(out + '.csv', index=False)
d = ImageDraw.Draw(img)
for _, r in t.iterrows():
    cx, cy = r.x - x0, r.y - y0
    d.rectangle([cx - r.w // 2, cy - r.h // 2, cx + r.w // 2, cy + r.h // 2], outline=(255, 0, 255), width=3)
    d.text((cx - r.w // 2 + 3, cy - r.h // 2 - 14), str(r.n), fill=(255, 0, 0))
# tiles of 1400 x 1000 px, scaled
W, H = img.size
k = 0
for ty in range(0, H, 1000):
    for tx in range(0, W, 1400):
        c = img.crop((tx, ty, min(tx + 1400, W), min(ty + 1000, H)))
        c.resize((int(c.width * sc), int(c.height * sc))).save(f'{out}_{k}.png'); k += 1
print(len(t), 'swatches;', k, 'tiles')
