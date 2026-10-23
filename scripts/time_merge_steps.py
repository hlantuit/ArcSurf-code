#!/usr/bin/env python
"""Timing of the new merge steps on a dense tile (merge-42 output as input): union with / without the 1 cm grid,
and the whole-tile _planarize. usage: time_merge_steps.py TILE_ID"""
import importlib.util
import os
import sys
import time

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

spec = importlib.util.spec_from_file_location('mt', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                 'merge_tiles_test.py'))
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)
tid = sys.argv[1]
t = gpd.read_parquet(f'/albedo/work/user/hlantuit/arctic_surficial/work/a0_tiles_m42/{tid}.parquet')
g = t.geometry.values
print(tid, 'polygons', len(t), 'vertices', int(shapely.get_num_coordinates(g).sum()), flush=True)
t0 = time.time(); u1 = shapely.union_all(g); print('union_all float   ', round(time.time() - t0, 1), 's', flush=True)
t0 = time.time(); u2 = shapely.union_all(g, grid_size=0.01); print('union_all grid 1cm', round(time.time() - t0, 1), 's', flush=True)
sub = g[: len(g) // 4]
t0 = time.time(); shapely.intersection(sub, u1); print('intersect 1/4 float', round(time.time() - t0, 1), 's', flush=True)
t0 = time.time(); shapely.intersection(sub, u1, grid_size=0.01); print('intersect 1/4 grid ', round(time.time() - t0, 1), 's', flush=True)
t0 = time.time(); r = mt._planarize(t, np.arange(len(t), dtype=float)); print('planarize(tile)   ', round(time.time() - t0, 1), 's', len(r), flush=True)
