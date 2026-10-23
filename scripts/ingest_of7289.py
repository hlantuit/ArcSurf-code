#!/usr/bin/env python
"""
GSC Open File 7289 (Cote, Duchesne, Wright & Ednie 2013), Digital compilation of the surficial sediments of the
Mackenzie Valley corridor, Yukon Coastal Plain, and the Tuktoyaktuk Peninsula; DOI 10.4095/292494.
Seven polygon shapefiles (LCC 'NWT Mackenzie Valley', NAD83) digitised from 1970s-2000 GSC terrain maps:
  1:125 000  south        085D 095A/B/G/H/I/J/N/O  Rutter et al. / Hawes, Preliminary Maps (1979-81)
             middle_east  096C/D/E 106H (OF 155, 1973), 096F 106P (OF 294, 1975), 106I (OF 97, 1972)
             106mn        106M/N (OF 97, 1972)
             northslope   107B 117A/C/D, Rampton (OF 191, 1974)
             tuk_rich     107C/D/E, Rampton (OF 96, 1972)
  1:250 000  middle_west  106G/J/K/L/O, Aylsworth et al. (GSC Bulletin 547, 2000)
             107b         107B, Aylsworth et al. (2000)
Three legends (report section 3, the extended legends):
  'duchesne' (south, middle_east, 106mn): dominant (D_), veneer (V_) and secondary (S_) unit, each a terrain
      symbol GENETIC (caps) + morphology (lower case) with two texture letters. Genetic M = MORAINAL (-> T),
      not marine. A veneer unit lies ON the dominant one (V 'Mv' over D 'R' = till veneer on bedrock): the
      veneer is the surface class and the dominant unit becomes hclass2; otherwise the secondary unit
      (5-49 %, D_PER) is hclass2. Morphology b = beach, v = veneer (< 1.5 m), k = kettled (G) or
      thermokarst (L, A).
  'rampton' (northslope, tuk_rich): GEN_CAT (C E F G L M O R X Y; Y = MARINE) + GEN_MOD (G glacial: FG
      glaciofluvial, LG glaciolacustrine, YG glaciomarine; Z / A active; K thermokarst; 1-5 terrace
      levels) + MOR_MOD + TXT_MOD + VENEER (a unit overlying the mapped one: surface class, mapped unit ->
      hclass2). Lower-case northslope VENEER values (a f g r, 45 km2) are not in the legend: ignored.
  'b547' (both 1:250k layers): plain symbols; here Mb = moraine BLANKET.
Dropped so that coarser sources show through (no harmonisable unit): U / Ug Upland, X undifferentiated or
unknown, S.H. (not in the legend), Photo Gap. Water -> H. Texture = the polygon's own first texture letter
(carried), else the genetic default. These legends map no ice content: ice_rich unknown; thermokarst
modifiers stay in src_extra. src_sheet = layer:NTS (sheet by representative point in
Basedata/corridor.shp, restricted to the layer's sheets); pub_year = that hardcopy map's year.
Source -> ca_gsc_of7289. usage: ingest_of7289.py
"""
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

SRC = 'ca_gsc_of7289'
D = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/ostr_new/292494/x/Data/Shapefiles'
LAYERS = {  # layer: (legend, scale, shapefile)
    'south': ('duchesne', 125_000, 'Scale125000/south.shp'),
    'middle_east': ('duchesne', 125_000, 'Scale125000/middle_east.shp'),
    '106mn': ('duchesne', 125_000, 'Scale125000/106mn.shp'),
    'northslope': ('rampton', 125_000, 'Scale125000/northslope.shp'),
    'tuk_rich': ('rampton', 125_000, 'Scale125000/tuk_rich.shp'),
    'middle_west': ('b547', 250_000, 'Scale250000/middle_west.shp'),
    '107b': ('b547', 250_000, 'Scale250000/107b.shp'),
}
PM = 'GSC Preliminary Map'
B547 = 'Aylsworth et al., GSC Bulletin 547'
SHEETS = {  # layer: {NTS: (pub_year, hardcopy map)}, from the report's 'Hardcopy Reference' tables
    'south': {'085D': (1979, f'Rutter & Boydell, {PM} 14-1978'),
              '095A': (1980, f'Rutter, Minning & Netterville, {PM} 16-1978'),
              '095B': (1980, f'Hawes, {PM} 11-1979'), '095G': (1981, f'Rutter & Boydell, {PM} 10-1979'),
              '095H': (1980, f'Rutter, Minning & Netterville, {PM} 3-1978'),
              '095I': (1980, f'Hawes, {PM} 10-1978'), '095J': (1980, f'Hawes, {PM} 9-1978'),
              '095N': (1980, f'Rutter, Minning & Netterville, {PM} 18-1978'),
              '095O': (1980, f'Rutter & Boydell, {PM} 13-1978')},
    'middle_east': {**{s: (1973, 'Hanley et al., GSC OF 155') for s in ('096C', '096D', '096E', '106H')},
                    **{s: (1975, 'Chatwin et al., GSC OF 294') for s in ('096F', '106P')},
                    '106I': (1972, 'Hughes, Hodgson & Pilon, GSC OF 97')},
    '106mn': {s: (1972, 'Hughes, Hodgson & Pilon, GSC OF 97') for s in ('106M', '106N')},
    'northslope': {s: (1974, 'Rampton, GSC OF 191') for s in ('107B', '117A', '117C', '117D')},
    'tuk_rich': {s: (1972, 'Rampton, GSC OF 96') for s in ('107C', '107D', '107E')},
    'middle_west': {s: (2000, B547) for s in ('106G', '106J', '106K', '106L', '106O')},
    '107b': {'107B': (2000, B547)},
}

