"""Write CA_MISSING.md from sources/ca_missing_nts.csv (ca_missing_nts.py output + group/block columns) and
sources/gap_vs_pending.csv (gap_vs_pending.py). The paragraph on what the latest merge changed is read from a
small text file, so the numbers and tables are never edited by hand.
Groups: A = no catalogued GSC product <= 1:1M, inside the catalogue selection (centroid > 60 N, or 51-60 N east
of 102 W); C = same but outside it (never searched); B = catalogued, not processed; E = processed, not covering.
usage: ca_missing_md.py <merge no> <changes.txt> [out=CA_MISSING.md]"""
import datetime
import re
import sys

import pandas as pd

run, notes = sys.argv[1], open(sys.argv[2], encoding='utf-8').read().strip()
out = sys.argv[3] if len(sys.argv) > 3 else 'CA_MISSING.md'
d = pd.read_csv('sources/ca_missing_nts.csv', keep_default_na=False)
d['coarse_km2'] = d['coarse_km2'].astype(float)
d['land_km2'] = d['land_km2'].astype(float)
pv = pd.read_csv('sources/gap_vs_pending.csv', keep_default_na=False)
NONSURF = re.compile(r'well log|permafrost thickness|gas hydrat|ground ?water|aquifer|geographical bulletin|marine|shelf|'
                     r'sea ?bed|seafloor|offshore|bathymet|settlements', re.I)
pv = pv[~pv['title'].str.contains(NONSURF)]
# census rows that are not separate products
NOTPRODUCT = {'223362': 'OF 5116 atlas surficial theme record (no files of its own; its layers are merged)'}
pv = pv[~pv['geoscan'].astype(str).isin(NOTPRODUCT)]


def k10(v):
    return f'{int(round(float(v) / 10.0) * 10):,}'


G = {'A': 'A. No catalogued GSC surficial product at 1:1M or finer: deep-search list',
     'C': 'C. Outside the GSC catalogue selection (BC, Alberta Rockies): never searched',
     'B': 'B. Catalogued but not yet processed: our backlog (mostly line/label maps)',
     'E': 'E. Processed products that do not cover the sheet (partial maps, unmapped parts, QC fail)'}
INTRO = {
    'A': 'What to look for: GSC maps missing from the footprint index (A-series, Open Files, Bulletins, Memoirs with '
         'map sheets), NWT Geological Survey and Canada-Nunavut Geoscience Office surficial maps, Polar Continental '
         'Shelf / university theses, and 1970s Mackenzie Valley and Arctic Islands pipeline terrain studies '
         '(1:125k-1:250k). Most sheets north of 76 N are the Queen Elizabeth Islands (Ellesmere, Axel Heiberg, '
         'Ringnes, Devon, Bathurst), where 1:2.5M+ is often all there is. `best` = finest other class present on '
         'part of the sheet.',
    'C': 'The catalogue only took footprints with a centroid north of 60 N, or at 51-60 N east of 102 W. These sheets '
         'are inside the permafrost domain (Obu 2019 mountain permafrost) but were never searched. Likely sources: BC '
         'terrain inventory mapping (TEIS; `ca_bc_ter` covers only the mapped parts), Alberta Geological Survey '
         '(`ca_ab_ags`), and GSC Cordilleran surficial maps.',
    'B': 'Products exist in our catalogue but are not processed yet. Most are black-and-white line or label maps (line '
         'pipeline; each polygon label must be read).',
    'E': ''}
L = []
date = datetime.date.today().isoformat()
L.append('# Canada: NTS 1:250k map areas covered only at >= 1:2.5M\n')
L.append(f'*{date}, merged layer after merge {run}. Scripts `scripts/ca_missing_nts.py` and `scripts/ca_missing_md.py`; '
         f'full table `sources/ca_missing_nts.csv`.*\n')
