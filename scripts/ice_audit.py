#!/usr/bin/env python
"""Critical audit of the glacier / ice-cap outlines against the merged surficial geology, BEFORE the ice override
(decision 2026-10-01: one ice layer everywhere, the source class kept under it; 2026-10-06: no slivers between the ice
and the geology). Input: the merge-40 tiles (hard-linked to work/ice_audit/tiles_m40), RGI 6.0 per glacier (raw zips,
with dates) and PROMICE 2022 (Greenland ice sheet + connected glaciers).

Per tile touching ice (100 km tiles, EPSG:6931), with the outline O = RGI glaciers U PROMICE:
  areas      outline on the merged coverage, source-mapped ice (hclass I), both, outline-only, source-only
  under      outline-only area by the geology class the merge has there (what the outline would overwrite)
  srconly    source ice outside the outline, by src_id, split into thin (< w wide: boundary noise) and wide (deglaciated
             since the source map, or a generalised source)
  offset     distance from points every 250 m on the source-ice boundary to the outline boundary
  slivers    what a NAIVE overlay leaves: non-ice geology minus O -> whole pieces narrower than w (opening test) touching
             O, and thin appendages (piece minus its opening) within w of the outline, for w = 50, 100, 250, 500 m, by
             src_id (the right w depends on the source scale)
Writes work/ice_audit/{tiles,under,srconly,slivers,offset}.csv and prints per-region summaries; the RGI date table is
work/ice_audit/rgi_dates.csv.
usage: ice_audit.py [--workers N] [--only TILE_ID,...]"""
import glob
import os
import sys
import zipfile
from multiprocessing import Pool

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
OUT = f'{ROOT}/work/ice_audit'
TILES = f'{OUT}/tiles_m40'
WS = (50, 100, 250, 500)
GRID = 0.01                      # m: precision for the robust overlay fallback

a = sys.argv[1:]
WORKERS = int(a[a.index('--workers') + 1]) if '--workers' in a else 32
ONLY = set(a[a.index('--only') + 1].split(',')) if '--only' in a else None


def load_rgi():
    parts, dates = [], []
    for z in sorted(glob.glob(f'{RAW}/rgi/[01][0-9]_rgi60_*.zip')):
        reg = os.path.basename(z)[:2]
        if reg == '00':
            continue
        with zipfile.ZipFile(z) as zf:
            shp = [n for n in zf.namelist() if n.endswith('.shp')][0]
        g = gpd.read_file(f'zip://{z}!{shp}', columns=['RGIId', 'BgnDate', 'EndDate', 'Area']).to_crs(6931)
        g['region'] = reg
        g['geometry'] = shapely.make_valid(shapely.force_2d(g.geometry.values))
        y = pd.to_numeric(g['BgnDate'].astype(str).str[:4], errors='coerce').where(lambda s: s > 1800)
        g['year'] = y
        dates.append(dict(region=reg, n=len(g), km2=round(g['Area'].sum()), year_known=f'{y.notna().mean():.0%}',
                          y_min=y.min(), y_p10=y.quantile(.1), y_med=y.median(), y_p90=y.quantile(.9), y_max=y.max(),
                          pre1980_km2=round(g.loc[y < 1980, 'Area'].sum())))
        parts.append(g[['region', 'RGIId', 'year', 'geometry']])
    p = gpd.read_file(glob.glob(f'{RAW}/promice/*polygon*.gpkg')[0]).to_crs(6931)
    p = gpd.GeoDataFrame({'region': 'GrIS', 'RGIId': 'PROMICE2022', 'year': 2022.0},
                         geometry=shapely.make_valid(shapely.force_2d(p.geometry.values)), index=range(len(p)), crs=6931)
    ice = pd.concat(parts + [p], ignore_index=True)
    return gpd.GeoDataFrame(ice, geometry='geometry', crs=6931), pd.DataFrame(dates)


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


def tbox(tid):
    x, y = (int(v) for v in tid.split('_'))
    return shapely.box(x * 1000, y * 1000, (x + 100) * 1000, (y + 100) * 1000)


ICE, DATES = load_rgi()
TREE = shapely.STRtree(ICE.geometry.values)


