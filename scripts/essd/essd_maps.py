#!/usr/bin/env python
"""ESSD manuscript maps from a merged tile set (default work/a0_tiles_m43). One pass over the tiles rasterises the
polygon attributes on a 2.5 km polar grid (EPSG:6931, the A0 frame) and sums the areas; then each figure is a map (a)
and a bar chart (b) whose bars double as the legend.

  fig_age          publication year of the source map, by decade (cividis; year unknown in a colour outside it)
  fig_agency       agency that produced the source map (Okabe-Ito)
  fig_licence      redistribution status of the polygon (the 'redistribution' attribute as it stands)
  fig_lgm          glacial classes against the LGM ice limit (Batchelor et al. 2019), once its shapefile is in raw/basemap/lgm
  fig_permafrost   permafrost zone (Obu et al. 2019) and IRYP v2 Yedoma 'yes', from the polygon attributes, with the
                   class (hclass) composition of each zone and of the Yedoma domain

usage: essd_maps.py [TILES_DIR] [--only=fig_age,fig_agency] [--fresh]
  -> out/essd_figs/<fig>.png (300 dpi) and .pdf; work/essd_tables/maps_area_<tiles>.csv; rasters cached in
     work/essd_tables/maps_rasters_<tiles>.npz (delete it, or pass --fresh, after a new merge)
House style (as the Herschel figures): 170 mm wide, sans 7 pt, no titles inside panels (the caption carries them),
bold (a)/(b) labels, pdf.fonttype 42, author metadata."""
import glob
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
for _d in (os.path.dirname(os.path.abspath(__file__)), os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')):
    sys.path.insert(0, _d)                       # a0_map.py next to this script or one level up (scripts/essd/)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import rasterio.features  # noqa: E402
from affine import Affine  # noqa: E402
import a0_map as A  # noqa: E402   frame, palette, coastline, land mask
import matplotlib  # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402

ROOT = A.ROOT
ARGS = [a for a in sys.argv[1:] if not a.startswith('--')]
TD = ARGS[0] if ARGS else f'{ROOT}/work/a0_tiles_m43'
TNAME = os.path.basename(os.path.normpath(TD))
OUT = f'{ROOT}/out/essd_figs'
TAB = f'{ROOT}/work/essd_tables'
RES = 2500.0
X0, Y0, X1, Y1 = A.FRAME
NX, NY = int(round((X1 - X0) / RES)), int(round((Y1 - Y0) / RES))
TILE = 100_000
NT = int(TILE / RES)
NOTMAP = 254                                    # polygon present, class U or no source

SEA, PAPER, NOTMAP_C = '#e3edf3', '#f4f1ea', '#d0d0d0'
COAST, GRAT = '#5b7f95', '#a9b6bf'
DECADES = [(0, 1969, 'before 1970'), (1970, 1979, '1970s'), (1980, 1989, '1980s'),
           (1990, 1999, '1990s'), (2000, 2009, '2000s'), (2010, 2019, '2010s'), (2020, 2029, '2020s')]
DEC_COL = [matplotlib.colors.to_hex(c) for c in plt.get_cmap('cividis')(np.linspace(0.0, 1.0, len(DECADES)))]
YEAR_UNKNOWN = '#e3a99c'                         # outside the cividis range (blue - grey - yellow)
# agency groups: the first matching src_id prefix wins (ca_gsc before the other ca_ sources)
AGENCY = [('VSEGEI (Russia)', ('ru_vsegei',), '#d55e00'),
          ('Siberian database\n(Bryant et al. 2017)', ('ru_bryant',), '#e69f00'),
          ('GSC / NRCan', ('ca_gsc',), '#0072b2'),
          ('Canadian provinces\nand territories', ('ca_',), '#56b4e9'),
          ('USGS', ('us_usgs',), '#009e73'),
          ('Alaska DGGS', ('us_ak',), '#00544a'),
          ('GEUS', ('gl_geus',), '#cc79a7'),
          ('Nordic surveys\n(NGU, SGU, GTK,\nNÍ, NPI, FO)', ('no_', 'se_', 'fi_', 'is_', 'sj_', 'fo_'), '#f0e442'),
          ('Research maps\n(AWI, PANGAEA)', ('ru_veremeeva', 'ru_lena', 'ru_kytalyk'), '#8c564b')]
AGENCY_OTHER = '#999999'
LIC = [('open', 'Open licence', '#1b9e77'),
       ('open_sa', 'Open licence,\nshare-alike (CC BY-SA)', '#8cc1a2'),     # GEUS, 2026-10-08
       ('internal_only', 'Internal use only\n(permission or legal\nreview pending)', '#d95f02'),
       ('unknown', 'Terms not yet\nestablished', '#e6ab02')]
PF = [('continuous', 'Continuous'), ('discontinuous', 'Discontinuous'), ('sporadic', 'Sporadic'),
      ('isolated', 'Isolated patches'), ('none', 'Outside the zones')]
PF_COL = {z: c for z, _, c in A.PF_ZONES}
PF_COL['none'] = A.NO_PF
HC_ORDER = [c for _, cls in A.GROUPS for c in cls] + ['H', 'U']
# short class names where a legend column is narrow (fig_permafrost); full names in Fig. 1 and the caption
SHORT = {'F': 'Fluvial, deltaic', 'C': 'Colluvial', 'W': 'Residual', 'Y': 'Ice complex', 'R': 'Bedrock',
         'Q': 'Quat. undivided', 'I': 'Glacier ice', 'T': 'Till', 'M': 'Marine', 'K': 'Thermokarst', 'E': 'Eolian',
         'O': 'Organic', 'V': 'Volcanic', 'X': 'Anthropogenic'}


SC_BOUNDS = [c[0] for c in A.SCALE_CLASSES]    # source-scale classes of the A0 reliability diagram (1..5)
KEYS = ['decade', 'agency', 'lic', 'scale', 'pf_zone', 'yedoma', 'hclass']


def agency_code(src):
    if src is None or src == 'none' or src == '':
        return 0
    for i, (_, prefs, _) in enumerate(AGENCY):
        if src.startswith(prefs):
            return i + 1
    return len(AGENCY) + 1


def decade_code(years):
    y = pd.to_numeric(pd.Series(years), errors='coerce').astype('float64').to_numpy()     # Int64 NA -> NaN
    out = np.full(len(y), len(DECADES) + 1, np.uint8)                  # unknown year
    for i, (a, b, _) in enumerate(DECADES):
        out[(y >= a) & (y <= b)] = i + 1
    return out


LGM_SHP = f'{A.BM}/lgm/LGM_best_estimate.shp'    # Batchelor et al. (2019), OSF 7jen3: best-estimate LGM ice extent
_LGM = {}


def _lgm():
    """LGM ice extent as one prepared geometry in EPSG:6931 (None until the shapefile is downloaded)"""
    if 'g' not in _LGM:
        g = None
        if os.path.exists(LGM_SHP):
            d = gpd.read_file(LGM_SHP).to_crs(6931)
            g = shapely.union_all(shapely.make_valid(d.geometry.values[d.geometry.notna().values]), grid_size=1.0)
            shapely.prepare(g)
        _LGM['g'] = g
    return _LGM['g']


def one(f):
    """rasterise one 100 km tile (window of the global grid) + area sums by attribute combination"""
    tid = os.path.basename(f)[:-8]
    tx, ty = (int(v) * 1000 for v in tid.split('_'))
    g = gpd.read_parquet(f, columns=['geometry', 'src_id', 'hclass', 'pub_year', 'redistribution', 'pf_zone',
                                     'yedoma', 'area_km2', 'scale_den'])
    if g.empty:
        return None
    s = lambda c, d: g[c].astype('string').fillna(d).to_numpy(dtype=object)   # noqa: E731  numpy, not StringArray
    hc, src, red, pfz, yed = s('hclass', 'U'), s('src_id', 'none'), s('redistribution', 'unknown'), \
        s('pf_zone', 'none'), s('yedoma', '')
    na = (hc == 'U') | (src == 'none')
    dec = decade_code(g['pub_year'].values)
    ag = np.array([agency_code(x) for x in src], np.uint8)
    lic = np.array([next((i + 1 for i, (k, _, _) in enumerate(LIC) if k == r), len(LIC)) for r in red], np.uint8)
    dec[na], ag[na], lic[na] = NOTMAP, NOTMAP, NOTMAP
    pf = np.array([next((i + 1 for i, (k, _) in enumerate(PF) if k == z), len(PF)) for z in pfz], np.uint8)
    pf[hc == 'I'] = 9                                                   # glaciers / ice sheet drawn white
    pf[yed == 'yes'] = 10                                               # Yedoma on top
    hcode = np.array([HC_ORDER.index(h) + 1 if h in HC_ORDER else len(HC_ORDER) for h in hc], np.uint8)
    sd = pd.to_numeric(g['scale_den'], errors='coerce').astype('float64').fillna(1e13).to_numpy()
    sc = np.minimum(np.searchsorted(SC_BOUNDS, sd, side='left') + 1, len(SC_BOUNDS)).astype(np.uint8)
    sc[na] = NOTMAP
    q = shapely.force_2d(g.geometry.values)
    area = pd.to_numeric(g['area_km2'], errors='coerce').astype('float64').fillna(0.0).to_numpy()
    lgm = np.zeros(len(g))                                              # km2 inside the LGM ice limit (if available)
    lg = _lgm()
    if lg is not None:
        box = shapely.box(tx, ty, tx + TILE, ty + TILE)
        if lg.intersects(box):
            piece = shapely.intersection(lg, box)
            if piece.covers(box):
                lgm = area.copy()
            elif not piece.is_empty:
                lgm = shapely.area(shapely.intersection(q, piece)) / 1e6
    stats = pd.DataFrame({'decade': dec, 'agency': ag, 'lic': lic, 'scale': sc, 'pf_zone': pfz, 'yedoma': yed,
                          'hclass': hc, 'area_km2': area, 'lgm_km2': lgm})
    stats = stats.groupby(KEYS, as_index=False)[['area_km2', 'lgm_km2']].sum()
    if tx >= X1 or tx + TILE <= X0 or ty >= Y1 or ty + TILE <= Y0:
        return None, None, None, stats
    tr = Affine(RES, 0, tx, 0, -RES, ty + TILE)
    arrs = {}
    for k, v in (('dec', dec), ('ag', ag), ('lic', lic), ('pf', pf), ('hc', hcode), ('sc', sc)):
        a = np.zeros((NT, NT), np.uint8)
        try:
            rasterio.features.rasterize([(p, int(c)) for p, c in zip(q, v) if p is not None and not p.is_empty],
                                        out=a, transform=tr)
        except ValueError:                                              # no valid geometry in the tile
            pass
        arrs[k] = a
    r0, c0 = int(round((Y1 - (ty + TILE)) / RES)), int(round((tx - X0) / RES))
    return r0, c0, arrs, stats


def build():
    files = sorted(glob.glob(f'{TD}/*.parquet'))
    print(TD, len(files), 'tiles', flush=True)
    G = {k: np.zeros((NY, NX), np.uint8) for k in ('dec', 'ag', 'lic', 'pf', 'hc', 'sc')}
    parts = []
    with Pool(int(os.environ.get('SLURM_CPUS_PER_TASK', '8'))) as pool:
        for i, res in enumerate(pool.imap_unordered(one, files, chunksize=4)):
            if res is None:
                continue
            r0, c0, arrs, stats = res
            parts.append(stats)
            if arrs is None:
                continue
            rr0, cc0, rr1, cc1 = max(r0, 0), max(c0, 0), min(r0 + NT, NY), min(c0 + NT, NX)
            if rr1 <= rr0 or cc1 <= cc0:
                continue
            for k, a in arrs.items():
                sub = a[rr0 - r0:rr1 - r0, cc0 - c0:cc1 - c0]
                dst = G[k][rr0:rr1, cc0:cc1]
                m = sub > 0
                dst[m] = sub[m]
            if i % 500 == 0:
                print(i, flush=True)
    st = pd.concat(parts).groupby(KEYS, as_index=False)[['area_km2', 'lgm_km2']].sum()
    G['land'] = A.land_mask(A.FRAME, RES).astype(np.uint8)
    if _lgm() is not None:                                              # LGM ice limit on the grid, for the map
        m = np.zeros((NY, NX), np.uint8)
        rasterio.features.rasterize([(_lgm(), 1)], out=m, transform=Affine(RES, 0, X0, 0, -RES, Y1))
        G['lgm'] = m
    return G, st


# ------------------------------------------------------------------ drawing
def style():
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['DejaVu Sans'], 'font.size': 7,
                         'axes.linewidth': 0.5, 'xtick.major.width': 0.5, 'ytick.major.width': 0.5,
                         'xtick.major.size': 2, 'ytick.major.size': 0, 'pdf.fonttype': 42,
                         'savefig.facecolor': 'white'})


