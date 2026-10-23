"""Outlines of sheets NOT YET in the merge, for the coverage artifact (out/web/pending.json):
status 'downloaded' (on Albedo, awaiting processing) or 'available' (known, not downloaded).
Russia: work/ru_domain_sheets.csv (geokniga 1:200k / 1:1M Quaternary sheets in the domain;
held flag), minus sheets already ingested (ingest_russia.PDF_SHEETS). Canada: OSTR census
maps in the domain (downloaded; triage says colour map or line map) and GSC-index sheets in
the domain found nowhere else (work/ca_domain_sheets.csv, 'available').
Rings in EASE-Grid 2.0 North km, like sheets.json."""
import json
import numpy as np
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import nomen  # noqa: E402
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
src = open(f'{ROOT}/scripts/ingest_russia.py', encoding='utf-8').read()
done = set(re.findall(r"'([A-U]-[0-9A-Z,()\-]+)'", src[src.index('_G200'):src.index('PDF_SHEETS')]))
done |= {'R-52', 'Q-42'}
# 1:1M sheets merged through ingest_russia._G1M (listed as '<nomen>_g3'): the _G200 slice above
# missed them, so merged 1:1M sheets (R-54, S-44, Q-48 ...) still showed as 'downloaded'
g1m = src[src.index('_G1M'):]
g1m = g1m[:g1m.index(']') + 1]
done |= {re.sub(r'_(?:g\d|pq)$', '', s) for s in re.findall(r"'([A-U]-[0-9A-Z,()\-]+_(?:g\d|pq))'", g1m)}
# preview-derived 1:1M sheets (ingest_russia.PREVIEW_SHEETS, '<nomen>_g2pv', source ru_vsegei_preview)
if 'PREVIEW_SHEETS =' in src:
    pv = src[src.index('PREVIEW_SHEETS ='):]
    pv = pv[:pv.index('}') + 1]
    # 1:1M previews carry '_g2pv'; 1:200k previews (2026-10-04) are plain nomenclature keys
    done |= {re.sub(r'_g\dpv$', '', s) for s in re.findall(r"'([A-U]-[0-9A-Z,()\-]+(?:_g\dpv)?)'", pv)}
# 'N-49,(50)' (census) == 'N-49-50' (ingest name): drop brackets, comma -> hyphen
norm = lambda s: re.sub(r'[_ ()+;]', '', s).replace(',', '-')   # noqa: E731   ('N-56-VI;N-57-I' == 'N-56-VI_N-57-I')
done = {norm(d) for d in done}


def rings_of(g4326, tol_km=1.0):
    g = gpd.GeoSeries([shapely.segmentize(g4326, 0.25)], crs=4326).to_crs(S.CRS).iloc[0].simplify(tol_km * 1000)
    out = []
    for p in shapely.get_parts(g):
        if p.geom_type == 'Polygon':
            out.append([[round(x / 1000, 1), round(y / 1000, 1)] for x, y in p.exterior.coords])
    return out


items = []
ru = pd.read_csv(f'{S.WORK}/ru_domain_sheets.csv')
for _, r in ru.iterrows():
    code = re.sub(r'_g\d$', '', r.sheet)
    if norm(code) in done:
        continue
    try:
        b = nomen.frame(re.sub(r'[()]', '', code))
    except Exception:
        continue
    if b[2] <= b[0]:
        continue                                         # crosses 180 (Q-60,1 etc.): skipped
    items.append(dict(status='downloaded' if r.held else 'available', src='geokniga (VSEGEI)', sheet=r.sheet,
                      scale=int(r.scale), title=str(r.title), note='' if r.scale == 200000 else f"1:1M generation {int(r.get('gen') or 2)}",
                      rings=rings_of(shapely.box(*b))))
tri = pd.read_csv(f'{S.WORK}/ostrvec/triage.csv', dtype={'label': str}).groupby('label').usable.any().to_dict()
oc = pd.read_csv(f'{ROOT}/sources/canada_ostr_new_in_domain.csv', dtype={'geoscan': str})


