"""Sheet legend for GSC Paper 81-9 red 'lithogenetic' units (Hodgson 1982; Map 2-1981 Southern Ellef Ringnes,
King Christian and adjacent islands; Map 1-1981 uses the same units), generated for every transcribed label.
Label grammar: unit number 1-14, '7a/7b/8a/8b' are units; any other trailing letter is the bedrock formation
(legend 'Rock Formation/Type', red letters a-r); 'N/D' = veneer N over unit D: the legend's marine veneers
'9/5', '10/6', '10/5+6' (+ formation letter), and on Map 1-1981 also '11/3o', '9/8a', '10/7b', '8b/7a' (top unit,
cover veneer, bottom unit -> hclass2); 'A+B' = A with B (B -> hclass2).
Rock/residual rock (2, 3) = 'bedrock commonly mantled by residual weathered rock' -> R with W (hclass2), and
marine-reworked rock (5, 6) -> R with M: the newer CGM maps of the same islands (CGM 398/399/426, Amund Ringnes)
map this terrain as bedrock; with W first, Map 1-1981 agreed 31 % with them, with W read as R 80 %. Texture from the
formation's 'weathers to ...' where it differs from the unit's (b rubble; d, f, g mixed).
usage: legend_hodgson81.py <labels.csv (id,label)> <out legend.csv>"""
import re
import sys

import pandas as pd

UNIT = {  # unit: hclass, hclass2, texture, cover, legend text
    '14': ('F', '', 'sand', '', 'Fluvial coarse grained sediments: dominantly sand, locally gravel'),
    '13': ('F', '', 'fines', '', 'Fluvial fine grained sediments: very fine sand, silt; minor clay, gravel'),
    '12': ('F', 'M', 'sand', '', 'Deltaic sediments - coarse over fine: sand; minor fines, gravel; overlies fines'),
    '11': ('C', '', 'mixed', '', 'Colluvial deposits: rubble to fines'),
    '10': ('M', '', 'sand', 'blanket', 'Marine thick coarse grained sediment: sand, minor gravel, >2 m thick'),
    '9': ('M', '', 'fines', 'blanket', 'Marine thick fine grained sediment: clay to fine sand, >2 m thick'),
    '10/': ('M', 'R', 'sand', 'veneer', 'Marine coarse grained veneer over coarse or fine grained marine-reworked rock: '
            'sand, minor gravel, <2 m thick, overlying unit {d}'),
    '9/': ('M', 'R', 'fines', 'veneer', 'Marine fine grained veneer over fine rock: clay to fine sand, <2 m thick, '
           'overlying unit {d}'),
    '8b': ('T', 'F', 'diamicton', 'veneer', 'Cornwall and Graham diamicton: fines and gravel, 1-2 m thick overlying '
           'plateau gravel (unit 7a)'),
    '8a': ('T', '', 'diamicton', 'blanket', 'Amund Ringnes diamicton: thick silty stony clay'),
    '7b': ('GF', '', 'sand', '', 'Gravel ridges (mid-Quaternary eskers?): sand, minor gravel to fines'),
    '7a': ('F', '', 'gravel', '', 'Plateau gravel (relict fluvial?): gravel to fines'),
    '6': ('R', 'M', 'sand', '', 'Coarse grained marine-reworked rock: marine-reworked form of the clastic rock units of '
          'unit 3'),
    '5': ('R', 'M', 'fines', '', 'Fine grained marine-reworked rock: marine-reworked form of the clastic rock units of '
          'unit 2'),
    '4': ('R', '', 'unknown', '', 'Dykes and sills'),
    '3': ('R', 'W', 'sand', '', 'Coarse grained rock/residual rock: dominantly sandstone, noncemented to indurated'),
    '2': ('R', 'W', 'fines', '', 'Fine grained rock/residual rock: shale, siltstone, minor sandstone'),
    '1': ('R', '', 'unknown', '', 'Diapiric dome: gypsum, anhydrite, igneous rocks'),
}
FORM = {'a': 'Bjorne Fm (sandstone; weathers to sand and rubble)',
        'b': 'Schei Point Fm (siltstone, sandstone, indurated; weathers to rubble, minor silt and sand)',
        'c': 'Blaa Mountain Fm (shale, siltstone; weathers to clayey silt)',
        'd': 'Heiberg Fm lower member (sandstone and shale; weathers to sand, fines, rubble)',
        'e': 'Heiberg Fm upper member (sandstone; weathers to sand, sandstone rubble)',
        'f': 'Jaeger Fm (sandstone; weathers to silty sand, gravel, sandstone rubble)',
        'g': 'Borden Island Fm (sandstone; weathers to silty sand, gravel, sandstone rubble)',
        'h': 'Savik Fm (shale, minor sandstone; weathers to silty clay, silt, shale fragments)',
        'i': 'Ringnes Fm (papery shale; weathers to clayey silt)',
        'j': 'Awingak Fm (sandstone; weathers to sand, minor silt, rubble)',
        'k': 'Deer Bay Fm (papery shale; weathers to clayey silt)',
        'm': 'Isachsen Fm (sandstone, minor siltstone and shale; weathers to sand, minor silt and clay)',
        'n': 'Christopher Fm (soft papery shale; weathers to silty clay or clay)',
        'o': 'Hassel Fm (sandstone, poorly cemented; weathers to sand, silt)',
        'p': 'Kanguk Fm (soft acidic shale; weathers to clayey silt and shale fragments)',
        'q': 'Eureka Sound Fm lower member (sandstone, siltstone, shale; weathers to fine sand to silty clay)',
        'r': 'Eureka Sound Fm upper member (poorly to noncemented; weathers to sand, silt)'}
