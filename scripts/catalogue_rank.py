"""Rank every GSC catalogue map that is NOT in a merged source by what its bbox would add on the current merged
layer (out/coverage_class.tif): land cells coarser than the map's scale class (gain) and cells now at >= 1:2.5M
(gain_coarse). Records the files on disk (raw/canada/gsc_scans/<label>, raw/canada/gsc/<label>) and their kind.
usage: catalogue_rank.py   -> work/catalogue_rank.csv"""
import glob
import json
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import rasterio
import shapely

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SCR = '/albedo/scratch/user/hlantuit/arctic_surficial'
cat = json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']
done = set()
for f in glob.glob(f'{ROOT}/work/xw/ca_*.gpkg'):
    try:
        done |= set(gpd.read_file(f, layer='footprint', ignore_geometry=True)['src_sheet'].astype(str).str.split('_').str[0])
    except Exception:
        pass
r = rasterio.open(f'{ROOT}/out/coverage_class.tif'); g = r.read(1); tf = r.transform
tr = pyproj.Transformer.from_crs(4326, r.crs, always_xy=True)
geod = pyproj.Geod(ellps='WGS84')


def pclass(sc):
    return 1 if sc <= 100_000 else 2 if sc <= 260_000 else 3 if sc <= 700_000 else 4 if sc <= 1_500_000 else 5


rows = []
for s in cat:
    lab = s['label']
    if lab in done or not s.get('bbox_wgs84'):
        continue
    w, so, e, n = s['bbox_wgs84']
    lo, la = np.meshgrid(np.linspace(w, e, 120), np.linspace(so, n, 120))
    x, y = tr.transform(lo.ravel(), la.ravel())
    rr, cc = rasterio.transform.rowcol(tf, x, y)
    rr, cc = np.array(rr), np.array(cc)
    ok = (rr >= 0) & (rr < g.shape[0]) & (cc >= 0) & (cc < g.shape[1])
    v = np.zeros(len(rr), np.uint8); v[ok] = g[rr[ok], cc[ok]]
    per = abs(geod.geometry_area_perimeter(shapely.box(w, so, e, n))[0]) / 1e6 / len(v)
    pc = pclass(s.get('scale') or 10**9)
    files = []
    for d in (f'{ROOT}/raw/canada/gsc_scans/{lab}', f'{SCR}/raw/canada/gsc_scans/{lab}', f'{ROOT}/raw/canada/gsc/{lab}'):
        files += [os.path.basename(f) for f in glob.glob(d + '/*')]
    kind = ('vector' if s.get('vector') else 'zip' if any(f.endswith('.zip') for f in files) else
            'jp2' if any(f.endswith('.jp2') for f in files) else 'pdf' if any(f.endswith('.pdf') for f in files) else 'none')
    rows.append(dict(label=lab, scale=s.get('scale'), year=str(s.get('release', ''))[:4], kind=kind,
                     land_km2=round(float((v > 0).sum() * per)), gain_km2=round(float(((v > pc) & (v > 0)).sum() * per)),
                     gain_coarse_km2=round(float((v == 5).sum() * per)), title=s['title'][:90], files=';'.join(sorted(set(files)))[:120]))
df = pd.DataFrame(rows).sort_values(['gain_coarse_km2', 'gain_km2'], ascending=False)
df.to_csv(f'{ROOT}/work/catalogue_rank.csv', index=False)
print(f'{len(df)} unmerged catalogue maps; with gain_coarse > 1000 km2: {(df.gain_coarse_km2 > 1000).sum()}, '
      f'sum {df[df.gain_coarse_km2 > 1000].gain_coarse_km2.sum() / 1e3:.0f}k km2 (bbox-based, overlapping maps double-count)')
pd.set_option('display.width', 230); pd.set_option('display.max_colwidth', 70)
print(df.head(40)[['label', 'scale', 'year', 'kind', 'land_km2', 'gain_coarse_km2', 'title']].to_string(index=False))