def graticule():
    out = []
    lons = np.linspace(-180, 180, 721)
    for lat in (50, 60, 70, 80):
        out.append(np.c_[lons, np.full_like(lons, lat)])
    for lon in range(-180, 180, 30):
        out.append(np.c_[np.full(60, lon), np.linspace(45, 89.5, 60)])
    s = gpd.GeoSeries([shapely.LineString(c) for c in out], crs=4326).to_crs(6931)
    return [shapely.get_coordinates(x) for x in s.values]


def rgb_of(code, land, colours):
    """colours: {code: hex}; 0 = sea or land outside the domain"""
    rgb = np.empty(code.shape + (3,))
    rgb[:] = A.hex2rgb(SEA)
    rgb[(land > 0) | (code > 0)] = A.hex2rgb(PAPER)
    for c, col in colours.items():
        rgb[code == c] = A.hex2rgb(col)
    return rgb


def map_axes(fig, rect, rgb, coast, grat, label):
    ax = fig.add_axes(rect)
    ax.imshow(rgb, extent=(X0, X1, Y0, Y1), interpolation='nearest', zorder=1)
    ax.add_collection(LineCollection(grat, colors=GRAT, linewidths=0.25, linestyles=(0, (2, 2)), zorder=2))
    ax.add_collection(LineCollection(coast, colors=COAST, linewidths=0.3, zorder=3))
    ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1); ax.set_aspect('equal')
    ax.set_xticks([]); ax.set_yticks([])
    ax.text(0.012, 0.985, label, transform=ax.transAxes, fontweight='bold', fontsize=8, va='top', ha='left')
    return ax


