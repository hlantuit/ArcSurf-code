#!/usr/bin/env python
"""Check of the dissolved release (dissolve_release.py) in OUT:
  - asid: unique, 1..N without gaps; every piece of piece_asid.parquet points to an existing asid
  - residual: pairs of final polygons with the same KEY that still run along each other within 1 cm for more than
    1 m (the dissolve should have merged them; point contacts are allowed). Candidates come from envelopes, so the
    check stays affordable on the full domain (13 M polygons). Both boundaries of a pair are clipped to the pair's
    common box before the 1 cm buffer: nowhere else can they run within 1 cm of each other, so the length is the
    same, but a large polygon is no longer buffered whole once for each of its neighbours. Merge 47: a task of 2,000
    pairs could hold 2,000 decoded copies of one large polygon, the job reached its 200 GB, the kernel killed 9
    workers, and Pool, which never re-runs a killed worker's task, waited until the time limit. Each geometry is now
    decoded once per task, and a worker that dies stops the check (BrokenProcessPool) instead of hanging it.
  - overlap (--overlap, small tests only): total area shared by two final polygons; mm slivers where a snap moved
    vertices. On the full domain the overlay of every touching pair of large polygons ran out of memory.
--pieces TILES: the same checks on the pieces of the tiled version (a baseline), for these comma-separated tiles.
--only TILES: the final polygons of these tiles only (tests; no asid checks).
--compare N: also the former length (whole boundaries) for N random pairs of at most 20,000 vertices together (the
  former method on large polygons is what made the check unaffordable: 1,000 random pairs of the 12 largest tiles
  did not finish in 2 h) and for the 20 longest residual pairs; exit 1 if any differs by more than 1 cm or the two
  disagree on a pair over 1 m.
--csv PATH: every residual pair (longer than 1 m) with both polygons' asid, tile, source, sheet, hclass, pieces, tiles
  and vertices.
usage: dissolve_check.py OUT [--overlap] [--pieces T1,T2] [--only T1,T2] [--compare N] [--csv PATH] [--workers N]"""
import argparse
import glob
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Pool

import numpy as np
import pandas as pd
import geopandas as gpd
import pyarrow.parquet as pq
import shapely

import dissolve_release as D

STEP = 2000       # pairs per task
MARGIN = 1.0      # m around a pair's common box: any margin >= 0 gives the same length; this one keeps the contacts
                  # clear of the clip edges


def _tasks(i, j, wk):
    """STEP pairs per task; a task carries each of its geometries once (ia, ib index into them)"""
    for k in range(0, len(i), STEP):
        ic, jc = i[k:k + STEP], j[k:k + STEP]
        u = np.unique(np.concatenate([ic, jc]))
        yield np.searchsorted(u, ic), np.searchsorted(u, jc), wk[u]


def _contact(job):
    """length (m) along which b's boundary runs within 1 cm of a's, for every pair of the task. A point of b's
    boundary within TOL of a's boundary lies in bbox(b) and within TOL of bbox(a), and so does its partner on a's
    boundary, so both boundaries are clipped to the common box grown by TOL + MARGIN before the buffer."""
    ia, ib, wk = job
    g = shapely.from_wkb(wk)
    bd = shapely.boundary(g)
    bb = shapely.bounds(g)
    lo = np.maximum(bb[ia, :2], bb[ib, :2]) - (D.TOL + MARGIN)
    hi = np.minimum(bb[ia, 2:], bb[ib, 2:]) + (D.TOL + MARGIN)
    ca = [shapely.clip_by_rect(bd[p], lo[k, 0], lo[k, 1], hi[k, 0], hi[k, 1]) for k, p in enumerate(ia)]
    cb = [shapely.clip_by_rect(bd[q], lo[k, 0], lo[k, 1], hi[k, 0], hi[k, 1]) for k, q in enumerate(ib)]
    return shapely.length(shapely.intersection(cb, shapely.buffer(ca, D.TOL)))


