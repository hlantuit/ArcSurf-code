"""Catalogue entries -> title, scale, type, files on disk, and what their bbox would add on the current coverage
(out/coverage_class.tif: land cells coarser than the product's scale class; cells at >= 1:2.5M).
usage: catalogue_gain.py LABEL [LABEL ...]"""
import glob
import json
import os
import sys

import numpy as np
import pyproj
import rasterio

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SC = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada'
cat = {s['label']: s for s in json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']}
r = rasterio.open(f'{ROOT}/out/coverage_class.tif'); g = r.read(1); tf = r.transform
tr = pyproj.Transformer.from_crs(4326, r.crs, always_xy=True)
cell = abs(tf.a * tf.e) / 1e6


def pclass(sc):
    return 1 if sc <= 100_000 else 2 if sc <= 260_000 else 3 if sc <= 700_000 else 4 if sc <= 1_500_000 else 5


for lab in sys.argv[1:]:
    s = cat.get(lab)
    if not s:
        print(lab, 'not in catalogue'); continue
    w, so, e, n = s['bbox_wgs84']
    lo, la = np.meshgrid(np.linspace(w, e, 200), np.linspace(so, n, 200))
    x, y = tr.transform(lo.ravel(), la.ravel())
    rr, cc = rasterio.transform.rowcol(tf, x, y)
    rr, cc = np.array(rr), np.array(cc)
    ok = (rr >= 0) & (rr < g.shape[0]) & (cc >= 0) & (cc < g.shape[1])
    v = g[rr[ok], cc[ok]]
    # bbox area from the grid samples (each sample = bbox_area / n)
    area = abs(pyproj.Geod(ellps='WGS84').geometry_area_perimeter(
        __import__('shapely').box(w, so, e, n))[0]) / 1e6
    per = area / len(lo.ravel())
    pc = pclass(s['scale'] or 10**9)
    gain = float(((v > pc) & (v > 0)).sum() * per); coarse = float((v == 5).sum() * per); land = float((v > 0).sum() * per)
    files = [os.path.basename(f) for d in (f"{SC}/gsc_scans/{lab}", f"{SC}/gsc/{lab}", f"{ROOT}/raw/canada/gsc/{lab}", f"{ROOT}/raw/canada/gsc_scans/{lab}")
             for f in glob.glob(d + '/*')]
    print(f"{lab:8s} 1:{s['scale']:<8} {s['release'][:4]} vec={s['vector']!s:5} land {land:7.0f} gain {gain:7.0f} >=2.5M {coarse:7.0f} km2 | "
          f"{s['title'][:70]} | files: {', '.join(files[:3]) or '-'}")
