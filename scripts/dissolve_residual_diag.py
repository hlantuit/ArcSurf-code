#!/usr/bin/env python
"""Diagnose same-KEY final polygons that still run within 1 cm of each other (dissolve_check 'residual'):
for the longest such pairs print asid, rep tiles, n_pieces / n_tiles, the contact length, their distance, whether
they intersect, the DE-9IM relate string before and after snapping b to a, and the float union's part count.
usage: dissolve_residual_diag.py OUT [N]"""
import glob
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

import dissolve_release as D

out = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 15
F = pd.concat([gpd.read_parquet(f) for f in sorted(glob.glob(f'{out}/final/*.parquet'))], ignore_index=True)
kh = D.khash(F)
g = np.asarray(F.geometry.values, dtype=object)
i, j = shapely.STRtree(g).query(g, predicate='dwithin', distance=D.TOL)
m = (i < j) & (kh[i] == kh[j])
i, j = i[m], j[m]
L = shapely.length(shapely.intersection(shapely.boundary(g[j]), shapely.buffer(shapely.boundary(g[i]), D.TOL)))
o = np.argsort(-L)
print(f'same-KEY pairs within 1 cm: {len(i):,}; with contact > 1 m: {int((L > 1).sum()):,}')
for k in o[:N]:
    a, b = g[i[k]], g[j[k]]
    ra = shapely.relate(a, b)
    rs = shapely.relate(a, shapely.snap(b, a, D.TOL))
    u = D._polys(shapely.union_all([a, b]))
    us = D._polys(shapely.union_all([a, shapely.snap(b, a, D.TOL)]))
    print(f'asid {F.asid[i[k]]} ({F.rep_tile[i[k]]}, n_pieces {F.n_pieces[i[k]]}, n_tiles {F.n_tiles[i[k]]}) x '
          f'asid {F.asid[j[k]]} ({F.rep_tile[j[k]]}, n_pieces {F.n_pieces[j[k]]}, n_tiles {F.n_tiles[j[k]]}): '
          f'contact {L[k]:.2f} m, distance {shapely.distance(a, b):.2e} m, intersects {shapely.intersects(a, b)}, '
          f'relate {ra} snapped {rs}, union parts {len(u)} / after snap {len(us)}; hclass {F.hclass[i[k]]} '
          f'src {F.src_id[i[k]]}', flush=True)
