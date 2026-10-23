#!/usr/bin/env python
"""Which sources hold the footprints of the USGS Siberian database sheets (ru_bryant_vsegei1m) in the merged map:
area by source sheet, scale and year inside each Bryant sheet's footprint (Bryant has no publication year, so every
dated 1:1M sheet outranks it in the merge).
usage: bryant_precedence.py TILES_DIR XW_GPKG OUT.csv"""
import math
import os
import sys

import geopandas as gpd
import pandas as pd
import pyogrio

TD, XW, OUT = sys.argv[1:4]
print(pyogrio.list_layers(XW))
lay = [l for l, _ in pyogrio.list_layers(XW)]
fp = gpd.read_file(XW, layer='footprint' if 'footprint' in lay else lay[0])
print(fp.columns.tolist(), len(fp))
key = 'src_sheet' if 'src_sheet' in fp else ('sheet' if 'sheet' in fp else None)
fp = fp.to_crs('EPSG:6931')
if key:
    fp = fp.dissolve(by=key).reset_index()
rows = []
for r in fp.itertuples():
    geom = r.geometry
    x0, y0, x1, y1 = geom.bounds
    tiles = [f'{tx * 100:+06d}_{ty * 100:+06d}' for tx in range(math.floor(x0 / 1e5), math.floor(x1 / 1e5) + 1)
             for ty in range(math.floor(y0 / 1e5), math.floor(y1 / 1e5) + 1)]
    parts = [gpd.read_parquet(f'{TD}/{t}.parquet', columns=['src_id', 'src_sheet', 'scale_den', 'pub_year', 'geometry'])
             for t in tiles if os.path.exists(f'{TD}/{t}.parquet')]
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs='EPSG:6931')
    g = g[g.intersects(geom)]
    g['a'] = g.geometry.intersection(geom).area / 1e6
    s = g.groupby(['src_id', 'src_sheet', 'scale_den', 'pub_year'], dropna=False)['a'].sum().reset_index()
    s.insert(0, 'bryant_sheet', getattr(r, key) if key else r.Index)
    s['footprint_km2'] = geom.area / 1e6
    rows.append(s)
    top = s.sort_values('a', ascending=False).head(6)
    print(f'== {s["bryant_sheet"].iloc[0]} footprint {geom.area / 1e6:,.0f} km2')
    print(top[['src_id', 'src_sheet', 'scale_den', 'pub_year', 'a']].round(0).to_string(index=False))
pd.concat(rows).to_csv(OUT, index=False)
