"""Candidate WATER tint of a scanned sheet: median colour of pale-blue face pixels (5x5 median; L >= minL,
b* <= maxb, chroma 6-30), their share of the face, and the distance to every legend fill. Wide rivers and lakes
printed in a pale blue are otherwise read as the nearest unit (O-46-XV: the Yenisei as a terrace).
usage: water_tint.py <img> <legend.csv> x0,y0,x1,y1 [minL=72] [maxb=-6]"""
import sys

import numpy as np
import pandas as pd
from scipy import ndimage as ndi

sys.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
from jpg_to_polygons import load_rgb, to_lab  # noqa: E402

img, legf, box = sys.argv[1:4]
minL = float(sys.argv[4]) if len(sys.argv) > 4 else 72.0
maxb = float(sys.argv[5]) if len(sys.argv) > 5 else -6.0
x0, y0, x1, y1 = map(int, box.split(','))
rgb = ndi.median_filter(load_rgb(img)[y0:y1, x0:x1], size=(5, 5, 1))[::3, ::3]
lab = to_lab(rgb)
ch = np.hypot(lab[..., 1], lab[..., 2])
m = (lab[..., 0] >= minL) & (lab[..., 2] <= maxb) & (ch >= 6) & (ch <= 30)
m = ndi.binary_opening(m, iterations=2)
print(f'pale-blue share of face {m.mean():.2%}')
if m.sum() < 50:
    sys.exit()
med = np.median(rgb[m], 0).astype(int)
ml = np.median(lab[m], 0)
print(f'median #{med[0]:02x}{med[1]:02x}{med[2]:02x}  L{ml[0]:.0f} a{ml[1]:.1f} b{ml[2]:.1f}')
L = pd.read_csv(legf, dtype=str, keep_default_na=False)
cl = to_lab(np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in L.fill], np.uint8)[None])[0]
d = np.linalg.norm(cl - ml, axis=1)
print('nearest legend fills: ' + ', '.join(f'{L["index"].iloc[i]} {d[i]:.1f}' for i in np.argsort(d)[:4]))
