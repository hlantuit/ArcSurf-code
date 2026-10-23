#!/usr/bin/env python
"""Screening of the Russian sheets for extraction and crosswalk errors (runs on local files; no map geometry needed).

Unit screens (every unit of every VSEGEI sheet, with its area in the release, from ru_index_check_<tag>.csv):
  S1 index      the genetic part of the Russian index (a alluvial, g glacial, ...; compound indices such as 'e,d' or
                'd,aIII-H' component by component; PREQ and pre-Quaternary age codes = bedrock) against hclass/hclass2
  S2 wording    genetic words of the unit description (Russian or English) against hclass/hclass2
  S3 sameness   the same index coded with different classes on different sheets (minority codings, by area)
Sheet screens (raster sheets: georef records jpgvec/<sheet>.json and legends/legend_<sheet>.csv):
  S4 dominance  one legend colour holds >= 60 % of a 1:200,000 sheet (>= 75 % of a 1:1,000,000 sheet)
  S5 confusion  the dominant colour lies within dE 15 (CIE76) of another colour of the same legend
  S6 missing    the legend has slope or residual units (e, d, c, s) but they hold < 2 % of a 1:200,000 sheet
  S7 region     the dominant class of a 1:200,000 sheet holds < 10 % of the 1:1,000,000 sheet(s) around it
usage: qa_screen.py INDEX_CHECK.csv GEOREF_DIR LEGENDS_DIR OUT_DIR"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

IDX, GEO, LEG, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)

# --- S1: genetic part of the index -> classes it allows ------------------------------------------------------------
ALLOW = [
    ('lg', {'GL'}), ('gl', {'GL'}), ('fg', {'GF'}), ('gf', {'GF', 'T'}), ('gm', {'GM', 'M'}), ('mg', {'GM', 'M'}),
    ('lb', {'K', 'L', 'O'}), ('bl', {'K', 'L', 'O'}), ('la', {'L', 'F', 'K'}), ('al', {'F', 'L', 'K'}),
    ('am', {'F', 'M'}), ('ma', {'M', 'F'}), ('ml', {'M', 'L'}), ('lm', {'L', 'M'}),
    ('ed', {'W', 'C'}), ('de', {'C', 'W'}), ('dp', {'C', 'F'}), ('pd', {'C', 'F'}), ('ds', {'C'}), ('sd', {'C'}),
    ('cd', {'C'}), ('dc', {'C'}), ('pl', {'O'}), ('ap', {'F', 'C'}), ('pa', {'F', 'C'}),
    ('a', {'F'}), ('f', {'GF'}), ('g', {'T'}), ('m', {'M', 'GM'}), ('l', {'L', 'K'}), ('b', {'O'}), ('h', {'O'}),
    ('d', {'C'}), ('c', {'C'}), ('s', {'C'}), ('e', {'W'}), ('v', {'E'}), ('p', {'F', 'C'}), ('t', {'X'}),
]
# Yedoma / ice complex and thermokarst are coded from the unit's own words, whatever its index (rule of Sect. 4)
EXTRA = {'Y', 'K', 'E'}          # E: loessoid / subaerial cover units may carry any index (rule of Sect. 4)
PRE = re.compile(r'^(?:s:)?([a-z]{1,3})(?=[IVXHEQNP\d(Ɛ-]|$)')
# pre-Quaternary ages (Archean ... Cretaceous); Q, H (Holocene), E (Eopleistocene), N and P (Neogene / Paleogene,
# often combined with Q) are left unscored
PREQ = re.compile(r'^(AR|PR|PZ|MZ|Ɛ|Є|O|S|D|T|J|K)(?:\d|[_ -]|$)')


def comp_allowed(c):
    m = PRE.match(c)
    if not m:
        return None
    p = m.group(1)
    for k, s in ALLOW:
        if p == k:
            return s
    for k, s in ALLOW:
        if p.startswith(k):
            return s
    return None


def allowed(code):
    code = str(code).strip()
    if code.upper() == 'PREQ' or (PREQ.match(code) and 'Q' not in code):
        return {'R'}
    sets = [comp_allowed(c.strip()) for c in re.split(r'[,+;/]', code) if c.strip()]
    sets = [s for s in sets if s]
    return set().union(*sets) if sets else None


# --- S2: genetic words of the description -> classes ----------------------------------------------------------------
WORDS = [
    (r'ледниково-морск|glaciomarine|glacio-marine', {'GM', 'M'}),
    (r'озерно-ледник|лимногляц|glaciolacustrine|limnoglacial', {'GL'}),
    (r'водно-ледник|флювиогляц|fluvioglacial|glaciofluvial|outwash', {'GF'}),
    (r'морен|ледников|\btill\b|moraine|glacial', {'T', 'GF', 'GL', 'GM'}),
    (r'аллюв|alluvi|fluvial|floodplain|terrace', {'F', 'L', 'K'}),
    (r'озерн|lacustrine|lake', {'L', 'K', 'GL', 'F'}),
    (r'морск|marine|littoral|beach', {'M', 'GM', 'F'}),
    (r'болот|торф|peat|bog|palustrine|mire', {'O', 'K', 'L'}),
    (r'элюв|eluvi', {'W', 'C'}),
    (r'делюв|коллюв|солифлюк|осып|deluvi|colluvi|solifluct|scree|talus', {'C', 'W'}),
    (r'эолов|лёсс|лесс|eolian|aeolian|loess|dune', {'E'}),
    (r'пролюв|proluvi', {'F', 'C'}),
    (r'ледов[а-я]* комплекс|едом|ice complex|yedoma', {'Y'}),
    (r'термокарст|алас|thermokarst|alas', {'K', 'L', 'O'}),
    (r'дочетвертич|pre-quaternary|bedrock|коренн', {'R'}),
]


def word_classes(desc):
    d = str(desc).lower()
    hits = [s for pat, s in WORDS if re.search(pat, d)]
    return set().union(*hits) if hits else None


# --- unit screens ------------------------------------------------------------------------------------------------
U = pd.read_csv(IDX)
U = U[~U['hclass'].astype(str).isin(['I', 'U', 'H'])].copy()
U['cls'] = [{h} | ({h2} if isinstance(h2, str) and h2 else set()) for h, h2 in zip(U['hclass'], U['hclass2'])]
a1 = [allowed(c) for c in U['src_code']]
U['s1_scored'] = [a is not None for a in a1]
U['s1_ok'] = [a is None or bool(c & (a | EXTRA)) for a, c in zip(a1, U['cls'])]
U['s1_allowed'] = [','.join(sorted(a)) if a else '' for a in a1]
a2 = [word_classes(d) for d in U['src_desc']]
U['s2_scored'] = [a is not None for a in a2]
U['s2_ok'] = [a is None or bool(c & a) for a, c in zip(a2, U['cls'])]
U['s2_allowed'] = [','.join(sorted(a)) if a else '' for a in a2]
key = U['src_code'].astype(str).str.replace(r'\s+', '', regex=True)
maj = U.assign(k=key).groupby(['k', 'hclass'])['area_km2'].sum().reset_index().sort_values('area_km2')
maj = maj.groupby('k').agg(maj_class=('hclass', 'last'), n_class=('hclass', 'nunique'))
nsh = U.assign(k=key).groupby('k')['src_sheet'].nunique()
U = U.assign(k=key).join(maj, on='k').join(nsh.rename('n_sheets'), on='k')
U['s3_flag'] = (U['n_sheets'] >= 3) & (U['n_class'] > 1) & (U['hclass'] != U['maj_class'])
U.to_csv(f'{OUT}/qa_units.csv', index=False)

tot = U['area_km2'].sum()


def share(m):
    return 100 * U.loc[m, 'area_km2'].sum() / tot


print(f'units: {len(U):,} rows, {tot:,.0f} km2')
print(f'S1 index: scored {share(U.s1_scored):.1f} % of the area; disagreeing {share(U.s1_scored & ~U.s1_ok):.2f} % '
      f'({(U.s1_scored & ~U.s1_ok).sum()} units)')
print(f'S2 wording: scored {share(U.s2_scored):.1f} %; disagreeing {share(U.s2_scored & ~U.s2_ok):.2f} % '
      f'({(U.s2_scored & ~U.s2_ok).sum()} units)')
print(f'S3 sameness: minority codings {share(U.s3_flag):.2f} % ({U.s3_flag.sum()} units)')

# --- sheet screens -----------------------------------------------------------------------------------------------


def lab(hexc):
    rgb = np.array([int(hexc[i:i + 2], 16) for i in (1, 3, 5)]) / 255.0
    rgb = np.where(rgb > 0.04045, ((rgb + 0.055) / 1.055) ** 2.4, rgb / 12.92)
    xyz = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]) @ rgb
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def is200(s):
    return bool(re.search(r'-[IVXL]+(?:[,_]|$)', s))


def parents(s):
    m = re.match(r'^([A-Z])-', s)
    return m.group(1) if m else None


comp = U.groupby(['src_sheet', 'hclass'])['area_km2'].sum().unstack(fill_value=0)
onem = [s for s in comp.index if not is200(s)]


def onem_cover(sheet):
    """1:1,000,000 sheets (by name) whose column range contains the 1:200,000 sheet's column"""
    m = re.match(r'^([A-Z])-(\d+)-', sheet)
    if not m:
        return []
    row, col = m.group(1), int(m.group(2))
    out = []
    for s in onem:
        n = re.match(r'^([A-Z])-\(?(\d+)\)?(?:[-,]\(?(\d+)\)?)?(?:[-,]\(?(\d+)\)?)?', s)
        if n and n.group(1) == row:
            cols = [int(x) for x in n.groups()[1:] if x]
            if min(cols) <= col <= max(cols):
                out.append(s)
    return out


