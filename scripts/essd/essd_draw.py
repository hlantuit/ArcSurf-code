#!/usr/bin/env python
"""ESSD figures in the house style, drawn on the laptop from the bundle that essd_maps.py --export writes on Albedo
(rasters on the 2.5 km polar grid, coast / graticule / AMAP / LGM lines, code definitions, area sums). Needs only
numpy, pandas and matplotlib, so the figures can use the fonts installed here.

House style (H. Lantuit 2026-10-07: a distinct atlas look, Futura-like type):
  - type: Tw Cen MT (Twentieth Century, the Futura-like face installed here; Futura itself is not); 7-8.5 pt;
  - maps without a frame: pale sea with a white graticule that shows over the sea only, coast as a hairline, AMAP
    limit dashed brick with a white casing, small line keys and a 1000 km scale bar inside the map;
  - no default charts: keys are small tables (swatch, name, area, share with a hairline bar); time as columns on a
    decade axis; composition as a mosaic (column width = zone area); shares inside the LGM limit as a dot plot;
  - panel letters a, b, c in bold lower case outside the panels; descriptions belong in the captions.

usage: essd_draw.py BUNDLE.npz [OUTDIR] [--only=fig_age,...]
  -> OUTDIR/<fig>.pdf (TrueType text), .png (600 dpi), .jpg (300 dpi, for the manuscript artifact)"""
import json
import os
import sys

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
BUNDLE = ARGS[0]
OUT = ARGS[1] if len(ARGS) > 1 else os.path.join(os.path.dirname(os.path.abspath(BUNDLE)), 'figs')

# ------------------------------------------------------------------ style
for f in ('TCM_____.TTF', 'TCB_____.TTF', 'TCMI____.TTF', 'TCBI____.TTF'):         # Tw Cen MT
    p = os.path.join(os.environ.get('WINDIR', 'C:/Windows'), 'Fonts', f)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
FONT = 'Tw Cen MT' if any(f.name == 'Tw Cen MT' for f in font_manager.fontManager.ttflist) else 'DejaVu Sans'
INK, SOFT = '#262626', '#6e6a64'
SEA, PAPER, COAST = '#dde6ea', '#f1eee8', '#7a8d97'
NOTMAP_C = '#cfccc6'
EDGE = '#5b5751'
plt.rcParams.update({'font.family': FONT, 'font.size': 8.5, 'text.color': INK, 'axes.edgecolor': INK,
                     'axes.linewidth': 0.4, 'xtick.color': INK, 'ytick.color': INK, 'xtick.major.width': 0.4,
                     'xtick.major.size': 2.0, 'ytick.major.size': 0, 'pdf.fonttype': 42, 'svg.fonttype': 'none',
                     'savefig.facecolor': 'white'})
MM = 1 / 25.4
W_MM = 170.0

# ------------------------------------------------------------------ data
Z = np.load(BUNDLE)
META = json.loads(str(Z['meta']))
ST = pd.read_csv(BUNDLE.replace('.npz', '.csv'), keep_default_na=False)
for c in ('decade', 'agency', 'lic', 'scale'):
    ST[c] = ST[c].astype(int)
X0, Y0, X1, Y1 = META['frame']
NOTMAP = META['notmap']
PAL, NAMES, SHORT = META['pal'], META['names'], META['short']
HC_ORDER = META['hc_order']
TOTAL = ST['area_km2'].sum()


def lines(name):
    xy, idx = Z[f'v_{name}_xy'], Z[f'v_{name}_idx']
    return [xy[idx[i]:idx[i + 1]] for i in range(len(idx) - 1) if idx[i + 1] - idx[i] > 1]


COASTL, GRATL, AMAPL, LGML = lines('coast'), lines('grat'), lines('amap'), lines('lgm')
LAND = Z['r_land'] > 0


def hexrgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def area_by(col):
    return ST.groupby(col)['area_km2'].sum()


