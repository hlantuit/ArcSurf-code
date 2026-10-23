"""Russian IMW 1:1M frames whose permafrost is still on the 1:2.5M fallback, measured on the MERGED layer
(out/coverage_class.tif from coverage_map.py: finest source class per 2.5 km cell; class 5 = >= 1:2.5M,
6 = no source) instead of from sheet codes (ru1m_missing.py subtracts the frames named by the merged sheet
codes, so a combined sheet registered under one code, e.g. S-51_g3 = S-51 + S-52, left S-52 'missing', and a
sheet extracted only in part, e.g. P-54-55_g2 without its O-55 block, was counted as covering nothing there).
Permafrost = Obu et al. 2019 zones (work/domain_obu_amap.gpkg 'permafrost_zones') inside Russia (Natural Earth).
Frames are single IMW sheets (6 x 4 deg). Columns 'held' / 'geokniga' are carried over from work/ru1m_missing.csv.
usage: ru1m_missing_cov.py [min_km2=2000]   -> work/ru1m_missing_cov.csv"""
import sys

import numpy as np
import pandas as pd
import pyproj
import rasterio
import rasterio.features as rf

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import surflib as S  # noqa: E402

W0 = '/albedo/work/user/hlantuit/arctic_surficial'
min_km2 = float(sys.argv[1]) if len(sys.argv) > 1 else 2000.0
r = rasterio.open(f'{S.OUT}/coverage_class.tif'); g = r.read(1); tf = r.transform
cell = abs(tf.a * tf.e) / 1e6
ne = gpd.read_file(f'{W0}/raw/naturalearth/ne_10m_admin_0_countries.shp')
ru = ne[ne['ADM0_A3'].eq('RUS')].to_crs(r.crs).union_all()
pf = gpd.read_file(f'{S.WORK}/domain_obu_amap.gpkg', layer='permafrost_zones').to_crs(r.crs)
zone_r = np.zeros(g.shape, np.uint8)
zones = list(pf['zone'])
for k, (z, geom) in enumerate(zip(pf['zone'], pf.geometry), 1):
    m = rf.rasterize([(shapely.intersection(shapely.make_valid(geom), ru), 1)], out_shape=g.shape, transform=tf,
                     fill=0, dtype='uint8') == 1
    zone_r[m & (zone_r == 0)] = k
rows, cols = np.nonzero((zone_r > 0) & (g > 0))
x = tf.c + (cols + 0.5) * tf.a; y = tf.f + (rows + 0.5) * tf.e
lon, lat = pyproj.Transformer.from_crs(r.crs, 4326, always_xy=True).transform(x, y)
lon = np.where(lon < 0, lon + 360, lon)
letter = np.array(list('ABCDEFGHIJKLMNOPQRSTUV'))[np.clip((lat // 4).astype(int), 0, 21)]
num = np.where(lon < 180, np.floor(lon / 6).astype(int) + 31, np.floor((lon - 180) / 6).astype(int) + 1)
sheet = np.char.add(np.char.add(letter.astype(str), '-'), num.astype(str))
c = g[rows, cols]; zr = zone_r[rows, cols]
df = pd.DataFrame(dict(sheet=sheet, missing=(c >= 5), zone=[zones[k - 1] for k in zr]))
pf_km2 = df.groupby('sheet').size() * cell
miss = df[df.missing]
t = (miss.groupby(['sheet', 'zone']).size().unstack(fill_value=0) * cell).round()
t.columns = [f'z_{z}' for z in t.columns]
t['missing_km2'] = t.sum(1)
t['pf_km2'] = pf_km2.reindex(t.index).round()
t = t[t.missing_km2 >= min_km2].sort_values('missing_km2', ascending=False)
old = pd.read_csv(f'{S.WORK}/ru1m_missing.csv', keep_default_na=False).set_index('sheet')
for ccol in ('held', 'geokniga', 'lon0', 'lat0', 'lon1', 'lat1'):
    if ccol in old:
        t[ccol] = old[ccol].reindex(t.index).fillna('')
t.reset_index().to_csv(f'{S.WORK}/ru1m_missing_cov.csv', index=False)
print(f'{len(t)} frames, {t.missing_km2.sum() / 1e6:.2f} M km2 of Russian permafrost on >= 1:2.5M or no source')
both = set(t.index) | set(old.index)
cmp = pd.DataFrame({'codes': old['missing_km2'].reindex(sorted(both)), 'merged': t['missing_km2'].reindex(sorted(both))}).fillna(0).round(-2)
cmp['diff'] = cmp.merged - cmp.codes
print(cmp[cmp['diff'].abs() >= 2000].sort_values('diff').to_string())
