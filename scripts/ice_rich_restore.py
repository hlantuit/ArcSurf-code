#!/usr/bin/env python
"""Undo ice_rich clearings that ice_rich_reclass.py made by mistake: rows it cleared carry its NOTE; when the map's own
wording (description_ru / description) matches the CURRENT ice_rich_reclass.ICE pattern, ice_rich goes back to 'yes'
and the NOTE is removed. 2026-10-06: the first pattern lacked the nominative 'лед/лёд' (S-47-V,VI gIIImr 'лед с
примесью алеврита, щебня и дресвы (до 40 м)').
usage: ice_rich_restore.py <sources_dir> [--dry-run]"""
import glob
import os
import re
import sys

import pandas as pd

ICE = re.compile('|'.join([r'\bice\b', r'\bicy\b', r'ice-rich', r'ice[ -]?wedge', r'yedoma', r'льд', r'ледов', r'ледян',
                           r'(?<![а-яё])л[её]д(?![а-яё])', r'клинья льда', r'пжл', r'повторно-жильн', r'едом', r'шлир',
                           r'линз[а-я]* льда']), re.I)          # = ice_rich_reclass.ICE
NOTE = '2026-10-06: ice_rich cleared (inferred from the unit type; the legend states no ground ice)'
src = sys.argv[1]
dry = '--dry-run' in sys.argv
n = 0
for f in sorted(glob.glob(os.path.join(src, 'legend_*.csv'))):
    try:
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
    except Exception:
        continue
    if not {'index', 'ice_rich', 'note'} <= set(d.columns):
        continue
    hit = d['note'].str.contains(NOTE, regex=False) & (d['ice_rich'] == '')
    ch = False
    for i in d.index[hit]:
        txt = ' '.join(str(d.at[i, c]) for c in ('description_ru', 'description') if c in d.columns)
        m = ICE.search(txt)
        if m:
            print(os.path.basename(f), d.at[i, 'index'], '| restored on', repr(m.group(0)), '|', txt[max(0, m.start() - 40):m.end() + 30])
            d.at[i, 'ice_rich'] = 'yes'
            d.at[i, 'note'] = re.sub(r'(; )?' + re.escape(NOTE), '', d.at[i, 'note'])
            ch, n = True, n + 1
    if ch and not dry:
        d.to_csv(f, index=False)
print(n, 'rows restored', '(dry run)' if dry else '')
