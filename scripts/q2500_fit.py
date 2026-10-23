"""Projection of the VSEGEI 1:2.5M Quaternary map from its own graticule.

Graticule strokes are #b0b91d like the rivers, and the page carries three inset maps with
their own graticules, so: keep only runs inside the MAIN map frame and outside the inset
box; meridians = long straight runs (apex = their least-squares intersection); parallels =
long runs of near-constant radius about the apex. Each line gets its value from the
degree label nearest to where it meets the frame. Then:
  meridian angle  = theta0 + n * (lon - lon0)             -> cone constant n, lon0
  parallel radius = rho(lat) : linear (equidistant conic) or rho0 * t(lat)^n (LCC)
and the page->projection similarity (scale, rotation, apex) follows. Writes
work/q2500/fit.json. Null space: fits the graticule only; paper/drafting distortion of
the map face is tested separately (coastline vs OSM)."""
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
SC = 1500 / page.rect.width                       # QC render px per pt
FRAME = (60 / SC, 165 / SC, 1450 / SC, 925 / SC)   # main map frame, from the QC render (pt)
INSET = (95 / SC, 795 / SC, 245 / SC, 895 / SC)    # bottom-left inset inside the frame (pt)


def hexc(c):
    return '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) if c else None


def runs_of(d):
    runs, cur, last = [], [], None
    for it in d['items']:
        if it[0] not in ('l', 'c'):
            continue
        a = it[1]
        if last is None or abs(a.x - last.x) > .01 or abs(a.y - last.y) > .01:
            if cur:
                runs.append(cur)
            cur = [(a.x, a.y)]
        if it[0] == 'l':
            b = it[2]; cur.append((b.x, b.y))
        else:
            b1, b2, b = it[2], it[3], it[4]
            for t in np.linspace(0, 1, 9)[1:]:
                cur.append(((1-t)**3*a.x + 3*(1-t)**2*t*b1.x + 3*(1-t)*t**2*b2.x + t**3*b.x,
                            (1-t)**3*a.y + 3*(1-t)**2*t*b1.y + 3*(1-t)*t**2*b2.y + t**3*b.y))
        last = b
    if cur:
        runs.append(cur)
    return [np.array(r) for r in runs if len(r) >= 2]


def inbox(p, box, pad=0):
    return (p[:, 0] > box[0] - pad) & (p[:, 0] < box[2] + pad) & (p[:, 1] > box[1] - pad) & (p[:, 1] < box[3] + pad)


R = []
for d in page.get_drawings():
    if d.get('fill') is not None or hexc(d.get('color')) != '#b0b91d':
        continue
    for r in runs_of(d):
        if np.hypot(*np.diff(r, axis=0).T).sum() < 300:
            continue
        if not inbox(r, FRAME, 5).all() or inbox(r, INSET, 20).any():
            continue
        R.append(r)
print('candidate runs in main frame', len(R), flush=True)


def straightness(r):
    c = r - r.mean(0)
    s = np.linalg.svd(c, compute_uv=False)
    return s[1] / max(s[0], 1e-9)


S = [r for r in R if straightness(r) < 0.002 and np.hypot(*(r[-1] - r[0])) > 1000]
# robust apex: iteratively drop lines far from the common point
lines = []
for r in S:
    p0, p1 = r[0], r[-1]
    dv = (p1 - p0) / np.linalg.norm(p1 - p0)
    lines.append((np.array([-dv[1], dv[0]]), p0, r))
keep = np.ones(len(lines), bool)
for _ in range(10):
    A = np.array([l[0] for l in lines])[keep]; b = np.array([l[0] @ l[1] for l in lines])[keep]
    apex = np.linalg.lstsq(A, b, rcond=None)[0]
    res = np.array([abs(l[0] @ apex - l[0] @ l[1]) for l in lines])
    new = res < max(3 * np.median(res[keep]), 2.0)
    if (new == keep).all():
        break
    keep = new
