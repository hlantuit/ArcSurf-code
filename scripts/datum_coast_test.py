#!/usr/bin/env python
"""Which datum is an extracted sheet really on? Compare its mapped shoreline with the
OSM coastline under two readings of the same lon/lat numbers: Pulkovo-1942 (4284,
current) vs WGS 84 (4326). Sea = large offshore-unit polygons (area > min_km2).
Distance measured from OSM coastline sample points (within 3 km of the mapped sea
edge) to the mapped sea boundary; median, IQR and the median offset VECTOR (a
consistent datum shift shows up as a coherent vector, noise does not).
usage: datum_coast_test.py <sheet.gpkg> <sea_index,...> [min_km2]"""
import sys

import numpy as np
import geopandas as gpd
import pyogrio
import pyproj
import shapely

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

gp, sea_idx = sys.argv[1], sys.argv[2].split(',')
min_km2 = float(sys.argv[3]) if len(sys.argv) > 3 else 100
u = gpd.read_file(gp, layer='units')
sea = u[u['index'].isin(sea_idx) & (u.area > min_km2 * 1e6)]
print(f'{len(sea)} offshore polygons > {min_km2} km2, {sea.area.sum()/1e6:,.0f} km2')
seaU = shapely.union_all(sea.geometry.values)
land = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='land', bbox=tuple(shapely.bounds(shapely.buffer(seaU, 5000))))
landU = shapely.union_all(land.geometry.values)
frame = gpd.read_file(gp, layer='neatline').geometry.iloc[0]
coast = shapely.intersection(shapely.boundary(landU), shapely.buffer(frame, -2000))

to_ll = pyproj.Transformer.from_crs(S.CRS, 4284, always_xy=True)
as4326 = pyproj.Transformer.from_crs(4326, S.CRS, always_xy=True)


def reread(g):   # same lon/lat numbers, read as WGS 84 instead of Pulkovo
    return shapely.transform(g, lambda xy: np.c_[as4326.transform(*to_ll.transform(xy[:, 0], xy[:, 1]))])


for name, sg in (('Pulkovo-1942 (4284)', seaU), ('WGS 84 (4326)', reread(seaU))):
    edge = shapely.boundary(sg)
    near = shapely.intersection(coast, shapely.buffer(edge, 3000))
    pts = shapely.points(shapely.get_coordinates(shapely.segmentize(near, 200)))
    if len(pts) == 0:
        print(name, 'no coastline near the mapped sea edge')
        continue
    nearest = shapely.shortest_line(pts, edge)
    c = shapely.get_coordinates(nearest).reshape(-1, 2, 2)
    v = c[:, 1] - c[:, 0]
    d = np.hypot(v[:, 0], v[:, 1])
    q = np.percentile(d, [25, 50, 75])
    mv = np.median(v, axis=0)
    print(f'{name:22s} n={len(d):6d}  median {q[1]:6.0f} m  IQR {q[0]:.0f}-{q[2]:.0f} m  '
          f'median offset vector ({mv[0]:+.0f}, {mv[1]:+.0f}) m, |v|={np.hypot(*mv):.0f} m')
