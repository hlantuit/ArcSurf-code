"""Reader for CGM sheets WITHOUT a GEO_POLYS layer in a Data/GDB geodatabase (70 of 240:
older SDM versions, shapefile-only packages, PMF/Apps geodatabases). ingest_canada.one_sheet
falls back to find_units() when no GEO_POLYS gdb exists.

Key: the GSC Surficial Data Model symbol id '3.01.XX.YYY' is present in almost every
schema (SYMBOL, SYMBOL1, SYMBOL1_DI, SYMBOL_DID, SurfCode, GSC_Surfic) and its XX group
is the genetic category across all versions -> xkey 'SYM:XX'. Where no symbol field
exists, the GSC terrain label (Tv, GFc, GLb ...) -> xkey 'LBL:<genetic caps>' (the same
keys as the oldest gdb schema, CGM295/297/298).
"""
import glob
import os
import re

import pandas as pd
import pyogrio

SYM_RE = re.compile(r'^3\.0?1\.(\d{2})\.')
# unit layer candidates, in preference order: (glob relative to the sheet dir, layer or None)
CANDIDATES = [
    ('**/Data/SHP/Surficial/GEO_POLYS.shp', None),
    ('**/Data/SHP/Surficial/GEO_POLYS_*.shp', None),
    ('**/GEO_POLYS.shp', None),
    ('**/*.gdb', 'GEO_POLYS_CGM*'),
    ('**/*.gdb', 'Geo_Ply'),
    ('**/Surficial/GeologyPolygons.shp', None),
    ('**/Surficial/GeoUnits*.shp', None),
    ('**/Surficial/geo*_poly.shp', None),
    ('**/Geology/geo*_poly.shp', None),            # CGM40/41/43 (Manitoba 1:50k, 2012): Data/Shape/Geology
    ('**/Geology/GeoUnits*.shp', None),            # CGM42
    ('**/geology/geo*_ply.shp', None),          # legacy A-series / Open File vector packages
    ('**/*.gdb', 'unit_polys'),
    ('**/*.gdb', 'Surf_poly'),
    ('**/*.gdb', 'surficial_deposit'),
    ('**/*.gdb', 'surficial_unit'),
    ('**/*.gdb', 'IQA_surficial_deposits_CGC'),
]
SYM_FIELDS = ('SYMBOL', 'SYMBOL1', 'SYMBOL1_DI', 'SYMBOL_DID', 'SURFCODE', 'GSC_SURFIC', 'SYMBOL1_DID')
LBL_FIELDS = ('ULABEL1', 'ULABEL1_DI', 'ULABEL1_DID', 'CODE', 'ORI_CODE_P', 'LABEL1', 'TAG', 'UTYPE_DID', 'UNIT', 'LABEL')


def _layers(path):
    try:
        return [n for n, t in pyogrio.list_layers(path) if t and 'Polygon' in str(t)]
    except Exception:
        return []


def find_units(d):
    """(path, layer) of the unit polygons of a sheet dir, or (None, None)."""
    for pat, layer in CANDIDATES:
        hits = []
        for p in glob.glob(f'{d}/{pat}', recursive=True):
            low = p.lower()
            if any(k in low for k in ('carto', 'topo', 'base.gdb', 'anno')):
                continue
            if layer is None:
                if p.endswith('.shp'):
                    hits.append((p, None))
            else:
                for n in _layers(p):
                    if re.fullmatch(layer.replace('*', '.*'), n, flags=re.I):
                        hits.append((p, n))
        if hits:
            # most features wins (a sheet can ship an older copy, e.g. GEO_POLYS_Oct15)
            def nf(h):
                # annotation layers (label boxes stored as polygons) can carry unit-like
                # names (CGM65 'surficial_unit'): a TextString field disqualifies a layer
                try:
                    i = pyogrio.read_info(h[0], layer=h[1])
                except Exception:
                    return 0
                return 0 if 'TextString' in list(i['fields']) else i['features']
            best = max(hits, key=nf)
            if nf(best) > 0:
                return best
    return None, None


def _col(df, names):
    up = {c.upper(): c for c in df.columns}
    return next((up[n] for n in names if n in up), None)