def merged_geoscans():
    """GEOSCAN ids of OSTR items already in a merged Canadian source: every staged sheet dir
    (raw/canada/gsc*/<label>/_MANIFEST.json) whose label is a footprint sheet of ca_gsc_cgm,
    ca_gsc_legacy or ca_gsc_scans (2026-10-01: CGM233 Somerset etc. still showed as
    'downloaded, not processed'), plus the single-item sources."""
    import glob
    import os
    import pyogrio
    labels = set()
    for s in ('ca_gsc_cgm', 'ca_gsc_legacy', 'ca_gsc_scans'):
        p = f'{S.WORK}/xw/{s}.gpkg'
        if os.path.exists(p):
            labels |= {str(x).split('_')[0] for x in pyogrio.read_dataframe(p, layer='footprint', read_geometry=False)['src_sheet']}
    out = {'291820', '221968', '315667'}           # OF7038, OF5153, OF8651 (own sources)
    for m in glob.glob(f'{S.RAW}/canada/gsc*/*/_MANIFEST.json'):
        lab = os.path.basename(os.path.dirname(m)).replace('CGMx_', '')
        if lab.split('_')[0] in labels:
            try:
                out.add(str(json.load(open(m)).get('geoscan')))
            except Exception:
                pass
    return out


merged = merged_geoscans()
print('OSTR items already merged:', len(merged & set(oc.geoscan)))
oc = oc[~oc.geoscan.isin(merged)]
for _, r in oc.iterrows():
    bb = [float(v) for v in str(r.bbox).split(',')]
    kind = 'colour map' if tri.get(r.geoscan) else ('line/label map' if r.geoscan in tri else 'no map image')
    items.append(dict(status='downloaded', src='NRCan OSTR', sheet=str(r.geoscan), scale=int(r.scale), year=str(r.year),
                      title=str(r.title), note=kind, rings=rings_of(shapely.box(*bb))))
cd = pd.read_csv(f'{S.WORK}/ca_domain_sheets.csv', dtype={'geoscan': str})
miss = set(cd[~cd.inv & ~cd.downloaded].geoscan)
g = gpd.read_file(f'{S.WORK}/ca_domain_sheets.gpkg')
for _, r in g[g.geoscan.astype(str).isin(miss)].iterrows():
    items.append(dict(status='available', src='GSC index', sheet=str(r.geoscan), scale=None, title=str(r['name']),
                      note='not in inventory or census', rings=rings_of(r.geometry)))
items = [i for i in items if i['rings']]
# GAIN per item on the merged coverage grid (out/coverage_class.tif from coverage_map.py; class 1 <=1:100k, 2 1:125-250k,
# 3 1:500-600k, 4 1:1M, 5 >=1:2.5M, 6 none): land cells that are now COARSER than the item's own scale class. Items
# whose gain is < 100 km2 or < 2 % of their land are 'superseded' (2026-10-03: the 62 Keewatin/Manitoba OSTR maps west
# of Hudson Bay drew 600k km2 of footprints, but only 1.3k km2 of it is still on the fallback: newer CGMs cover it)
import rasterio
from rasterio.features import geometry_mask
try:
    with rasterio.open(f'{S.OUT}/coverage_class.tif') as cg:
        A = cg.read(1); TF = cg.transform; CELL = abs(TF.a * TF.e) / 1e6
    for it in items:
        polys = [shapely.Polygon(np.array(r) * 1000.0) for r in it['rings'] if len(r) >= 4]
        polys = [p for p in polys if p.is_valid and not p.is_empty]
        if not polys:
            continue
        m = geometry_mask(polys, out_shape=A.shape, transform=TF, invert=True)
        v = A[m]
        sc = int(it['scale'] or 0) or 250000
        k = 1 if sc <= 100000 else 2 if sc <= 250000 else 3 if sc <= 600000 else 4
        land = float(((v > 0) & (v < 7)).sum() * CELL)
        gain = float(((v > k) & (v < 7)).sum() * CELL)
        it['gain_km2'] = round(gain); it['gap_km2'] = round(float((v >= 5).sum() * CELL))
        if gain < max(100.0, 0.02 * land):
            it['status'] = 'superseded'
except FileNotFoundError:
    print('no coverage grid yet: gain not computed')
json.dump(items, open(f'{S.OUT}/web/pending.json', 'w'), separators=(',', ':'))
c = pd.DataFrame(items).groupby(['status', 'src']).size()
print(c.to_string()); print('items', len(items))
