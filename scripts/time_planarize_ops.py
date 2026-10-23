#!/usr/bin/env python
"""Time the candidate _planarize operations on the real giant polygon of tile -01900_-00300 (merge 43, exact old
version): difference(small, giant) with and without a box pre-clip, clip_by_rect vs intersection(giant, box), and
prepared-geometry tests, on the 200 small polygons nearest to the giant's interior. usage: time_planarize_ops.py"""
import sys
import time

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

t = gpd.read_parquet('/albedo/work/user/hlantuit/arctic_surficial/work/tiles/-01900_-00300.parquet')
g = t.geometry.values
nc = shapely.get_num_coordinates(g)
gi = int(np.argmax(nc))
giant = g[gi]
print('giant', gi, t.iloc[gi][['src_id', 'hclass']].tolist(), 'coords', int(nc[gi]), 'area km2',
      round(giant.area / 1e6, 1), 'holes', shapely.get_num_interior_rings(giant), flush=True)
# small polygons whose bbox intersects the giant's bbox (as the losers are)
tree = shapely.STRtree(g)
cand = tree.query(giant)
cand = [i for i in cand if i != gi and nc[i] < 2000][:200]
small = g[cand]
print('test polygons', len(small), flush=True)


def tm(name, fn, n=len(small)):
    t0 = time.time()
    out = fn()
    dt = time.time() - t0
    print(f'{name:45s} {dt:8.3f} s total  {1000 * dt / n:8.2f} ms each', flush=True)
    return out


boxes = shapely.box(*shapely.bounds(small).T)
r1 = tm('difference(small, giant)', lambda: [shapely.difference(s, giant) for s in small])
r2 = tm('intersection(giant, box) + difference', lambda: [shapely.difference(s, shapely.intersection(giant, b))
                                                          for s, b in zip(small, boxes)])
r3 = tm('clip_by_rect(giant, box) + difference', lambda: [shapely.difference(s, shapely.make_valid(
    shapely.clip_by_rect(giant, *shapely.bounds(s)))) for s in small])
shapely.prepare(giant)
tm('prepared covers(giant, small)', lambda: [giant.covers(s) for s in small])
tm('prepared intersects(giant, small)', lambda: [giant.intersects(s) for s in small])
a1, a2, a3 = (np.array([x.area for x in r]) for r in (r1, r2, r3))
print('area diff |exact - box-intersection| max m2', float(np.abs(a1 - a2).max()),
      ' |exact - clip_by_rect| max m2', float(np.abs(a1 - a3).max()), flush=True)
# one-time subdivision of the giant into grid cells, then difference against the touching cells only
t0 = time.time()
x0, y0, x1, y1 = giant.bounds
step = 2000.0
xs, ys = np.arange(x0, x1, step), np.arange(y0, y1, step)
cells = shapely.box(*np.array([(x, y, x + step, y + step) for x in xs for y in ys]).T)
pieces = shapely.intersection(giant, cells)
pieces = pieces[~shapely.is_empty(pieces)]
print(f'subdivide giant into {len(pieces)} cells of {step / 1000:.0f} km: {time.time() - t0:.2f} s', flush=True)
ptree = shapely.STRtree(pieces)


def via_cells():
    out = []
    for s in small:
        idx = ptree.query(s)
        out.append(shapely.difference(s, shapely.union_all(pieces[idx])) if len(idx) else s)
    return out


r4 = tm('difference against touching cells', via_cells)
a4 = np.array([x.area for x in r4])
print('area diff |exact - cells| max m2', float(np.abs(a1 - a4).max()), flush=True)
