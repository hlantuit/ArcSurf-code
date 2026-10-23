#!/usr/bin/env python
"""Independent registration check of a re-registered 1:1M raster sheet against the 1:200k sheets
inside its frame (ru_vsegei200 + the 1:200k sheets of ru_vsegei_pdf; corner-read at ~17 m/px,
fit rms 1-50 m, i.e. registered independently of the 1:1M).

For each 1:200k sheet with >= 1000 km2 inside the 1:1M frame: both maps are rasterised as hclass
on a 250 m grid (EASE-Grid 2.0 N) and the 1:1M layer is shifted by up to +-R km; the agreement
(share of cells with the same hclass, both mapped) is computed per shift. A registration error
shows as an agreement peak AWAY from zero shift. Reported per reference sheet and per version
(OLD = work/jpgvec, NEW = work/g2_redo): agreement at zero shift, best shift (dx, dy km) and the
agreement there.
Null space: the two maps differ in generalisation and partly in interpretation; a flat
agreement surface (peak - zero < 1 point) means 'no measurable shift', not 'no error'.

usage: g2_shift_check.py <sheet> [--old PATH] [--new PATH] [--r-km 6] [--cell 250]"""
import argparse
import sys

import numpy as np
import pandas as pd
import pyogrio
import shapely
import geopandas as gpd
from rasterio.features import rasterize
from rasterio.transform import from_origin

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('sheet'); ap.add_argument('--old'); ap.add_argument('--new')
ap.add_argument('--r-km', type=float, default=6.0); ap.add_argument('--cell', type=float, default=250.0)
ap.add_argument('--min-km2', type=float, default=1000.0)
a = ap.parse_args()
ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
old = a.old or f'{ROOT}/work/jpgvec/{a.sheet}.gpkg'
new = a.new or f'{ROOT}/work/g2_redo/{a.sheet}.gpkg'
leg = pd.read_csv(f'{ROOT}/sources/legend_{a.sheet}.csv', dtype=str, keep_default_na=False)
h_of = dict(zip(leg['index'], leg['hclass'])); h_of['WATER'] = 'H'


def load(p):
    u = gpd.read_file(p, layer='units').to_crs(S.CRS)
    u['hclass'] = u['index'].map(h_of).fillna('')
    return u[u.hclass != '']


V = {'OLD': load(old), 'NEW': load(new)}
frame = gpd.read_file(new, layer='neatline').to_crs(S.CRS).geometry.values[0]
refs = []
for src in ('ru_vsegei200', 'ru_vsegei_pdf'):
    r = pyogrio.read_dataframe(f'{S.WORK}/xw/{src}.gpkg', layer='units', bbox=tuple(frame.bounds),
                               columns=['src_sheet', 'hclass', 'scale_den'])
    refs.append(r[r.scale_den == 200000])
ref = pd.concat(refs, ignore_index=True)
ref = gpd.GeoDataFrame(ref, geometry='geometry', crs=S.CRS)
codes = {c: i + 1 for i, c in enumerate(sorted(set(ref.hclass.dropna()) | set(V['OLD'].hclass) | set(V['NEW'].hclass)))}
R = int(round(a.r_km * 1000 / a.cell)); cs = a.cell
rows = []
for sh, g in ref.groupby('src_sheet'):
    fp = shapely.intersection(shapely.union_all(g.geometry.values), shapely.buffer(frame, -2 * a.r_km * 1000))
    if fp.is_empty or fp.area / 1e6 < a.min_km2:
        continue
    x0, y0, x1, y1 = fp.bounds
    x0 -= R * cs; y0 -= R * cs; x1 += R * cs; y1 += R * cs
    W = int(np.ceil((x1 - x0) / cs)); H = int(np.ceil((y1 - y0) / cs))
    tf = from_origin(x0, y1, cs, cs)
    gi = g[g.hclass.notna() & (g.hclass != '')]
    A = rasterize([(geom, codes[c]) for geom, c in zip(gi.geometry, gi.hclass)], out_shape=(H, W), transform=tf, fill=0, dtype='int16')
    inside = rasterize([(fp, 1)], out_shape=(H, W), transform=tf, fill=0, dtype='uint8').astype(bool)
    A[~inside] = 0
    out = dict(ref_sheet=sh, km2=round(fp.area / 1e6))
    for ver, u in V.items():
        uu = u[u.intersects(shapely.buffer(fp, R * cs))]
        B = rasterize([(geom, codes[c]) for geom, c in zip(uu.geometry, uu.hclass)], out_shape=(H, W), transform=tf, fill=0, dtype='int16')
        # B shifted by (dx, dy) cells: compare A[r, c] with B[r - dy, c - dx]; positive dx = 1:1M content moved east
        core = A[R:H - R, R:W - R]
        mask = core > 0
        best = (-1, 0, 0); zero = np.nan
        for dy in range(-R, R + 1):
            for dx in range(-R, R + 1):
                Bs = B[R - dy:H - R - dy, R - dx:W - R - dx]
                m = mask & (Bs > 0)
                n = m.sum()
                if n < 0.5 * mask.sum():
                    continue
                ag = float((core[m] == Bs[m]).mean())
                if dx == 0 and dy == 0:
                    zero = ag
                if ag > best[0]:
                    best = (ag, dx, dy)
        out[f'{ver}_zero'] = round(zero * 100, 1)
        out[f'{ver}_best'] = round(best[0] * 100, 1)
        # B at (r - dy, c - dx) matches A at (r, c): the 1:1M content must move by (+dx, -dy) cells (row axis points south)
        out[f'{ver}_dx_km'] = round(best[1] * cs / 1000, 2)
        out[f'{ver}_dy_km'] = round(-best[2] * cs / 1000, 2)
    rows.append(out)
df = pd.DataFrame(rows)
if df.empty:
    print(a.sheet, 'no 1:200k reference >= %d km2 inside the frame' % a.min_km2)
    sys.exit(0)
for ver in V:
    df[f'{ver}_shift_km'] = np.hypot(df[f'{ver}_dx_km'], df[f'{ver}_dy_km']).round(2)
pd.set_option('display.width', 250)
print(a.sheet)
print(df.to_string(index=False))
w = df.km2 / df.km2.sum()
print('area-weighted: OLD zero %.1f best %.1f |shift| median %.2f km;  NEW zero %.1f best %.1f |shift| median %.2f km' % (
    (df.OLD_zero * w).sum(), (df.OLD_best * w).sum(), df.OLD_shift_km.median(),
    (df.NEW_zero * w).sum(), (df.NEW_best * w).sum(), df.NEW_shift_km.median()))
df.to_csv(f'{ROOT}/work/g2_redo/{a.sheet}_shift.csv', index=False)