# ------------------------------------------------------------------ building blocks
AMAP_LINE = [dict(colors='white', linewidths=1.5, alpha=0.8),
             dict(colors='#8c2d1e', linewidths=0.6, linestyles=[(0, (4, 2))])]
LGM_LINE = [dict(colors='white', linewidths=1.6, alpha=0.8), dict(colors='#1d3550', linewidths=0.7)]


def rgba(code, colours):
    """sea transparent (the axes face and the graticule show through), land outside the domain in paper tone"""
    out = np.zeros(code.shape + (4,))
    land = LAND | (code > 0)
    out[land, :3] = hexrgb(PAPER)
    out[land, 3] = 1.0
    for c, col in colours.items():
        m = code == c
        out[m, :3] = hexrgb(col)
        out[m, 3] = 1.0
    return out


def letter_at(fig, rect, letter, dx_mm=0.0, top=None):
    """bold lower-case panel letter above the panel's top-left corner (top: figure fraction to put it at instead)"""
    fw, fh = fig.get_size_inches()
    y = top if top is not None else rect[1] + rect[3] + 1.2 * MM / fh
    fig.text(rect[0] + dx_mm * MM / fw, y, letter, fontsize=12, fontweight='bold', va='bottom', ha='left', color=INK)


def map_panel(fig, rect, img, letter, extra=(), notes=(('AMAP Arctic limit', AMAP_LINE),), scalebar=True):
    """map without a frame: sea face + white graticule (it shows over the sea only: the raster is transparent
    there), data raster, coast hairline, extra line layers [(segments, [style, ...])], small line keys (notes) in
    the lower right over land outside the domain, and a scale bar in the lower left over the North Atlantic"""
    ax = fig.add_axes(rect)
    ax.set_facecolor(SEA)
    ax.add_collection(LineCollection(GRATL, colors='white', linewidths=0.45, zorder=1))
    ax.imshow(img, extent=(X0, X1, Y0, Y1), interpolation='nearest', zorder=2)
    ax.add_collection(LineCollection(COASTL, colors=COAST, linewidths=0.3, zorder=3))
    z = 4.0
    layers = list(extra)
    if any(lab.startswith('AMAP') for lab, _ in notes) and AMAPL:
        layers.append((AMAPL, AMAP_LINE))
    for segs, styles in layers:
        for st in styles:
            ax.add_collection(LineCollection(segs, zorder=z, **st))
            z += 0.1
    ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1); ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    lx, ly = X1 - 2_300_000, Y0 + 330_000                 # Belarus / southern Russia: outside the domain
    for i, (lab, styles) in enumerate(notes):
        yy = ly + i * 230_000
        for st in styles:
            ax.add_collection(LineCollection([[(lx, yy), (lx + 400_000, yy)]], zorder=6, **st))
        ax.text(lx + 480_000, yy, lab, fontsize=7, va='center', color=INK, zorder=6)
    if scalebar:
        sx, sy = X0 + 250_000, Y0 + 260_000
        for k in range(2):
            ax.add_patch(Rectangle((sx + k * 500_000, sy), 500_000, 45_000, fc=INK if k == 0 else 'white',
                                   ec=INK, lw=0.4, zorder=6))
        ax.text(sx, sy + 90_000, '0', ha='center', va='bottom', fontsize=7, color=INK, zorder=6)
        ax.text(sx + 1_000_000, sy + 90_000, '1000 km', ha='center', va='bottom', fontsize=7, color=INK, zorder=6)
    letter_at(fig, rect, letter)
    return ax


