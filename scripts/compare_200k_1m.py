#!/usr/bin/env python
"""Side-by-side view of a 1:200k sheet and the 1:1M sheet over the SAME frame, for PI decisions where the two maps
disagree (2026-10-06: P-39-X and P-39-XII vs P-39_g3).
  top row    the printed maps: the 1:200k (its vector PDF rendered, or the geokniga preview JPG) and the 1:1M vector PDF
             cropped to the 1:200k frame (red outline). PDF crops use the page->map affine dumped by
             work/cmp_p39/pdf_fit_dump.py (FIT_DUMP=...; inverse affine, residual 10-30 m)
  bottom row our hclass coding of both extractions (sources/legend_<sheet>.csv; largest polygons labelled with the map's
             own unit index) and their primary-hclass agreement on a 100 m grid
Writes work/cmp_p39/<sheet>_vs_<1m>.png, the full-resolution printed crops <sheet>_printed_200k.png / _printed_1m.png
and <sheet>_vs_<1m>_units.csv (units in the frame: km2, share, hclass, description).
usage: compare_200k_1m.py <sheet200> <sheet1m> <pdf1m> <fit1m.json> (--pdf <pdf200> <fit200.json> | --preview <jpg> <jpgvec.json>)"""
import json
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')   # pymupdf
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402  (first: PROJ fix)
import nomen  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pymupdf  # noqa: E402
import pyproj  # noqa: E402
import rasterio.features  # noqa: E402
import shapely  # noqa: E402
from affine import Affine  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
OUT = f'{ROOT}/work/cmp_p39'
PAL = {'T': '#c9a36b', 'GF': '#f2a7c6', 'GL': '#9fc5e8', 'GM': '#7fb3a3', 'M': '#4f9fd1', 'F': '#f6e27a',
       'L': '#7ec8e3', 'K': '#b8e0d2', 'Y': '#8e7cc3', 'E': '#f9cb9c', 'C': '#c27c4e', 'W': '#e0c09a',
       'O': '#6aa84f', 'V': '#cc4125', 'X': '#999999', 'I': '#ffffff', 'Q': '#d9d2b9', 'H': '#3d85c6',
       'R': '#a64d79', 'U': '#eeeeee'}
UTM = 32600 + int((nomen.frame(sys.argv[1])[0] + 180) // 6) + 1       # local UTM zone of the 1:200k sheet

a = sys.argv[1:]
s200, s1m, pdf1m, fit1m = a[:4]
mode = a[4]
frame = nomen.frame(s200)                                         # lon0, lat0, lon1, lat1 (Pulkovo-1942)
ring = shapely.segmentize(shapely.box(*frame), 0.01)
flon, flat = np.array(ring.exterior.coords).T


def pdf_crop(pdf, fit, dpi, margin_pt):
    """frame -> page via the inverse page->projected affine; render the bbox (+margin); return image + frame in px"""
    F = json.load(open(fit))
    fwd = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4284), pyproj.CRS.from_proj4(F['crs']), always_xy=True)
    E, N = fwd.transform(flon, flat)
    M = np.array([[F['cx'][0], F['cx'][1]], [F['cy'][0], F['cy'][1]]])
    uv = np.linalg.solve(M, np.vstack([E - F['cx'][2], N - F['cy'][2]])).T
    # the fit is in ROTATED page coordinates when the map is drawn sideways (pdf_to_polygons --rot: 90 (x,y)->(-y,x),
    # 270 (x,y)->(y,-x), 180 (x,y)->(-x,-y)): back to page coordinates for the clip
    rot = F.get('rot', 0)
    u, v = uv[:, 0], uv[:, 1]
    xy = {0: np.c_[u, v], 90: np.c_[v, -u], 270: np.c_[-v, u], 180: np.c_[-u, -v]}[rot]
    doc = pymupdf.open(pdf)
    page = doc[0]
    if page.rotation:
        # drawings are in UNROTATED page space, the renderer draws the page as displayed (/Rotate applied, i.e. the
        # sideways content comes out upright): clip in displayed coordinates, no extra turn of the image
        m = page.rotation_matrix
        xy = np.array([[(pymupdf.Point(x, y) * m).x, (pymupdf.Point(x, y) * m).y] for x, y in xy])
        rot = 0
    x0, y0 = xy.min(0) - margin_pt
    x1, y1 = xy.max(0) + margin_pt
    clip = pymupdf.Rect(x0, y0, x1, y1)
    pix = page.get_pixmap(clip=clip, dpi=dpi)
    im = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    px = (xy - [x0, y0]) * (dpi / 72)
    # content drawn sideways on an UNROTATED page: turn the crop like the points (90: right -> down = clockwise)
    if rot == 90:
        px = np.c_[im.height - 1 - px[:, 1], px[:, 0]]; im = im.transpose(Image.ROTATE_270)
    elif rot == 270:
        px = np.c_[px[:, 1], im.width - 1 - px[:, 0]]; im = im.transpose(Image.ROTATE_90)
    elif rot == 180:
        px = np.c_[im.width - 1 - px[:, 0], im.height - 1 - px[:, 1]]; im = im.transpose(Image.ROTATE_180)
    return im, px, F


