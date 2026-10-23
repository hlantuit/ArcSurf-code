#!/usr/bin/env python
"""Calibrate legend tints ON THE MAP for a colour-classified scan (geokniga 1:1M previews: P-48,49, T-48-50, P-46,47).

Printed legends and map faces differ (fade, screening, hatching, scan): a fill sampled from the legend swatch can sit
10-20 dE from the same unit on the map. Seeds = the legend fills (column `fill`, plus optional `fill2`, e.g. the
hatch+white mean of a hatched swatch). Iterate: classify the face (5x5 median-filtered, CIELAB) by nearest seed; for
each unit take the median of its FLAT pixels (local 5x5 SD sum < flat_sd) within `core_de` of the current centre; move
the centre there, but never more than `drift_cap` dE from the nearest seed. Units with fewer than `min_core` core pixels
keep their legend fill, and so do units named in --pin (e.g. a pale unit that would drift onto white paper, or a
hatched unit that blends into its neighbour).

Writes <out.csv> = the legend with `fill` replaced by the calibrated tint, and prints per unit: share of the face, core
pixels, calibrated fill, drift, share of its pixels > 14 dE (poorly matched), plus confusable pairs (< 8 dE).
--zone 'idx;idx@x,y;x,y;...' restricts units to a pixel polygon while classifying (as jpg_to_polygons --restrict).

usage: preview_tint_calib.py <map.jpg> <legend.csv> <out.csv> --box x0,y0,x1,y1 [--pin idx,idx] [--zone SPEC]
       [--drift-cap 15] [--core-de 9] [--flat-sd 10] [--min-core 150] [--iters 5]"""
import argparse

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None


def lab(rgb):
    c = np.asarray(rgb, np.float32) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = c @ M.T / np.array([0.95047, 1, 1.08883], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def to_hex(L):
    fy = (L[0] + 16) / 116; fx = fy + L[1] / 500; fz = fy - L[2] / 200
    xyz = np.array([fx, fy, fz]); xyz = np.where(xyz ** 3 > 0.008856, xyz ** 3, (xyz - 16 / 116) / 7.787) * np.array([0.95047, 1, 1.08883])
    M = np.linalg.inv(np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]))
    c = M @ xyz; c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return '#%02x%02x%02x' % tuple(np.clip(np.round(c * 255), 0, 255).astype(int))


def hex_lab(h):
    h = h.lstrip('#')
    return lab(np.array([[[int(h[i:i + 2], 16) for i in (0, 2, 4)]]], np.uint8))[0, 0]


ap = argparse.ArgumentParser()
ap.add_argument('img'); ap.add_argument('legend'); ap.add_argument('out')
ap.add_argument('--box', required=True); ap.add_argument('--pin', default=''); ap.add_argument('--zone', default='')
ap.add_argument('--drift-cap', type=float, default=15.0); ap.add_argument('--core-de', type=float, default=9.0)
ap.add_argument('--flat-sd', type=float, default=10.0); ap.add_argument('--min-core', type=int, default=150)
ap.add_argument('--iters', type=int, default=5)
a = ap.parse_args()
leg = pd.read_csv(a.legend, dtype=str, keep_default_na=False)
pins = {p for p in a.pin.split(',') if p}
keys = list(dict.fromkeys(leg['index']))
seeds = {}
for k in keys:
    r = leg[leg['index'] == k].iloc[0]
    s = [hex_lab(r['fill'])]
    if 'fill2' in leg.columns and r.get('fill2'):
        s.append(hex_lab(r['fill2']))
    seeds[k] = s
x0, y0, x1, y1 = map(int, a.box.split(','))
img = np.asarray(Image.open(a.img).convert('RGB'))
sub = ndi.median_filter(img[y0:y1, x0:x1], size=(5, 5, 1))
Lb = lab(sub)
sd = sum(np.sqrt(np.clip(ndi.uniform_filter(Lb[..., i] ** 2, 5) - ndi.uniform_filter(Lb[..., i], 5) ** 2, 0, None)) for i in range(3))
X = Lb.reshape(-1, 3); F = (sd < a.flat_sd).ravel()
allow = {}
if a.zone:
    from matplotlib.path import Path
    yy, xx = np.mgrid[y0:y1, x0:x1]
    for spec in a.zone.split('|'):
        nms, poly = spec.split('@', 1)
        pts = [tuple(map(float, q.split(','))) for q in poly.split(';')]
        m = Path(pts).contains_points(np.c_[xx.ravel(), yy.ravel()])
        for nm in nms.split(';'):
            allow[nm] = m


def classify(cent):
    best = np.full(len(X), np.inf, np.float32); arg = np.zeros(len(X), np.int16)
    for i, k in enumerate(keys):
        for c in cent[k]:
            d = np.sqrt(((X - c) ** 2).sum(1)).astype(np.float32)
            if k in allow:
                d[~allow[k]] = np.inf
            m = d < best; best[m] = d[m]; arg[m] = i
    return arg, best


cent = {k: list(v) for k, v in seeds.items()}
for _ in range(a.iters):
    arg, best = classify(cent)
    new = {}
    for i, k in enumerate(keys):
        m = (arg == i) & F & (best < a.core_de)
        if k not in pins and m.sum() > a.min_core:
            c = np.median(X[m], 0)
            s0 = min(seeds[k], key=lambda s: np.linalg.norm(c - s))
            dr = np.linalg.norm(c - s0)
            if dr > a.drift_cap:
                c = s0 + (c - s0) * a.drift_cap / dr
            new[k] = [c]
        else:
            new[k] = [seeds[k][0]]
    cent = new
arg, best = classify(cent)
out = leg.copy()
for i, k in enumerate(keys):
    m = arg == i; c = cent[k][0]; dr = min(np.linalg.norm(c - s) for s in seeds[k])
    out.loc[out['index'] == k, 'fill'] = to_hex(c)
    print(f'{k:12s} share {m.mean() * 100:5.1f}%  core {(m & F & (best < a.core_de)).sum():7d}  {to_hex(c)}  '
          f'drift {dr:5.1f}  >14dE {(best[m] > 14).mean() * 100 if m.any() else 0:5.1f}%{"  PINNED" if k in pins else ""}')
print('pixels > 14 dE from every unit:', round(float((best > 14).mean()), 3))
C = np.array([cent[k][0] for k in keys]); D = np.sqrt(((C[:, None] - C[None]) ** 2).sum(-1))
print('confusable pairs (< 8 dE):', [(keys[i], keys[j], round(float(D[i, j]), 1)) for i in range(len(keys)) for j in range(i + 1, len(keys)) if D[i, j] < 8])
out.drop(columns=[c for c in ('fill2',) if c in out.columns]).to_csv(a.out, index=False)
print('wrote', a.out)