def key_table(fig, rect, rows, letter, head=('', 'million km²', 'share'), sort=False):
    """an atlas key: swatch | name | area | share, a hairline bar for the share under each name.
    rows: (label, colour, area_km2)"""
    if sort:
        rows = sorted(rows, key=lambda r: -r[2])
    ax = fig.add_axes(rect)
    ax.set_axis_off()
    n = len(rows)
    ax.set_xlim(0, 1); ax.set_ylim(n + 0.9, -0.3)
    ax.text(0.0, -0.15, head[0].upper(), fontsize=7, color=SOFT, va='bottom', ha='left')
    ax.text(0.82, -0.15, head[1], fontsize=7, color=SOFT, va='bottom', ha='right')
    ax.text(1.0, -0.15, head[2], fontsize=7, color=SOFT, va='bottom', ha='right')
    ax.plot([0, 1], [0.05, 0.05], color=INK, lw=0.5)
    tot = sum(r[2] for r in rows)
    for i, (lab, col, a) in enumerate(rows):
        y = i + 0.55
        ax.add_patch(Rectangle((0.0, y - 0.28), 0.075, 0.42, fc=col, ec=EDGE, lw=0.3))
        ax.text(0.11, y - 0.06, lab, fontsize=8.5, va='center', ha='left')
        ax.text(0.82, y - 0.06, f'{a / 1e6:.2f}', fontsize=8.5, va='center', ha='right')
        ax.text(1.0, y - 0.06, f'{100 * a / tot:.0f} %' if a / tot >= 0.005 else '< 1 %', fontsize=8.5,
                va='center', ha='right')
        ax.plot([0.11, 1.0], [y + 0.3, y + 0.3], color='#e3dfd8', lw=1.6, solid_capstyle='butt')
        ax.plot([0.11, 0.11 + 0.89 * a / tot], [y + 0.3, y + 0.3], color=col, lw=1.6, solid_capstyle='butt')
    ax.plot([0, 1], [n + 0.75, n + 0.75], color=INK, lw=0.3)
    ax.text(0.11, n + 0.85, 'total', fontsize=7.5, color=SOFT, va='top')
    ax.text(0.82, n + 0.85, f'{tot / 1e6:.2f}', fontsize=7.5, color=SOFT, va='top', ha='right')
    letter_at(fig, rect, letter, dx_mm=-1.5)
    return ax


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    md = {'Author': 'Hugues Lantuit'}
    fig.savefig(f'{OUT}/{name}.pdf', metadata=md)
    fig.savefig(f'{OUT}/{name}.png', dpi=600, metadata=md)
    fig.savefig(f'{OUT}/{name}.jpg', dpi=300, pil_kwargs={'quality': 92})
    plt.close(fig)
    print('wrote', f'{OUT}/{name}.(pdf|png|jpg)', flush=True)


H_MAP = 0.64 * W_MM * (Y1 - Y0) / (X1 - X0)            # 108.8 x 93.1 mm map


def figure(h_mm):
    fig = plt.figure(figsize=(W_MM * MM, h_mm * MM))
    return fig, [2.5 / W_MM, (h_mm - 6.0 - H_MAP) / h_mm, 0.64, H_MAP / h_mm]      # 2.5 mm left margin


# ------------------------------------------------------------------ figures
SCALE_COL = [c[2] for c in META['scale_classes']]
# labels from the bundle, so that they follow its class limits (merge 49: 1:125 000 - 1:253 440); the key head says 1 : ...
SCALE_LAB = [c[1].replace('1:', '').replace(' – ', '–').replace(' - ', '–').strip() for c in META['scale_classes']]


def fig_scale():
    fig, mrect = figure(102.0)
    cols = {i + 1: c for i, c in enumerate(SCALE_COL)}
    cols[NOTMAP] = NOTMAP_C
    map_panel(fig, mrect, rgba(Z['r_sc'], cols), 'a')
    a = area_by('scale')
    rows = [(SCALE_LAB[i], SCALE_COL[i], float(a.get(i + 1, 0.0))) for i in range(len(SCALE_COL))]
    rows.append(('not mapped', NOTMAP_C, float(a.get(NOTMAP, 0.0))))
    key_table(fig, [0.675, 0.30, 0.31, 0.50], rows, 'b', head=('source scale 1 : …', 'million km²', 'share'))
    save(fig, 'fig2_source_scale')