def thin_pieces(geom, w):
    """pieces of geom narrower than w everywhere (vanish under a w/2 inward buffer)"""
    return [p for p in shapely.get_parts(geom) if not p.is_empty and shapely.buffer(p, -w / 2).is_empty]


def do_tile(tid):
    try:
        return _do_tile(tid)
    except Exception as e:
        print("TILE ERROR", tid, repr(e)[:300], flush=True)
        return None


def _do_tile(tid):
    tb = tbox(tid)
    hit = TREE.query(tb, predicate='intersects')
    if not len(hit):
        return None
    sub = ICE.iloc[hit]
    # clip to the tile rectangle first (the PROMICE polygon has millions of vertices; a full intersection per tile crawls)
    clipped = shapely.make_valid(shapely.clip_by_rect(sub.geometry.values, *tb.bounds))
    keep = ~shapely.is_empty(clipped)
    if not keep.any():
        return None
    a_ = pd.Series(shapely.area(clipped[keep]), index=sub['region'].values[keep])
    reg = a_.groupby(level=0).sum().idxmax()
    O = robust(shapely.union_all, clipped[keep])
    g = gpd.read_parquet(f'{TILES}/{tid}.parquet', columns=['geometry', 'hclass', 'src_id', 'scale_den'])
    g['geometry'] = shapely.make_valid(shapely.force_2d(g.geometry.values))
    g = g[~g.geometry.is_empty]
    cov = robust(shapely.union_all, g.geometry.values)
    Oc = robust(shapely.intersection, O, cov)
    isI = (g['hclass'] == 'I').values
    src = robust(shapely.union_all, g.geometry.values[isI]) if isI.any() else shapely.Polygon()
    row = dict(tile=tid, region=reg, outline_km2=Oc.area / 1e6, src_ice_km2=src.area / 1e6,
               both_km2=robust(shapely.intersection, Oc, src).area / 1e6)
    row['outline_only_km2'] = row['outline_km2'] - row['both_km2']
    row['src_only_km2'] = row['src_ice_km2'] - row['both_km2']
    under, srconly, slv, off = [], [], [], []
    shapely.prepare(Oc)
    non = g[~isI]
    # what the outline overwrites
    if not Oc.is_empty:
        m = shapely.intersects(non.geometry.values, Oc)
        if m.any():
            x = non[m].assign(a=shapely.area(robust(shapely.intersection, non.geometry.values[m], Oc)) / 1e6)
            for (h, s), v in x.groupby(['hclass', 'src_id'])['a'].sum().items():
                under.append(dict(tile=tid, region=reg, hclass=h, src_id=s, km2=v))
    # source ice outside the outline
    if isI.any():
        for s, gs in g[isI].groupby('src_id'):
            rest = robust(shapely.difference, robust(shapely.union_all, gs.geometry.values), O)
            if rest.is_empty:
                continue
            r = dict(tile=tid, region=reg, src_id=s, scale_den=float(pd.to_numeric(gs['scale_den'], errors='coerce').fillna(0).iloc[0]), km2=rest.area / 1e6)
            for w in WS:
                r[f'thin{w}_km2'] = sum(p.area for p in thin_pieces(rest, w)) / 1e6
            srconly.append(r)
        # boundary offset source ice -> outline
        if not O.is_empty and not src.is_empty:
            b = shapely.segmentize(shapely.boundary(src), 250)
            pts = shapely.points(shapely.get_coordinates(b))
            pts = pts[shapely.within(pts, tb.buffer(-1))]                  # tile edges are not ice edges
            if len(pts):
                ob = shapely.boundary(O)
                shapely.prepare(ob)
                d = shapely.distance(pts, ob)
                off.append(dict(tile=tid, region=reg, n=len(d), med=float(np.median(d)), p90=float(np.quantile(d, .9)),
                                le100=float((d <= 100).mean()), le250=float((d <= 250).mean()), le500=float((d <= 500).mean())))
    # slivers of a naive overlay: non-ice geology minus the outline
    if not O.is_empty:
        ob = shapely.boundary(O)
        near = non[shapely.dwithin(non.geometry.values, O, 1.0)]
        for s, gs in near.groupby('src_id'):
            cut = robust(shapely.difference, robust(shapely.union_all, gs.geometry.values), O)
            if cut.is_empty:
                continue
            pieces = [p for p in shapely.get_parts(cut) if shapely.dwithin(p, O, 1.0)]
            r = dict(tile=tid, region=reg, src_id=s, scale_den=float(pd.to_numeric(gs['scale_den'], errors='coerce').fillna(0).iloc[0]))
            for w in WS:
                th = [p for p in pieces if shapely.buffer(p, -w / 2).is_empty]
                r[f'n{w}'] = len(th)
                r[f'piece{w}_km2'] = sum(p.area for p in th) / 1e6
                if w in (100, 250):                           # thin appendages along the outline
                    band = shapely.buffer(ob, w)
                    app = 0.0
                    for p in pieces:
                        if shapely.buffer(p, -w / 2).is_empty:
                            continue
                        op_ = shapely.buffer(shapely.buffer(p, -w / 2), w / 2)
                        app += robust(shapely.intersection, robust(shapely.difference, p, op_), band).area
                    r[f'app{w}_km2'] = app / 1e6
            slv.append(r)
    return row, under, srconly, slv, off


