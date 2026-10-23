"""Unit polygons from the VSEGEI 1:2.5M Quaternary map of Russia (Quart_2500.pdf, 2014 ed.).

1. Render the MAIN map face with anti-aliasing OFF, so every pixel carries an exact fill
   colour in the PDF's own painter's order (Z px per pt).
2. Colour -> unit index by the live text labels (69k spans): each index label votes for
   the fill colour under it. Colours that receive no votes (river strokes, hatch glyphs,
   symbols, text) are treated as overprint and filled from the nearest unit pixel; big
   unvoted pale-blue fills are water (H).
3. Majority filter, sieve, polygonise; page -> equidistant conic (lat_1 46.4, lat_2 71.8,
   lon_0 100E, Krassowsky; q2500_solve.py, 41 m RMS) -> Pulkovo-1942 lon/lat -> EPSG:6931.
4. hclass from the index genesis letters (ru_index); uppercase 'L' loess-like indices
   (Ice Complex, as on the 1:200k sheets) -> Y.
Writes work/q2500/q2500.gpkg (units) + q2500_report.json."""
import collections
import json
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pymupdf  # noqa: E402
import pyproj  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import shape  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
import rasterio.features as rf  # noqa: E402
from affine import Affine  # noqa: E402
import ru_index as RI  # noqa: E402

PDF = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/russia_hunt/Quart_2500.pdf'
OUT = '/albedo/work/user/hlantuit/arctic_surficial/work/q2500'
Z = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0          # px per pt (3 -> 294 m px)
G = json.load(open(f'{OUT}/graticule_fit_input.json'))
PJ = json.load(open(f'{OUT}/projection.json'))
FRAME, INSET = G['frame'], G['inset']

pymupdf.TOOLS.set_aa_level(0)
doc = pymupdf.open(PDF)
page = doc[0]
clip = pymupdf.Rect(*FRAME)
pix = page.get_pixmap(matrix=pymupdf.Matrix(Z, Z), clip=clip, alpha=False)
img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width, 3)
code = (img[..., 0].astype(np.uint32) << 16) | (img[..., 1].astype(np.uint32) << 8) | img[..., 2]
del img
print('rendered', pix.width, pix.height, flush=True)
H, W = code.shape
# inset box -> nodata
ix0, iy0 = int((INSET[0] - FRAME[0]) * Z), int((INSET[1] - FRAME[1]) * Z)
ix1, iy1 = int((INSET[2] - FRAME[0]) * Z), int((INSET[3] - FRAME[1]) * Z)
code[max(iy0, 0):iy1, max(ix0, 0):ix1] = 0xFFFFFF

# palette of fill colours actually painted as fills in the PDF
fillc = collections.Counter()
for d in page.get_drawings():
    f = d.get('fill')
    if f is not None:
        fillc[(int(round(f[0] * 255)) << 16) | (int(round(f[1] * 255)) << 8) | int(round(f[2] * 255))] += 1
pal = np.array(sorted(fillc), np.uint32)
print('fill colours', len(pal), flush=True)

