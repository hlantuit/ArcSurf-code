#!/usr/bin/env python
"""Tiles whose ice comes only from the source maps (no row in work/ice_by_tile.gpkg): does RGI 6.0 really have no glacier
there, or did the ice build miss the tile? For each such tile: the source-ice area and the RGI glacier area intersecting
the tile (read directly from the RGI zips). usage: ice_source_only_check.py"""
import glob
import os
import sys
import zipfile

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402
import surflib as S  # noqa: E402

a = pd.read_csv(f'{S.WORK}/ice_sliver_audit.csv')
ib = pyogrio.read_dataframe(f'{S.WORK}/ice_by_tile.gpkg', layer='ice', columns=['tile_id'], read_geometry=False)
src_only = a[(a['ice_km2'] > 0) & ~a['tile_id'].isin(set(ib['tile_id']))].copy()
tl = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='tiles')
tl = tl[tl['tile_id'].isin(src_only['tile_id'])].to_crs(4326)
box = shapely.box(*tl.total_bounds)
rgi = []
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'          # where ice_build.py reads RGI / PROMICE
for z in sorted(glob.glob(f'{RAW}/rgi/[01][0-9]_rgi60_*.zip')):
    if os.path.basename(z)[:2] == '00':                 # 00_rgi60_regions / summary are not glaciers
        continue
    shp = [n for n in zipfile.ZipFile(z).namelist() if n.endswith('.shp')]
    if not shp:
        continue
    g = pyogrio.read_dataframe(f'/vsizip/{z}/{shp[0]}', bbox=box.bounds, columns=['RGIId', 'Area'])
    if len(g):
        rgi.append(g.to_crs(4326))
R = gpd.GeoDataFrame(pd.concat(rgi, ignore_index=True), crs=4326) if rgi else None
print('RGI glaciers read in the bbox:', 0 if R is None else len(R))
pf = glob.glob(f'{RAW}/promice/*polygon*.gpkg')[0]
pcrs = pyogrio.read_info(pf)['crs']
PM = gpd.read_file(pf, mask=gpd.GeoSeries([box], crs=4326).to_crs(pcrs).iloc[0]).to_crs(4326)
print('PROMICE polygons read in the bbox:', len(PM))
rows = []
for _, t in tl.iterrows():
    n = ar = 0
    if R is not None:
        hit = R[R.intersects(t.geometry)]
        n = len(hit)
        if n:
            ar = float(gpd.GeoSeries(hit.intersection(t.geometry), crs=4326).to_crs(6931).area.sum() / 1e6)
    pm = PM[PM.intersects(t.geometry)]
    pa = float(gpd.GeoSeries(pm.intersection(t.geometry), crs=4326).to_crs(6931).area.sum() / 1e6) if len(pm) else 0.0
    rows.append(dict(tile_id=t['tile_id'], rgi_glaciers=n, rgi_km2=round(ar, 2), promice_km2=round(pa, 2)))
d = src_only[['tile_id', 'ice_km2']].merge(pd.DataFrame(rows), on='tile_id')
d.to_csv(f'{S.WORK}/ice_source_only_tiles.csv', index=False)
print('source-ice-only tiles', len(d), '| source ice km2', round(d['ice_km2'].sum(), 1))
print('tiles where RGI or PROMICE HAS ice (ice build missed them?):', int(((d['rgi_km2'] > 0) | (d['promice_km2'] > 0)).sum()),
      '| RGI km2', round(d['rgi_km2'].sum(), 1), '| PROMICE km2', round(d['promice_km2'].sum(), 1))
print(d.sort_values('ice_km2', ascending=False).head(15).to_string(index=False))
