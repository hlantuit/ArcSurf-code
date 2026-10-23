#!/usr/bin/env python
"""Legend screens of the Russian sheets (local files):
  S8 borrowed   the legend's notes name another sheet (a legend transcribed from, or mixed up with, a different sheet;
                also catches seam remarks, so every hit is read)
  S9 fit        on a raster sheet, half or more of the legend units (pre-Quaternary, water and technogenic excluded)
                receive no pixels: the legend may not belong to the map face
usage: qa_legend_screen.py LEGENDS_DIR GEOREF_DIR OUT_DIR"""
import glob
import json
import os
import re
import sys

import pandas as pd

LEG, GEO, OUT = sys.argv[1:4]
NOM = re.compile(r'\b([A-U])-\(?(\d{1,2})\)?(?:-([IVXL]+))?\b')


def own(sheet):
    m = NOM.search(sheet)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else None


rows = []
for f in sorted(glob.glob(f'{LEG}/legend_*.csv')):
    sh = os.path.basename(f)[7:-4]
    L = pd.read_csv(f, dtype=str).fillna('')
    notes = ' '.join(L['note']) if 'note' in L else ''
    o = own(sh)
    others = sorted({m.group(0) for m in NOM.finditer(notes)
                     if o and (m.group(1), int(m.group(2)), m.group(3)) != o
                     and not (m.group(3) is None and (m.group(1), int(m.group(2))) == o[:2])})
    rec = f'{GEO}/{sh}.json'
    fit = None
    if os.path.exists(rec):
        u = json.load(open(rec, encoding='utf-8')).get('units') or {}
        used = {str(v.get('index')) for v in u.values() if v.get('px', 0) > 0}
        idx = [i for i in L['index'] if i and not re.match(r'^(PREQ|WATER|t[A-Z]|tH)', i)]
        fit = 1 - sum(i in used for i in idx) / len(idx) if idx else None
    rows.append(dict(sheet=sh, n_units=len(L), other_sheets_in_notes=';'.join(others),
                     note_excerpt=notes[:220], unused_share=None if fit is None else round(fit, 2)))
R = pd.DataFrame(rows)
R['S8_borrowed'] = R['other_sheets_in_notes'] != ''
R['S9_fit'] = R['unused_share'].fillna(0) >= 0.5
R.to_csv(f'{OUT}/qa_legends.csv', index=False)
print(f'legends: {len(R)}; S8 notes naming another sheet: {R.S8_borrowed.sum()}; '
      f'S9 half or more legend units unused (raster sheets): {R.S9_fit.sum()}; both: {(R.S8_borrowed & R.S9_fit).sum()}')
print(R.loc[R.S8_borrowed | R.S9_fit, ['sheet', 'other_sheets_in_notes', 'unused_share', 'note_excerpt']]
      .sort_values('unused_share', ascending=False).to_string(index=False, max_colwidth=110))