L.append(f'A sheet is listed when **>= 300 km2** of its land inside the build domain has no source finer than the GSC '
         f'1:5M "Surficial materials of Canada" (`ca_gsc_5m`). That gives {len(d)} sheets and '
         f'{d.coarse_km2.sum() / 1e6:.2f} M km2. Large lakes are holes in the 1:5M map, so they count as unmapped and are '
         f'**not** included. Each sheet is matched by bounding box against our GSC surficial catalogue '
         f'(`sources/canada_gsc_sheets.json`, 650 GSC maps from the footprint index and OSTR), counting products at 1:1M '
         f'or finer that overlap more than 5% of the sheet. NTS codes follow the NTS grid rules (checked on 085J '
         f'Yellowknife, 107C Tuktoyaktuk, 107B Aklavik); north of 80 N (marked `~`) they are approximate.\n')
L.append('| group | sheets | km2 at >= 1:2.5M |\n|---|---|---|')
for g in 'ACBE':
    s = d[d.group == g]
    L.append(f'| {G[g]} | {len(s)} | {k10(s.coarse_km2.sum())} |')
L.append('')
L.append(notes + '\n')
L.append('\n## Already-downloaded maps that land on group A / C sheets (OSTR census cross-check)\n')
L.append('Group A was matched only against the GSC footprint index. Our OSTR census (`out/web/pending.json`) also holds '
         'maps that index lacks: Memoirs and Papers with map sheets, some A-series maps, and British Columbia maps. '
         'These are downloaded but not yet processed. Non-surficial items with huge footprints (well-log permafrost '
         'maps, groundwater notes, aquifers, the 1964 Geographical Bulletin, marine and shelf maps) are filtered out. '
         '`scripts/gap_vs_pending.py`, full table `sources/gap_vs_pending.csv`. Also dropped: '
         + '; '.join(f'{k} = {v}' for k, v in NOTPRODUCT.items()) + '.\n')
grp = pv.groupby(['nts', 'group'], sort=False)
rows = []
for (nts, g), s in grp:
    km2 = float(s['coarse_km2'].iloc[0])
    items = '<br>'.join(f"{r.geoscan}: {r.title[:70]} (1:{int(float(r.scale)) // 1000}k, {r.year}, {r.note}, "
                        f"{float(r.share):.0%} of sheet)" for r in s.itertuples())
    rows.append((km2, f'| {nts} | {g} | {k10(km2)} | {items} |'))
na, nc = pv[pv.group == 'A'].nts.nunique(), pv[pv.group == 'C'].nts.nunique()
L.append(f'{na + nc} sheets ({na} in group A, {nc} in group C) have at least one such map:\n')
L.append('| NTS | group | km² at >= 1:2.5M | downloaded, unprocessed map(s) |\n|---|---|---|---|')
L += [r for _, r in sorted(rows, key=lambda x: -x[0])]
for g in 'ACBE':
    s = d[d.group == g].sort_values('coarse_km2', ascending=False)
    L.append(f'\n## {G[g]}\n')
    if INTRO[g]:
        L.append(INTRO[g] + '\n')
    if g in 'AC':
        L.append('| NTS | box | km2 >= 1:2.5M | land km2 | best |\n|---|---|---|---|---|')
        L += [f'| {r.nts} | {r.bbox} | {k10(r.coarse_km2)} | {k10(r.land_km2)} | {r.best_other} |' for r in s.itertuples()]
    else:
        col = 'catalogued, unprocessed' if g == 'B' else 'catalogue'
        L.append(f'| NTS | box | km2 >= 1:2.5M | {col} |\n|---|---|---|---|')
        L += [f'| {r.nts} | {r.bbox} | {k10(r.coarse_km2)} | {r.gsc_catalogue} |' for r in s.itertuples()]
open(out, 'w', encoding='utf-8', newline='\n').write('\n'.join(L) + '\n')
print(out, len(d), 'sheets', round(d.coarse_km2.sum()), 'km2')
