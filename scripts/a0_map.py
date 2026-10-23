#!/usr/bin/env python
"""A0 wall map of the pan-Arctic surficial geology (design requested by H. Lantuit 2026-10-06: beautiful, readable, the
geology is the star, subtle hillshade, places / roads, a little in the spirit of old maps, QR code to the PANGAEA DOI).

Layout: A0 landscape (1189 x 841 mm), Lambert azimuthal equal-area centred on the North Pole (EPSG:6931, Greenwich
down), 1:10 000 000: map face 900 x 770 mm (x -4500..4500 km, y -3400..4300 km), side panel ~250 mm.
Layers (bottom up):
  ocean      ETOPO 2022 30" bathymetry, pale blue ramp + soft hillshade
  land       out-of-domain land: paper tone + hillshade; domain: hclass colours (rasterised at 2x, averaged = anti-aliased
             unit edges), yedoma (IRYP v2 'yes') as a fine hatch, hillshade multiplied (subtle)
  vectors    coast, lakes, rivers, roads, railways, graticule (10 deg / 30 deg), Arctic Circle, places, sea / region names
Fonts: P052 (Palatino) / C059 (Century Schoolbook), on Albedo.

usage: a0_map.py mockup|sheetmock <name> <cx_km> <cy_km> <w_mm> <h_mm> [--tiles DIR]   true-scale crop, 300 dpi PNG
       a0_map.py layout [--dpi 30] [--tiles DIR] [--pdf]                             whole sheet (PNG preview or print PDF)
  options: --halo MM (label halo width, 0 = none; default 0.2)  --outline A (contact-line opacity, 0 = none; 0.5)
           --tag T (suffix of the output name)
           --doi-data DOI / --doi-paper DOI (the two QR codes: PANGAEA dataset, ESSD paper; placeholders by default)
           --dry (layout test: blank map face, real panel insets)  --fresh (recompute the cached rasters)"""
import glob
import os
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import rasterio  # noqa: E402
import rasterio.features  # noqa: E402
from rasterio.warp import reproject, Resampling  # noqa: E402
from affine import Affine  # noqa: E402
import shapely  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
BM = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/basemap'
ETOPO = f'{BM}/ETOPO_2022_v1_30s_N90W180_surface.tif'
NE = f'{BM}/ne'
NE_LAND = '/albedo/work/user/hlantuit/arcticbeach/data/naturalearth/ne_10m_land'
OUTD = f'{ROOT}/out/a0'
SCALE = 10_000_000
MM = 1e-3 * SCALE                                   # metres on the ground per mm on paper (10 km)
FRAME = (-4_500_000, -3_400_000, 4_500_000, 4_300_000)

# hclass palette (H. Lantuit 2026-10-07): GSC Surficial Data Model legend chart v2.5.1 (Deblonde et al., GSC Open File
# 8236, 2024, Appendix B), the swatch of each category's undifferentiated unit, read from the vector PDF. Adapted for a
# 1:10M wall map:
#   - bedrock: SDM R #f6989e lightened 30 % toward white;
#   - residual: the SDM veneer tint Wv #db918b instead of W #ce6c6c (1.7M km2 of Siberian uplands in full red);
#   - classes the SDM lacks: Y ice complex (tawny), K thermokarst (pale teal, apart from the lacustrine lavender),
#     H water (pale blue).
# The earlier ArcSurf v5 palette is PALETTES['arcsurf_v5'].
PAL = {'F': '#fffac2', 'T': '#c8ddbd', 'GF': '#fecf8c', 'GL': '#d5b5c9', 'GM': '#77bbe7', 'M': '#aae1fa',
       'L': '#afacd5', 'K': '#a3d1c4', 'Y': '#dfa36f', 'E': '#d6c36b', 'C': '#f0cfc0', 'W': '#db918b',
       'O': '#d2d3d5', 'V': '#ae6882', 'X': '#c18b8a', 'I': '#ffffff', 'Q': '#d8c6c0', 'H': '#cfe8f3',
       'R': '#f9b7bb', 'U': '#efeee9'}
PAL_NOTE = ('Class colours after the GSC Surficial Data Model legend v2.5.1 (Deblonde et al. 2024); bedrock and residual '
            'lightened; ice complex, thermokarst and water added.')
NAMES = {'F': 'Fluvial, alluvial, deltaic', 'T': 'Till, morainal', 'GF': 'Glaciofluvial', 'GL': 'Glaciolacustrine',
         'GM': 'Glaciomarine', 'M': 'Marine, littoral', 'L': 'Lacustrine', 'K': 'Thermokarst, alas',
         'Y': 'Ice complex (yedoma)', 'E': 'Eolian, loess', 'C': 'Colluvial, mass wasting', 'W': 'Residual, weathered',
         'O': 'Organic (peat)', 'V': 'Quaternary volcanic', 'X': 'Anthropogenic', 'I': 'Glaciers, ice sheet',
         'Q': 'Quaternary undivided', 'H': 'Water', 'R': 'Bedrock (pre-Quaternary)', 'U': 'Not mapped'}
CODES = {c: i + 1 for i, c in enumerate(PAL)}
# alternative palettes (--palette). 'sdm': GSC Surficial Data Model legend chart v2.5.1 (Deblonde et al., GSC Open File
# 8236, 2024, Appendix B), the swatch of each category's undifferentiated unit, read from the vector PDF; classes the
# SDM lacks (K thermokarst, Y ice complex, H water) chosen to fit. 'vsegei': medoid printed colour per class over the
# ~500 VSEGEI legends we sampled (work_local/a0/class_colours_by_survey.csv); Q and U kept.
PALETTES = {
    'arcsurf_v5': {'F': '#f4e8a6', 'T': '#d4b58a', 'GF': '#ecb9a1', 'GL': '#b3c2ea', 'GM': '#a6cbc6', 'M': '#92c1cf',
                   'L': '#b4d9ea', 'K': '#a9dccb', 'Y': '#db9a68', 'E': '#f2d07c', 'C': '#c2ab8d', 'W': '#ddd2bf',
                   'O': '#9fb586', 'V': '#b85c50', 'X': '#a6a6a6', 'I': '#fbfdff', 'Q': '#e6dfcf', 'H': '#b4d9ea',
                   'R': '#c9c2ba', 'U': '#efeee9'},
    'sdm': {'T': '#c8ddbd', 'GF': '#fecf8c', 'GL': '#d5b5c9', 'GM': '#77bbe7', 'M': '#aae1fa', 'F': '#fffac2',
            'L': '#afacd5', 'E': '#d6c36b', 'C': '#f0cfc0', 'W': '#ce6c6c', 'O': '#d2d3d5', 'V': '#ae6882',
            'X': '#c18b8a', 'I': '#ffffff', 'Q': '#d8c6c0', 'R': '#f6989e', 'K': '#bfa8d9', 'Y': '#dfa36f',
            'H': '#cfe8f3', 'U': '#efeee9'},
    'vsegei': {'F': '#cde4aa', 'T': '#d29b71', 'GF': '#b8c57f', 'GL': '#7accc8', 'GM': '#af8fba', 'M': '#8cb5df',
               'L': '#93ccc5', 'K': '#94edcf', 'Y': '#ffd38e', 'E': '#f4e3a0', 'C': '#eea086', 'W': '#eca4af',
               'O': '#d2ccb2', 'V': '#b2cb8e', 'X': '#bec0c2', 'I': '#f4f8fb', 'R': '#a677b4', 'H': '#cfe8f3',
               'Q': '#e6dfcf', 'U': '#efeee9'},
}
PAPER = np.array([0.965, 0.955, 0.93])            # out-of-domain land / margins
SEA_SHALLOW, SEA_DEEP = np.array([0.845, 0.905, 0.935]), np.array([0.655, 0.765, 0.835])
INK = '#3b3a36'
WATER_INK = '#4f7f9f'
CONTACT_INK, ICE_INK = '#4a3b2c', '#7f97ad'
# rendering options (CLI): label halo width in mm (0 = none), contact-line opacity (0 = no contacts)
OPT = {'halo': 0.2, 'outline': 0.5}

# A0 review of 2026-10-22 (H.L.): water names the map does not need (matched on a normalised name with a little
# tolerance for spelling; the render log lists every entry that matched nothing), the size of the ocean and sea names,
# and region names to add
DROP_NAMES = [
    'Columbia River', 'Salish Sea', 'Smith Sound', 'Queen Charlotte Sound', 'Dixon Entrance', 'Cordova Bay',
    'Prince William Sound', 'Cook Inlet', 'Gulf of Kamchatka', 'Kronotskiy Gulf', 'Uchiura Bay', 'La Perouse Strait',
    'Tatar Strait', 'Gulf of Sakhalin', 'Philippine Sea', 'Inner Sea', 'Chaun Bay', 'Dmitriy Laptev Strait',
    'Gulf of Yana', 'Yana Bay', 'Guba Gusinaya', 'Ozero Mogotoyevo', 'Gulf of Olenek', 'Olenek Gulf',
    'Vilkitskogo Strait', 'Yenisey Gulf', 'Gulf of Ob', 'Matochkin Shar Strait', 'Karskiye Strait',
    'Karskiye Vorota Strait', 'Storfjorden', 'Gulf of Bothnia', 'Gulf of Finland', 'Vestfjorden', 'Trondheimsfjorden',
    'Skagerrak', 'Ogneffjorden', 'Ofotfjorden', 'Garabogaz Bay', 'Strait of Belle Isle', 'Saint Lawrence River',
    "Bras d'Or Lake", 'Bay of Fundy', 'Hudson Strait', 'Eclipse Sound', 'Fury and Hecla Strait', 'Jones Sound',
    'The North Western Passages', 'Wager Bay', 'Gulf of Boothia', 'Bathurst Inlet', 'Minto Inlet', 'Prince Albert Sound',
    "M'Clure Strait", 'Richard Collinson Inlet', 'Wynniatt Bay', 'Viscount Melville Sound', 'Liddon Gulf',
    'Goldsmith Channel', 'Franklin Bay', 'Darnley Bay', 'Husky Lakes', 'Mackenzie Bay', 'Melville Bay', 'Murchison Sound',
    'Kane Basin', 'Kennedy Channel', 'Robeson Channel', 'North Magnetic Pole', 'Magnetic Pole', 'Magnetic North Pole']
