#!/usr/bin/env python
"""CryoGrid parameters of the ArcSurf addendum (Hugues 2026-10-08: "fill the table ... thoroughly documenting it";
"map values tier 1, the Westermann strategy the fallback").

TEMPLATES  one layered stratigraphy per deposit type, in the convention of CryoGrid's
           GROUND_freezeC_bucketW_Xice_seb(_snow) with STRAT_layers (fractions of the soil MATRIX, Xice relative to
           the matrix, soil_type 1 sand / 2 silt / 3 clay / 4 peat / 5 free water or blocks, field capacity as a
           fraction of the matrix, Ksat in m/s); bedrock in GROUND_freeW_seb, glaciers in GLACIER_freeW_seb.
           Values from the published CryoGrid literature as compiled in
           addendum/cryogrid_stratigraphies_compilation_2026-10-07.md, section C (source keys in its section B:
           W13 = Westermann et al. 2013, C23 = Czekirda et al. 2023, R23 = Renette et al. 2023, ...). Marks:
           (i) interpretation of a published sentence, (d) derived from published numbers, proxy = taken from another
           deposit because nothing is published for this one.
           Excess ice: the geology does not carry ground ice (ArcSurf rule), so Xice = 0 everywhere except Yedoma
           (the one exception Hugues allows); the published value is kept in Xice_published.
ASSIGN     (hclass, hclass2, texture, cover, LGM ice share) -> template
THICKNESS  depth of the base of the Quaternary cover (the bedrock contact) of templates that have one:
           tier 1a  a thickness stated in the unit's own legend text (src_desc), or the legend of GSC Map 1814A
           tier 1b  the cover term (veneer / blanket / discontinuous) defined numerically by the source's legend
                    system (COVER_DEFS)
           tier 2   the template's default (the Westermann et al. 2013 strategy: thick till 10 m, thin till 1 m, ...)
           A veneer or a stated maximum thickness on a template without a bedrock contact adds bedrock at that
           depth (thin cover over rock).
REALIZE    template + thickness -> STRAT_layers rows
usage (self-test): addendum_params.py --test"""
import math
import re
import sys

X = 'GROUND_freezeC_bucketW_Xice_seb_snow'
FW = 'GROUND_freeW_seb'
GL = 'GLACIER_freeW_seb'
ROCK = (0.03, 0.97, 0.0)                     # W13 class 130: 3 % porosity, saturated (also JS21, M21, R23)


def L(top, wi, mi, org, st=None, fc=None, ks=None, xice=0.0, cls=X, xpub=None):
    return dict(top_m=top, waterIce=wi, mineral=mi, organic=org, soil_type=st, field_capacity=fc,
                satHydraulicConductivity=ks, Xice=xice, Xice_published=xpub if xpub is not None else xice, cls=cls)


def BED(top):
    return L(top, *ROCK, cls=FW)


