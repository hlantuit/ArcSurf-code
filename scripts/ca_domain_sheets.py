"""GSC surficial-index sheets (raw/canada gsc_surficial_geology.gdb, all Canada) that
intersect the permafrost domain OUTSIDE AMAP (domain_obu_amap.gpkg minus the AMAP polygon),
i.e. what the 650-sheet Arctic inventory left out. Prints the layers/fields found, then
counts by scale and the domain area each scale class covers; writes
work/ca_domain_sheets.csv (all index attributes + km2 of outside-AMAP domain covered)."""
import glob
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402

RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada'
gdb = f'/vsizip/{RAW}/gsc_surficial_geology.gdb.zip'
inner = [l for l in __import__('zipfile').ZipFile(f'{RAW}/gsc_surficial_geology.gdb.zip').namelist() if l.endswith('.gdb/')]
if inner:
    gdb += '/' + inner[0].rstrip('/')
print(gdb)
lays = pyogrio.list_layers(gdb)
print(lays)
dom = gpd.read_file(f'{S.WORK}/domain_obu_amap.gpkg').to_crs(S.CRS)
out_amap = shapely.difference(shapely.make_valid(dom.union_all()), S.amap_geom())
can = shapely.intersection(out_amap, gpd.GeoSeries([shapely.box(-141, 41, -52, 70)], crs=4326).to_crs(S.CRS).iloc[0])
print('Canadian domain outside AMAP km2', round(can.area / 1e6))
best = None
for name, typ in lays:
    if 'olygon' not in str(typ):
        continue
    g = gpd.read_file(gdb, layer=name)
    print('layer', name, len(g), list(g.columns)[:25])
    if best is None or len(g) > len(best[1]):
        best = (name, g)
name, g = 'index', gpd.read_file(gdb, layer='index')       # sheet footprints (1060), not the 1:5M units
g = g.to_crs(S.CRS)
g['geometry'] = shapely.make_valid(g.geometry.values)
can = shapely.make_valid(can)
g = g[g.intersects(can)].copy()
g['km2_dom'] = [shapely.intersection(x, can).area / 1e6 for x in g.geometry.values]
g = g[g.km2_dom > 1]
import re
g['scale'] = [int(re.sub(r'\D', '', m.group(1))) if (m := re.search(r'1\s*:\s*([\d ,]+)', str(a) + ' ' + str(b))) else None
              for a, b in zip(g.label_en, g.name)]
sc = 'scale'
print('using layer', name, '| sheets touching the Canadian domain outside AMAP:', len(g), '| scale field', sc)
if sc:
    print(g.groupby(sc).km2_dom.agg(['count', 'sum']).round(0).sort_values('sum', ascending=False).head(20).to_string())
pd.DataFrame(g.drop(columns='geometry')).to_csv(f'{S.WORK}/ca_domain_sheets.csv', index=False)
g.to_crs(4326)[['geoscan', 'name', 'scale', 'release_date_diffusion', 'km2_dom', 'geometry']].to_file(f'{S.WORK}/ca_domain_sheets.gpkg')
print(g[['geoscan', 'name', 'label_en']].head(5).to_string())
