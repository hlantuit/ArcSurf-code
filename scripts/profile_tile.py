#!/usr/bin/env python
"""Profile merge_tiles_test.do_tile on one tile: timestamps for every overlay call slower than 20 s and for the
post-processing steps (planarize, ice, zone splits). Writes to a scratch MERGE_TDIR. usage: profile_tile.py TILE_ID"""
import importlib.util
import json
import os
import sys
import tempfile
import time

os.environ['MERGE_TDIR'] = tempfile.mkdtemp(prefix='prof_', dir='/albedo/work/user/hlantuit/arctic_surficial/work')
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shapely  # noqa: E402
import pyogrio  # noqa: E402

spec = importlib.util.spec_from_file_location('mt', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                 'merge_tiles_test.py'))
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)
tid = sys.argv[1]
mt._init(json.load(open(f'{mt.S.WORK}/merge_sources.json')))
TG = pyogrio.read_dataframe(mt.LAND, layer='tiles', where=f"tile_id = '{tid}'").geometry.values[0]
T0 = time.time()


def stamp(msg):
    print(f'[{time.time() - T0:8.1f}s] {msg}', flush=True)


def _size(x):
    if isinstance(x, shapely.Geometry):
        return int(shapely.get_num_coordinates(x))
    if hasattr(x, '__len__') and not isinstance(x, str):
        try:
            return int(shapely.get_num_coordinates(list(x)).sum())
        except Exception:
            return len(x)
    return 0


def timed(name, fn, thresh=20.0):
    def w(*a, **kw):
        big = sum(_size(x) for x in a) > 200_000
        if big:                                     # announce big calls BEFORE they run: a hang shows up
            stamp(f'start {name} coords={[_size(x) for x in a]} kw={kw}')
        t = time.time()
        r = fn(*a, **kw)
        dt = time.time() - t
        if dt > thresh:
            n = [len(x) if hasattr(x, '__len__') and not isinstance(x, (str, shapely.Geometry)) else
                 (shapely.get_num_coordinates(x) if isinstance(x, shapely.Geometry) else '-') for x in a]
            stamp(f'{name} took {dt:.1f}s args={n}')
        return r
    return w


for n in ('_sinter', '_sdiff', '_sunion'):
    setattr(mt, n, timed(n, getattr(mt, n)))
for n in ('_planarize', 'split_by_zone', 'split_by_yedoma'):
    setattr(mt, n, timed(n, getattr(mt, n), thresh=5.0))
mt.IA.apply_ice = timed('apply_ice', mt.IA.apply_ice, thresh=1.0)
stamp('start')
print(mt.do_tile((tid, TG)))
stamp('done')