def bars(fig, rect, labels, values, colours, label, unit='M km²', total=None):
    """horizontal bars that double as the legend; value + share at the end of each bar"""
    ax = fig.add_axes(rect)
    y = np.arange(len(labels))[::-1]
    ax.barh(y, values, color=colours, edgecolor='#444444', linewidth=0.3, height=0.72)
    total = total or float(np.sum(values))
    vmax = max(values) if len(values) else 1
    for yy, v in zip(y, values):
        ax.text(v + 0.02 * vmax, yy, f'{v:.2f} ({100 * v / total:.0f} %)' if total else f'{v:.2f}', va='center',
                fontsize=6)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=6.5)
    ax.set_xlim(0, vmax * 1.55)
    ax.set_xlabel(unit, fontsize=6.5)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.tick_params(axis='x', labelsize=6)
    ax.text(-0.02, 1.0, label, transform=ax.transAxes, fontweight='bold', fontsize=8, va='bottom', ha='right')
    return ax


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    for ext, kw in (('png', dict(dpi=300)), ('pdf', {})):
        fig.savefig(f'{OUT}/{name}.{ext}', metadata={'Author': 'Hugues Lantuit'}, **kw)
    plt.close(fig)
    print('wrote', f'{OUT}/{name}.png/.pdf', flush=True)


