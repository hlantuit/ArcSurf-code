#!/usr/bin/env python
"""
Faroe Islands (Hugues 2026-09-30: 'let's add it'). No digital surficial map exists (the
Rasmussen & Noe-Nygaard 1969 1:50k map is bedrock only), so a PROXY from the Umhvørvisstovan
habitat layer 'Lendissløg í Føroyum' (KMS 1:20k topographic terrain classes, 1990; ArcGIS REST
gis.us.fo .../margfeldi/us_lendisslog/MapServer/0; attribution licence 'Data from the Faroese
Environment Agency, Umhvørvisstovan'):
  svarðloysi (no turf: scree / bare ground) -> C (hclass2 R), bouldery
  hellusvað  (bare rock flats)              -> R
  mýra       (mire)                         -> O, organic
  vatn       (water)                        -> DROP
  bøur, lyngur and ALL OTHER LAND (no habitat polygon) -> W 'thin till / regolith over
             Palaeogene basalt, INFERRED' (hclass2 T, veneer) - flagged in src_desc
No permafrost (Humlum & Christiansen 1998) -> pf_zone 'none' from the merge.
usage: ingest_faroe.py download | ingest"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402

URL = 'https://gis.us.fo/arcgis/rest/services/margfeldi/us_lendisslog/MapServer/0/query'
RAWF = f'{S.RAW}/faroe/us_lendisslog.geojson'
UA = {'User-Agent': 'AWI-research/1.0 (+https://www.awi.de)'}
SRC = 'fo_us_lendisslog'
MAP = {'svarðloysi': ('C', 'R', 'bouldery', '', 'scree / bare ground (no turf)'),
       'hellusvað': ('R', '', '', '', 'bare rock flats'),
       'mýra': ('O', '', 'organic', '', 'mire'),
       'vatn': ('DROP', '', '', '', 'water'),
       'REGOLITH': ('W', 'T', 'mixed', 'veneer', 'thin till / regolith over basalt, INFERRED (infield, heath or no habitat polygon)')}


def download():
    os.makedirs(os.path.dirname(RAWF), exist_ok=True)
    feats, off = [], 0
    while True:
        q = dict(where='1=1', outFields='OBJECTID,ground_type,collection_date,collected_by', outSR=4326,
                 f='geojson', resultOffset=off, resultRecordCount=2000, orderByFields='OBJECTID')
        url = URL + '?' + urllib.parse.urlencode(q)
        for i in range(4):
            try:
                d = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180)); break
            except Exception as e:
                time.sleep(10 * (i + 1)); err = e
        else:
            raise err
        f = d.get('features', [])
        feats += f
        print('offset', off, 'got', len(f), 'total', len(feats), flush=True)
        if len(f) < 2000:
            break
        off += 2000
        time.sleep(2)
    json.dump(dict(type='FeatureCollection', features=feats), open(RAWF, 'w'))
    print('wrote', RAWF, len(feats))
    assert len(feats) >= 14000, 'expected ~14,200 polygons'


def ingest():
    g = gpd.read_file(RAWF).to_crs(S.CRS)
    g = S.polygons_only(g)
    g['gt'] = g['ground_type'].fillna('').str.strip()
    g.loc[~g['gt'].isin(['svarðloysi', 'hellusvað', 'mýra', 'vatn']), 'gt'] = 'REGOLITH'
    # land of the islands (build land mask) minus the habitat polygons -> inferred regolith
    box = gpd.GeoSeries([shapely.box(-7.8, 61.3, -6.2, 62.5)], crs=4326).to_crs(S.CRS).iloc[0]
    land = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='land', bbox=box.bounds)
    land_u = shapely.make_valid(shapely.union_all(land.geometry.values))
    rest = shapely.difference(land_u, shapely.make_valid(shapely.union_all(g.geometry.values)))
    r = gpd.GeoDataFrame(dict(gt=['REGOLITH']), geometry=[rest], crs=S.CRS)
    g = S.polygons_only(gpd.GeoDataFrame(pd.concat([g[['gt', 'geometry']], r], ignore_index=True), crs=S.CRS))
    g['desc'] = g['gt'].map(lambda k: MAP[k][4])
    u, _ = S.standardise(g, src_id=SRC, code='gt', desc='desc', xkey='gt', scale_den=20_000, pub_year=1990,
                         conf_tier='Predictive',
                         licence='Data from the Faroese Environment Agency, Umhvørvisstovan (Lendissløg í Føroyum); habitat proxy, not a geological map',
                         redistribution='open')
    S.write_std(u, S.footprint_from_units(u), SRC, dict(title='Faroe Islands: surficial PROXY from Umhvørvisstovan habitat types (KMS 1:20k, 1990)'))
    pd.DataFrame([[k, *v[:4], '', v[4]] for k, v in MAP.items()],
                 columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(f'{S.XWALK}/{SRC}.csv', index=False)
    print(SRC, len(u), 'polygons', round(u.area.sum() / 1e6), 'km2', u.groupby('src_code').geometry.apply(lambda s: round(s.area.sum() / 1e6)).to_dict())


if __name__ == '__main__':
    import urllib.parse  # noqa: F401
    {'download': download, 'ingest': ingest}[sys.argv[1]]()
