#!/usr/bin/env python
"""Figure 3 of the data paper: the Russian sheets used in ArcSurf, (a) by scale and form, (b) by georeferencing error.
Frames from the sheet nomenclature (ru_nomenclature.py), clipped to Russia (Natural Earth 1:10m); 1:200,000 sheets
drawn over the 1:1,000,000 sheets they take precedence over. Errors as in Table 3: the RMS residual of the frame fit
(vector PDFs) or of the corner and tie fit (rasters); USGS per-sheet RMS for the Siberian database.
House style of essd_draw.py: coast and graticule from the map bundle, Tw Cen MT, no frames.
usage: fig3_russian_sheets.py TABLE3.csv NE_COUNTRIES.shp BUNDLE.npz OUTDIR [SOURCES.csv [FOOTPRINTS.gpkg]]
  SOURCES.csv (sources_table.py of the release): the sheets with area in the map; without it, final_map_km2 of
  TABLE3.csv decides
  FOOTPRINTS.gpkg (ru_sheet_footprints.py): draw the land each sheet holds in the map instead of its nominal frame
  (a frame shows a sheet that keeps a thin strip as if it held its whole quadrangle)"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ru_nomenclature as RN  # noqa: E402

T3, NE, BUNDLE, OUT = sys.argv[1:5]
SRC = sys.argv[5] if len(sys.argv) > 5 else None
FP = sys.argv[6] if len(sys.argv) > 6 else None


def _dash(s):
    """'P50,51' of the USGS database -> 'P-50-51' of the nomenclature."""
    m = re.match(r'^([A-Z])(\d+),(\d+)$', str(s))
    return '{}-{}-{}'.format(*m.groups()) if m else str(s)


for f in ('TCM_____.TTF', 'TCB_____.TTF'):
    p = os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts', f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
FONT = 'Tw Cen MT' if any(f.name == 'Tw Cen MT' for f in font_manager.fontManager.ttflist) else 'DejaVu Sans'
INK, SOFT, SEA, PAPER, COAST = '#262626', '#6e6a64', '#dde6ea', '#f1eee8', '#7a8d97'
plt.rcParams.update({'font.family': FONT, 'font.size': 8.0, 'text.color': INK, 'pdf.fonttype': 42,
                     'savefig.facecolor': 'white'})
MM = 1 / 25.4
W_MM = 170.0

FORM = [('200k_vector', '1:200k vector PDF', '#1d4566'), ('200k_scan', '1:200k scan', '#4f8a8b'),
        ('200k_preview', '1:200k preview', '#a9cfc9'), ('1M_vector', '1:1M vector PDF', '#7b4a24'),
        ('1M_rendered', '1:1M rendered or raster face', '#b4813a'), ('1M_g2scan', '1:1M scan, 2nd generation', '#d9a441'),
        ('1M_preview', '1:1M preview', '#efdfae'), ('usgs', 'USGS database, 1:1M', '#8a79ad')]
ERR = [(10, '≤ 10 m', '#1d4566'), (50, '10–50 m', '#3f7a8c'), (200, '50–200 m', '#8fb8b4'),
       (500, '200–500 m', '#e3c98f'), (1000, '0.5–1 km', '#d08c3c'), (1e9, '> 1 km', '#9c3d2c')]
# USGS Siberian database: per-sheet RMS from the USGS rectification metadata (R55,57: none given)
USGS = {'P-50-51': 302, 'P-52-53': 236, 'Q-50-51': 225, 'Q-52-53': 142, 'Q-54-55': 205, 'Q-56-57': 175,
        'R-53-55': 189, 'S-47-49': 257, 'S-50-52': 137, 'S-53-55': 127, 'R-55-57': np.nan}
USGS_IN_MAP = {'P-50-51', 'P-52-53', 'Q-52-53', 'Q-54-55', 'Q-56-57', 'R-53-55', 'R-55-57', 'S-47-49', 'S-50-52',
               'S-53-55'}

t = pd.read_csv(T3)
if SRC:
    sm = pd.read_csv(SRC)
    sm = sm[sm['area_km2'] > 0]
    used = set(sm.loc[sm['src_id'].isin(['ru_vsegei_pdf', 'ru_vsegei_preview']), 'src_sheet'])
    t = t[t['sheet'].isin(used)].copy()
    bry = sm.loc[sm['src_id'] == 'ru_bryant_vsegei1m', 'src_sheet'].astype(str)
    USGS_IN_MAP = {_dash(b) for b in bry}
else:
    t = t[t['final_map_km2'].fillna(0) > 0].copy()
u = pd.DataFrame({'sheet': list(USGS), 'category': 'usgs', 'fit_rms_m': list(USGS.values())})
u = u[u['sheet'].isin(USGS_IN_MAP)]
t = pd.concat([t[['sheet', 'category', 'fit_rms_m']], u], ignore_index=True)
ne = gpd.read_file(NE)
ru = ne[ne['ADM0_A3'] == 'RUS'].geometry.union_all()
if FP:
    # keyed by (USGS database?, sheet): a USGS sheet and a VSEGEI sheet may share a name; PDF and preview of one
    # VSEGEI sheet are drawn as one
    fp = gpd.read_file(FP).to_crs('EPSG:6931')
    fpg = {}
    for usgs, sh, gm in zip(fp['src_id'] == 'ru_bryant_vsegei1m', fp['src_sheet'], fp.geometry):
        fpg.setdefault((bool(usgs), _dash(sh)), []).append(gm)
    fpg = {k: shapely.union_all(np.array(v)) for k, v in fpg.items()}
    # the simplified footprints are riddled with slivers and pinholes that the white sheet outline turns into speckle;
    # a 1 km closing removes them and changes nothing else at the figure's ~4 km per pixel
    fpg = {k: shapely.buffer(shapely.buffer(v, 1000.0, quad_segs=2), -1000.0, quad_segs=2) for k, v in fpg.items()}
    t['geometry'] = [fpg.get((c == 'usgs', s)) for c, s in zip(t['category'], t['sheet'])]
    miss = t.loc[t['geometry'].isna(), 'sheet'].tolist()
    if miss:
        print(f'no footprint for {len(miss)} sheets: {miss[:12]}')
    g = gpd.GeoDataFrame(t[t['geometry'].notna()], geometry='geometry', crs='EPSG:6931')
else:
    t['geometry'] = [RN.frame(s) for s in t['sheet']]
    g = gpd.GeoDataFrame(t, geometry='geometry', crs='EPSG:4326')
    g['geometry'] = g.geometry.intersection(ru)
    g = g.to_crs('EPSG:6931')
g = g[~g.geometry.is_empty]
ROT = -100.0          # degrees: turn the polar map so that 100 E points down and Russia lies across the page
g['geometry'] = g.geometry.rotate(ROT, origin=(0, 0))
g['scale'] = np.where(g['category'].str.startswith('200k'), 2, 1)       # 1:200k drawn over 1:1M
g = g.sort_values('scale')

Z = np.load(BUNDLE)


def lines(name):
    xy, idx = Z[f'v_{name}_xy'], Z[f'v_{name}_idx']
    return [xy[idx[i]:idx[i + 1]] for i in range(len(idx) - 1) if idx[i + 1] - idx[i] > 1]


def rot(a):
    c, s_ = np.cos(np.radians(ROT)), np.sin(np.radians(ROT))
    return np.c_[a[:, 0] * c - a[:, 1] * s_, a[:, 0] * s_ + a[:, 1] * c]


coast, grat = [rot(a) for a in lines('coast')], [rot(a) for a in lines('grat')]
x0, y0, x1, y1 = g.total_bounds
pad = 150_000
x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
PW_MM = 145.0
PH = PW_MM * (y1 - y0) / (x1 - x0)
TOPM, KEYM = 5.0, 11.5
OTHER = 'Land held by other sources, or outside the ArcSurf domain'
H_MM = 2 * (TOPM + PH + KEYM)
XL = (W_MM - PW_MM) / 2
fig = plt.figure(figsize=(W_MM * MM, H_MM * MM))


def panel(k, top_mm, colour, key, title):
    ax = fig.add_axes([XL / W_MM, (H_MM - top_mm - PH) / H_MM, PW_MM / W_MM, PH / H_MM])
    ax.set_axis_off()
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=SEA, ec='none', zorder=0))
    ax.add_collection(LineCollection(grat, colors='white', linewidths=0.4, zorder=1))
    ne6931 = gpd.GeoSeries([ru], crs='EPSG:4326').to_crs('EPSG:6931').rotate(ROT, origin=(0, 0))
    ne6931.plot(ax=ax, color=PAPER, linewidth=0, zorder=2)
    g.plot(ax=ax, color=colour, edgecolor='white', linewidth=0.15, zorder=3)
    ax.add_collection(LineCollection(coast, colors=COAST, linewidths=0.3, zorder=4))
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect('equal')
    fig.text((XL - 1.0) / W_MM, (H_MM - top_mm + 0.6) / H_MM, k, fontsize=12, fontweight='bold', va='bottom',
             ha='right')
    # key in the lower margin of the panel
    # the paper tone (land without a Russian sheet) starts a row of its own
    for i, (lab, c, n) in enumerate(key + [(OTHER, PAPER, None)]):
        col, row = (i % 4, i // 4) if n is not None else (0, (len(key) + 3) // 4)
        xk, yk = (XL + 37 * col) / W_MM, (H_MM - top_mm - PH - 4.0 - 3.3 * row) / H_MM
        fig.patches.append(Rectangle((xk, yk), 3 / W_MM, 2.2 / H_MM, transform=fig.transFigure, fc=c, ec=SOFT,
                                     lw=0.3))
        fig.text(xk + 4 / W_MM, yk, f'{lab} ({n})' if n is not None else lab, fontsize=6.8, va='bottom')


cnt = g.groupby('category').size()
form_col = {k: c for k, _, c in FORM}
panel('a', TOPM, [form_col[c] for c in g['category']],
      [(lab, c, int(cnt.get(k, 0))) for k, lab, c in FORM], 'Scale and form of the sheets used')


def err_col(v):
    if pd.isna(v):
        return '#cfccc6'
    for lim, _, c in ERR:
        if v <= lim:
            return c


ecls = [next((lab for lim, lab, _ in ERR if v <= lim), None) if pd.notna(v) else 'not given' for v in g['fit_rms_m']]
ecnt = pd.Series(ecls).value_counts()
panel('b', 2 * TOPM + PH + KEYM, [err_col(v) for v in g['fit_rms_m']],
      [(lab, c, int(ecnt.get(lab, 0))) for _, lab, c in ERR] + [('not given', '#cfccc6', int(ecnt.get('not given', 0)))],
      'Georeferencing error')
os.makedirs(OUT, exist_ok=True)
md = {'Author': 'Hugues Lantuit'}
fig.savefig(f'{OUT}/fig3_russian_sheets.pdf', metadata=md)
fig.savefig(f'{OUT}/fig3_russian_sheets.png', dpi=600, metadata=md)
fig.savefig(f'{OUT}/fig3_russian_sheets.jpg', dpi=300, pil_kwargs={'quality': 92})
print(f'figure {W_MM:.0f} x {H_MM:.0f} mm; sheets drawn {len(g)}; by form {cnt.to_dict()}; by error {ecnt.to_dict()}')
