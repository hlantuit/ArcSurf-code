#!/usr/bin/env python
"""One ice layer for the merge, per merge tile (work/land_amap.gpkg layer 'tiles'), from RGI 6.0 per glacier (regions
01-10, with outline years) and PROMICE-2022 Ice Mask v3 (Greenland Ice Sheet + connected glaciers, Sentinel-2 10 m).
Replaces ice_unify.py (2026-10-01; it used the per-region dissolved RGI layer without dates and failed on a GEOS
non-noded intersection in a global overlay). Everything here is local to a tile (+2 km context) with a grid-size
fallback, so the overlays stay small and robust.

Per tile:
  1. ice U = union of the RGI glaciers and PROMICE inside the tile + 2 km, CLOSED by +-GAP_M (gaps narrower than
     2*GAP_M between neighbouring glaciers / between RGI and PROMICE are filled: they would otherwise leave thin
     strips of geology inside the ice)
  2. source zones: PROMICE = U within GAP_M of PROMICE (the newer, finer outline wins its own margin and the closing
     fill next to it); RGI = the rest. RGI remnants narrower than 2*SLIV_M that touch PROMICE are dropped (the 2000
     RGI-05 fringe around the 2022 PROMICE margin)
  3. parts clipped to the tile, attributes ice_src ('PROMICE2022' | 'RGI6-<region>') and ice_year (PROMICE 2022; RGI:
     area-weighted median outline year of the glaciers in the part)
Writes work/ice_by_tile.gpkg layer 'ice' (tile_id, ice_src, ice_year, geometry; EPSG:6931) and work/ice_build.json.
usage: ice_build.py [--workers N] [--only TILE_ID,...]"""
import glob
import json
import os
import sys
import zipfile
from multiprocessing import Pool

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
OUTP = f'{ROOT}/work/ice_by_tile.gpkg'
GAP_M, SLIV_M, CTX_M, GRID = 30.0, 60.0, 2000.0, 0.01
a = sys.argv[1:]
WORKERS = int(a[a.index('--workers') + 1]) if '--workers' in a else 32
ONLY = set(a[a.index('--only') + 1].split(',')) if '--only' in a else None


def robust(op, *args, **kw):
    """GEOS op with fallbacks: as is -> inputs repaired (make_valid) -> inputs snapped to GRID + grid_size"""
    try:
        return op(*args, **kw)
    except shapely.errors.GEOSException:
        pass
    fix = [shapely.make_valid(x) if isinstance(x, (shapely.Geometry, np.ndarray)) else x for x in args]
    try:
        return op(*fix, **kw)
    except shapely.errors.GEOSException:
        pass
    snap = [shapely.make_valid(shapely.set_precision(x, GRID)) if isinstance(x, (shapely.Geometry, np.ndarray)) else x
            for x in fix]
    return op(*snap, grid_size=GRID, **kw)


def load():
    parts = []
    for z in sorted(glob.glob(f'{RAW}/rgi/[01][0-9]_rgi60_*.zip')):
        reg = os.path.basename(z)[:2]
        if reg == '00':
            continue
        with zipfile.ZipFile(z) as zf:
            shp = [n for n in zf.namelist() if n.endswith('.shp')][0]
        g = gpd.read_file(f'zip://{z}!{shp}', columns=['RGIId', 'BgnDate']).to_crs(6931)
        g['src'] = 'RGI6-' + reg
        g['year'] = pd.to_numeric(g['BgnDate'].astype(str).str[:4], errors='coerce').where(lambda s: s > 1800)
        g['geometry'] = shapely.make_valid(shapely.force_2d(g.geometry.values))
        parts.append(g[['src', 'year', 'geometry']])
    p = gpd.read_file(glob.glob(f'{RAW}/promice/*polygon*.gpkg')[0]).to_crs(6931)
    p = gpd.GeoDataFrame({'src': 'PROMICE2022', 'year': 2022.0},
                         geometry=shapely.make_valid(shapely.force_2d(p.geometry.values)), index=range(len(p)), crs=6931)
    g = gpd.GeoDataFrame(pd.concat(parts + [p], ignore_index=True), geometry='geometry', crs=6931)
    return g[~g.geometry.is_empty].reset_index(drop=True)


ICE = load()
TREE = shapely.STRtree(ICE.geometry.values)
TILES = pyogrio.read_dataframe(f'{ROOT}/work/land_amap.gpkg', layer='tiles')


