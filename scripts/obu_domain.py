"""Long-term domain (Hugues, 2026-09-30): AMAP land  UNION  Obu et al. (2019) permafrost
(PERZONES: continuous / discontinuous / sporadic / isolated), the permafrost part limited to
the Arctic countries (RU, CA, US-Alaska, GL, NO incl. Svalbard, SE, FI, IS) - no Mongolia,
China, Central Asia.
Writes work/domain_obu_amap.gpkg (layers: permafrost_zones [clipped, dissolved by zone],
domain, beyond_amap = domain minus current AMAP merge domain) and out/web/obu.json
(simplified rings for the coverage artifact), and prints the area budget."""
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

OBU = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/obu2019/UiO_PEX_PERZONES_5.0_20181128_2000_2016_NH.shp'
NE = f'{S.RAW}/naturalearth/ne_10m_admin_0_countries.shp'
COUNTRIES = {'RUS', 'CAN', 'USA', 'GRL', 'NOR', 'SWE', 'FIN', 'ISL'}
ZN = {'Cont': 'continuous', 'Discon': 'discontinuous', 'Spor': 'sporadic', 'Spora': 'sporadic', 'Isol': 'isolated'}

z = gpd.read_file(OBU).to_crs(S.CRS)
z['zone'] = z['EXTENT'].map(ZN).fillna(z['EXTENT'])
print('Obu zones', z['zone'].value_counts().to_dict(), flush=True)
ne = gpd.read_file(NE)
key = 'ADM0_A3' if 'ADM0_A3' in ne else 'ISO_A3'
ne = ne[ne[key].isin(COUNTRIES)].to_crs(S.CRS)
# USA: Alaska only (the part north of 50N and west of 130W)
usa = ne[ne[key] == 'USA']
ak_box = gpd.GeoSeries([shapely.box(-180, 50, -129, 72)], crs=4326).to_crs(S.CRS).geometry.values[0]
parts = [g for g in ne[ne[key] != 'USA'].geometry.values] + [shapely.intersection(usa.geometry.values[0], ak_box)]
arctic = shapely.union_all([shapely.buffer(p, 0) for p in parts])
shapely.prepare(arctic)
zones = []
for name, sub in z.groupby('zone'):
    g = shapely.intersection(shapely.union_all(shapely.make_valid(sub.geometry.values)), arctic)
    zones.append(dict(zone=name, geometry=g))
    print(name, round(g.area / 1e6), 'km2', flush=True)
zones = gpd.GeoDataFrame(zones, crs=S.CRS)
# Caucasus excluded (Hugues 2026-09-30: 'we do not need the caucasus'): mountain permafrost
# south of 46N between 34E and 52E
cauc = gpd.GeoSeries([shapely.box(34, 38, 52, 46)], crs=4326).to_crs(S.CRS).iloc[0]
zones['geometry'] = shapely.difference(zones.geometry.values, cauc)
pf = shapely.union_all(zones.geometry.values)
amap = S.amap_only_geom()
domain = shapely.union_all([pf, amap])
beyond = shapely.difference(pf, amap)
out = f'{S.WORK}/domain_obu_amap.gpkg'
zones.to_file(out, layer='permafrost_zones', driver='GPKG')
gpd.GeoDataFrame(dict(name=['domain']), geometry=[domain], crs=S.CRS).to_file(out, layer='domain', driver='GPKG')
# zones diced on the merge's 100 km tile grid (tile ids as prep_land.py / merge_tiles.py),
# so merge_tiles can split every final polygon by permafrost zone reading only its tile
T = 100_000.0
dice = []
for r in zones.itertuples():
    parts = shapely.get_parts(r.geometry)
    tree = shapely.STRtree(parts)
    x0, y0, x1, y1 = r.geometry.bounds
    for x in np.arange(np.floor(x0 / T) * T, x1, T):
        for y in np.arange(np.floor(y0 / T) * T, y1, T):
            b = shapely.box(x, y, x + T, y + T)
            idx = tree.query(b, predicate='intersects')
            if len(idx):
                g = shapely.make_valid(shapely.intersection(shapely.union_all(parts[idx]), b))
                if not g.is_empty and g.area > 1.0:
                    dice.append(dict(zone=r.zone, tile_id=f'{int(x//1000):+06d}_{int(y//1000):+06d}', geometry=g))
    print('diced', r.zone, len(dice), flush=True)
gpd.GeoDataFrame(dice, crs=S.CRS).to_file(out, layer='zones_by_tile', driver='GPKG')
bz = gpd.GeoDataFrame([dict(zone=r.zone, geometry=shapely.difference(r.geometry, amap)) for r in zones.itertuples()], crs=S.CRS)
bz.to_file(out, layer='beyond_amap', driver='GPKG')
# per country budget of permafrost beyond AMAP
cb = {}
for c, g in zip(ne[key], ne.geometry.values):
    gg = shapely.intersection(beyond, g if c != 'USA' else shapely.intersection(g, ak_box))
    cb[c] = round(gg.area / 1e6)
print(json.dumps(dict(permafrost_km2=round(pf.area / 1e6), amap_km2=round(amap.area / 1e6), domain_km2=round(domain.area / 1e6),
                      permafrost_beyond_amap_km2=round(beyond.area / 1e6), beyond_by_country=cb,
                      beyond_by_zone={r.zone: round(r.geometry.area / 1e6) for r in bz.itertuples()}), indent=1))


def rings(g, tol):
    g = shapely.simplify(g, tol)
    return [np.round(np.asarray(p.exterior.coords) / 1000, 1).tolist() for p in shapely.get_parts(g)
            if p.geom_type == 'Polygon' and p.area > tol * tol * 6]


web = dict(beyond={r.zone: rings(r.geometry, 5000) for r in bz.itertuples()},
           zones_outline={r.zone: rings(r.geometry, 5000) for r in zones.itertuples()})
json.dump(web, open(f'{S.OUT}/web/obu.json', 'w'), separators=(',', ':'))
print('wrote', out, f'{S.OUT}/web/obu.json')
