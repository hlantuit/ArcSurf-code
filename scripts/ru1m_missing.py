"""Russian 1:1M IMW sheets in the permafrost zone that still lack a usable 1:1M Quaternary map.
For every 1:1M frame (rows K..U; 6 x 4 deg below 60 N, 12 x 4 deg 60-76 N, 24 x 4 deg above 76 N, as
nomen.frame gives), intersect with Obu 2019 permafrost (work/domain_obu_amap.gpkg 'permafrost_zones')
restricted to Russia (Natural Earth admin-0), subtract the frames of all 1:1M sheets merged or queued
(ingest_russia _G1M + R-52, Q-42) and the frames of all 1:200k sheets in _G200/_JPG200.
Reports the remaining permafrost km2 per sheet with what geokniga holds (sources/geokniga_q1000.json:
gen 2/3 pages; scratch raw/russia_geokniga_1m: preview-only vs full scan).
Writes work/ru1m_missing.csv."""
import glob
import json
import os
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from PIL import Image  # noqa: E402
import nomen  # noqa: E402
import surflib as S  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
W0 = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
src = open(f'{W0}/scripts/ingest_russia.py', encoding='utf-8').read()


def lst(name):
    i = src.index(name + ' ='); j = src.index(']', i)
    return re.findall(r"'([^']+)'", src[i:j])


def frames(code):
    """frames of '<row>-<a>[-<b>]' or 'R-58-60' / 'N-49-50' / 'Q-60-1' style multi-sheet codes"""
    code = re.sub(r'_(?:g\d|pq)$', '', code)
    m = re.match(r'([A-U])-(\d+)(?:-(\d+))?$', code)
    if not m:
        return []
    row, a = m.group(1), int(m.group(2))
    b = int(m.group(3)) if m.group(3) else a
    nums = list(range(a, b + 1)) if b >= a else list(range(a, 61)) + list(range(1, b + 1))
    out = []
    for n in nums:
        try:
            lo0, la0, lo1, la1 = nomen.frame(f'{row}-{n}')
            out.append(shapely.box(lo0, la0, lo1, la1))
        except Exception:
            pass
    return out


have1m = [f for c in lst('_G1M') + ['R-52', 'Q-42'] for f in frames(c)]
have200 = []
for s in lst('_G200') + lst('_JPG200'):
    for part in s.split('_'):
        try:
            have200.append(shapely.box(*nomen.frame(re.sub(r'[()]', '', part.split(',')[0]))))
        except Exception:
            pass
cover = shapely.union_all(have1m + have200)
pf = gpd.read_file(f'{S.WORK}/domain_obu_amap.gpkg', layer='permafrost_zones').to_crs(4326)
ne = f'{W0}/raw/naturalearth/ne_10m_admin_0_countries.shp'
ru = gpd.read_file(ne); ru = ru[ru['ADM0_A3'].eq('RUS')].union_all()
pf_ru = shapely.intersection(shapely.make_valid(pf.union_all()), ru)
zones = {z: shapely.intersection(shapely.make_valid(g), ru) for z, g in zip(pf['zone'], pf.geometry)}
cen = json.load(open(f'{W0}/sources/geokniga_q1000.json'))
man = json.load(open(f'{RAW}/russia_geokniga_1m/MANIFEST.json'))


def km2(g):
    return 0.0 if g.is_empty else float(gpd.GeoSeries([g], crs=4326).to_crs(S.CRS).area.iloc[0] / 1e6)


def held(nomcode):
    """what is on disk for this 1:1M nomenclature: list of 'label:WxH' for every raw dir that covers it"""
    out = []
    for d in glob.glob(f'{RAW}/russia_geokniga_1m/*_g[23]'):
        lab = os.path.basename(d)
        code = re.sub(r'[_()]', '', re.sub(r'_g\d$', '', lab)).replace(',', '-')
        if any(f.equals(shapely.box(*nomen.frame(nomcode))) for f in frames(code)):
            sz = ''
            j = sorted(glob.glob(f'{d}/*.jpg'), key=os.path.getsize)
            if j:
                try:
                    w, h = Image.open(j[-1]).size; sz = f'jpg {w}x{h}'
                except Exception:
                    sz = 'jpg ?'
            pdfs = glob.glob(f'{d}/*.pdf')
            out.append(f"{lab}: {sz}{' +pdf' if pdfs else ''}")
    return '; '.join(out)


rows = []
for row in 'KLMNOPQRSTU':
    for col in range(1, 61):
        try:
            b = nomen.frame(f'{row}-{col}')
        except Exception:
            continue
        box = shapely.box(*b)
        if not box.intersects(pf_ru):
            continue
        p = shapely.intersection(box, pf_ru)
        a_pf = km2(p)
        if a_pf < 2000:
            continue
        miss = shapely.difference(p, cover)
        a_miss = km2(miss)
        if a_miss < 2000:
            continue
        zs = {z: round(km2(shapely.intersection(miss, g))) for z, g in zones.items()}
        rows.append(dict(sheet=f'{row}-{col}', lon0=b[0], lat0=b[1], lon1=b[2], lat1=b[3], pf_km2=round(a_pf),
                         missing_km2=round(a_miss), **{f'z_{k}': v for k, v in zs.items()}, held=held(f'{row}-{col}')))
t = pd.DataFrame(rows).sort_values('missing_km2', ascending=False)
t.to_csv(f'{S.WORK}/ru1m_missing.csv', index=False)
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 90)
print(t.to_string(index=False))
print('sheets', len(t), 'missing km2', t.missing_km2.sum())
