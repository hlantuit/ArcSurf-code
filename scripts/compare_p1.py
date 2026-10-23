#!/usr/bin/env python
"""Pass-1 outputs of two dissolve runs, tile by tile: the same patches (key hash, attributes, exact geometry) and the
same piece -> patch map? (regression test of a change to dissolve_release.py that must not change results)
usage: compare_p1.py DIR_A DIR_B T1,T2,...|ALL   (ALL: every tile both runs have; only differing tiles are listed)"""
import glob
import os
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

A, B = sys.argv[1], sys.argv[2]
if sys.argv[3] == 'ALL':
    names = lambda d: {os.path.basename(f)[:-8] for f in glob.glob(f'{d}/p1/*.parquet') if not f.endswith('.map.parquet')}
    tiles = sorted(names(A) & names(B))
    quiet = True
else:
    tiles = sys.argv[3].split(',')
    quiet = False
bad = 0
for t in tiles:
    a = gpd.read_parquet(f'{A}/p1/{t}.parquet')
    b = gpd.read_parquet(f'{B}/p1/{t}.parquet')
    ma = pd.read_parquet(f'{A}/p1/{t}.map.parquet')
    mb = pd.read_parquet(f'{B}/p1/{t}.map.parquet')
    msg = []
    if len(a) != len(b):
        msg.append(f'patches {len(a)} vs {len(b)}')
    else:
        cols = [c for c in a.columns if c not in ('geometry',)]
        diffc = [c for c in cols if not a[c].astype(str).equals(b[c].astype(str))]
        if diffc:
            msg.append(f'attributes differ: {diffc}')
        eq = shapely.equals_exact(a.geometry.values, b.geometry.values, 0.0)
        if not eq.all():
            d = np.flatnonzero(~eq)
            sym = shapely.area(shapely.symmetric_difference(a.geometry.values[d], b.geometry.values[d]))
            msg.append(f'{len(d)} geometries not identical (symmetric difference {sym.sum():.4f} m2, max {sym.max():.4f})')
    if not ma.equals(mb):
        msg.append('piece -> patch map differs')
    bad += bool(msg)
    if msg or not quiet:
        print(t, 'IDENTICAL' if not msg else '; '.join(msg), flush=True)
print(f'{len(tiles)} tiles compared: ' + ('all identical' if not bad else f'{bad} tiles differ'))
