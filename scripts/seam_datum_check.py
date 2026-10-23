#!/usr/bin/env python
"""Seam offset between an extracted PDF sheet and its Bryant neighbours, with the
Bryant files read as EPSG:4326 (as labelled) vs EPSG:4284 (Pulkovo, native sheets).
usage: seam_datum_check.py <sheet.gpkg> <bryant_shp> [...]"""
import sys

import numpy as np
import geopandas as gpd
import shapely

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

B = '/albedo/work/user/hlantuit/arcticbeach/data/bryant_siberia/SiberianDatabase-open'
sheet = gpd.read_file(sys.argv[1], layer='neatline').geometry.iloc[0]
for f in sys.argv[2:]:
    g = gpd.read_file(f'{B}/{f}')
    print(f, 'raw bounds', [round(v, 4) for v in g.total_bounds])
    for epsg in (4326, 4284):
        u = shapely.union_all(shapely.make_valid(g.set_crs(epsg, allow_override=True).to_crs(S.CRS).geometry.values))
        ov = shapely.intersection(u, sheet).area / 1e6
        near = shapely.intersection(shapely.boundary(sheet), shapely.buffer(u, 3000))
        d = []
        if not near.is_empty:
            for t in np.linspace(0.05, 0.95, 19):
                p = shapely.line_interpolate_point(shapely.line_merge(near) if near.geom_type == 'MultiLineString' else near,
                                                   t, normalized=True)
                d.append(shapely.distance(p, shapely.boundary(u)))
        med = float(np.median(d)) if d else float('nan')
        print(f'   as EPSG:{epsg}: overlap with sheet {ov:9.2f} km2; seam offset median {med:7.1f} m (n={len(d)})')
