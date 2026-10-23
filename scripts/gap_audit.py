"""Gap audit: where should a finer source exist that we did not find?
Input: out/coverage_class.tif (coverage_map.py; finest source class per 2.5 km cell of land).
'Gap' = land whose finest source is 1:500k or coarser (classes 3-5) or none (6).

1. Countries (Natural Earth admin-0) of every gap cell: gap km2 by class.
2. Canada: each gap cell is checked against the GSC surficial catalogue (sources/canada_gsc_sheets.json,
   bbox_wgs84 + scale). Status:
   'catalogued, not processed' = a catalogued sheet at <= 1:250k covers the cell and is not in any merged
   source (the src_sheet values of the xw/ca_*.gpkg footprints);
   'catalogued, processed but not used here' = the covering sheet was processed but left the cell uncovered
   (mapping limit, QC fail, unmapped parts);
   'no catalogued product <= 1:250k' = what a deep search should look for (other agencies, theses, NTGS,
   Nunavut, provincial surveys).
   Aggregated to 1 x 2 deg blocks (1 x 4 deg north of 68N), written to out/gap_canada_blocks.csv.
3. Russia: per IMW 1:1M sheet, the share of land per class -> out/gap_russia_1m.csv. Sheets with only
   >= 1:2.5M = 1:1M gaps (see RU_1M_MISSING.md); sheets with 1:1M but < 5 % at <= 1:250k = 1:200k candidates.
4. Land with no source at all, by country.
usage: gap_audit.py   (writes out/gap_*.csv and prints a markdown summary)"""
import glob
import json
import sys

import numpy as np
import pandas as pd
import pyproj
import rasterio

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import geopandas as gpd  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
CLS = {1: '<=1:100k', 2: '1:125k-1:250k', 3: '1:500k-1:600k', 4: '1:1M', 5: '>=1:2.5M', 6: 'unmapped'}
with rasterio.open(f'{S.OUT}/coverage_class.tif') as r:
    g = r.read(1)
    tf = r.transform
cell_km2 = abs(tf.a * tf.e) / 1e6
rows, cols = np.nonzero(g > 0)
x = tf.c + (cols + 0.5) * tf.a
y = tf.f + (rows + 0.5) * tf.e
lon, lat = pyproj.Transformer.from_crs(S.CRS, 4326, always_xy=True).transform(x, y)
c = g[rows, cols]
gap = c >= 3
print(f'land cells {len(c)} ({len(c) * cell_km2 / 1e6:.2f} M km2); gap {gap.sum() * cell_km2 / 1e6:.2f} M km2')

# 1. countries
ne = gpd.read_file(f'{S.RAW}/naturalearth/ne_10m_admin_0_countries.shp')[['ADMIN', 'geometry']]
pts = gpd.GeoDataFrame(dict(cls=c), geometry=gpd.points_from_xy(lon, lat), crs=4326)
pts = gpd.sjoin(pts, ne, how='left', predicate='within')
pts = pts[~pts.index.duplicated()]
pts['ADMIN'] = pts['ADMIN'].fillna('(no country / sea)')
tab = pts.groupby(['ADMIN', 'cls']).size().unstack(fill_value=0) * cell_km2
tab.columns = [CLS[k] for k in tab.columns]
tab['gap_km2'] = tab[[v for k, v in CLS.items() if k >= 3 and v in tab]].sum(1)
tab = tab.sort_values('gap_km2', ascending=False)
tab.round().to_csv(f'{S.OUT}/gap_by_country.csv')
print('\n## Gap by country (km2; gap = best source 1:500k or coarser, or none)\n')
print(tab[tab.gap_km2 > 0].round(-2).astype(int).to_string())

# 2. Canada vs the GSC catalogue
cat = json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']
cat = [s for s in cat if s.get('bbox_wgs84') and (s.get('scale') or 10**9) <= 260_000]
done = set()
for f in glob.glob(f'{S.WORK}/xw/ca_*.gpkg'):
    try:
        fp = gpd.read_file(f, layer='footprint', ignore_geometry=True)
        done |= set(fp['src_sheet'].astype(str).str.split('_').str[0])
    except Exception:
        pass
ca = (pts['ADMIN'].values == 'Canada') & gap
idx = np.flatnonzero(ca)
status = np.full(len(idx), 'no catalogued product <= 1:250k', dtype=object)
cover = [[] for _ in idx]
lo, la = lon[idx], lat[idx]
for s in cat:
    w, so, e, n = s['bbox_wgs84']
    m = (lo >= w) & (lo <= e) & (la >= so) & (la <= n)
    for j in np.flatnonzero(m):
        cover[j].append(s['label'])