# ---- 'duchesne' legend
DGEN = {'A': 'F', 'C': 'C', 'E': 'E', 'G': 'GF', 'L': 'L', 'M': 'T', 'O': 'O', 'P': 'F', 'R': 'R', 'S': 'C'}
DNAME = {'A': 'alluvial', 'C': 'colluvial', 'E': 'eolian', 'G': 'glaciofluvial', 'GL': 'glaciolacustrine',
         'L': 'lacustrine', 'M': 'morainal', 'O': 'organic', 'P': 'piedmont (mountain-front fans and aprons)',
         'R': 'bedrock', 'S': 'slump'}
MORPH = {'b': 'beach', 'c': 'channelled', 'd': 'drumlinoid', 'e': 'eroded', 'f': 'fan', 'g': 'glaciated',
         'h': 'hummocky', 'k': 'kettled / thermokarst', 'm': 'rolling', 'n': 'n', 'p': 'plain', 'r': 'ridged',
         's': 'striated (fluted)', 't': 'terrace', 'v': 'veneer (<1.5 m)', 'x': 'complex'}
SPECIAL = {'Water': ('H', 'unknown', 'water'), 'Mar': ('M', 'unknown', 'marine deposits'),
           'pO': ('O', 'unknown', 'peat'), 'pfO': ('O', 'unknown', 'bog-dominant peatland'),
           'fpO': ('O', 'unknown', 'fen-dominant peatland'), 'o': ('O', 'unknown', 'organic'),
           'sE': ('E', 'unknown', 'sandy eolian'),
           'U': ('DROP', 'unknown', 'Upland: bedrock-controlled upland, surficial units not differentiated'),
           'Ug': ('DROP', 'unknown', 'Upland (glaciated): surficial units not differentiated'),
           'X': ('DROP', 'unknown', 'undifferentiated or unknown'),
           'S.H.': ('DROP', 'unknown', 'S.H.: symbol not in the legend'),
           'Photo Gap': ('DROP', 'unknown', 'photo gap: not mapped')}
TXT = {'t': 'diamicton', 's': 'sand', '$': 'fines', 'c': 'fines', 'g': 'gravel', 'b': 'bouldery', 'r': 'bouldery',
       'p': 'organic', 'f': 'organic', 'o': 'organic'}       # sh / ss (bedrock lithology), q, k, m: unknown
TXT_NAME = {'b': 'boulders', 'c': 'clay', 'f': 'fen', 'g': 'gravel', 'o': 'organic', 'p': 'peat', 'r': 'rock and rubble',
            's': 'sand', '$': 'silt', 'sh': 'shale', 'ss': 'sandstone', 't': 'till'}
