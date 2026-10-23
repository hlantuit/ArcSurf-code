"""Windows around predicted graticule crossings of a scanned sheet, to read tie points by eye.
usage: grat_windows.py <jpg> lon0,lat0,lon1,lat1 "TL;TR;BR;BL" lons lats <out.png> [half=60] [scale=3]
lons / lats: comma lists. Prediction = homography from the 4 frame corners through a tmerc on the
sheet's central meridian (Krassowsky). Each window: 10 px grid, red cross = prediction, label =
lon,lat and window origin (full-res px = origin + grid px)."""
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
half = int(sys.argv[7]) if len(sys.argv) > 7 else 60
sc = int(sys.argv[8]) if len(sys.argv) > 8 else 3
crs = pyproj.CRS.from_proj4(f'+proj=tmerc +lat_0=0 +lon_0={(lo0 + lo1) / 2} +k=1 +a=6378245 +rf=298.3 +units=m +no_defs')
T = pyproj.Transformer.from_crs(4284, crs, always_xy=True)
ll = np.array([(lo0, la1), (lo1, la1), (lo1, la0), (lo0, la0)])
E, N = T.transform(ll[:, 0], ll[:, 1])
A, b = [], []
for e, n, (x, y) in zip(E, N, P):
    A += [[e, n, 1, 0, 0, 0, -x * e, -x * n], [0, 0, 0, e, n, 1, -y * e, -y * n]]; b += [x, y]
H = np.r_[np.linalg.solve(np.array(A), np.array(b)), 1].reshape(3, 3)
im = Image.open(f).convert('RGB')
w = 2 * half * sc
canvas = Image.new('RGB', (len(lons) * (w + 6), len(lats) * (w + 6)), 'white')
for j, la in enumerate(lats):
    for i, lo in enumerate(lons):
        e, n = T.transform(lo, la)
        v = H @ [e, n, 1]
        xp, yp = int(round(v[0] / v[2])), int(round(v[1] / v[2]))
        x0, y0 = xp - half, yp - half
        t = im.crop((x0, y0, x0 + 2 * half, y0 + 2 * half)).resize((w, w), Image.NEAREST)
        d = ImageDraw.Draw(t)
        for g in range(0, 2 * half + 1, 10):
            d.line([(g * sc, 0), (g * sc, w)], fill=(0, 170, 255)); d.line([(0, g * sc), (w, g * sc)], fill=(0, 170, 255))
        c = half * sc
        d.line([(c - 8, c), (c + 8, c)], fill=(255, 0, 0)); d.line([(c, c - 8), (c, c + 8)], fill=(255, 0, 0))
        d.text((3, 3), f'{lo:g},{la:g} o {x0},{y0}', fill=(0, 0, 0))
        canvas.paste(t, (i * (w + 6), j * (w + 6)))
        print(f'{lo:g},{la:g} predicted {xp},{yp} origin {x0},{y0}')
canvas.save(out)
