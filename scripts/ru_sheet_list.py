#!/usr/bin/env python
"""
IMW / Gosgeolkarta 1:1,000,000 sheet list for Arctic Russia, ranked by coastline.

Sheet grid: rows by 4 deg latitude (P 60-64, Q 64-68, R 68-72, S 72-76, T 76-80,
U 80-84, V 84-88), columns by 6 deg longitude, column n spanning
(n-31)*6 .. (n-30)*6 deg E (column 1 starts at 180 W).  VSEGEI publishes combined
editions north of 60 N (double sheets such as Q-50,51; triples such as S-50-52), so
single sheets are listed and the Bryant coverage is shown per single sheet.

Per sheet: land km2 inside AMAP within Russia (OSM land mask x Natural Earth admin-0),
coastline km (boundary of dissolved land minus the sheet edge; the OSM 'split'
product's artificial cut lines are removed by dissolving first), and whether the
open Bryant subset covers it.
Output: out/ru_imw_sheets.csv
"""
import os
import sys
import zipfile
import urllib.request

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

NE = f'{S.RAW}/naturalearth'
NE_URL = 'https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip'
ROWS = {'P': 60, 'Q': 64, 'R': 68, 'S': 72, 'T': 76, 'U': 80, 'V': 84}


def russia():
    os.makedirs(NE, exist_ok=True)
    z = f'{NE}/ne_10m_admin_0_countries.zip'
    if not os.path.exists(z):
        req = urllib.request.Request(NE_URL, headers={'User-Agent': 'AWI-research/1.0 (+https://www.awi.de)'})
        open(z, 'wb').write(urllib.request.urlopen(req, timeout=300).read())
        zipfile.ZipFile(z).extractall(NE)
    c = gpd.read_file(f'{NE}/ne_10m_admin_0_countries.shp')
    r = c[c['ADM0_A3'] == 'RUS']
    assert len(r) == 1
    return r.geometry.iloc[0]


def main():
    rus_ll = russia()
    bry = pyogrio.read_dataframe(f'{S.WORK}/xw/ru_bryant_vsegei1m.gpkg', layer='footprint')
    bry_u = shapely.union_all(bry.geometry.values)
    rows = []
    for letter, lat0 in ROWS.items():
        for col in range(1, 61):
            lon0 = (col - 31) * 6
            cell_ll = shapely.box(lon0, lat0, lon0 + 6, lat0 + 4)
            if not shapely.intersects(cell_ll, rus_ll):
                continue
            rus_cell = shapely.intersection(cell_ll, rus_ll)
            # densify before reprojecting: sheet edges are meridians/parallels
            cell = gpd.GeoSeries([shapely.segmentize(cell_ll, 0.05)], crs=4326).to_crs(S.CRS).iloc[0]
            rc = gpd.GeoSeries([shapely.segmentize(rus_cell, 0.05)], crs=4326).to_crs(S.CRS).iloc[0]
            land = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='land', bbox=cell.bounds)
            if land.empty:
                continue
            lt = shapely.intersection(shapely.union_all(land.geometry.values), cell)
            lt = shapely.intersection(lt, shapely.buffer(rc, 5000))   # 5 km slack for NE's coarse coast
            if lt.is_empty or lt.area < 1e6:
                continue
            coast = shapely.difference(shapely.boundary(lt), shapely.buffer(shapely.boundary(cell), 10))
            # land borders (Norway/Finland/USA) are not coast: drop boundary far from the sea
            bryant = shapely.intersection(lt, bry_u).area / lt.area
            rows.append(dict(sheet=f'{letter}-{col}', lat=f'{lat0}-{lat0+4}N',
                             lon=f'{lon0}-{lon0+6}' + ('E' if lon0 >= 0 else ''),
                             land_km2=round(lt.area / 1e6), coast_km=round(coast.length / 1e3),
                             bryant_frac=round(bryant, 2)))
            print(rows[-1], flush=True)
    df = pd.DataFrame(rows).sort_values('coast_km', ascending=False)
    df['rank'] = np.arange(1, len(df) + 1)
    os.makedirs(S.OUT, exist_ok=True)
    df.to_csv(f'{S.OUT}/ru_imw_sheets.csv', index=False)
    print(df.to_string(index=False))
    print('sheets', len(df), 'land km2', df.land_km2.sum(), 'coast km', df.coast_km.sum(),
          'with >50% Bryant', int((df.bryant_frac > 0.5).sum()))


if __name__ == '__main__':
    main()