def main():
    tiles = sorted(os.path.basename(f)[:-8] for f in glob.glob(f'{TILES}/*.parquet'))
    if ONLY:
        tiles = [t for t in tiles if t in ONLY]
    boxes = [tbox(t) for t in tiles]
    keep = sorted(set(TREE.query(boxes, predicate='intersects')[0]))
    tiles = [tiles[i] for i in keep]
    print(len(tiles), 'tiles touch ice', flush=True)
    DATES.to_csv(f'{OUT}/rgi_dates.csv', index=False)
    print(DATES.to_string(index=False), flush=True)
    res = {k: [] for k in ('tiles', 'under', 'srconly', 'slivers', 'offset')}
    with Pool(WORKERS) as pool:
        for i, r in enumerate(pool.imap_unordered(do_tile, tiles, chunksize=2)):
            if r is None:
                continue
            row, under, srconly, slv, off = r
            res['tiles'].append(row); res['under'] += under; res['srconly'] += srconly
            res['slivers'] += slv; res['offset'] += off
            if i % 100 == 0:
                print(i, 'tiles done', flush=True)
    for k, v in res.items():
        pd.DataFrame(v).to_csv(f'{OUT}/{k}.csv', index=False)
    T = pd.DataFrame(res['tiles'])
    print('\nPER REGION (km2):')
    print(T.groupby('region')[['outline_km2', 'src_ice_km2', 'both_km2', 'outline_only_km2', 'src_only_km2']].sum().round(0).to_string())
    U = pd.DataFrame(res['under'])
    if len(U):
        print('\nOUTLINE-ONLY: geology under the outline (km2, top 25):')
        print(U.groupby(['region', 'hclass'])['km2'].sum().sort_values(ascending=False).head(25).round(1).to_string())
    S = pd.DataFrame(res['srconly'])
    if len(S):
        print('\nSOURCE ICE OUTSIDE THE OUTLINE by source (km2):')
        print(S.groupby('src_id')[['km2'] + [f'thin{w}_km2' for w in WS]].sum().sort_values('km2', ascending=False).round(1).to_string())
    L = pd.DataFrame(res['slivers'])
    if len(L):
        print('\nNAIVE-OVERLAY SLIVERS touching the outline by source (pieces n / km2; appendages km2):')
        cols = [c for w in WS for c in (f'n{w}', f'piece{w}_km2')] + ['app100_km2', 'app250_km2']
        print(L.groupby('src_id')[cols].sum().sort_values('piece250_km2', ascending=False).round(2).to_string())
    F = pd.DataFrame(res['offset'])
    if len(F):
        w = F['n']
        print('\nBOUNDARY OFFSET source ice -> outline by region (weighted by samples):')
        print(F.groupby('region').apply(lambda d: pd.Series(dict(n=d['n'].sum(), med=np.average(d['med'], weights=d['n']),
                                                                    p90=np.average(d['p90'], weights=d['n']),
                                                                    le100=np.average(d['le100'], weights=d['n']),
                                                                    le250=np.average(d['le250'], weights=d['n'])))).round(2).to_string())


if __name__ == '__main__':
    main()