DEFTEX = {'T': 'diamicton', 'O': 'organic', 'E': 'sand', 'GF': 'gravel', 'GL': 'fines', 'L': 'fines'}
PER = {1: 'unknown %', 2: '5-15 %', 3: '16-49 %'}
# ---- 'b547' legend (report 3.2): symbol -> hclass, texture, cover, legend text
B547L = {'Ap': ('F', 'unknown', 'unknown', 'Alluvial plain'), 'At': ('F', 'unknown', 'unknown', 'Alluvial terrace'),
         'Af': ('F', 'unknown', 'unknown', 'Alluvial fan'), 'C': ('C', 'unknown', 'unknown', 'Colluvium'),
         'Cz': ('C', 'unknown', 'unknown', 'Colluvial complex'), 'E': ('E', 'sand', 'unknown', 'Eolian ridges'),
         'Lpf': ('L', 'fines', 'unknown', 'Lacustrine plain, fine grained sediments'),
         'Lpc': ('L', 'sand', 'unknown', 'Lacustrine plain, coarse grained sediments'),
         'Lv': ('L', 'unknown', 'veneer', 'Lacustrine veneer'),
         'Gp': ('GF', 'gravel', 'unknown', 'Glaciofluvial outwash plain'),
         'Gx': ('GF', 'gravel', 'unknown', 'Glaciofluvial ice contact deposits'),
         'Mp': ('T', 'diamicton', 'unknown', 'Moraine plain'), 'Mb': ('T', 'diamicton', 'blanket', 'Moraine blanket'),
         'Mv': ('T', 'diamicton', 'veneer', 'Moraine veneer'), 'Md': ('T', 'diamicton', 'unknown', 'Drumlinoid plain'),
         'Mh': ('T', 'diamicton', 'unknown', 'Hummocky moraine'), 'R': ('R', 'unknown', 'unknown', 'Bedrock'),
         'Mar': ('M', 'unknown', 'unknown', 'Marine deposits'),
         'fpO': ('O', 'organic', 'unknown', 'Fen dominant peatland'),
         'pfO': ('O', 'organic', 'unknown', 'Bog dominant peatland')}
# ---- 'rampton' legend (report 3.1.4-3.1.5)
RGEN = {'C': 'C', 'E': 'E', 'F': 'F', 'G': 'GF', 'L': 'L', 'M': 'T', 'O': 'O', 'R': 'R', 'Y': 'M'}
RNAME = {'C': 'colluvial', 'E': 'eolian', 'F': 'fluvial', 'G': 'glaciofluvial', 'L': 'lacustrine', 'M': 'morainal',
         'O': 'organic', 'R': 'bedrock', 'Y': 'marine'}
RMOD = {'A': 'active deposition', 'Z': 'process still active', 'F': 'fluvial', 'G': 'glacial', 'K': 'thermokarst',
        '1': 'floodplain and low-level terrace', '2': 'terrace level 2', '3': 'intermediate level terrace',
        '4': 'high level terrace', '5': 'pediment level'}
RTXT = {'fines': 'fines', 'g': 'gravel', 'b': 'bouldery', 'coarse': 'mixed', 'f,g': 'mixed', 's': 'sand',
        't': 'diamicton', 'c': 'fines', 't,g': 'diamicton', '$': 'fines', 'stony c': 'diamicton', 's,g': 'sand',
        's,$': 'sand', 'c,s': 'fines', 'c,$': 'fines', 'g,s': 'gravel', '$,s': 'fines', '$,c': 'fines', 's,c': 'sand'}


def dparse(c):
    """'duchesne' symbol -> (hclass, cover, name); None when not a unit ('' or B boulders)."""
    if not c:
        return None
    if c in SPECIAL:
        return SPECIAL[c]
    gen, morph = ('GL', c[2:]) if c.startswith('GL') else (c[0], c[1:])
    h = 'GL' if gen == 'GL' else DGEN.get(gen)
    if h is None:
        return None
    cover = 'veneer' if 'v' in morph else 'unknown'
    name = DNAME[gen] + (' ' + ', '.join(MORPH.get(m, m) for m in morph) if morph else '')
    return h, cover, name


def rparse(cat, mod):
    """'rampton' GEN_CAT + GEN_MOD -> (hclass, hclass2, name)."""
    if cat == 'Water':
        return 'H', '', 'water'
    if cat in ('X', 'Photo Gap', ''):
        return 'DROP', '', 'undifferentiated or unknown' if cat == 'X' else 'photo gap: not mapped'
    cats = [x.strip() for x in cat.split(',')]
    h, h2 = RGEN[cats[0]], (RGEN[cats[1]] if len(cats) > 1 else '')
    if mod == 'G':
        h = {'F': 'GF', 'L': 'GL', 'Y': 'GM'}.get(cats[0], h)
    if mod == 'K' and cats[0] == 'L':
        h, h2 = 'K', 'L'
    name = ' with '.join(RNAME[x] for x in cats) + (f' ({RMOD.get(mod, mod)})' if mod else '')
    if h != RGEN[cats[0]]:
        name += ' = ' + S.HCLASS[h].lower()
    return h, ('' if h2 == h else h2), name


