#!/usr/bin/env python
"""Which pieces does ice_apply.sliver_check count on a merged tile, and why are they there? For each whole-piece
sliver (geology narrower than w, >= CONTACT_FRAC of its outline on the ice edge): its attributes, and whether a
touching neighbour has the same hclass and source (= an attribute split, e.g. at a pf_zone / yedoma limit, rather
than an overlay sliver). usage: ice_sliver_diag.py TILE_ID [TILES_DIR]"""
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402
import surflib as S  # noqa: E402
import ice_apply as IA  # noqa: E402

tid = sys.argv[1]
tdir = sys.argv[2] if len(sys.argv) > 2 else f'{S.WORK}/tiles'
t = gpd.read_parquet(f'{tdir}/{tid}.parquet')
tl = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='tiles', where=f"tile_id = '{tid}'")
tgeom = tl.geometry.values[0]
isI = (t['hclass'] == 'I').values
I = IA.robust(shapely.union_all, t.geometry.values[isI])
g = t[~isI].reset_index(drop=True)
touch = shapely.dwithin(g.geometry.values, I, IA.TOL)
gg = g[touch].reset_index(drop=True)
w = IA.width(gg['scale_den'].values)
inner = shapely.buffer(gg.geometry.values, -w / 2, join_style='mitre', mitre_limit=10.0)
whole = shapely.is_empty(inner)
edge = IA.robust(shapely.difference, shapely.boundary(I), shapely.buffer(shapely.boundary(tgeom), 1.0))
seg, tree = IA._edge_index(edge)
frac = IA._contact(gg.geometry.values, seg, tree) / np.maximum(shapely.length(gg.geometry.values), 1e-9)
sl = gg[whole & (frac >= IA.CONTACT_FRAC)].copy()
sl['area_m2'] = sl.area
sl['contact'] = frac[whole & (frac >= IA.CONTACT_FRAC)]
# same-class, same-source neighbour touching it?
gt = shapely.STRtree(g.geometry.values)
same = []
for _, r in sl.iterrows():
    idx = gt.query(r.geometry, predicate='intersects')
    nb = g.iloc[idx]
    nb = nb[~nb.geometry.geom_equals(r.geometry)]
    same.append(bool(((nb['hclass'] == r['hclass']) & (nb['src_id'] == r['src_id'])).any()))
sl['same_nb'] = same
cols = ['hclass', 'src_id', 'src_sheet', 'scale_den', 'pf_zone', 'yedoma', 'gapfill', 'ice_note', 'area_m2', 'contact',
        'same_nb']
print(tid, 'whole-piece slivers', len(sl), 'km2', round(sl['area_m2'].sum() / 1e6, 3))
print(sl[cols].groupby(['src_id', 'hclass', 'pf_zone', 'gapfill', 'same_nb'], dropna=False)['area_m2']
      .agg(['count', 'sum']).sort_values('sum', ascending=False).head(15).to_string())
print('median area m2', round(float(sl['area_m2'].median()), 1), '| median contact', round(float(sl['contact'].median()), 2))
