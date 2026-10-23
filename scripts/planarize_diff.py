#!/usr/bin/env python
"""Compare one tile merged with the old whole-tile _planarize (work/tiles, merge 43, union of ALL winners per loser) and
with the clip_by_rect patch (work/merge_test_v4): the patched run lost 0.5 km2 / 23 polygons on -01900_-00300
(2026-10-07). Prints the area each version has that the other lacks, the old polygons that lost area (by source),
and the largest missing pieces. usage: planarize_diff.py TILE [NEWDIR]"""
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

W = '/albedo/work/user/hlantuit/arctic_surficial/work'
tid = sys.argv[1]
newd = sys.argv[2] if len(sys.argv) > 2 else f'{W}/merge_test_v4'
a = gpd.read_parquet(f'{W}/tiles/{tid}.parquet')
b = gpd.read_parquet(f'{newd}/{tid}.parquet')
print('old', len(a), round(a.area.sum() / 1e6, 4), 'km2   new', len(b), round(b.area.sum() / 1e6, 4), 'km2', flush=True)
ua = shapely.union_all(a.geometry.values, grid_size=0.01)
ub = shapely.union_all(b.geometry.values, grid_size=0.01)
print('union old', round(ua.area / 1e6, 4), 'new', round(ub.area / 1e6, 4), '(sum - union = overlap)', flush=True)
lost = shapely.difference(ua, ub, grid_size=0.01)
gained = shapely.difference(ub, ua, grid_size=0.01)
print('in old, not in new:', round(lost.area / 1e6, 4), 'km2 in', shapely.get_num_geometries(lost), 'parts', flush=True)
print('in new, not in old:', round(gained.area / 1e6, 4), 'km2 in', shapely.get_num_geometries(gained), 'parts', flush=True)
la = shapely.area(shapely.intersection(a.geometry.values, lost, grid_size=0.01))
k = la > 1.0
d = a.loc[k, ['src_id', 'src_sheet', 'hclass', 'scale_den']].assign(lost_m2=la[k].round(0),
                                                                    poly_m2=a.area.values[k].round(0))
d['whole'] = (d['lost_m2'] >= 0.99 * d['poly_m2'])
print(f'\nold polygons losing > 1 m2: {len(d)}  (wholly lost: {int(d["whole"].sum())})')
print(d.sort_values('lost_m2', ascending=False).head(30).to_string())
print(d.groupby('src_id')['lost_m2'].agg(['count', 'sum']).sort_values('sum', ascending=False).head(10).to_string())
print('\nlargest missing pieces (m2, point):')
for p in sorted(shapely.get_parts(lost), key=lambda p: -p.area)[:12]:
    print(round(p.area), p.representative_point().wkt)