FTEX = {'b': 'bouldery', 'd': 'mixed', 'f': 'mixed', 'g': 'mixed'}


def unit(tok):
    """one unit symbol ('3o', '8a', '12', '5'): number 1-14; '7a/7b/8a/8b' are units, any other letter a formation"""
    m = re.match(r'^(\d+)([a-z]?)\??$', tok)
    if not m:
        raise ValueError(f'unparsed unit {tok!r}')
    num, let = m.groups()
    key, form = (num + let, '') if num in ('7', '8') else (num, let)
    h, h2, tex, cov, txt = UNIT[key]
    if form:
        txt += f'; formation {form}: {FORM[form]}'
        if key in ('2', '3', '5', '6'):          # rock units weather to the formation's material; veneers keep theirs
            tex = FTEX.get(form, tex)
    return h, h2, tex, cov, txt


def one(tok):
    """'N/D' = veneer N over unit D (the legend's own '10/6', '9/5', '8b over 7a'; D may be '5+6'); else a unit"""
    m = re.match(r'^(\d+[a-z]?)/((?:5\+6|6\+5)[a-z]?|\d+[a-z]?)\??$', tok)
    if not m:
        return unit(tok)
    top, bot = m.groups()
    if top in ('9', '10') and re.match(r'^(5|6|5\+6|6\+5)[a-z]?$', bot):
        d, let = re.match(r'^([\d+]+)([a-z]?)$', bot).groups()
        h, h2, tex, cov, txt = UNIT[top + '/']
        txt = txt.format(d=d.replace('6+5', '5+6'))
        if let:
            txt += f'; formation {let}: {FORM[let]}'
        return h, h2, tex, cov, txt
    th, _, ttex, _, ttxt = unit(top)
    bh = unit(bot.split('+')[0])
    if top in ('9', '10'):                   # the marine units' own texts say 'thick, >2 m': not for a veneer
        ttxt = ('Marine coarse grained sediment: sand, minor gravel' if top == '10' else
                'Marine fine grained sediment: clay to fine sand') + ', <2 m thick'
    return th, (bh[0] if bh[0] != th else ''), ttex, 'veneer', f'{ttxt}; as a veneer over unit {bot}: {bh[4]}'


rows = []
for lbl in sorted(pd.read_csv(sys.argv[1], dtype=str, keep_default_na=False)['label'].unique()):
    # 'A+B': A with B (B -> hclass2); a '+' inside a fraction's denominator ('9/5+6') belongs to the fraction
    m = re.match(r'^(\d+[a-z]?/(?:5\+6|6\+5)[a-z]?)(?:\+(.+))?$', lbl)
    parts = [m.group(1)] + ([m.group(2)] if m.group(2) else []) if m else lbl.split('+')
    h, h2, tex, cov, txt = one(parts[0])
    if len(parts) > 1:
        o = one(parts[1])
        h2 = o[0] if o[0] != h else h2
        txt += f' | with {o[4]}'
    rows.append((lbl, h, h2, tex, cov, txt))
pd.DataFrame(rows, columns=['label', 'hclass', 'hclass2', 'texture', 'cover', 'description']).to_csv(sys.argv[2], index=False)
print(len(rows), 'labels ->', sys.argv[2])