for j, labs in enumerate(cover):
    if labs:
        status[j] = ('catalogued, not processed' if any(l not in done for l in labs)
                     else 'catalogued, processed but not used here')
blk_lat = np.floor(la).astype(int)
wdeg = np.where(la >= 68, 4, 2)
blk_lon = (np.floor(lo / wdeg) * wdeg).astype(int)
df = pd.DataFrame(dict(lat0=blk_lat, lon0=blk_lon, w=wdeg, status=status, cls=[CLS[k] for k in c[idx]],
                       sheets=[';'.join(sorted(set(l for l in labs if l not in done))) for labs in cover]))
st = df.groupby('status').size() * cell_km2
print('\n## Canada gap by catalogue status (km2)\n')
print(st.round(-2).astype(int).to_frame('km2').to_string())
blk = df.groupby(['lat0', 'lon0', 'w', 'status']).agg(km2=('cls', 'size'),
                                                       best=('cls', lambda v: v.value_counts().index[0]),
                                                       unprocessed=('sheets', lambda v: ';'.join(sorted(set(';'.join(v).split(';')) - {''}))))
blk['km2'] = blk['km2'] * cell_km2
blk = blk.reset_index().sort_values('km2', ascending=False)
blk['block'] = blk.apply(lambda r: f"{r.lat0}-{r.lat0 + 1}N {abs(r.lon0 + r.w)}-{abs(r.lon0)}W", axis=1)
blk.to_csv(f'{S.OUT}/gap_canada_blocks.csv', index=False)
print('\n### Largest Canadian gap blocks with no catalogued product <= 1:250k\n')
print(blk[blk.status.str.startswith('no')].head(25)[['block', 'km2', 'best']].round().to_string(index=False))
print('\n### Largest Canadian gap blocks with catalogued but unprocessed sheets\n')
t = blk[blk.status.eq('catalogued, not processed')].head(25).copy()
t['unprocessed'] = t['unprocessed'].str.slice(0, 80)
print(t[['block', 'km2', 'best', 'unprocessed']].round().to_string(index=False))

# 3. Russia per IMW 1:1M sheet
ru = pts['ADMIN'].values == 'Russia'
lr, ar, cr = lon[ru], lat[ru], c[ru]
lr = np.where(lr < 0, lr + 360, lr)                      # Chukotka east of 180
letter = np.array(list('ABCDEFGHIJKLMNOPQRSTUV'))[np.clip((ar // 4).astype(int), 0, 21)]
num = np.where(lr < 180, (np.floor(lr / 6) + 31).astype(int), (np.floor((lr - 180) / 6) + 1).astype(int))
key = np.char.add(np.char.add(letter.astype(str), '-'), num.astype(str))
rdf = pd.DataFrame(dict(sheet=key, cls=[CLS[k] for k in cr]))
rt = rdf.groupby(['sheet', 'cls']).size().unstack(fill_value=0) * cell_km2
for v in CLS.values():
    if v not in rt:
        rt[v] = 0.0
rt['land_km2'] = rt.sum(1)
rt['fine_share'] = (rt['<=1:100k'] + rt['1:125k-1:250k']) / rt['land_km2']
rt['q2500_share'] = rt['>=1:2.5M'] / rt['land_km2']
rt = rt.sort_values('land_km2', ascending=False)
rt.round(3).to_csv(f'{S.OUT}/gap_russia_1m.csv')
g1 = rt[(rt.q2500_share > 0.5) & (rt.land_km2 > 5000)]
print(f'\n## Russia: {len(g1)} IMW 1:1M sheets mostly at >= 1:2.5M (1:1M gaps; see RU_1M_MISSING.md)\n')
print(', '.join(g1.index[:60]))
g2 = rt[(rt['1:1M'] / rt.land_km2 > 0.5) & (rt.fine_share < 0.05) & (rt.land_km2 > 5000)]
print(f'\n## Russia: {len(g2)} 1:1M sheets with < 5 % at <= 1:250k (1:200k candidates), largest first\n')
print(g2.head(40)[['land_km2', 'fine_share']].round(3).to_string())

# 4. no source at all
nz = pts[pts.cls == 6].groupby('ADMIN').size().sort_values(ascending=False) * cell_km2
print('\n## Land with no source at all (km2)\n')
print(nz.round(-2).astype(int).to_frame('km2').to_string())