# base: index of the layer whose top is the bedrock contact (None: no bedrock in the published profile)
TEMPLATES = {
    'ICE': dict(name='Glacier ice', base=None, layers=[L(0, 1.0, 0.0, 0.0, cls=GL)],
                sources='W23 2.2.8 (layers of pure ice, mineral 0); S23 (20 m of ice)',
                confidence='high for the ice; the glacier bed is a gap (C23: bedrock, 0 C bed)'),
    'BEDROCK': dict(name='Bedrock', base=None, layers=[BED(0)],
                    sources='W13 class 130; JS21; M21; R23', confidence='high',
                    note='rock thermal conductivity k_m is a run constant in CryoGrid (published 2.0-5.5 W/m/K)'),
    'COLL_BOULDERY': dict(name='Colluvium, bouldery (talus, block slopes)', base=1,
                          layers=[L(0, 0.02, 0.50, 0.0, 5, 0.01, 1e-5), BED(5)],
                          sources='R23 "blocks only" (mineral, fc, Ksat); wI My19 / C23 (i); st 5 = free-water '
                                  'freezing (R23) in this class', confidence='medium (Norway only)'),
    'TILL_THICK': dict(name='Till, thick (blanket / unknown cover)', base=2,
                       layers=[L(0, 0.30, 0.60, 0.0, 1, 0.30, 1e-5), L(2, 0.40, 0.60, 0.0, 1, 0.30, 1e-5), BED(10)],
                       sources='W13 classes 11/15/81 (= C23 e); fc 0.30 (i) from W13 "some silt and clay in the '
                               'tills increase the field capacity"', confidence='medium (coarse Fennoscandian till)'),
    'TILL_VENEER': dict(name='Till, veneer over bedrock', base=1,
                        layers=[L(0, 0.30, 0.60, 0.0, 1, 0.30, 1e-5), BED(1)],
                        sources='W13 classes 12/140 (= C23 b); fc (i) as TILL_THICK', confidence='medium'),
    'COLL_FINES': dict(name='Colluvium, fine / unknown / mixed', base=2,
                       layers=[L(0, 0.30, 0.60, 0.0, 2, 0.30, 1e-5), L(2, 0.40, 0.60, 0.0, 2, 0.30, 1e-5), BED(10)],
                       sources='W13 (colluvium has "the same ground properties as for thick till"); C23 f; '
                               'soil_type 2 (i; published 1)', confidence='low-medium'),
    'COLL_FINES_THIN': dict(name='Colluvium, thin over bedrock', base=1,
                            layers=[L(0, 0.30, 0.60, 0.0, 2, 0.30, 1e-5), BED(1)],
                            sources='C23 c (thin colluvium, bedrock from 1 m); soil_type 2 (i)',
                            confidence='low-medium'),
    'REG_BOULDERY': dict(name='Residual regolith, bouldery / blockfield', base=2,
                         layers=[L(0, 0.10, 0.60, 0.0, 5, 0.15, 1e-5), L(2, 0.40, 0.60, 0.0, 1, 0.15, 1e-5), BED(5)],
                         sources='W13 class 73 (= C23 l); fc, st, Ksat R23 "blocks with sediment" (i)',
                         confidence='medium'),
    'REG_FINES': dict(name='Residual regolith, fine / unknown', base=2,
                      layers=[L(0, 0.10, 0.60, 0.0, 1, 0.10, 1e-5), L(1, 0.40, 0.60, 0.0, 1, 0.10, 1e-5), BED(5)],
                      sources='W13 class 71 (C23 i, j); fc is a gap (0.10 i)', confidence='low-medium'),
    'PEAT': dict(name='Organic deposits (bog, fen, mire)', base=3,
                 layers=[L(0, 0.30, 0.20, 0.30, 4, 0.55, 1e-5), L(0.5, 0.50, 0.20, 0.30, 4, 0.55, 1e-5),
                         L(2, 0.50, 0.40, 0.10, 2, 0.55, 1e-5), BED(10)],
                 sources='W13 class 90; fc and Ksat M21; soil_type 4 (peat) after A23 practice (W13 typed it sand)',
                 confidence='medium', note='palsas / peat plateaus: M21 Xice 0.47 below the active layer (published)'),
    'PEAT_THIN': dict(name='Thin organic cover over bedrock or shallow regolith', base=1,
                      layers=[L(0, 0.40, 0.50, 0.10, 4, 0.55, 1e-5), BED(0.5)],
                      sources='C23 h (corrects W13 class 100, which sums to 1.1 in the final paper too)',
                      confidence='medium'),
    'FLUV_COARSE': dict(name='Fluvial / glaciofluvial-like gravel and sand, upland', base=2,
                        layers=[L(0, 0.10, 0.60, 0.0, 1, 0.10, 1e-4), L(1, 0.40, 0.60, 0.0, 1, 0.10, 1e-4),
                                BED(10)],
                        sources='W13 class 50 (= C23 k, E22); fc (i) W13 / SvD21 code; Ksat (d) A23 sand',
                        confidence='medium'),
    'SAND_LOWLAND': dict(name='Lowland sand (no shallow bedrock)', base=None,
                         layers=[L(0, 0.40, 0.60, 0.0, 1, 0.25, 1e-4), L(10, 0.30, 0.70, 0.0, 1)],
                         sources='W16 / W17 Arga sands (Lena delta); fc SvD21 code', confidence='medium (proxy '
                                 'outside fluvial terraces)'),
    'FLUV_FINES': dict(name='Fluvial fines / alluvium with organics', base=None,
                       layers=[L(0, 0.60, 0.10, 0.15, 1, 0.50, 1e-5), L(0.15, 0.65, 0.30, 0.05, 2, 0.50, 1e-5),
                               L(9, 0.30, 0.70, 0.0, 1)],
                       sources='W17 first terrace / floodplain; fc, Ksat N19', confidence='medium (Lena delta)'),
    'GLACIOFLUVIAL': dict(name='Glaciofluvial sand and gravel', base=2,
                          layers=[L(0, 0.10, 0.60, 0.0, 1, 0.10, 1e-4), L(1, 0.40, 0.60, 0.0, 1, 0.10, 1e-4),
                                  BED(20)],
                          sources='W13 classes 20/21; fc (i); Ksat (d) A23', confidence='medium'),
    'SILT_PROXY': dict(name='Fine-grained deposits without a published set (glaciolacustrine, loess, lacustrine '
                            'in glaciated terrain)', base=2,
                       layers=[L(0, 0.375, 0.10, 0.15, 1, 0.50, 1e-5), L(0.15, 0.45, 0.55, 0.0, 2, 0.50, 1e-6),
                               L(9, 0.30, 0.70, 0.0, cls=FW)],
                       sources='proxy: A23 simplified silt with organic top (d); fc N19', confidence='low (proxy)'),
    'MARINE_FINES': dict(name='Marine and glaciomarine fines', base=None,
                         layers=[L(0, 0.65, 0.175, 0.175, 2, 0.50, 1e-5), L(0.2, 0.55, 0.45, 0.0, 2, 0.50, 1e-5)],
                         sources='proxy: G23 Table B3, Barrow coastal plain (d); fc, Ksat generic (N19)',
                         confidence='low (proxy)', note='pore-water salinity cannot be represented in this class'),
    'LAC_UNGLACIATED': dict(name='Lacustrine / thermokarst basin, unglaciated permafrost lowland', base=None,
                            layers=[L(0, 0.85, 0.0, 0.15, 1, 0.50, 1e-5), L(0.1, 0.75, 0.10, 0.15, 1, 0.50, 1e-5),
                                    L(0.2, 0.65, 0.25, 0.10, 2, 0.50, 1e-5),
                                    L(1.0, 0.55, 0.257, 0.193, 1, 0.50, 1e-5, xpub=0.286),
                                    L(10, 0.55, 0.35, 0.10, 1, None, 1e-5), L(20, 0.45, 0.50, 0.05, 1),
                                    L(40, 0.10, 0.90, 0.0, 1)],
                            sources='N20 drained lake basin (LB, centre tile); fc N19; Ksat N20 SI',
                            confidence='medium in the Yedoma region, low elsewhere'),
    'YEDOMA': dict(name='Ice complex (Yedoma)', base=None,
                   layers=[L(0, 0.30, 0.10, 0.10, 1, 0.50, 1e-5), L(0.15, 0.70, 0.25, 0.05, 1, 0.50, 1e-5),
                           L(0.55, 0.40, 0.30, 0.30, 1, 0.50, 1e-5, xice=5.0), L(20, 0.30, 0.70, 0.0, 1)],
                   sources='W16 "Ice complex, high excess ground-ice content" (Xice 5.0 d from bulk 0.9/0.05/0.05, '
                           'porosity 0.4); fc, Ksat N19/N20; ice-rich silt typed "sand" as published (W17)',
                   confidence='medium-high', note='Xice kept: Yedoma is the one ground-ice exception'),
    'VOLCANIC': dict(name='Quaternary volcanic (lava, scree, tephra)', base=2,
                     layers=[L(0, 0.10, 0.60, 0.0, 1, None, 1e-5), L(1, 0.40, 0.60, 0.0, 1, None, 1e-5),
                             L(10, 0.08, 0.92, 0.0, 1)],
                     sources='C19 Leptosol and basalt (Iceland); fc a gap; Ksat generic', confidence='medium (Iceland)'),
    'NONE': dict(name='No ground stratigraphy (water body, unmapped, anthropogenic)', base=None, layers=[],
                 sources='-', confidence='-', note='water bodies belong to CryoGrid LAKE classes'),
}
# templates whose first layer is reused to make a thin cover over bedrock when a veneer / maximum thickness is known
THIN_OK = {'SAND_LOWLAND', 'FLUV_FINES', 'MARINE_FINES', 'LAC_UNGLACIATED', 'SILT_PROXY', 'VOLCANIC'}
# which boundary a unit thickness controls: the bedrock contact (the template's base layer) by default; for peat the
# base of the organic deposit (top of PEAT's mineral-organic layer), since a stated peat thickness says nothing about
# the depth to rock ("peat cover (up to 2 m) over 1st terrace alluvium", VSEGEI)
THK_LAYER = {'PEAT': 2}
OVER_ROCK = re.compile(r'over (?:bed)?rock|on (?:bed)?rock|over bedrock|sur (?:le )?roc|socle|коренн|berggrunn|'
                       r'kallio|berggrund', re.I)