OCEANS = ['Arctic Ocean', 'North Atlantic Ocean', 'North Pacific Ocean']
MAIN_SEAS = ['Barents Sea', 'Kara Sea', 'Laptev Sea', 'East Siberian Sea', 'Chukchi Sea', 'Beaufort Sea', 'Bering Sea',
             'Sea of Okhotsk', 'Hudson Bay', 'Baffin Bay', 'Greenland Sea', 'Norwegian Sea', 'Labrador Sea',
             'Lincoln Sea', 'Pechora Sea', 'White Sea', 'Gulf of Alaska', 'Baltic Sea', 'North Sea', 'Sea of Japan',
             'Caspian Sea', 'Davis Strait', 'Foxe Basin']
# where a sea's name goes when its Natural Earth polygon reaches beyond the water the name means (lon, lat): the White
# Sea polygon takes in the funnel towards the Barents Sea, and the name sat at its mouth (A0 review, 22 Oct)
SEA_ANCHOR = {'White Sea': (37.0, 65.4)}
# (name, lon, lat, size pt, physical feature = italic); placed right after the sea names, before the towns
REGIONS = [('Greenland', -40.0, 72.5, 11.0, False), ('Alaska', -152.0, 64.5, 10.0, False),
           ('Iceland', -18.6, 64.9, 8.0, False), ('Svalbard', 16.5, 78.6, 7.0, False),
           ('Faroe Islands', -6.9, 62.05, 5.0, False), ('Novaya Zemlya', 56.0, 74.2, 6.5, True),
           ('Severnaya Zemlya', 97.5, 79.4, 6.5, True), ('New Siberian Islands', 141.0, 75.3, 6.5, True),
           ('Franz Josef Land', 54.0, 80.8, 6.5, True), ('Wrangel Island', -179.6, 71.25, 5.5, True),
           ('Ellesmere Island', -79.0, 79.8, 7.0, True), ('Baffin Island', -71.0, 68.5, 7.0, True),
           ('Victoria Island', -109.0, 71.0, 6.5, True), ('Banks Island', -121.5, 72.8, 6.0, True),
           ('Devon Island', -87.5, 75.2, 5.5, True), ('Southampton Island', -84.5, 64.5, 5.5, True),
           ('Mackenzie Delta', -135.0, 68.7, 5.5, True), ('Lena Delta', 126.3, 72.8, 5.5, True)]


def _norm(s):
    import unicodedata
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c)).lower()
    return ' '.join(re.sub(r"[^a-z0-9 ]+", ' ', s.replace("'", '')).split())


_DROP = {_norm(n) for n in DROP_NAMES}
_HIT = set()


def dropped(name):
    """True for a name of DROP_NAMES (exact after normalising, contained as whole words, e.g. a dated 'North Magnetic
    Pole (2015)', or close: SequenceMatcher ratio >= 0.88)"""
    import difflib
    n = _norm(name)
    for d in _DROP:
        if n == d or re.search(rf'\b{re.escape(d)}\b', n) or difflib.SequenceMatcher(None, n, d).ratio() >= 0.88:
            _HIT.add(d)
            return True
    return False


def fonts():
    # URW base35 OTFs copied into the project (compute nodes have no /usr/share/fonts/urw-base35)
    for f in glob.glob(f'{ROOT}/pylib/fonts/*.otf'):
        font_manager.fontManager.addfont(f)
    names = {f.name for f in font_manager.fontManager.ttflist}
    serif = 'P052' if 'P052' in names else 'DejaVu Serif'
    plt.rcParams.update({'font.family': 'serif', 'font.serif': [serif, 'C059', 'DejaVu Serif']})
    return serif


def hex2rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def grid(bounds, px):
    x0, y0, x1, y1 = bounds
    W, H = int(round((x1 - x0) / px)), int(round((y1 - y0) / px))
    return Affine(px, 0, x0, 0, -px, y1), (H, W)


def geology(bounds, px, tiles_dir, ss=2):
    """class codes + yedoma mask on the grid; rasterised at ss x and returned as RGB averaged back (anti-aliasing)"""
    tr, (H0, W0) = grid(bounds, px)             # the supersampled grid is derived from the print grid, so both have the
    tr2, shp2 = tr * Affine.scale(1 / ss), (H0 * ss, W0 * ss)     # same shape (rounding them separately can differ by 1 px)
    cls = np.zeros(shp2, np.uint8)
    yed = np.zeros(shp2, np.uint8)
    x0, y0, x1, y1 = bounds
    for f in sorted(glob.glob(f'{tiles_dir}/*.parquet')):
        tx, ty = (int(v) * 1000 for v in os.path.basename(f)[:-8].split('_'))
        if tx > x1 or tx + 100_000 < x0 or ty > y1 or ty + 100_000 < y0:
            continue
        g = gpd.read_parquet(f, columns=['geometry', 'hclass', 'yedoma'])
        g = g[shapely.intersects(g.geometry.values, shapely.box(*bounds))]
        if g.empty:
            continue
        shapes = [(q, CODES.get(h, CODES['U'])) for q, h in zip(shapely.force_2d(g.geometry.values), g['hclass'])]
        rasterio.features.rasterize(shapes, out=cls, transform=tr2, merge_alg=rasterio.enums.MergeAlg.replace)
        ys = g[g['yedoma'].astype('string').fillna('').isin(['yes'])]
        if len(ys):
            rasterio.features.rasterize([(q, 1) for q in shapely.force_2d(ys.geometry.values)], out=yed, transform=tr2)
    lut = np.zeros((len(CODES) + 1, 3))
    for c, i in CODES.items():
        lut[i] = hex2rgb(PAL[c])
    rgb = lut[cls]
    dom = (cls > 0).astype(float)
    H, W = shp2[0] // ss, shp2[1] // ss
    down = lambda a: a[:H * ss, :W * ss].reshape(H, ss, W, ss).mean((1, 3))      # noqa: E731
    rgb = rgb[:H * ss, :W * ss].reshape(H, ss, W, ss, 3).mean((1, 3))
    dom, yed = down(dom), down(yed)
    ice, qq = down((cls == CODES['I']).astype(float)), down((cls == CODES['Q']).astype(float))
    edges = contacts(cls, px / ss / MM) if OPT['outline'] > 0 and px / MM <= 0.2 else None
    if edges is not None:
        edges = {k: down(v.astype(np.float32)) for k, v in edges.items()}
    return rgb, dom, yed, ice, qq, edges


def mode_filter(cls, size):
    """majority class in a size x size window (sea / no data = 0 takes part, so coasts do not move)"""
    best = np.zeros(cls.shape, np.float32)
    out = np.zeros_like(cls)
    for k in np.unique(cls):
        c = ndi.uniform_filter((cls == k).astype(np.float32), size=size, mode='nearest')
        m = c > best
        best[m] = c[m]
        out[m] = k
    return out


def contacts(cls, mm_per_px, gen_mm=0.3):
    """hairline contacts between classes, on the supersampled grid (both sides of a change = 1 print pixel at 2x).
    Drawn from a majority-filtered copy, so units narrower than ~gen_mm/2 on paper keep their colour but get no
    outline (otherwise detailed areas turn into a grey felt of tiny rings). Returns masks: water (either side H),
    ice (either side I), geology (the rest); sea / out-of-domain borders are left to the coastline."""
    size = max(1, int(round(gen_mm / mm_per_px))) | 1
    m = mode_filter(cls, size) if size > 1 else cls
    e = {k: np.zeros(m.shape, bool) for k in ('geo', 'ice', 'water')}
    for a, b, sa, sb in ((m[:, 1:], m[:, :-1], np.s_[:, 1:], np.s_[:, :-1]),
                         (m[1:, :], m[:-1, :], np.s_[1:, :], np.s_[:-1, :])):
        d = (a != b) & (a > 0) & (b > 0)
        wat = d & ((a == CODES['H']) | (b == CODES['H']))
        ice = d & ~wat & ((a == CODES['I']) | (b == CODES['I']))
        geo = d & ~wat & ~ice
        for k, v in (('geo', geo), ('ice', ice), ('water', wat)):
            e[k][sa] |= v
            e[k][sb] |= v
    return e