LIC_COL = {'open': '#3e7c5d', 'open_sa': '#8cc1a2', 'internal_only': '#b4513a', 'unknown': '#d6a23e'}
LIC_LAB = {'open': 'Open licence', 'open_sa': 'Open, share-alike', 'internal_only': 'Internal use only',
           'unknown': 'Terms not stated'}


def fig_licence():
    fig, mrect = figure(102.0)
    cols = {i + 1: LIC_COL[k] for i, (k, _, _) in enumerate(META['lic'])}
    cols[NOTMAP] = NOTMAP_C
    map_panel(fig, mrect, rgba(Z['r_lic'], cols), 'a')
    a = area_by('lic')
    rows = [(LIC_LAB[k], LIC_COL[k], float(a.get(i + 1, 0.0))) for i, (k, _, _) in enumerate(META['lic'])]
    rows.append(('Not mapped', NOTMAP_C, float(a.get(NOTMAP, 0.0))))
    key_table(fig, [0.675, 0.40, 0.31, 0.36], rows, 'b', head=('redistribution', 'million km²', 'share'))
    save(fig, 'fig3_licence')


# age: faded sepia for old maps to deep blue for recent ones (monotonic in lightness)
AGE_COL = ['#e8dcc5', '#d6bf98', '#bf9f74', '#8f8f7a', '#5a8486', '#2f6a80', '#1d4566']
AGE_UNKNOWN = '#b49aaa'
AGE_TICK = ['pre-\n’70', '’70s', '’80s', '’90s', '’00s', '’10s', '’20s']        # compact decade labels


def fig_age():
    fig, mrect = figure(102.0)
    cols = {i + 1: c for i, c in enumerate(AGE_COL)}
    cols[len(AGE_COL) + 1] = AGE_UNKNOWN
    cols[NOTMAP] = NOTMAP_C
    map_panel(fig, mrect, rgba(Z['r_dec'], cols), 'a')
    a = area_by('decade')
    vals = [float(a.get(i + 1, 0.0)) / 1e6 for i in range(len(AGE_COL))]
    unk = float(a.get(len(AGE_COL) + 1, 0.0)) / 1e6
    rect = [0.70, 0.20, 0.285, 0.55]
    ax = fig.add_axes(rect)
    x = np.arange(len(vals))
    ax.bar(x, vals, width=0.74, color=AGE_COL, edgecolor=EDGE, linewidth=0.3)
    xu = len(vals) + 0.7
    ax.bar([xu], [unk], width=0.74, color=AGE_UNKNOWN, edgecolor=EDGE, linewidth=0.3)
    top = max(vals + [unk])
    for xx, v in list(zip(x, vals)) + [(xu, unk)]:
        s = v * 1e6 / TOTAL                                       # small shares as in the key tables ('< 1 %')
        ax.text(xx, v + 0.02 * top, f'{100 * s:.0f} %' if s >= 0.005 or s == 0 else '< 1 %', ha='center',
                va='bottom', fontsize=7.5)
    ax.text(0.0, -0.2, f'share of the domain, 100 % = {TOTAL / 1e6:.2f} million km²', fontsize=7, color=SOFT,
            va='top', transform=ax.transAxes)
    ax.set_xticks(list(x) + [xu])
    ax.set_xticklabels(AGE_TICK + ['n.d.'], fontsize=7.5)
    ax.tick_params(axis='x', length=0, pad=3)
    ax.set_yticks([])
    for sp in ('top', 'right', 'left'):
        ax.spines[sp].set_visible(False)
    ax.set_ylim(0, top * 1.12)
    letter_at(fig, rect, 'b', dx_mm=-3)
    save(fig, 'fig7_age')


AG_COL = ['#b4513a', '#dc9a58', '#2d5a86', '#86a9cb', '#4d865a', '#a7c48b', '#8a5a8b', '#d8c159', '#6a4f3f']
AG_LAB = ['VSEGEI', 'Siberian database', 'Geol. Survey of Canada', 'Canadian provinces', 'USGS', 'Alaska DGGS',
          'GEUS', 'Nordic surveys', 'Research maps']                    # full names in the caption


