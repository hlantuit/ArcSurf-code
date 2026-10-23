#!/usr/bin/env python
"""Figure 4 of the data paper: from a printed sheet to polygons, on the scanned 1:1,000,000 sheet R-(35)-37 Murmansk
(new series, 2000). House style of essd_draw.py (Tw Cen MT, no frames, bold lower-case panel letters).

  (a) the scan with the four measured frame corners and their residuals, the straight chord between the southern
      corners and the 68 N parallel of the fitted projection, which sags 202 px (17 km) below it at the central
      meridian (inset)
  (b) the colour classification of the map face (jpg_to_polygons.py writes it at 1/6 resolution)
  (c) the sheet in ArcSurf: its pieces on land, coded by the transcribed legend (fill = legend swatch); land taken by
      finer sources in grey
  (d) a detail at full resolution: the scan with the boundaries of the extracted polygons

Inputs (from Albedo: work/facefix, the geokniga raw scan, essd/sheet_in_map.py on final_m44): R-35-37_scan.jpg,
R-35-37_g2.json (corners, residuals), R-35-37_g2_class.png, R-35-37_g2.gpkg (units, neatline),
fig4_R-35-37_in_map.gpkg, legend_R-35-37_g2.csv.
usage: fig4_sheet_example.py INDIR OUTDIR"""
import json
import os
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from PIL import Image
from pyproj import Transformer
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402

IN, OUT = sys.argv[1:3]
Image.MAX_IMAGE_PIXELS = None
for f in ('TCM_____.TTF', 'TCB_____.TTF', 'TCMI____.TTF', 'TCBI____.TTF'):          # Tw Cen MT, as essd_draw.py
    p = os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts', f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
FONT = 'Tw Cen MT' if any(f.name == 'Tw Cen MT' for f in font_manager.fontManager.ttflist) else 'DejaVu Sans'
INK, SOFT, BRICK, HAIR, OTHER, SEA = '#262626', '#6e6a64', '#b4513a', '#1d1d1b', '#d9d6d0', '#dde6ea'
plt.rcParams.update({'font.family': FONT, 'font.size': 8.0, 'text.color': INK, 'pdf.fonttype': 42,
                     'savefig.facecolor': 'white'})
MM = 1 / 25.4
W_MM = 170.0
CASE = [pe.Stroke(linewidth=2.4, foreground='white'), pe.Normal()]

R = json.load(open(f'{IN}/R-35-37_g2.json'))
corners = np.array([c['snapped'] for c in R['corners']], float)        # TL, TR, BR, BL (px of the full scan)
cres = R['corner_residuals_m']
mpp = R['m_per_px']
PROJ = '+proj=eqdc +lat_1=47 +lat_2=62 +lon_0=34.5 +ellps=krass +units=m +no_defs'
LON0, LAT0, LON1, LAT1 = 27.0, 68.0, 42.0, 72.0
ll = np.array([(LON0, LAT1), (LON1, LAT1), (LON1, LAT0), (LON0, LAT0)])
to_p = Transformer.from_crs('EPSG:4284', PROJ, always_xy=True)
E, N = to_p.transform(ll[:, 0], ll[:, 1])
A = np.c_[E, N, np.ones(4)]
cx = np.linalg.lstsq(A, corners[:, 0], rcond=None)[0]                  # projection -> scan pixels, affine
cy = np.linalg.lstsq(A, corners[:, 1], rcond=None)[0]
AFF = [cx[0], cx[1], cy[0], cy[1], cx[2], cy[2]]


def ll2px(lon, lat):
    e, n = to_p.transform(np.asarray(lon, float), np.asarray(lat, float))
    m = np.c_[e, n, np.ones(len(np.atleast_1d(e)))]
    return m @ cx, m @ cy


def to_px(g):
    """EPSG:6931 polygons -> the sheet's projection -> scan pixels (affine of the corner fit)"""
    g = g.to_crs(PROJ)
    g['geometry'] = g.geometry.affine_transform(AFF)
    return g


