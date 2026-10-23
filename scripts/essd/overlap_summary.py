#!/usr/bin/env python
"""Summarise work/essd_tables/geo_overlap_tiles.jsonl -> overlap_by_source.csv, overlap_by_sheet.csv,
overlap_inter_source_tiles.csv (all in work/essd_tables)."""
import collections
import json
import re

import pandas as pd

O = '/albedo/work/user/hlantuit/arctic_surficial/work/essd_tables'
ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
S = collections.defaultdict(collections.Counter)
SH = collections.Counter()
SHN = collections.Counter()
T = collections.Counter()
inter = []
err = []
n = 0
done = set()
for ln in open(f'{O}/geo_overlap_tiles.jsonl'):
    r = json.loads(ln)
    if 'error' in r:
        err.append((r['tile_id'], r['error'][-300:]))
        continue
    n += 1
    done.add(r['tile_id'])
    T['land_km2'] += r['land_km2']
    T['sum_km2'] += r['sum_km2']
    T['union_km2'] += r['union_km2']
    T['excess_vs_land_km2'] += r['excess_vs_land_km2']
    T['excess_vs_union_km2'] += r['excess_vs_union_km2']
    T['inter_source_overlap_km2'] += r['inter_source_overlap_km2']
    T['invalid_geoms'] += r['invalid']
    if r['inter_source_overlap_km2'] > 1:
        inter.append(dict(tile_id=r['tile_id'], inter_km2=r['inter_source_overlap_km2'],
                          srcs=', '.join(s['src_id'] for s in r['sources'])))
    for s in r['sources']:
        c = S[s['src_id']]
        for k in ('sum_km2', 'union_km2', 'self_overlap_km2', 'within_group_overlap_km2', 'cross_group_overlap_km2',
                  'cross_sheet_overlap_km2'):
            c[k] += s[k]
        c['tiles'] += 1
        for sh in s['sheets']:
            SH[(s['src_id'], sh['sheet'])] += sh['self_overlap_km2']
            SHN[(s['src_id'], sh['sheet'])] += 1
# tiles NOT analysed (log diff <= 0.01 %) and their residual excess
L = []
for ln in open(f'{ROOT}/work/merge_tiles.log'):
    m = re.match(r'(\S+) ok n=(\d+) land=([\d.]+) out=([\d.]+) diff=([-+\d.]+)%', ln.strip())
    if m:
        L.append((m.group(1), float(m.group(3)), float(m.group(4))))
rest = sum(o - l for t, l, o in L if t not in done)
print('tiles analysed', n, 'errors', len(err), {k: round(v, 1) for k, v in T.items()})
print('excess in tiles not analysed (log):', round(rest, 1), 'km2; total log excess', round(sum(o - l for t, l, o in L), 1))
for e in err[:5]:
    print('ERR', e)
src = pd.DataFrame([dict(src_id=k, **v) for k, v in S.items()]).sort_values('self_overlap_km2', ascending=False)
src.to_csv(f'{O}/overlap_by_source.csv', index=False)
pd.set_option('display.width', 250)
print(src[src['self_overlap_km2'].abs() > 0.05].round(1).to_string(index=False))
sh = pd.DataFrame([dict(src_id=k[0], sheet=k[1], self_overlap_km2=v, tiles=SHN[k]) for k, v in SH.items()]) \
    .sort_values('self_overlap_km2', ascending=False)
sh.to_csv(f'{O}/overlap_by_sheet.csv', index=False)
print('sheets with self-overlap > 1 km2:', int((sh['self_overlap_km2'] > 1).sum()))
print(sh.head(25).round(1).to_string(index=False))
it = pd.DataFrame(inter).sort_values('inter_km2', ascending=False) if inter else pd.DataFrame()
it.to_csv(f'{O}/overlap_inter_source_tiles.csv', index=False)
if len(it):
    print('tiles with inter-source overlap > 1 km2:', len(it), 'sum', round(it['inter_km2'].sum(), 1))
    print(it.head(15).round(1).to_string(index=False))
