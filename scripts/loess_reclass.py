#!/usr/bin/env python
"""Hugues 2026-10-04 (yedoma decision): hclass follows each map. Loess-like (loessoid) units are
Eolian (E) unless the map itself calls the unit yedoma / ice complex (then Y); whether the ground is
yedoma comes from the separate `yedoma` column (IRYP v2, merge_tiles.split_by_yedoma).

Rewrites the Russian legend CSVs (sources/legend_*.csv with columns index, hclass, description_ru):
rows with hclass Y are classed by the map's own description (not our notes) and index:
  explicit  description names yedoma / ice complex / (syngenetic) ice wedges / ice bodies
            (едом-, ледов-, клинья льда, ПЖЛ, повторно-жильные, 'льды')               -> stay Y
  loessoid  description says loess / loessoid / subaerial cover (лёссов-, покровн-),
            or the index starts with L                                                 -> E
            (hclass2 kept; texture 'fines' if empty; note appended)
  other     reported, not changed
Writes work/loess_reclass_log.csv on Albedo (./loess_reclass_log.csv elsewhere). --dry-run changes nothing.

usage: loess_reclass.py <sources_dir> [--dry-run]"""
import glob
import os
import re
import sys

import pandas as pd

EXPL = re.compile('|'.join([r'yedoma', r'ice[ -]?complex', r'ice[ -]?wedge', r'syngenetic ice', r'едом', r'ледов',
                            r'ледян', r'клинья льда', r'пжл', r'повторно-жильн', r'(?<![а-яё])льды(?![а-яё])']), re.I)
LOESS = re.compile(r'loess|лёсс|лесс|subaerial|покровн', re.I)
NOTE = '2026-10-04: Y->E (loessoid; hclass follows the map, yedoma flag = IRYP v2 column)'
src = sys.argv[1]
dry = '--dry-run' in sys.argv
log = []
for f in sorted(glob.glob(os.path.join(src, 'legend_*.csv'))):
    try:
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
    except Exception:
        continue
    if not {'index', 'hclass'} <= set(d.columns):
        continue
    ch = False
    for i, r in d[d['hclass'] == 'Y'].iterrows():
        # the MAP's own wording only (description columns), not our earlier interpretive notes
        txt = ' '.join(str(r.get(c, '')) for c in ('description_ru', 'description'))
        if EXPL.search(txt):
            kind = 'explicit'
        elif LOESS.search(txt) or str(r['index']).startswith('L'):
            kind = 'loessoid'
        else:
            kind = 'other'
        log.append(dict(file=os.path.basename(f), index=r['index'], kind=kind, hclass2=r.get('hclass2', ''),
                        desc=txt[:140]))
        if kind == 'loessoid':
            d.at[i, 'hclass'] = 'E'
            if 'texture' in d.columns and not d.at[i, 'texture']:
                d.at[i, 'texture'] = 'fines'
            if 'note' in d.columns:
                d.at[i, 'note'] = (d.at[i, 'note'] + '; ' if d.at[i, 'note'] else '') + NOTE
            ch = True
    if ch and not dry:
        d.to_csv(f, index=False)
L = pd.DataFrame(log)
out = ('/albedo/work/user/hlantuit/arctic_surficial/work/loess_reclass_log.csv' if sys.platform.startswith('linux')
       else 'loess_reclass_log.csv')
L.to_csv(out, index=False)
if len(L):
    print(L.groupby('kind').size().to_dict())
print('dry run' if dry else 'written', '| log', out)
