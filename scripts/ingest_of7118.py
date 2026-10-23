#!/usr/bin/env python
"""
GSC Open File 7118 (Byatt et al. 2013?, see report), Remote predictive mapping of surficial earth materials:
Wager Bay North area, Nunavut (NTS 56-G, 56-H north, 56-I, 56-J south); DOI 10.4095/293158.
Source raster data/images/classifications/of_7118_rcm_majority_classification.img: robust-classification majority
map, 30 m pixels, NAD83 UTM 16N (EPSG:26916), uint8 classes with category names (GDAL). Class meanings from the
report, Table 3 (training classes, Landsat 7/4/2 + DEM): see XW below. 'Masked Pixels' (water / ice / outside) and
'Unclassified' are dropped.
Processing: 5 x 5 majority filter over the valid classes, sieve to 100 pixels (9 ha; the map is read at 1:250 000),
polygonise, crosswalk. Tier 'Predictive' (remote predictive map, not field-checked surficial geology).
Source -> ca_gsc_of7118. usage: ingest_of7118.py
"""
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.features as rf
from scipy import ndimage as ndi
from shapely.geometry import shape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

SRC = 'ca_gsc_of7118'
IMG = ('/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/ostr_new/293158/x/data/images/classifications/'
       'of_7118_rcm_majority_classification.img')
# category name -> hclass, hclass2, texture, cover, description (report Table 3)
XW = {
    'Ap': ('F', '', 'sand', 'unknown', 'Sand and minor silt: exposed or water-saturated; alluvial terraces, plains, deltas and fans; '
           'eolian veneers and dunes; intertidal flats'),
    'Mg': ('M', 'GL', 'fines', 'blanket', 'Silt and clay: exposed thick marine or glaciolacustrine deposits with gullied slopes'),
    'Ms_1': ('M', 'GL', 'fines', 'blanket', 'Silt, clay and fine sand: grass-covered; thick marine or glaciolacustrine deposits'),
    'Ms_2': ('M', 'GL', 'sand', 'unknown', 'Fine sand and silt: grass- and lichen-covered; locally wave-washed; marine or '
             'glaciolacustrine deposits (Ms2 + SG2)'),
    'O': ('O', '', 'organic', 'unknown', 'Organics: saturated, poorly drained; shallow sedge fens and sphagnum bogs'),
    'SG_1': ('GF', 'M', 'gravel', 'unknown', 'Sand and gravel: mainly grass- and/or lichen-covered; beaches, deltas, eskers, '
             'outwash terraces, ice-contact glaciofluvial deposits'),
    'Tb_1': ('T', '', 'diamicton', 'blanket', 'Non-bouldery till: silty-sand diamicton; thick deposits, grass- and lichen-covered; '
             'blanket and streamlined till'),
    'Tb_2': ('T', '', 'diamicton', 'blanket', 'Bouldery till: silty-sand to sandy diamicton; thick streamlined till and till blankets '
             'with abundant lichen-covered boulders'),
    'B': ('W', 'R', 'bouldery', 'unknown', 'Boulders: exposed and lichen-covered felsenmeer and boulder fields'),
    'Ct': ('T', '', 'diamicton', 'unknown', 'Carbonate-rich till: sandy-silt matrix-rich calcareous diamicton; solifluction stripes common'),
    'R1': ('R', '', 'unknown', 'unknown', 'Undifferentiated bedrock: exposed outcrop; sporadic boulders'),
    'R2': ('R', 'T', 'unknown', 'veneer', 'Undifferentiated bedrock: lichen-covered outcrop and felsenmeer; patches of boulders and '
           'thin drift cover'),
}

with rasterio.open(IMG) as r:
    a = r.read(1)
    tf, crs = r.transform, r.crs
    names = r.descriptions  # band descriptions, not categories
from osgeo import gdal  # noqa: E402
ds = gdal.Open(IMG)                       # keep the dataset referenced: a chained call lets it be collected
cats = ds.GetRasterBand(1).GetCategoryNames()
lut = {i: n.replace('_final', '') for i, n in enumerate(cats)}
valid_ids = [i for i, n in lut.items() if n in XW]
print('classes:', {i: lut[i] for i in valid_ids}, '| other:', {i: n for i, n in lut.items() if i not in valid_ids})
valid = np.isin(a, valid_ids)
# 5 x 5 majority among valid classes (invalid pixels do not vote and stay invalid)
best = np.zeros(a.shape, np.float32); arg = np.zeros(a.shape, np.uint8)
for i in valid_ids:
    cnt = ndi.uniform_filter((a == i).astype(np.float32), 5)
    m = cnt > best
    best[m], arg[m] = cnt[m], i
arg[~valid] = 0
arg = rf.sieve(arg, size=100, mask=valid)
arg[~valid] = 0
print(f'valid pixels {valid.mean():.1%}, area {valid.sum() * 900 / 1e6:.0f} km2')
rows = [dict(cls=lut[int(v)], geometry=shape(g)) for g, v in rf.shapes(arg, mask=arg > 0, transform=tf)]
g = gpd.GeoDataFrame(rows, crs=crs)
g['geometry'] = g.geometry.simplify(15.0)
g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
g['xkey'] = g['cls']
g['desc'] = g['cls'].map(lambda k: XW[k][4])
u, _ = S.standardise(g, src_id=SRC, code='xkey', desc='desc', xkey='xkey', scale_den=250_000, pub_year=2013,
                     conf_tier='Predictive', licence='Open Government Licence - Canada', redistribution='open')
p, m = S.write_std(u, S.footprint_from_units(u, coarse=250.0), SRC,
                   dict(title='GSC OF 7118 remote predictive surficial earth materials, Wager Bay North (30 m classification, '
                              'majority-filtered and sieved to 9 ha)'))
pd.DataFrame([[k, *v[:4], 'unknown', f'OF 7118 class {k}: {v[4]}'] for k, v in XW.items()],
             columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(
    f'{S.XWALK}/{SRC}.csv', index=False)
print(SRC, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes') if k in m})
print(u.assign(km2=u.area / 1e6).groupby('xkey').km2.sum().round().to_dict())
