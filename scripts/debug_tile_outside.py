#!/usr/bin/env python
"""Debug: which step of merge_tiles.do_tile produces geometry OUTSIDE its tile (merge 42: a 265 km2 Bryant polygon in
+01100_+02300, 79 km2 of GSC 5M in -02200_+01600)? Replays the precedence loop for one tile and reports, after each
footprint, any take / sliver geometry outside the tile. usage: debug_tile_outside.py TILE_ID"""
import importlib.util
import json
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shapely  # noqa: E402
import pyogrio  # noqa: E402

spec = importlib.util.spec_from_file_location('mt', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                 'merge_tiles_test.py'))
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)
tid = sys.argv[1]
sources = json.load(open(f'{mt.S.WORK}/merge_sources.json'))
mt._init(sources)
tiles = pyogrio.read_dataframe(mt.LAND, layer='tiles', where=f"tile_id = '{tid}'")
tgeom = tiles.geometry.values[0]
land = pyogrio.read_dataframe(mt.LAND, layer='land', bbox=tgeom.bounds)
land_t = shapely.make_valid(mt._sinter(mt._sunion(land.geometry.values), tgeom))
print('land_t outside tile km2', round(shapely.area(shapely.difference(land_t, tgeom)) / 1e6, 4))
fps = mt.FOOT[shapely.intersects(mt.FOOT.geometry.values, tgeom)].copy()
fps = fps.sort_values(['prec_scale', 'tier_rank', 'pub_year'], ascending=[True, True, False])
covered = shapely.Polygon()
for _, f in fps.iterrows():
    d = float(f['d'])
    local = mt._sinter(f.geometry, shapely.buffer(tgeom, 2 * d + 1))
    claim = mt._sinter(shapely.buffer(local, d), land_t)
    claim = mt._sdiff(claim, covered)
    if claim.is_empty or claim.area < mt.MIN_AREA:
        continue
    out_c = shapely.area(shapely.difference(claim, tgeom)) / 1e6
    u = pyogrio.read_dataframe(f'{mt.XW}/{f["src_id"]}.gpkg', layer='units', bbox=shapely.buffer(tgeom, 2000).bounds)
    if f['src_sheet']:
        u = u[u['src_sheet'] == f['src_sheet']]
    u = u[shapely.intersects(u.geometry.values, claim)]
    if u.empty:
        continue
    g = mt._clean(mt._sinter(u.geometry.values, claim))
    out_t = sum(shapely.area(shapely.difference(x, tgeom)) for x in g if x is not None) / 1e6
    print(f"{f['src_id']:24s} {str(f['src_sheet'])[:16]:16s} d={d:6.0f} claim_out={out_c:8.3f} take_out={out_t:8.3f} "
          f"claim={claim.area / 1e6:9.1f} geom_type={claim.geom_type}")
    covered = mt._sunion([covered] + [x for x in g if x is not None])