W_MM, H_MM = 170.0, 97.0
MAP_RECT = [0.004, 2.0 / H_MM, 0.64, 0.64 * W_MM / H_MM * (Y1 - Y0) / (X1 - X0)]   # 108.8 x 93.1 mm, 2 mm margins


def fig_age(G, st, coast, grat):
    fig = plt.figure(figsize=(W_MM / 25.4, H_MM / 25.4))
    cols = {i + 1: c for i, c in enumerate(DEC_COL)}
    cols[len(DECADES) + 1] = YEAR_UNKNOWN
    cols[NOTMAP] = NOTMAP_C
    map_axes(fig, MAP_RECT, rgb_of(G['dec'], G['land'], cols), coast, grat, '(a)')
    a = st.groupby('decade')['area_km2'].sum() / 1e6
    keys = list(range(1, len(DECADES) + 2)) + [NOTMAP]
    labs = [d[2] for d in DECADES] + ['year unknown', 'not mapped']
    bars(fig, [0.80, 0.12, 0.17, 0.82], labs, [float(a.get(k, 0.0)) for k in keys], [cols[k] for k in keys], '(b)')
    save(fig, 'fig_age')


def fig_agency(G, st, coast, grat):
    fig = plt.figure(figsize=(W_MM / 25.4, H_MM / 25.4))
    cols = {i + 1: c for i, (_, _, c) in enumerate(AGENCY)}
    cols[len(AGENCY) + 1] = AGENCY_OTHER
    cols[NOTMAP] = NOTMAP_C
    map_axes(fig, MAP_RECT, rgb_of(G['ag'], G['land'], cols), coast, grat, '(a)')
    a = st.groupby('agency')['area_km2'].sum() / 1e6
    keys = [k for k in list(range(1, len(AGENCY) + 2)) + [NOTMAP] if a.get(k, 0) > 0]
    names = {i + 1: n for i, (n, _, _) in enumerate(AGENCY)}
    names.update({len(AGENCY) + 1: 'other', NOTMAP: 'not mapped'})
    bars(fig, [0.80, 0.12, 0.17, 0.82], [names[k] for k in keys], [float(a[k]) for k in keys],
         [cols[k] for k in keys], '(b)')
    save(fig, 'fig_agency')


