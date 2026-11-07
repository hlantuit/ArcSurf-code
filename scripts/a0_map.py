#!/usr/bin/env python
"""A0 wall map of the pan-Arctic surficial geology (design requested by H. Lantuit 2026-10-06: beautiful, readable, the
geology is the star, subtle hillshade, places / roads, a little in the spirit of old maps, QR code to the PANGAEA DOI).
Revised after the independent design review of the merge-48 sheet (2026-11-04, work_local/map_review_m48/REVIEW.md,
items M1-M9, S1-S17, C1-C12):
  - the sheet names itself: ArcSurf v1.0, edition, licence, citation with DOI, every source agency, licence notices;
  - type: URW Gothic (geometric sans) for title, panel, places and countries, P052 italic for water and landforms;
    real tracking (glyph by glyph, not inserted spaces), sea, ocean and country names curved along the parallels;
  - labels: ~190 curated towns at 6.5 / 8 pt with a dot-collision test, landform names, 0.5 mm halos tinted from the
    ground under them; parallels, Arctic Circle and North Pole labelled; meridian labels only on the frame;
  - colour: palette checked for colour-vision deficiency (work_local/tools/palette_check.py), peat no longer grey,
    anthropogenic patterned, marine units dashed; anti-aliased patterns that the legend swatches reproduce; a lighter
    ocean and lighter insets; a key for the base map; faint borders; roads and railways that print;
  - layout: equal side margins, no sheet border, neatline above the map, panel aligned to the neatlines;
  - print PDF tagged as sRGB (C12): one ICC profile for every colour and an sRGB output intent (scripts/pdf_srgb.py).

Layout: A0 landscape (1189 x 841 mm), Lambert azimuthal equal-area centred on the North Pole (EPSG:6931, Greenwich
down), 1:10 000 000: map face 900 x 770 mm (x -4500..4500 km, y -3400..4300 km), side panel 211 mm.
Layers (bottom up):
  ocean      ETOPO 2022 30" bathymetry, pale blue ramp + very soft hillshade
  land       out-of-domain land: paper tone + hillshade; domain: hclass colours (rasterised at 2x, averaged = anti-aliased
             unit edges), patterns (yedoma hatch, Q stipple, X cross-hatch, M / GM dashes), hillshade multiplied
  vectors    coast, lakes, rivers, borders, roads, railways, graticule, Arctic Circle, names
The rasters are cached without colours (class codes, yedoma, contacts; relief), so a palette or label change costs
minutes, not the ~40 min of rasterising 13 M polygons; the 300 dpi cache also serves 100 and 150 dpi previews.

usage: a0_map.py mockup <name> <cx_km> <cy_km> <w_mm> <h_mm> [--tiles DIR]   true-scale crop, 300 dpi PNG
       a0_map.py layout [--dpi 30] [--tiles DIR] [--pdf]                     whole sheet (PNG preview or print PDF)
  options: --halo MM (label halo width, 0 = none; default 0.5)  --outline A (contact-line opacity, 0 = none; 0.5)
           --tag T (suffix of the output name)
           --doi-data DOI / --doi-paper DOI (the two QR codes: PANGAEA dataset, ESSD paper; placeholders by default)
           --dry (layout test: blank map face, real panel insets)  --fresh (recompute the cached rasters)"""
import functools
import glob
import os
import re
import subprocess
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
from matplotlib.collections import LineCollection, PatchCollection  # noqa: E402
from matplotlib.patches import Circle, PathPatch  # noqa: E402
from matplotlib.path import Path  # noqa: E402
from matplotlib.textpath import TextPath  # noqa: E402
from matplotlib.transforms import Affine2D  # noqa: E402
import matplotlib.patheffects as pe  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
BM = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/basemap'
ETOPO = f'{BM}/ETOPO_2022_v1_30s_N90W180_surface.tif'
NE = f'{BM}/ne'
NE_LAND = '/albedo/work/user/hlantuit/arcticbeach/data/naturalearth/ne_10m_land'
# admin-1 polygons (the boundary-line layers are not on Albedo): borders = lines shared by two polygons
ADMIN1 = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/naturalearth_admin1/ne_10m_admin_1_states_provinces.shp'
OUTD = f'{ROOT}/out/a0'
SCALE = 10_000_000
MM = 1e-3 * SCALE                                   # metres on the ground per mm on paper (10 km)
PT = 25.4 / 72                                      # mm per point
FRAME = (-4_500_000, -3_400_000, 4_500_000, 4_300_000)
# sheet layout, mm from the lower left (review S15: the map hugged the left edge with 9.8 mm free inside an 8 mm sheet
# border; now 30 mm side margins, 35.5 mm top and bottom, no sheet border)
SHEET = (1189.0, 841.0)
MRECT = (30.0, 35.5, 900.0, 770.0)
PRECT = (948.0, 35.5, 211.0, 770.0)

# hclass palette (H. Lantuit 2026-10-07): GSC Surficial Data Model legend chart v2.5.1 (Deblonde et al., GSC Open File
# 8236, 2024, Appendix B), the swatch of each category's undifferentiated unit, read from the vector PDF. Adapted for a
# 1:10M wall map: residual the SDM veneer tint Wv #db918b instead of W #ce6c6c (1.7M km2 of Siberian uplands in full
# red); classes the SDM lacks: Y ice complex (tawny), K thermokarst, H water (pale blue). Design review 2026-11-04,
# checked with CIEDE2000 and the Machado 2009 colour-vision-deficiency simulation (work_local/tools/palette_check.py):
#   - colluvial, till and bedrock 6-19 L* apart (they differed only on the red-green axis; deuteranopic dE00 0.6-3.3):
#     C #f8e2d6 (L* 91), T #c3dcc0 (85), R #dea0a8 (72, a dusty rose: the review's #f2a2aa made the Canadian Shield and
#     Greenland's ice-free margin loud pink); deuteranopic dE00 T-C 4.5, T-R 8.2, C-R 12.4; residual-bedrock 7.0
#   - peat olive-brown #a3977a (the neutral grey #d2d3d5 read as "not mapped")
#   - anthropogenic a neutral grey under a black cross-hatch, the made-ground convention (#c18b8a matched residual)
#   - thermokarst #9ccfd6, bluer (protanopic dE00 0.9 to Q undivided); glaciers and ice sheet a cool #f1f6f9
# The pairs still under 4 dE00 for a colour-blind reader all involve a patterned class (Q, X, M, GM).
# The earlier palettes: PALETTES['merge48'] (the first A0 sheets), PALETTES['arcsurf_v5'].
CLASS_ORDER = ['F', 'T', 'GF', 'GL', 'GM', 'M', 'L', 'K', 'Y', 'E', 'C', 'W', 'O', 'V', 'X', 'I', 'Q', 'H', 'R', 'U']
CODES = {c: i + 1 for i, c in enumerate(CLASS_ORDER)}          # the codes of the cached class rasters: never reorder
PAL = {'F': '#fffac2', 'T': '#c3dcc0', 'GF': '#fecf8c', 'GL': '#d5b5c9', 'GM': '#77bbe7', 'M': '#aae1fa',
       'L': '#afacd5', 'K': '#9ccfd6', 'Y': '#dfa36f', 'E': '#d6c36b', 'C': '#f8e2d6', 'W': '#db918b',
       'O': '#a3977a', 'V': '#ae6882', 'X': '#8a8a8a', 'I': '#f1f6f9', 'Q': '#d8c6c0', 'H': '#cfe8f3',
       'R': '#dea0a8', 'U': '#efeee9'}
PAL_NOTE = ('Class colours after the GSC Surficial Data Model legend v2.5.1 (Deblonde et al. 2024), adapted for '
            'readers with colour-vision deficiency; ice complex, thermokarst and water added.')
NAMES = {'F': 'Fluvial, alluvial, deltaic', 'T': 'Till, morainal', 'GF': 'Glaciofluvial', 'GL': 'Glaciolacustrine',
         'GM': 'Glaciomarine', 'M': 'Marine, littoral', 'L': 'Lacustrine', 'K': 'Thermokarst, alas',
         'Y': 'Ice complex (yedoma)', 'E': 'Aeolian, loess', 'C': 'Colluvial, mass wasting', 'W': 'Residual, weathered',
         'O': 'Organic (peat)', 'V': 'Quaternary volcanic', 'X': 'Anthropogenic (made ground)', 'I': 'Glaciers, ice sheet',
         'Q': 'Quaternary undivided', 'H': 'Water', 'R': 'Bedrock (pre-Quaternary)', 'U': 'Not mapped'}
PALETTES = {
    'merge48': {'F': '#fffac2', 'T': '#c8ddbd', 'GF': '#fecf8c', 'GL': '#d5b5c9', 'GM': '#77bbe7', 'M': '#aae1fa',
                'L': '#afacd5', 'K': '#a3d1c4', 'Y': '#dfa36f', 'E': '#d6c36b', 'C': '#f0cfc0', 'W': '#db918b',
                'O': '#d2d3d5', 'V': '#ae6882', 'X': '#c18b8a', 'I': '#ffffff', 'Q': '#d8c6c0', 'H': '#cfe8f3',
                'R': '#f9b7bb', 'U': '#efeee9'},
    'arcsurf_v5': {'F': '#f4e8a6', 'T': '#d4b58a', 'GF': '#ecb9a1', 'GL': '#b3c2ea', 'GM': '#a6cbc6', 'M': '#92c1cf',
                   'L': '#b4d9ea', 'K': '#a9dccb', 'Y': '#db9a68', 'E': '#f2d07c', 'C': '#c2ab8d', 'W': '#ddd2bf',
                   'O': '#9fb586', 'V': '#b85c50', 'X': '#a6a6a6', 'I': '#fbfdff', 'Q': '#e6dfcf', 'H': '#b4d9ea',
                   'R': '#c9c2ba', 'U': '#efeee9'},
}
PAPER = np.array([0.965, 0.955, 0.93])            # out-of-domain land / margins
# ocean (review S4: the deep blue, L* 77, was darker than most land and its relief the strongest texture on the sheet)
SEA_SHALLOW, SEA_DEEP = np.array([0.845, 0.905, 0.935]), np.array([0.78, 0.85, 0.89])
SEA_RELIEF = (0.97, 0.03)                           # sea x (a + b * hillshade); was 0.92 + 0.08
SHADE = (0.86, 0.14)                                # geology x (a + b * hillshade); was 0.82 + 0.18 (S6: shaded bedrock came
HS_FLAT = np.sin(np.radians(45))                    # within dE00 5.7 of residual). Hillshade of flat ground = sin(45 deg),
FLAT = SHADE[0] + SHADE[1] * HS_FLAT                # so flat geology prints at x0.959: the legend swatches too
ICE_SHADE = (np.array([0.86, 0.89, 0.93]), np.array([0.14, 0.11, 0.07]))   # cool shading on the ice (review C1)
INK = '#3b3a36'
WATER_INK = '#4f7f9f'
SEA_INK = '#3f6987'                                 # water names
LAND_INK = '#5a4632'                                # landform and island names
COUNTRY_INK = '#6a5d52'                             # country and region names
GRAT_INK = '#4f6f88'
CONTACT_INK, ICE_INK = '#4a3b2c', '#7f97ad'
BORDER_INK = '#7d6c5e'
ROAD_INK = '#9a5a48'
LAKE = '#d3e6ef'                                    # Natural Earth lakes, as the shallow sea (was #b8d7e8: 4.7 dE00 from Marine)
SWATCH_EDGE = '#8c8a84'                             # 0.25 pt mid-grey swatch outlines (review C8: 0.4 pt ink round pastels)
# rendering options (CLI): label halo width in mm (0 = none; review M4: 0.2 was too thin), contact-line opacity
OPT = {'halo': 0.5, 'outline': 0.5}
MMU_MM2 = 0.4                                       # print generalisation (review C11), see compose()

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
    'Kane Basin', 'Kennedy Channel', 'Robeson Channel', 'North Magnetic Pole', 'Magnetic Pole', 'Magnetic North Pole',
    # 2026-11-04 (review S11): out-of-domain clutter
    'Hecate Strait', 'Sea of Japan', 'Caspian Sea', 'Yellow Sea', 'Korea Bay', 'East Korea Bay', 'Bohai Sea']
OCEANS = ['Arctic Ocean', 'North Atlantic Ocean', 'North Pacific Ocean']
MAIN_SEAS = ['Barents Sea', 'Kara Sea', 'Laptev Sea', 'East Siberian Sea', 'Chukchi Sea', 'Beaufort Sea', 'Bering Sea',
             'Sea of Okhotsk', 'Hudson Bay', 'Baffin Bay', 'Greenland Sea', 'Norwegian Sea', 'Labrador Sea',
             'Lincoln Sea', 'Pechora Sea', 'White Sea', 'Gulf of Alaska', 'Baltic Sea', 'North Sea', 'Davis Strait',
             'Foxe Basin']
# (lon, lat) a name starts its search from, and the size (pt) of the ocean names (review S12: 12 pt across an ocean
# 400 mm wide); the White Sea polygon takes in the funnel towards the Barents Sea, and the name sat at its mouth
SEA_ANCHOR = {'White Sea': (37.0, 65.4), 'Arctic Ocean': (-150.0, 81.0), 'North Atlantic Ocean': (-33.0, 57.5),
              'North Pacific Ocean': (-152.0, 51.5)}
