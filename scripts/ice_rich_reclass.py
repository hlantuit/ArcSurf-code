#!/usr/bin/env python
"""LEGEND.md rule for `ice_rich`: 'yes' only where the SOURCE maps ground ice, never inferred. Several Russian
legend CSVs set ice_rich=yes from the unit TYPE (transcription rule "'ds' = C (fines, ice_rich yes)"): solifluction
'ds', 's', 'cs' units etc. This script clears those inferred flags.

Rows of sources/legend_*.csv with ice_rich == 'yes' are kept when the map's own wording (description_ru /
description; our notes do not count) mentions ground ice or the unit is an ice complex:
  ice / icy / ice-rich / ice wedge(s) / yedoma; льд- (льды, льдистые, ледяные), ледов-, клинья льда, ПЖЛ,
  повторно-жильн-, едом-, шлиры, линзы льда
or hclass is Y. All other 'yes' become '' (unknown) with a note appended. --dry-run changes nothing.
Writes work/ice_rich_reclass_log.csv on Albedo (./ice_rich_reclass_log.csv elsewhere).
usage: ice_rich_reclass.py <sources_dir> [--dry-run]"""
import glob
import os
import re
import sys

import pandas as pd

# the nominative 'лед/лёд' as a WORD (2026-10-06: S-47-V,VI 'лед с примесью алеврита ... (до 40 м)' was cleared without it);
# the lookarounds keep 'ледник-' (glacier, glacial) out
ICE = re.compile('|'.join([r'\bice\b', r'\bicy\b', r'ice-rich', r'ice[ -]?wedge', r'yedoma', r'льд', r'ледов', r'ледян',
                           r'(?<![а-яё])л[её]д(?![а-яё])', r'клинья льда', r'пжл', r'повторно-жильн', r'едом', r'шлир',
                           r'линз[а-я]* льда']), re.I)
NOTE = '2026-10-06: ice_rich cleared (inferred from the unit type; the legend states no ground ice)'
src = sys.argv[1]
dry = '--dry-run' in sys.argv
log = []
for f in sorted(glob.glob(os.path.join(src, 'legend_*.csv'))):
    try:
        d = pd.read_csv(f, dtype=str, keep_default_na=False)
    except Exception:
        continue
    if not {'index', 'ice_rich'} <= set(d.columns):
        continue
    ch = False
    for i, r in d[d['ice_rich'].str.lower() == 'yes'].iterrows():
        txt = ' '.join(str(r.get(c, '')) for c in ('description_ru', 'description'))
        keep = bool(ICE.search(txt)) or r.get('hclass', '') == 'Y'
        log.append(dict(file=os.path.basename(f), index=r['index'], hclass=r.get('hclass', ''), keep=keep, desc=txt[:120]))
        if not keep:
            d.at[i, 'ice_rich'] = ''
            if 'note' in d.columns:
                d.at[i, 'note'] = (d.at[i, 'note'] + '; ' if d.at[i, 'note'] else '') + NOTE
            ch = True
    if ch and not dry:
        d.to_csv(f, index=False)
L = pd.DataFrame(log)
out = ('/albedo/work/user/hlantuit/arctic_surficial/work/ice_rich_reclass_log.csv' if sys.platform.startswith('linux')
       else 'ice_rich_reclass_log.csv')
L.to_csv(out, index=False)
if len(L):
    print('rows with ice_rich=yes:', len(L), '| kept:', int(L.keep.sum()), '| cleared:', int((~L.keep).sum()),
          '| files changed:', L[~L.keep].file.nunique())
print('dry run' if dry else 'written', '| log', out)