def fig_licence(G, st, coast, grat):
    fig = plt.figure(figsize=(W_MM / 25.4, H_MM / 25.4))
    cols = {i + 1: c for i, (_, _, c) in enumerate(LIC)}
    cols[NOTMAP] = NOTMAP_C
    map_axes(fig, MAP_RECT, rgb_of(G['lic'], G['land'], cols), coast, grat, '(a)')
    a = st.groupby('lic')['area_km2'].sum() / 1e6
    keys = [k for k in list(range(1, len(LIC) + 1)) + [NOTMAP] if a.get(k, 0) > 0]
    names = {i + 1: n for i, (_, n, _) in enumerate(LIC)}
    names[NOTMAP] = 'not mapped'
    bars(fig, [0.80, 0.30, 0.17, 0.45], [names[k] for k in keys], [float(a[k]) for k in keys],
         [cols[k] for k in keys], '(b)')
    save(fig, 'fig_licence')


def fig_permafrost(G, st, coast, grat):
    """taller than the others (122 mm): zone legend under the map, class legend under the bars"""
    h_mm = 122.0
    fig = plt.figure(figsize=(W_MM / 25.4, h_mm / 25.4))
    map_h = 0.64 * W_MM * (Y1 - Y0) / (X1 - X0)                        # 93.1 mm
    cols = {i + 1: PF_COL[z] for i, (z, _) in enumerate(PF)}
    cols[9], cols[10] = A.INSET_ICE, A.PAL['Y']
    map_axes(fig, [0.004, (h_mm - 2 - map_h) / h_mm, 0.64, map_h / h_mm], rgb_of(G['pf'], G['land'], cols), coast,
             grat, '(a)')
    lg = fig.add_axes([0.004, 0.005, 0.64, (h_mm - 6 - map_h) / h_mm])
    lg.set_axis_off(); lg.set_xlim(0, 4); lg.set_ylim(0, 2)
    zone_items = [(n, PF_COL[z]) for z, n in PF] + [('Glaciers, ice sheet', A.INSET_ICE),
                                                       ('Yedoma (IRYP v2: yes)', A.PAL['Y'])]
    for k, (n, c) in enumerate(zone_items):
        xx, yy = k % 4, 1.75 - (k // 4) * 0.9
        lg.add_patch(plt.Rectangle((xx + 0.02, yy - 0.3), 0.13, 0.5, fc=c, ec='#444444', lw=0.3))
        lg.text(xx + 0.2, yy - 0.05, n, va='center', fontsize=6.5)
    # (b) class composition (share of area) of each zone and of the IRYP Yedoma domain
    rows = [(n, st['pf_zone'] == z) for z, n in PF] + [('IRYP Yedoma (yes)', st['yedoma'] == 'yes')]
    comp = pd.DataFrame({n: st[m].groupby('hclass')['area_km2'].sum() for n, m in rows}).T.fillna(0.0)
    tot = comp.sum(axis=1)
    frac = comp.div(tot.replace(0, np.nan), axis=0).fillna(0.0)
    hcs = [h for h in HC_ORDER if h in frac.columns and frac[h].max() > 0]
    ax = fig.add_axes([0.80, 0.55, 0.17, 0.42])
    y = np.arange(len(frac))[::-1]
    left = np.zeros(len(frac))
    for h in hcs:
        ax.barh(y, frac[h].values, left=left, color=A.PAL[h], edgecolor='#444444', linewidth=0.2, height=0.72)
        left += frac[h].values
    ax.set_yticks(y)
    ax.set_yticklabels([f'{n}\n{tot[n] / 1e6:.2f} M km²' for n in frac.index], fontsize=6)
    ax.set_xlim(0, 1); ax.set_xticks([0, 0.5, 1]); ax.set_xticklabels(['0', '50', '100 %'], fontsize=6)
    for sp in ('top', 'right'):
        ax.spines[sp].set_visible(False)
    ax.text(-0.02, 1.0, '(b)', transform=ax.transAxes, fontweight='bold', fontsize=8, va='bottom', ha='right')
    cl = fig.add_axes([0.655, 0.01, 0.345, 0.47])
    cl.set_axis_off(); cl.set_xlim(0, 2); cl.set_ylim(0, 10.5)
    for k, hh in enumerate(hcs):
        xx, yy = k // 10, 10 - (k % 10)
        cl.add_patch(plt.Rectangle((xx + 0.01, yy - 0.3), 0.09, 0.6, fc=A.PAL[hh], ec='#444444', lw=0.3))
        cl.text(xx + 0.14, yy, SHORT.get(hh, A.NAMES[hh]), va='center', fontsize=6)
    save(fig, 'fig_permafrost')


GLACIAL = ['T', 'GF', 'GL', 'GM']
LGM_GROUPS = [('Till, morainal', ['T']), ('Glaciofluvial', ['GF']), ('Glaciolacustrine', ['GL']),
              ('Glaciomarine', ['GM']), ('Marine, littoral', ['M']), ('Fluvial, lacustrine,\nthermokarst', ['F', 'L', 'K']),
              ('Eolian', ['E']), ('Ice complex (yedoma)', ['Y']), ('Colluvial, residual', ['C', 'W']),
              ('Organic', ['O']), ('Bedrock', ['R']), ('Quaternary undivided', ['Q'])]
MUTED = '#d6d0c4'                               # darker than PAPER: the mapped domain stays visible


def fig_lgm(G, st, coast, grat):
    """(a) glacial and marine classes in colour, the rest muted, LGM ice limit (Batchelor et al. 2019) as a line;
    (b) share of each class group's area inside that limit: a check of the harmonised classes against an independent
    reconstruction (pre-LGM glaciations leave glacial deposits outside it, so it is a check, not a test)"""
    lg = _lgm()
    if lg is None or 'lgm' not in G or st['lgm_km2'].sum() == 0:
        print('fig_lgm skipped: no LGM extent (download', LGM_SHP, 'and rerun with --fresh)', flush=True)
        return
    fig = plt.figure(figsize=(W_MM / 25.4, H_MM / 25.4))
    cols = {k: MUTED for k in range(1, len(HC_ORDER) + 1)}
    cols.update({HC_ORDER.index(h) + 1: A.PAL[h] for h in GLACIAL + ['M']})
    cols[HC_ORDER.index('I') + 1] = A.INSET_ICE
    cols[HC_ORDER.index('H') + 1] = A.PAL['H']
    cols[HC_ORDER.index('U') + 1] = NOTMAP_C
    ax = map_axes(fig, MAP_RECT, rgb_of(G['hc'], G['land'], cols), coast, grat, '(a)')
    lines = A._lines([shapely.intersection(shapely.boundary(lg), shapely.box(X0, Y0, X1, Y1))])
    ax.add_collection(LineCollection(lines, colors='#1f3b57', linewidths=0.7, zorder=4))
    rows = []
    for name, cls in LGM_GROUPS:
        m = st['hclass'].isin(cls)
        rows.append((name, float(st.loc[m, 'area_km2'].sum()), float(st.loc[m, 'lgm_km2'].sum()), A.PAL[cls[0]]))
    rows = [r for r in rows if r[1] > 0]
    b = fig.add_axes([0.80, 0.14, 0.17, 0.82])
    y = np.arange(len(rows))[::-1]
    pct = [100 * i / a for _, a, i, _ in rows]
    b.barh(y, pct, color=[c for *_, c in rows], edgecolor='#444444', linewidth=0.3, height=0.72)
    for yy, p in zip(y, pct):
        b.text(p + 2, yy, f'{p:.0f} %', va='center', fontsize=6)
    b.set_yticks(y)
    b.set_yticklabels([f'{n}\n{a / 1e6:.2f} M km²' for n, a, _, _ in rows], fontsize=6)
    b.set_xlim(0, 115); b.set_xticks([0, 50, 100])
    b.set_xlabel('% of the area inside\nthe LGM ice limit', fontsize=6.5)
    for sp in ('top', 'right'):
        b.spines[sp].set_visible(False)
    b.tick_params(axis='x', labelsize=6)
    b.text(-0.02, 1.0, '(b)', transform=b.transAxes, fontweight='bold', fontsize=8, va='bottom', ha='right')
    save(fig, 'fig_lgm')


FIGS = {'fig_age': fig_age, 'fig_agency': fig_agency, 'fig_licence': fig_licence, 'fig_permafrost': fig_permafrost,
        'fig_lgm': fig_lgm}


DEGLAC = f'{A.BM}/deglac'                       # downloaded 2026-10-07 with H.L.'s approval (CC-BY)


def deglac_raster():
    """deglaciation age on the figure grid in half-ka units (uint8): the age of the YOUNGEST time slice whose ice
    still covered the pixel (it became ice-free between that slice and the next younger one). Slices: NADI-1
    'OPTIMAL' (Dalton et al. 2023: North America, 25-1 ka every 0.5 ka) and DATED-1 'most credible' (Hughes et al.
    2016: Eurasia, 25-10 ka every 1 ka). 0 = under ice in no slice: ice-free since before 25 ka, OR not
    reconstructed (Greenland is in neither; PaleoGrIS not downloaded)."""
    import re
    slices = []
    for p in glob.glob(f'{DEGLAC}/nadi1/*/*ka_cal_OPTIMAL_NADI-1_Dalton_etal_QSR.shp'):
        slices.append((float(os.path.basename(p).split('ka_cal')[0]), p))
    for p in glob.glob(f'{DEGLAC}/dated1/*/TS*_mc.shp'):
        m = re.match(r'TS(\d+)_mc\.shp$', os.path.basename(p))
        if m:
            slices.append((float(m.group(1)), p))
    out = np.zeros((NY, NX), np.uint8)
    tr = Affine(RES, 0, X0, 0, -RES, Y1)
    import pyogrio
    for t, p in sorted(slices, key=lambda s: -s[0]):                 # oldest first: younger slices overwrite
        # raw WKB + on_invalid='fix': some isochrone rings are not closed (GEOS refused to build them, 2026-10-07)
        meta, _, wkb, _ = pyogrio.raw.read(p, read_geometry=True)
        geoms = shapely.from_wkb(wkb, on_invalid='fix')
        g = gpd.GeoSeries(geoms[[q is not None for q in geoms]], crs=meta['crs']).to_crs(6931)
        parts = shapely.get_parts(shapely.make_valid(shapely.force_2d(g.values)))
        polys = [q for q in parts if q.geom_type in ('Polygon', 'MultiPolygon') and not q.is_empty]
        if polys:
            m = np.zeros((NY, NX), np.uint8)
            rasterio.features.rasterize([(q, 1) for q in polys], out=m, transform=tr)
            out[m > 0] = int(round(2 * t))
    print('deglaciation slices', len(slices), 'pixels with an age', int((out > 0).sum()), flush=True)
    return out


def export_bundle(G, st, path):
    """rasters + vector lines (coast, graticule, AMAP limit, LGM limit) + the code definitions, so the figures can be
    drawn without the GIS stack (scripts/essd/essd_draw.py on the laptop, with the fonts installed there)"""
    import json

    def pack(lines):
        if not lines:
            return np.zeros((0, 2), np.float32), np.zeros(1, np.int64)
        return np.concatenate(lines).astype(np.float32), np.cumsum([0] + [len(c) for c in lines]).astype(np.int64)
    lg = _lgm()
    vec = {'coast': A._coast(A.FRAME, tol=1000.0), 'grat': graticule(), 'amap': A._amap_lines(A.FRAME, tol=1000.0),
           'lgm': A._lines([shapely.intersection(shapely.boundary(lg), shapely.box(X0, Y0, X1, Y1))]) if lg is not None
           else []}
    out = {f'r_{k}': v for k, v in G.items()}
    if os.path.isdir(DEGLAC):
        out['r_deg'] = deglac_raster()
    for k, lines in vec.items():
        out[f'v_{k}_xy'], out[f'v_{k}_idx'] = pack(lines)
    meta = dict(frame=list(A.FRAME), res=RES, notmap=NOTMAP, pal=A.PAL, names=A.NAMES, groups=A.GROUPS,
                scale_classes=[[float(c[0]), c[1], c[2]] for c in A.SCALE_CLASSES], pf_zones=A.PF_ZONES,
                no_pf=A.NO_PF, inset_ice=A.INSET_ICE, decades=DECADES, agency=[[a[0], list(a[1]), a[2]] for a in AGENCY],
                lic=LIC, pf=PF, hc_order=HC_ORDER, short=SHORT, glacial=GLACIAL, lgm_groups=LGM_GROUPS)
    out['meta'] = np.array(json.dumps(meta))
    np.savez_compressed(path, **out)
    st.to_csv(path.replace('.npz', '.csv'), index=False)
    print('bundle', path, {k: len(v) for k, v in vec.items()}, flush=True)


def main():
    os.makedirs(TAB, exist_ok=True)
    # the cached rasters and sums hold CODES (decade bin, agency group, ...): the key carries the definitions, so a
    # re-binning cannot be drawn with the old codes (2026-10-07: 'before 1960' -> 'before 1970' shifted every label)
    import hashlib
    key = hashlib.md5(repr((DECADES, [a[1] for a in AGENCY], LIC, PF, HC_ORDER, LGM_SHP, SC_BOUNDS, KEYS)).encode()).hexdigest()[:6]
    cache = f'{TAB}/maps_rasters_{TNAME}_{key}.npz'
    tab = f'{TAB}/maps_area_{TNAME}_{key}.csv'
    if os.path.exists(cache) and os.path.exists(tab) and '--fresh' not in sys.argv:
        z = np.load(cache)
        G, st = {k: z[k] for k in z.files}, pd.read_csv(tab, keep_default_na=False)
        for c in ('decade', 'agency', 'lic', 'scale'):
            st[c] = st[c].astype(int)
        if 'lgm_km2' not in st:
            st['lgm_km2'] = 0.0
    else:
        G, st = build()
        np.savez_compressed(cache, **G)
        st.to_csv(tab, index=False)
    print('area total', round(st['area_km2'].sum() / 1e6, 3), 'M km2', flush=True)
    if '--export' in sys.argv:                      # for essd_draw.py (house style, drawn on the laptop)
        export_bundle(G, st, f'{TAB}/maps_bundle_{TNAME}_{key}.npz')
        return
    style()
    coast, grat = A._coast(A.FRAME, tol=1000.0), graticule()
    only = next((a.split('=', 1)[1].split(',') for a in sys.argv if a.startswith('--only=')), list(FIGS))
    for name in only:
        FIGS[name](G, st, coast, grat)


if __name__ == '__main__':
    main()
