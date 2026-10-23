#!/usr/bin/env python
"""
Island coverage report (owed since 2026-09-30; island_coverage.py timed out unioning tile-diced
land pieces). Raster approach: OSM land (work/land_amap.gpkg 'land') rasterised at RES over the
Canadian Arctic Archipelago, 8-connected components = islands (500 m keeps Bellot Strait, ~2 km,
open between Somerset and Boothia), each island picked by a seed point; the collected merge
(out/arctic_surficial_geology.gpkg 'surficial') burnt finest-scale-last at the same grid, with the
source of the finest polygon per cell. Writes work/island_coverage2.json and prints a table.
"""
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
import rasterio.features as rf  # noqa: E402
from affine import Affine  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
from pyproj import Transformer  # noqa: E402
import surflib as S  # noqa: E402

RES = 500.0
SEEDS = {'Baffin': (-70.5, 68.5), 'Ellesmere': (-80.0, 80.0), 'Southampton': (-84.5, 64.5),
         'Somerset': (-93.5, 73.0), 'Prince Patrick': (-119.5, 76.6), 'Ellef Ringnes': (-102.5, 78.6)}
CLASSES = [('<=1:100k', 0, 100_000), ('1:125k-1:250k', 100_001, 260_000), ('1:500k-1:600k', 260_001, 700_000),
           ('1:1M', 700_001, 1_500_000), ('>=1:2.5M', 1_500_001, 10**9)]
tr = Transformer.from_crs(4326, S.CRS, always_xy=True)
xs, ys = tr.transform(np.array([-125, -125, -60, -60, -95]), np.array([61, 84, 61, 84, 61]))
# the box in lon/lat is curved in EASE north: bound it by many points along its edges
ll = [(lo, la) for lo in np.linspace(-125, -60, 60) for la in (61, 84)] + [(lo, la) for la in np.linspace(61, 84, 40) for lo in (-125, -60)]
X, Y = tr.transform(*np.array(ll).T)
x0, y0, x1, y1 = X.min(), Y.min(), X.max(), Y.max()
W, H = int((x1 - x0) / RES) + 1, int((y1 - y0) / RES) + 1
tf = Affine(RES, 0, x0, 0, -RES, y1)
print('grid', W, H, flush=True)
land = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='land', bbox=(x0, y0, x1, y1)).to_crs(S.CRS)
L = rf.rasterize(((g, 1) for g in land.geometry.values), out_shape=(H, W), transform=tf, fill=0, dtype='uint8')
lab, n = ndi.label(L, structure=np.ones((3, 3), bool))
print('land components', n, flush=True)
m = pyogrio.read_dataframe(f'{S.OUT}/arctic_surficial_geology.gpkg', layer='surficial', bbox=(x0, y0, x1, y1),
                           columns=['src_id', 'src_sheet', 'scale_den', 'hclass'])
m = m[m.scale_den.notna()]
m['scale_den'] = m.scale_den.astype(float)
print('merged polygons in box', len(m), flush=True)
src_codes = {s: i + 1 for i, s in enumerate(sorted(m.src_id.unique()))}
order = np.argsort(-m.scale_den.to_numpy())               # coarse first, fine last (finest wins)
SC = rf.rasterize(((m.geometry.iat[i], int(m.scale_den.iat[i])) for i in order), out_shape=(H, W), transform=tf, fill=0, dtype='int32')
SR = rf.rasterize(((m.geometry.iat[i], src_codes[m.src_id.iat[i]]) for i in order), out_shape=(H, W), transform=tf, fill=0, dtype='int32')
inv = {v: k for k, v in src_codes.items()}
out = {}
for name, (lo, la) in SEEDS.items():
    sx, sy = tr.transform(lo, la)
    c, r = int((sx - x0) / RES), int((y1 - sy) / RES)
    comp = lab[r, c]
    if comp == 0:                                          # seed on water: nearest land cell
        rr, cc = np.nonzero(lab[max(r - 40, 0):r + 40, max(c - 40, 0):c + 40])
        k = np.argmin((rr - 40) ** 2 + (cc - 40) ** 2); comp = lab[max(r - 40, 0) + rr[k], max(c - 40, 0) + cc[k]]
    msk = lab == comp
    km2 = float(msk.sum() * RES * RES / 1e6)
    s = SC[msk]
    by = {cn: round(float(((s >= lo_) & (s <= hi_)).sum() * RES * RES / 1e6)) for cn, lo_, hi_ in CLASSES}
    by['unmapped'] = round(float((s == 0).sum() * RES * RES / 1e6))
    srcs = pd.Series(SR[msk]).map(inv).value_counts()
    out[name] = dict(km2=round(km2), by_class=by,
                     top_sources={k: round(float(v * RES * RES / 1e6)) for k, v in srcs.head(5).items()})
    print(f'{name:15s} {km2:9.0f} km2 |', ' '.join(f'{k} {v}' for k, v in by.items()), '|', out[name]['top_sources'], flush=True)
json.dump(out, open(f'{S.WORK}/island_coverage2.json', 'w'), indent=1)
