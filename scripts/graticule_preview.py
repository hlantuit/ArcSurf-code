"""Preview of a scan with the graticule drawn from a 4-corner TM fit (to see which graticule blocks are
mapped on a partly mapped sheet, and to place --exclude-lonlat blocks).
usage: graticule_preview.py <img> <out.png> lon0,lat0,lon1,lat1 "TL;TR;BR;BL" dlon dlat [datum=4267] [scale=10]"""
import sys

import numpy as np
import pyproj
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
img, out, fr, cs, dlon, dlat = sys.argv[1:7]
datum = int(sys.argv[7]) if len(sys.argv) > 7 else 4267
sc = int(sys.argv[8]) if len(sys.argv) > 8 else 10
lon0, lat0, lon1, lat1 = map(float, fr.split(','))
P = np.array([[float(v) for v in c.split(',')] for c in cs.split(';')])
ll = np.array([(lon0, lat1), (lon1, lat1), (lon1, lat0), (lon0, lat0)])
ell = pyproj.CRS.from_epsg(datum).ellipsoid
tm = pyproj.CRS.from_proj4(f'+proj=tmerc +lat_0=0 +lon_0={(lon0 + lon1) / 2} +k=0.9996 +a={ell.semi_major_metre} '
                           f'+rf={ell.inverse_flattening} +units=m +no_defs')
T = pyproj.Transformer.from_crs(datum, tm, always_xy=True)
E, N = T.transform(ll[:, 0], ll[:, 1])
A = np.c_[E, N, np.ones(4)]
cx, *_ = np.linalg.lstsq(A, P[:, 0], rcond=None); cy, *_ = np.linalg.lstsq(A, P[:, 1], rcond=None)
res = np.hypot(A @ cx - P[:, 0], A @ cy - P[:, 1])
print('corner residual px', np.round(res, 1))


def px(lo, la):
    e, n = T.transform(np.atleast_1d(lo), np.atleast_1d(la))
    B = np.c_[e, n, np.ones(len(e))]
    return B @ cx / sc, B @ cy / sc


im = Image.open(img).convert('RGB')
im = im.resize((im.width // sc, im.height // sc))
d = ImageDraw.Draw(im)
for lo in np.arange(lon0, lon1 + 1e-9, float(dlon)):
    x, y = px(np.full(50, lo), np.linspace(lat0, lat1, 50))
    d.line(list(zip(x, y)), fill=(255, 0, 0), width=2)
    d.text((x[-1] + 3, y[-1] + 3), f'{lo:g}', fill=(255, 0, 0))
for la in np.arange(lat0, lat1 + 1e-9, float(dlat)):
    x, y = px(np.linspace(lon0, lon1, 80), np.full(80, la))
    d.line(list(zip(x, y)), fill=(255, 0, 0), width=2)
    d.text((x[0] + 3, y[0] - 12), f'{la:g}', fill=(255, 0, 0))
im.save(out)