def assign(hclass, hclass2='', texture='', cover='', lgm_ice_share=0.0):
    """template id for a polygon's geology (+ the LGM ice share for lacustrine deposits)"""
    h, h2, tx, cv = (hclass or ''), (hclass2 or ''), (texture or ''), (cover or '')
    thin = cv in ('veneer', 'discontinuous')
    if h == 'I':
        return 'ICE'
    if h == 'R':
        if h2 == 'O':
            return 'PEAT_THIN'
        if thin and h2 == 'C':
            return 'COLL_FINES_THIN'
        if thin and h2 in ('T', 'W', 'GF', 'M', 'GM', 'Q'):
            return 'TILL_VENEER'            # thin mineral cover over rock: the published thin-till profile (proxy)
        return 'BEDROCK'
    if h == 'T':
        return 'TILL_VENEER' if thin else 'TILL_THICK'
    if h == 'C':
        if tx == 'bouldery':
            return 'COLL_BOULDERY'
        return 'COLL_FINES_THIN' if thin else 'COLL_FINES'
    if h == 'W':
        return 'REG_BOULDERY' if tx == 'bouldery' else 'REG_FINES'
    if h == 'O':                    # thin peat over mineral soil (GTK, NGU) stays PEAT with a shallow peat base;
        return 'PEAT_THIN' if h2 == 'R' else 'PEAT'     # only peat over rock is the thin-organic-on-bedrock profile
    if h == 'F':
        if tx in ('fines', 'organic') or h2 in ('M', 'L', 'O'):
            return 'FLUV_FINES'
        return 'FLUV_COARSE'
    if h == 'GF':
        return 'GLACIOFLUVIAL'
    if h == 'GL':
        return 'SILT_PROXY'
    if h in ('M', 'GM'):
        if tx in ('sand', 'gravel'):
            return 'SAND_LOWLAND'
        return 'TILL_VENEER' if thin and h == 'GM' else 'MARINE_FINES'
    if h in ('L', 'K'):
        return 'LAC_UNGLACIATED' if (h == 'K' or (lgm_ice_share or 0.0) < 0.5) else 'SILT_PROXY'
    if h == 'Y':
        return 'YEDOMA'
    if h == 'E':
        return 'SAND_LOWLAND' if tx in ('sand', 'gravel') else 'SILT_PROXY'
    if h == 'V':
        return 'VOLCANIC'
    if h == 'Q':
        return 'TILL_THICK'
    return 'NONE'


