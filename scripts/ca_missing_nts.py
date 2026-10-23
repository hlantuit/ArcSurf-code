"""Canadian NTS 1:250k map areas whose land (in the build domain) has only >= 1:2.5M coverage (the GSC 1:5M
'Surficial materials of Canada' backdrop), from a coverage class grid (coverage_grid.py / coverage_map.py).

NTS codes: 1:1M block = 3 digits <col><row>: col = floor((W - 48) / 8) (8-deg longitude bands from 48 W),
row = floor((N - 40) / 4). 1:250k letters, boustrophedon from the SE corner:
  south of 68 N: 1 x 2 deg sheets, A-D (row 0, east to west), E-H (west to east), I-L, M-P;
  68-80 N:       1 x 4 deg sheets, A-B (row 0, east to west), C-D (west to east), E-F, G-H;
  north of 80 N: 1 x 8 deg sheets in blocks of two columns (120, 340, 560 ...), lettered as 68-80 N
                 (approximate: checked only against the series numbers, not against sheet indexes).
Checked: 085J Yellowknife, 107C Tuktoyaktuk, 107B Aklavik/Inuvik.

Each sheet is matched against the GSC surficial catalogue (sources/canada_gsc_sheets.json: bbox + scale):
catalogued products overlapping the sheet, at <= 1:1M, with 'processed' = in a merged source footprint
(xw/ca_*.gpkg src_sheet). Output: out/ca_missing_nts_<tag>.csv and a markdown list on stdout.
usage: ca_missing_nts.py <coverage tif> <tag> [min_km2=300]"""
import glob
import json
import sys

import numpy as np
import pandas as pd
import pyproj
import rasterio

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import geopandas as gpd  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
tif, tag = sys.argv[1], sys.argv[2]
min_km2 = float(sys.argv[3]) if len(sys.argv) > 3 else 300.0
CLS = {1: '<=1:100k', 2: '1:125k-1:250k', 3: '1:500k-1:600k', 4: '1:1M', 5: '>=1:2.5M', 6: 'unmapped'}


def nts(lon, lat):
    """NTS 1:250k code and its bbox (w, s, e, n) for a point (vectorised over arrays)."""
    W = -np.asarray(lon, float)
    N = np.asarray(lat, float)
    col = np.floor((W - 48) / 8).astype(int)
    row = np.floor((N - 40) / 4).astype(int)
    r = np.floor(N - np.floor(N / 4) * 4).astype(int)            # 0..3 within the block
    out, box = [], []
    for c, rw, ri, w, n in zip(col, row, r, W, N):
        if n < 68:
            ce = int(np.floor((w - (48 + 8 * c)) / 2))             # 0 = east column
            k = [ce, 4 + (3 - ce), 8 + ce, 12 + (3 - ce)][ri]
            blk = f'{c:02d}{rw}'
            we = 48 + 8 * c + 2 * ce
            out.append(f'{int(blk):03d}{"ABCDEFGHIJKLMNOP"[k]}')
            box.append((-(we + 2), np.floor(n), -we, np.floor(n) + 1))
        elif n < 80:
            ce = int(np.floor((w - (48 + 8 * c)) / 4))
            k = [ce, 2 + (1 - ce), 4 + ce, 6 + (1 - ce)][ri]
            we = 48 + 8 * c + 4 * ce
            out.append(f'{int(f"{c:02d}{rw}"):03d}{"ABCDEFGH"[k]}')
            box.append((-(we + 4), np.floor(n), -we, np.floor(n) + 1))
        else:
            c1 = 2 * int(np.floor((c - 1) / 2)) + 1
            ce = int(np.floor((w - (48 + 8 * c1)) / 8))
            k = [ce, 2 + (1 - ce), 4 + ce, 6 + (1 - ce)][ri]
            we = 48 + 8 * c1 + 8 * ce
            out.append(f'{c1}{c1 + 1}0{"ABCDEFGH"[k]}~')
            box.append((-(we + 8), np.floor(n), -we, np.floor(n) + 1))
    return out, box


assert nts([-114.4], [62.45])[0] == ['085J'] and nts([-133.0], [69.4])[0] == ['107C'] and nts([-133.7], [68.36])[0] == ['107B']

with rasterio.open(tif) as rr:
    g = rr.read(1); tf = rr.transform
    if rr.count > 1:                       # band 2 = water (coverage_grid.py): lakes are not missing land
        g = np.where(rr.read(2) == 1, 0, g)
