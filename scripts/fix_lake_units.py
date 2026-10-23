"""Reclassify lake-interior polygons that a raster sheet read as a deposit unit (bathymetric
contour bundles in a paper-coloured lake classify as the nearest pale unit) to WATER.
usage: fix_lake_units.py <jpgvec gpkg> <unit> lon0,lat0,lon1,lat1 <min_km2>
Polygons (exploded parts) of <unit> whose representative point lies in the lon/lat box and whose
area is >= min_km2 become index WATER (fill kept; ingest maps WATER -> H). Rewrites layer 'units'
in place and appends a record to <gpkg>.fixes.txt.
M-47-48_g2 (2026-10-02): lIV, 103.5,51.3,106.6,52.0, 500 km2 -> one 2,235 km2 polygon = Baikal."""
import sys

import geopandas as gpd
import pandas as pd
import shapely

path, unit, box, min_km2 = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
g = gpd.read_file(path, layer='units')
b = gpd.GeoSeries([shapely.box(*map(float, box.split(',')))], crs=4326).to_crs(g.crs).iloc[0]
e = g.explode(index_parts=False).reset_index(drop=True)
sel = (e['index'] == unit) & e.geometry.representative_point().within(b) & (e.area / 1e6 >= min_km2)
e.loc[sel, 'index'] = 'WATER'
for c in ('k',):
    if c in e:
        e.loc[sel, c] = ''
if 'description_ru' in e:
    e.loc[sel, 'description_ru'] = 'водоём'
out = e.dissolve(by=[c for c in ('index', 'fill') if c in e.columns], as_index=False, aggfunc='first')
out.to_file(path, layer='units', driver='GPKG')
msg = f'{unit} in {box} >= {min_km2} km2 -> WATER: {int(sel.sum())} polygons, {e[sel].area.sum() / 1e6:.0f} km2'
open(path + '.fixes.txt', 'a').write(msg + '\n')
print(msg)