# ------------------------------------------------------------------ thickness
NUM = r'(\d+(?:[.,]\d+)?)'
_UNIT = r'\s*(cm|m)\b'
_PATS = [  # (kind, regex): kind tells how to read the numbers
    ('range', re.compile(rf'{NUM}\s*(?:-|–|—|to|до|à|a|til|till)\s*{NUM}{_UNIT}\s*(?:thick|in thickness)?', re.I)),
    ('max', re.compile(rf'(?:less than|under|up to|<|≤|inférieure à|до|менее)\s*{NUM}{_UNIT}', re.I)),
    ('min', re.compile(rf'(?:greater than|more than|over|>|≥|supérieure à|свыше|более)\s*{NUM}{_UNIT}', re.I)),
    ('exact', re.compile(rf'(?:about|approximately|around|около)?\s*{NUM}{_UNIT}\s*(?:thick|in thickness)', re.I)),
]
_CONTEXT = re.compile(r'thick|épaisseur|мощн|m(?:e|ä)ktighet|paksu|couverture|veneer|blanket|mantle|cover', re.I)
_NOT_THICKNESS = re.compile(r'\b(?:high|long|wide|relief|across|in diameter|deep water|elevation|a\.s\.l)\b', re.I)
_NOT_BEFORE = re.compile(r'(?:relief|height|high|diameter|wide|width|long|length|depth|elevation|altitude|'
                         r'высот|глубин|hauteur|profondeur)\w*(?:\W+\w{1,5}){0,2}\W*$', re.I)   # 'relief of', 'high, up to'