def relief(bounds, px):
    """ETOPO 2022 elevation on the grid (bilinear) -> elevation, hillshade (0..1)"""
    tr, shp = grid(bounds, px)
    z = np.full(shp, np.nan, np.float32)
    with rasterio.open(ETOPO) as src:
        reproject(rasterio.band(src, 1), z, dst_transform=tr, dst_crs='EPSG:6931', resampling=Resampling.bilinear,
                  dst_nodata=np.nan)
    zz = np.nan_to_num(z, nan=0.0)
    gy, gx = np.gradient(zz, px)
    az, alt, zf = np.radians(315), np.radians(45), 3.0                 # light from the NW, exaggerated a little
    slope = np.arctan(zf * np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return z, np.clip(hs, 0, 1)


def land_mask(bounds, px):
    tr, shp = grid(bounds, px)
    g = _land()
    g = g[shapely.intersects(g.geometry.values, shapely.box(*bounds))]
    m = np.zeros(shp, np.uint8)
    if len(g):
        rasterio.features.rasterize([(q, 1) for q in g.geometry.values], out=m, transform=tr)
    return m.astype(bool)


def hatch(shape, px, spacing_mm=1.3, width_mm=0.18):
    """45-degree line pattern (1 = ink) at the print resolution"""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    s = spacing_mm * MM / px
    d = ((xx + yy) % s) / s
    return (d < (width_mm / spacing_mm)).astype(float)


def stipple(shape, px, spacing_mm=0.9, dot_mm=0.16):
    """regular dot screen (1 = ink), offset every other row"""
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]].astype(float)
    s = spacing_mm * MM / px
    xs = (xx + 0.5 * s * ((yy // s) % 2)) % s - s / 2
    ys = yy % s - s / 2
    return (np.hypot(xs, ys) < dot_mm * MM / px / 2 + 0.35).astype(float)


def compose(bounds, px, tiles_dir):
    rgb_g, dom, yed, ice, qq, edges = geology(bounds, px, tiles_dir)
    z, hs = relief(bounds, px)
    land = land_mask(bounds, px) | (dom > 0.5)
    H, W = dom.shape
    z, hs, land = z[:H, :W], hs[:H, :W], land[:H, :W]
    out = np.empty((H, W, 3))
    # ocean: depth ramp + very soft shading
    d = np.clip(-np.nan_to_num(z, nan=0) / 4000.0, 0, 1) ** 0.7
    sea = SEA_SHALLOW[None, None] * (1 - d[..., None]) + SEA_DEEP[None, None] * d[..., None]
    sea *= (0.92 + 0.08 * hs)[..., None]
    out[:] = sea
    # land outside the domain: paper + hillshade
    paper = PAPER[None, None] * (0.80 + 0.20 * hs)[..., None]
    out[land] = paper[land]
    # domain geology: colour x subtle hillshade (stronger on bedrock / ice-free uplands than on plains is automatic)
    shade = (0.82 + 0.18 * hs)[..., None]
    geo = rgb_g * shade
    geo = np.where(ice[..., None] > 0.5, rgb_g * (0.90 + 0.10 * hs)[..., None], geo)      # ice: lighter shading
    a = np.clip(dom, 0, 1)[..., None]
    out = out * (1 - a) + geo * a
    # yedoma hatch (dark umber lines over the unit colour)
    hm = hatch((H, W), px) * np.clip(yed, 0, 1)
    out = out * (1 - 0.45 * hm[..., None]) + np.array([0.35, 0.22, 0.12])[None, None] * 0.45 * hm[..., None]
    # Q (undivided) stipple: fine dots, so it reads as mapped-but-undifferentiated, not as a gap
    qd = stipple((H, W), px) * np.clip(qq, 0, 1)
    out = out * (1 - 0.35 * qd[..., None]) + np.array([0.45, 0.40, 0.33])[None, None] * 0.35 * qd[..., None]
    # hairline contacts on top: umber between units, grey-blue round the ice, blue round water bodies
    if edges is not None:
        for k, col in (('geo', CONTACT_INK), ('ice', ICE_INK), ('water', WATER_INK)):
            a = OPT['outline'] * np.clip(edges[k][:H, :W], 0, 1)[..., None]
            out = out * (1 - a) + hex2rgb(col)[None, None] * a
    return np.clip(out, 0, 1), (dom > 0.5)


def _land():
    """Natural Earth land north of 30N: Antarctica turns inside-out in a north-polar projection and covered the whole map"""
    g = gpd.read_file(glob.glob(f'{NE_LAND}/*.shp')[0])
    g['geometry'] = shapely.intersection(g.geometry.values, shapely.box(-180, 30, 180, 90))
    g = g[~g.geometry.is_empty]
    return g.to_crs(6931)


def _lines(geoms):
    """(n, 2) coordinate arrays of every LineString part, through Multi* geometries and collections"""
    out = []
    for p in shapely.get_parts(np.asarray(list(geoms), dtype=object)):
        if p is None or p.is_empty:
            continue
        if p.geom_type in ('LineString', 'LinearRing'):
            c = shapely.get_coordinates(p)
            if len(c) >= 2:
                out.append(c)
        elif hasattr(p, 'geoms'):
            out += _lines(list(p.geoms))
    return out


def _coast(bounds, tol=0.0):
    """coastline: Natural Earth land outlines north of 30N, WITHOUT the edges Natural Earth adds where it cuts land at
    180 deg (Chukotka and Wrangel Island: their outlines drew a straight line across both on the merge-42 A0, found
    2026-10-07) and without the 30N clip edge; EPSG:6931, clipped to bounds, simplified by tol (m) if given.
    Returns (n, 2) arrays in metres."""
    g = gpd.read_file(glob.glob(f'{NE_LAND}/*.shp')[0])
    g = shapely.intersection(shapely.make_valid(g.geometry.values[g.geometry.notna().values]),
                             shapely.box(-180, 30, 180, 90))
    pieces = []
    for c in _lines(shapely.boundary(g[~shapely.is_empty(g)])):
        lon, lat = c[:, 0], c[:, 1]
        cut = (((np.abs(lon[:-1]) > 179.9999) & (np.abs(lon[1:]) > 179.9999))
               | ((lat[:-1] < 30.0001) & (lat[1:] < 30.0001)))           # segment i joins vertices i and i + 1
        start = 0
        for i in np.flatnonzero(cut):
            if i + 1 - start >= 2:
                pieces.append(c[start:i + 1])
            start = i + 1
        if len(c) - start >= 2:
            pieces.append(c[start:])
    s = gpd.GeoSeries([shapely.LineString(p) for p in pieces], crs=4326).to_crs(6931)
    out = shapely.intersection(np.asarray(s.values, dtype=object), shapely.box(*bounds))
    if tol:
        out = shapely.simplify(out, tol)
    return _lines(out)


def ne(name):
    """Natural Earth layer north of 30N, valid in EPSG:6931 (whole-ocean polygons reaching the southern hemisphere turn
    invalid in a north-polar projection: GEOS side-location conflict on the full A0 frame, 2026-10-06)"""
    p = glob.glob(f'{NE}/{name}.shp')
    if not p:
        return None
    g = gpd.read_file(p[0])
    g = g[g.geometry.notna()].copy()
    g['geometry'] = shapely.intersection(shapely.make_valid(g.geometry.values), shapely.box(-180, 30, 180, 90))
    g = g[~g.geometry.is_empty].to_crs(6931)
    g['geometry'] = shapely.make_valid(g.geometry.values)
    g.columns = [c if c == 'geometry' else c.lower() for c in g.columns]       # NE mixes 'SCALERANK' / 'scalerank'
    return g


def _domain(buffer_m=30_000.0):
    """mapped domain (AMAP + permafrost), buffered a little so edge towns keep their labels; None if unavailable"""
    try:
        g = gpd.read_file(f'{ROOT}/work/domain_obu_amap.gpkg', layer='domain').to_crs(6931)
        d = shapely.buffer(shapely.union_all(shapely.make_valid(g.geometry.values)), buffer_m)
        shapely.prepare(d)
        return d
    except Exception:
        return None


def water_spots(poly, n_max=400, near=None):
    """candidate label centres in a water polygon: its pole of inaccessibility (or the point `near`, EPSG:6931) first,
    then a grid of points inside it ordered by their distance from that point (the first candidate whose label box
    clears the land wins)"""
    from shapely.ops import polylabel
    parts = [p for p in shapely.get_parts(poly) if p.geom_type == 'Polygon' and not p.is_empty]
    if not parts:
        return []
    main = max(parts, key=lambda p: p.area)
    if near is not None:
        c0 = shapely.Point(near)
    else:
        try:
            c0 = polylabel(main, tolerance=2_000.0)
        except Exception:
            c0 = main.representative_point()
    x0, y0, x1, y1 = poly.bounds
    step = max(1 * MM, ((x1 - x0) * (y1 - y0) / n_max) ** 0.5)         # 10 km in a small bay
    gx, gy = np.meshgrid(np.arange(x0 + step / 2, x1, step), np.arange(y0 + step / 2, y1, step))
    pts = shapely.points(gx.ravel(), gy.ravel())
    pts = pts[shapely.contains(poly, pts)]
    d = shapely.distance(pts, c0)
    return ([(c0.x, c0.y)] if poly.contains(c0) else []) + [(p.x, p.y) for p in pts[np.argsort(d)]]


def _two_lines(name):
    """the name on two lines, split where the longer line is shortest ('East Korea Bay' -> 'East' / 'Korea Bay')"""
    w = name.split()
    if len(w) < 2:
        return name
    i = min(range(1, len(w)), key=lambda i: max(len(' '.join(w[:i])), len(' '.join(w[i:]))))
    return ' '.join(w[:i]) + '\n' + ' '.join(w[i:])


def vectors(ax, bounds, dpi, serif):
    """linework and labels in map coordinates (metres); line widths in points at print scale. Roads, railways and
    places only inside the mapped domain (outside it the full-sheet preview was crowded with southern Canada and
    Fennoscandia); outside, only the largest cities (scalerank <= 2) keep a label"""
    box = shapely.box(*bounds)
    dom = _domain()
    lw = lambda mm: mm / 0.3528                                         # noqa: E731  mm -> points
    from matplotlib.collections import LineCollection
    ax.add_collection(LineCollection(_coast(bounds), colors=WATER_INK, linewidths=lw(0.12), zorder=5))
    lakes = ne('ne_10m_lakes')
    if lakes is not None:
        lakes = lakes[shapely.intersects(lakes.geometry.values, box) & (lakes['scalerank'] <= 6)]
        lakes.plot(ax=ax, color='#b8d7e8', edgecolor=WATER_INK, linewidth=lw(0.08), zorder=6)
    lake_u = shapely.union_all(lakes.geometry.values) if lakes is not None and len(lakes) else None
    riv = ne('ne_10m_rivers_lake_centerlines')
    if riv is not None:
        # rivers end at the shores of the lakes drawn (H.L. 2026-10-22: the line over Lake Baikal was Natural Earth's
        # lake centreline of the Selenga-Angara, and Athabasca and Winnipeg had the same); centrelines through lakes
        # too small to draw stay, so those rivers keep running
        riv = riv[shapely.intersects(riv.geometry.values, box) & (riv['scalerank'] <= 6)]
        if lake_u is not None:
            riv = riv.assign(geometry=shapely.difference(riv.geometry.values, lake_u))
            riv = riv[~riv.geometry.is_empty]
        for sr, d in riv.groupby('scalerank'):
            d.plot(ax=ax, color=WATER_INK, linewidth=lw(max(0.10, 0.32 - 0.035 * sr)), zorder=7)
    # communications kept quiet (H.L. 2026-10-06: roads were too strong; 2026-10-22: still too prominent, and they ran
    # beyond the mapped zone): thin, muted, transparent; clipped to the domain itself (the 30 km buffer of the labels
    # let them cross the gaps between the isolated-permafrost patches), never across lakes (a railway ferry drew a line
    # over Lake Baikal), no ferry features
    dom_lines = _domain(buffer_m=0.0)

    def _clip_lines(g):
        obj = [c for c in g.columns if c != 'geometry' and g[c].dtype == object]
        if obj:
            g = g[~g[obj].apply(lambda c: c.astype(str).str.contains('ferry', case=False, na=False)).any(axis=1)]
        geom = g.geometry.values
        if dom_lines is not None:
            geom = shapely.intersection(geom, dom_lines)
        if lake_u is not None:
            geom = shapely.difference(geom, lake_u)
        g = g.assign(geometry=geom)
        g = g[~g.geometry.is_empty].explode(index_parts=False)          # a clip can leave points (drawn as dots)
        return g[g.geom_type == 'LineString']

    rail = ne('ne_10m_railroads')
    if rail is not None:
        rail = _clip_lines(rail[shapely.intersects(rail.geometry.values, box)])
        rail.plot(ax=ax, color=INK, linewidth=lw(0.10), alpha=0.5, zorder=8)
        rail.plot(ax=ax, color='#fbfaf6', linewidth=lw(0.04), linestyle=(0, (3, 3)), alpha=0.8, zorder=8.1)
    roads = ne('ne_10m_roads')
    if roads is not None:                   # v4 0.22 mm opaque (too strong), v5a 0.07-0.11 mm at 50 % (vanished), v6 0.10-0.14 mm (strong)
        roads = roads[shapely.intersects(roads.geometry.values, box) & roads['type'].isin(['Major Highway', 'Secondary Highway', 'Road'])]
        roads = _clip_lines(roads)
        for typ, w_, a_ in (('Road', 0.06, 0.40), ('Secondary Highway', 0.07, 0.45), ('Major Highway', 0.09, 0.55)):
            roads[roads['type'] == typ].plot(ax=ax, color='#9a5a48', linewidth=lw(w_), alpha=a_, zorder=8.5)
    # graticule: parallels every 10 deg, meridians every 30 deg, Arctic Circle dashed
    lons = np.linspace(-180, 180, 721)
    for lat in range(40, 90, 10):
        g = gpd.GeoSeries([shapely.LineString(np.c_[lons, np.full_like(lons, lat)])], crs=4326).to_crs(6931)
        g.plot(ax=ax, color='#6b8aa3', linewidth=lw(0.08), alpha=0.55, zorder=4)
    for lon in range(-180, 180, 30):
        g = gpd.GeoSeries([shapely.LineString([(lon, 40), (lon, 89.0)])], crs=4326).to_crs(6931)
        g.plot(ax=ax, color='#6b8aa3', linewidth=lw(0.08), alpha=0.55, zorder=4)
    ac = gpd.GeoSeries([shapely.LineString(np.c_[lons, np.full_like(lons, 66.5622)])], crs=4326).to_crs(6931)
    ac.plot(ax=ax, color='#6b8aa3', linewidth=lw(0.16), linestyle=(0, (6, 4)), zorder=4)
    lab = Labels(ax, frame=box.buffer(-1.5 * MM))                       # labels keep 1.5 mm off the neatline
    land = shapely.union_all(shapely.make_valid(_land().geometry.values))   # labels of water stay off land
    shapely.prepare(land)
    oceans, seas = {_norm(n) for n in OCEANS}, {_norm(n) for n in MAIN_SEAS}
    # sea names first (italic spaced capitals; oceans > main seas > the rest), then region names, places, physical names
    mp = ne('ne_10m_geography_marine_polys')
    if mp is not None:
        mp = mp[shapely.intersects(mp.geometry.values, box) & mp['name'].notna()].copy()
        mp['rank'] = [0 if _norm(n) in oceans else (1 if _norm(n) in seas else 2) for n in mp['name']]
        mp = mp.sort_values(['rank', 'scalerank'])
        for _, r in mp.iterrows():
            if r['rank'] == 2 and dropped(r['name']):
                continue
            try:
                poly = shapely.intersection(r.geometry, box.buffer(-6 * MM))
            except shapely.errors.GEOSException:          # one bad polygon costs one label, not the render
                continue
            if poly.is_empty:
                continue
            size = (12.0, 8.5, 5.8)[r['rank']]
            name = str(r['name'])
            near = SEA_ANCHOR.get(name)
            if near is not None:            # within 150 km of the anchor (the Natural Earth polygon may not reach it),
                near = gpd.GeoSeries([shapely.Point(*near)], crs=4326).to_crs(6931).iloc[0].coords[0]
                poly = shapely.Point(near).buffer(150_000.0)        # smaller there rather than elsewhere at full size
            spots = water_spots(poly, near=near)
            # a sea too narrow for its name at full size gets it smaller; a small bay (Kotzebue Sound, Uda Bay) then in
            # italic lower case, on one line or two; never on land
            small = max(4.6, round(0.65 * size, 1))
            tries = [(' '.join(name.upper()), s, True)
                     for s in sorted({size, max(4.6, round(0.8 * size, 1)), small}, reverse=True)]
            tries += [(name, small, False), (_two_lines(name), small, False)]
            for text, s, sp in tries:
                if any(lab.place(c[0], c[1], text, s, ha='center', va='center', color='#3f6987', style='italic',
                                 zorder=9, fontfamily=serif, spaced=sp, clamp=r['rank'] < 2, avoid=land)
                       for c in spots):
                    break
    halo_r = [pe.withStroke(linewidth=lw(OPT['halo']), foreground=(*PAPER, 0.6))] if OPT['halo'] > 0 else []
    pts = gpd.GeoSeries([shapely.Point(lo, la) for _, lo, la, _, _ in REGIONS], crs=4326).to_crs(6931)
    for (name, _, _, size, phys), p in zip(REGIONS, pts):
        for dy in (0.0, 2.0 * MM, -2.0 * MM, 4.0 * MM, -4.0 * MM):
            if lab.place(p.x, p.y + dy, ' '.join(name.upper()), size, ha='center', va='center',
                         color='#5a4a3a' if phys else INK, style='italic' if phys else 'normal', zorder=9.6,
                         fontfamily=serif, spaced=True, clamp=True, path_effects=halo_r):
                break
    region_names = {_norm(n) for n, *_ in REGIONS}
    pp = ne('ne_10m_populated_places')
    if pp is not None:
        pp = pp[shapely.within(pp.geometry.values, box.buffer(-2 * MM))]
        pp = pp[(pp['scalerank'] <= 8) | (pp['latitude'] > 60)]
        if dom is not None:
            pp = pp[shapely.within(pp.geometry.values, dom) | (pp['scalerank'] <= 2)]
        pp = pp.sort_values('scalerank')
        # thin paper-tone halo (stroke centred on the glyph outline: half of it shows outside), or none
        halo = [pe.withStroke(linewidth=lw(OPT['halo']), foreground=(*PAPER, 0.7))] if OPT['halo'] > 0 else []
        for _, r in pp.iterrows():
            x, y = r.geometry.x, r.geometry.y
            big = r['scalerank'] <= 4
            fs = 6.0 if big else 4.8
            d = 1.1 * MM
            for (dx, dy, ha, va) in ((d, 0.4 * d, 'left', 'center'), (-d, 0.4 * d, 'right', 'center'),
                                     (0, 1.3 * d, 'center', 'bottom'), (0, -1.3 * d, 'center', 'top')):
                if lab.place(x + dx, y + dy, str(r['name']), fs, ha=ha, va=va, color=INK, zorder=9.5,
                             path_effects=halo, fontfamily=serif):
                    ax.plot(x, y, 'o', ms=lw(0.9 if big else 0.6), color=INK, mec=PAPER, mew=lw(0.06), zorder=9)
                    lab.block(x, y, 0.7 * MM)
                    break
    rp = ne('ne_10m_geography_regions_points')
    if rp is not None:
        rp = rp[shapely.within(rp.geometry.values, box) & rp['name'].notna()].sort_values('scalerank')
        d = 0.7 * MM
        for _, r in rp.iterrows():
            name = str(r['name'])
            if dropped(name) or _norm(name) in region_names:
                continue
            text, x, y = ' '.join(name.upper()), r.geometry.x, r.geometry.y
            kw = dict(color='#5a4a3a', zorder=9, fontfamily=serif, style='italic', spaced=True, path_effects=halo_r)
            if 'cape' in str(r.get('featurecla', '')).lower() or re.match(r'^(cape|mys|kap|point)\b', _norm(name)):
                # a cape's name goes beside it on the water, as close to the shore as the land allows (not half on land)
                offs = ((1, 0, 'left', 'center'), (-1, 0, 'right', 'center'), (0, 1, 'center', 'bottom'),
                        (0, -1, 'center', 'top'), (1, 1, 'left', 'bottom'), (-1, 1, 'right', 'bottom'),
                        (1, -1, 'left', 'top'), (-1, -1, 'right', 'top'))
                for k in (d, 2 * d, 3.5 * d):
                    if any(lab.place(x + k * ux, y + k * uy, text, 4.6, ha=ha, va=va, avoid=land, **kw)
                           for ux, uy, ha, va in offs):
                        break
            else:
                lab.place(x, y, text, 4.6, ha='center', va='center', clamp=True, **kw)
    miss = sorted(_DROP - _HIT)
    print(f'labels: {len(_HIT)} of {len(_DROP)} names of DROP_NAMES matched; not found: {miss}', flush=True)


class Labels:
    """greedy placement: a label is drawn only if its box (estimated from font size and text length) clears the boxes
    already placed AND stays inside the frame (H.L. 2026-10-07: labels ran over the map edges); callers try candidates
    in priority order. clamp=True (area names) slides a box that crosses the frame back inside instead of dropping it;
    point labels are not slid, they try their next position."""
    def __init__(self, ax, frame=None):
        self.ax, self.boxes, self.frame = ax, [], frame

    def _box(self, x, y, text, size, ha, va, spaced):
        em = size * 0.3528 * MM                         # 1 pt = 0.3528 mm on paper
        lines = text.split('\n')
        w = (0.46 if spaced else 0.52) * em * max(len(t) for t in lines)
        h = 1.2 * em * len(lines)
        x0 = x - w / 2 if ha == 'center' else (x - w if ha == 'right' else x)
        y0 = y - h / 2 if va == 'center' else (y - h if va == 'top' else y)
        return shapely.box(x0, y0, x0 + w, y0 + h)

    def block(self, x, y, r):
        self.boxes.append(shapely.box(x - r, y - r, x + r, y + r))

    def place(self, x, y, text, size, ha='left', va='center', pad=0.5, spaced=False, clamp=False, avoid=None, **kw):
        """avoid: geometry the label box must not touch (land, for the names of seas and capes)"""
        b = self._box(x, y, text, size, ha, va, spaced)
        if self.frame is not None and not self.frame.contains(b):
            if not clamp:
                return False
            fx0, fy0, fx1, fy1 = self.frame.bounds
            bx0, by0, bx1, by1 = b.bounds
            if bx1 - bx0 > fx1 - fx0 or by1 - by0 > fy1 - fy0:
                return False
            dx = max(0.0, fx0 - bx0) - max(0.0, bx1 - fx1)
            dy = max(0.0, fy0 - by0) - max(0.0, by1 - fy1)
            x, y = x + dx, y + dy
            b = shapely.box(bx0 + dx, by0 + dy, bx1 + dx, by1 + dy)
        if any(b.buffer(pad * MM).intersects(o) for o in self.boxes):
            return False
        if avoid is not None and avoid.intersects(b.buffer(0.3 * MM)):
            return False
        self.boxes.append(b)
        self.ax.text(x, y, text, fontsize=size, ha=ha, va=va, **kw)
        return True


GROUPS = [('Glacial', ['T', 'GF', 'GL', 'GM']), ('Marine and coastal', ['M']),
          ('Fluvial and lacustrine', ['F', 'L', 'K']), ('Eolian', ['E']), ('Permafrost', ['Y']),
          ('Slope and residual', ['C', 'W']), ('Organic', ['O']), ('Other', ['V', 'R', 'Q', 'I', 'X'])]
# the two QR codes (H. Lantuit 2026-10-07: PANGAEA entry AND ESSD paper). Placeholders until the DOIs are minted: pass
# --doi-data / --doi-paper for the print run. The PANGAEA DOI is the parent (collection) DOI if the CryoGrid addendum
# becomes a second dataset; ESSD gives a discussion-paper DOI first, the final one on acceptance.
DOIS = {'data': '10.1594/PANGAEA.XXXXXX', 'paper': '10.5194/essd-2026-XXX'}


def doi_url(doi):
    return f'https://doi.org/{doi}'


def draw_qr(ax, text, x, y, size, colour=INK):
    """QR code (error level M) as ONE vector path, lower-left corner at (x, y), size in axis units. Dark modules are
    merged into runs per row and filled as a single compound path, so PDF viewers show no hairline seams between
    modules. Keep ~4 modules of blank paper around it (quiet zone)."""
    import segno
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch
    m = np.array([[1 if v else 0 for v in row] for row in segno.make(text, error='m').matrix], dtype=np.int8)
    n = m.shape[0]
    cell = size / n
    verts, codes = [], []
    for r in range(n):
        d = np.diff(np.r_[0, m[r], 0])
        for c0, c1 in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
            xa, xb = x + c0 * cell, x + c1 * cell
            yb = y + size - r * cell
            ya = yb - cell
            verts += [(xa, ya), (xb, ya), (xb, yb), (xa, yb), (xa, ya)]
            codes += [Path.MOVETO, Path.LINETO, Path.LINETO, Path.LINETO, Path.CLOSEPOLY]
    ax.add_patch(PathPatch(Path(verts, codes), fc=colour, ec='none', lw=0))


def panel(fig, rect, serif, present=None):
    """title cartouche, grouped legend, scale bar, QR code; rect = [x0, y0, w, h] in figure fractions"""
    ax = fig.add_axes(rect)
    W_mm = rect[2] * fig.get_figwidth() * 25.4
    H_mm = rect[3] * fig.get_figheight() * 25.4
    ax.set_xlim(0, W_mm); ax.set_ylim(0, H_mm); ax.set_axis_off()
    y = H_mm - 5
    ax.text(W_mm / 2, y, 'S U R F I C I A L   G E O L O G Y', ha='center', va='top', fontsize=10.5, fontweight='bold',
            fontfamily=serif, color=INK)
    y -= 6.0
    ax.text(W_mm / 2, y, 'OF THE ARCTIC PERMAFROST REGION', ha='center', va='top', fontsize=7.2, fontfamily=serif,
            color=INK)
    y -= 5
    ax.plot([6, W_mm - 6], [y, y], color=INK, lw=0.5); ax.plot([6, W_mm - 6], [y - 0.8, y - 0.8], color=INK, lw=0.25)
    y -= 4.0
    for g, cls in GROUPS:
        cls = [c for c in cls if present is None or c in present]
        if not cls:
            continue
        ax.text(4, y, g.upper(), fontsize=4.6, style='italic', fontfamily=serif, color='#5a4a3a', va='top')
        y -= 3.1
        for c in cls:
            ax.add_patch(plt.Rectangle((6, y - 3.0), 7, 3.4, fc=PAL[c], ec=INK, lw=0.25))
            if c == 'Q':
                for xx in np.arange(6.6, 13, 0.9):
                    for yy in np.arange(y - 2.7, y + 0.2, 0.9):
                        ax.plot(xx, yy, '.', ms=0.6, color='#6b5f50')
            ax.text(15, y - 1.3, NAMES[c], fontsize=5.0, va='center', fontfamily=serif, color=INK)
            y -= 4.1
        if g == 'Permafrost':
            ax.add_patch(plt.Rectangle((6, y - 3.0), 7, 3.4, fc='white', ec=INK, lw=0.25, hatch='/////'))
            ax.text(15, y - 1.3, 'Yedoma domain (IRYP v2), overprint', fontsize=5.0, va='center', fontfamily=serif,
                    color=INK)
            y -= 4.1
        y -= 1.0
    # scale bar: 0-500 km = 50 mm at 1:10M
    y -= 3
    ax.text(6, y + 2.6, 'Scale 1 : 10 000 000', fontsize=5, fontfamily=serif, va='bottom')
    for k in range(5):
        ax.add_patch(plt.Rectangle((6 + 10 * k, y), 10, 1.2, fc=INK if k % 2 == 0 else 'white', ec=INK, lw=0.3))
        ax.text(6 + 10 * k, y - 1, f'{100 * k}', fontsize=4.2, ha='center', va='top', fontfamily=serif)
    ax.text(56, y - 1, '500 km', fontsize=4.2, ha='center', va='top', fontfamily=serif)
    y -= 6
    ax.text(6, y, 'Lambert azimuthal equal-area projection\ncentred on the North Pole', fontsize=4.2,
            fontfamily=serif, va='top', style='italic')
    # QR code (vector modules) to the dataset
    size = 22.0
    q0x, q0y = W_mm - size - 6, 9
    draw_qr(ax, doi_url(DOIS['data']), q0x, q0y, size)
    ax.text(q0x + size / 2, q0y - 1.2, f'Dataset (PANGAEA)\ndoi: {DOIS["data"]}', fontsize=4.0, ha='center',
            va='top', fontfamily=serif)
    ax.text(6, 16, 'Lantuit H. and Fritz M. (2026)\nAlfred Wegener Institute\nHelmholtz Centre for Polar and\nMarine Research, Potsdam',
            fontsize=4.4, fontfamily=serif, va='top', color=INK)
    ax.add_patch(plt.Rectangle((1, 1), W_mm - 2, H_mm - 2, fc='none', ec=INK, lw=0.6))


def render(bounds, w_mm, h_mm, dpi, tiles_dir, out_png, title=None, panel_mm=0):
    serif = fonts()
    px = 25.4 / dpi * MM                    # ground metres per print pixel
    img, dom = compose(bounds, px, tiles_dir)
    W = w_mm + panel_mm + (6 if panel_mm else 0)
    fig = plt.figure(figsize=(W / 25.4, h_mm / 25.4), dpi=dpi)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([0, 0, w_mm / W, 1])
    x0, y0, x1, y1 = bounds
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation='nearest', zorder=1)
    vectors(ax, bounds, dpi, serif)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_axis_off()
    if title:
        ax.text(0.012, 0.985, title, transform=ax.transAxes, fontsize=6, va='top', color=INK, fontfamily=serif,
                bbox=dict(boxstyle='square,pad=0.4', fc=(1, 1, 1, 0.85), ec=INK, lw=0.4))
    if panel_mm:
        panel(fig, [(w_mm + 6) / W, 0, panel_mm / W, 1], serif, None)
    fig.savefig(out_png, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_png


SCALE_CLASSES = [(100_000, '1:100 000 and finer', '#1f6b4f'), (250_000, '1:125 000 - 1:250 000', '#5aa27c'),
                 (600_000, '1:500 000 - 1:600 000', '#a9d18e'), (1_000_000, '1:1 000 000', '#e6e59a'),
                 (1e12, '1:2 500 000 - 1:5 000 000', '#f3c98b')]


# second panel inset (H. Lantuit 2026-10-07): permafrost zones (Obu et al. 2019) with the IRYP v2 Yedoma domain on top,
# in the tawny of the ice-complex class. Zones as a violet ramp: apart from the sea blue and from the green-orange
# reliability diagram above it.
PF_ZONES = [('continuous', 'Continuous', '#54408a'), ('discontinuous', 'Discontinuous', '#8873b8'),
            ('sporadic', 'Sporadic', '#b8a9d6'), ('isolated', 'Isolated patches', '#ddd5ec')]
NO_PF, INSET_ICE = '#d9d4c7', '#ffffff'
INSET_PX = 4_000.0                  # inset grid (m): 0.1 mm on the 217 mm wide insets (12 km before 2026-10-07)


def inset_rasters(bounds, px, tiles_dir):
    """the two panel insets on one coarse grid, in one pass over the tiles:
      rel   finest source-scale class (1..5 = SCALE_CLASSES, 6 = not mapped, 0 = no polygon)
      yed   IRYP v2 Yedoma 'yes' (confirmed + likely: the hatch of the main map)
      ice   glaciers and ice sheet (hclass I)
      land  Natural Earth land; dom  the mapped domain (work/domain_obu_amap.gpkg 'domain')
      zone  permafrost zone (Obu et al. 2019; 1..4 = PF_ZONES, 0 = none), from the same file"""
    tr, shp = grid(bounds, px)
    rel, yed, ice = (np.zeros(shp, np.uint8) for _ in range(3))
    for f in sorted(glob.glob(f'{tiles_dir}/*.parquet')):
        g = gpd.read_parquet(f, columns=['geometry', 'hclass', 'scale_den', 'yedoma'])
        if g.empty:
            continue
        q = shapely.force_2d(g.geometry.values)
        hc = g['hclass'].astype('string').fillna('U').to_numpy(dtype=object)      # numpy masks, not BooleanArray
        sd = pd.to_numeric(g['scale_den'], errors='coerce').fillna(1e13).values
        k = np.searchsorted([c[0] for c in SCALE_CLASSES], sd, side='left') + 1
        k = np.where(hc == 'U', 6, np.minimum(k, 5))
        rasterio.features.rasterize([(a, int(v)) for a, v in zip(q, k)], out=rel, transform=tr)
        for mask, out in ((g['yedoma'].astype('string').fillna('').to_numpy(dtype=object) == 'yes', yed), (hc == 'I', ice)):
            if mask.any():
                rasterio.features.rasterize([(a, 1) for a in q[mask]], out=out, transform=tr)
    gp = f'{ROOT}/work/domain_obu_amap.gpkg'
    d = gpd.read_file(gp, layer='domain').to_crs(6931)
    dom = np.zeros(shp, np.uint8)
    rasterio.features.rasterize([(a, 1) for a in shapely.force_2d(d.geometry.values)], out=dom, transform=tr)
    z = gpd.read_file(gp, layer='permafrost_zones').to_crs(6931)
    code = {n: i + 1 for i, (n, _, _) in enumerate(PF_ZONES)}
    zone = np.zeros(shp, np.uint8)
    rasterio.features.rasterize([(a, code[v]) for a, v in zip(shapely.force_2d(z.geometry.values), z['zone'])
                                 if v in code], out=zone, transform=tr)
    return dict(rel=rel, yed=yed, ice=ice, land=land_mask(bounds, px).astype(np.uint8), dom=dom, zone=zone)


def neatline(fig, rect_mm, sheet_mm, serif):
    """classic double neatline and graticule labels where meridians / parallels meet the frame"""
    W, H = sheet_mm
    x0, y0, w, h = rect_mm
    ax = fig.add_axes([0, 0, 1, 1], zorder=-1)
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_axis_off()
    for d, lw_ in ((0, 0.9), (2.2, 0.35)):
        ax.add_patch(plt.Rectangle((x0 - d, y0 - d), w + 2 * d, h + 2 * d, fc='none', ec=INK, lw=lw_))
    ax.add_patch(plt.Rectangle((8, 8), W - 16, H - 16, fc='none', ec=INK, lw=0.5))
    fx0, fy0, fx1, fy1 = FRAME
    sx, sy = w / (fx1 - fx0), h / (fy1 - fy0)
    edges = {'bottom': shapely.LineString([(fx0, fy0), (fx1, fy0)]), 'top': shapely.LineString([(fx0, fy1), (fx1, fy1)]),
             'left': shapely.LineString([(fx0, fy0), (fx0, fy1)]), 'right': shapely.LineString([(fx1, fy0), (fx1, fy1)])}
    lines = []
    for lon in range(-180, 180, 30):
        g = gpd.GeoSeries([shapely.LineString([(lon, 35), (lon, 89.9)])], crs=4326).to_crs(6931).geometry.values[0]
        lab = f'{abs(lon)}\u00b0{"E" if lon > 0 else ("W" if lon < 0 else "")}' if lon not in (0, -180) else ('0\u00b0' if lon == 0 else '180\u00b0')
        lines.append((g, lab))
    lons = np.linspace(-180, 180, 1441)
    for lat in range(40, 80, 10):
        g = gpd.GeoSeries([shapely.LineString(np.c_[lons, np.full_like(lons, lat)])], crs=4326).to_crs(6931).geometry.values[0]
        lines.append((g, f'{lat}\u00b0N'))
    for g, lab in lines:
        for side, e in edges.items():
            ip = shapely.intersection(g, e)
            for q in shapely.get_parts(ip):
                if q.geom_type != 'Point':
                    continue
                px_, py_ = x0 + (q.x - fx0) * sx, y0 + (q.y - fy0) * sy
                off = 4.5
                if side == 'left':
                    # the 20 mm left margin holds the double neatline and the sheet border at 8 mm: horizontal labels
                    # ran over the border (H.L. 2026-10-22); upright along the edge, centred in the free strip
                    ax.text((8.0 + x0 - 2.2) / 2, py_, lab, ha='center', va='center', rotation=90, fontsize=9,
                            fontfamily=serif, color=INK)
                else:
                    pos = {'bottom': (px_, y0 - off, 'center', 'top'), 'top': (px_, y0 + h + off, 'center', 'bottom'),
                           'right': (x0 + w + off, py_, 'left', 'center')}[side]
                    ax.text(pos[0], pos[1], lab, ha=pos[2], va=pos[3], fontsize=9, fontfamily=serif, color=INK)
                tick = {'bottom': ((px_, px_), (y0 - 2.2, y0)), 'top': ((px_, px_), (y0 + h, y0 + h + 2.2)),
                        'left': ((x0 - 2.2, x0), (py_, py_)), 'right': ((x0 + w, x0 + w + 2.2), (py_, py_))}[side]
                ax.plot(*tick, color=INK, lw=0.6)


CITATION = ('Lantuit H. and Fritz M. (2026). Surficial geology of the Arctic permafrost region,\n'
            'a harmonised 1:5 000 - 1:5 000 000 compilation. Alfred Wegener Institute, Helmholtz\n'
            'Centre for Polar and Marine Research, Potsdam.')
LOGO = f'{ROOT}/pylib/logos/AWI_Logo_Farbe_RGB_durchsichtig.png'      # AWI corporate design, colour, transparent
PDF_META = {'Title': 'ArcSurf v1.0 - Surficial geology of the Arctic permafrost region, wall map 1:10 000 000',
            'Author': 'Lantuit H., Fritz M.', 'Subject': 'A harmonised compilation of geological and '
            'Quaternary maps, 1:5 000 to 1:5 000 000', 'Keywords': 'surficial geology, permafrost, Arctic, ArcSurf'}


def credits():
    return ('Lambert azimuthal equal-area projection centred on the North Pole (EPSG:6931). Areas are true;\n'
            'distances are true only near the Pole. Relief and bathymetry: ETOPO 2022 (NOAA NCEI). '
            'Land: © OpenStreetMap contributors (ODbL).\n'
            'Places, roads, rivers: Natural Earth. Glaciers: RGI 6.0; Greenland Ice Sheet: PROMICE 2022.\n'
            'Permafrost zones: Obu et al. (2019). Yedoma domain: IRYP v2 (Strauss et al. 2021, 2022). Arctic limit: AMAP.\n'
            # GEUS permission of 2026-10-22: the four datasets cited on the map, GEUS acknowledged, licences stated
            'Greenland: Geological Survey of Denmark and Greenland (GEUS), Kokfelt et al. (2023), doi:10.22008/FK2/FWX5ET; '
            'Guarnieri et al. (2022a, b, c),\ndoi:10.22008/FK2/IBHIZL, FK2/PGSMJH, FK2/07OYKX. Originals CC BY-SA 4.0 on '
            'GEUS Dataverse; derived component CC BY 4.0 with permission from GEUS.\n'
            + PAL_NOTE.replace('(Deblonde et al. 2024); ', '(Deblonde et al. 2024);\n'))


INSET_ROW, INSET_TITLE = 7.5, 6.0                       # inset legend row and title heights (mm)
# AMAP Arctic limit on both insets (H.L. 2026-10-07: the domain is AMAP + permafrost, so show where AMAP runs)
AMAP_SHP = f'{ROOT}/raw/amap/amaplim_lam_poly.shp'
AMAP_STYLE = dict(colors='#8c2d1e', linewidths=0.8, linestyles=[(0, (4.0, 2.0))])


def _amap_lines(bounds, tol=2_000.0):
    """outline of the AMAP area polygon (the Arctic limit used for the domain) in EPSG:6931, clipped to bounds"""
    try:
        a = gpd.read_file(AMAP_SHP).to_crs(6931)
    except Exception as e:                                      # the insets still render without it
        print('AMAP limit not drawn:', str(e)[:120], flush=True)
        return []
    b = shapely.boundary(shapely.make_valid(shapely.union_all(a.geometry.values)))
    b = shapely.intersection(b, shapely.box(*bounds))
    return _lines([shapely.simplify(b, tol) if tol else b])


def _legend_grid(ax, x, y, width, items, ncol, serif, fs=8.5):
    """swatch rows under an inset (items: (label, colour) or (label, style dict, 'line')); returns the y below the
    last row"""
    for k, it in enumerate(items):
        lab, col_ = it[0], it[1]
        xx, yz = x + (k % ncol) * (width / ncol), y - (k // ncol) * INSET_ROW
        if len(it) > 2 and it[2] == 'line':
            from matplotlib.collections import LineCollection
            ax.add_collection(LineCollection([[(xx, yz - 2.4), (xx + 8.5, yz - 2.4)]], **col_))
        else:
            ax.add_patch(plt.Rectangle((xx, yz - 4.8), 8.5, 4.8, fc=col_, ec=INK, lw=0.3))
        ax.text(xx + 10.5, yz - 2.4, lab, fontsize=fs, va='center', fontfamily=serif, color=INK)
    return y - ((len(items) - 1) // ncol + 1) * INSET_ROW


def _inset(ax, rgb, x, ytop, iw, bounds, coast, serif, title, amap=None):
    """overview map in the panel: italic title, raster, coastline and AMAP limit (vector), frame; returns the y below
    the frame"""
    from matplotlib.collections import LineCollection
    ax.text(x, ytop, title, fontsize=9.5, style='italic', fontfamily=serif, color='#5a4a3a', va='top')
    ytop -= INSET_TITLE
    ih = iw * (bounds[3] - bounds[1]) / (bounds[2] - bounds[0])
    ax.imshow(rgb, extent=(x, x + iw, ytop - ih, ytop), interpolation='nearest', zorder=2)
    sx, sy = iw / (bounds[2] - bounds[0]), ih / (bounds[3] - bounds[1])
    to_mm = lambda cs: [np.c_[x + (c[:, 0] - bounds[0]) * sx, ytop - ih + (c[:, 1] - bounds[1]) * sy] for c in cs]  # noqa: E731
    if coast:
        ax.add_collection(LineCollection(to_mm(coast), colors=WATER_INK, linewidths=0.25, alpha=0.9, zorder=3))
    if amap:                                    # white casing under the dashes: legible on the dark purples as well
        segs = to_mm(amap)
        ax.add_collection(LineCollection(segs, colors='white', linewidths=1.6, alpha=0.75, zorder=3.4))
        ax.add_collection(LineCollection(segs, zorder=3.5, **AMAP_STYLE))
    ax.add_patch(plt.Rectangle((x, ytop - ih), iw, ih, fc='none', ec=INK, lw=0.4, zorder=4))
    return ytop - ih


def big_panel(fig, rect_mm, sheet_mm, serif, ins, bounds, coast=None, pdf=False):
    """side panel: title, legend, two overview insets (reliability diagram; permafrost zones + Yedoma domain), scale
    bar, credits, citation, AWI logo and two QR codes (PANGAEA dataset, ESSD paper). The bottom block sits at the foot
    of the panel; the height left between it and the legend is shared out as three equal gaps around the insets (the insets
    shrink, centred, only if they would not fit with 8 mm gaps)."""
    W, H = sheet_mm
    x0, y0, w, h = rect_mm
    ax = fig.add_axes([x0 / W, y0 / H, w / W, h / H])
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.set_axis_off()
    y = h - 10
    ax.text(w / 2, y, 'S U R F I C I A L   G E O L O G Y', ha='center', va='top', fontsize=30, fontweight='bold',
            fontfamily=serif, color=INK)
    y -= 15
    ax.text(w / 2, y, 'OF THE ARCTIC PERMAFROST REGION', ha='center', va='top', fontsize=17, fontfamily=serif, color=INK)
    y -= 12
    ax.plot([10, w - 10], [y, y], color=INK, lw=1.2); ax.plot([10, w - 10], [y - 1.6, y - 1.6], color=INK, lw=0.5)
    y -= 7
    ax.text(w / 2, y, 'A harmonised compilation of geological and Quaternary maps, 1 : 5 000 to 1 : 5 000 000',
            ha='center', va='top', fontsize=9.5, style='italic', fontfamily=serif, color=INK)
    y -= 12
    # legend, two columns
    col_x, col_y0 = [8, w / 2 + 2], y
    col, yy = 0, col_y0
    half = 5
    # sizes raised 2026-10-07 (H.L.: legend text too small): class names 11 pt (was 9), group headings 9.5 pt (8),
    # swatches 15 x 7.5 mm (13 x 6.5), rows 10 mm apart (8.5)
    sw, sh, row = 15.0, 7.5, 10.0
    ymin = col_y0                                           # foot of the LONGER column (was: the last one)
    for gi, (g, cls) in enumerate(GROUPS):
        if gi == half:
            col, yy = 1, col_y0
        ax.text(col_x[col], yy, g.upper(), fontsize=9.5, style='italic', fontfamily=serif, color='#5a4a3a', va='top')
        yy -= 7
        for c in cls:
            ax.add_patch(plt.Rectangle((col_x[col] + 2, yy - sh + 1), sw, sh, fc=PAL[c], ec=INK, lw=0.4))
            if c == 'Q':
                for xx in np.arange(col_x[col] + 3, col_x[col] + 2 + sw, 1.5):
                    for yz in np.arange(yy - sh + 1.5, yy + 0.6, 1.5):
                        ax.plot(xx, yz, '.', ms=1.2, color='#6b5f50')
            ax.text(col_x[col] + 21, yy - sh / 2 + 1, NAMES[c], fontsize=11, va='center', fontfamily=serif, color=INK)
            yy -= row
        if g == 'Permafrost':
            ax.add_patch(plt.Rectangle((col_x[col] + 2, yy - sh + 1), sw, sh, fc='white', ec=INK, lw=0.4, hatch='////'))
            ax.text(col_x[col] + 21, yy - sh / 2 + 1, 'Yedoma domain (IRYP v2)', fontsize=11, va='center',
                    fontfamily=serif, color=INK)
            yy -= row
        yy -= 3
        ymin = min(ymin, yy)
    y_leg = min(ymin, col_y0 - 150) - 6

    # bottom block, from the foot of the panel up: QR codes + citation, credits, scale bar
    qs, qy = 27.0, 12.0                                     # QR size and lower edge (mm)
    qx2 = w - 8 - qs                                        # ESSD paper, right
    qx1 = qx2 - 13 - qs                                     # PANGAEA dataset, left (13 mm apart: quiet zones)
    for qx, head, doi in ((qx1, 'Dataset  ·  PANGAEA', DOIS['data']), (qx2, 'Data paper  ·  ESSD', DOIS['paper'])):
        draw_qr(ax, doi_url(doi), qx, qy, qs)
        ax.text(qx + qs / 2, qy - 1.6, f'{head}\ndoi:{doi}', fontsize=6.3, ha='center', va='top', fontfamily=serif,
                color=INK, linespacing=1.3)
    ax.text(8, qy + qs, CITATION, fontsize=7.5, fontfamily=serif, va='top', color=INK, linespacing=1.35)
    # AWI logo (H.L. 2026-10-22): the colour file of the AWI corporate design, bottom left, level with the QR codes,
    # under the citation; in the PDF at its own resolution (2000 px over 70 mm, ~700 dpi)
    if os.path.exists(LOGO):
        im = plt.imread(LOGO)
        lh = 12.5
        ax.imshow(im, extent=(8, 8 + lh * im.shape[1] / im.shape[0], qy, qy + lh),
                  interpolation='none' if pdf else 'antialiased', zorder=5)
    else:
        print('AWI logo missing:', LOGO, flush=True)
    y_cred = qy + qs + 31                                   # 8 lines of 7 pt end ~5 mm above the QR codes
    ax.text(8, y_cred, credits(), fontsize=7, fontfamily=serif, va='top', style='italic', color=INK, linespacing=1.35)
    y_sb = y_cred + 8                                       # scale bar: 0-1000 km = 100 mm at 1:10M
    for k in range(5):
        ax.add_patch(plt.Rectangle((8 + 20 * k, y_sb), 20, 2, fc=INK if k % 2 == 0 else 'white', ec=INK, lw=0.4))
        ax.text(8 + 20 * k, y_sb - 1.5, f'{200 * k}', fontsize=7, ha='center', va='top', fontfamily=serif)
    ax.text(108, y_sb - 1.5, '1000 km', fontsize=7, ha='center', va='top', fontfamily=serif)
    ax.text(8, y_sb + 8, 'Scale 1 : 10 000 000', fontsize=9, fontfamily=serif, va='top')
    y_foot = y_sb + 8

    # the two insets share the height between the legend and the bottom block
    aspect = (bounds[3] - bounds[1]) / (bounds[2] - bounds[0])
    fixed = 2 * (INSET_TITLE + 4 + 2 * INSET_ROW)            # per inset: title, gap, two legend rows
    iw = min(w - 16, (y_leg - y_foot - fixed - 3 * 8) / (2 * aspect))
    gap = (y_leg - y_foot - fixed - 2 * iw * aspect) / 3
    xi = (w - iw) / 2
    land = (ins['land'] > 0) | (ins['rel'] > 0)
    # 1. reliability diagram: finest source scale; land outside the domain in paper tone, not sea blue
    code = np.where(ins['rel'] > 0, ins['rel'].astype(np.int16) + 1, land.astype(np.int16))
    lut = np.array([SEA_SHALLOW, PAPER] + [hex2rgb(c) for _, _, c in SCALE_CLASSES] + [hex2rgb('#d9d9d9')])
    amap = _amap_lines(bounds)
    amap_key = ('AMAP Arctic limit', AMAP_STYLE, 'line')
    y = y_leg - gap
    y = _inset(ax, lut[code], xi, y, iw, bounds, coast, serif, 'RELIABILITY DIAGRAM: SCALE OF THE SOURCE MAPS', amap)
    _legend_grid(ax, xi, y - 4, iw, [(lab, c) for _, lab, c in SCALE_CLASSES] + [('Not mapped', '#d9d9d9'), amap_key],
                 4, serif)
    # 2. permafrost zones (Obu et al. 2019) inside the mapped domain, glaciers, IRYP v2 Yedoma domain on top
    mapped = (ins['rel'] > 0) | ((ins['dom'] > 0) & (ins['land'] > 0))
    code = land.astype(np.int16)                            # 0 sea, 1 land outside the domain
    code[mapped] = 2                                        # mapped, outside the permafrost zones
    zz = mapped & (ins['zone'] > 0)
    code[zz] = 2 + ins['zone'][zz]                          # 3..6 continuous .. isolated
    code[ins['ice'] > 0] = 7
    code[ins['yed'] > 0] = 8
    lut = np.array([SEA_SHALLOW, PAPER, hex2rgb(NO_PF)] + [hex2rgb(c) for _, _, c in PF_ZONES]
                   + [hex2rgb(INSET_ICE), hex2rgb(PAL['Y'])])
    y = y - 4 - 2 * INSET_ROW - gap
    y = _inset(ax, lut[code], xi, y, iw, bounds, coast, serif,
               'PERMAFROST ZONES (OBU ET AL. 2019) AND YEDOMA DOMAIN (IRYP V2)', amap)
    _legend_grid(ax, xi, y - 4, iw, [(lab, c) for _, lab, c in PF_ZONES]
                 + [('No permafrost', NO_PF), ('Glaciers, ice sheet', INSET_ICE), ('Yedoma domain (IRYP v2)', PAL['Y']),
                    amap_key], 4, serif)
    print(f'panel: legend foot {y_leg:.1f} mm, insets {iw:.1f} mm wide, gaps {gap:.1f} mm, bottom block top '
          f'{y_foot:.1f} mm', flush=True)


def fit_labels(fig, ax, margin_mm=1.0):
    """exact check after placement (Labels uses estimated boxes): every text of the map axes is measured as it
    renders, and one that crosses the neatline (inset by margin_mm) is nudged back inside by its overflow (H.L.
    2026-10-07: labels ran over the map edges). Returns the texts nudged."""
    r = fig.canvas.get_renderer()
    ab = ax.get_window_extent(r)
    m = margin_mm / 25.4 * fig.dpi
    x0, y0, x1, y1 = ab.x0 + m, ab.y0 + m, ab.x1 - m, ab.y1 - m
    moved = []
    for t in ax.texts:
        bb = t.get_window_extent(r)
        dx = max(0.0, x0 - bb.x0) - max(0.0, bb.x1 - x1)
        dy = max(0.0, y0 - bb.y0) - max(0.0, bb.y1 - y1)
        if dx or dy:
            px, py = ax.transData.transform(t.get_position())
            t.set_position(ax.transData.inverted().transform((px + dx, py + dy)))
            moved.append((t.get_text(), round(dx / fig.dpi * 25.4, 2), round(dy / fig.dpi * 25.4, 2)))
    return moved


def layout(dpi, tiles_dir, out_png):
    serif = fonts()
    sheet = (1189.0, 841.0)
    mrect = (20.0, 35.0, 900.0, 770.0)
    prect = (20.0 + 900.0 + 16.0, 35.0, 1189.0 - 20.0 - 900.0 - 16.0 - 20.0, 770.0)
    px = 25.4 / dpi * MM
    # the rasters take most of the time (all tiles read twice): cached, so a failure in the vector / panel part
    # does not cost the whole render (delete the .npz, or pass --fresh, after a new merge)
    import hashlib                                                     # a palette change must not reuse old rasters
    pal_key = hashlib.md5(repr(sorted(PAL.items())).encode()).hexdigest()[:6]
    tname = os.path.basename(os.path.normpath(tiles_dir))
    cache = f'{OUTD}/a0_layout_{dpi}dpi_{tname}_{OPT["outline"]}_{pal_key}.npz'
    icache = f'{OUTD}/a0_insets_{tname}_{int(INSET_PX)}.npz'          # class rasters of the insets (palette-free)
    fresh = '--fresh' in sys.argv
    if '--dry' in sys.argv:                     # layout test: blank map face (minutes instead of ~40 min), real insets
        _, (H, W) = grid(FRAME, px)
        img = np.full((H, W, 3), (PAPER * 255 + 0.5).astype(np.uint8), np.uint8)
    elif os.path.exists(cache) and not fresh:
        img = np.load(cache)['img']                                   # (older caches also hold a 12 km 'rel')
    else:
        img, _ = compose(FRAME, px, tiles_dir)
        img = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)       # 8 bit: a 300 dpi cache stays ~0.3 GB
        np.savez(cache, img=img)
    if img.dtype != np.uint8:                                         # caches written before 2026-10-07 are float
        img = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    if os.path.exists(icache) and not fresh:
        z = np.load(icache)
        ins = {k: z[k] for k in z.files}
    else:
        ins = inset_rasters(FRAME, INSET_PX, tiles_dir)
        np.savez(icache, **ins)
    fig = plt.figure(figsize=(sheet[0] / 25.4, sheet[1] / 25.4), dpi=dpi)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([mrect[0] / sheet[0], mrect[1] / sheet[1], mrect[2] / sheet[0], mrect[3] / sheet[1]])
    x0, y0, x1, y1 = FRAME
    pdf = out_png.lower().endswith('.pdf')
    # PDF: the geology raster is embedded as is (interpolation 'none' = no resampling, it is already at the print
    # resolution); frame, labels, legend and QR stay vector
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation='none' if pdf else 'nearest', zorder=1)
    vectors(ax, FRAME, dpi, serif)
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_axis_off()
    moved = fit_labels(fig, ax)
    print(f'labels nudged back inside the frame: {len(moved)}', moved[:40], flush=True)
    neatline(fig, mrect, sheet, serif)
    big_panel(fig, prect, sheet, serif, ins, FRAME, _coast(FRAME, tol=2_000.0), pdf=pdf)
    if pdf:
        plt.rcParams['pdf.compression'] = 9
        try:                                        # TrueType embedding (editable text for the print shop) ...
            plt.rcParams['pdf.fonttype'] = 42
            fig.savefig(out_png, dpi=dpi, facecolor=fig.get_facecolor(), metadata=PDF_META)
        except Exception as e:                      # ... the URW OTF (CFF) faces may refuse: Type 3 then
            print('fonttype 42 failed (', str(e)[:120], ') -> Type 3 fonts', flush=True)
            plt.rcParams['pdf.fonttype'] = 3
            fig.savefig(out_png, dpi=dpi, facecolor=fig.get_facecolor(), metadata=PDF_META)
    else:
        fig.savefig(out_png, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_png


def main():
    a = sys.argv[1:]
    tiles = a[a.index('--tiles') + 1] if '--tiles' in a else f'{ROOT}/work/tiles'
    for k in ('halo', 'outline'):
        if f'--{k}' in a:
            OPT[k] = float(a[a.index(f'--{k}') + 1])
    if '--palette' in a:
        PAL.update(PALETTES[a[a.index('--palette') + 1]])
    for k in ('data', 'paper'):
        if f'--doi-{k}' in a:
            DOIS[k] = a[a.index(f'--doi-{k}') + 1]
    tag = f"_{a[a.index('--tag') + 1]}" if '--tag' in a else ''
    os.makedirs(OUTD, exist_ok=True)
    if a[0] in ('mockup', 'sheetmock'):
        name, cx, cy, w_mm, h_mm = a[1], float(a[2]) * 1000, float(a[3]) * 1000, float(a[4]), float(a[5])
        b = (cx - w_mm / 2 * MM, cy - h_mm / 2 * MM, cx + w_mm / 2 * MM, cy + h_mm / 2 * MM)
        p = render(b, w_mm, h_mm, 300, tiles, f'{OUTD}/{a[0]}_{name}{tag}.png',
                   title=f'Mockup: a {w_mm:.0f} x {h_mm:.0f} mm crop of the A0 sheet at print scale 1:{SCALE:,}',
                   panel_mm=85 if a[0] == 'sheetmock' else 0)
        print('wrote', p)
    elif a[0] == 'layout':
        dpi = int(a[a.index('--dpi') + 1]) if '--dpi' in a else 30
        if '--pdf' in a:                            # print file: out/a0/arcsurf_a0_<tiles>_<dpi>dpi.pdf
            name = f"arcsurf_a0_{os.path.basename(os.path.normpath(tiles))}_{dpi}dpi{tag}.pdf"
            print('wrote', layout(dpi, tiles, f'{OUTD}/{name}'))
        else:
            print('wrote', layout(dpi, tiles, f'{OUTD}/a0_layout_{dpi}dpi.png'))


if __name__ == '__main__':
    main()
