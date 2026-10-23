#!/usr/bin/env python
"""Test the seam tools on R-52 (PDF) vs Bryant Q-52,53 along 68N, 126-132E.
Bryant read as Pulkovo-1942 (the project decision), band-snapped to its exact frame,
crosswalked; R-52 crosswalked; then match_seam on the shared edge. Writes
work/seam_test.gpkg (both sheets before/after, pairs, conflicts) and prints stats."""
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import seam  # noqa: E402

B = '/albedo/work/user/hlantuit/arcticbeach/data/bryant_siberia/SiberianDatabase-open'
OUT = f'{S.WORK}/seam_test.gpkg'

# Bryant Q-52,53 as Pulkovo, with hclass via its crosswalk (genetic-type names)
raw = gpd.read_file(f'{B}/GeologicPolygonQ5253_open.shp')
bounds = raw.total_bounds
lut = pyogrio.read_dataframe(f'{B}/GeneticTypeSymbol.dbf', read_geometry=False)
lut = lut[lut['Map'] == 'Q52,53'].drop_duplicates('Symbol')
raw['xkey'] = raw['GeneticTyp'].str.strip().map(dict(zip(lut['Symbol'].str.strip(), lut['GeneticTyp'])))
b = raw.set_crs(4284, allow_override=True).to_crs(S.CRS)
x = S.load_xwalk('ru_bryant_vsegei1m').drop_duplicates('xkey').set_index('xkey')['hclass']
b['hclass'] = b['xkey'].map(x).fillna('Q')
b = S.polygons_only(b[['xkey', 'hclass', 'geometry']])
b2, rep = seam.band_snap(b, bounds, datum=4284, band=500)
print('Bryant Q-52,53 band snap:', rep)

# R-52 with hclass
r = gpd.read_file(f'{S.WORK}/pdfvec/R-52.gpkg', layer='units')
xr = S.load_xwalk('ru_vsegei_pdf').set_index('xkey')['hclass']
r['hclass'] = ('R-52|' + r['index']).map(xr).fillna('Q')
r, rep_r = seam.band_snap(r[['index', 'hclass', 'geometry']], (126, 68, 132, 72), datum=4284, band=200)
print('R-52 band snap:', rep_r)

edge = seam.exact_frame_lines(126, 68, 132, 72, 4284)['S']
# only the part of Bryant Q-52,53's north edge that R-52 shares (126-132E)
bn = b2[shapely.dwithin(b2.geometry.values, edge, 5000)]
rn = r[shapely.dwithin(r.geometry.values, edge, 5000)]
gap_before = shapely.intersection(shapely.buffer(edge, 1000),
                                  shapely.difference(shapely.buffer(edge, 1000),
                                                     shapely.union_all(np.r_[b.geometry.values, r.geometry.values]))).area
gap_after = shapely.intersection(shapely.buffer(edge, 1000),
                                 shapely.difference(shapely.buffer(edge, 1000),
                                                    shapely.union_all(np.r_[b2.geometry.values, r.geometry.values]))).area
ov_before = shapely.intersection(shapely.union_all(b.geometry.values), shapely.union_all(r.geometry.values)).area
ov_after = shapely.intersection(shapely.union_all(b2.geometry.values), shapely.union_all(r.geometry.values)).area
print(f'seam strip (2 km wide): gap {gap_before/1e6:.2f} -> {gap_after/1e6:.2f} km2; overlap {ov_before/1e6:.2f} -> {ov_after/1e6:.2f} km2')

A2, B2, pairs, conf, stats = seam.match_seam(rn[['hclass', 'geometry']], bn[['hclass', 'geometry']], edge,
                                             tol=1000, band=3000)
print('seam match R-52 | Q-52,53:', stats)
print(pairs.head(10).to_string())
print('conflict classes (a=R-52, b=Bryant), km:',
      (conf.groupby(['a', 'b']).size() * 25 / 1e3).sort_values(ascending=False).head(12).to_dict())
for lyr, g in (('bryant_raw', b), ('bryant_snapped', b2), ('r52', r), ('r52_matched', A2), ('bryant_matched', B2)):
    g.to_file(OUT, layer=lyr, driver='GPKG')
print('wrote', OUT)