def do_tile(i):
    tid, tb = TILES['tile_id'].iat[i], TILES.geometry.iat[i]
    ctx = shapely.buffer(tb, CTX_M)
    hit = TREE.query(ctx, predicate='intersects')
    if not len(hit):
        return None
    sub = ICE.iloc[hit]
    clip = shapely.make_valid(shapely.clip_by_rect(sub.geometry.values, *ctx.bounds))
    ok = ~shapely.is_empty(clip)
    sub, clip = sub[ok], clip[ok]
    if not len(clip):
        return None
    isP = (sub['src'] == 'PROMICE2022').values
    U0 = robust(shapely.union_all, clip)
    U = shapely.make_valid(shapely.buffer(shapely.buffer(U0, GAP_M, join_style='mitre'), -GAP_M, join_style='mitre'))
    rep = dict(tile=tid, raw_km2=robust(shapely.intersection, U0, tb).area / 1e6,
               closed_km2=robust(shapely.intersection, U, tb).area / 1e6, dropped_km2=0.0)
    rows = []
    if isP.any():
        P = robust(shapely.union_all, clip[isP])
        Pz = robust(shapely.intersection, U, shapely.buffer(P, GAP_M))
        R = robust(shapely.difference, U, Pz)
        keep = []
        for q in shapely.get_parts(R):
            if shapely.dwithin(q, P, GAP_M + 1) and shapely.buffer(q, -SLIV_M).is_empty:
                rep['dropped_km2'] += q.area / 1e6
                continue
            keep.append(q)
        R = robust(shapely.union_all, keep) if keep else shapely.Polygon()
        rows.append(('PROMICE2022', 2022.0, robust(shapely.intersection, Pz, tb)))
    else:
        R = U
    if not R.is_empty:
        rsub, rclip = sub[~isP], clip[~isP]
        for q in shapely.get_parts(robust(shapely.intersection, R, tb)):
            if q.is_empty or q.area < 1.0:
                continue
            w = shapely.area(robust(shapely.intersection, rclip, q))
            m = w > 0
            if not m.any():                       # pure closing fill between two sources: nearest glacier
                j = int(np.argmin(shapely.distance(rclip, q)))
                src, yr = rsub['src'].iat[j], rsub['year'].iat[j]
            else:
                s = pd.DataFrame({'src': rsub['src'].values[m], 'year': rsub['year'].values[m], 'w': w[m]})
                src = s.groupby('src')['w'].sum().idxmax()
                y = s.dropna(subset=['year']).sort_values('year')
                yr = float(y['year'].values[np.searchsorted(y['w'].cumsum().values, y['w'].sum() / 2)]) if len(y) else np.nan
            rows.append((src, yr, q))
    out = []
    for src, yr, g in rows:
        for q in shapely.get_parts(shapely.make_valid(g)):
            if q.geom_type == 'Polygon' and q.area >= 1.0:
                out.append(dict(tile_id=tid, ice_src=src, ice_year=yr, geometry=q))
    rep['out_km2'] = sum(r['geometry'].area for r in out) / 1e6
    return out, rep


def main():
    idx = [i for i in range(len(TILES)) if not ONLY or TILES['tile_id'].iat[i] in ONLY]
    boxes = [shapely.buffer(TILES.geometry.iat[i], CTX_M) for i in idx]
    hit = sorted(set(TREE.query(boxes, predicate='intersects')[0]))
    idx = [idx[i] for i in hit]
    print(len(idx), 'tiles touch ice', flush=True)
    rows, reps = [], []
    with Pool(WORKERS) as pool:
        for k, r in enumerate(pool.imap_unordered(do_tile, idx, chunksize=2)):
            if r is None:
                continue
            rows += r[0]; reps.append(r[1])
            if k % 200 == 0:
                print(k, 'tiles', flush=True)
    g = gpd.GeoDataFrame(rows, geometry='geometry', crs=6931)
    g['ice_year'] = pd.to_numeric(g['ice_year'], errors='coerce').round().astype('Int64')
    if not ONLY and os.path.exists(OUTP):
        os.remove(OUTP)
    outp = OUTP if not ONLY else OUTP.replace('.gpkg', '_test.gpkg')
    g.to_file(outp, layer='ice', driver='GPKG')
    R = pd.DataFrame(reps)
    tot = dict(tiles=len(R), raw_km2=round(R['raw_km2'].sum()), closed_fill_km2=round((R['closed_km2'] - R['raw_km2']).sum(), 1),
               rgi_fringe_dropped_km2=round(R['dropped_km2'].sum(), 1), out_km2=round(R['out_km2'].sum()), parts=len(g),
               by_src_km2=g.assign(a=g.area / 1e6).groupby('ice_src')['a'].sum().round(0).to_dict(),
               gap_m=2 * GAP_M, sliver_m=2 * SLIV_M)
    json.dump(tot, open(outp.replace('.gpkg', '.json'), 'w'), indent=1)
    print(json.dumps(tot, indent=1))


if __name__ == '__main__':
    main()
