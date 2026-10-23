#!/usr/bin/env python
"""
One ice layer from RGI 6.0 (regions 01-10) + PROMICE-2022 Ice Mask v3 (Greenland Ice Sheet),
at FULL resolution; the finer, newer source wins where they overlap.

  PROMICE-2022: Sentinel-2 10 m, Aug 2022, contiguous ice incl. CL1-connected glaciers.
  RGI 6.0 region 05 (Rastner et al. 2012): Landsat ~30 m, ~2000. -> PROMICE wins.
Rules (Greenland only; other regions pass through unchanged):
  1. RGI-05 minus PROMICE (exact difference; removes the overlap fringe).
  2. Remnant pieces of RGI polygons that touched PROMICE are dropped when they are slivers:
     nothing survives an inward buffer of SLIV_M (i.e. narrower than 2*SLIV_M).
  3. Hairline gaps between the two outlines (< 2*GAP_M wide) are closed on the Greenland
     union (buffer +GAP_M / -GAP_M), so the boundary is shared, not doubled.
Outputs: work/ice_unified.gpkg layer 'ice' (src = promice2022 | rgi60, rgi_region, area_km2;
         PROMICE kept as one polygon, RGI pieces abut it after steps 1-3)
         out/web/ice.json  polys = [[outer, hole, ...], ...] simplified AFTER unification
         work/ice_unify_report.json
"""
import json
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402,F401  (sets PROJ data dir)

W = '/albedo/work/user/hlantuit/arctic_surficial'
PROMICE = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/promice/02-PROMICE-2022-IceMask-polygon-v3.gpkg'
SLIV_M, GAP_M, WEB_TOL, WEB_MIN_KM2 = 60.0, 30.0, 1500.0, 4.0

r = gpd.read_file(f'{W}/work/rgi_arctic.gpkg', layer='ice').to_crs(6931)
reg = r['rgi_region'].astype(str).str.zfill(2).str[:2]
p = gpd.read_file(PROMICE).to_crs(6931)
P = shapely.make_valid(shapely.union_all(p.geometry.values))
shapely.prepare(P)
print('rgi', len(r), 'promice km2', round(P.area / 1e6), flush=True)

g5 = r[reg == '05'].copy()
rest = r[reg != '05'].copy()
# tile PROMICE (millions of 10 m vertices) so every overlay below is local
x0, y0, x1, y1 = P.bounds
T = 25_000.0
tiles = [shapely.clip_by_rect(P, x, y, x + T, y + T)
         for x in np.arange(x0, x1, T) for y in np.arange(y0, y1, T)]
tiles = [t for t in tiles if not t.is_empty]
tree = shapely.STRtree(tiles)
print('promice tiles', len(tiles), flush=True)


def local_P(g, pad=0.0):
    idx = tree.query(shapely.buffer(g, pad) if pad else g)
    return shapely.union_all([tiles[i] for i in idx]) if len(idx) else None


keep, pieces, drop_n, drop_km2, overlap_km2, n_hit = [], [], 0, 0.0, 0.0, 0
for i, g in zip(g5.index, g5.geometry.values):
    Pl = local_P(g)
    if Pl is None or not shapely.intersects(g, Pl):
        pieces.append((g5.at[i, 'rgi_region'], g, Pl is not None))
        continue
    n_hit += 1
    overlap_km2 += shapely.area(shapely.intersection(g, Pl)) / 1e6
    for q in shapely.get_parts(shapely.make_valid(shapely.difference(g, Pl))):
        if q.geom_type != 'Polygon' or q.is_empty:
            continue
        if shapely.buffer(q, -SLIV_M).is_empty:
            drop_n += 1; drop_km2 += q.area / 1e6
            continue
        pieces.append((g5.at[i, 'rgi_region'], q, True))
print('greenland: rgi touching promice', n_hit, 'overlap km2', round(overlap_km2, 1),
      'slivers dropped', drop_n, round(drop_km2, 2), 'km2', flush=True)

