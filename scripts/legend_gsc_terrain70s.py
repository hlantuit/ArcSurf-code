"""Sheet legend for the 1970s GSC Mackenzie Valley terrain maps (OF 97, 155, 294; the hardcopy behind OF 7289's
'Duchesne' layers), generated for every transcribed label. Grammar (OF 7289 report, sections 3.1.1-3.1.3):
  unit   = texture letters (lower case: t till, s sand, $ silt, c clay, g gravel, b boulders, r rubble, p peat,
           f fen, o organic) + GENETIC capital (A alluvial, C colluvial, E eolian, G glaciofluvial, GL
           glaciolacustrine, L lacustrine, M MORAINAL, O organic, P piedmont, R bedrock, S slump, U upland)
           + morphology (b beach, c channelled, d drumlinoid, e eroded, f fan, h hummocky, k kettled/thermokarst
           or karst, m rolling, p plain, r ridged, s striated, t terrace, v veneer < 1.5 m, x complex)
  A/B    = A with 5-15 % B;  A-B = A with 16-49 % B;  A+B = A with an unknown share of B   (B -> hclass2)
  A//B   = A over B: the map's stacked symbol, a veneer A on B (cover veneer, B -> hclass2); transcribed as '//'
M is morainal (T), not marine. Texture = the first unit's first texture letter ('sg'/'gs' -> gravel), else the
genetic default. Ice content is not mapped: ice_rich unknown.
usage: legend_gsc_terrain70s.py <labels.csv (id,label)> <out legend.csv>"""
import re
import sys

import pandas as pd

GEN = {'A': 'F', 'C': 'C', 'E': 'E', 'G': 'GF', 'L': 'L', 'M': 'T', 'O': 'O', 'P': 'F', 'R': 'R', 'S': 'C', 'U': 'R'}
GNAME = {'A': 'alluvial', 'C': 'colluvial', 'E': 'eolian', 'G': 'glaciofluvial', 'GL': 'glaciolacustrine',
         'L': 'lacustrine', 'M': 'morainal', 'O': 'organic', 'P': 'piedmont', 'R': 'bedrock', 'S': 'slump',
         'U': 'upland'}
MORPH = {'b': 'beach', 'c': 'channelled', 'd': 'drumlinoid', 'e': 'eroded', 'f': 'fan', 'h': 'hummocky',
         'k': 'kettled / thermokarst (karst on bedrock)', 'm': 'rolling', 'p': 'plain', 'r': 'ridged',
         's': 'striated', 't': 'terrace', 'v': 'veneer (<1.5 m)', 'x': 'complex'}
TXT = {'t': 'diamicton', 's': 'sand', '$': 'fines', 'c': 'fines', 'g': 'gravel', 'b': 'bouldery', 'r': 'bouldery',
       'p': 'organic', 'f': 'organic', 'o': 'organic'}
TNAME = {'t': 'till', 's': 'sand', '$': 'silt', 'c': 'clay', 'g': 'gravel', 'b': 'boulders', 'r': 'rubble',
         'p': 'peat', 'f': 'fen', 'o': 'organic'}
DEFTEX = {'T': 'diamicton', 'O': 'organic', 'E': 'sand', 'GF': 'gravel', 'GL': 'fines', 'L': 'fines'}
SHARE = {'/': '5-15 %', '-': '16-49 %', '+': 'unknown share'}


def unit(tok):
    m = re.match(r'^([a-z$]*)(GL|[A-Z])([a-z]*)$', tok)
    if not m:
        raise ValueError(f'unparsed unit {tok!r}')
    tx, gen, morph = m.groups()
    h = 'GL' if gen == 'GL' else GEN[gen]
    tex = 'gravel' if tx[:2] in ('sg', 'gs') else TXT.get(tx[:1], DEFTEX.get(h, 'unknown'))
    cover = 'veneer' if 'v' in morph else 'unknown'
    name = (f"{'/'.join(TNAME.get(c, c) for c in tx)} " if tx else '') + GNAME[gen] + \
        (' ' + ', '.join(MORPH.get(c, c) for c in morph) if morph else '')
    return h, tex, cover, name


rows = []
for lbl in sorted(pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)['label'].unique()):
    if '//' in lbl:                               # stacked: veneer over the lower unit
        top, bot = lbl.split('//', 1)
        h, tex, _, name = unit(re.split(r'[/+-]', top)[0])
        b = unit(re.split(r'[/+-]', bot)[0])
        rows.append((lbl, h, b[0] if b[0] != h else '', tex, 'veneer', f'{name}, as a veneer over {b[3]}'))
        continue
    m = re.match(r'^([^/+-]+)(?:([/+-])(.+))?$', lbl)
    a, sep, b = m.groups()
    h, tex, cov, name = unit(a)
    h2, desc = '', name
    if sep:
        o = unit(b)
        h2 = o[0] if o[0] != h else ''
        desc += f' with {SHARE[sep]} {o[3]}'
    rows.append((lbl, h, h2, tex, cov, desc))
pd.DataFrame(rows, columns=['label', 'hclass', 'hclass2', 'texture', 'cover', 'description']).to_csv(
    sys.argv[2], index=False, lineterminator='\n')
print(len(rows), 'labels ->', sys.argv[2])