def gen_caps(s):
    """'Tv' -> 'T', 'GFc' -> 'GF', 'GLb' -> 'GL', 'pO' -> 'O', 'R.Tv' -> 'R', 'nTm' -> 'T'."""
    m = re.match(r'^[a-z]*([A-Z]{1,2})', str(s).strip())
    if not m:
        return None
    g = m.group(1)
    # two caps are a genetic pair only for GF/GL/GM; 'Tb'/'TV' style second caps are modifiers
    return g if g in ('GF', 'GL', 'GM') else g[0]


def keys(df):
    """Series xkey, Series code (label), Series desc, and the field names used."""
    sym_c = _col(df, SYM_FIELDS)
    # some schemas put the symbol id in a differently named field: detect by value
    if sym_c is None:
        for c in df.columns:
            try:
                v = df[c].astype('string')
            except (UnicodeDecodeError, TypeError, ValueError):
                continue                      # binary / blob columns (CGM65)
            if v.str.match(SYM_RE.pattern, na=False).mean() > 0.5:
                sym_c = c
                break
    lbl_c = _col(df, LBL_FIELDS)
    numbered = False
    if lbl_c is not None and df[lbl_c].astype('string').str.match(r'^\d', na=False).mean() > 0.3 \
            and not df[lbl_c].astype('string').str.match(r'^\d+$', na=False).mean() > 0.9:
        # map-specific numbered legend units (1a, 4b, 7a): keep the field, flag it; the
        # meaning is in the sheet legend (geo<n>_leg.dbf / PDF), not in the symbol
        numbered = True
    elif lbl_c is not None and df[lbl_c].astype('string').str.match(r'^\d+$', na=False).mean() > 0.5:
        # a numeric 'label' (CGM136 CONTROL_SI/UTYPE_DID swap) is not a label
        alt = [c for c in df.columns if c != lbl_c and df[c].dtype == object or str(df[c].dtype).startswith(('str', 'string'))]
        # only label-like fields may stand in; GEO_TYPE ('GEO'/'CON') decoded as G in A1847a
        alt = [c for c in alt if c != lbl_c and re.search(r'LABEL|CODE|UNIT|SYM', c, re.I) and not re.search(r'TYPE|_ID$|LINK|PAT', c, re.I)
               and df[c].astype('string').str.match(r'^[a-z]*[A-Z]', na=False).mean() > 0.5]
        lbl_c = alt[0] if alt else None
    code = df[lbl_c].astype('string').str.strip() if lbl_c else pd.Series(pd.NA, index=df.index, dtype='string')
    key = pd.Series(pd.NA, index=df.index, dtype='string')
    if sym_c is not None:
        xx = df[sym_c].astype('string').str.extract(SYM_RE)[0]
        key = ('SYM:' + xx).astype('string')
    if lbl_c is not None:
        lk = code.map(gen_caps)
        key = key.fillna(('LBL:' + lk.astype('string')))
    ut = _col(df, ('UTYPE1', 'UTYPE'))
    desc = df[ut].astype('string') if ut is not None and not df[ut].astype('string').str.match(r'^\d+$', na=False).all() else code
    return key, code.fillna(''), desc.fillna(''), dict(symbol=sym_c, label=lbl_c, numbered=numbered)


if __name__ == '__main__':
    import collections
    import sys
    GSC = '/albedo/work/user/hlantuit/arctic_surficial/raw/canada/gsc'
    tally = collections.Counter()
    ex = {}
    for s in sys.argv[1].split(','):
        p, lyr = find_units(f'{GSC}/{s}')
        if p is None:
            print(s, 'NO UNIT LAYER')
            continue
        df = pyogrio.read_dataframe(p, layer=lyr, read_geometry=False)
        k, c, dsc, used = keys(df)
        vc = k.value_counts(dropna=False)
        for kk, n in vc.items():
            tally[kk] += n
            sub = dsc[k == kk] if pd.notna(kk) else dsc[k.isna()]
            ex.setdefault(kk, collections.Counter()).update(sub.head(200).tolist())
        print(s, p.split(s + '/')[-1], lyr or '', len(df), used, dict(list(vc.head(6).items())))
    print('== keys over all sheets')
    for kk, n in tally.most_common():
        print(f'  {str(kk):10s} {n:7d}  e.g. {[e for e, _ in ex[kk].most_common(4)]}')