OCEAN_SIZE = {'Arctic Ocean': 26.0, 'North Atlantic Ocean': 19.0, 'North Pacific Ocean': 19.0}
SEA_SIZE, MINOR_SIZE = 12.0, 7.5                    # main seas; bays, straits, gulfs (review M4: 7 pt at least)
ARC_MIN = 1.6e6                                     # names near the Pole curve no tighter than a 160 mm radius
# romanisation (review M8, C9): Natural Earth mixes ISO 9 and BGN/PCGN; the map uses BGN/PCGN-like forms throughout
NAME_FIX = {'Zvëzdnyj': 'Zvyozdny', 'Matočkin Šar': 'Matochkin Shar', 'Shelikhova Gulf': 'Shelikhov Gulf'}
# names of countries and regions (URW Gothic caps, tracked; 'par' = curved along the parallel), landforms and islands
# (P052 italic; 'mer' = along the meridian), and small islands named on the water beside them (review M3, S11)
# (name, lon, lat, size pt, tracking / 1000 em, orientation)
COUNTRIES = [('Canada', -103.0, 62.0, 17.0, 700, 'par'), ('Russia', 95.0, 62.0, 17.0, 800, 'par'),
             ('Alaska', -150.5, 64.6, 12.0, 400, 'par'), ('Greenland', -40.0, 73.0, 14.0, 500, 'par'),
             ('China', 125.0, 48.0, 11.0, 400, 'par'), ('Iceland', -18.6, 64.9, 8.5, 250, None),
             ('Svalbard', 16.5, 78.6, 8.5, 250, None), ('Norway', 10.5, 62.5, 9.0, 300, None),
             ('Sweden', 16.8, 63.2, 9.0, 300, None), ('Finland', 26.8, 64.2, 9.0, 300, None)]
LANDFORMS = [('Brooks Range', -152.5, 68.1, 10.0, 150, 'par'), ('Mackenzie Mountains', -129.5, 64.0, 9.0, 120, 'mer'),
             ('Canadian Shield', -99.0, 60.0, 13.0, 200, 'par'), ('Hudson Bay Lowland', -86.0, 54.4, 9.5, 120, 'par'),
             ('Ungava Peninsula', -73.5, 60.2, 9.0, 120, 'par'), ('Ural Mountains', 59.6, 63.5, 10.0, 150, 'mer'),
             ('West Siberian Plain', 75.0, 61.2, 13.0, 200, 'par'), ('Yamal Peninsula', 69.6, 70.4, 8.5, 100, 'mer'),
             ('Taymyr Peninsula', 100.0, 74.2, 10.0, 150, 'par'), ('Putorana Plateau', 94.0, 68.8, 9.0, 120, 'par'),
             ('Central Siberian Plateau', 106.0, 64.4, 13.0, 200, 'par'),
             ('Verkhoyansk Range', 129.0, 66.6, 9.5, 120, 'mer'), ('Chersky Range', 145.5, 65.6, 9.5, 120, 'mer'),
             ('Yana–Indigirka Lowland', 142.0, 70.6, 9.0, 120, 'par'), ('Kolyma Lowland', 156.0, 68.9, 9.0, 120, 'par'),
             ('Central Yakutian Lowland', 123.0, 63.2, 9.0, 120, 'par'), ('Chukotka', 172.0, 66.9, 11.0, 250, 'par'),
             ('Kamchatka', 159.0, 56.6, 10.0, 200, 'mer'), ('Kola Peninsula', 36.5, 67.7, 9.0, 120, 'par'),
             ('Seward Peninsula', -164.5, 65.3, 8.0, 100, 'par')]
ISLANDS = [('Novaya Zemlya', 56.0, 74.0, 9.0, 120, 'mer'), ('Severnaya Zemlya', 97.5, 79.4, 9.0, 120, None),
           ('Franz Josef Land', 54.0, 80.8, 9.0, 120, None), ('Ellesmere Island', -79.0, 79.8, 10.0, 150, None),
           ('Baffin Island', -71.0, 68.5, 10.0, 150, None), ('Victoria Island', -109.0, 71.0, 9.5, 120, None),
           ('Banks Island', -121.5, 72.8, 8.5, 100, None), ('Devon Island', -87.5, 75.2, 8.0, 100, None),
           ('Southampton Island', -84.5, 64.5, 8.0, 100, None), ('Mackenzie Delta', -135.0, 68.7, 7.5, 80, None),
           ('Lena Delta', 126.3, 72.8, 7.5, 80, None)]
SEA_SIDE = [('Faroe Islands', -6.9, 62.05, 7.5, 100), ('Wrangel Island', -179.6, 71.25, 8.0, 100),
            ('New Siberian Islands', 141.0, 75.3, 8.5, 100)]
# capes worth a name at 1:10M (review M4: 24 letterspaced 4.6 pt caps, most of them noise); Natural Earth lacks two
CAPES = ['Point Barrow', 'Cape Morris Jesup', 'Nordkapp', 'Nunap Isua', 'Cape York', 'Cape Churchill']
CAPES_ADD = [('Cape Chelyuskin', 104.25, 77.72), ('Cape Dezhnev', -169.65, 66.08)]
N_TOWNS = 190                                       # review S11: ~150-200 curated settlements instead of 549


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


def fix_name(n):
    """Natural Earth name -> map name: NAME_FIX, and no soft-sign apostrophe ("Gulf of Anadyr'" next to the town
    "Anadyr", review M8); an apostrophe inside a word (M'Clure) stays"""
    n = NAME_FIX.get(n, n)
    return re.sub(r"(?<=[A-Za-z])'(?=\s|$)", '', n)


# --- type -----------------------------------------------------------------------------------------------------------
FONTS = {}

try:                                                # matplotlib >= 3.10
    from matplotlib.ft2font import LoadFlags, Kerning
    _NOHINT, _KERN = LoadFlags.NO_HINTING, Kerning.DEFAULT
except ImportError:
    from matplotlib.ft2font import LOAD_NO_HINTING as _NOHINT, KERNING_DEFAULT as _KERN


def fonts():
    """URW base35 OTFs copied into the project (compute nodes have no /usr/share/fonts/urw-base35): URW Gothic, a
    geometric sans after ITC Avant Garde, for the title, legend, panel, places and countries; P052 (Palatino) italic for
    water and landforms, the classic atlas pairing (review S1: one Palatino clone for every role)"""
    for f in glob.glob(f'{ROOT}/pylib/fonts/*.otf'):
        font_manager.fontManager.addfont(f)
    names = {f.name for f in font_manager.fontManager.ttflist}
    sans = 'URW Gothic' if 'URW Gothic' in names else 'DejaVu Sans'
    serif = 'P052' if 'P052' in names else 'DejaVu Serif'
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': [sans, 'DejaVu Sans'],
                         'font.serif': [serif, 'DejaVu Serif']})
    FP = font_manager.FontProperties
    FONTS.update(sans=FP(family=sans), sans_demi=FP(family=sans, weight='demibold'),
                 sans_oblique=FP(family=sans, style='oblique'), serif=FP(family=serif),
                 serif_italic=FP(family=serif, style='italic'), serif_bold=FP(family=serif, weight='bold'))
    print('fonts:', {k: os.path.basename(font_manager.findfont(v)) for k, v in FONTS.items()}, flush=True)
    return sans, serif


def _font(fp, size):
    f = font_manager.get_font(font_manager.findfont(fp))
    f.set_size(size, 72)                            # 72 dpi: advances in points
    return f


def typeset_name(name, fp):
    """the name, or without its diacritics where the font lacks a letter (Utqiaġvik): never a notdef box"""
    import unicodedata
    f = _font(fp, 10)
    if all(f.get_char_index(ord(ch)) for ch in name if not ch.isspace()):
        return name
    plain = ''.join(c for c in unicodedata.normalize('NFKD', name) if not unicodedata.combining(c))
    print(f'font lacks a letter of {name!r}: set as {plain!r}', flush=True)
    return plain


def pen(text, fp, size, track=0.0):
    """pen positions (pt, from the start of the line) of every character of `text` set in fp at `size`, with the
    font's kerning plus `track` thousandths of an em per gap; the glyph advances; the advance of the whole line"""
    f = _font(fp, size)
    x, xs, adv, prev = 0.0, [], [], None
    for ch in text:
        gi = f.get_char_index(ord(ch))
        if prev is not None:
            x += f.get_kerning(prev, gi, _KERN) / 64 + track / 1000 * size
        a = f.load_glyph(gi, flags=_NOHINT).linearHoriAdvance / 65536
        xs.append(x)
        adv.append(a)
        x += a
        prev = gi
    return np.array(xs), np.array(adv), x


@functools.lru_cache(maxsize=None)
def _metrics(fname):
    """cap height, ascender and descender (em) of a font file, read from its H, d and p"""
    f = font_manager.get_font(fname)
    f.set_size(100, 72)                             # 1 em = 100 px

    def g(ch):
        gl = f.load_char(ord(ch), flags=_NOHINT)
        return gl.horiBearingY / 6400, (gl.height - gl.horiBearingY) / 6400
    cap = g('H')[0]
    return {'cap': cap, 'asc': max(cap, g('d')[0]), 'desc': g('p')[1]}


def glyph_layout(x, y, text, fp, size, track=0.0, ha='center', va='center', angle=0.0, arc=None, k=PT * MM):
    """where the glyphs of a one-line label go: origins (axis units) and rotations (deg), and the label's outline (the
    union of its glyph boxes, for the collision test). k = axis units per point (map: metres; panel: mm).
    Straight: anchor (x, y), rotation `angle` (deg, counter-clockwise); untracked straight text stays ONE text object.
    arc: radius of the circle the label follows, centred on the line from (x, y) through the Pole (arc = |(x, y)|: the
    parallel through the anchor; larger: a gentler curve). The text reads left to right and stays upright; each glyph
    is centred on the arc and turned to it (review S12: every name was straight)."""
    xs, adv, W = pen(text, fp, size, track)
    m = _metrics(font_manager.findfont(fp))
    caps = not any(ch.islower() for ch in text)
    top, bot = (m['cap'], 0.02) if caps else (m['asc'], m['desc'])
    vb = {'baseline': 0.0, 'center': -m['cap'] / 2, 'bottom': bot, 'top': -top}[va]         # baseline offset, em
    u0 = {'left': 0.0, 'center': -W / 2, 'right': -W}[ha]
    s = size * k                                    # one em in axis units
    if arc is None:
        c, sn = np.cos(np.radians(angle)), np.sin(np.radians(angle))
        lx0, lx1, ly0, ly1 = u0 * k, (u0 + W) * k, (vb - bot) * s, (vb + top) * s
        corners = np.array([[lx0, ly0], [lx1, ly0], [lx1, ly1], [lx0, ly1]])
        outline = shapely.Polygon(np.c_[x + c * corners[:, 0] - sn * corners[:, 1],
                                        y + sn * corners[:, 0] + c * corners[:, 1]])
        if track == 0:
            o = np.array([[x + c * u0 * k - sn * vb * s, y + sn * u0 * k + c * vb * s]])
            return dict(o=o, rot=np.array([angle]), strs=[text], outline=outline)
        lx, ly = (u0 + xs) * k, vb * s
        o = np.c_[x + c * lx - sn * ly, y + sn * lx + c * ly]
        return dict(o=o, rot=np.full(len(text), angle), strs=list(text), outline=outline)
    r0 = np.hypot(x, y)
    nx, ny = x / r0, y / r0                         # outward from the Pole
    sgn = 1.0 if (-ny > 1e-9 or (abs(ny) <= 1e-9 and nx > 0)) else -1.0        # counter-clockwise reads left to right?
    R = arc
    cx, cy = x - nx * R, y - ny * R                 # centre of the arc
    Rb = R - sgn * vb * s                           # radius of the baseline
    phi0 = np.arctan2(ny, nx)
    sc = (u0 + xs + adv / 2) * k                    # arc length to each glyph's centre
    phi = phi0 + sgn * sc / Rb
    dx, dy = -sgn * np.sin(phi), sgn * np.cos(phi)  # reading direction at each glyph
    px_, py_ = cx + Rb * np.cos(phi), cy + Rb * np.sin(phi)
    o = np.c_[px_ - adv / 2 * k * dx, py_ - adv / 2 * k * dy]
    rot = np.degrees(np.arctan2(dy, dx))
    # glyph boxes: [0, adv] x [-bot, top] em, turned and moved to each origin
    loc = np.stack([np.c_[np.zeros_like(adv), np.full_like(adv, -bot * s)],
                    np.c_[adv * k, np.full_like(adv, -bot * s)],
                    np.c_[adv * k, np.full_like(adv, top * s)],
                    np.c_[np.zeros_like(adv), np.full_like(adv, top * s)]], axis=1)          # (n, 4, 2)
    ux, uy = -dy, dx                                # up
    gx = o[:, None, 0] + loc[..., 0] * dx[:, None] + loc[..., 1] * ux[:, None]
    gy = o[:, None, 1] + loc[..., 0] * dy[:, None] + loc[..., 1] * uy[:, None]
    boxes = shapely.polygons(np.stack([gx, gy], axis=-1))
    outline = shapely.union_all(shapely.buffer(boxes, 0.15 * s, join_style='mitre'))
    return dict(o=o, rot=rot, strs=list(text), outline=outline)


