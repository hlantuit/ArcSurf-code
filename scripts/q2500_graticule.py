"""Graticule of the VSEGEI 1:2.5M Quaternary map (Quart_2500.pdf): extract candidate
graticule strokes (#b0b91d, 0.36 pt, the long-stroke population in the survey) and the
degree labels; classify strokes as straight (meridians) or curved (parallels); fit the
apex of the meridians and circles to the parallels. Writes work/q2500/graticule.json and
a QC render. The projection fit itself uses these (q2500_fit.py)."""
import json
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pymupdf  # noqa: E402

PDF = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/russia_hunt/Quart_2500.pdf'
OUT = '/albedo/work/user/hlantuit/arctic_surficial/work/q2500'
page = pymupdf.open(PDF)[0]


def hexc(c):
    return '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) if c else None


def pts_of(d):
    """flatten a drawing's items to one point list per subpath"""
    runs, cur, last = [], [], None
    for it in d['items']:
        op = it[0]
        if op == 'l':
            a, b = it[1], it[2]
            if last is None or abs(a.x - last.x) > .01 or abs(a.y - last.y) > .01:
                if cur:
                    runs.append(cur)
                cur = [(a.x, a.y)]
            cur.append((b.x, b.y)); last = b
        elif op == 'c':
            a, b1, b2, b = it[1:5]
            if last is None or abs(a.x - last.x) > .01 or abs(a.y - last.y) > .01:
                if cur:
                    runs.append(cur)
                cur = [(a.x, a.y)]
            for t in np.linspace(0, 1, 9)[1:]:
                x = (1-t)**3*a.x + 3*(1-t)**2*t*b1.x + 3*(1-t)*t**2*b2.x + t**3*b.x
                y = (1-t)**3*a.y + 3*(1-t)**2*t*b1.y + 3*(1-t)*t**2*b2.y + t**3*b.y
                cur.append((x, y))
            last = b
    if cur:
        runs.append(cur)
    return [np.array(r) for r in runs if len(r) >= 2]


runs = []
for d in page.get_drawings():
    if d.get('fill') is not None or hexc(d.get('color')) != '#b0b91d':
        continue
    w = round(d.get('width') or 0, 2)
    if w not in (0.36, 0.48):
        continue
    for r in pts_of(d):
        L = np.hypot(*np.diff(r, axis=0).T).sum()
        if L > 200:                       # graticule lines are long; river/contour bits are not
            runs.append(r)
print('long olive runs', len(runs), flush=True)
feat = []
for r in runs:
    c = r - r.mean(0)
    u, s, vt = np.linalg.svd(c, full_matrices=False)
    straight = s[1] / max(s[0], 1e-9) < 0.004          # relative off-line spread
    feat.append(dict(n=len(r), length=float(np.hypot(*np.diff(r, axis=0).T).sum()), straight=bool(straight),
                     x0=float(r[0, 0]), y0=float(r[0, 1]), x1=float(r[-1, 0]), y1=float(r[-1, 1]),
                     spread=float(s[1] / max(s[0], 1e-9))))
F = pd.DataFrame(feat)
print(F.straight.value_counts().to_dict(), F.length.describe().round(0).to_dict())
# apex: least-squares intersection of the straight runs (each as a line through its ends)
S = [r for r, f in zip(runs, feat) if f['straight']]
A, b = [], []
for r in S:
    p0, p1 = r[0], r[-1]
    dvec = (p1 - p0) / np.linalg.norm(p1 - p0)
    nrm = np.array([-dvec[1], dvec[0]])
    A.append(nrm); b.append(nrm @ p0)
apex = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)[0] if len(A) >= 2 else [np.nan, np.nan]
res = np.array(A) @ apex - np.array(b) if len(A) >= 2 else np.array([np.nan])
print('apex', np.round(apex, 1), 'line residual pt: median', round(float(np.median(np.abs(res))), 2), 'max', round(float(np.abs(res).max()), 2))
# parallels: radius of every curved run about the apex (constant radius = concentric)
C = [r for r, f in zip(runs, feat) if not f['straight']]
rad = [(float(np.median(np.hypot(*(r - apex).T))), float(np.std(np.hypot(*(r - apex).T))), float(np.hypot(*np.diff(r, axis=0).T).sum())) for r in C]
rad.sort()
print('curved runs', len(C), '| radius (median, sd, length) first 30:', [tuple(round(v, 1) for v in x) for x in rad[:30]])
# meridian angles about the apex
ang = sorted(float(np.degrees(np.arctan2(*(r[len(r) // 2] - apex)[::-1]))) for r in S)
print('meridian angles (deg, image frame):', [round(a, 2) for a in ang])
tx = pd.read_parquet(f'{OUT}/text.parquet')
deg = tx[tx.t.str.match(r'^\d{1,3}\s*°')].copy()
deg['v'] = deg.t.str.extract(r'^(\d{1,3})')[0].astype(int)
deg['xc'], deg['yc'] = (deg.x0 + deg.x1) / 2, (deg.y0 + deg.y1) / 2
deg['r_apex'] = np.hypot(deg.xc - apex[0], deg.yc - apex[1])
deg['ang'] = np.degrees(np.arctan2(deg.yc - apex[1], deg.xc - apex[0]))
json.dump(dict(apex=list(map(float, apex)), meridian_angles=ang, parallels=rad,
               labels=deg[['t', 'v', 'xc', 'yc', 'r_apex', 'ang', 'size']].to_dict('records')),
          open(f'{OUT}/graticule.json', 'w'), indent=1)
# QC render: page at low res with the runs overlaid
sc = 1500 / page.rect.width
pix = page.get_pixmap(matrix=pymupdf.Matrix(sc, sc))
from PIL import Image, ImageDraw  # noqa: E402
im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
dr = ImageDraw.Draw(im)
for r, f in zip(runs, feat):
    dr.line([tuple(p * sc) for p in r], fill=(220, 0, 0) if f['straight'] else (0, 90, 220), width=2)
for _, q in deg.iterrows():
    dr.text((q.xc * sc, q.yc * sc), str(q.v), fill=(0, 0, 0))
im.save(f'{OUT}/graticule_qc.png')
print('saved QC')
