"""Compare a legend CSV's fills with the dominant colour clusters ON THE MAP FACE (scanned
prints differ from their legend swatches by dE 10-17: A1693a, A1849a). Prints the top
clusters with the nearest two legend units and the share of face pixels that would stay
unassigned at dE 14.
usage: tint_check.py <image> <legend.csv> x0,y0,x1,y1 [step]"""
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
import jpg_to_polygons as J  # noqa: E402

img, legf, box = sys.argv[1:4]
step = int(sys.argv[4]) if len(sys.argv) > 4 else 3
x0, y0, x1, y1 = map(int, box.split(','))
a = J.load_rgb(img)[y0:y1:step, x0:x1:step]
s = ndi.median_filter(a, size=(5, 5, 1))
L = J.to_lab(s).reshape(-1, 3); p = s.reshape(-1, 3)
keep = ~((L[:, 0] > 95) & (np.hypot(L[:, 1], L[:, 2]) < 4)) & (L[:, 0] > 22)
L, p = L[keep], p[keep]
leg = pd.read_csv(legf, dtype=str, keep_default_na=False).drop_duplicates('fill')
cl = J.to_lab(np.array([J.hex2rgb(h) for h in leg['fill']])[None])[0]
d = np.sqrt(((L[:, None] - cl[None]) ** 2).sum(-1))
print('face px (non-paper):', len(L), '| unassigned at dE14:', round(float((d.min(1) > 14).mean()), 3))
print('per unit direct share:', {leg['index'].iloc[i]: round(float(((d.argmin(1) == i) & (d.min(1) <= 14)).mean()), 3) for i in range(len(leg))})
q = (p // 14).astype(int); k = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
u, c = np.unique(k, return_counts=True)
for i in np.argsort(-c)[:25]:
    m = k == u[i]; lab = L[m].mean(0); dd = np.sqrt(((cl - lab) ** 2).sum(1)); j = np.argsort(dd)[:2]
    print('#%02x%02x%02x' % tuple(p[m].mean(0).astype(int)), round(c[i] / len(k), 3), [(leg['index'].iloc[x], round(float(dd[x]), 1)) for x in j])