def shift_layout(L, dx, dy):
    return dict(o=L['o'] + [dx, dy], rot=L['rot'], strs=L['strs'],
                outline=shapely.transform(L['outline'], lambda c: c + [dx, dy]))


def draw_layout(ax, L, fp, size, color, zorder, halo=None, k=PT * MM):
    """draw a glyph layout as text (searchable in the PDF: the merge-48 sheet drew every haloed name as outlines) with
    the halo as ONE compound outline path under it: halo = (stroke width mm, rgb, alpha). Tracked and curved names are
    one text object per glyph; their halos still merge into one path, so neighbouring letters' halos do not overlap."""
    paths = []
    for (ox, oy), r, t in zip(L['o'], L['rot'], L['strs']):
        if not t.strip():
            continue
        ax.text(ox, oy, t, fontproperties=fp, fontsize=size, rotation=r, rotation_mode='anchor', ha='left',
                va='baseline', color=color, zorder=zorder)
        if halo:
            p = TextPath((0, 0), t, size=size, prop=fp)
            paths.append(p.transformed(Affine2D().scale(k).rotate_deg(r).translate(ox, oy)))
    if halo and paths:
        w, col, a = halo
        ax.add_patch(PathPatch(Path.make_compound_path(*paths), fc=col, ec=col, lw=w / PT, alpha=a, joinstyle='round',
                               capstyle='round', zorder=zorder - 0.05))


def ptext(ax, x, y, text, fp, size, color=INK, ha='left', va='baseline', track=0.0, zorder=5):
    """panel text (axis units mm), tracked if asked; returns its width in mm"""
    L = glyph_layout(x, y, text, fp, size, track, ha, va, k=PT)
    draw_layout(ax, L, fp, size, color, zorder, k=PT)
    return pen(text, fp, size, track)[2] * PT


def cap_mm(fp, size):
    return _metrics(font_manager.findfont(fp))['cap'] * size * PT


def paragraph(ax, x, ytop, runs, measure, size, leading, color=INK, draw=True):
    """runs [(text, FontProperties)] set ragged right on a `measure` (mm) from the top-left (x, ytop); '\\n' breaks the
    line. Words keep their run's font, so run-in labels in the demi weight sit inside the lines (review S14: eight
    hard-broken lines of 7 pt italic, 73-166 mm long). Returns the y of the last baseline."""
    toks = []
    for text, fp in runs:
        for t in re.findall(r'\n| |[^ \n]+', text):
            if len(t) > 1 and pen(t, fp, size)[2] * PT > measure:      # a URL longer than the line breaks after '/'
                toks += [(p, fp) for p in re.findall(r'.+?(?:/+|$)', t)]
            else:
                toks.append((t, fp))
    lines, cur, w = [], [], 0.0
    for t, fp in toks:
        if t == '\n':
            lines.append(cur)
            cur, w = [], 0.0
            continue
        tw = pen(t, fp, size)[2] * PT
        if t == ' ':
            if cur:
                cur.append((t, fp, tw))
                w += tw
            continue
        if cur and w + tw > measure:
            while cur and cur[-1][0] == ' ':
                w -= cur.pop()[2]
            lines.append(cur)
            cur, w = [], 0.0
        cur.append((t, fp, tw))
        w += tw
    if cur:
        lines.append(cur)
    y = ytop - cap_mm(runs[0][1], size)
    for ln in lines:
        while ln and ln[-1][0] == ' ':
            ln.pop()
        chunks = []
        for t, fp, tw in ln:
            if chunks and chunks[-1][1] is fp:
                chunks[-1][0] += t
                chunks[-1][2] += tw
            else:
                chunks.append([t, fp, tw])
        xx = x
        for t, fp, tw in chunks:
            if draw:
                ax.text(xx, y, t, fontproperties=fp, fontsize=size, ha='left', va='baseline', color=color, zorder=5)
            xx += tw
        y -= leading
    return y + leading


# --- rasters --------------------------------------------------------------------------------------------------------
def hex2rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])


def grid(bounds, px):
    x0, y0, x1, y1 = bounds
    W, H = int(round((x1 - x0) / px)), int(round((y1 - y0) / px))
    return Affine(px, 0, x0, 0, -px, y1), (H, W)


@functools.lru_cache(maxsize=None)
def _to6931():
    from pyproj import Transformer
    return Transformer.from_crs(4326, 6931, always_xy=True)


def lonlat(lon, lat):
    return _to6931().transform(lon, lat)


def classes(bounds, px, tiles_dir, ss=2):
    """class codes (CODES) and the IRYP v2 yedoma 'yes' mask on the ss x supersampled print grid"""
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
    return cls, yed


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


def class_cache(bounds, px, dpi, tiles_dir, fresh=False):
    """the map face without colours, cached (out/a0/a0_classes_<dpi>dpi_<tiles>.npz): class codes and yedoma on the 2x
    grid, contact masks on the print grid (quarters of a pixel, 0..4). A 300 dpi cache also serves 100 and 150 dpi
    previews (every 3rd / 2nd supersampled pixel). Delete the file, or pass --fresh, after a new merge."""
    tname = os.path.basename(os.path.normpath(tiles_dir))
    path = lambda d: f'{OUTD}/a0_classes_{d}dpi_{tname}.npz'          # noqa: E731
    if os.path.exists(path(dpi)) and not fresh:
        z = np.load(path(dpi))
        print('class rasters from', path(dpi), flush=True)
        return {k: z[k] for k in z.files}
    _, (H0, W0) = grid(bounds, px)
    if dpi < 300 and 300 % dpi == 0 and os.path.exists(path(300)) and not fresh:
        st = 300 // dpi
        o = (st - 1) // 2
        z = np.load(path(300))
        c = {k: np.ascontiguousarray(z[k][o::st, o::st][:2 * H0, :2 * W0]) for k in ('cls', 'yed')}
        print(f'class rasters: every {st}th supersampled pixel of {path(300)}', flush=True)
    else:
        cls, yed = classes(bounds, px, tiles_dir)
        c = {'cls': cls, 'yed': yed}
    if c['cls'].shape != (2 * H0, 2 * W0):
        raise ValueError(f'class raster {c["cls"].shape} does not match the print grid {(2 * H0, 2 * W0)}')
    if OPT['outline'] > 0 and px / MM <= 0.2:
        for k, v in contacts(c['cls'], px / 2 / MM).items():
            c[f'edge_{k}'] = v.reshape(H0, 2, W0, 2).sum((1, 3), dtype=np.uint8)
    np.savez_compressed(path(dpi), **c)
    return c


def relief(bounds, px):
    """ETOPO 2022 elevation on the grid (bilinear)"""
    tr, shp = grid(bounds, px)
    z = np.full(shp, np.nan, np.float32)
    with rasterio.open(ETOPO) as src:
        reproject(rasterio.band(src, 1), z, dst_transform=tr, dst_crs='EPSG:6931', resampling=Resampling.bilinear,
                  dst_nodata=np.nan)
    return z


def hillshade(z, px):
    zz = np.nan_to_num(z, nan=0.0)
    gy, gx = np.gradient(zz, px)
    az, alt, zf = np.radians(315), np.radians(45), 3.0                 # light from the NW, exaggerated a little
    slope = np.arctan(zf * np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1).astype(np.float32)


def relief_cache(bounds, px, dpi, fresh=False):
    f = f'{OUTD}/a0_relief_{dpi}dpi.npz'
    if bounds == FRAME and os.path.exists(f) and not fresh:
        return np.load(f)['z']
    z = relief(bounds, px)
    if bounds == FRAME:
        np.savez_compressed(f, z=z)
    return z


def land_mask(bounds, px):
    tr, shp = grid(bounds, px)
    g = _land()
    g = g[shapely.intersects(g.geometry.values, shapely.box(*bounds))]
    m = np.zeros(shp, np.uint8)
    if len(g):
        rasterio.features.rasterize([(q, 1) for q in g.geometry.values], out=m, transform=tr)
    return m.astype(bool)


# patterns, anti-aliased (coverage of each pixel, box filter), positions in mm on paper (y up) (review C6: the binary
# hatch and stipple stair-stepped)
def lines_cov(x, y, pxmm, spacing, width, angle):
    """parallel lines running at `angle` (deg), `spacing` apart, `width` wide"""
    a = np.radians(angle)
    u = -x * np.sin(a) + y * np.cos(a)
    d = np.abs(u - spacing * np.round(u / spacing))
    return np.clip((width / 2 - d) / pxmm + 0.5, 0, 1)


def dots_cov(x, y, pxmm, spacing, dot):
    """dot screen, every other row offset by half a step"""
    j = np.floor(y / spacing)
    xo = x + 0.5 * spacing * (j % 2)
    d = np.hypot(xo - (np.floor(xo / spacing) + 0.5) * spacing, y - (j + 0.5) * spacing)
    return np.clip((dot / 2 - d) / pxmm + 0.5, 0, 1)


def dash_cov(x, y, pxmm, row, period, length, width):
    """horizontal dashes, rows `row` apart, every other row offset by half a period (the marine-sediment ornament)"""
    j = np.floor(y / row)
    dy = np.abs(y - (j + 0.5) * row)
    t = np.mod(x + 0.5 * period * (j % 2), period)
    e = np.where(t < length, -np.minimum(t, length - t), np.minimum(t - length, period - t))
    return np.clip((width / 2 - dy) / pxmm + 0.5, 0, 1) * np.clip(0.5 - e / pxmm, 0, 1)


# class -> [(coverage(x, y, pxmm), ink rgb, opacity)]: Q stipple (mapped but undifferentiated, not a gap), X black
# cross-hatch (made ground; review M6), M / GM horizontal dashes (marine; review S5: Marine read as lakes, Glaciomarine
# as Hudson Bay)
PATTERNS = {
    'Q': [(lambda x, y, p: dots_cov(x, y, p, 0.9, 0.16), (0.45, 0.40, 0.33), 0.35)],
    'X': [(lambda x, y, p: lines_cov(x, y, p, 0.7, 0.15, 45), (0.0, 0.0, 0.0), 0.55),
          (lambda x, y, p: lines_cov(x, y, p, 0.7, 0.15, -45), (0.0, 0.0, 0.0), 0.55)],
    'M': [(lambda x, y, p: dash_cov(x, y, p, 0.9, 1.5, 0.75, 0.12), (0.16, 0.36, 0.53), 0.45)],
    'GM': [(lambda x, y, p: dash_cov(x, y, p, 0.9, 1.5, 0.75, 0.12), (0.12, 0.27, 0.42), 0.40)]}
# IRYP v2 Yedoma domain: dark umber lines over the unit colour
YEDOMA = (lambda x, y, p: lines_cov(x, y, p, 0.95, 0.13, 45), (0.35, 0.22, 0.12), 0.45)


def overlay(out, frac, pattern, pxmm, r0=0, c0=0):
    """blend a pattern into out (H, W, 3) where frac (H, W) > 0, weighted by frac; (r0, c0) = the pixel offset of out
    on the sheet, so patterns stay continuous"""
    cov, ink, alpha = pattern
    r, c = np.nonzero(frac > 0)
    if not len(r):
        return
    x, y = (c + c0 + 0.5) * pxmm, -(r + r0 + 0.5) * pxmm
    a = (alpha * cov(x, y, pxmm) * frac[r, c]).astype(np.float32)[:, None]
    out[r, c] = out[r, c] * (1 - a) + np.asarray(ink, np.float32)[None] * a


def generalise(dom, land, px):
    """print generalisation (review C11: the domain edge in isolated-patch country - Amur, Baikal-Bratsk, NE British
    Columbia - was moth-eaten speckle): inland mapped patches smaller than MMU_MM2 go to the out-of-domain tone, inland
    gaps smaller than MMU_MM2 inside the domain take their nearest mapped colour. Islets (patches touching the sea)
    stay. Returns (drop, fill) masks."""
    n = MMU_MM2 / (px / MM) ** 2
    st = np.ones((3, 3), bool)
    d = dom > 0.5
    lab, k = ndi.label(d, structure=st)
    size = np.bincount(lab.ravel(), minlength=k + 1)
    coast = np.unique(lab[ndi.binary_dilation(~land, structure=st) & d])
    small = size < n
    small[0] = False
    small[coast] = False
    drop = small[lab]
    gaps = land & ~d
    lab, k = ndi.label(gaps, structure=st)
    size = np.bincount(lab.ravel(), minlength=k + 1)
    small = size < n
    small[0] = False
    edge = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    small[edge] = False
    fill = small[lab]
    print(f'print generalisation: {int(drop.sum()):,} px of inland specks dropped, {int(fill.sum()):,} px of gaps '
          f'filled (< {MMU_MM2} mm2 = {n:.0f} px)', flush=True)
    return drop, fill