def tx(t1, t2):
    return '/'.join(TXT_NAME.get(t, t) for t in (t1, t2) if t)


XW = {}          # xkey -> (hclass, hclass2, texture, cover, note)


def duchesne(g, layer):
    out = []
    for r in g.itertuples(index=False):
        Dc, Vc, Sc = r.D_GENE, r.V_GENE, r.S_GENE
        d, v, s = dparse(Dc), dparse(Vc), dparse(Sc)
        dper = pd.to_numeric(r.D_PER, errors='coerce')
        if v and v[0] not in ('DROP', 'H') and d:
            key, t1, h2 = Vc, r.V_TXT1, (d[0] if d[0] not in ('DROP', 'H') else '')
            code = f'{r.V_TXT1}{r.V_TXT2}{Vc}/{r.D_TXT1}{r.D_TXT2}{Dc}'
            desc = f'{v[2]} ({tx(r.V_TXT1, r.V_TXT2) or "texture n/a"}) over {d[2]} ({tx(r.D_TXT1, r.D_TXT2) or "texture n/a"})'
            surf = v
        else:
            key, t1, surf = Dc, r.D_TXT1, d
            h2 = s[0] if (s and s[0] not in ('DROP', 'H')) else ''
            code = f'{r.D_TXT1}{r.D_TXT2}{Dc}' + (f' + {r.S_TXT1}{r.S_TXT2}{Sc}' if Sc else '')
            desc = (f'{d[2]} ({tx(r.D_TXT1, r.D_TXT2) or "texture n/a"})' if d else Dc) + (
                f'; with {s[2]} ({tx(r.S_TXT1, r.S_TXT2) or "texture n/a"}), {PER.get(dper, "share n/a")}' if s else '')
        if surf is None:                                        # empty D_GENE: not a unit
            surf, key = ('DROP', 'unknown', 'no unit'), key or '(empty)'
        if key not in XW:                                       # Lb = lacustrine BEACH: no fines default
            XW[key] = (surf[0], '', 'unknown' if key == 'Lb' else DEFTEX.get(surf[0], 'unknown'), surf[1],
                       f'OF 7289 {key}: {surf[2]}')
        h2 = '' if h2 == surf[0] else h2
        out.append((key, h2, TXT.get(t1, 'unknown'), 'unknown', code, desc,
                    f'D={Dc} {r.D_TXT1},{r.D_TXT2} per={r.D_PER}; V={Vc} {r.V_TXT1},{r.V_TXT2} per={r.V_PER}; '
                    f'S={Sc} {r.S_TXT1},{r.S_TXT2} per={r.S_PER}'))
    return out


def rampton(g, layer):
    out = []
    has_notes = 'NOTES' in g.columns
    for r in g.itertuples(index=False):
        cat, mod, mor, txm, ven = r.GEN_CAT, r.GEN_MOD, r.MOR_MOD, r.TXT_MOD, r.VENEER
        h, h2, name = rparse(cat, mod)
        sym = f'{cat}{mod}' + (f' {mor}' if mor else '') + (f' [{txm}]' if txm else '')
        if ven and ven[0].isupper():
            vh, vname = RGEN[ven[0]], RNAME[ven[0]] + ' ' + ', '.join({'v': 'veneer', 'r': 'ridges', 'p': 'plain'}.get(m, m) for m in ven[1:])
            key = f'Rv:{ven}'
            if key not in XW:
                XW[key] = (vh, '', DEFTEX.get(vh, 'unknown'), 'veneer', f'OF 7289 Rampton veneer {ven}: {vname.strip()} overlying the mapped unit')
            out.append((key, h if h not in ('DROP', 'H', vh) else '', 'unknown', 'unknown', f'{ven}/{sym}',
                        f'{vname.strip()} over {name}' + (f' ({txm})' if txm else ''), None))
        else:
            key = f'R:{cat}' + (f'|{mod}' if mod else '')
            if key not in XW:
                XW[key] = (h, h2, DEFTEX.get(h, 'unknown'), 'unknown', f'OF 7289 Rampton {cat}{mod}: {name}')
            cov = 'veneer' if 'v' in [m.strip() for m in mor.split(',')] else 'unknown'
            out.append((key, '', RTXT.get(txm, 'unknown'), cov, sym, name + (f', {mor}' if mor else '') + (f' ({txm})' if txm else ''), None))
        raw = f'GEN_CAT={cat} GEN_MOD={mod} MOR_MOD={mor} TXT_MOD={txm} VENEER={ven}' + (f' NOTES={r.NOTES}' if has_notes else '')
        out[-1] = out[-1][:6] + (raw,)
    return out


