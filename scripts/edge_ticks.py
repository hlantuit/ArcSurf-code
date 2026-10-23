"""Windows on the frame edges of a scanned sheet at given meridians (top/bottom edges) and
parallels (left/right edges), predicted by homography from the 4 corners (tmerc, Krassowsky),
to read the degree ticks by eye where the map face has no interior graticule.
usage: edge_ticks.py <jpg> lon0,lat0,lon1,lat1 "TL;TR;BR;BL" lons lats <out.png> [half=80] [scale=3]"""
import sys

import numpy as np
import pyproj
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
f = sys.argv[1]
lo0, la0, lo1, la1 = map(float, sys.argv[2].split(','))
P = np.array([list(map(float, p.split(','))) for p in sys.argv[3].split(';')])
lons = [float(v) for v in sys.argv[4].split(',')]
lats = [float(v) for v in sys.argv[5].split(',')]
out = sys.argv[6]
half = int(sys.argv[7]) if len(sys.argv) > 7 else 80
sc = int(sys.argv[8]) if len(sys.argv) > 8 else 3
crs = pyproj.CRS.from_proj4(f'+proj=tmerc +lat_0=0 +lon_0={(lo0 + lo1) / 2} +k=1 +a=6378245 +rf=298.3 +units=m +no_defs')
T = pyproj.Transformer.from_crs(4284, crs, always_xy=True)
ll = np.array([(lo0, la1), (lo1, la1), (lo1, la0), (lo0, la0)])
E, N = T.transform(ll[:, 0], ll[:, 1])
A, b = [], []
for e, n, (x, y) in zip(E, N, P):
    A += [[e, n, 1, 0, 0, 0, -x * e, -x * n], [0, 0, 0, e, n, 1, -y * e, -y * n]]; b += [x, y]
H = np.r_[np.linalg.solve(np.array(A), np.array(b)), 1].reshape(3, 3)
pts = [(lo, la1, f'{lo:g}E top') for lo in lons] + [(lo, la0, f'{lo:g}E bottom') for lo in lons] + \
      [(lo0, la, f'{la:g}N left') for la in lats] + [(lo1, la, f'{la:g}N right') for la in lats]
im = Image.open(f).convert('RGB')
w = 2 * half * sc
canvas = Image.new('RGB', (min(len(pts), 4) * (w + 6), ((len(pts) + 3) // 4) * (w + 6)), 'white')
for i, (lo, la, lab) in enumerate(pts):
    e, n = T.transform(lo, la); v = H @ [e, n, 1]
    xp, yp = int(round(v[0] / v[2])), int(round(v[1] / v[2]))
    x0, y0 = xp - half, yp - half
    t = im.crop((x0, y0, x0 + 2 * half, y0 + 2 * half)).resize((w, w), Image.NEAREST)
    d = ImageDraw.Draw(t)
    for g in range(0, 2 * half + 1, 10):
        d.line([(g * sc, 0), (g * sc, w)], fill=(0, 170, 255)); d.line([(0, g * sc), (w, g * sc)], fill=(0, 170, 255))
    c = half * sc
    d.line([(c - 10, c), (c + 10, c)], fill=(255, 0, 0)); d.line([(c, c - 10), (c, c + 10)], fill=(255, 0, 0))
    d.text((3, 3), f'{lab} o {x0},{y0}', fill=(0, 0, 0))
    canvas.paste(t, ((i % 4) * (w + 6), (i // 4) * (w + 6)))
    print(f'{lab}: predicted {xp},{yp} origin {x0},{y0}')
canvas.save(out)
