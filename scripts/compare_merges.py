#!/usr/bin/env python
"""Area changes between the old and new versions of re-merged tiles (merge_subset.py): by source, by licence class
and by harmonised class, plus per-tile land-area agreement. Attributes only, no geometry.
usage: compare_merges.py <tag>   (reads work/<tag>_tiles.txt, work/old/tiles_<tag>/ and work/tiles/)"""
import sys

import pandas as pd

import surflib as S

tag = sys.argv[1]
tiles = [t for t in open(f'{S.WORK}/{tag}_tiles.txt').read().split() if t]
cols = ['src_id', 'redistribution', 'hclass', 'area_km2']
old = pd.concat([pd.read_parquet(f'{S.WORK}/old/tiles_{tag}/{t}.parquet', columns=cols).assign(tile=t)
                 for t in tiles], ignore_index=True)
new = pd.concat([pd.read_parquet(f'{S.WORK}/tiles/{t}.parquet', columns=cols).assign(tile=t) for t in tiles],
                ignore_index=True)
pd.set_option('display.width', 200)
for k in ('src_id', 'redistribution', 'hclass'):
    d = pd.DataFrame({'old_km2': old.groupby(k)['area_km2'].sum(), 'new_km2': new.groupby(k)['area_km2'].sum()})
    d = d.fillna(0.0)
    d['change_km2'] = d['new_km2'] - d['old_km2']
    d = d[d['change_km2'].abs() > 0.5].sort_values('change_km2')
    print(f'== by {k} (changes > 0.5 km2)')
    print(d.round(1).to_string())
t = pd.DataFrame({'old': old.groupby('tile')['area_km2'].sum(), 'new': new.groupby('tile')['area_km2'].sum()})
t['diff_pct'] = 100 * (t['new'] - t['old']) / t['old']
print(f'== {len(tiles)} tiles: total {t["old"].sum():,.1f} -> {t["new"].sum():,.1f} km2; '
      f'largest per-tile change {t["diff_pct"].abs().max():.4f} %')