# close hairline gaps locally: fill = closing(q U P_local) minus both, kept within GAP_M of both
gap_km2, fixed = 0.0, []
for rg, q, cand in pieces:
    if cand:
        Pl = local_P(q, 2 * GAP_M)
        if Pl is not None and shapely.dwithin(q, Pl, 2 * GAP_M):
            u = shapely.union(q, Pl)
            c = shapely.buffer(shapely.buffer(u, GAP_M, join_style='mitre'), -GAP_M, join_style='mitre')
            fill = shapely.intersection(shapely.difference(c, u), shapely.buffer(q, 2 * GAP_M))
            if not fill.is_empty:
                gap_km2 += fill.area / 1e6
                q = shapely.make_valid(shapely.union(q, fill))
    fixed.append((rg, q))
print('gaps closed km2', round(gap_km2, 2), flush=True)
gl = gpd.GeoDataFrame({'rgi_region': '05', 'src': 'promice2022'}, geometry=[P], crs=6931)
gr = gpd.GeoDataFrame({'rgi_region': [a for a, _ in fixed], 'src': 'rgi60'}, geometry=[q for _, q in fixed], crs=6931)
gr = gr.explode(index_parts=False)
out = pd.concat([gl, gr, rest.assign(src='rgi60')], ignore_index=True)
out = gpd.GeoDataFrame(out[['rgi_region', 'src', 'geometry']], geometry='geometry', crs=6931)
out['area_km2'] = out.area / 1e6
p_out = f'{W}/work/ice_unified.gpkg'
if os.path.exists(p_out):
    os.remove(p_out)
out.to_file(p_out, layer='ice', driver='GPKG')
rep = dict(promice_km2=P.area / 1e6, rgi05_touching=n_hit, overlap_removed_km2=overlap_km2,
           slivers_dropped=drop_n, slivers_km2=drop_km2, gaps_closed_km2=gap_km2,
           total_km2=float(out['area_km2'].sum()), n=len(out), sliver_width_m=2 * SLIV_M, gap_width_m=2 * GAP_M)
json.dump(rep, open(f'{W}/work/ice_unify_report.json', 'w'), indent=1)
print(rep, flush=True)

# web layer: simplify each unified polygon once (shared boundaries are already merged)
near = out[(out['src'] == 'rgi60') & (out['rgi_region'].astype(str).str.zfill(2).str[:2] == '05')]
near = near[[bool(len(tree.query(g, predicate='dwithin', distance=3 * GAP_M))) for g in near.geometry.values]]
U = shapely.union_all(np.concatenate([[P], near.geometry.values]))
web_geoms = list(shapely.get_parts(U)) + list(out.drop(index=near.index).query("src == 'rgi60'").geometry.values)
print('greenland web union parts', len(shapely.get_parts(U)), flush=True)
polys = []
for g in web_geoms:
    s = shapely.simplify(g, WEB_TOL, preserve_topology=True)
    for q in shapely.get_parts(s):
        if q.geom_type != 'Polygon' or q.area < WEB_MIN_KM2 * 1e6:
            continue
        rings = [q.exterior] + [h for h in q.interiors if shapely.Polygon(h).area >= WEB_MIN_KM2 * 1e6]
        polys.append([[[round(x / 1000, 1), round(y / 1000, 1)] for x, y in ring.coords] for ring in rings])
web = dict(polys=polys, km2=round(rep['total_km2'], 1), km2_gris=round(rep['promice_km2'], 1),
           n_glaciers=90015,
           source='RGI 6.0 (RGI Consortium 2017, doi:10.7265/N5-RGI-60) regions 01-10; Greenland Ice Sheet: '
                  'PROMICE-2022 Ice Mask v3 (GEUS, CC-BY 4.0, doi:10.22008/FK2/O8CLRE); PROMICE wins on overlap')
json.dump(web, open(f'{W}/out/web/ice.json', 'w'), separators=(',', ':'))
print('web polys', len(polys), 'bytes', os.path.getsize(f'{W}/out/web/ice.json'))