scan = Image.open(f'{IN}/R-35-37_scan.jpg').convert('RGB')
W, H = scan.size
small = np.asarray(scan.resize((W // 5, H // 5), Image.LANCZOS))
x0, y0 = corners[:, 0].min() - 120, corners[:, 1].min() - 120          # map-face window of the scan
x1, y1 = corners[:, 0].max() + 120, corners[:, 1].max() + 330

# layout in mm: two rows of two panels, a line key under (a)
GAP, TOP, KEY, BOT = 4.0, 6.0, 10.0, 6.0
PW = (W_MM - 3 * GAP) / 2
PH = PW * (y1 - y0) / (x1 - x0)
H_MM = TOP + PH + KEY + PH + BOT
fig = plt.figure(figsize=(W_MM * MM, H_MM * MM))


def rect(col, row):
    x = GAP + col * (PW + GAP)
    y = BOT + (0 if row else PH + KEY)
    return [x / W_MM, y / H_MM, PW / W_MM, PH / H_MM]


def axes(k, col, row):
    r = rect(col, row)
    ax = fig.add_axes(r)
    ax.set_axis_off()
    fig.text(r[0] - 2.8 / W_MM, r[1] + r[3] + 0.8 / H_MM, k, fontsize=12, fontweight='bold', va='bottom', ha='left')
    return ax


# (a) scan, corners, chord and parallel
ax = axes('a', 0, 0)
ax.imshow(small, extent=(0, W, H, 0), interpolation='lanczos')
ax.set_xlim(x0, x1)
ax.set_ylim(y1, y0)
lon = np.linspace(LON0, LON1, 300)
px, py = ll2px(lon, np.full(300, LAT0))
ax.plot(px, py, color=HAIR, lw=0.8, path_effects=CASE)
ax.plot(corners[[3, 2], 0], corners[[3, 2], 1], color=BRICK, lw=0.9, ls=(0, (4, 2)), path_effects=CASE)
for (x, y), r in zip(corners, cres):
    ax.plot(x, y, 'o', ms=3.4, mfc='white', mec=HAIR, mew=0.7)
    ax.annotate(f'{r:.0f} m', (x, y), xytext=(4, 4 if y < 3000 else -10), textcoords='offset points', fontsize=6.5,
                bbox=dict(boxstyle='square,pad=0.15', fc='white', ec='none', alpha=0.85))
xm, ym = ll2px([34.5], [LAT0])
xm, ym = float(xm[0]), float(ym[0])
ych = float(np.interp(xm, corners[[3, 2], 0], corners[[3, 2], 1]))
iw, ih = 1000, 420                                                     # inset window (scan px), over the sea
ra = rect(0, 0)
iwm = 0.42 * PW
ins = fig.add_axes([ra[0] + 0.555 * ra[2], ra[1] + ra[3] - (iwm * ih / iw + 0.06 * PH) / H_MM, iwm / W_MM,
                    iwm * ih / iw / H_MM])
crop = np.asarray(scan.crop((int(xm - iw / 2), int(ych - 120), int(xm + iw / 2), int(ych - 120 + ih))))
ins.imshow(crop, extent=(xm - iw / 2, xm + iw / 2, ych - 120 + ih, ych - 120))
ins.plot(px, py, color=HAIR, lw=0.9, path_effects=CASE)
ins.plot(corners[[3, 2], 0], corners[[3, 2], 1], color=BRICK, lw=1.0, ls=(0, (4, 2)), path_effects=CASE)
ins.set_xlim(xm - iw / 2, xm + iw / 2)
ins.set_ylim(ych - 120 + ih, ych - 120)
ins.annotate('', (xm + 330, ym), (xm + 330, ych), arrowprops=dict(arrowstyle='<->', lw=0.7, color=INK,
                                                                 shrinkA=0, shrinkB=0))
ins.text(xm + 355, (ym + ych) / 2, f'{(ym - ych) * mpp / 1000:.0f} km', va='center', fontsize=7.5,
         bbox=dict(boxstyle='square,pad=0.15', fc='white', ec='none', alpha=0.9))
ins.set_xticks([])
ins.set_yticks([])
for s in ins.spines.values():
    s.set_linewidth(0.6)
    s.set_color(HAIR)
ax.add_patch(Rectangle((xm - iw / 2, ych - 120), iw, ih, fill=False, lw=0.6, ec=HAIR))
ax.plot([xm, xm + 0.18 * (x1 - x0)], [ych - 120, y0 + 0.45 * (y1 - y0)], color=HAIR, lw=0.4)   # leader to inset
key = [Line2D([], [], color=BRICK, lw=0.9, ls=(0, (4, 2)), path_effects=CASE, label='chord between corners'),
       Line2D([], [], color=HAIR, lw=0.8, label='68° N parallel, fitted'),
       Line2D([], [], marker='o', ms=3.4, mfc='white', mec=HAIR, ls='', label='measured corner, residual')]
fig.legend(handles=key, loc='upper left', bbox_to_anchor=(ra[0], (BOT + PH + KEY - 0.6) / H_MM), ncol=2,
           frameon=False, fontsize=7, handlelength=2.0, columnspacing=0.9, handletextpad=0.5, borderaxespad=0)

# (b) colour classification (1/6 of the scan's resolution, origin at the corner box of the face)
ax = axes('b', 1, 0)
cls = np.asarray(Image.open(f'{IN}/R-35-37_g2_class.png').convert('RGB'))
fx0, fy0 = corners[:, 0].min(), corners[:, 1].min()
ax.imshow(cls, extent=(fx0, fx0 + 6 * cls.shape[1], fy0 + 6 * cls.shape[0], fy0), interpolation='nearest')
ax.set_xlim(x0, x1)
ax.set_ylim(y1, y0)

# (c) the sheet in ArcSurf
ax = axes('c', 0, 1)
leg = pd.read_csv(f'{IN}/legend_R-35-37_g2.csv', keep_default_na=False)
fill = dict(zip(leg['index'], leg['fill']))
M = to_px(gpd.read_file(f'{IN}/fig4_R-35-37_in_map.gpkg'))
NL = to_px(gpd.read_file(f'{IN}/R-35-37_g2.gpkg', layer='neatline'))
ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc='white', ec='none'))
NL.plot(ax=ax, color=SEA, linewidth=0)
M['geometry'] = shapely.intersection(shapely.make_valid(M.geometry.values, method='structure', keep_collapsed=False), NL.geometry.iloc[0], grid_size=0.5)  # frame only (px)
M['geometry'] = [shapely.union_all([p for p in shapely.get_parts(g) if p.geom_type in ('Polygon', 'MultiPolygon')])
                 if g.geom_type == 'GeometryCollection' else g for g in M.geometry]   # drop collapsed points/lines
M = M[~M.geometry.is_empty & M.geom_type.isin(['Polygon', 'MultiPolygon'])]
oth = M[M['this_sheet'] == 0]
mine = M[M['this_sheet'] == 1].copy()
oth.plot(ax=ax, color=OTHER, linewidth=0)
mine.plot(ax=ax, color=[fill.get(c, '#ffffff') for c in mine['src_code'].astype(str)], linewidth=0)
NL.boundary.plot(ax=ax, color=HAIR, linewidth=0.5)
ax.set_xlim(x0, x1)
ax.set_ylim(y1, y0)
ax.set_aspect('equal')
ax.set_axis_off()
rc = rect(0, 1)
for i, (c, lab) in enumerate([(OTHER, 'land mapped from finer sources'), (SEA, 'sea')]):
    fig.patches.append(Rectangle((rc[0] + (1 + 45 * i) / W_MM, rc[1] - 4.6 / H_MM), 3 / W_MM, 2 / H_MM,
                                 transform=fig.transFigure, fc=c, ec=SOFT, lw=0.3))
    fig.text(rc[0] + (5 + 45 * i) / W_MM, rc[1] - 4.7 / H_MM, lab, fontsize=7, va='bottom')

# (d) detail at full resolution: the scan with the polygon boundaries
ax = axes('d', 1, 1)
U = to_px(gpd.read_file(f'{IN}/R-35-37_g2.gpkg', layer='units'))
dx, dy = 3000, 4700                     # inland Kola Peninsula, around Murmansk (scan pixels)
dw = 1250
dh = dw * (y1 - y0) / (x1 - x0)
det = np.asarray(scan.crop((dx, dy, dx + dw, int(dy + dh))))
ax.imshow(det, extent=(dx, dx + dw, dy + dh, dy), interpolation='lanczos')
box = shapely.box(dx, dy, dx + dw, dy + dh)
B = U[U.intersects(box)].copy()
B['geometry'] = B.geometry.intersection(box)
B.boundary.plot(ax=ax, color=HAIR, linewidth=0.45)
ax.set_xlim(dx, dx + dw)
ax.set_ylim(dy + dh, dy)
ax.set_aspect('equal')
ax.set_axis_off()
km = 10_000 / mpp                                                      # 10 km bar
ax.plot([dx + 40, dx + 40 + km], [dy + dh - 40] * 2, color='white', lw=2.6, solid_capstyle='butt')
ax.plot([dx + 40, dx + 40 + km], [dy + dh - 40] * 2, color=HAIR, lw=1.2, solid_capstyle='butt')
ax.text(dx + 40 + km / 2, dy + dh - 60, '10 km', ha='center', va='bottom', fontsize=7,
        bbox=dict(boxstyle='square,pad=0.1', fc='white', ec='none', alpha=0.85))
fig.axes[0].add_patch(Rectangle((dx, dy), dw, dh, fill=False, lw=0.7, ec='white'))   # where the detail lies, in (a)

os.makedirs(OUT, exist_ok=True)
md = {'Author': 'Hugues Lantuit'}
fig.savefig(f'{OUT}/fig4_sheet_example.pdf', metadata=md)
fig.savefig(f'{OUT}/fig4_sheet_example.png', dpi=600, metadata=md)
fig.savefig(f'{OUT}/fig4_sheet_example.jpg', dpi=300, pil_kwargs={'quality': 92})
area_sheet = float(gpd.read_file(f'{IN}/fig4_R-35-37_in_map.gpkg').query('this_sheet == 1').area.sum() / 1e6)
print(f'figure {W_MM:.0f} x {H_MM:.0f} mm; sag at the central meridian {ym - ych:.1f} px = '
      f'{(ym - ych) * mpp / 1000:.2f} km; sheet polygons {len(U)}; pieces in ArcSurf {len(mine)} '
      f'({area_sheet:,.0f} km2); other sources {len(oth)}; detail polygons {len(B)}')
