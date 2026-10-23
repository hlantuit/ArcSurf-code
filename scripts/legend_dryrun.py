"""Dry run of the nearest-colour classification on a map face, to see which legend units occur and how
ambiguous they are before an extraction: per unit, share of face pixels (5x5 median, dE <= max, L >= minL),
and the share of its pixels whose second-nearest unit is within `amb` dE (a coin toss between the two).
usage: legend_dryrun.py <img> <legend.csv> x0,y0,x1,y1 [step=3] [dE=14] [amb=3]"""
import sys

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None
img, legf, box = sys.argv[1:4]
step = int(sys.argv[4]) if len(sys.argv) > 4 else 3
dEmax = float(sys.argv[5]) if len(sys.argv) > 5 else 14.0
amb = float(sys.argv[6]) if len(sys.argv) > 6 else 3.0
x0, y0, x1, y1 = map(int, box.split(','))


def to_lab(rgb):
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = (c @ M.T) / np.array([0.95047, 1.0, 1.08883], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


from jpg_to_polygons import load_rgb   # CMYK scans through their ICC profile, as the extraction sees them
im = load_rgb(img)[y0:y1, x0:x1]
im = ndi.median_filter(im, size=(5, 5, 1))[::step, ::step]
lab = to_lab(im).reshape(-1, 3)
L = pd.read_csv(legf, dtype=str, keep_default_na=False)
cl = to_lab(np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in L.fill], np.uint8)[None])[0]
d = np.sqrt(((lab[:, None, :] - cl[None]) ** 2).sum(-1))
o = np.argsort(d, 1)
b1, b2 = o[:, 0], o[:, 1]
d1 = d[np.arange(len(d)), b1]; d2 = d[np.arange(len(d)), b2]
ok = (d1 <= dEmax) & (lab[:, 0] >= 38)
print(f'face pixels {len(d)} (step {step}); assigned {ok.mean():.1%}; dark/linework {np.mean(lab[:, 0] < 38):.1%}')
rows = []
for k, r in L.iterrows():
    m = ok & (b1 == k)
    if m.sum() == 0:
        continue
    near = pd.Series(L['index'].values[b2[m]]).value_counts()
    rows.append((m.mean(), r['index'], r.hclass, np.mean(d2[m] - d1[m] < amb), near.index[0], near.iloc[0] / m.sum()))
for share, idx, hc, a, nb, nbs in sorted(rows, reverse=True):
    print(f'{idx:>10} ({hc:>2}) {share:6.2%}  ambiguous(<{amb:g} dE) {a:5.1%}  2nd-nearest mostly {nb} ({nbs:.0%})')