rows = []
for f in sorted(glob.glob(f'{GEO}/*.json')):
    d = json.load(open(f, encoding='utf-8'))
    sh = d.get('sheet') or os.path.basename(f)[:-5]
    units = d.get('units') or {}
    px = {c: u.get('px', 0) for c, u in units.items()}
    tot_px = sum(px.values()) or 1
    if not px:
        continue
    dom_c = max(px, key=px.get)
    dom_share = px[dom_c] / tot_px
    lf = f'{LEG}/legend_{sh}.csv'
    leg = pd.read_csv(lf) if os.path.exists(lf) else pd.DataFrame(columns=['fill', 'index', 'hclass'])
    fills = [c for c in leg.get('fill', pd.Series(dtype=str)).dropna().astype(str) if re.match(r'^#[0-9a-fA-F]{6}$', c)]
    others = [c for c in fills if c.lower() != dom_c.lower()]
    de = min((float(np.linalg.norm(lab(dom_c) - lab(c))) for c in others), default=np.nan)
    near = min(others, key=lambda c: np.linalg.norm(lab(dom_c) - lab(c))) if others else ''
    near_idx = leg.loc[leg['fill'].astype(str).str.lower() == near.lower(), 'index'].astype(str).head(1).tolist()
    slope_idx = [i for i in leg.get('index', pd.Series(dtype=str)).astype(str) if re.match(r'^(e|d|c|s|ed|de|cd|dc|ds|sd)(?:[,;]|$|[IVXH])', i)]
    slope_px = sum(px[c] for c, u in units.items() if re.match(r'^(e|d|c|s|ed|de|cd|dc|ds|sd)(?:[,;]|$|[IVXH])', str(u.get('index', ''))))
    dom_idx = units[dom_c].get('index', '')
    dom_cls = leg.loc[leg['index'].astype(str) == str(dom_idx), 'hclass'].astype(str).head(1).tolist()
    dom_cls = dom_cls[0] if dom_cls else ''
    reg = onem_cover(sh) if is200(sh) else []
    if reg:
        c = comp.loc[[r for r in reg if r in comp.index]].sum()
        reg_share = float(c.get(dom_cls, 0) / c.sum()) if c.sum() else np.nan
    else:
        reg_share = np.nan
    s200 = is200(sh)
    rows.append(dict(sheet=sh, scale='200k' if s200 else '1M', source=d.get('source', ''), rms_m=d.get('rms_m'),
                     cover_frac=d.get('cover_frac'), unassigned=d.get('unassigned_before_fill'),
                     dom_index=dom_idx, dom_class=dom_cls, dom_colour=dom_c, dom_share=round(dom_share, 3),
                     nearest_index=near_idx[0] if near_idx else '', nearest_colour=near, dE_nearest=round(de, 1),
                     n_slope_units=len(slope_idx), slope_share=round(slope_px / tot_px, 3),
                     onem_sheets=';'.join(reg), dom_class_share_1M=round(reg_share, 3) if pd.notna(reg_share) else np.nan))
