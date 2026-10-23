#!/usr/bin/env python
"""
GSC Open File 7196 (Wright, Ambrose, Lemkow & Bonham-Carter, eds, 2013), Mineral and Energy Resource Assessment for
the proposed Thaidene Nene National Park Reserve, East Arm of Great Slave Lake; Digital Supplement 2: Surficial
geology (D.E. Kerr; airphoto interpretation and 520 ground observations), 1:250 000, UTM NAD83. Only this PDF map
exists: the supplement-3 GIS database holds outcrop points and till geochemistry but no unit polygons. PDF and
the compilation-area polygon were pulled out of the 3.98 GB zip with HTTP range requests (remote_zip.py).
Vector PDF: units are filled paths in the 12 legend colours (legend swatches read from the panel).
Georeference: the map face is a lon/lat graticule frame (111 45 W - 105 50 W, 61 45 N - 64 00 N, NAD83, UTM
projection): neatline ring corners -> jpg_to_polygons.corner_fit. (An ICP of the coloured outline onto the
supplement's Area_of_compilation polygon converged to 1:335 000 with a 14 km median misfit: not usable.)
The Area_of_compilation polygon is used only as an independent check of the fit.
Source -> ca_gsc_of7196. usage: ingest_of7196.py
"""
import glob
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402,F401  (load before pymupdf: libstdc++ clash)
import geopandas as gpd  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pymupdf  # noqa: E402
import shapely  # noqa: E402
from scipy.spatial import cKDTree  # noqa: E402

import surflib as S  # noqa: E402
from pdf_to_polygons import hexc, poly_from_drawing  # noqa: E402

SRC = 'ca_gsc_of7196'
D = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/ostr_new/292447'
PDF = glob.glob(f'{D}/**/Surficial Map MERA compilation.pdf', recursive=True)[0]
AOC = glob.glob(f'{D}/**/Cultural_base/Area_of_compilation.shp', recursive=True)[0]
LEGEND_BOX = (500, 230, 1660, 1400)          # legend panel, title, location maps (page pt): excluded from the map
SWATCH_X = (660, 705)
XW = {  # code: hclass, hclass2, texture, cover, legend text (abridged)
    'O': ('O', '', 'organic', 'unknown', 'Organic deposits: peat and muck up to 2 m thick; bogs, depressions, poorly '
          'drained areas, valley bottoms; may contain ice-wedge polygons'),
    'C': ('C', '', 'bouldery', 'unknown', 'Colluvial deposits: angular pebbles, cobbles to boulders, up to 10 m thick; '
          'talus from weathering and frost shattering of bedrock along escarpments'),
    'E': ('E', '', 'sand', 'unknown', 'Eolian sediments: fine to medium sand, 1 m to at least 4 m thick; active and '
          'stabilized dunes and blow-outs; derived from glaciofluvial deposits'),
    'A': ('F', '', 'mixed', 'unknown', 'Alluvial sediments: silt to gravel, 1 m to at least 3 m thick; floodplains and '
          'alluvial fans of modern streams and rivers'),
    'L': ('GL', '', 'fines', 'unknown', 'Glaciolacustrine blanket and veneer: silt and sand, 1 to 3 m thick; '
          'temporary glacier-dammed lakes during deglaciation'),
    'D': ('GL', 'GF', 'sand', 'unknown', 'Glaciolacustrine deltas: sand, gravel and cobbles, up to 5 m or more thick; '
          'temporary glacier-dammed lakes; kettles, braided paleochannels, ice-wedge polygons, beach ridges'),
    'G2': ('GF', '', 'gravel', 'unknown', 'Outwash: sand and gravel, less than 3 m to at least 20 m thick; subaqueous '
           'deposits, subaerial fans and terraces'),
    'G1': ('GF', '', 'gravel', 'unknown', 'Esker sediments: sand, gravel, cobbles and small boulders, 1 to at least 30 m '
           'thick; ridges up to 20 km long with flanking aprons'),
    'T3': ('T', '', 'diamicton', 'unknown', 'Hummocky till: diamicton, compact, 3 m to at least 5 m thick; irregular to '
           'rolling terrain, low morainal ridges'),
    'T2': ('T', '', 'diamicton', 'blanket', 'Till blanket: diamicton, moderately compact, 2 to 5 m thick; till plains '
           'and drumlinoid fields; may contain till veneer'),
    'T1': ('T', 'R', 'diamicton', 'veneer', 'Till veneer: diamicton, less than 1-2 m thick, discontinuous, rock structure '
           'visible; lag on washed bedrock; small patches of bedrock'),
    'R': ('R', '', 'unknown', 'unknown', 'Bedrock: undifferentiated sedimentary, volcanic, plutonic and metamorphic '
          'rocks; patches of till veneer and glaciofluvial sediments; shattered rock and meltwater scour'),
}