def compose(bounds, px, c, z=None, mmu=True):
    """RGB of the map face from the class rasters c (class_cache, or classes() for a crop) and the elevation z"""
    cls2, yed2 = c['cls'], c['yed']
    H, W = cls2.shape[0] // 2, cls2.shape[1] // 2
    down = lambda a: a[:2 * H, :2 * W].reshape(H, 2, W, 2).mean((1, 3), dtype=np.float32)    # noqa: E731
    lut = np.zeros((len(CODES) + 1, 3), np.float32)
    for k, i in CODES.items():
        lut[i] = hex2rgb(PAL[k])
    rgb = np.empty((H, W, 3), np.float32)
    for r0 in range(0, H, 1024):                    # mean of the 2 x 2 sub-pixel colours, in blocks of rows
        r1 = min(H, r0 + 1024)
        rgb[r0:r1] = lut[cls2[2 * r0:2 * r1, :2 * W]].reshape(r1 - r0, 2, W, 2, 3).mean((1, 3))
    dom = down(cls2 > 0)
    ice = down(cls2 == CODES['I'])
    if z is None:
        z = relief(bounds, px)
    z = z[:H, :W]
    hs = hillshade(z, px)
    land = land_mask(bounds, px)[:H, :W] | (dom > 0.5)
    # ocean: depth ramp + very soft shading
    d = np.clip(-np.nan_to_num(z, nan=0) / 4000.0, 0, 1) ** 0.7
    out = (SEA_SHALLOW[None, None] * (1 - d[..., None]) + SEA_DEEP[None, None] * d[..., None]).astype(np.float32)
    out *= (SEA_RELIEF[0] + SEA_RELIEF[1] * hs)[..., None]
    # land outside the domain: paper + hillshade
    out[land] = (PAPER[None, None] * (0.80 + 0.20 * hs)[..., None])[land]
    # domain geology: colour x subtle hillshade; ice: cool shading
    geo = rgb * (SHADE[0] + SHADE[1] * hs)[..., None]
    icy = ice > 0.5
    geo[icy] = rgb[icy] * (ICE_SHADE[0][None] + ICE_SHADE[1][None] * hs[icy][:, None])
    if mmu:
        drop, fill = generalise(dom, land, px)
        dom[drop] = 0.0
        if fill.any():
            idx = ndi.distance_transform_edt(dom <= 0.5, return_distances=False, return_indices=True)
            geo[fill] = geo[idx[0][fill], idx[1][fill]]
            dom[fill] = 1.0
            del idx
    a = np.clip(dom, 0, 1)[..., None]
    out = out * (1 - a) + geo * a
    pxmm = px / MM
    for k, pats in PATTERNS.items():
        f = down(cls2 == CODES[k]) * (dom > 0.5)
        for p in pats:
            overlay(out, f, p, pxmm)
    overlay(out, down(yed2) * (dom > 0.5), YEDOMA, pxmm)
    # hairline contacts on top: umber between units, grey-blue round the ice, blue round water bodies
    for k, col in (('geo', CONTACT_INK), ('ice', ICE_INK), ('water', WATER_INK)):
        if f'edge_{k}' in c:
            a = (OPT['outline'] * c[f'edge_{k}'][:H, :W].astype(np.float32) / 4 * (dom > 0.5))[..., None]
            out = out * (1 - a) + hex2rgb(col).astype(np.float32)[None, None] * a
    return np.clip(out, 0, 1), dom > 0.5


def swatch_rgb(key, w_mm, h_mm, dpi):
    """a legend swatch as the map prints flat ground: class colour x FLAT, ice with its cool shading, its pattern at
    the map's metrics (review S6: flat colours, a black '////' hatch and 1.5 mm dots that the map never shows).
    key: a class, 'U' (paper), 'yedoma' (the hatch over white), 'Y+' (ice complex inside the Yedoma domain)"""
    pxmm = 25.4 / dpi
    nw, nh = max(2, int(round(w_mm / pxmm))), max(2, int(round(h_mm / pxmm)))
    if key == 'U':
        base = PAPER * (0.80 + 0.20 * HS_FLAT)
    elif key == 'yedoma':
        base = np.ones(3) * FLAT
    elif key == 'I':
        base = hex2rgb(PAL['I']) * (ICE_SHADE[0] + ICE_SHADE[1] * HS_FLAT)
    else:
        base = hex2rgb(PAL[key.rstrip('+')]) * FLAT
    out = np.empty((nh, nw, 3), np.float32)
    out[:] = base
    one = np.ones((nh, nw), np.float32)
    for p in PATTERNS.get(key, []):
        overlay(out, one, p, pxmm)
    if key in ('yedoma', 'Y+'):
        overlay(out, one, YEDOMA, pxmm)
    return np.clip(out, 0, 1)


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


def borders(bounds, tol=1_000.0):
    """international boundaries and Canadian province / territory boundaries (review C10: the straight seams of the
    data follow borders and sheet edges; faint borders explain the first kind), from the Natural Earth admin-1
    polygons: the part of a polygon's outline within 200 m of a neighbour of another country (international) or of
    another Canadian province (provincial). EPSG:6931 lines (n, 2), clipped to bounds."""
    try:
        a = gpd.read_file(ADMIN1, bbox=(-180, 30, 180, 90))
    except Exception as e:
        print('borders not drawn:', str(e)[:120], flush=True)
        return [], []
    a.columns = [c if c == 'geometry' else c.lower() for c in a.columns]
    a = a[a.geometry.notna()].copy()
    a['geometry'] = shapely.intersection(shapely.make_valid(a.geometry.values), shapely.box(-180, 30, 180, 90))
    a = a[~a.geometry.is_empty]
    ctry = a.dissolve('adm0_a3').reset_index()

    def shared(g):
        geom = np.asarray(g.geometry.values, dtype=object)
        tree = shapely.STRtree(geom)
        i, j = tree.query(geom, predicate='intersects')
        m = i < j
        nv = shapely.get_num_coordinates(geom)
        out = []
        for p, q in zip(i[m], j[m]):
            if nv[q] > nv[p]:                       # buffer the simpler of the two (Russia's outline is huge)
                p, q = q, p
            ln = shapely.intersection(shapely.boundary(geom[p]), shapely.buffer(geom[q], 0.002))
            out += [c for c in _lines([ln]) if len(c) >= 2]
        return out

    def proj(lines):
        if not lines:
            return []
        s = gpd.GeoSeries([shapely.LineString(c) for c in lines], crs=4326).to_crs(6931)
        g = shapely.simplify(shapely.intersection(np.asarray(s.values, dtype=object), shapely.box(*bounds)), tol)
        return _lines(g)
    can = a[a['adm0_a3'] == 'CAN']
    return proj(shared(ctry)), proj(shared(can))


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
        return [name]
    i = min(range(1, len(w)), key=lambda i: max(len(' '.join(w[:i])), len(' '.join(w[i:]))))
    return [' '.join(w[:i]), ' '.join(w[i:])]


def reading_angle(x, y):
    """angle (deg) of the parallel through (x, y), turned to read left to right"""
    a = np.degrees(np.arctan2(x, -y))               # tangent (-y, x)
    return (a + 90) % 180 - 90


def meridian_angle(lon):
    """angle (deg) of the meridian `lon` on the map, turned to read left to right"""
    return (lon - 90 + 90) % 180 - 90


class Labels:
    """greedy placement with exact outlines (union of the glyph boxes): a label is drawn only if its outline clears
    every label and town dot placed before it, stays inside the frame (1.5 mm off the neatline) and, for names of water
    and capes, off the land. Callers try candidates in priority order. clamp=True slides an area name that crosses the
    frame back inside (point labels try their next position instead). Halos are tinted from the ground under the
    label (bg), so a name on the sea gets a pale blue halo, not a cream patch."""
    def __init__(self, ax, frame, bg=None):
        self.ax, self.frame, self.bg = ax, frame, bg
        shapely.prepare(frame)
        self.geoms, self._tree, self.log = [], None, []

    def add(self, g):
        self.geoms.append(g)
        self._tree = None

    def free(self, g, pad):
        if not self.geoms:
            return True
        if self._tree is None:
            self._tree = shapely.STRtree(self.geoms)
        return len(self._tree.query(shapely.buffer(g, pad * MM), predicate='intersects')) == 0

    def halo(self, g):
        if OPT['halo'] <= 0:
            return None
        b = np.asarray(self.bg(g) if self.bg is not None else PAPER, float)
        return (OPT['halo'], tuple(np.clip(b + 0.62 * (1 - b), 0, 1)), 0.85)

    def fit(self, L, clamp):
        """the layout if it lies inside the frame; with clamp, a name that crosses the frame is slid back inside by up
        to 25 mm (a name whose anchor lies outside the frame, as in a crop, is dropped)"""
        o = L['outline']
        if self.frame.contains(o):
            return L
        if not clamp or not self.frame.intersects(o):
            return None
        fx0, fy0, fx1, fy1 = self.frame.bounds
        bx0, by0, bx1, by1 = o.bounds
        if bx1 - bx0 > fx1 - fx0 or by1 - by0 > fy1 - fy0:
            return None
        dx, dy = max(0.0, fx0 - bx0) - max(0.0, bx1 - fx1), max(0.0, fy0 - by0) - max(0.0, by1 - fy1)
        if np.hypot(dx, dy) > 25 * MM:
            return None
        L = shift_layout(L, dx, dy)
        return L if self.frame.contains(L['outline']) else None

    def place(self, x, y, text, fp, size, color, track=0.0, ha='center', va='center', angle=0.0, arc=None, pad=0.5,
              clamp=False, avoid=None, halo=True, zorder=9.5, kind=''):
        """one-line label; True if drawn"""
        L = self.fit(glyph_layout(x, y, text, fp, size, track, ha, va, angle, arc), clamp)
        return L is not None and self._draw([L], fp, size, color, pad, avoid, halo, zorder, kind, text)

    def place_lines(self, x, y, lines, fp, size, color, pad=0.5, avoid=None, halo=True, zorder=9.5, kind=''):
        """several straight lines centred on (x, y)"""
        lead = 1.15 * size * PT * MM
        Ls = [glyph_layout(x, y + (len(lines) - 1) / 2 * lead - i * lead, t, fp, size) for i, t in enumerate(lines)]
        if not all(self.frame.contains(L['outline']) for L in Ls):
            return False
        return self._draw(Ls, fp, size, color, pad, avoid, halo, zorder, kind, ' / '.join(lines))

    def _draw(self, Ls, fp, size, color, pad, avoid, halo, zorder, kind, text):
        o = shapely.union_all([L['outline'] for L in Ls])
        if not self.free(o, pad):
            return False
        if avoid is not None and avoid.intersects(shapely.buffer(o, 0.3 * MM)):
            return False
        h = self.halo(o) if halo else None
        for L in Ls:
            draw_layout(self.ax, L, fp, size, color, zorder, h)
        self.add(o)
        self.log.append((kind, text, size))
        return True


def bg_sampler(img, bounds, px):
    """mean colour (0..1) of the composed map face under a geometry's bounding box"""
    x0, y0, x1, y1 = bounds

    def bg(g):
        bx0, by0, bx1, by1 = g.bounds
        c0, c1 = max(0, int((bx0 - x0) / px)), max(1, int((bx1 - x0) / px) + 1)
        r0, r1 = max(0, int((y1 - by1) / px)), max(1, int((y1 - by0) / px) + 1)
        sub = img[r0:r1:2, c0:c1:2]
        return sub.reshape(-1, 3).mean(0) / 255.0 if sub.size else PAPER
    return bg


