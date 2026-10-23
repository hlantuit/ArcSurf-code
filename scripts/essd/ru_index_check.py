#!/usr/bin/env python
"""Check of the Russian legend transcription: the genetic prefix of a VSEGEI unit index (a alluvial, g glacial,
f fluvioglacial, lg glaciolacustrine, m marine, l lacustrine, b bog, d deluvial, e eluvial, v eolian, ...) against the
harmonised class given to the unit, by area of the release geometry. Glacier-override (I) and unmapped (U) polygons,
and indices without a genetic prefix (pre-Quaternary, undivided), are not scored.
usage: ru_index_check.py DISSOLVE_DIR OUT.csv"""
import glob
import re
import sys

import pandas as pd

DD, OUT = sys.argv[1:3]
# genetic prefix -> classes it allows (hclass or hclass2). Order matters: longer prefixes first.
ALLOW = [
    ('lg', {'GL'}), ('gl', {'GL'}), ('fg', {'GF'}), ('gf', {'GF', 'T'}), ('gm', {'GM', 'M'}), ('mg', {'GM', 'M'}),
    ('lb', {'K', 'L', 'O'}), ('bl', {'K', 'L', 'O'}), ('la', {'L', 'F', 'K'}), ('al', {'F', 'L', 'K'}),
    ('am', {'F', 'M'}), ('ma', {'M', 'F'}), ('ml', {'M', 'L'}), ('lm', {'L', 'M'}),
    ('ed', {'W', 'C'}), ('de', {'C', 'W'}), ('dp', {'C', 'F'}), ('pd', {'C', 'F'}), ('ds', {'C'}), ('sd', {'C'}),
    ('cd', {'C'}), ('dc', {'C'}), ('pl', {'O'}), ('ap', {'F', 'C'}), ('pa', {'F', 'C'}),
    ('a', {'F'}), ('f', {'GF'}), ('g', {'T'}), ('m', {'M', 'GM'}), ('l', {'L', 'K'}), ('b', {'O'}), ('h', {'O'}),
    ('d', {'C'}), ('c', {'C'}), ('s', {'C'}), ('e', {'W'}), ('v', {'E'}), ('p', {'F', 'C'}), ('t', {'X'}),
]
PRE = re.compile(r'^(?:s:)?([a-z]{1,3})(?=[IVXH\d(Ɛ-]|$)')


def allowed(code):
    m = PRE.match(code or '')
    if not m:
        return None, None
    p = m.group(1)
    for k, s in ALLOW:
        if p == k:
            return k, s
    for k, s in ALLOW:                      # a longer prefix that starts with a known one, e.g. 'aml'
        if p.startswith(k):
            return k, s
    return p, None


cols = ['src_id', 'src_sheet', 'src_code', 'src_desc', 'hclass', 'hclass2', 'area_km2']
F = pd.concat([pd.read_parquet(f, columns=cols) for f in sorted(glob.glob(f'{DD}/final/*.parquet'))], ignore_index=True)
F = F[F['src_id'].astype(str).isin(['ru_vsegei_pdf', 'ru_vsegei_preview', 'ru_vsegei200'])]
F = F[~F['hclass'].astype(str).isin(['I', 'U', 'H'])].copy()
u = F.groupby(['src_id', 'src_sheet', 'src_code', 'hclass', 'hclass2'], dropna=False).agg(
    area_km2=('area_km2', 'sum'), src_desc=('src_desc', 'first')).reset_index()
res = [allowed(str(c)) for c in u['src_code']]
u['prefix'] = [r[0] for r in res]
u['allowed'] = [','.join(sorted(r[1])) if r[1] else '' for r in res]
scored = u['allowed'] != ''
u['agree'] = [bool(a) and (h in a.split(',') or (isinstance(h2, str) and h2 in a.split(',')))
              for a, h, h2 in zip(u['allowed'], u['hclass'].astype(str), u['hclass2'])]
tot = u['area_km2'].sum()
sc = u.loc[scored, 'area_km2'].sum()
ag = u.loc[scored & u['agree'], 'area_km2'].sum()
print(f'Russian VSEGEI units (no ice, water, unmapped): {len(u):,} unit-class rows, {tot:,.0f} km2')
print(f'scored (genetic prefix recognised): {scored.sum():,} rows, {sc:,.0f} km2 ({100 * sc / tot:.1f} %)')
print(f'prefix agrees with hclass or hclass2: {100 * ag / sc:.1f} % of the scored area '
      f'({(scored & u["agree"]).sum():,} of {scored.sum():,} rows)')
d = u[scored & ~u['agree']].sort_values('area_km2', ascending=False)
print('\nlargest disagreements by area:')
for r in d.head(40).itertuples():
    print(f'  {r.src_sheet:22s} {str(r.src_code):14s} prefix {r.prefix:3s} -> {r.hclass:3s}/{str(r.hclass2):4s} '
          f'{r.area_km2:9,.0f} km2  {str(r.src_desc)[:80]}')
print('\ndisagreeing area by (prefix, hclass):')
print(d.groupby(['prefix', 'hclass'])['area_km2'].sum().sort_values(ascending=False).head(20).round(0).to_string())
print('\nunscored area by prefix:')
print(u[~scored].groupby('prefix', dropna=False)['area_km2'].sum().sort_values(ascending=False).head(15).round(0).to_string())
u.to_csv(OUT, index=False)
