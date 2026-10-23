#!/usr/bin/env python
"""Prepare Bryant coastal sheets for datum_coast_test.py: re-express the ingested
units (read as EPSG:4326 at ingest) as if their lon/lat were Pulkovo-1942, so the
test's '4284' reading = Pulkovo and its '4326' reading = Bryant as labelled.
Offshore units (shelf / submerged / marine stream) -> index 'SEA'."""
import sys

import numpy as np
import geopandas as gpd
import pyproj
import shapely

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

u = gpd.read_file(f'{S.STD}/ru_bryant_vsegei1m.gpkg', layer='units')
to_ll = pyproj.Transformer.from_crs(S.CRS, 4326, always_xy=True)
from4284 = pyproj.Transformer.from_crs(4284, S.CRS, always_xy=True)
for sh in sys.argv[1:]:
    s = u[u['src_sheet'] == sh].copy()
    sea = s['xkey'].str.contains('shallow shelves|Shallow Shelves|Submerged|Marine Stream', regex=True)
    s['index'] = s['xkey'].where(~sea, 'SEA')
    s['geometry'] = shapely.transform(s.geometry.values,
                                      lambda xy: np.c_[from4284.transform(*to_ll.transform(xy[:, 0], xy[:, 1]))])
    out = f'/tmp/hl_bry_{sh.replace(",", "_")}.gpkg'
    s[['index', 'geometry']].to_file(out, layer='units', driver='GPKG')
    gpd.GeoDataFrame(geometry=[shapely.union_all(shapely.make_valid(s.geometry.values))], crs=S.CRS) \
        .to_file(out, layer='neatline', driver='GPKG')
    print(sh, int(sea.sum()), 'sea polygons ->', out)
