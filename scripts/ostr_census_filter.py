"""Post-filter of sources/canada_ostr_census.json: keep NEW maps (not in the 650-sheet
inventory) at scale <= 1:500k whose bbox intersects the domain (AMAP land UNION Obu 2019
permafrost, work/domain_obu_amap.gpkg), drop non-surficial themes (peat bog surveys, dam sites,
InSAR, bathymetry, volcanic complexes, bedrock). Writes sources/canada_ostr_new_in_domain.csv
sorted by scale; flags the Tuktoyaktuk / Mackenzie Delta window (-138..-127 W, 68..70.5 N)."""
import json
import re

import geopandas as gpd
import pandas as pd
import shapely

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
x = pd.DataFrame(json.load(open(f'{ROOT}/sources/canada_ostr_census.json', encoding='utf-8')))
x = x[~x.in_inventory & x.scale.notna() & (x.scale <= 500000)].copy()
bad = r'peat bog|dam site|insar|bathymetr|volcanic|bedrock geology|gold values|field trip|optional trip|seasonal surface displacement|nearshore sedimentation'
x = x[~x.title.str.lower().str.contains(bad)]


def box(b):
    if not b:
        return None
    lons = [v for v in b if v < -50]
    lats = [v for v in b if 40 <= v <= 90]
    if len(lons) < 1 or len(lats) < 1:
        return None
    return shapely.box(min(lons), min(lats), max(lons), max(lats)) if len(lons) > 1 and len(lats) > 1 else shapely.Point(lons[0], lats[0]).buffer(0.1)


x['geometry'] = [box(b) for b in x.bbox_n]
x = gpd.GeoDataFrame(x[x.geometry.notna()], crs=4326)
dom = gpd.read_file(f'{ROOT}/work/domain_obu_amap.gpkg').to_crs(4326)
dom = shapely.make_valid(dom.union_all())
x = x[x.intersects(dom)].copy()
tuk = shapely.box(-138, 68, -127, 70.5)
x['tuk_delta'] = x.intersects(tuk)
x['bbox'] = [','.join(f'{v:.2f}' for v in g.bounds) for g in x.geometry]
out = pd.DataFrame(x.drop(columns=['geometry', 'bbox_n'])).sort_values(['tuk_delta', 'scale'], ascending=[False, True])
out.to_csv(f'{ROOT}/sources/canada_ostr_new_in_domain.csv', index=False)
print('new, <= 1:500k, in domain:', len(out), '| Tuk/Delta window:', int(out.tuk_delta.sum()))
print(out.groupby(pd.cut(out.scale, [0, 50000, 125000, 250000, 500000])).size().to_dict())
pd.set_option('display.width', 250)
print(out[['geoscan', 'scale', 'year', 'filetype', 'tuk_delta', 'title']].head(70).to_string(index=False))
