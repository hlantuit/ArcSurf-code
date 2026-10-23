"""Measure graticule crossings on a scanned sheet automatically. Around each predicted crossing
(homography from the 4 frame corners, tmerc, Krassowsky) the column (meridian) and row (parallel)
darkness profiles over a +-H px strip are taken; a straight thin line gives a sharp peak, curved
unit boundaries smear out. Peak = offset; prominence = peak / median of the profile.
usage: grat_auto.py <jpg> lon0,lat0,lon1,lat1 "TL;TR;BR;BL" lons lats [search=25] [H=150]
Prints lon,lat,x,y,prom_x,prom_y per crossing (use only crossings where both prominences are high)."""
import sys

import numpy as np
import pyproj
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
f = sys.argv[1]
lo0, la0, lo1, la1 = map(float, sys.argv[2].split(','))
P = np.array([list(map(float, p.split(','))) for p in sys.argv[3].split(';')])
lons = [float(v) for v in sys.argv[4].split(',')]
lats = [float(v) for v in sys.argv[5].split(',')]
S = int(sys.argv[6]) if len(sys.argv) > 6 else 25
Hh = int(sys.argv[7]) if len(sys.argv) > 7 else 150
crs = pyproj.CRS.from_proj4(f'+proj=tmerc +lat_0=0 +lon_0={(lo0 + lo1) / 2} +k=1 +a=6378245 +rf=298.3 +units=m +no_defs')
T = pyproj.Transformer.from_crs(4284, crs, always_xy=True)
ll = np.array([(lo0, la1), (lo1, la1), (lo1, la0), (lo0, la0)])
E, N = T.transform(ll[:, 0], ll[:, 1])
A, b = [], []
for e, n, (x, y) in zip(E, N, P):
    A += [[e, n, 1, 0, 0, 0, -x * e, -x * n], [0, 0, 0, e, n, 1, -y * e, -y * n]]; b += [x, y]
H = np.r_[np.linalg.solve(np.array(A), np.array(b)), 1].reshape(3, 3)
im = np.asarray(Image.open(f).convert('RGB')).astype(float)
L = im.mean(axis=2)
sat = im.max(axis=2) - im.min(axis=2)
dark = np.clip(200 - L, 0, None) * (sat < 60)          # grey linework, not saturated colour


def proj(lo, la):
    e, n = T.transform(lo, la); v = H @ [e, n, 1]
    return v[0] / v[2], v[1] / v[2]


for la in lats:
    for lo in lons:
        x, y = proj(lo, la)
        # local line directions from the projection (meridian / parallel are slightly tilted)
        xm, ym = proj(lo, la + 0.05); xp, yp = proj(lo + 0.05, la)
        sm = (xm - x) / (ym - y)                         # dx per dy along the meridian
        sp = (yp - y) / (xp - x)                         # dy per dx along the parallel
        xi, yi = int(round(x)), int(round(y))
        # meridian: for each candidate x offset, sum darkness along the tilted line over +-Hh rows
        ys = np.arange(yi - Hh, yi + Hh + 1)
        prof_x = []
        for dx in range(-S, S + 1):
            xs = np.round(xi + dx + sm * (ys - yi)).astype(int)
            prof_x.append(dark[ys, xs].sum())
        xs_ = np.arange(xi - Hh, xi + Hh + 1)
        prof_y = []
        for dy in range(-S, S + 1):
            yy = np.round(yi + dy + sp * (xs_ - xi)).astype(int)
            prof_y.append(dark[yy, xs_].sum())
        prof_x, prof_y = np.array(prof_x), np.array(prof_y)
        kx, ky = int(np.argmax(prof_x)), int(np.argmax(prof_y))
        px = prof_x[kx] / (np.median(prof_x) + 1); py = prof_y[ky] / (np.median(prof_y) + 1)
        print(f'{lo:g},{la:g},{xi + kx - S},{yi + ky - S},{px:.2f},{py:.2f}  (pred {xi},{yi}; d {kx - S},{ky - S})')
