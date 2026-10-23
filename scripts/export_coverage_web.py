"""Export for the interactive coverage artifact:
- out/web/coverage.png : best-scale class grid (the coverage_map grid), 1 px per cell, class
  id encoded in the red channel (0 sea/outside, 1..6 classes), downsampled to 5 km
- out/web/sheets.json  : every source sheet footprint (work/xw/*.gpkg footprint layer),
  simplified to ~3 km, in EPSG:6931 km, with product, sheet, scale, year, licence, km2
- out/web/amap.json    : AMAP boundary, and a coarse land outline for context
Coordinates are kept in EPSG:6931 (km) so the page draws them with a linear transform."""
import glob
import json
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import pyogrio  # noqa: E402
from PIL import Image  # noqa: E402
import coverage_map as CM  # noqa: E402

OUT = f'{S.OUT}/web'
os.makedirs(OUT, exist_ok=True)
TITLES = {}
for f in glob.glob(f'{S.WORK}/std/*.json'):
    try:
        TITLES[os.path.basename(f)[:-5]] = json.load(open(f)).get('title', '')
    except Exception:
        pass


def coords(g, tol):
    g = shapely.simplify(g, tol)
    out = []
    for p in shapely.get_parts(g):
        if p.geom_type != 'Polygon' or p.area < (tol * tol * 4):
            continue
        ring = np.round(np.asarray(p.exterior.coords) / 1000, 1).tolist()
        out.append(ring)
    return out


sheets = []
for f in sorted(glob.glob(f'{S.WORK}/xw/*.gpkg')):
    src = os.path.basename(f)[:-5]
    try:
        fp = gpd.read_file(f, layer='footprint').to_crs(S.CRS)
    except Exception:
        continue
    for _, r in fp.iterrows():
        if r.geometry is None or r.geometry.is_empty:
            continue
        rings = coords(r.geometry, 3000 if r.geometry.area > 5e10 else 1500)
        if not rings:
            continue
        sheets.append(dict(src=src, title=TITLES.get(src, ''), sheet=str(r.get('src_sheet') or ''),
                           scale=int(r['scale_den']) if 'scale_den' in fp and r['scale_den'] == r['scale_den'] else None,
                           year=int(r['pub_year']) if 'pub_year' in fp and r['pub_year'] == r['pub_year'] else None,
                           overlay=int(r.get('overlay') or 0), km2=round(r.geometry.area / 1e6), rings=rings))
# licence per source from the units layer
lic = {}
for f in glob.glob(f'{S.WORK}/xw/*.gpkg'):
    try:
        d = pyogrio.read_dataframe(f, layer='units', columns=['licence', 'redistribution'], read_geometry=False, max_features=1)
        lic[os.path.basename(f)[:-5]] = (str(d.licence.iat[0]), str(d.redistribution.iat[0]))
    except Exception:
        pass
for s in sheets:
    s['licence'], s['redist'] = lic.get(s['src'], ('', ''))
print('sheets', len(sheets), flush=True)
json.dump(sheets, open(f'{OUT}/sheets.json', 'w'), separators=(',', ':'))

# coverage grid at 5 km from the tiles (reuse coverage_map's per-tile rasteriser)
from multiprocessing import Pool  # noqa: E402
files = sorted(glob.glob(f'{S.WORK}/tiles/*.parquet'))
with Pool(32) as p:
    res = p.map(CM.one, files)
grid = np.zeros((CM.NR, CM.NC), np.uint8)
for _, (r0, c0, arr) in res:
    h, w = arr.shape
    rs, cs = max(r0, 0), max(c0, 0)
    sub = arr[rs - r0:min(h, CM.NR - r0), cs - c0:min(w, CM.NC - c0)]
    tgt = grid[rs:rs + sub.shape[0], cs:cs + sub.shape[1]]
    np.copyto(tgt, sub, where=sub > 0)
k = 2                                          # 2.5 km -> 5 km, keep the finest class present
H, W = grid.shape[0] // k * k, grid.shape[1] // k * k
g = grid[:H, :W].reshape(H // k, k, W // k, k).transpose(0, 2, 1, 3).reshape(H // k, W // k, k * k)
g = np.where(g == 0, 99, g).min(-1)
g[g == 99] = 0
rgb = np.zeros(g.shape + (3,), np.uint8); rgb[..., 0] = g
Image.fromarray(rgb).save(f'{OUT}/coverage.png', optimize=True)
amap = CM.AMAP.geometry.values[0]
meta = dict(x0=CM.GX0 / 1000, y1=CM.GY1 / 1000, cell_km=CM.RES * k / 1000, w=int(g.shape[1]), h=int(g.shape[0]),
            classes=[c[0] for c in CM.CLASSES], colours=[c[3] for c in CM.CLASSES], amap=coords(amap, 5000))
json.dump(meta, open(f'{OUT}/meta.json', 'w'), separators=(',', ':'))
print('grid', g.shape, 'written', OUT)
