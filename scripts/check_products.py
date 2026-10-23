"""Is a GSC product in our catalogue (sources/canada_gsc_sheets.json) and in a merged source (xw/ca_*.gpkg)?
usage: check_products.py LABEL [LABEL ...]"""
import glob
import json
import sys

import geopandas as gpd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
cat = {s['label']: s for s in json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']}
done = {}
for f in glob.glob(f'{ROOT}/work/xw/ca_*.gpkg'):
    try:
        fp = gpd.read_file(f, layer='footprint', ignore_geometry=True)
    except Exception:
        continue
    for s in fp['src_sheet'].astype(str):
        done.setdefault(s.split('_')[0], set()).add(f.split('/')[-1][:-5])
for lab in sys.argv[1:]:
    c = cat.get(lab)
    cs = f"1:{c['scale']} {c['release'][:4]} bbox={c['bbox_wgs84']}" if c else 'NO'
    print(f'{lab:8s} catalogue: {cs} | merged: {sorted(done.get(lab, [])) or "NO"}')