def _f(s, unit):
    v = float(s.replace(',', '.'))
    return v / 100.0 if unit.lower() == 'cm' else v


def parse_thickness(text):
    """(min_m, max_m, matched text) from a legend description, or None. Only statements in a thickness context;
    heights of landforms ('< 10 m high', '2 km long') are not thicknesses."""
    if not isinstance(text, str) or not _CONTEXT.search(text):
        return None
    for kind, p in _PATS:
        for m in p.finditer(text):
            tail = text[m.end():m.end() + 12]
            head = text[max(0, m.start() - 24):m.start()]
            if _NOT_THICKNESS.search(tail) or _NOT_THICKNESS.search(m.group(0)) or _NOT_BEFORE.search(head):
                continue
            g = m.groups()
            if kind == 'range':
                a, b = sorted((_f(g[0], g[2]), _f(g[1], g[2])))
                return a, b, m.group(0).strip()
            v = _f(g[0], g[1])
            if kind == 'max':
                return 0.0, v, m.group(0).strip()
            if kind == 'min':
                return v, math.inf, m.group(0).strip()
            return v, v, m.group(0).strip()
    return None


# GSC Map 1814A (Klassen et al. 1992), raster legend read 2026-10-07: thickness stated per unit (tier 1a)
MAP1814A = {'glaciomarine and marine': (5.0, math.inf, 'thick (>5 m) blanket'),
            'glaciolacustrine': (2.0, math.inf, 'blanket deposits >2 m thick'),
            'till, undifferentiated': (0.0, math.inf, 'includes thin (<2 m) and discontinuous deposits; no unit '
                                                       'thickness'),
            'drift poor': (0.0, 1.0, 'materials generally <1 m thick and discontinuous; >80 % bedrock')}