def vectors(ax, bounds, bg=None):
    """linework and names in map coordinates (metres); line widths in points at print scale. Roads, railways and
    places only inside the mapped domain (outside it the full-sheet preview was crowded with southern Canada and
    Fennoscandia); outside it, only national capitals north of 55N. Returns the Labels (the log of placed names)."""
    box = shapely.box(*bounds)
    dom = _domain()
    lw = lambda mm: mm / PT                                           # noqa: E731  mm -> points
    ax.add_collection(LineCollection(_coast(bounds), colors=WATER_INK, linewidths=lw(0.12), zorder=5))
    lakes = ne('ne_10m_lakes')
    if lakes is not None:
        lakes = lakes[shapely.intersects(lakes.geometry.values, box) & (lakes['scalerank'] <= 6)]
        lakes.plot(ax=ax, color=LAKE, edgecolor=WATER_INK, linewidth=lw(0.08), zorder=6)
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
            ax.add_collection(LineCollection(_lines(d.geometry.values), colors=WATER_INK,
                                             linewidths=lw(max(0.10, 0.32 - 0.035 * sr)), zorder=7))
    intl, prov = borders(bounds)
    ax.add_collection(LineCollection(prov, colors=BORDER_INK, linewidths=lw(0.14), alpha=0.65,
                                     linestyles=[(0, (1.2, 2.4))], zorder=4.6))
    ax.add_collection(LineCollection(intl, colors=BORDER_INK, linewidths=lw(0.22), alpha=0.75,
                                     linestyles=[(0, (7, 2.2, 1.4, 2.2))], zorder=4.7))
    # communications (H.L. 2026-10-06: roads were too strong; 2026-10-22: still too prominent, and they ran beyond the
    # mapped zone; review S10 2026-11-04: at 0.06-0.09 mm and 40-55 % they did not print, and rail could not be told
    # from road): roads 0.10-0.13 mm at 50-60 %, railways a 0.12 mm line with 0.08 mm cross ticks, both in the key;
    # clipped to the domain itself, never across lakes (a railway ferry drew a line over Lake Baikal), no ferries
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
        ax.add_collection(LineCollection(_lines(rail.geometry.values), path_effects=RAIL_EFFECTS, **RAIL_STYLE))
    roads = ne('ne_10m_roads')
    if roads is not None:
        roads = roads[shapely.intersects(roads.geometry.values, box) & roads['type'].isin(list(ROAD_STYLE))]
        roads = _clip_lines(roads)
        for typ, (w_, a_) in ROAD_STYLE.items():
            ax.add_collection(LineCollection(_lines(roads[roads['type'] == typ].geometry.values), colors=ROAD_INK,
                                             linewidths=lw(w_), alpha=a_, zorder=8.5))
    # graticule: parallels every 10 deg, meridians every 30 deg to the Pole, Arctic Circle dashed
    lons = np.linspace(-180, 180, 721)
    grat = []
    for lat in range(40, 90, 10):
        grat.append(shapely.LineString(np.c_[lons, np.full_like(lons, lat)]))
    for lon in range(-180, 180, 30):
        grat.append(shapely.LineString(np.c_[np.full(60, lon), np.linspace(35, 90, 60)]))
    g = gpd.GeoSeries(grat, crs=4326).to_crs(6931)
    ax.add_collection(LineCollection(_lines(g.values), colors=GRAT_STYLE['color'], linewidths=lw(0.08),
                                     alpha=GRAT_STYLE['alpha'], zorder=4))
    ac = gpd.GeoSeries([shapely.LineString(np.c_[lons, np.full_like(lons, 66.5622)])], crs=4326).to_crs(6931)
    ax.add_collection(LineCollection(_lines(ac.values), colors=GRAT_STYLE['color'], linewidths=lw(0.16),
                                     linestyles=[(0, (6, 4))], zorder=4))
    lab = Labels(ax, frame=box.buffer(-1.5 * MM), bg=bg)              # labels keep 1.5 mm off the neatline
    land = shapely.union_all(shapely.make_valid(_land().geometry.values))   # labels of water stay off land
    shapely.prepare(land)
    F = FONTS
    # 1. graticule (review S9): parallels on their line just east of the 0 deg meridian, the Arctic Circle in the
    # Norwegian Sea, a cross and a name at the Pole
    for lat in (60, 70, 80):
        x, y = lonlat(0.0, lat)
        r = np.hypot(x, y)
        a = 9 * MM / r
        lab.place(r * np.sin(a), -r * np.cos(a), f'{lat}°N', F['serif_italic'], 7.5, GRAT_INK, arc=r, zorder=9.2,
                  kind='graticule')
    x, y = lonlat(-6.0, 66.5622)
    lab.place(x, y, 'Arctic Circle', F['serif_italic'], 7.5, GRAT_INK, track=40, arc=np.hypot(x, y), zorder=9.2,
              kind='graticule')
    for dx, dy in (((-1.6, 1.6), (0, 0)), ((0, 0), (-1.6, 1.6))):
        ax.plot(np.array(dx) * MM, np.array(dy) * MM, color=INK, lw=lw(0.25), zorder=9.2, solid_capstyle='butt')
    lab.place(1.4 * MM, -1.4 * MM, 'North Pole', F['serif_italic'], 7.5, INK, ha='left', va='top', zorder=9.2,
              kind='graticule')
    lab.add(shapely.box(-1.8 * MM, -1.8 * MM, 1.8 * MM, 1.8 * MM))
    # 2. oceans and main seas, 3. major towns, 4. countries, landforms, islands, 5. other towns, 6. bays and straits,
    # 7. capes
    sea_names(lab, box, land, ranks=(0, 1))
    pp = towns(box, dom)
    place_towns(ax, lab, pp[pp['major']], N_TOWNS)
    for name, lo, la, size, track, orient in COUNTRIES:
        area_name(lab, name.upper(), lo, la, F['sans'], size, COUNTRY_INK, track, orient, 'country')
    for name, lo, la, size, track, orient in LANDFORMS + ISLANDS:
        area_name(lab, name, lo, la, F['serif_italic'], size, LAND_INK, track, orient, 'landform')
    for name, lo, la, size, track in SEA_SIDE:
        beside(lab, name, lo, la, F['serif_italic'], size, LAND_INK, track, land, (2.5, 4.0, 6.0), 'island')
    n_major = sum(1 for k, *_ in lab.log if k == 'town')
    place_towns(ax, lab, pp[~pp['major']], N_TOWNS - n_major)
    sea_names(lab, box, land, ranks=(2,))
    rp = ne('ne_10m_geography_regions_points')
    capes = list(CAPES_ADD)
    if rp is not None:
        rp = rp[rp['name'].isin(CAPES)]
        capes += [(str(r['name']), *lonlat_inv(r.geometry.x, r.geometry.y)) for _, r in rp.iterrows()]
    for name, lo, la in capes:
        beside(lab, name, lo, la, F['serif_italic'], 6.8, LAND_INK, 0, land, (1.2, 2.2, 3.5), 'cape')
    draw_dots(ax)
    miss = sorted(_DROP - _HIT)
    print(f'labels: {len(_HIT)} of {len(_DROP)} names of DROP_NAMES matched; not found: {miss}', flush=True)
    kinds = pd.Series([k for k, *_ in lab.log]).value_counts().to_dict()
    print(f'labels placed: {len(lab.log)} {kinds}', flush=True)
    for k in ('country', 'landform', 'island', 'ocean', 'sea'):
        print(f'  {k}:', ', '.join(f'{t} {s:g}' for kk, t, s in lab.log if kk == k), flush=True)
    return lab


@functools.lru_cache(maxsize=None)
def _to4326():
    from pyproj import Transformer
    return Transformer.from_crs(6931, 4326, always_xy=True)


def lonlat_inv(x, y):
    return _to4326().transform(x, y)


RAIL_STYLE = dict(colors=INK, linewidths=0.12 / PT, alpha=0.6, zorder=8)
RAIL_EFFECTS = [pe.TickedStroke(spacing=1.6 / PT, angle=90, length=0.14, linewidth=0.08 / PT),
                pe.TickedStroke(spacing=1.6 / PT, angle=-90, length=0.14, linewidth=0.08 / PT), pe.Normal()]
ROAD_STYLE = {'Road': (0.10, 0.50), 'Secondary Highway': (0.11, 0.55), 'Major Highway': (0.13, 0.60)}
GRAT_STYLE = dict(color='#6b8aa3', alpha=0.55)


def sea_names(lab, box, land, ranks):
    """oceans and main seas: italic capitals, tracked, curved along the parallel where it runs within 50 deg of the
    horizontal, smaller only if they do not fit; bays and straits: italic lower case, on one line or two, 7 pt at least
    (review M4, S12); never on land"""
    mp = ne('ne_10m_geography_marine_polys')
    if mp is None:
        return
    oceans, seas = {_norm(n) for n in OCEANS}, {_norm(n) for n in MAIN_SEAS}
    mp = mp[shapely.intersects(mp.geometry.values, box) & mp['name'].notna()].copy()
    mp['rank'] = [0 if _norm(n) in oceans else (1 if _norm(n) in seas else 2) for n in mp['name']]
    mp = mp[mp['rank'].isin(ranks)].sort_values(['rank', 'scalerank'])
    fp = FONTS['serif_italic']
    for _, r in mp.iterrows():
        name = fix_name(str(r['name']))
        if (r['rank'] == 2 and dropped(name)) or _norm(name) in _DROP:     # oceans and main seas: exact names only
            continue
        try:
            poly = shapely.intersection(r.geometry, box.buffer(-6 * MM))
        except shapely.errors.GEOSException:          # one bad polygon costs one label, not the render
            continue
        if poly.is_empty:
            continue
        near = SEA_ANCHOR.get(name)
        if near is not None:
            near = lonlat(*near)
            if name == 'White Sea':                   # within 150 km of the anchor, smaller rather than elsewhere
                poly = shapely.Point(near).buffer(150_000.0)
        spots = water_spots(poly, near=near)
        rank = r['rank']
        if rank < 2:
            size0 = OCEAN_SIZE.get(name, SEA_SIZE)
            track = 220 if rank == 0 else 150
            sizes = sorted({size0, round(0.85 * size0, 1), max(8.5, round(0.72 * size0, 1))}, reverse=True)
            done = False
            for s in sizes:
                for curved in (True, False):
                    for x, y in spots[:80 if curved else 250]:
                        arc = None
                        if curved:
                            if abs(reading_angle(x, y)) > 50:
                                continue
                            arc = max(np.hypot(x, y), ARC_MIN)
                        if lab.place(x, y, name.upper(), fp, s, SEA_INK, track=track, arc=arc, avoid=land, halo=False,
                                     clamp=rank == 0, zorder=9.0, kind='ocean' if rank == 0 else 'sea'):
                            done = True
                            break
                    if done:
                        break
                if done:
                    break
        else:
            for s in (MINOR_SIZE, 7.0):
                if any(lab.place(x, y, name, fp, s, SEA_INK, avoid=land, halo=False, zorder=9.0, kind='water')
                       for x, y in spots[:250]):
                    break
                if len(name.split()) > 1 and any(lab.place_lines(x, y, _two_lines(name), fp, s, SEA_INK, avoid=land,
                                                                 halo=False, zorder=9.0, kind='water')
                                                 for x, y in spots[:250]):
                    break


def towns(box, dom):
    """settlements (review S11): Natural Earth places in the mapped domain, without 'Historic place' entries and
    places of population 0 (abandoned Ambarchik outranked Chersky); outside the domain only national capitals north of
    55N. Ordered by importance: cities of 100 000 or more and capitals ('major', 8 pt), then Natural Earth's scalerank,
    then population. Romanisation fixed (NAME_FIX)."""
    pp = ne('ne_10m_populated_places')
    pp = pp[shapely.within(pp.geometry.values, box.buffer(-2 * MM))]
    pp = pp[(pp['featurecla'] != 'Historic place') & (pp['pop_max'] != 0)]
    cap0 = pp['featurecla'].str.startswith('Admin-0 capital') & (pp['latitude'] > 55)
    if dom is not None:
        pp = pp[shapely.within(pp.geometry.values, dom) | cap0]
    pp = pp.assign(major=(pp['pop_max'] >= 100_000) | pp['featurecla'].str.startswith('Admin-0 capital'),
                   label=[typeset_name(fix_name(n), FONTS['sans']) for n in pp['name']])
    return pp.sort_values(['major', 'scalerank', 'pop_max'], ascending=[False, True, False])


_DOTS = {True: [], False: []}
DOT_MM = {True: 1.15, False: 0.75}                  # town dot diameters: major, other


def place_towns(ax, lab, pp, limit):
    """a town is named only if its dot is clear of every name placed before it (review M3: eight dots printed inside
    other names, Pokrovsk in 'Yakutsk', Torshavn in 'FAROE ISLANDS'); its name then tries eight positions round the
    dot. Dots are drawn at the end, above the halos."""
    fp, n = FONTS['sans'], 0
    for _, r in pp.iterrows():
        if n >= limit:
            break
        x, y, major = r.geometry.x, r.geometry.y, bool(r['major'])
        rad = DOT_MM[major] / 2 * MM
        dot = shapely.Point(x, y).buffer(rad + 0.25 * MM, quad_segs=4)
        if not lab.free(dot, 0.0):
            continue
        own = shapely.Point(x, y).buffer(rad, quad_segs=4)          # the name must clear its own dot too
        fs = 8.0 if major else 6.5                  # review M4: 446 of 549 names were 4.8 pt
        d = rad + 0.55 * MM
        e = 0.72 * d
        for dx, dy, ha, va in ((d, 0, 'left', 'center'), (-d, 0, 'right', 'center'), (0, d, 'center', 'bottom'),
                               (0, -d, 'center', 'top'), (e, e, 'left', 'bottom'), (-e, e, 'right', 'bottom'),
                               (e, -e, 'left', 'top'), (-e, -e, 'right', 'top')):
            if lab.place(x + dx, y + dy, r['label'], fp, fs, INK, ha=ha, va=va, pad=0.35, avoid=own, zorder=9.5,
                         kind='town'):
                lab.add(dot)
                _DOTS[major].append((x, y))
                n += 1
                break


def draw_dots(ax):
    for major, pts in _DOTS.items():
        if pts:
            ax.add_collection(PatchCollection([Circle(p, DOT_MM[major] / 2 * MM) for p in pts], fc=INK,
                                              ec=PAPER, lw=0.12 / PT, zorder=9.6))


