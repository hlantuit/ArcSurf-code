#!/usr/bin/env python
"""Check of the dissolved release (dissolve_release.py) in OUT:
  - asid: unique, 1..N without gaps; every piece of piece_asid.parquet points to an existing asid
  - residual: pairs of final polygons with the same KEY that still run along each other within 1 cm for more than
    1 m (the dissolve should have merged them; point contacts are allowed). Candidates come from envelopes, so the
    check stays affordable on the full domain (13 M polygons).
  - overlap (--overlap, small tests only): total area shared by two final polygons; mm slivers where a snap moved
    vertices. On the full domain the overlay of every touching pair of large polygons ran out of memory.
--pieces TILES: the same checks on the pieces of the tiled version (a baseline), for these comma-separated tiles.
usage: dissolve_check.py OUT [--overlap] [--pieces T1,T2] [--workers N]"""
import argparse
import glob
from multiprocessing import Pool

import numpy as np
import pandas as pd
import geopandas as gpd
import pyarrow.parquet as pq
import shapely

import dissolve_release as D


def _contact(job):
    """length (m) along which b's boundary runs within 1 cm of a's"""
    wa, wb = job
    a, b = shapely.from_wkb(wa), shapely.from_wkb(wb)
    return shapely.length(shapely.intersection(shapely.boundary(b), shapely.buffer(shapely.boundary(a), D.TOL)))


def _overlap(job):
    wa, wb = job
    a, b = shapely.from_wkb(wa), shapely.from_wkb(wb)
    inner = shapely.relate_pattern(a, b, '2********')          # interiors overlap: only these get an overlay
    ov = np.zeros(len(a))
    if inner.any():
        ov[inner] = shapely.area(shapely.intersection(a[inner], b[inner]))
    return float(ov.sum()), int((ov > 0.01).sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--overlap', action='store_true')
    ap.add_argument('--pieces')
    ap.add_argument('--workers', type=int, default=32)
    a = ap.parse_args()
    if a.pieces:
        F = pd.concat([gpd.read_parquet(f'{a.out}/{t}.parquet') for t in a.pieces.split(',')], ignore_index=True)
        print(f'pieces {len(F):,} (baseline, tiled version)', flush=True)
    else:
        fs = sorted(glob.glob(f'{a.out}/final/*.parquet'))
        F = pd.concat([gpd.read_parquet(f) for f in fs], ignore_index=True)
        asid = F['asid'].to_numpy()
        u = np.unique(asid)
        print(f'final polygons {len(F):,}; asid unique {len(u) == len(asid)}; range {asid.min()}..{asid.max()}; '
              f'gaps {int(asid.max() - len(u))}', flush=True)
        pa = pq.read_table(f'{a.out}/piece_asid.parquet', columns=['asid']).column('asid').to_numpy()
        print(f'pieces {len(pa):,}; pointing to a missing asid {int((~np.isin(pa, u)).sum())}; '
              f'final polygons without a piece {len(u) - len(np.unique(pa))}', flush=True)
    kh = D.khash(F)
    g = np.asarray(F.geometry.values, dtype=object)
    i, j = D._near_pairs(g, kh)
    print(f'same-KEY pairs within {D.TOL} m: {len(i):,}', flush=True)
    wk = shapely.to_wkb(g)
    step = 2000
    with Pool(a.workers) as pool:
        L = np.concatenate([np.asarray(x) for x in pool.imap(
            _contact, ((wk[i[k:k + step]], wk[j[k:k + step]]) for k in range(0, len(i), step)))] or [np.zeros(0)])
    print(f'residual same-KEY contacts longer than 1 m: {int((L > 1.0).sum()):,} (longest {L.max(initial=0):.2f} m)',
          flush=True)
    if a.overlap:
        ii, jj = shapely.STRtree(g).query(g, predicate='intersects')
        m = ii < jj
        ii, jj = ii[m], jj[m]
        with Pool(a.workers) as pool:
            res = list(pool.imap(_overlap, ((wk[ii[k:k + step]], wk[jj[k:k + step]])
                                            for k in range(0, len(ii), step))))
        print(f'touching pairs {len(ii):,}; overlap total {sum(r[0] for r in res):,.3f} m2 in '
              f'{sum(r[1] for r in res):,} pairs (> 0.01 m2)', flush=True)


if __name__ == '__main__':
    main()