def preview_crop(jpg, js, margin_px):
    J = json.load(open(js))
    c = np.array([q['snapped'] for q in J['corners']], float)    # tl, tr, br, bl in image pixels
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(jpg).convert('RGB')
    x0, y0 = np.maximum(c.min(0) - margin_px, 0)
    x1, y1 = np.minimum(c.max(0) + margin_px, im.size)
    return im.crop((int(x0), int(y0), int(x1), int(y1))), np.r_[c, c[:1]] - [int(x0), int(y0)]


def outline(im, px, width):
    d = ImageDraw.Draw(im)
    d.line([tuple(p) for p in px], fill=(230, 0, 0), width=width)
    return im


im1m, px1m, F1 = pdf_crop(pdf1m, fit1m, 400, 14)
outline(im1m, px1m, 3).save(f'{OUT}/{s200}_printed_1m.png')
if mode == '--pdf':
    im200, px200, F2 = pdf_crop(a[5], a[6], 150, 20)
    outline(im200, px200, 3).save(f'{OUT}/{s200}_printed_200k.png')
else:
    im200, px200 = preview_crop(a[5], a[6], 25)
    outline(im200, px200, 2).save(f'{OUT}/{s200}_printed_200k.png')


def coded(sheet, gpkg, clip):
    g = gpd.read_file(gpkg, layer='units')
    L = pd.read_csv(f'{ROOT}/sources/legend_{sheet}.csv', dtype=str, keep_default_na=False)
    first = g['index'].str.split('|').str[0]
    lk = L.drop_duplicates('index').set_index('index')
    g['hclass'] = first.map(lk['hclass']).fillna('')
    g['hclass2'] = first.map(lk['hclass2']).fillna('')
    g.loc[g['index'] == 'WATER', 'hclass'] = 'H'
    g['desc'] = first.map(lk['description_ru']).fillna('')
    g = gpd.clip(g, clip) if clip is not None else g
    return g.to_crs(UTM)


g200f = next(f for f in (f'{ROOT}/work/pdfvec/{s200}.gpkg', f'{ROOT}/work/jpgvec/{s200}.gpkg')
             if os.path.exists(f))
nl = gpd.read_file(g200f, layer='neatline')
u200 = coded(s200, g200f, None)
u1m = coded(s1m, f'{ROOT}/work/pdfvec1m/{s1m}.gpkg', nl.to_crs(S.CRS).geometry.values[0])
nlu = nl.to_crs(UTM)

