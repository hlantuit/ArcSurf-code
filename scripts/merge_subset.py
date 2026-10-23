#!/usr/bin/env python
"""Partial re-merge: only the tiles within 1 km of the footprints of the listed sources are merged again (the merge
claims a source's footprint buffered by 0.5 mm at its scale, 500 m at 1:1M); every other tile of work/tiles stays
as it is. The old versions of those tiles are moved to work/old/tiles_<tag>/ first; snapshots such as final_m43
keep their own hard links. The merge uses every source of work/merge_sources.json plus the listed ones, so a new
source joins the list (merge_tiles.py rewrites the json at the end).
First use: merge 44 (2026-10-07), GSC Map 1814A from the GSC release (ca_gsc_1814a) replacing the GeoAtlas copy
of it (ca_nl_labrador layer 12).
usage: merge_subset.py <tag> <src,src,...>"""
import json
import os
import subprocess
import sys

import pyogrio
import shapely

import surflib as S

tag, srcs = sys.argv[1], sys.argv[2].split(',')
geoms = []
for s in srcs:
    geoms.extend(pyogrio.read_dataframe(f'{S.WORK}/xw/{s}.gpkg', layer='footprint').geometry.values)
fp = shapely.union_all(shapely.make_valid(geoms))
shapely.prepare(fp)
tiles = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='tiles')
hit = sorted(tiles.loc[shapely.dwithin(tiles.geometry.values, fp, 1000.0), 'tile_id'])
old = f'{S.WORK}/old/tiles_{tag}'
os.makedirs(old, exist_ok=True)
moved = 0
for t in hit:
    p = f'{S.WORK}/tiles/{t}.parquet'
    if os.path.exists(p):
        os.replace(p, f'{old}/{t}.parquet')
        moved += 1
open(f'{S.WORK}/{tag}_tiles.txt', 'w').write('\n'.join(hit) + '\n')
src = json.load(open(f'{S.WORK}/merge_sources.json'))
src += [s for s in srcs if s not in src]
print(f'{tag}: {len(hit)} tiles within 1 km of {srcs}; {moved} old tiles moved to {old}; '
      f'merging with {len(src)} sources', flush=True)
# '--only=...' in one token: tile ids such as '-01900_-01700' start with '-', and argparse takes a separate value
# that starts with '-' for an option (merge 44's first run stopped there, after moving the old tiles)
r = subprocess.run([sys.executable, 'merge_tiles.py', ','.join(src), f'--only={",".join(hit)}'])
sys.exit(r.returncode)
