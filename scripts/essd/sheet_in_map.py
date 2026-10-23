#!/usr/bin/env python
"""The pieces of one source sheet as they stand in the merged map (land only, after precedence), for a figure.
usage: sheet_in_map.py TILES_DIR SHEET NEATLINE_GPKG OUT.gpkg"""
import math
import os
import sys

import geopandas as gpd
import pandas as pd

TD, SHEET, NL, OUT = sys.argv[1:5]
nl = gpd.read_file(NL, layer='neatline').to_crs('EPSG:6931')
x0, y0, x1, y1 = nl.total_bounds
tiles = [f'{tx * 100:+06d}_{ty * 100:+06d}' for tx in range(math.floor(x0 / 1e5), math.floor(x1 / 1e5) + 1)
         for ty in range(math.floor(y0 / 1e5), math.floor(y1 / 1e5) + 1)]
parts = []
for t in tiles:
    f = f'{TD}/{t}.parquet'
    if os.path.exists(f):
        g = gpd.read_parquet(f, columns=['src_id', 'src_sheet', 'src_code', 'hclass', 'geometry'])
        parts.append(g)
g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs='EPSG:6931')
g = g[g.intersects(nl.geometry.iloc[0])]
g['this_sheet'] = (g['src_sheet'].astype(str) == SHEET).astype(int)
g.to_file(OUT, driver='GPKG')
print(len(tiles), 'tiles;', len(g), 'pieces in the frame;', int(g['this_sheet'].sum()), 'from', SHEET,
      '; other sources:', g.loc[g['this_sheet'] == 0, 'src_id'].value_counts().head(8).to_dict())