page = pymupdf.open(PDF)[0]
dr = page.get_drawings()
# 1. legend: swatch fill colour -> code, matched by vertical position to the code letters printed in the swatches
words = [w for w in page.get_text('words') if SWATCH_X[0] <= (w[0] + w[2]) / 2 <= SWATCH_X[1] and w[4] in XW]
sw = {}
for d in dr:
    r, c = d['rect'], hexc(d.get('fill'))
    if c in (None, '#ffffff') or not (SWATCH_X[0] - 20 <= r.x0 and r.x1 <= SWATCH_X[1] + 20) or not (15 < r.width < 60 and 10 < r.height < 40):
        continue                         # white: the legend panel background overlaps the swatch rows (took 'O' once)
    hit = [w[4] for w in words if r.y0 <= (w[1] + w[3]) / 2 <= r.y1]
    if len(hit) == 1:
        sw[c] = hit[0]
print('legend swatches:', sw)
assert set(sw.values()) == set(XW), f'missing swatches: {set(XW) - set(sw.values())}'
# 2. unit fills on the map, painter's order (later drawings cover earlier ones)
lb = shapely.box(*LEGEND_BOX)
recs, other = [], {}
for i, d in enumerate(dr):
    c = hexc(d.get('fill'))
    if c is None:
        continue
    r = d['rect']
    if lb.contains(shapely.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
        continue
    if c not in sw:
        other[c] = other.get(c, 0) + r.width * r.height
        continue
    g = poly_from_drawing(d)
    if g is not None and not g.is_empty and g.area > 0:
        recs.append((i, sw[c], g))
print(len(recs), 'unit fills; largest non-unit fill colours (bbox pt2):', sorted(other.items(), key=lambda kv: -kv[1])[:8])
recs.sort(key=lambda r: -r[0])
kept, done, tree, n_tree = [], [], None, 0
for i, code, g in recs:
    hits = [done[j] for j in tree.query(g, predicate='intersects')] if tree is not None else []
    hits += [h for h in done[n_tree:] if shapely.intersects(h, g)]
    if hits:
        g = shapely.difference(g, shapely.union_all(hits))
    if g.is_empty or g.area <= 1e-3:
        continue
    kept.append((code, g))
    done.append(g)
    if len(done) - n_tree >= 500:
        tree, n_tree = shapely.STRtree(done), len(done)
print(len(kept), 'unit pieces after painter order')
# 3. georeference: the map face is a lon/lat graticule frame, 111 45 W - 105 50 W, 61 45 N - 64 00 N (labels on the
#    page); neatline = the closed ring whose bbox matches the frame, corners by extreme x+y / x-y; page -> EPSG:6931
#    by jpg_to_polygons.corner_fit (projection + thin-plate spline pinned at the corners), NAD83
import jpg_to_polygons as J  # noqa: E402
from pdf_to_polygons import subpaths  # noqa: E402
LON0, LAT0, LON1, LAT1 = -111.75, 61.75, -(105 + 50 / 60), 64.0
# the frame is four separate stroked paths (dark blue, one per edge; the parallels sag ~38 pt mid-frame)
edges = []
for d in dr:
    r = d['rect']
    if d.get('fill') is None and d.get('color') and max(r.width, r.height) > 2500 and             np.allclose(d['color'], (0.153, 0.282, 0.404), atol=0.01):
        edges.append(np.array(subpaths(d['items'])[0]))
assert len(edges) == 4, f'{len(edges)} frame edges'
top = min(edges, key=lambda e: e[:, 1].mean()); bot = max(edges, key=lambda e: e[:, 1].mean())
lft = min(edges, key=lambda e: e[:, 0].mean()); rgt = max(edges, key=lambda e: e[:, 0].mean())
top, bot = top[np.argsort(top[:, 0])], bot[np.argsort(bot[:, 0])]
lft, rgt = lft[np.argsort(lft[:, 1])], rgt[np.argsort(rgt[:, 1])]
tl, tr, br, bl = top[0], top[-1], bot[-1], bot[0]
print('neatline corners (pt):', [tuple(np.round(c, 1)) for c in (tl, tr, br, bl)])


def frac(e):
    s_ = np.r_[0, np.cumsum(np.hypot(*np.diff(e, axis=0).T))]
    return s_ / s_[-1]


ties = []
for e, lat in ((top, LAT1), (bot, LAT0)):          # parallels: longitude by arc-length fraction
    f_ = frac(e)
    for q in np.linspace(0.1, 0.9, 9):
        k = int(np.argmin(abs(f_ - q)))
        ties.append((LON0 + f_[k] * (LON1 - LON0), lat, e[k, 0], e[k, 1]))
for e, lon in ((lft, LON0), (rgt, LON1)):          # meridians: latitude by length fraction (top -> bottom)
    f_ = frac(e)
    for q in np.linspace(0.1, 0.9, 9):
        k = int(np.argmin(abs(f_ - q)))
        ties.append((lon, LAT1 + f_[k] * (LAT0 - LAT1), e[k, 0], e[k, 1]))
tf, fit = J.corner_fit([tuple(tl), tuple(tr), tuple(br), tuple(bl)], LON0, LAT0, LON1, LAT1, '4269', ties=ties)
print('corner_fit', fit['projection'], 'rms', round(fit['rms_m'], 1), 'm (corners + 36 edge ties); m/pt',
      round(fit['m_per_px'], 2), '(1:250 000 = 88.19)')
best = np.r_[top, rgt, bot[::-1], lft[::-1]]
face = shapely.make_valid(shapely.Polygon(best))
# 4. polygons -> EPSG:6931, standardise
shapely.prepare(face)
geoms, codes = [], []
for c_, g_ in kept:
    g_ = shapely.intersection(g_, face)
    if g_.is_empty:
        continue
    geoms.append(shapely.transform(g_, lambda xy: np.asarray(tf(xy))))
    codes.append(c_)
g = gpd.GeoDataFrame({'code': codes}, geometry=geoms, crs=S.CRS)
g = S.in_amap(S.polygons_only(g))
g['desc'] = g['code'].map(lambda k: XW[k][4])
u, _ = S.standardise(g, src_id=SRC, code='code', desc='desc', xkey='code', scale_den=250_000, pub_year=2013,
                     conf_tier='Surficial', licence='Open Government Licence - Canada', redistribution='open')
fp = S.footprint_from_units(u, coarse=250.0)
aoc = gpd.read_file(AOC).to_crs(S.CRS)
print('check: units vs Area_of_compilation: share of unit area inside the AOC',
      round(float(shapely.intersection(shapely.union_all(u.geometry.values), aoc.geometry.iloc[0]).area / u.area.sum()), 3))
p, m = S.write_std(u, fp, SRC, dict(title='GSC OF 7196 (2013) MERA East Arm / Thaidene Nene, Supplement 2 surficial geology '
                                          '(Kerr), 1:250 000, from the vector PDF'))
pd.DataFrame([[k, *v[:4], 'unknown', f'OF 7196 unit {k}: {v[4]}'] for k, v in XW.items()],
             columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(
    f'{S.XWALK}/{SRC}.csv', index=False)
print(SRC, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes') if k in m})
print(u.assign(km2=u.area / 1e6).groupby('xkey').km2.sum().round().to_dict())