# cover terms per legend system (tier 1b): {system: {term: (min_m, max_m, definition, citation)}}; a term may instead
# map to {hclass: (...)} when the system defines it per deposit (GTK: thin / thick peat vs thin till on rock).
# Compiled 2026-10-08, quotes and sources in addendum/cover_term_definitions_2026-10-08.md. 'inferred' marks a
# convention applied to a product that does not state it.
INF = math.inf
_SDM = 'GSC Surficial Data Model (Deblonde et al. 2017, OF 8236 v2.3.0, App. 4; v2.5.1 2024, doi:10.4095/332530)'
_TCS = 'Howes and Kenk 1997, Terrain Classification System for British Columbia v2'
COVER_DEFS = {
    'GSC_SDM': {'veneer': (0.0, 2.0, '"veneer sediments < 2 m"', _SDM),
                'blanket': (2.0, INF, '"blanket sediments > 2 m"', _SDM)},
    'GSC_PRE_SDM': {'veneer': (0.0, 2.0, 'GSC convention (SDM "< 2 m") applied to a pre-SDM map (inferred)', _SDM),
                    'blanket': (2.0, INF, 'GSC convention (SDM "> 2 m") applied to a pre-SDM map (inferred)', _SDM)},
    'GSC_CGM195': {'veneer': (0.0, 2.0, 'till veneer "inférieur à 2 m d\'épaisseur" (French legend)',
                              'CGM 195, doi:10.4095/295462'),
                   'blanket': (2.0, INF, 'not quantified in CGM 195; SDM "> 2 m" applied (inferred)', _SDM)},
    'BC_TCS': {'veneer': (0.1, 1.0, '"between about 10 cm and 1m in thickness"', _TCS + ', pp. 39-40'),
               'blanket': (1.0, INF, '"A blanket is greater than 1 metre thick"', _TCS + ', p. 29')},
    'YGS': {'veneer': (0.1, 1.0, '"veneer (0.1 - 1 m thick)"', 'Lipovsky and Bond 2023, Yukon surficial compilation'),
            'blanket': (1.0, INF, '"blanket (>1 m thick)"', 'Lipovsky and Bond 2023, Yukon surficial compilation')},
    'QC_SIGEOM': {'veneer': (0.0, 1.0, 'Tm "Diamicton de moins de 1 m d\'épaisseur"',
                             'MRNF Québec, zones morphosédimentologiques'),
                  'blanket': (1.0, INF, 'Tc "dont l\'épaisseur est supérieure à 1 m"',
                              'MRNF Québec, zones morphosédimentologiques')},
    'NL_50K': {'veneer': (0.0, 1.5, '"Any deposit less than 1.5 m thick"', 'GSNL 1:50 000 surficial legend, morphology'),
               'blanket': (1.5, INF, '"Any deposit greater than 1.5 m thick"',
                           'GSNL 1:50 000 surficial legend, morphology')},
    'SK': {'veneer': (0.1, 1.0, 'not stated in the 1:250k product; SGS 1:1M "10 cm to 1 m thick" and the CSSC '
                                'convention (inferred)', 'Saskatchewan Geological Survey 1:1M; CSSC 3rd ed. ch. 18')},
    'NGU': {'discontinuous': (0.0, 0.5, '"normalt mindre enn 0,5 m" (thin or discontinuous cover)',
                              'NGU løsmassetype kodeliste, codes 12, 43, 52'),
            'veneer': (0.0, 0.5, '"sjelden mer enn 0.5 m tykk" (thin cover)', 'NGU løsmassetype kodeliste, code 12'),
            'blanket': (0.5, INF, '"tykkelse fra 0,5 m til flere ti-talls meter" (continuous cover)',
                        'NGU produktspesifikasjon LøsmasseN250/N50 (2010), pp. 9-10')},
    'GTK': {'veneer': {'O': (0.3, 0.6, 'thin peat "0,3-0,6 m turvetta"', 'GTK maaperä 1:200 000 metadata'),
                       '*': (0.0, 1.0, 'rock with thin till "ohuesti (alle 1 m) moreenin peittämää kalliota"',
                             'Kielosto et al. 2008, GTK map explanation, p. 3')},
            'blanket': {'O': (0.6, INF, 'thick peat "> 0,6 m"', 'GTK maaperä 1:200 000 metadata')}},
}
SRC_SYSTEM = {'ca_gsc_cgm': 'GSC_SDM', 'ca_gsc_5m': 'GSC_CGM195', 'ca_ygs_compilation': 'YGS',
              'ca_bc_ter': 'BC_TCS', 'ca_bc_tem_extra': 'BC_TCS', 'ca_qc_sigeom': 'QC_SIGEOM',
              'ca_nl_labrador': 'NL_50K', 'ca_sk_250k': 'SK', 'no_ngu_losmasser': 'NGU',
              'fi_gtk_maapera200k': 'GTK', 'fi_gtk_maapera20k': 'GTK'}
for _s in ('ca_gsc_scans', 'ca_gsc_legacy', 'ca_gsc_lines', 'ca_gsc_of5116', 'ca_gsc_of7038', 'ca_gsc_of7118',
           'ca_gsc_of7196', 'ca_gsc_of7289', 'ca_gsc_of8651', 'ca_gsc_bc_ofs'):
    SRC_SYSTEM[_s] = 'GSC_PRE_SDM'


