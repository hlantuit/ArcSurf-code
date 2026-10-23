"""Per-island coverage report: finest source now in the merge (work/tiles) and the candidate
maps known for the island (GSC index sheets + their scan/vector status, OSTR census items +
triage). Island = the land polygon (work/land_amap.gpkg) containing a seed point.
usage: island_coverage.py  -> prints a report, writes work/island_coverage.json"""
import glob
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SEEDS = {'Somerset': (-93.5, 73.2), 'Baffin': (-72.0, 69.0), 'Ellesmere': (-80.0, 80.0),
         'Prince Patrick': (-119.0, 76.6), 'Ellef Ringnes': (-101.5, 78.5), 'Southampton': (-84.5, 64.3)}
land = gpd.read_file(f'{S.WORK}/land_amap.gpkg', layer='land').to_crs(S.CRS)
tiles = gpd.read_file(f'{S.WORK}/land_amap.gpkg', layer='tiles').to_crs(S.CRS)
sheets = json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']
try:
    tri = pd.read_csv(f'{S.WORK}/gscvec/triage.csv').groupby('label').usable.any().to_dict()
except FileNotFoundError:
    tri = {}
done = set(pd.read_csv(f'{S.WORK}/gscvec/summary.csv').label.str.split('_').str[0])
ostr = pd.read_csv(f'{ROOT}/sources/canada_ostr_new_in_domain.csv', dtype={'geoscan': str})
otri = pd.read_csv(f'{S.WORK}/ostrvec/triage.csv', dtype={'label': str}).groupby('label').usable.any().to_dict()
BOX = {'Somerset': (-96, 72, -89.5, 74.2), 'Baffin': (-91, 61.5, -61, 74), 'Ellesmere': (-93, 76, -60, 83.3),
       'Prince Patrick': (-124.5, 75.5, -112.5, 77.6), 'Ellef Ringnes': (-105, 77.5, -97.5, 79.6),
       'Southampton': (-89, 61.5, -79.5, 66.2)}
bins = [0, 100000, 250000, 600000, 1000000, 1e12]
names = ['<=1:100k', '1:125k-250k', '1:500k', '1:1M', '>=1:2.5M']
rep = {}
for isl, (lon, lat) in SEEDS.items():
    p = gpd.GeoSeries([shapely.Point(lon, lat)], crs=4326).to_crs(S.CRS).iloc[0]
    # land_amap 'land' is cut into 100 km tile pieces: union the pieces in a box around
    # the island, keep the part containing the seed (Baffin came out 4,581 km2 otherwise)
    lo0, la0, lo1, la1 = BOX[isl]
    bx = gpd.GeoSeries([shapely.box(lo0, la0, lo1, la1)], crs=4326).to_crs(S.CRS).iloc[0]
    u = shapely.union_all(shapely.buffer(land[land.intersects(bx)].geometry.values, 1.0))
    parts_ = [q for q in shapely.get_parts(u) if q.intersects(p)]
    if not parts_:
        print(isl, 'seed not on land'); continue
    poly = parts_[0]
    a_isl = poly.area / 1e6
    parts = []
    for tid in tiles[tiles.intersects(poly)].tile_id:
        f = f'{S.WORK}/tiles/{tid}.parquet'
        try:
            g = gpd.read_parquet(f, columns=['src_id', 'scale_den', 'hclass', 'geometry'])
        except Exception:
            continue
        g = g[g.intersects(poly)]
        g['geometry'] = shapely.intersection(g.geometry.values, poly)
        parts.append(g)
    g = pd.concat(parts, ignore_index=True)
    g['km2'] = g.area / 1e6
    g['cls'] = pd.cut(g.scale_den.astype(float), bins, labels=names)
    by_cls = g.groupby('cls', observed=True).km2.sum().round().to_dict()
    by_src = g.groupby(['src_id', 'scale_den']).km2.sum().round().sort_values(ascending=False).head(6)
    unm = float(g[g.hclass.eq('U')].km2.sum())
    # candidate maps
    pll = gpd.GeoSeries([poly], crs=S.CRS).to_crs(4326).iloc[0]
    cs = []
    for x in sheets:
        b = x.get('bbox_wgs84')
        if b and shapely.box(*b).intersects(pll):
            st = 'vector (in merge)' if x.get('vector') else ('scan DONE' if x['label'] in done else
                  ('scan colour map, TODO' if tri.get(x['label']) else ('scan line/label map' if x['label'] in tri else 'no scan')))
            cs.append(dict(src='GSC index', id=x['label'], scale=x.get('scale'), year=str(x.get('release') or '')[:4],
                           status=st, title=x['title'][:90]))
    for _, r in ostr.iterrows():
        bb = [float(v) for v in str(r.bbox).split(',')]
        if shapely.box(*bb).intersects(pll):
            st = 'colour map, TODO' if otri.get(r.geoscan) else ('line/label map' if r.geoscan in otri else 'no image')
            cs.append(dict(src='OSTR census', id=r.geoscan, scale=int(r.scale), year=str(r.year), status=st, title=r.title[:90]))
    rep[isl] = dict(km2=round(a_isl), by_class=by_cls, unmapped_km2=round(unm),
                    top_sources=[f'{s} 1:{int(d)} {int(k)} km2' for (s, d), k in by_src.items()],
                    candidates=sorted(cs, key=lambda c: (c['scale'] or 9e9)))
    print(f'\n=== {isl}: {a_isl:,.0f} km2 | finest now: {by_cls} | U {unm:,.0f}')
    print('   sources:', rep[isl]['top_sources'])
    for c in rep[isl]['candidates']:
        if (c['scale'] or 9e9) <= 500000:
            print(f"   {c['src']:11s} {c['id']:>8} 1:{c['scale']:<7} {c['year']} {c['status']:24s} {c['title']}")
json.dump(rep, open(f'{S.WORK}/island_coverage.json', 'w'), indent=1, default=str)
