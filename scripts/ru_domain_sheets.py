"""Russian sheets for the permafrost domain (AMAP land UNION Obu 2019): which geokniga
Quaternary sheets (1:200k census sources/geokniga_q200_all.json, 1:1M census
sources/geokniga_q1000.json) intersect the Russian part of the domain, how much domain
land each covers, and whether we already hold it. Frames from nomen.frame.
Writes work/ru_domain_sheets.csv and prints totals by row and scale."""
import json
import os
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import nomen  # noqa: E402
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
dom = gpd.read_file(f'{S.WORK}/domain_obu_amap.gpkg').to_crs(4326)
cols = [c for c in dom.columns if c.lower() in ('country', 'iso', 'cntry', 'adm0')]
print('domain columns', list(dom.columns)[:10])
if cols:
    dom = dom[dom[cols[0]].astype(str).str.upper().str.contains('RU')]
ru = shapely.make_valid(shapely.union_all(dom.geometry.values))
ru = shapely.intersection(ru, shapely.box(19, 40, 180, 90))           # Russia east of Kaliningrad; W of 180
ru = shapely.union_all([ru, shapely.intersection(shapely.make_valid(shapely.union_all(dom.geometry.values)),
                                                  shapely.box(-180, 60, -168, 72))])   # Chukotka E of 180
held200 = {re.sub(r'[_ ]', '', d) for d in os.listdir(f'{RAW}/russia_geokniga')}
held1m = {d for d in os.listdir(f'{RAW}/russia_geokniga_1m')} if os.path.exists(f'{RAW}/russia_geokniga_1m') else set()
to6931 = lambda g: gpd.GeoSeries([g], crs=4326).to_crs(S.CRS).iloc[0]   # noqa: E731
rows = []
q200 = json.load(open(f'{ROOT}/sources/geokniga_q200_all.json', encoding='utf-8'))
for x in q200:
    t = x['title'].lower()
    if 'четвертич' not in t or 'дочетвертич' in t:
        continue
    for nom in re.split(r'[;]\s*', x['nom']):
        try:
            b = nomen.frame(nom.strip())
        except Exception:
            continue
        box = shapely.box(*b)
        if not box.intersects(ru):
            continue
        a = to6931(shapely.intersection(box, ru)).area / 1e6
        rows.append(dict(scale=200000, sheet=nom.strip(), row=nom.strip()[0], km2=round(a), title=x['title'][:100],
                         held=re.sub(r'[_ ]', '', nom.strip()) in held200 or re.sub(r'[_ ]', '', x['nom']) in held200))
for x in json.load(open(f'{ROOT}/sources/geokniga_q1000.json', encoding='utf-8')):
    try:
        b = nomen.frame(f"{x['row']}-{min(x['cols'])}-{max(x['cols'])}" if len(x['cols']) > 1 and max(x['cols']) - min(x['cols']) < 6
                        else f"{x['row']}-{x['cols'][0]}")
    except Exception:
        continue
    box = shapely.box(*b)
    if not box.intersects(ru):
        continue
    a = to6931(shapely.intersection(box, ru)).area / 1e6
    lab = re.sub(r'[^A-Za-z0-9,()\-]', '', x['title'].split(' ')[0]) + f"_g{x['gen']}"
    rows.append(dict(scale=1000000, sheet=lab, row=x['row'], km2=round(a), title=x['title'][:100], held=lab in held1m, gen=x['gen']))
t = pd.DataFrame(rows).drop_duplicates(['scale', 'sheet'])
t.to_csv(f'{S.WORK}/ru_domain_sheets.csv', index=False)
ru_km2 = to6931(ru).area / 1e6
print(f'Russian domain {ru_km2/1e6:.2f} M km2')
for sc, g in t.groupby('scale'):
    print(f'1:{sc}: sheets {len(g)}, held {int(g.held.sum())}, not held {int((~g.held).sum())};',
          'by row (n, not held):', {r: (len(h), int((~h.held).sum())) for r, h in g.groupby('row')})
