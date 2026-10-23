#!/usr/bin/env python
"""Where does pass 1 of the dissolve spend its time on one tile? (merge 44: tile -03900_-00300, Hudson Bay Lowland,
still running after 6 h while every other tile took < 65 min.) The same steps as dissolve_release.pass1 and _union,
timed group by group, the groups with the most vertices first. Before every step of a large group a 'start' line is
written, so a step that never ends is the last line of the log. Writes nothing but the log.
usage: dissolve_debug_tile.py TILES_DIR TILE"""
import os
import sys
import time

import numpy as np
import geopandas as gpd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dissolve_release as D  # noqa: E402

BIG = 20_000          # vertices: groups this large get a 'start' line before every step
SLOW = 5.0            # s: any step slower than this is logged


def step(label, k, verbose, fn, *args):
    if verbose:
        print(f'    [{k}] start {label}', flush=True)
    t = time.time()
    out = fn(*args)
    dt = time.time() - t
    if verbose or dt > SLOW:
        print(f'    [{k}] {label}: {dt:.1f} s', flush=True)
    return out, dt


def main():
    tiles, tid = sys.argv[1:3]
    t0 = time.time()
    g = gpd.read_parquet(f'{tiles}/{tid}.parquet')
    n = len(g)
    geoms = np.asarray(shapely.force_2d(g.geometry.values), dtype=object)
    nv = shapely.get_num_coordinates(geoms)
    print(f'{tid}: {n:,} pieces, {int(nv.sum()):,} vertices, largest piece {int(nv.max()):,} '
          f'({time.time() - t0:.0f} s)', flush=True)
    kh = D.khash(g)
    a, b = D._near_pairs(geoms, kh)
    print(f'near pairs {len(a):,} ({time.time() - t0:.0f} s)', flush=True)
    nc, lab = D._components(a, b, n)
    groups = D._groups(lab, nc)
    nbrs = D._neighbours(a, b, n, groups)
    gv = np.array([int(nv[m].sum()) for m in groups])
    order = np.argsort(-gv, kind='stable')
    print(f'{nc:,} components, {len(groups):,} groups to merge ({time.time() - t0:.0f} s); the largest: ' +
          ', '.join(f'{len(groups[i])} pieces / {gv[i]:,} v' for i in order[:8]), flush=True)
    tot = {}
    for k, gi in enumerate(order):
        mem, nbr = groups[gi], nbrs[gi]
        G = geoms[mem]
        v = nv[mem]
        deg = np.array([len(x) for x in nbr])
        snapcost = max((int(v[i]) * int(v[x].sum()) for i, x in enumerate(nbr) if len(x)), default=0)
        verbose = gv[gi] >= BIG or snapcost >= 1e9
        if verbose:
            print(f'[{k}] group {gi}: {len(mem):,} pieces, {gv[gi]:,} vertices, largest piece {int(v.max()):,}, '
                  f'max degree {int(deg.max())}, worst snap {snapcost:.2e} vertex pairs ({time.time() - t0:.0f} s)',
                  flush=True)
        total = float(shapely.area(G).sum())
        mode = None
        valid, dt = step('coverage_is_valid', k, verbose, shapely.coverage_is_valid, G)
        tot['valid'] = tot.get('valid', 0) + dt
        if valid:
            u, dt = step('coverage_union_all', k, verbose, shapely.coverage_union_all, G)
            tot['cov'] = tot.get('cov', 0) + dt
        else:
            u, dt = step('union_all (float)', k, verbose, shapely.union_all, G)
            tot['float'] = tot.get('float', 0) + dt
        parts = D._polys(u)
        if len(parts) == 1 and D._area_ok(parts, total):
            mode = 'cov' if valid else 'float'
        else:
            if verbose:
                print(f'    [{k}] exact union gave {len(parts)} parts', flush=True)
            s, dt = step('snap to neighbours', k, verbose, D._snap_to_neighbours, G, nbr)
            tot['snap_nbr'] = tot.get('snap_nbr', 0) + dt
            u, dt = step('union_all (snapped)', k, verbose, shapely.union_all, s)
            tot['union_snapped'] = tot.get('union_snapped', 0) + dt
            parts = D._polys(u)
            if D._area_ok(parts, total):
                mode = 'snapto'
            else:
                u, dt = step('union_all (1 cm grid)', k, verbose, lambda x: shapely.union_all(x, grid_size=D.TOL), G)
                tot['grid'] = tot.get('grid', 0) + dt
                parts = D._polys(u)
                mode = 'snap'
        idx, dt = step('assign', k, verbose, D._assign, G, parts)
        tot['assign'] = tot.get('assign', 0) + dt
        npart_orphan = len(parts) - len(np.unique(idx))
        if verbose or npart_orphan:
            print(f'    [{k}] {mode}: {len(parts):,} parts, {npart_orphan:,} without a piece', flush=True)
        _, dt = step('rep_members', k, verbose or npart_orphan > 0, D._rep_members, G, parts, idx)
        tot['rep'] = tot.get('rep', 0) + dt
        if k % 2000 == 0:
            print(f'  {k:,}/{len(groups):,} groups ({time.time() - t0:.0f} s) ' +
                  ', '.join(f'{x} {y:.0f} s' for x, y in tot.items()), flush=True)
    print(f'done {time.time() - t0:.0f} s: ' + ', '.join(f'{x} {y:.0f} s' for x, y in tot.items()), flush=True)


if __name__ == '__main__':
    main()