S = pd.DataFrame(rows)
S['S4_dominance'] = np.where(S['scale'] == '200k', S['dom_share'] >= 0.60, S['dom_share'] >= 0.75)
S['S5_confusion'] = S['S4_dominance'] & (S['dE_nearest'] < 15)
S['S6_missing'] = (S['scale'] == '200k') & (S['n_slope_units'] >= 2) & (S['slope_share'] < 0.02)
S['S7_region'] = (S['scale'] == '200k') & (S['dom_class_share_1M'] < 0.10)
fl = ['S4_dominance', 'S5_confusion', 'S6_missing', 'S7_region']
S['n_flags'] = S[fl].sum(axis=1)
S = S.sort_values(['n_flags', 'dom_share'], ascending=False)
S.to_csv(f'{OUT}/qa_sheets.csv', index=False)
print(f'\nraster sheets screened: {len(S)} ({(S.scale == "200k").sum()} at 1:200,000)')
for c in fl:
    print(f'  {c}: {int(S[c].sum())}')
print(f'  two or more flags: {(S.n_flags >= 2).sum()}')
cols = ['sheet', 'scale', 'dom_index', 'dom_class', 'dom_share', 'nearest_index', 'dE_nearest', 'slope_share',
        'dom_class_share_1M', 'n_flags']
print(S.loc[S.n_flags >= 2, cols].to_string(index=False))
