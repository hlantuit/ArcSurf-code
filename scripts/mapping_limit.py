"""Mapping limit of a partly mapped scan (Manitoba-Ontario series: only the Manitoba side is coloured)
and a staircase of --exclude boxes covering the unmapped side (to the RIGHT of the limit).
Per row (every 25 px) inside the face box: mapped pixel = saturation > 35 (crit 'sat'), or also any
non-paper pixel, mean < 230 (crit 'nonpaper': counts grey/low-saturation units such as organic
deposits 7, which 'sat' misses; thin linework on the unmapped side stays below the 0.5 average).
The limit is the rightmost x where a 101-px moving average of mapped pixels exceeds 0.5. A polynomial
x = f(y) (degree 1 or 2) is fitted with iterative 3-sigma (min 40 px) rejection, so white lakes and
grey polygons touching the limit, and solid insets on the unmapped side, drop out. Residuals of the
kept rows are printed per fifth of the height: a systematic pattern = a curved limit (use --deg 2).
Exclude boxes start at the fit's largest x within each band + margin and run to the face's right edge.
A curve method (first gap of the mapped average right of fit-600 px, band medians) is also written to
<img>.limit.csv for limit_overlay.py.
usage: mapping_limit.py <img> x0,y0,x1,y1 [--margin 40] [--band 100] [--deg 1] [--crit sat|nonpaper]"""
import argparse

import numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter1d

Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser()
ap.add_argument('img'); ap.add_argument('box')
ap.add_argument('--margin', type=int, default=40); ap.add_argument('--band', type=int, default=100)
ap.add_argument('--deg', type=int, default=1); ap.add_argument('--crit', default='sat', choices=['sat', 'nonpaper'])
a = ap.parse_args()
x0, y0, x1, y1 = (int(v) for v in a.box.split(','))
im = np.asarray(Image.open(a.img).convert('RGB').crop((x0, y0, x1, y1))).astype(np.int16)
sat = im.max(axis=2) - im.min(axis=2)
mean = im.mean(axis=2)
col = (sat > 35) & (mean < 245)
if a.crit == 'nonpaper':
    col |= mean < 230
del im
ys, xs = [], []
for r in range(0, col.shape[0], 25):
    m = uniform_filter1d(col[r].astype(float), 101)
    idx = np.flatnonzero(m > 0.5)
    if len(idx):
        ys.append(r + y0); xs.append(idx[-1] + x0)
ys, xs = np.array(ys, float), np.array(xs, float)
keep = np.ones(len(ys), bool)
for _ in range(15):
    c = np.polyfit(ys[keep], xs[keep], a.deg)
    res = xs - np.polyval(c, ys)
    sd = max(res[keep].std(), 15.0)
    new = np.abs(res) < max(3 * sd, 40)
    if (new == keep).all():
        break
    keep = new
f = lambda y: np.polyval(c, y)  # noqa: E731
print(f'fit deg {a.deg} ({a.crit}): coef {" ".join(f"{v:.6g}" for v in c)} ; rows kept {keep.sum()}/{len(keep)} ; '
      f'residual sd {res[keep].std():.1f} px')
q = np.linspace(y0, y1, 6)
print('kept-row residual median by fifth of height: ' + ', '.join(
    f'y{int(q[k])}-{int(q[k + 1])}: {np.median(res[keep & (ys >= q[k]) & (ys < q[k + 1])]):+.0f}'
    if (keep & (ys >= q[k]) & (ys < q[k + 1])).any() else f'y{int(q[k])}-{int(q[k + 1])}: -' for k in range(5)))
print(f'top ({f(y0):.0f},{y0})  bottom ({f(y1):.0f},{y1})')
if a.deg == 1:
    print(f'line x = {c[1]:.1f} + {c[0]:.5f}*y')
boxes = []
y = y0
while y < y1:
    yy = np.linspace(y, min(y + a.band, y1), 11)
    xl = f(yy).max() + a.margin
    boxes.append(f'{int(xl)},{int(y)},{x1 + 20},{int(min(y + a.band, y1 + 20))}')
    y += a.band
print('EXCLUDE ' + ';'.join(boxes))
# curve: per row (every 10 px) the FIRST x right of (fit - 600) where the 51-px moving average drops
# below 0.5 and the next 400 px are < 15 % mapped; band medians (50 rows), 7-band running median, bands
# > 80 px off it re-interpolated (for limit_overlay.py; a curve stops early at white lakes on the limit)
W = col.shape[1]
lim = []
for r in range(0, col.shape[0], 10):
    yv = r + y0
    row = col[r].astype(float)
    m = uniform_filter1d(row, 51)
    cs = np.concatenate([[0.0], np.cumsum(row)])
    ii = np.arange(W)
    e = np.minimum(ii + 400, W)
    frac = (cs[e] - cs[ii]) / np.maximum(e - ii, 1)
    ok = (m < 0.5) & (frac < 0.15) & (e - ii >= 100)
    ok[:int(max(0, f(yv) - 600 - x0))] = False
    idx = np.flatnonzero(ok)
    if len(idx):
        lim.append((yv, idx[0] + x0))
lim = np.array(lim, float)
yb = np.arange(y0, y1, 50)
sel = [(lim[:, 0] >= v) & (lim[:, 0] < v + 50) for v in yb]
med = np.array([np.median(lim[s, 1]) if s.any() else np.nan for s in sel])
good = np.isfinite(med)
for _ in range(3):
    rm = np.array([np.nanmedian(np.where(good, med, np.nan)[max(0, k - 3):k + 4]) for k in range(len(yb))])
    good = np.isfinite(med) & (np.abs(med - rm) < 80)
curve = np.interp(yb + 25, yb[good] + 25, med[good])
print(f'curve: {good.sum()}/{len(yb)} bands kept; curve minus fit at ' + ', '.join(
    f'y{int(v)}:{cv - f(v + 25):+.0f}' for v, cv in list(zip(yb, curve))[::10]))
cb = []
for k, v in enumerate(yb):
    lo, hi = curve[max(0, k - 1)], curve[min(len(yb) - 1, k + 1)]
    xl = max(curve[k], (curve[k] + lo) / 2, (curve[k] + hi) / 2) + a.margin
    cb.append(f'{int(xl)},{int(v)},{x1 + 20},{int(min(v + 50, y1 + 20))}')
print('EXCLUDE_CURVE ' + ';'.join(cb))
np.savetxt(a.img + '.limit.csv', np.c_[yb + 25, curve, good], fmt='%.0f', delimiter=',',
           header='y,x,measured', comments='')
