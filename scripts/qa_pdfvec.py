#!/usr/bin/env python
"""QA figure for a PDF-extracted sheet: polygons in their source colours over the
OSM coastline, for a lon/lat window. usage: qa_pdfvec.py <gpkg> <lon0> <lat0> <lon1> <lat1> <out.png>"""
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

g, lo0, la0, lo1, la1, out = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6]
box = gpd.GeoSeries([shapely.segmentize(shapely.box(lo0, la0, lo1, la1), 0.05)], crs=4326).to_crs(S.CRS)
b = box.total_bounds
u = gpd.read_file(g, layer='units', bbox=tuple(b))
land = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='land', bbox=tuple(b))
coast = shapely.boundary(shapely.intersection(shapely.union_all(land.geometry.values), box.iloc[0]))
fig, ax = plt.subplots(figsize=(11, 11))
u.plot(ax=ax, color=u['fill'], edgecolor='k', linewidth=0.15)
gpd.GeoSeries([coast], crs=S.CRS).plot(ax=ax, color='red', linewidth=0.8)
ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3]); ax.set_aspect('equal')
ax.set_title(f'{g.split("/")[-1]}: extracted polygons (source colours), OSM coastline in red')
fig.savefig(out, dpi=110, bbox_inches='tight')
print('saved', out)