# agreement on a 100 m grid
xmin, ymin, xmax, ymax = nlu.total_bounds
W, H = int((xmax - xmin) // 100) + 1, int((ymax - ymin) // 100) + 1
tr = Affine(100, 0, xmin, 0, -100, ymax)
codes = {c: i + 1 for i, c in enumerate(PAL)}


def rast(u):
    shapes = [(geom, codes.get(h, codes['U'])) for geom, h in zip(u.geometry, u.hclass) if geom is not None and not geom.is_empty]
    return rasterio.features.rasterize(shapes, out_shape=(H, W), transform=tr, fill=0, dtype='uint8')


r200, r1m = rast(u200), rast(u1m)
inside = rasterio.features.rasterize([(nlu.geometry.values[0], 1)], out_shape=(H, W), transform=tr, fill=0, dtype='uint8') == 1
both = inside & (r200 > 0) & (r1m > 0) & (r200 != codes['H']) & (r1m != codes['H'])
agree = float((r200[both] == r1m[both]).mean()) if both.any() else float('nan')
inv = {v: k for k, v in codes.items()}
pairs = pd.Series([f'{inv[x]} -> {inv[y]}' for x, y in zip(r200[both], r1m[both])]).value_counts(normalize=True).head(8)

# units table
rows = []
for name, u in (('1:200k ' + s200, u200), ('1:1M ' + s1m, u1m)):
    t = u.assign(km2=u.area / 1e6).groupby(['index', 'hclass', 'hclass2', 'desc'], as_index=False).km2.sum()
    t['share'] = t.km2 / t.km2.sum()
    t.insert(0, 'map', name)
    rows.append(t.sort_values('km2', ascending=False))
T = pd.concat(rows)
T.to_csv(f'{OUT}/{s200}_vs_{s1m}_units.csv', index=False)

# figure
fig = plt.figure(figsize=(20, 19), dpi=110)
gs = fig.add_gridspec(2, 6, height_ratios=[1.15, 1])
ax = fig.add_subplot(gs[0, 0:3]); ax.imshow(im200); ax.set_axis_off()
ax.set_title(f'{s200} 1:200 000 as printed' + (' (geokniga preview)' if mode != '--pdf' else ''), fontsize=13)
ax = fig.add_subplot(gs[0, 3:6]); ax.imshow(im1m); ax.set_axis_off()
ax.set_title(f'{s1m} 1:1 000 000 as printed, same frame (red)', fontsize=13)
for j, (u, ttl) in enumerate(((u200, f'{s200}: our hclass coding'), (u1m, f'{s1m}: our hclass coding'))):
    ax = fig.add_subplot(gs[1, 2 * j:2 * j + 2])
    u.plot(ax=ax, color=[PAL.get(h, '#000000') for h in u.hclass], edgecolor='#555555', linewidth=0.2)
    nlu.boundary.plot(ax=ax, color='red', linewidth=1)
    big = u.explode(index_parts=False)
    big = big[big.area > 25e6]                                      # label parts > 25 km2 with the map's own index
    for geom, idx in zip(big.geometry, big['index']):
        p = geom.representative_point()
        ax.annotate(idx.split('|')[0], (p.x, p.y), fontsize=6.5, ha='center', va='center')
    ax.set_title(ttl, fontsize=12); ax.set_axis_off(); ax.set_aspect('equal')
ax = fig.add_subplot(gs[1, 4:6])
img = np.full((H, W, 3), 255, np.uint8)
img[both & (r200 == r1m)] = (120, 190, 120)
img[both & (r200 != r1m)] = (220, 110, 110)
ax.imshow(img, extent=(xmin, xmin + W * 100, ymax - H * 100, ymax))
nlu.boundary.plot(ax=ax, color='black', linewidth=0.8)
ax.set_title(f'primary hclass: same (green) {agree:.0%} / different (red)', fontsize=12); ax.set_axis_off()
txt = '200k -> 1M (share of frame):\n' + '\n'.join(f'{k}  {v:.0%}' for k, v in pairs.items())
ax.text(0.02, -0.02, txt, transform=ax.transAxes, va='top', fontsize=9, family='monospace')
present = sorted(set(u200.hclass) | set(u1m.hclass))
fig.legend([Patch(facecolor=PAL.get(h, '#000'), edgecolor='#555') for h in present],
           [f'{h} {S.HCLASS.get(h, "")}' for h in present], loc='lower center', ncol=min(len(present), 6), fontsize=10)
fig.tight_layout(rect=(0, 0.04, 1, 1))
fig.savefig(f'{OUT}/{s200}_vs_{s1m}.png')
print(s200, 'agreement', round(agree, 3), '| top transitions', pairs.round(3).to_dict())
print(T.groupby('map').head(8).to_string(index=False, max_colwidth=70))
