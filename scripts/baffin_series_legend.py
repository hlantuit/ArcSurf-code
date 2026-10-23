"""Legend for one sheet of the GSC Baffin 1:100k surficial series (Dredge et al. 2003: OF4296, 4354,
4355, 4357, 4411, 4412, 1535, 1569-1572; common legend, coloured boxes = units on this sheet,
white boxes = units absent). Swatches found with swatch_scan logic along x0..x1; the 21 boxes are
assigned to the series codes IN ORDER; white boxes are dropped; fills sampled per print.
usage: baffin_series_legend.py <img> <out.csv> <label>   (finds the legend column itself)"""
import sys

import numpy as np
import pandas as pd
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
SERIES = [
    ('ICE', 'I', '', '', 'Glacier ice'),
    ('A', 'F', '', 'gravel', 'Fluvial deposits: gravel sand boulders 1-5 m'),
    ('Mr', 'M', '', 'gravel', 'Marine beach sediments'),
    ('Md', 'M', 'F', 'sand', 'Marine deltaic sediments'),
    ('Mb', 'M', '', 'sand', 'Marine blanket'),
    ('Mv', 'M', 'T', 'mixed', 'Marine veneer over till or rock'),
    ('GM', 'GM', '', 'diamicton', 'Glaciomarine blanket'),
    ('Lb', 'GL', '', 'sand', 'Glaciolacustrine blanket'),
    ('Lv', 'GL', 'T', 'sand', 'Glaciolacustrine veneer'),
    ('Gp', 'GF', '', 'gravel', 'Glaciofluvial outwash'),
    ('Gr', 'GF', '', 'gravel', 'Glaciofluvial ice-contact'),
    ('Tm', 'T', '', 'diamicton', 'Massive end moraines'),
    ('Th', 'T', '', 'diamicton', 'Hummocky till'),
    ('Tb', 'T', '', 'diamicton', 'Till blanket'),
    ('Tv', 'T', 'R', 'diamicton', 'Till veneer'),
    ('RC', 'R', '', '', 'Bedrock: Paleozoic limestone and dolomite'),
    ('RF', 'R', '', '', 'Bedrock: Fury and Hecla marble'),
    ('RA', 'R', '', '', 'Bedrock: Astarte River formation'),
    ('RL', 'R', '', '', 'Bedrock: clastic metasedimentary rocks'),
    ('RB', 'R', '', '', 'Bedrock: mafic and ultramafic rocks'),
    ('RG', 'R', '', '', 'Bedrock: granite and gneiss'),
]
img, out, lab = sys.argv[1], sys.argv[2], sys.argv[3]
full = np.asarray(Image.open(img).convert('RGB')).astype(int)
H, W = full.shape[:2]


def scan(x0, x1, y0, y1):
    im = full[y0:y1, x0:x1]
    L = im.mean(axis=2)
    ys = np.flatnonzero((L < 100).mean(axis=1) > 0.5)
    boxes = []
    for a, b in zip(ys[:-1], ys[1:]):
        if 80 <= b - a <= 140:
            inner = im[a + 5:b - 4, 4:-4].reshape(-1, 3)
            inner = inner[inner.mean(axis=1) >= 100]
            if len(inner):
                boxes.append('#%02x%02x%02x' % tuple(np.median(inner, axis=0).astype(int)))
    return boxes


# the legend column is somewhere in the right fifth: try x positions until 21 boxes are found
boxes, where = [], None
for x in range(int(W * 0.78), W - 120, 20):
    b = scan(x, x + 100, int(H * 0.03), int(H * 0.7))
    b = b[:len(SERIES)]                            # boxes below the legend (title block) are ignored
    coloured = sum(min(int(f[i:i + 2], 16) for i in (1, 3, 5)) < 245 for f in b)
    if len(b) == len(SERIES) and coloured >= 4:      # an all-white column is not the legend
        boxes, where = b, x
        break
if not boxes:
    sys.exit(f'{lab}: no column with {len(SERIES)} legend boxes found')
print(lab, 'legend column at x', where)
rows = []
for (code, h, h2, t, d), f in zip(SERIES, boxes):
    c = np.array([int(f[i:i + 2], 16) for i in (1, 3, 5)])
    if c.min() >= 245:                     # white box = unit absent on this sheet
        continue
    if code == 'ICE':                      # ice tint (#f4ffff) is within dE of paper; ice comes from RGI/PROMICE
        continue
    rows.append(dict(k=len(rows), fill=f, index=code, description_ru=d, hclass=h, hclass2=h2, texture=t, ice_rich='', note=''))
t = pd.DataFrame(rows)
t.loc[0, 'note'] = f'GSC {lab} Baffin 1:100k surficial series (Dredge et al. 2003), common legend; fills sampled on this print'
t.to_csv(out, index=False)
print(lab, ' '.join(f'{a}:{b}' for a, b in zip(t['index'], t.fill)))