# labels: index-like text spans inside the frame
tx = pd.read_parquet(f'{OUT}/text.parquet')
idx_re = r'^(?:[a-z]{1,5}|L[a-z]{0,4})(?:,[a-z]{1,4})*(?:[IVX]+|H|N|E|Q)'
lab = tx[tx.t.str.match(idx_re)].copy()
lab['xc'], lab['yc'] = (lab.x0 + lab.x1) / 2, (lab.y0 + lab.y1) / 2
lab = lab[(lab.xc > FRAME[0]) & (lab.xc < FRAME[2]) & (lab.yc > FRAME[1]) & (lab.yc < FRAME[3])]
lab = lab[~((lab.xc > INSET[0]) & (lab.xc < INSET[2]) & (lab.yc > INSET[1]) & (lab.yc < INSET[3]))]
print('index labels in frame', len(lab), flush=True)
votes = collections.defaultdict(collections.Counter)
where = []
palset = set(pal.tolist())
for _, r in lab.iterrows():
    # colour under the label: the most common palette colour in a ring around the text box
    x0, y0 = int((r.x0 - FRAME[0]) * Z) - 3, int((r.y0 - FRAME[1]) * Z) - 3
    x1, y1 = int((r.x1 - FRAME[0]) * Z) + 3, int((r.y1 - FRAME[1]) * Z) + 3
    if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H:
        continue
    win = code[y0:y1, x0:x1].ravel()
    win = win[np.isin(win, pal) & (win != 0xFFFFFF)]
    if len(win) == 0:
        continue
    c = collections.Counter(win.tolist()).most_common(1)[0][0]
    votes[c][r.t.strip()] += 1
    where.append(((x0 + x1) // 2, (y0 + y1) // 2, r.t.strip(), c))
unit = {}
# 1) the LEGEND: a stratigraphic correlation chart (bottom-left band) where every coloured
#    box carries its index as live text -> colour -> index directly from the map's own legend
SC = 1500 / page.rect.width
LEG = pymupdf.Rect(60 / SC, 893 / SC, 662 / SC, 1012 / SC)
spans = tx[(tx.x0 >= LEG.x0) & (tx.x1 <= LEG.x1) & (tx.y0 >= LEG.y0) & (tx.y1 <= LEG.y1)]
legend = collections.defaultdict(collections.Counter)
for d in page.get_drawings():
    f = d.get('fill')
    r = d['rect']
    if f is None or not LEG.contains(r) or r.width < 4 or r.height < 4:
        continue
    c = (int(round(f[0] * 255)) << 16) | (int(round(f[1] * 255)) << 8) | int(round(f[2] * 255))
    if c in (0xFFFFFF, 0):
        continue
    # the index text is about as wide as the chart bar: test the text CENTRE (a
    # containment test with 0.5 pt tolerance read 0 colours)
    xc, yc = (spans.x0 + spans.x1) / 2, (spans.y0 + spans.y1) / 2
    inside = spans[(xc > r.x0) & (xc < r.x1) & (yc > r.y0) & (yc < r.y1)]
    for t in inside.sort_values(['y0', 'x0']).t.str.strip():
        if re.match(idx_re, t):
            legend[c][t] += 1
for c, v in legend.items():
    unit[c] = v.most_common(1)[0][0] if len(v) == 1 or v.most_common(1)[0][1] >= 2 * v.most_common(2)[1][1] else '|'.join(k for k, _ in v.most_common(2))
print('legend colours read', len(unit), flush=True)
# 2) map labels only for colours the legend chart does not carry
for c, v in votes.items():
    if c in unit:
        continue
    top, n = v.most_common(1)[0]
    tot = sum(v.values())
    if tot >= 3 and n / tot >= 0.5:
        unit[c] = top
print('colours with a unit index', len(unit), '| label-voted colours', len(votes), flush=True)
# lake blue: #c6eafb / #c7eafb are water on land (the legend's offshore mbH shares
# #c7eafb; offshore is clipped by the land mask anyway, so both are H)
LAKE = [0xC6EAFB, 0xC7EAFB]
for c in LAKE:
    unit.pop(c, None)
# the map face and the legend chart were converted to RGB separately: map fills differ
# from their legend swatch by 1-2 units per channel (#e2ab83 vs #e3ac83). Snap every map
# colour to the nearest legend colour within 6 RGB units.
vals, cnt = np.unique(code, return_counts=True)
ucol = np.array(sorted(unit), np.int64)
urgb = np.c_[(ucol >> 16) & 255, (ucol >> 8) & 255, ucol & 255]
snapped = 0
for v, n in zip(vals.tolist(), cnt.tolist()):
    if v in unit or v in LAKE or v in (0xFFFFFF, 0):
        continue
    rgb = np.array([(v >> 16) & 255, (v >> 8) & 255, v & 255])
    dd = np.abs(urgb - rgb).max(axis=1)
    j = int(np.argmin(dd))
    if dd[j] <= 6:
        unit[v] = unit[int(ucol[j])]
        snapped += n
print(f'snapped near-legend colours: {snapped / cnt[vals != 0xFFFFFF].sum():.1%} of the face', flush=True)
# second pass for LARGE colours still unmatched: the chart and the map face differ by more
# than 6 units for some slope/eluvial units (#fab282 on the map vs #fab072 in the chart).
# Non-unit colours are named explicitly (a size rule blanked eastern Siberia).
NOT_UNIT = {0xF9E9C7: 'neighbouring countries (beige)', 0x221F1F: 'black linework', 0xD6007F: 'magenta overprint',
            0xA7AF38: 'olive rivers/graticule', 0xAFB91C: 'olive rivers/graticule', 0x3CB3DB: 'blue linework', 0x9FDBE9: 'sea tint'}


def _lab(rgb):
    import colorsys  # noqa: F401  (stdlib; Lab computed below)
    c = np.asarray(rgb, float) / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


legend_cols = np.array(sorted(c for c in legend), np.int64)
llab = _lab(np.c_[(legend_cols >> 16) & 255, (legend_cols >> 8) & 255, legend_cols & 255])
face_n = cnt[vals != 0xFFFFFF].sum()
matched2 = []
for v, n in zip(vals.tolist(), cnt.tolist()):
    if v in unit or v in LAKE or v in NOT_UNIT or v in (0xFFFFFF, 0) or n < 0.001 * face_n:
        continue
    d = np.sqrt(((llab - _lab([(v >> 16) & 255, (v >> 8) & 255, v & 255])) ** 2).sum(-1))
    j = int(np.argmin(d))
    if d[j] <= 15:
        unit[v] = unit[int(legend_cols[j])]
        matched2.append(('#%06x' % v, round(n / face_n, 4), '#%06x' % int(legend_cols[j]), unit[v], round(float(d[j]), 1)))
    else:
        matched2.append(('#%06x' % v, round(n / face_n, 4), None, 'UNMATCHED', round(float(d[j]), 1)))
print('large-colour Lab snap (map colour, face share, legend colour, index, dE):', flush=True)
for m in sorted(matched2, key=lambda x: -x[1]):
    print('   ', m, flush=True)
water = [c for c in vals.tolist() if c in LAKE]
cls_of = {c: i + 1 for i, c in enumerate(sorted(unit))}
WATER_ID = len(cls_of) + 1
lut_c = np.array(sorted(list(cls_of) + water), np.uint32)
lut_v = np.array([cls_of.get(c, WATER_ID) for c in sorted(list(cls_of) + water)], np.int32)
pos = np.searchsorted(lut_c, code)
pos = np.clip(pos, 0, len(lut_c) - 1)
cls = np.where(lut_c[pos] == code, lut_v[pos], 0).astype(np.int32)
face = code != 0xFFFFFF
# large-area colours that are neither units nor water (beige neighbouring countries,
# sea background) are NOT overprint: they stay no-data instead of being filled
vals, cnt = np.unique(code[(cls == 0) & face], return_counts=True)
big = vals[cnt > 0.004 * face.sum()]
# linework (black contacts, olive rivers, magenta/blue overprint) is DRAWN ON units: it must
# be filled from the neighbouring unit, not left as no-data (that left thin holes along
# every line = 542,000 km2 of merge 'slivers'). Only true background stays no-data.
LINEWORK = {0x221F1F, 0xD6007F, 0xA7AF38, 0xAFB91C, 0x3CB3DB}
big = np.array([v for v in big if v not in LINEWORK], dtype=vals.dtype)
face &= ~np.isin(code, big)
print('large non-unit colours set to no-data:', ['#%06x' % v for v in big], flush=True)
del code, pos
print('assigned before fill', round(float((cls > 0)[face].mean()), 3), flush=True)
# fill overprint pixels from the nearest unit pixel (within the coloured face only)
miss = (cls == 0) & face
_, (iy, ix) = ndi.distance_transform_edt(cls == 0, return_indices=True)
cls[miss] = cls[iy[miss], ix[miss]]
del iy, ix
cls[~face] = 0
cls = rf.sieve(cls, size=int(Z * Z * 4), mask=face)          # < ~4 pt2 (~3 km2) -> neighbours
# QC render: unit colours as painted, no-data white, at 1/8
from PIL import Image  # noqa: E402
inv_rgb = np.zeros((WATER_ID + 1, 3), np.uint8); inv_rgb[0] = 255
for c, i in cls_of.items():
    inv_rgb[i] = [(c >> 16) & 255, (c >> 8) & 255, c & 255]
inv_rgb[WATER_ID] = [170, 210, 240]
Image.fromarray(inv_rgb[cls[::8, ::8]]).save(f'{OUT}/q2500_class.png')
# polygonise in page pt, then page -> projection -> lon/lat -> 6931
crs = pyproj.CRS.from_proj4(PJ['proj'])
apex = np.array(G['apex'])
# similarity page->proj recomputed exactly as in q2500_solve.py
sol = __import__('q2500_solve')          # re-runs the tiny solve, gives fit()
_, s, ph, _ = sol.fit(*[float(x.split('=')[1]) for x in PJ['proj'].split() if x.startswith(('+lat_1', '+lat_2'))])
rows = []
page_tf = Affine.translation(FRAME[0], FRAME[1]) * Affine.scale(1 / Z)
for g, v in rf.shapes(cls, mask=cls > 0, transform=page_tf):
    rows.append((int(v), shape(g).simplify(0.3)))
print('raw polygons', len(rows), flush=True)
# page (x, y down) -> w = x - i y -> z = coef0 w + coef1
w = sol.page[:, 0] + 1j * sol.page[:, 1]
E, N = pyproj.Transformer.from_crs(4284, crs, always_xy=True).transform(sol.ll[:, 0], sol.ll[:, 1])
coef, *_ = np.linalg.lstsq(np.c_[w, np.ones_like(w)], E + 1j * N, rcond=None)
inv = pyproj.Transformer.from_crs(crs, 4284, always_xy=True)
to6931 = pyproj.Transformer.from_crs(4284, S.CRS, always_xy=True)


def tf(xy):
    z = coef[0] * (xy[:, 0] - 1j * xy[:, 1]) + coef[1]
    lo, la = inv.transform(z.real, z.imag)
    return np.c_[to6931.transform(lo, la)]


geoms = shapely.make_valid(shapely.transform(np.array([g for _, g in rows], dtype=object), tf))
inv_cls = {i: c for c, i in cls_of.items()}
idx = [unit[inv_cls[v]] if v in inv_cls else 'WATER' for v, _ in rows]
fillhex = ['#%06x' % inv_cls[v] if v in inv_cls else 'water' for v, _ in rows]
g = gpd.GeoDataFrame(dict(index=idx, fill=fillhex), geometry=geoms, crs=S.CRS)
g = S.polygons_only(g)
g = g.dissolve(by=['index', 'fill'], as_index=False)
g = S.polygons_only(g)


def hcl(ix):
    if ix == 'WATER':
        return 'H', '', 'water fill'
    first = ix.split('|')[0]
    if re.match(r'^L[a-z]*(?:[IVX]|H)', first):
        return 'Y', 'L', 'L-prefix loess-like unit = Ice Complex (as on the 1:200k sheets)'
    c = RI.classify_index(first)
    return (c[0], c[1], c[2]) if c else ('Q', '', 'UNKNOWN PREFIX - review')


h = g['index'].map(hcl)
g['hclass'], g['hclass2'], g['note'] = [x[0] for x in h], [x[1] for x in h], [x[2] for x in h]
g.to_file(f'{OUT}/q2500.gpkg', layer='units', driver='GPKG')
rep = dict(z_px_per_pt=Z, m_per_px=PJ['m_per_pt'] / Z, labels=len(lab), voted_colours=len(votes),
           unit_colours=len(unit), water_colours=len(water), polygons=len(g),
           km2=round(float(g.area.sum() / 1e6)), hclass_km2=g.assign(a=g.area / 1e6).groupby('hclass').a.sum().round().to_dict(),
           ambiguous_colours={('#%06x' % c): dict(v.most_common(3)) for c, v in votes.items() if c in unit and '|' in unit[c]})
json.dump(rep, open(f'{OUT}/q2500_report.json', 'w'), indent=1, ensure_ascii=False, default=str)
print(json.dumps({k: v for k, v in rep.items() if k != 'ambiguous_colours'}, ensure_ascii=False, default=str))
