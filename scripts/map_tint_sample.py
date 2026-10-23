"""Sample printed map tints next to labelled polygons of a scanned sheet and compare with the
legend swatch colours (scanned prints differ from their legend boxes: saturation, halftone).
usage: map_tint_sample.py <jpg> <legend.csv> <points.csv: index,x,y> [--fit out.json]
Per point: 13x13 px windows at the label and 4 offsets (+-14 px in x, +-12 in y), dark pixels
(linework, glyphs) dropped; the offset closest to the legend colour is kept (most likely inside
the labelled polygon). Prints legend vs map colour per point; with --fit, fits a per-channel
affine legend->map from all points and writes the coefficients."""
import argparse
import json

import numpy as np
import pandas as pd
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser()
ap.add_argument('jpg'); ap.add_argument('legend'); ap.add_argument('points'); ap.add_argument('--fit')
ap.add_argument('--max-fit', type=float, default=45.0, help='points farther from their legend colour are not fitted')
ap.add_argument('--max-direct', type=float, default=65.0, help='map samples used directly as the unit fill')
ap.add_argument('--write-legend', help='write a corrected legend csv')
a = ap.parse_args()
from jpg_to_polygons import load_rgb   # CMYK scans through their ICC profile, as the extraction sees them
im = load_rgb(a.jpg).astype(int)
leg = pd.read_csv(a.legend, dtype=str, keep_default_na=False).set_index('index')
pts = pd.read_csv(a.points)


def h2c(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], float)


def c2h(c):
    return '#%02x%02x%02x' % tuple(int(round(v)) for v in np.clip(c, 0, 255))


L, M, K = [], [], []
for _, p in pts.iterrows():
    lc = h2c(leg.loc[p['index'], 'fill'])
    cand = []
    for dx, dy in ((0, 0), (-14, 0), (14, 0), (0, -12), (0, 12)):
        w = im[p.y + dy - 6:p.y + dy + 7, p.x + dx - 6:p.x + dx + 7].reshape(-1, 3)
        w = w[w.mean(axis=1) >= 90]
        if len(w) >= 40:
            m = np.median(w, axis=0)
            cand.append((np.linalg.norm(m - lc), m))
    if not cand:
        continue
    d, m = min(cand, key=lambda t: t[0])
    L.append(lc); M.append(m); K.append(p['index'])
    print(f"{p['index']:10s} legend {c2h(lc)} map {c2h(m)} dist {d:.0f}")
if a.fit:
    L, M = np.array(L), np.array(M)
    D = np.linalg.norm(L - M, axis=1)
    use = D <= a.max_fit                      # points that landed in a neighbouring polygon are dropped
    coef = {}
    for i, ch in enumerate('rgb'):
        A = np.c_[L[use, i], np.ones(use.sum())]
        s, o = np.linalg.lstsq(A, M[use, i], rcond=None)[0]
        coef[ch] = [float(s), float(o)]
    fit = lambda c: np.array([c[i] * coef[ch][0] + coef[ch][1] for i, ch in enumerate('rgb')])   # noqa: E731
    res = np.linalg.norm(np.array([fit(c) for c in L[use]]) - M[use], axis=1)
    print('fit on', int(use.sum()), 'of', len(L), 'points', coef, 'residual median', round(float(np.median(res)), 1), 'max', round(float(res.max()), 1))
    json.dump(dict(coef=coef, n=int(use.sum()), residual_median=float(np.median(res))), open(a.fit, 'w'), indent=1)
    if a.write_legend:
        # every unit gets the fitted tint; units sampled on the map within max_direct of their
        # legend colour take the median of their own samples instead
        out = leg.reset_index()
        direct = pd.DataFrame(dict(index=K, d=D, r=M[:, 0], g=M[:, 1], b=M[:, 2]))
        direct = direct[direct.d <= a.max_direct].groupby('index')[['r', 'g', 'b']].median()
        src = []
        for j, r in out.iterrows():
            if r['index'] in direct.index:
                out.loc[j, 'fill'] = c2h(direct.loc[r['index']].to_numpy()); src.append('map')
            else:
                out.loc[j, 'fill'] = c2h(fit(h2c(r['fill']))); src.append('fit')
        out['note'] = out['note'].astype(str)
        out.loc[0, 'note'] = (out.loc[0, 'note'] + f'; fills = map tints ({sum(s == "map" for s in src)} units sampled on the map, '
                              f'rest legend swatch x per-channel fit, scripts/map_tint_sample.py)')
        out.to_csv(a.write_legend, index=False)
        print('legend written', a.write_legend, dict(pd.Series(src).value_counts()))
