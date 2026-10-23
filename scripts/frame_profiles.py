"""Dark-line positions around approximate map-face corners, from grey-level profiles (to read the
inner neatline to ~1 px; refine_corner's L<50 rule misses faint inner lines and can snap to the
minute bar instead). For each corner TL;TR;BR;BL (interior direction (+1,+1), (-1,+1), (-1,-1), (+1,-1)):
  rows: mean grey over x in [x + sx*10, x + sx*(10+avg)] for y in y-half..y+half  (horizontal lines)
  cols: mean grey over y in [y + sy*10, y + sy*(10+avg)] for x in x-half..x+half  (vertical lines)
Prints runs of profile values < thr as start-end(min), outermost first.
usage: frame_profiles.py <img> "x,y;x,y;x,y;x,y" [half=40] [avg=50] [thr=200]"""
import sys

import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
im = np.asarray(Image.open(sys.argv[1]).convert('L'), dtype=np.float32)
pts = [tuple(int(v) for v in p.split(',')) for p in sys.argv[2].split(';')]
half = int(sys.argv[3]) if len(sys.argv) > 3 else 40
avg = int(sys.argv[4]) if len(sys.argv) > 4 else 50
thr = float(sys.argv[5]) if len(sys.argv) > 5 else 200


def runs(v, lo):
    idx = np.flatnonzero(v < thr)
    out, s = [], None
    for k, i in enumerate(idx):
        if s is None:
            s = i
        if k == len(idx) - 1 or idx[k + 1] != i + 1:
            out.append(f'{lo + s}-{lo + i}({int(v[s:i + 1].min())})')
            s = None
    return ' '.join(out)


for lab, (x, y), (sx, sy) in zip(('TL', 'TR', 'BR', 'BL'), pts, [(1, 1), (-1, 1), (-1, -1), (1, -1)]):
    xa, xb = sorted((x + sx * 10, x + sx * (10 + avg)))
    ya, yb = sorted((y + sy * 10, y + sy * (10 + avg)))
    rows = im[y - half:y + half, xa:xb].mean(1)
    cols = im[ya:yb, x - half:x + half].mean(0)
    print(f'{lab} ({x},{y}) rows y: {runs(rows, y - half)}')
    print(f'{lab} ({x},{y}) cols x: {runs(cols, x - half)}')