def b547(g, layer):
    out = []
    for r in g.itertuples(index=False):
        c = r.POLYGON_AT
        h, t, cov, name = B547L[c] if c in B547L else ('DROP', 'unknown', 'unknown', f'{c}: not in the legend')
        key = f'B547:{c}'
        if key not in XW:
            XW[key] = (h, '', t, cov, f'OF 7289 (Bulletin 547 legend) {c}: {name}')
        out.append((key, '', 'unknown', 'unknown', c, name, f'POLYGON_AT={c}'))
    return out


corr = gpd.read_file(f'{D}/Basedata/corridor.shp')[['MAPSHEET', 'geometry']]
parts = []
for layer, (legend, scale, path) in LAYERS.items():
    g = gpd.read_file(f'{D}/{path}')
    for c in g.columns:          # all-null columns come back float NaN, and astype(str) keeps NaN missing
        if c != 'geometry':
            g[c] = [('' if v is None or (isinstance(v, float) and np.isnan(v)) else str(v).strip()) for v in g[c]]
    ok = list(SHEETS[layer])
    cs = corr[corr.MAPSHEET.isin(ok)].reset_index(drop=True).to_crs(g.crs)
    rp = g.geometry.representative_point()
    dist = np.stack([rp.distance(geom).values for geom in cs.geometry], axis=1)
    g['nts'] = cs.MAPSHEET.values[dist.argmin(axis=1)]
    rows = {'duchesne': duchesne, 'rampton': rampton, 'b547': b547}[legend](g, layer)
    a = pd.DataFrame(rows, columns=['xkey', 'hclass2_src', 'texture_src', 'cover_src', 'code', 'desc', 'raw_attrs'])
    a['of7289_layer'] = layer
    a['src_sheet'] = layer + ':' + g['nts'].values
    a['scale_den'] = scale
    a['pub_year'] = [SHEETS[layer][s][0] for s in g['nts']]
    a['hardcopy'] = [SHEETS[layer][s][1] for s in g['nts']]
    parts.append(gpd.GeoDataFrame(a, geometry=g.geometry.values, crs=g.crs).to_crs(S.CRS))
    print(f'{layer}: {len(g)} polygons, sheets', g['nts'].value_counts().to_dict(), flush=True)
g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
g = S.in_amap(S.polygons_only(g))
u, _ = S.standardise(g, src_id=SRC, code='code', desc='desc', sheet='src_sheet', extra=('of7289_layer', 'hardcopy', 'raw_attrs'),
                     xkey='xkey', scale_den='scale_den', pub_year='pub_year', conf_tier='Surficial',
                     licence='Open Government Licence - Canada', redistribution='open',
                     carry=('hclass2_src', 'texture_src', 'cover_src'))
fps = []
for sh, grp in u.groupby('src_sheet'):
    f = S.footprint_from_units(grp, coarse=250.0)
    f['src_sheet'] = sh
    fps.append(f)
fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), geometry='geometry', crs=S.CRS)
p, m = S.write_std(u, fp, SRC, dict(title='GSC OF 7289 Digital compilation of the surficial sediments of the Mackenzie '
                                          'Valley corridor, Yukon Coastal Plain and Tuktoyaktuk Peninsula (1:125k 1972-81 '
                                          'terrain maps; 1:250k Bulletin 547)'))
pd.DataFrame([[k, *v[:4], 'unknown', v[4]] for k, v in sorted(XW.items())],
             columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(
    f'{S.XWALK}/{SRC}.csv', index=False)
print(SRC, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes') if k in m}, '| footprints', len(fp))
x = u.assign(km2=u.area / 1e6).merge(pd.DataFrame([(k, v[0]) for k, v in XW.items()], columns=['xkey', 'hclass']), on='xkey')
print('area by hclass (km2):', x.groupby('hclass').km2.sum().round().sort_values(ascending=False).to_dict())
print('area by layer:', x.groupby(x['src_sheet'].str.split(':').str[0]).km2.sum().round().to_dict())
print('carried texture:', u.assign(km2=u.area / 1e6).groupby('texture_src').km2.sum().round().to_dict())