cell = abs(tf.a * tf.e) / 1e6
rows, cols = np.nonzero(g > 0)
x = tf.c + (cols + 0.5) * tf.a; y = tf.f + (rows + 0.5) * tf.e
lon, lat = pyproj.Transformer.from_crs(S.CRS, 4326, always_xy=True).transform(x, y)
c = g[rows, cols]
sel = (lon > -142) & (lon < -52) & (lat > 41.5)                      # Canada's box; then the country test
lon, lat, c = lon[sel], lat[sel], c[sel]
ne = gpd.read_file(f'{S.RAW}/naturalearth/ne_10m_admin_0_countries.shp')
can = ne[ne['ADMIN'] == 'Canada'].geometry.union_all()
import shapely  # noqa: E402
shapely.prepare(can)
inside = shapely.contains_xy(can, lon, lat)
lon, lat, c = lon[inside], lat[inside], c[inside]
codes, boxes = nts(lon, lat)
df = pd.DataFrame(dict(nts=codes, cls=[CLS[k] for k in c]))
bx = dict(zip(codes, boxes))
t = df.groupby(['nts', 'cls']).size().unstack(fill_value=0) * cell
for v in CLS.values():
    if v not in t:
        t[v] = 0.0
t['land_km2'] = t[list(CLS.values())].sum(1)
t['coarse_km2'] = t['>=1:2.5M']
t['coarse_share'] = t['coarse_km2'] / t['land_km2']
t['best_other'] = t[['<=1:100k', '1:125k-1:250k', '1:500k-1:600k', '1:1M']].idxmax(axis=1).where(
    t[['<=1:100k', '1:125k-1:250k', '1:500k-1:600k', '1:1M']].sum(1) > 0, '')
miss = t[t.coarse_km2 >= min_km2].copy()
miss['bbox'] = [bx[k] for k in miss.index]

# catalogue
cat = json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']
done = set()
for f in glob.glob(f'{S.WORK}/xw/ca_*.gpkg'):
    try:
        fp = gpd.read_file(f, layer='footprint', ignore_geometry=True)
        done |= set(fp['src_sheet'].astype(str).str.split('_').str[0])
    except Exception:
        pass
cols_out, unit_out = [], []
for k, r in miss.iterrows():
    w, s, e, n = r.bbox
    hits, units = [], []
    for sh in cat:
        b = sh.get('bbox_wgs84')
        sc = sh.get('scale') or 10**9
        if not b or sc > 1_000_000:
            continue
        if sh.get('nts_sheets'):
            # inspected products whose sheets are known (OF 132 = 096D, 106G, 106H): the catalogue bbox is the union of
            # several map sheets and over-claimed 100k km2 of gap
            if k not in sh['nts_sheets']:
                continue
        else:
            ix = max(0, min(e, b[2]) - max(w, b[0])) * max(0, min(n, b[3]) - max(s, b[1]))
            if ix <= 0.05 * (e - w) * (n - s):                     # > 5 % of the sheet's lon-lat box
                continue
        kind = 'vector' if sh.get('vector') else ('scan' if sh.get('ostr_filetypes') else 'other')
        if sh.get('not_a_unit_map'):          # feature/symbol maps (eskers, striae): listed, but not a product
            hits.append(f"{sh['label']} 1:{int(sc / 1000)}k feature map, no units")
            continue
        if sh.get('no_gap_units'):            # processed and measured: its units do not reach this gap (OF 189)
            hits.append(f"{sh['label']} 1:{int(sc / 1000)}k checked, units not on the gap")
            continue
        h = f"{sh['label']} 1:{int(sc / 1000)}k {kind}{' (processed)' if sh['label'] in done else ''}"
        hits.append(h)
        units.append(h)
    cols_out.append('; '.join(hits))
    unit_out.append('; '.join(units))
miss['gsc_catalogue'] = cols_out
units_s = pd.Series(unit_out, index=miss.index)
miss['status'] = np.where(units_s.eq(''), 'NO catalogued surficial product <= 1:1M',
                          np.where(units_s.str.contains(r'k (?:vector|scan|other)(?:;|$)'),
                                   'catalogued, not yet processed', 'catalogued, processed (not used here)'))
miss = miss.sort_values('coarse_km2', ascending=False)
out = miss[['land_km2', 'coarse_km2', 'coarse_share', 'best_other', 'status', 'gsc_catalogue']].copy()
out.insert(0, 'bbox', [f'{abs(b[2]):g}-{abs(b[0]):g}W {b[1]:g}-{b[3]:g}N' for b in miss.bbox])
out.round(3).to_csv(f'{S.OUT}/ca_missing_nts_{tag}.csv')
print(f'Canada land in domain: {t.land_km2.sum() / 1e6:.2f} M km2; at >= 1:2.5M: {t.coarse_km2.sum() / 1e3:.0f}k km2 '
      f'in {int((t.coarse_km2 > 0).sum())} NTS sheets; listed (>= {min_km2:g} km2): {len(miss)} sheets, '
      f'{miss.coarse_km2.sum() / 1e3:.0f}k km2')
print(out.groupby('status').agg(n=('coarse_km2', 'size'), km2=('coarse_km2', 'sum')).round(-2).to_string())
