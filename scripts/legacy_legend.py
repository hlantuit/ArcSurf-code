"""Classify legacy GSC A-series / Open File units from the sheet's own legend table
(geo<n>_leg.dbf: CODE, LEVEL_1..6 hierarchy, ENTRY_1..n description). Symbol letters are
NOT reliable on these maps (A2094a: L = glaciolacustrine, D1/D2 = deltas, Pp-s = bedrock),
so the legend text decides. The deepest LEVEL naming a genesis wins, then the ENTRY text.
Texture/cover/ice only where the text states them."""
import glob
import re

import pyogrio

# (pattern, hclass); order matters: specific glacial-environment terms before generic ones
GEN = [
    (r'BEDROCK|PRE-QUATERNARY|PRECAMBRIAN|PALEOZOIC|PROTEROZOIC|ARCHEAN|ROCK WEATHERING', 'R'),
    (r'GLACIOLACUSTRINE|GLACIAL LAKE', 'GL'),
    (r'GLACIOMARINE|GLACIAL MARINE|GLACIMARINE', 'GM'),
    (r'GLACIOFLUVIAL|OUTWASH|ESKER|KAME|ICE-CONTACT', 'GF'),
    (r'\bTILL\b|MORAIN|DIAMICTON DEPOSITED BY GLACIER', 'T'),
    (r'EOLIAN|AEOLIAN|DUNE|LOESS', 'E'),
    (r'COLLUVI|LANDSLIDE|TALUS|MASS[- ]WASTING|SOLIFLUCTION|ROCK GLACIER|DEBRIS FLOW', 'C'),
    (r'WEATHERED|REGOLITH|FELSENMEER|BLOCKFIELD|RESIDUAL', 'W'),
    (r'ORGANIC|PEAT|\bBOG\b|\bFEN\b|MUCK', 'O'),
    (r'MARINE|LITTORAL|BEACH|TIDAL|ESTUARINE', 'M'),
    (r'ALLUVIAL|FLUVIAL|FLOODPLAIN|DELTAIC', 'F'),
    (r'LACUSTRINE', 'L'),
    (r'GLACIER|PERENNIAL (ICE|SNOW)|ICEFIELD|ICE CAP|SNOWFIELD', 'I'),
    (r'ANTHROPOGENIC|MAN-MADE|FILL|MINE TAILINGS', 'X'),
    (r'VOLCANIC', 'V'),
    (r'UNDIFFERENTIATED|UNDIVIDED', 'Q'),
]
WORD = {'GLACIER': 'I', 'ICE': 'I', 'SNOW': 'I', 'WATER': 'H', 'LAKE': 'H', 'UNMAPPED': 'DROP', 'NOT MAPPED': 'DROP'}


def classify_text(levels, entry):
    """levels: LEVEL_1..LEVEL_6 strings; entry: description. -> (hclass, note) or (None, note)."""
    def first(text):
        """genesis term mentioned FIRST in the text (A2046a 'FLUVIAL DEPOSITS ... organic'
        was O when the term list was checked in fixed order); ties keep list order"""
        hits = []
        for i, (pat, h) in enumerate(GEN):
            m = re.search(pat, text.upper())
            if m:
                hits.append((m.start(), i, h))
        return min(hits)[2] if hits else None
    for lv in reversed([x for x in levels if x]):
        h = first(lv)
        if h:
            return h, f'legend level "{lv[:60]}"'
    h = first(entry)
    if h:
        return h, f'legend text "{entry[:70]}"'
    return None, 'no genesis term in legend'


def attrs(entry):
    t = entry.lower()
    tex = 'unknown'
    if 'diamicton' in t:
        tex = 'diamicton'
    elif re.search(r'\bpeat\b|muck', t):
        tex = 'organic'
    else:
        clause = re.split(r'[;.]', t.split(':', 1)[-1])[0]          # material list after 'NAME:'
        pats = (('gravel', r'gravel|cobble|pebble'), ('bouldery', r'boulder'), ('sand', r'\bsand'), ('fines', r'\bsilt|\bclay|\bmud'))
        g = {k for k, pat in pats if re.search(pat, clause)}
        if len(g) == 1:
            tex = g.pop()
        elif len(g) > 1:
            tex = 'mixed'
    cover = 'veneer' if 'veneer' in t else ('blanket' if 'blanket' in t else 'unknown')
    ice = 'yes' if re.search(r'ice-rich|massive (ground )?ice|excess ice|segregated ice', t) else 'unknown'
    return tex, cover, ice


def read_legend(sheet_dir):
    """CODE -> dict(hclass, texture, cover, ice_rich, desc, note) for polygon units."""
    fs = glob.glob(f'{sheet_dir}/**/*_leg.dbf', recursive=True)
    if not fs:
        return {}
    d = pyogrio.read_dataframe(fs[0], read_geometry=False)
    up = {c.upper(): c for c in d.columns}
    lvl = [up[c] for c in (f'LEVEL_{i}' for i in range(1, 7)) if c in up]
    ent = sorted((c for c in d.columns if c.upper().startswith('ENTRY_')), key=lambda c: int(c.split('_')[1]))
    out = {}
    for _, r in d.iterrows():
        code = str(r[up['CODE']]).strip()
        levels = [str(r[c]).strip() for c in lvl if r[c] is not None and str(r[c]).strip() not in ('', 'nan', 'None')]
        if not levels:
            continue          # line / point symbols (ESKER, STRIAE ...) have no hierarchy
        entry = ' '.join(str(r[c]) for c in ent if r[c] is not None and str(r[c]) not in ('nan', 'None'))
        entry = re.sub(r'\s+', ' ', entry).strip()
        h, note = classify_text(levels, entry)
        tex, cover, ice = attrs(entry)
        out[code] = dict(hclass=h or 'Q', texture=tex, cover=cover, ice_rich=ice,
                         desc=(' > '.join(levels) + ' | ' + entry)[:400],
                         note=note if h else 'UNCLASSIFIED: ' + note)
    return out


def word_class(code):
    c = str(code).strip().upper()
    return WORD.get(c)