def cover_def(src_id, cover, hclass=''):
    """(min_m, max_m, definition, citation) of a cover term in the source's legend system, or None"""
    d = COVER_DEFS.get(SRC_SYSTEM.get(src_id, ''), {}).get(cover)
    if isinstance(d, dict):
        d = d.get(hclass, d.get('*'))
    return d


def representative(lo, hi, default):
    """one depth for the bedrock contact from a thickness range: the middle of a closed range, half of a stated
    maximum (a 'veneer < 2 m' is 1 m), and for an open minimum the template default if deeper, else the minimum"""
    if math.isinf(hi):
        return round(max(lo, default) if default is not None else lo, 3)
    if lo <= 0:
        return round(hi / 2.0, 3)
    return round((lo + hi) / 2.0, 3)


def thickness(tid, src_id, src_code, src_desc, cover, hclass2='', hclass=''):
    """(min_m, max_m, depth_m, tier, basis) of the boundary the unit thickness controls (THK_LAYER: the bedrock
    contact, or the base of the peat) for a polygon of template tid"""
    t = TEMPLATES[tid]
    k = THK_LAYER.get(tid, t['base'])
    default = t['layers'][k]['top_m'] if k is not None else None
    over_rock = cover in ('veneer', 'discontinuous') or hclass2 == 'R' or bool(OVER_ROCK.search(src_desc or ''))
    cand = None
    if src_id == 'ca_gsc_1814a' and src_code in MAP1814A:
        lo, hi, txt = MAP1814A[src_code]
        if lo > 0 or not math.isinf(hi):
            cand = (lo, hi, '1a', f'GSC Map 1814A legend: {txt}')
    if cand is None:
        p = parse_thickness(src_desc)
        if p:
            cand = (p[0], p[1], '1a', f'unit legend text: "{p[2]}"')
    if cand is None and cover in ('veneer', 'blanket', 'discontinuous'):
        d = cover_def(src_id, cover, hclass)
        if d:
            cand = (d[0], d[1], '1b', f'{cover}: {d[2]} ({d[3]})')
    if cand is None:
        if default is None:
            return None, None, None, '2', 'no bedrock contact in the published profile'
        return None, None, default, '2', f'template default (Westermann et al. 2013 strategy): {default:g} m'
    lo, hi, tier, basis = cand
    hi_ = None if math.isinf(hi) else hi
    if default is None:                         # deep profile: only a thin cover over rock gets a bedrock contact
        if tid in THIN_OK and over_rock and hi_ is not None:
            return lo, hi_, representative(lo, hi, None), tier, basis + '; thin cover over bedrock'
        return lo, hi_, None, tier, basis + '; published deep profile kept (no bedrock contact)'
    return lo, hi_, representative(lo, hi, default), tier, basis


def realize(tid, depth):
    """STRAT_layers rows of template tid with its controlled boundary (THK_LAYER) at depth; None: the published
    profile as is. Bedrock contact: the cover layers above depth, then the base layer at depth. Peat: the organic
    layers above depth, the mineral-organic layer from depth, bedrock at max(published, depth + 2 m)."""
    t = TEMPLATES[tid]
    lay = [dict(x) for x in t['layers']]
    if depth is None or not lay:
        return lay
    depth = round(float(depth), 3)
    if tid in THK_LAYER:
        k = THK_LAYER[tid]
        top = [x for x in lay[:k] if x['top_m'] < depth]
        rock = dict(lay[t['base']], top_m=max(lay[t['base']]['top_m'], round(depth + 2.0, 3)))
        return top + [dict(lay[k], top_m=depth), rock]
    if t['base'] is None:
        if tid not in THIN_OK:
            return lay
        return [x for x in lay if x['top_m'] < depth] + [BED(depth)]
    cover = [x for x in lay[:t['base']] if x['top_m'] < depth]
    return cover + [dict(lay[t['base']], top_m=depth)]