def fig_agency():
    fig, mrect = figure(102.0)
    cols = {i + 1: c for i, c in enumerate(AG_COL)}
    cols[len(AG_COL) + 1] = '#9a9a9a'
    cols[NOTMAP] = NOTMAP_C
    map_panel(fig, mrect, rgba(Z['r_ag'], cols), 'a')
    a = area_by('agency')
    rows = [(AG_LAB[i], AG_COL[i], float(a.get(i + 1, 0.0))) for i in range(len(AG_COL)) if a.get(i + 1, 0) > 0]
    rows = sorted(rows, key=lambda r: -r[2]) + [('Not mapped', NOTMAP_C, float(a.get(NOTMAP, 0.0)))]
    key_table(fig, [0.675, 0.10, 0.31, 0.78], rows, 'b', head=('source agency', 'million km²', 'share'))
    save(fig, 'fig8_agency')


def fig_permafrost():
    h = 124.0
    fig, mrect = figure(h)
    pfc = {z: c for z, _, c in META['pf_zones']}
    pfc['none'] = META['no_pf']
    cols = {i + 1: pfc[z] for i, (z, _) in enumerate(META['pf'])}
    cols[9], cols[10] = META['inset_ice'], PAL['Y']
    map_panel(fig, mrect, rgba(Z['r_pf'], cols), 'a')
    # zone key under the map
    k = fig.add_axes([mrect[0], 0.0, 0.64, (h - 9.0 - H_MAP) / h]); k.set_axis_off(); k.set_xlim(0, 4)
    k.set_ylim(2, 0)
    zname = {'none': 'No permafrost'}                    # as on the A0 inset
    items = ([(zname.get(z, n), pfc[z]) for z, n in META['pf']]
             + [('Glacier ice', META['inset_ice']), ('Yedoma (IRYP v2)', PAL['Y'])])
    for i, (n, c) in enumerate(items):
        xx, yy = i % 4, 0.55 + (i // 4) * 0.8
        k.add_patch(Rectangle((xx + 0.02, yy - 0.22), 0.12, 0.38, fc=c, ec=EDGE, lw=0.3))
        k.text(xx + 0.19, yy - 0.03, n, fontsize=8, va='center')
    # b: mosaic, column width = zone area, segments = classes
    zones = [(z, n) for z, n in META['pf']]
    comp = {z: ST[ST['pf_zone'] == z].groupby('hclass')['area_km2'].sum() for z, _ in zones}
    widths = np.array([comp[z].sum() for z, _ in zones])
    hcs = [c for c in HC_ORDER if any(comp[z].get(c, 0) > 0 for z, _ in zones)]
    rect = [0.70, 0.50, 0.285, 0.33]                     # room above for the rotated zone names
    ax = fig.add_axes(rect)
    x = 0.0
    gap = widths.sum() * 0.012
    names = {'continuous': 'continuous', 'discontinuous': 'discont.', 'sporadic': 'sporadic', 'isolated': 'isolated patches',
             'none': 'no permafrost'}
    for (z, n), wdt in zip(zones, widths):
        y = 0.0
        for c in hcs:
            f = comp[z].get(c, 0.0) / wdt
            if f > 0:
                ax.add_patch(Rectangle((x, y), wdt, f, fc=PAL[c], ec='white', lw=0.25))
            y += f
        ax.add_patch(Rectangle((x, 0), wdt, 1, fc='none', ec=EDGE, lw=0.4, zorder=3))   # white ice stays visible
        ax.text(x + wdt / 2, 1.03, names[z], rotation=90 if wdt < widths.sum() * 0.2 else 0, ha='center',
                va='bottom', fontsize=7.5)
        ax.text(x + wdt / 2, -0.03, f'{wdt / 1e6:.1f}', ha='center', va='top', fontsize=7.5)
        x += wdt + gap
    ax.set_xlim(0, x - gap); ax.set_ylim(0, 1)
    ax.set_axis_off()
    ax.text(0, -0.13, 'zone area, million km²', fontsize=7, color=SOFT, va='top')
    letter_at(fig, rect, 'b', dx_mm=-3)
    # c: the IRYP Yedoma domain as one 100 % strip
    y_ = ST[ST['yedoma'] == 'yes'].groupby('hclass')['area_km2'].sum()
    yt = y_.sum()
    rect2 = [0.70, 0.355, 0.285, 0.04]
    ax2 = fig.add_axes(rect2); ax2.set_axis_off(); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
    x = 0.0
    for c in hcs:
        f = y_.get(c, 0.0) / yt
        if f > 0:
            ax2.add_patch(Rectangle((x, 0), f, 1, fc=PAL[c], ec='white', lw=0.25))
            if f > 0.12:
                ax2.text(x + f / 2, 0.5, f'{100 * f:.0f} %', ha='center', va='center', fontsize=7)
        x += f
    ax2.text(0, 1.25, f'Yedoma domain (IRYP v2), {yt / 1e6:.2f} million km²', fontsize=7.5, va='bottom')
    letter_at(fig, rect2, 'c', dx_mm=-3)
    # class key
    kk = fig.add_axes([0.665, 0.0, 0.335, 0.31]); kk.set_axis_off(); kk.set_xlim(0, 2); kk.set_ylim(10.4, -0.2)
    for i, c in enumerate(hcs):
        xx, yy = i // 10, i % 10 + 0.5
        kk.add_patch(Rectangle((xx + 0.02, yy - 0.32), 0.1, 0.62, fc=PAL[c], ec=EDGE, lw=0.3))
        kk.text(xx + 0.16, yy, SHORT.get(c, NAMES[c]), fontsize=7.5, va='center')
    save(fig, 'fig9_permafrost')


LGM_SHORT = {'Fluvial, lacustrine,\nthermokarst': 'Fluvial, lacustrine', 'Quaternary undivided': 'Quat. undivided',
             'Ice complex (yedoma)': 'Ice complex'}


def fig_lgm():
    if not LGML:
        print('no LGM lines in the bundle', flush=True)
        return
    fig, mrect = figure(102.0)
    muted = '#d7d1c5'
    cols = {i + 1: muted for i in range(len(HC_ORDER))}
    for c in META['glacial'] + ['M']:
        cols[HC_ORDER.index(c) + 1] = PAL[c]
    cols[HC_ORDER.index('I') + 1] = META['inset_ice']
    cols[HC_ORDER.index('H') + 1] = PAL['H']
    cols[HC_ORDER.index('U') + 1] = NOTMAP_C
    map_panel(fig, mrect, rgba(Z['r_hc'], cols), 'a', extra=[(LGML, LGM_LINE)],
              notes=(('LGM ice limit', LGM_LINE),))
    rows = []
    for name, cls in META['lgm_groups']:
        m = ST['hclass'].isin(cls)
        a, i = float(ST.loc[m, 'area_km2'].sum()), float(ST.loc[m, 'lgm_km2'].sum())
        if a > 0:
            rows.append((LGM_SHORT.get(name, name.replace('\n', ' ')), a, 100 * i / a, PAL[cls[0]]))
    rows.sort(key=lambda r: -r[2])
    rect = [0.79, 0.12, 0.165, 0.80]                     # 7 mm right margin for the labels near 100 %
    ax = fig.add_axes(rect)
    n = len(rows)
    amax = max(r[1] for r in rows)
    for k, (name, a, p, col) in enumerate(rows):
        y = n - 1 - k
        ax.plot([0, 100], [y, y], color='#e3dfd8', lw=0.8, zorder=1)
        s = 8 + 120 * np.sqrt(a / amax)
        ax.scatter([p], [y], s=s, color=col, edgecolor='#3a3733', linewidth=0.4, zorder=3)
        ax.text(-4, y + 0.08, name, ha='right', va='center', fontsize=8)
        ax.text(-4, y - 0.36, f'{a / 1e6:.2f} million km²', ha='right', va='center', fontsize=6.5, color=SOFT)
        r_units = np.sqrt(s / np.pi) / (rect[2] * W_MM / 0.3528 / 100)        # dot radius in % units
        ax.text(p + r_units + 2.5, y, f'{p:.0f} %', ha='left', va='center', fontsize=7.5)
    ax.set_xlim(0, 100); ax.set_ylim(-0.8, n - 0.3)
    ax.set_yticks([]); ax.set_xticks([0, 50, 100]); ax.set_xticklabels(['0', '50', '100 %'], fontsize=7.5)
    for sp in ('top', 'right', 'left'):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel('share inside the LGM limit', fontsize=7, color=SOFT)
    letter_at(fig, [0.66] + rect[1:], 'b')
    save(fig, 'fig10_lgm')


# deglaciation age (NADI-1 OPTIMAL + DATED-1 most credible): bins in ka, old (dark) to young (light)
DEG_BINS = [(20.0, 25.0, '25–20'), (16.0, 20.0, '20–16'), (14.0, 16.0, '16–14'), (12.0, 14.0, '14–12'),
            (10.0, 12.0, '12–10'), (8.0, 10.0, '10–8'), (6.0, 8.0, '8–6'), (0.0, 6.0, '≤ 6')]
DEG_COL = ['#16223d', '#213d63', '#2b5d82', '#3b7d97', '#5b9ea8', '#86bcbb', '#b6d7cf', '#e0eee6']
DEG_NOTIME, DEG_FREE = '#c9cdd3', '#ddd4c2'
RIDGE = ['T', 'GF', 'GL', 'GM', 'M', 'O', 'R']


def fig_deglac():
    if 'r_deg' not in Z.files:
        print('no deglaciation raster in the bundle', flush=True)
        return
    deg = Z['r_deg'].astype(float) / 2.0                               # ka; 0 = no slice covered the pixel
    hc = Z['r_hc']
    dom = (hc > 0)
    ice = hc == HC_ORDER.index('I') + 1
    code = np.zeros(deg.shape, np.int16)
    for i, (lo, hi, _) in enumerate(DEG_BINS):
        code[(deg > lo) & (deg <= hi) & dom] = i + 1
    lgm = Z['r_lgm'] > 0 if 'r_lgm' in Z.files else np.zeros(deg.shape, bool)
    code[dom & (deg == 0) & lgm] = 20                                   # LGM ice, timing not reconstructed
    code[dom & (deg == 0) & ~lgm] = 21                                  # ice-free at the LGM
    code[ice] = 22                                                      # glacier ice today
    cols = {i + 1: c for i, c in enumerate(DEG_COL)}
    cols.update({20: DEG_NOTIME, 21: DEG_FREE, 22: META['inset_ice']})
    fig, mrect = figure(112.0)
    map_panel(fig, mrect, rgba(code, cols), 'a')
    # key under the map: the age ramp with ticks at the bin edges, the three other states stacked to its right
    h = 112.0
    k = fig.add_axes([mrect[0], 0.0, 0.64, (h - 8.0 - H_MAP) / h]); k.set_axis_off(); k.set_xlim(0, 1)
    k.set_ylim(1, 0)
    n, sw = len(DEG_COL), 0.055
    for i, c in enumerate(DEG_COL):
        k.add_patch(Rectangle((0.02 + i * sw, 0.30), sw, 0.26, fc=c, ec='none'))
    k.add_patch(Rectangle((0.02, 0.30), sw * n, 0.26, fc='none', ec=EDGE, lw=0.3))
    edges = [b[1] for b in DEG_BINS] + [0.0]
    for i, e in enumerate(edges):
        k.plot([0.02 + i * sw] * 2, [0.56, 0.62], color=EDGE, lw=0.3)
        k.text(0.02 + i * sw, 0.66, f'{e:g}', ha='center', va='top', fontsize=7)
    k.text(0.02, 0.24, 'deglaciated, ka before present', fontsize=7, color=SOFT, va='bottom')
    for j, (lab, c) in enumerate((('LGM ice, timing not reconstructed (Greenland)', DEG_NOTIME),
                                  ('Ice-free at the LGM', DEG_FREE), ('Glacier ice today', META['inset_ice']))):
        y = 0.12 + j * 0.30
        k.add_patch(Rectangle((0.54, y), 0.025, 0.2, fc=c, ec=EDGE, lw=0.3))
        k.text(0.575, y + 0.1, lab, fontsize=7, va='center')
    # b: ridgelines, area of each class against deglaciation age (0.5 ka steps; DATED-1 slices are whole ka);
    # names and numbers in their own column so they never cross the curves
    ages = np.arange(0, 51) / 2.0
    rect = [0.775, 0.14, 0.21, 0.80]
    ax = fig.add_axes(rect)
    lab = fig.add_axes([0.665, 0.14, 0.11, 0.80]); lab.set_axis_off(); lab.set_xlim(0, 1)
    lab.set_ylim(-0.1, len(RIDGE))
    half = Z['r_deg'].astype(np.int64)
    for r, c in enumerate(RIDGE):
        m = (hc == HC_ORDER.index(c) + 1) & (half > 0)
        if not m.any():
            continue
        cnt = np.bincount(half[m], minlength=51)[:51].astype(float)
        area_rec = m.sum() * 6.25 / 1e6                                 # million km2 with an age (2.5 km pixels)
        y0 = len(RIDGE) - 1 - r
        dens = cnt / cnt.max() * 0.92
        ax.fill_between(ages, y0, y0 + dens, color=PAL[c], lw=0, zorder=2 * r + 1)
        ax.plot(ages, y0 + dens, color='#3a3733', lw=0.5, zorder=2 * r + 2)
        ax.plot([0, 25], [y0, y0], color='#3a3733', lw=0.4, zorder=2 * r + 2)
        med = ages[np.searchsorted(np.cumsum(cnt), cnt.sum() / 2)]
        ax.plot([med, med], [y0, y0 + 0.92], color='#3a3733', lw=0.45, ls=(0, (2, 1.5)), zorder=2 * r + 2)
        lab.text(0.0, y0 + 0.62, SHORT.get(c, NAMES[c]), ha='left', va='center', fontsize=8)
        lab.text(0.0, y0 + 0.34, f'median {med:.1f} ka', ha='left', va='center', fontsize=6.5, color=SOFT)
        lab.text(0.0, y0 + 0.08, f'{area_rec:.2f} million km²', ha='left', va='center', fontsize=6.5, color=SOFT)
    ax.set_xlim(25, 0)                                                  # time runs left to right, old to young
    ax.set_ylim(-0.1, len(RIDGE))
    ax.set_yticks([]); ax.set_xticks([25, 20, 15, 10, 5, 0])
    ax.tick_params(axis='x', labelsize=7.5)
    for sp in ('top', 'right', 'left'):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel('deglaciation age, ka', fontsize=7, color=SOFT)
    letter_at(fig, [0.665] + rect[1:], 'b')
    save(fig, 'fig11_deglaciation')


FIGS = {'fig_scale': fig_scale, 'fig_licence': fig_licence, 'fig_age': fig_age, 'fig_agency': fig_agency,
        'fig_permafrost': fig_permafrost, 'fig_lgm': fig_lgm, 'fig_deglac': fig_deglac}

if __name__ == '__main__':
    print('font:', FONT, flush=True)
    only = next((a.split('=', 1)[1].split(',') for a in sys.argv if a.startswith('--only=')), list(FIGS))
    for name in only:
        FIGS[name]()