print(f'meridian lines {int(keep.sum())}/{len(lines)}; apex {apex.round(1)}; residual median {np.median(res[keep]):.2f} pt max {res[keep].max():.2f}')
mer = [l[2] for l, k in zip(lines, keep) if k]
# parallels: constant radius about the apex
par = []
for r in R:
    rr = np.hypot(*(r - apex).T)
    if rr.std() < 1.5 and np.hypot(*np.diff(r, axis=0).T).sum() > 1500:
        par.append((float(np.median(rr)), r))
# merge pieces of the same parallel
par.sort(key=lambda x: x[0])
rad = []
for rho, r in par:
    if rad and abs(rho - rad[-1][0]) < 3:
        rad[-1][1].append(rho)
    else:
        rad.append([rho, [rho]])
rad = [float(np.mean(x[1])) for x in rad]
print('parallel radii (pt)', [round(x, 1) for x in rad])

# labels: degree values with position
tx = pd.read_parquet(f'{OUT}/text.parquet')
deg = tx[tx.t.str.match(r'^\d{1,3}\s*°')].copy()
deg['v'] = deg.t.str.extract(r'^(\d{1,3})')[0].astype(int)
deg['xc'], deg['yc'] = (deg.x0 + deg.x1) / 2, (deg.y0 + deg.y1) / 2
deg = deg[inbox(deg[['xc', 'yc']].values, FRAME, 120) & ~inbox(deg[['xc', 'yc']].values, INSET, 60)]
fx0, fy0, fx1, fy1 = FRAME


def frame_hits(p0, dv):
    """intersections of the ray p0 + t dv with the frame rectangle"""
    hits = []
    for axis, val in ((0, fx0), (0, fx1), (1, fy0), (1, fy1)):
        if abs(dv[axis]) < 1e-9:
            continue
        t = (val - p0[axis]) / dv[axis]
        q = p0 + t * dv
        if fx0 - 1 <= q[0] <= fx1 + 1 and fy0 - 1 <= q[1] <= fy1 + 1:
            hits.append(q)
    return hits


def nearest_label(q, maxd=90):
    d = np.hypot(deg.xc - q[0], deg.yc - q[1])
    i = d.idxmin()
    return (int(deg.v[i]), float(d[i])) if d[i] < maxd else (None, float(d[i]))


mrows = []
for r in mer:
    ang = float(np.degrees(np.arctan2(*(r[len(r) // 2] - apex)[::-1])))
    dv = np.array([np.cos(np.radians(ang)), np.sin(np.radians(ang))])
    labs = [nearest_label(q) for q in frame_hits(apex, dv)]
    labs = [l for l in labs if l[0] is not None]
    if labs:
        v = min(labs, key=lambda l: l[1])[0]
        mrows.append(dict(angle=ang, lon=v))
M = pd.DataFrame(mrows).drop_duplicates('angle')
prows = []
for rho in rad:
    # a parallel meets the left/right frame edges: points at radius rho on x = fx0 / fx1
    for xe in (fx0, fx1):
        dy2 = rho ** 2 - (xe - apex[0]) ** 2
        if dy2 <= 0:
            continue
        for sgn in (1, -1):
            y = apex[1] + sgn * np.sqrt(dy2)
            if fy0 <= y <= fy1:
                v, dd = nearest_label(np.array([xe, y]))
                if v is not None:
                    prows.append(dict(rho=rho, lat=v, d=dd))
P = pd.DataFrame(prows).sort_values('d').drop_duplicates('rho') if prows else pd.DataFrame(columns=['rho', 'lat'])
print('meridians labelled', len(M), '| parallels labelled', len(P))
print(M.sort_values('angle').to_string(index=False)[:1500])
print(P.sort_values('rho').to_string(index=False))
# east longitudes: labels are 0-180 without E/W; the map spans ~20E..190E, so values on the
# east side past 180 are 360-v (e.g. 174 on the right edge beyond the date line = 186E)
json.dump(dict(apex=list(map(float, apex)), meridians=M.to_dict('records'), parallels=P.to_dict('records'),
               frame=FRAME, inset=INSET), open(f'{OUT}/graticule_fit_input.json', 'w'), indent=1)