def _test():
    assert assign('T', '', 'diamicton', 'veneer') == 'TILL_VENEER'
    assert assign('T', '', 'diamicton', 'blanket') == 'TILL_THICK'
    assert assign('L', '', 'fines', '', 0.9) == 'SILT_PROXY' and assign('L', '', 'fines', '', 0.0) == 'LAC_UNGLACIATED'
    assert parse_thickness('Till blanket: glacial diamicton; 2-10 m thick') == (2.0, 10.0, '2-10 m thick')
    assert parse_thickness('Diamicton with rubble; < 2 m thick; derived from weathering')[:2] == (0.0, 2.0)
    assert parse_thickness('fields of ridges, generally < 2 km long and < 10 m high') is None
    assert parse_thickness('Sédiments minces : épaisseur inférieure à 0,5 m')[:2] == (0.0, 0.5)
    lo, hi, d, tier, _ = thickness('TILL_THICK', 'ca_gsc_legacy', '', 'Till blanket: glacial diamicton; 2-10 m thick', '')
    assert (lo, hi, d, tier) == (2.0, 10.0, 6.0, '1a')
    assert [x['top_m'] for x in realize('TILL_THICK', 6.0)] == [0, 2, 6.0]
    assert [x['top_m'] for x in realize('TILL_THICK', 0.5)] == [0, 0.5]
    assert thickness('TILL_THICK', 'ru_vsegei_pdf', 'gIII', 'морена', '')[2:4] == (10, '2')
    lo, hi, d, tier, _ = thickness('MARINE_FINES', 'ca_gsc_1814a', 'glaciomarine and marine', '', 'blanket')
    assert (d, tier) == (None, '1a')
    lo, hi, d, tier, _ = thickness('PEAT', 'ru_vsegei_pdf', 'bH', 'Holocene bog peat cover (up to 2 m) over 1st '
                                   'terrace alluvium', '')
    assert (lo, hi, d, tier) == (0.0, 2.0, 1.0, '1a')
    assert [x['top_m'] for x in realize('PEAT', 1.0)] == [0, 0.5, 1.0, 10]
    lo, hi, d, tier, _ = thickness('MARINE_FINES', 'x', '', 'marine veneer: sand, less than 1 m thick over bedrock',
                                   'veneer')
    assert d == 0.5 and [x['top_m'] for x in realize('MARINE_FINES', d)] == [0, 0.2, 0.5]
    # tier 1b: the legend system's definition of the cover term
    assert thickness('TILL_VENEER', 'ca_ygs_compilation', 'Mv', 'morainal veneer', 'veneer')[2:4] == (0.55, '1b')
    assert thickness('TILL_VENEER', 'ca_gsc_cgm', 'Tv', 'Till veneer', 'veneer')[2:4] == (1.0, '1b')
    assert thickness('TILL_THICK', 'ca_qc_sigeom', 'Tc', 'till', 'blanket')[2:4] == (10, '1b')
    assert thickness('PEAT', 'fi_gtk_maapera200k', '19551891', 'ohut turve', 'veneer', '', 'O')[2:4] == (0.45, '1b')
    assert thickness('PEAT', 'fi_gtk_maapera200k', '19551892', 'paksu turve', 'blanket', '', 'O')[2:4] == (2, '1b')
    assert thickness('TILL_VENEER', 'fi_gtk_maapera200k', '195111', 'kalliomaa', 'veneer', 'Q', 'R')[2:4] == (0.5, '1b')
    assert thickness('TILL_VENEER', 'us_usgs_sim3340', 'Qs', 'x', 'veneer')[3] == '2'      # no system definition
    assert parse_thickness('hummocks with a relief of 2 to 10 m; till veneer') is None
    for k, t in TEMPLATES.items():
        for x in t['layers']:
            assert x['waterIce'] + x['mineral'] + x['organic'] <= 1.0 + 1e-9, (k, x)      # air = 1 - sum >= 0
    print('addendum_params self-test ok;', len(TEMPLATES), 'templates')


if __name__ == '__main__':
    if '--test' in sys.argv:
        _test()
