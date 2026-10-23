#!/usr/bin/env python
"""Apply a source's crosswalk and report area by hclass / texture / ice.

usage: check_xwalk.py <src_id>
Fails (via apply_xwalk) if any native key has no crosswalk row; also lists
crosswalk rows that match nothing (stale or misspelt keys).
"""
import os
import sys

import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

src = sys.argv[1]
u = gpd.read_file(f'{S.STD}/{src}.gpkg', layer='units')
x = S.load_xwalk(src)
unused = sorted(set(x['xkey']) - set(u['xkey']))
m, nd, ad = S.apply_xwalk(u, src)
m['km2'] = m.area / 1e6
tot = m['km2'].sum()
print(f'{src}: {len(m)} polygons, {tot:,.0f} km2 kept; dropped {nd} polygons / {ad:,.0f} km2 (DROP)')
for col in ('hclass', 'texture', 'ice_rich'):
    t = m.groupby(col)['km2'].sum().sort_values(ascending=False)
    print(f'\n{col}:')
    for k, v in t.items():
        print(f'  {k:10s} {v:12,.0f} km2  {100 * v / tot:5.1f}%  {S.HCLASS.get(k, "") if col == "hclass" else ""}')
if unused:
    print('\ncrosswalk rows matching nothing:', unused)