def area_name(lab, text, lon, lat, fp, size, color, track, orient, kind):
    """a country, region or landform name at (lon, lat): along the parallel ('par'), the meridian ('mer') or level;
    if blocked, nudged up to 4 mm across its line, then 15 % smaller; slid back inside the frame if it crosses it"""
    x, y = lonlat(lon, lat)
    if not lab.frame.contains(shapely.Point(x, y)):
        return False
    r = np.hypot(x, y)
    nx, ny = x / r, y / r
    for s in (size, round(0.85 * size, 1)):
        for off in (0.0, 2.0, -2.0, 4.0, -4.0):
            xx, yy = x + nx * off * MM, y + ny * off * MM
            if orient == 'par' and abs(reading_angle(xx, yy)) <= 50:
                ok = lab.place(xx, yy, text, fp, s, color, track=track, arc=np.hypot(xx, yy), clamp=True, kind=kind)
            else:
                ang = meridian_angle(lon) if orient == 'mer' else 0.0
                ox, oy = (-np.sin(np.radians(ang)) * off * MM, np.cos(np.radians(ang)) * off * MM) if orient == 'mer' \
                    else (0.0, off * MM)
                ok = lab.place(x + ox, y + oy, text, fp, s, color, track=track, angle=ang, clamp=True, kind=kind)
            if ok:
                return True
    return False


def beside(lab, text, lon, lat, fp, size, color, track, land, dists, kind):
    """a name on the water beside a point (a cape, a small island), as close as the land allows"""
    x, y = lonlat(lon, lat)
    offs = ((1, 0, 'left', 'center'), (-1, 0, 'right', 'center'), (0, 1, 'center', 'bottom'), (0, -1, 'center', 'top'),
            (0.7, 0.7, 'left', 'bottom'), (-0.7, 0.7, 'right', 'bottom'), (0.7, -0.7, 'left', 'top'),
            (-0.7, -0.7, 'right', 'top'))
    for dist in dists:
        for ux, uy, ha, va in offs:
            if lab.place(x + ux * dist * MM, y + uy * dist * MM, text, fp, size, color, track=track, ha=ha, va=va,
                         avoid=land, zorder=9.3, kind=kind):
                return True
    return False


def check_labels(fig, ax, margin_mm=1.0):
    """after placement (exact outlines): every text of the map axes measured as rendered; returns the ones that
    cross the neatline inset by margin_mm (should be none)"""
    r = fig.canvas.get_renderer()
    ab = ax.get_window_extent(r)
    m = margin_mm / 25.4 * fig.dpi
    bad = []
    for t in ax.texts:
        bb = t.get_window_extent(r)
        if bb.x0 < ab.x0 + m or bb.x1 > ab.x1 - m or bb.y0 < ab.y0 + m or bb.y1 > ab.y1 - m:
            bad.append(t.get_text())
    return bad