def _whole(job):
    """the former length: whole boundaries, one buffer per pair (--compare)"""
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
    ap.add_argument('--only')
    ap.add_argument('--compare', type=int, default=0)
    ap.add_argument('--csv')
    ap.add_argument('--workers', type=int, default=32)
    a = ap.parse_args()
    t0 = time.time()
    if a.pieces:
        F = pd.concat([gpd.read_parquet(f'{a.out}/{t}.parquet') for t in a.pieces.split(',')], ignore_index=True)
        print(f'pieces {len(F):,} (baseline, tiled version)', flush=True)
    elif a.only:
        F = pd.concat([gpd.read_parquet(f'{a.out}/final/{t}.parquet') for t in a.only.split(',')], ignore_index=True)
        print(f'final polygons {len(F):,} in {a.only.count(",") + 1} tiles (test, no asid checks)', flush=True)
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
    ids = F['asid'].to_numpy() if 'asid' in F else np.arange(len(F))
    kh = D.khash(F)
    g = np.asarray(F.geometry.values, dtype=object)
    i, j = D._near_pairs(g, kh)
    print(f'same-KEY pairs within {D.TOL} m: {len(i):,} ({time.time() - t0:.0f} s)', flush=True)
    wk = shapely.to_wkb(g)
    tasks = list(_tasks(i, j, wk))
    ctx = mp.get_context('forkserver')             # workers start small, not as copies of this process
    L = []
    with ProcessPoolExecutor(a.workers, mp_context=ctx) as ex:
        for n, x in enumerate(ex.map(_contact, tasks), 1):
            L.append(np.asarray(x))
            if n % 20 == 0 or n == len(tasks):
                print(f'  {n}/{len(tasks)} tasks, {time.time() - t0:.0f} s', flush=True)
    L = np.concatenate(L) if L else np.zeros(0)
    nv = shapely.get_num_coordinates(g)
    res = np.flatnonzero(L > 1.0)
    print(f'residual same-KEY contacts longer than 1 m: {len(res):,} (longest {L.max(initial=0):.2f} m)', flush=True)
    for k in np.argsort(-L)[:min(10, len(res))]:
        print(f'  asid {ids[i[k]]} and {ids[j[k]]}: {L[k]:.2f} m ({nv[i[k]]:,} + {nv[j[k]]:,} vertices)', flush=True)
    if a.csv:
        out = {'length_m': L[res].round(2)}
        for s, ix in (('a', i[res]), ('b', j[res])):
            out[f'asid_{s}'] = ids[ix]
            for c in ('rep_tile', 'src_id', 'src_sheet', 'hclass', 'n_pieces', 'n_tiles'):
                out[f'{c}_{s}'] = F[c].to_numpy()[ix] if c in F else ''
            out[f'vertices_{s}'] = nv[ix]
        pd.DataFrame(out).sort_values('length_m', ascending=False).to_csv(a.csv, index=False)
        print(f'{len(res):,} residual pairs -> {a.csv}', flush=True)
    ok = True
    if a.compare and len(i):
        small = np.flatnonzero(nv[i] + nv[j] <= 20000)
        r = np.sort(np.random.default_rng(0).choice(small, min(a.compare, len(small)), replace=False))
        top = np.argsort(-L)[:min(20, len(res))]
        jobs = [(wk[i[r[k:k + 50]]], wk[j[r[k:k + 50]]]) for k in range(0, len(r), 50)] + \
               [(wk[i[[t]]], wk[j[[t]]]) for t in top]
        with ProcessPoolExecutor(a.workers, mp_context=ctx) as ex:
            W = np.concatenate([np.asarray(x) for x in ex.map(_whole, jobs)])
        for name, s, w in (('random pairs of <= 20,000 vertices', r, W[:len(r)]),
                           ('longest residual pairs', top, W[len(r):])):
            d = np.abs(w - L[s])
            good = d.max(initial=0) <= 0.01 and ((w > 1.0) == (L[s] > 1.0)).all()
            ok = ok and good
            print(f'compare {len(s):,} {name}, whole boundaries vs clipped: largest difference '
                  f'{d.max(initial=0):.2e} m; over 1 m {int((w > 1.0).sum())} vs {int((L[s] > 1.0).sum())}; '
                  f'{"PASSED" if good else "FAILED"} ({time.time() - t0:.0f} s)', flush=True)
    if a.overlap:
        ii, jj = shapely.STRtree(g).query(g, predicate='intersects')
        m = ii < jj
        ii, jj = ii[m], jj[m]
        with Pool(a.workers) as pool:
            res = list(pool.imap(_overlap, ((wk[ii[k:k + STEP]], wk[jj[k:k + STEP]])
                                            for k in range(0, len(ii), STEP))))
        print(f'touching pairs {len(ii):,}; overlap total {sum(r[0] for r in res):,.3f} m2 in '
              f'{sum(r[1] for r in res):,} pairs (> 0.01 m2)', flush=True)
    print(f'done ({time.time() - t0:.0f} s)', flush=True)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