def render(bounds, w_mm, h_mm, dpi, tiles_dir, out_png, title=None):
    """a true-scale crop of the map face (labels placed for the crop alone)"""
    fonts()
    px = 25.4 / dpi * MM
    cls, yed = classes(bounds, px, tiles_dir)
    c = {'cls': cls, 'yed': yed}
    _, (H0, W0) = grid(bounds, px)
    if OPT['outline'] > 0 and px / MM <= 0.2:
        for k, v in contacts(cls, px / 2 / MM).items():
            c[f'edge_{k}'] = v.reshape(H0, 2, W0, 2).sum((1, 3), dtype=np.uint8)
    img, _ = compose(bounds, px, c, mmu=False)
    img = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    fig = plt.figure(figsize=(w_mm / 25.4, h_mm / 25.4), dpi=dpi)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([0, 0, 1, 1])
    x0, y0, x1, y1 = bounds
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation='nearest', zorder=1)
    vectors(ax, bounds, bg=bg_sampler(img, bounds, px))
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_axis_off()
    if title:
        ax.text(0.012, 0.985, title, transform=ax.transAxes, fontsize=6, va='top', color=INK,
                bbox=dict(boxstyle='square,pad=0.4', fc=(1, 1, 1, 0.85), ec=INK, lw=0.4))
    fig.savefig(out_png, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_png


# --- panel ----------------------------------------------------------------------------------------------------------
# reliability diagram: finest source scale per place. Classes by the bounds of their bins (review C4: the labels left
# gaps, and the Alaskan 1:253 440 quadrangles were filed under '1:500 000 - 1:600 000'); lighter ramp (S3)
SCALE_CLASSES = [(100_000, '1:5 000 – 1:100 000', '#4f9a78'), (300_000, '1:125 000 – 1:253 440', '#88c09b'),
                 (600_000, '1:500 000 – 1:600 000', '#c2dfa9'), (1_000_000, '1:1 000 000', '#ecebb2'),
                 (1e12, '1:2 500 000 – 1:5 000 000', '#f5d3a2')]
# second panel inset (H. Lantuit 2026-10-07): permafrost zones (Obu et al. 2019) with the IRYP v2 Yedoma domain on top
# as the main map's hatch (review S8: it was the solid ice-complex colour), zones as a violet ramp, lighter (S3: the
# continuous zone #54408a was the darkest mass on the sheet)
PF_ZONES = [('continuous', 'Continuous', '#7d6bb0'), ('discontinuous', 'Discontinuous', '#a597cc'),
            ('sporadic', 'Sporadic', '#c8bfe0'), ('isolated', 'Isolated patches', '#e6e1f1')]
NO_PF, INSET_ICE = '#d9d4c7', PAL['I']
INSET_PX = 4_000.0                  # inset grid (m): 0.07 mm on the 140 mm wide insets
NOT_MAPPED = '#ffffff'              # review M5: white with a grey hatch, not a third grey
NOT_MAPPED_HATCH = (lambda x, y, p: lines_cov(x, y, p, 0.8, 0.12, 45), (0.55, 0.55, 0.55), 0.6)
GROUPS = [('Glacial', ['T', 'GF', 'GL', 'GM']), ('Marine, fluvial and lacustrine', ['M', 'F', 'L']),
          ('Permafrost', ['Y', 'K']), ('Slope, residual, aeolian and organic', ['C', 'W', 'E', 'O']),
          ('Other units', ['V', 'X', 'Q']), ('Bedrock and ice', ['R', 'I'])]
# review S7: Bedrock and Ice closed an 'Other' group at positions 17 and 19, Thermokarst sat under Fluvial, three
# groups had one item; now six groups in two balanced columns, the Yedoma overprint and an example of it under
# Permafrost, 'not mapped' last
LEGEND_EXTRA = {'Permafrost': [('yedoma', 'Yedoma domain (IRYP v2), overprint'),
                               ('Y+', 'Ice complex within the Yedoma domain')],
                'Bedrock and ice': [('U', 'Not mapped, or outside the compilation domain')]}
# the two QR codes (H. Lantuit 2026-10-07: PANGAEA entry AND ESSD paper). Placeholders until the DOIs are minted: pass
# --doi-data / --doi-paper for the print run. The PANGAEA DOI is the parent (collection) DOI if the CryoGrid addendum
# becomes a second dataset; ESSD gives a discussion-paper DOI first, the final one on acceptance.
DOIS = {'data': '10.1594/PANGAEA.XXXXXX', 'paper': '10.5194/essd-2026-XXX'}
VERSION, EDITION = '1.0', 'November 2026'
COPYRIGHT = '© 2026 the authors'        # H.L. 2026-11-06, as ESSD's '© Author(s)'; CC BY 4.0 makes reusers keep it


def doi_url(doi):
    return f'https://doi.org/{doi}'


def draw_qr(ax, text, x, y, size, colour=INK):
    """QR code (error level M) as ONE vector path, lower-left corner at (x, y), size in axis units. Dark modules are
    merged into runs per row and filled as a single compound path, so PDF viewers show no hairline seams between
    modules. Keep ~4 modules of blank paper around it (quiet zone)."""
    import segno
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


def neatline(fig, rect_mm, sheet_mm):
    """double neatline drawn ABOVE the map (review S15: under the map raster the inner 0.9 pt line printed as a
    0.13 mm hairline), meridian labels where the meridians meet the frame, level on every side (S9: the parallels'
    labels repeated 40N eight times on the frame; they are on the map now)"""
    W, H = sheet_mm
    x0, y0, w, h = rect_mm
    ax = fig.add_axes([0, 0, 1, 1], zorder=3)
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.set_axis_off()
    for d, lw_ in ((0, 0.9), (2.2, 0.35)):
        ax.add_patch(plt.Rectangle((x0 - d, y0 - d), w + 2 * d, h + 2 * d, fc='none', ec=INK, lw=lw_))
    fx0, fy0, fx1, fy1 = FRAME
    sx, sy = w / (fx1 - fx0), h / (fy1 - fy0)
    edges = {'bottom': shapely.LineString([(fx0, fy0), (fx1, fy0)]), 'top': shapely.LineString([(fx0, fy1), (fx1, fy1)]),
             'left': shapely.LineString([(fx0, fy0), (fx0, fy1)]), 'right': shapely.LineString([(fx1, fy0), (fx1, fy1)])}
    fp = FONTS['sans']
    for lon in range(-180, 180, 30):
        g = gpd.GeoSeries([shapely.LineString([(lon, 35), (lon, 89.9)])], crs=4326).to_crs(6931).geometry.values[0]
        lab = '180°' if lon == -180 else ('0°' if lon == 0 else f'{abs(lon)}°{"E" if lon > 0 else "W"}')
        for side, e in edges.items():
            for q in shapely.get_parts(shapely.intersection(g, e)):
                if q.geom_type != 'Point':
                    continue
                px_, py_ = x0 + (q.x - fx0) * sx, y0 + (q.y - fy0) * sy
                off = 4.5
                pos = {'bottom': (px_, y0 - off, 'center', 'top'), 'top': (px_, y0 + h + off, 'center', 'bottom'),
                       'left': (x0 - off, py_, 'right', 'center'), 'right': (x0 + w + off, py_, 'left', 'center')}[side]
                ptext(ax, pos[0], pos[1], lab, fp, 8.5, INK, ha=pos[2], va=pos[3])
                tick = {'bottom': ((px_, px_), (y0 - 2.2, y0)), 'top': ((px_, px_), (y0 + h, y0 + h + 2.2)),
                        'left': ((x0 - 2.2, x0), (py_, py_)), 'right': ((x0 + w, x0 + w + 2.2), (py_, py_))}[side]
                ax.plot(*tick, color=INK, lw=0.6)


CITATION = ('Lantuit, H. and Fritz, M.: ArcSurf v{v} – Surficial geology of the Arctic permafrost region, wall map '
            '1:10 000 000, Alfred Wegener Institute, Helmholtz Centre for Polar and Marine Research, Potsdam, '
            'https://doi.org/{doi}, 2026.')
LOGO = f'{ROOT}/pylib/logos/AWI_Logo_Farbe_RGB_durchsichtig.png'      # AWI corporate design, colour, transparent
PDF_META = {'Title': 'ArcSurf v1.0 - Surficial geology of the Arctic permafrost region, wall map 1:10 000 000',
            'Author': 'Lantuit H., Fritz M.', 'Subject': 'A harmonised compilation of geological and '
            'Quaternary maps, 1:5 000 to 1:5 000 000', 'Keywords': 'surficial geology, permafrost, Arctic, ArcSurf'}
# source agencies and licence notices (review M2: the sheet credited GEUS only; pangaea/sources.csv lists ~1 590 source
# sheets). The Greenland sentence is the one the GEUS permission of 2026-10-22 asks for (the four datasets cited, GEUS
# acknowledged, licences stated); the Ontario one is what the OGS permission of November 2026 asks for (both products
# cited, the Crown copyright credit with the year of publication, the licence statement)
CREDITS = [
    ('Geology', 'compiled from the maps of VSEGEI (State Geological Map of Russia, Quaternary sheets, 1:200 000 – '
                '1:2 500 000); the Geological Survey of Canada; the Yukon Geological Survey; the Alberta Geological '
                'Survey; the Manitoba Geological Survey; the Saskatchewan Geological Survey; the Ontario Geological '
                'Survey; the Province of British Columbia; the Ministère des Ressources naturelles et des Forêts du '
                'Québec; the Geological Survey of Newfoundland and Labrador; the Alaska Division of Geological & '
                'Geophysical Surveys; the U.S. Geological '
                'Survey; GEUS; the Icelandic Institute of Natural History; Umhvørvisstovan (Faroe Islands); NGU; SGU; '
                'GTK; and published maps by Bryant et al. (2017), Giesche et al. (2024), Peter et al. (2014), Veremeeva '
                '(2021), van Huissteden and Belelli Marchesini (2014) and Zorenko et al. (2013). Every source sheet, '
                'with its scale, year and licence: sources.csv in the dataset.'),
    ('Licences', 'Contains information licensed under the Open Government Licences of Canada, Yukon, British '
                 'Columbia and Alberta, the OpenMB Information and Data Use Licence, the Saskatchewan Standard '
                 'Unrestricted Use Data Licence and the Norwegian Licence for Open Government Data (NLOD).'),
    ('Greenland', 'Geological Survey of Denmark and Greenland (GEUS): Kokfelt et al. (2023), doi:10.22008/FK2/FWX5ET; '
                  'Guarnieri et al. (2022a, b, c), doi:10.22008/FK2/IBHIZL, FK2/PGSMJH, FK2/07OYKX. Originals '
                  'CC BY-SA 4.0 on GEUS Dataverse; derived component CC BY 4.0 with permission from GEUS.'),
    ('Ontario', 'Ontario Geological Survey (2000), Quaternary geology, seamless coverage of the province of Ontario, '
                "Data Set 14—Revised, © King's Printer for Ontario, 2000; Ontario Geological Survey (2021), Far North "
                "Predictive Mapping, OGSEarth, © King's Printer for Ontario, 2021. Originals under the Ontario Ministry "
                'of Energy and Mines Terms of Use; the OGS-derived component is published under CC BY 4.0 with separate '
                "permission from the King's Printer for Ontario."),
    ('Permafrost', 'zones: Obu et al. (2019); Yedoma domain: IRYP v2 (Strauss et al. 2021, 2022); Arctic limit: AMAP. '
                   'Glaciers: RGI 6.0; Greenland Ice Sheet: PROMICE 2022.'),
    ('Base map', 'relief and bathymetry: ETOPO 2022 (NOAA NCEI); land of the geology: © OpenStreetMap contributors '
                 '(ODbL); coastline, lakes, rivers, boundaries, places, roads, railways and marine names: Natural Earth.'),
    ('Colours', PAL_NOTE[0].lower() + PAL_NOTE[1:]),
    ('Seams', 'straight boundaries along sheet edges, borders and meridians are where source maps of different scale '
              'or legend meet; the reliability diagram shows the scale of each. On this print, inland mapped patches '
              'and gaps smaller than 0.4 mm² (40 km²) are merged with their surroundings.')]


def _inset_rgb(code, lut, hatch_mask=None, hatch=None, pxmm=0.07):
    rgb = lut[code].astype(np.float32)
    if hatch_mask is not None and hatch_mask.any():
        overlay(rgb, hatch_mask.astype(np.float32), hatch, pxmm)
    return rgb


def _inset(ax, rgb, x, ytop, iw, bounds, coast, amap):
    """overview map in the panel: raster, coastline and AMAP limit (vector), frame; returns the y below the frame"""
    ih = iw * (bounds[3] - bounds[1]) / (bounds[2] - bounds[0])
    ax.imshow(rgb, extent=(x, x + iw, ytop - ih, ytop), interpolation='nearest', zorder=2)
    sx, sy = iw / (bounds[2] - bounds[0]), ih / (bounds[3] - bounds[1])
    to_mm = lambda cs: [np.c_[x + (c[:, 0] - bounds[0]) * sx, ytop - ih + (c[:, 1] - bounds[1]) * sy] for c in cs]  # noqa: E731
    clip = shapely.box(*bounds)
    crop = lambda cs: _lines(shapely.intersection(np.asarray([shapely.LineString(c) for c in cs], dtype=object), clip))  # noqa: E731
    if coast:
        ax.add_collection(LineCollection(to_mm(crop(coast)), colors=WATER_INK, linewidths=0.25, alpha=0.9, zorder=3))
    if amap:                                    # white casing under the dashes: legible on the purples as well
        segs = to_mm(crop(amap))
        ax.add_collection(LineCollection(segs, colors='white', linewidths=1.6, alpha=0.75, zorder=3.4))
        ax.add_collection(LineCollection(segs, zorder=3.5, **AMAP_STYLE))
    ax.add_patch(plt.Rectangle((x, ytop - ih), iw, ih, fc='none', ec=INK, lw=0.4, zorder=4))
    return ytop - ih


INSET_ROW = 7.4                                         # inset key row pitch (mm)
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


def key_item(ax, x, y, kind, spec, label, dpi, pdf, sw=8.0, sh=4.4, fs=8.0):
    """one row of a key: a swatch (kind 'patch': spec = rgb array image or colour; 'line': LineCollection style;
    'dot': diameter mm) and its label; (x, y) = the swatch's left end on the row's centre line"""
    if kind == 'image':
        ax.imshow(spec, extent=(x, x + sw, y - sh / 2, y + sh / 2), interpolation='none' if pdf else 'antialiased',
                  zorder=3)
        ax.add_patch(plt.Rectangle((x, y - sh / 2), sw, sh, fc='none', ec=SWATCH_EDGE, lw=0.25, zorder=4))
    elif kind == 'patch':
        ax.add_patch(plt.Rectangle((x, y - sh / 2), sw, sh, fc=spec, ec=SWATCH_EDGE, lw=0.25, zorder=3))
    elif kind == 'line':
        style = {k: v for k, v in spec.items() if k not in ('effects', 'zorder')}
        fx = spec.get('effects')
        lc = LineCollection([[(x, y), (x + sw, y)]], zorder=4, **style)
        if fx:
            lc.set_path_effects(fx)
        ax.add_collection(lc)
    elif kind == 'dot':
        ax.add_patch(Circle((x + sw / 2, y), spec / 2, fc=INK, ec=PAPER, lw=0.12 / PT, zorder=4))
    ptext(ax, x + sw + 2.6, y, label, FONTS['sans'], fs, INK, va='center')


def big_panel(fig, rect_mm, sheet_mm, ins, bounds, coast=None, pdf=False, dpi=300):
    """side panel, top to bottom: title block, geology key (two columns), base-map key, the two insets (reliability
    diagram; permafrost zones + Yedoma domain) with their keys beside them, credits and scale, and the foot (AWI logo,
    citation, two QR codes). Everything hangs on the panel's left edge; the kicker's cap line sits on the top neatline
    and the foot on the bottom neatline; the height left over is shared out as equal gaps (review S13)."""
    W, H = sheet_mm
    x0, y0, w, h = rect_mm
    ax = fig.add_axes([x0 / W, y0 / H, w / W, h / H], zorder=1)
    ax.set_xlim(0, w); ax.set_ylim(0, h); ax.set_axis_off()
    F = FONTS
    # sizes: H.L. 2026-10-07 asked for 11 pt class names, 15 x 7.5 mm swatches and 10 mm rows (the legend text was too
    # small); review M4: credits and QR captions 8 pt at least
    HEAD = dict(fp=F['sans_demi'], size=10.0, color=INK, track=160)
    SUB = dict(fp=F['sans_demi'], size=8.5, color='#6b5a48', track=130)
    KEY_FS, BASE_FS, INSET_FS = 11.0, 9.0, 8.5

    def heading(y, text, st=HEAD):
        ptext(ax, 0, y - cap_mm(st['fp'], st['size']), text.upper(), st['fp'], st['size'], st['color'],
              track=st['track'])
        return y - cap_mm(st['fp'], st['size'])

    # block heights first, then the gaps
    leg_rows = {}
    for col in (GROUPS[:3], GROUPS[3:]):
        for g, cls in col:
            leg_rows[g] = len(cls) + len(LEGEND_EXTRA.get(g, []))
    SW, SH, ROW, GHEAD, GGAP = 15.0, 7.5, 10.0, 7.5, 3.5
    col_h = [sum(GHEAD + leg_rows[g] * ROW + GGAP for g, _ in col) - GGAP for col in (GROUPS[:3], GROUPS[3:])]
    h_title = 54.0
    h_leg = 9.5 + max(col_h)
    BROW = 8.0
    h_base = 9.5 + 4 * BROW
    iw = 136.0
    # inset frame: the mapped domain's box, not the whole sheet (review C7: ~30 % of the frame was empty corners)
    m = (ins['rel'] > 0) | (ins['dom'] > 0)
    rr, cc = np.nonzero(m)
    pad = 12
    r0_, r1_ = max(0, rr.min() - pad), min(m.shape[0], rr.max() + pad + 1)
    c0_, c1_ = max(0, cc.min() - pad), min(m.shape[1], cc.max() + pad + 1)
    ib = (bounds[0] + c0_ * INSET_PX, bounds[3] - r1_ * INSET_PX, bounds[0] + c1_ * INSET_PX, bounds[3] - r0_ * INSET_PX)
    sl = np.s_[r0_:r1_, c0_:c1_]
    aspect = (ib[3] - ib[1]) / (ib[2] - ib[0])
    h_inset = lambda iw_: 9.5 + iw_ * aspect                         # noqa: E731
    h_foot = 36.0
    cred_runs = []
    for k, t in CREDITS:
        cred_runs += [(k + '  ', F['sans_demi']), (t + '\n', F['sans'])]
    CRED_FS, CRED_LEAD, MEASURE = 8.0, 3.75, 140.0
    yy = paragraph(ax, 0, 0, cred_runs, MEASURE, CRED_FS, CRED_LEAD, draw=False)
    h_cred = -yy + cap_mm(F['sans'], CRED_FS) + 2.0
    fixed = h_title + h_leg + h_base + 2 * h_inset(iw) + h_cred + h_foot
    gap = (h - fixed) / 6
    if gap > 13.0:                                  # spare height: larger insets (up to 150 mm), then larger gaps
        iw = min(150.0, iw + (gap - 13.0) * 6 / (2 * aspect))
        fixed = h_title + h_leg + h_base + 2 * h_inset(iw) + h_cred + h_foot
        gap = (h - fixed) / 6
    print(f'panel: gaps {gap:.1f} mm, insets {iw:.0f} x {iw * aspect:.0f} mm, credits {h_cred:.0f} mm', flush=True)

    # 1. title block (review M1, S17): the product's name and version over a 46 pt title in the sans
    y = h
    ptext(ax, 0, y - cap_mm(F['sans_demi'], 10.5), f'ARCSURF  ·  VERSION {VERSION}', F['sans_demi'], 10.5, INK,
          track=260)
    y -= cap_mm(F['sans_demi'], 10.5)
    ts = 46.0
    while pen('Surficial Geology', F['sans_demi'], ts)[2] * PT > w and ts > 30:
        ts -= 1
    y -= 19.0
    ptext(ax, -0.4, y, 'Surficial Geology', F['sans_demi'], ts, INK, track=-10)
    y -= 10.5
    ptext(ax, 0, y, 'of the Arctic Permafrost Region', F['sans'], 21, INK, track=10)
    y -= 6.5
    ax.plot([0, w], [y, y], color=INK, lw=1.1, solid_capstyle='butt')
    ax.plot([0, w], [y - 1.3, y - 1.3], color=INK, lw=0.4, solid_capstyle='butt')
    y -= 7.5
    ptext(ax, 0, y, 'A harmonised compilation of geological and Quaternary maps at 1:5 000 to 1:5 000 000',
          F['serif_italic'], 11, INK)
    y -= 5.6
    ptext(ax, 0, y, f'Wall map 1:10 000 000  ·  Version {VERSION}, {EDITION}  ·  {COPYRIGHT}  ·  Map and data '
          'licensed under CC BY 4.0', F['sans'], 8.5, INK)
    y = h - h_title - gap

    # 2. geology key: two columns of groups, swatches as the map prints them
    heading(y, 'Surficial geology')
    yl = y - 9.5
    cx = [0.0, w / 2 + 2.0]
    name_w = w / 2 - 2.0 - SW - 3.2                 # room for a class name in a column
    for ci, col in enumerate((GROUPS[:3], GROUPS[3:])):
        yy = yl
        for g, cls in col:
            ptext(ax, cx[ci], yy - cap_mm(SUB['fp'], SUB['size']), g.upper(), SUB['fp'], SUB['size'], SUB['color'],
                  track=SUB['track'])
            yy -= GHEAD
            items = [(c, NAMES[c]) for c in cls] + LEGEND_EXTRA.get(g, [])
            for key, label in items:
                ytop = yy - (ROW - SH) / 2 + 0.6
                img = swatch_rgb(key, SW, SH, dpi)
                ax.imshow(img, extent=(cx[ci], cx[ci] + SW, ytop - SH, ytop),
                          interpolation='none' if pdf else 'antialiased', zorder=3)
                ax.add_patch(plt.Rectangle((cx[ci], ytop - SH), SW, SH, fc='none', ec=SWATCH_EDGE, lw=0.25, zorder=4))
                lines = [label] if pen(label, F['sans'], KEY_FS)[2] * PT <= name_w else _two_lines(label)
                lead = 1.12 * KEY_FS * PT
                for li, t in enumerate(lines):
                    ptext(ax, cx[ci] + SW + 3.2, ytop - SH / 2 + ((len(lines) - 1) / 2 - li) * lead, t, F['sans'],
                          KEY_FS, INK, va='center')
                yy -= ROW
            yy -= GGAP
    y = y - h_leg - gap

    # 3. base map (review S16, S10)
    heading(y, 'Base map')
    lw = lambda mm: mm / PT                                         # noqa: E731
    items = [('line', dict(colors=WATER_INK, linewidths=lw(0.12)), 'Coastline'),
             ('patch', LAKE, 'Lake; rivers in blue lines'),
             # hairlines a little stronger than on the map: a 11 mm sample shows less than a long line
             ('line', dict(colors=CONTACT_INK, linewidths=lw(0.10), alpha=0.75), 'Contact between units'),
             ('line', dict(colors=BORDER_INK, linewidths=lw(0.22), alpha=0.85, linestyles=[(0, (7, 2.2, 1.4, 2.2))]),
              'International boundary'),
             ('line', dict(colors=BORDER_INK, linewidths=lw(0.16), alpha=0.85, linestyles=[(0, (1.2, 2.4))]),
              'Province or territory boundary'),
             ('line', dict(colors=ROAD_INK, linewidths=lw(0.13), alpha=0.75), 'Road'),
             ('line', dict(RAIL_STYLE, alpha=0.8, effects=RAIL_EFFECTS), 'Railway'),
             ('line', dict(colors=GRAT_STYLE['color'], linewidths=lw(0.10), alpha=0.8),
              'Parallels 10°, meridians 30°'),
             ('line', dict(colors=GRAT_STYLE['color'], linewidths=lw(0.16), linestyles=[(0, (6, 4))]), 'Arctic Circle'),
             ('dot', DOT_MM[True], 'City of 100 000 or more, capital'),
             ('dot', DOT_MM[False], 'Town or settlement')]
    for i, (kind, spec, label) in enumerate(items):
        col, row = i // 4, i % 4
        key_item(ax, col * (w / 3), y - 9.5 - row * BROW - 2.6, kind, spec, label, dpi, pdf, sw=11.0, sh=5.2,
                 fs=BASE_FS)
    y = y - h_base - gap

    # 4./5. insets, their keys beside them
    land = (ins['land'] > 0) | (ins['rel'] > 0)
    pxmm = iw / (c1_ - c0_)
    code = np.where(ins['rel'] > 0, ins['rel'].astype(np.int16) + 1, land.astype(np.int16))[sl]
    lut = np.array([SEA_SHALLOW, PAPER] + [hex2rgb(c) for _, _, c in SCALE_CLASSES] + [hex2rgb(NOT_MAPPED)])
    rgb = _inset_rgb(code, lut, code == 7, NOT_MAPPED_HATCH, pxmm)
    amap = _amap_lines(bounds)
    amap_key = ('line', AMAP_STYLE, 'AMAP Arctic limit')
    heading(y, 'Reliability: scale of the source maps')
    yb = _inset(ax, rgb, 0, y - 9.5, iw, ib, coast, amap)
    kx = iw + 6.0
    nm = swatch_rgb('U', 10.0, 5.2, dpi)
    nm[:] = hex2rgb(NOT_MAPPED)
    one = np.ones(nm.shape[:2], np.float32)
    overlay(nm, one, NOT_MAPPED_HATCH, 25.4 / dpi)
    rows = [('patch', c, lab_) for _, lab_, c in SCALE_CLASSES] + [('image', nm, 'Not mapped'), amap_key]
    for i, (kind, spec, label) in enumerate(rows):
        key_item(ax, kx, y - 9.5 - 3.0 - i * INSET_ROW, kind, spec, label, dpi, pdf, sw=10.0, sh=5.2, fs=INSET_FS)
    y = yb - gap
    mapped = (ins['rel'] > 0) | ((ins['dom'] > 0) & (ins['land'] > 0))
    code = land.astype(np.int16)                            # 0 sea, 1 land outside the domain
    code[mapped] = 2                                        # mapped, outside the permafrost zones
    zz = mapped & (ins['zone'] > 0)
    code[zz] = 2 + ins['zone'][zz]                          # 3..6 continuous .. isolated
    code[ins['ice'] > 0] = 7
    lut = np.array([SEA_SHALLOW, PAPER, hex2rgb(NO_PF)] + [hex2rgb(c) for _, _, c in PF_ZONES] + [hex2rgb(INSET_ICE)])
    rgb = _inset_rgb(code[sl], lut, (ins['yed'] > 0)[sl], YEDOMA, pxmm)
    heading(y, 'Permafrost zones and Yedoma domain')
    yb = _inset(ax, rgb, 0, y - 9.5, iw, ib, coast, amap)
    yd = swatch_rgb('yedoma', 10.0, 5.2, dpi)
    rows = [('patch', c, lab_) for _, lab_, c in PF_ZONES] + [('patch', NO_PF, 'No permafrost'),
                                                               ('patch', INSET_ICE, 'Glaciers, ice sheet'),
                                                               ('image', yd, 'Yedoma domain'), amap_key]
    for i, (kind, spec, label) in enumerate(rows):
        key_item(ax, kx, y - 9.5 - 3.0 - i * INSET_ROW, kind, spec, label, dpi, pdf, sw=10.0, sh=5.2, fs=INSET_FS)
    paragraph(ax, kx, y - 9.5 - 3.0 - len(rows) * INSET_ROW, [('Zones: Obu et al. (2019). Yedoma: IRYP v2 (Strauss '
              'et al. 2021, 2022), confirmed and likely.', F['sans_oblique'])], w - kx, 7.6, 3.4)
    y = yb - gap

    # 6. credits (left, 138 mm measure) and scale (right column)
    paragraph(ax, 0, y, cred_runs, MEASURE, CRED_FS, CRED_LEAD)
    sx = MEASURE + 9.0
    sw_ = w - sx
    yy = y - cap_mm(F['sans_demi'], 10.0)
    ptext(ax, sx, yy, 'SCALE 1:10 000 000', F['sans_demi'], 10.0, INK, track=120)
    yy -= 4.8
    ptext(ax, sx, yy, 'at A0, 1189 × 841 mm', F['sans'], 8.0, INK)
    yy -= 5.8
    seg = 10.0                                      # 100 km = 10 mm at 1:10M
    nseg = int(min(5, sw_ // seg - 0))
    for kk in range(nseg):
        ax.add_patch(plt.Rectangle((sx + seg * kk, yy - 1.8), seg, 1.8, fc=INK if kk % 2 == 0 else 'white', ec=INK,
                                   lw=0.35))
    for kk in range(nseg + 1):
        ptext(ax, sx + seg * kk, yy - 1.8 - 1.5 - cap_mm(F['sans'], 7.6), f'{100 * kk}' + (' km' if kk == nseg else ''),
              F['sans'], 7.6, INK, ha='center')
    yy -= 11.5
    paragraph(ax, sx, yy, [('Lambert azimuthal equal-area projection centred on the North Pole (EPSG:6931). Areas '
                            'are true everywhere; distances are true at the Pole. Along the meridians they are 1.5 % '
                            'too short at 70° N, 3.4 % at 60° N and 9.4 % at 40° N; along the parallels 1.5, 3.5 and '
                            '10.3 % too long.', F['sans'])], sw_, 8.0, 3.75)

    # 7. foot, on the bottom neatline: AWI logo, citation, two QR codes
    qs = 24.0
    cap_lines = 2
    cfs, clead = 8.0, 3.5
    qy = cap_lines * clead + 1.2                   # QR codes stand on their two caption lines
    heads = (('Dataset · PANGAEA', DOIS['data']), ('Data paper · ESSD', DOIS['paper']))
    span = [max(qs, pen(hd, F['sans_demi'], cfs)[2] * PT, pen(f'doi:{d}', F['sans'], cfs)[2] * PT) for hd, d in heads]
    c2 = w - span[1] / 2                            # the right caption ends on the panel's edge (rev2: 8 mm past it)
    c1 = c2 - span[1] / 2 - 8.0 - span[0] / 2
    qx1, qx2 = c1 - qs / 2, c2 - qs / 2
    for qx, (head, doi) in zip((qx1, qx2), heads):
        draw_qr(ax, doi_url(doi), qx, qy, qs)
        ptext(ax, qx + qs / 2, qy - 1.2 - cap_mm(F['sans'], cfs), head, F['sans_demi'], cfs, INK, ha='center')
        ptext(ax, qx + qs / 2, qy - 1.2 - cap_mm(F['sans'], cfs) - clead, f'doi:{doi}', F['sans'], cfs, INK, ha='center')
    lh = 12.5
    lw_mm = 0.0
    if os.path.exists(LOGO):
        im = plt.imread(LOGO)
        lw_mm = lh * im.shape[1] / im.shape[0]
        ax.imshow(im, extent=(0, lw_mm, 0, lh), interpolation='none' if pdf else 'antialiased', zorder=5)
    else:
        print('AWI logo missing:', LOGO, flush=True)
    cx0 = lw_mm + 7.0
    cite = [(CITATION.format(v=VERSION, doi=DOIS['data']), F['sans'])]
    cw_ = c1 - span[0] / 2 - 6.0 - cx0
    ytop = -paragraph(ax, cx0, 0.0, cite, cw_, 8.0, 3.6, draw=False)  # last baseline on the bottom neatline
    paragraph(ax, cx0, ytop, cite, cw_, 8.0, 3.6)
    ptext(ax, cx0, ytop + 2.8, 'PLEASE CITE', F['sans_demi'], 8.0, INK, track=140)


def layout(dpi, tiles_dir, out_path):
    fonts()
    px = 25.4 / dpi * MM
    fresh = '--fresh' in sys.argv
    tname = os.path.basename(os.path.normpath(tiles_dir))
    if '--dry' in sys.argv:                     # layout test: blank map face, real insets
        _, (H, W) = grid(FRAME, px)
        img = np.full((H, W, 3), (PAPER * 255 + 0.5).astype(np.uint8), np.uint8)
    else:
        c = class_cache(FRAME, px, dpi, tiles_dir, fresh)
        z = relief_cache(FRAME, px, dpi, fresh)
        img, _ = compose(FRAME, px, c, z)
        img = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
        del c
    skey = '-'.join(str(int(t)) for t, _, _ in SCALE_CLASSES[:-1])
    icache = f'{OUTD}/a0_insets_{tname}_{int(INSET_PX)}_{skey}.npz'   # class rasters of the insets (palette-free)
    if '--insets' in sys.argv:                  # layout tests: an existing inset cache, whatever its class bins
        icache = sys.argv[sys.argv.index('--insets') + 1]
    if os.path.exists(icache) and not fresh:
        zz = np.load(icache)
        ins = {k: zz[k] for k in zz.files}
    else:
        ins = inset_rasters(FRAME, INSET_PX, tiles_dir)
        np.savez_compressed(icache, **ins)
    W_, H_ = SHEET
    fig = plt.figure(figsize=(W_ / 25.4, H_ / 25.4), dpi=dpi)
    fig.patch.set_facecolor(PAPER)
    ax = fig.add_axes([MRECT[0] / W_, MRECT[1] / H_, MRECT[2] / W_, MRECT[3] / H_], zorder=1)
    x0, y0, x1, y1 = FRAME
    pdf = out_path.lower().endswith('.pdf')
    # PDF: the map raster is embedded as is (interpolation 'none' = no resampling, it is already at the print
    # resolution); frame, names, legend and QR stay vector
    ax.imshow(img, extent=(x0, x1, y0, y1), interpolation='none' if pdf else 'nearest', zorder=1)
    vectors(ax, FRAME, bg=bg_sampler(img, FRAME, px))
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_axis_off()
    bad = check_labels(fig, ax)
    print(f'texts crossing the frame: {len(bad)}', bad[:20], flush=True)
    neatline(fig, MRECT, SHEET)
    big_panel(fig, PRECT, SHEET, ins, FRAME, _coast(FRAME, tol=2_000.0), pdf=pdf, dpi=dpi)
    if pdf:
        plt.rcParams['pdf.compression'] = 6
        try:                                        # TrueType embedding (editable text for the print shop) ...
            plt.rcParams['pdf.fonttype'] = 42
            fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), metadata=PDF_META)
        except Exception as e:                      # ... the URW OTF (CFF) faces may refuse: Type 3 then
            print('fonttype 42 failed (', str(e)[:120], ') -> Type 3 fonts', flush=True)
            plt.rcParams['pdf.fonttype'] = 3
            fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor(), metadata=PDF_META)
        srgb(out_path)
    else:
        fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def srgb(path):
    """Tag the print PDF as sRGB in place (scripts/pdf_srgb.py). It needs pypdf; a python without it hands the file to
    PDF_PY (default: the psdb env on Albedo, which has pypdf)."""
    try:
        import pdf_srgb
        pdf_srgb.tag(path, path)
        return
    except ImportError:
        pass
    py = os.environ.get('PDF_PY', '/albedo/work/user/hlantuit/conda_envs/psdb/bin/python')
    r = subprocess.run([py, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pdf_srgb.py'), path])
    if r.returncode:
        print(f'WARNING: {path} is NOT tagged as sRGB: run scripts/pdf_srgb.py under a python with pypdf', flush=True)


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
        p = render(b, w_mm, h_mm, 300, tiles, f'{OUTD}/mockup_{name}{tag}.png',
                   title=f'Mockup: a {w_mm:.0f} x {h_mm:.0f} mm crop of the A0 sheet at print scale 1:{SCALE:,}')
        print('wrote', p)
    elif a[0] == 'layout':
        dpi = int(a[a.index('--dpi') + 1]) if '--dpi' in a else 30
        if '--pdf' in a:                            # print file: out/a0/arcsurf_a0_<tiles>_<dpi>dpi.pdf
            name = f"arcsurf_a0_{os.path.basename(os.path.normpath(tiles))}_{dpi}dpi{tag}.pdf"
            print('wrote', layout(dpi, tiles, f'{OUTD}/{name}'))
        else:
            print('wrote', layout(dpi, tiles, f'{OUTD}/a0_layout_{dpi}dpi{tag}.png'))


if __name__ == '__main__':
    main()
