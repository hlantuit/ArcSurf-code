#!/usr/bin/env python
"""
Per source: apply the crosswalk to work/std/<src>.gpkg and write work/xw/<src>.gpkg
with the harmonised columns, plus a footprint layer carrying the precedence keys
(scale_den, pub_year, tier_rank) per sheet.

usage: build_xw.py <src_id> [<src_id> ...]
"""
import json
import os
import sys

import pandas as pd
import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

XW = f'{S.WORK}/xw'
TIER_RANK = {'surficial': 0, 'reconnaissance': 1, 'predictive': 2}
KEEP = ['src_id', 'src_sheet', 'src_code', 'src_desc', 'hclass', 'hclass2', 'texture',
        'cover', 'ice_rich', 'scale_den', 'pub_year', 'survey_years', 'conf_tier',
        'licence', 'redistribution', 'xwalk_note', 'src_extra']


def tier_rank(s):
    s = (s or '').strip().lower()
    for k, v in TIER_RANK.items():
        if s.startswith(k):
            return v
    return 1   # unstated tier ranks with Reconnaissance: neither best nor worst


def build(src):
    u = gpd.read_file(f'{S.STD}/{src}.gpkg', layer='units')
    fp = gpd.read_file(f'{S.STD}/{src}.gpkg', layer='footprint')
    m, nd, ad = S.apply_xwalk(u, src)
    for c in KEEP:
        if c not in m:
            m[c] = None
    m = m[KEEP + ['geometry']]
    m['src_sheet'] = m['src_sheet'].fillna('')
    if 'src_sheet' not in fp or fp['src_sheet'].isna().all():
        fp['src_sheet'] = ''
    fp['src_sheet'] = fp['src_sheet'].fillna('')
    # precedence keys per sheet, from that sheet's own units
    per = (m.assign(tr=m['conf_tier'].map(tier_rank))
           .groupby('src_sheet')
           .agg(scale_den=('scale_den', 'max'), pub_year=('pub_year', 'max'),
                tier_rank=('tr', 'min'), conf_tier=('conf_tier', 'first')))
    if (fp['src_sheet'] == '').all():
        fp['scale_den'] = per['scale_den'].max()
        fp['pub_year'] = per['pub_year'].max()
        fp['tier_rank'] = per['tier_rank'].min()
        fp['conf_tier'] = per['conf_tier'].dropna().iloc[0] if per['conf_tier'].notna().any() else None
    else:
        fp = fp.drop(columns=[c for c in per.columns if c in fp]).merge(
            per, left_on='src_sheet', right_index=True, how='left')
        orphan = fp['scale_den'].isna()
        # a sheet whose every unit the crosswalk DROPS (CGM320/321: one water polygon inside
        # the domain; BC TER 'N' projects) keeps no claim: drop its footprint, log it
        if orphan.any():
            print(f'{src}: dropped {int(orphan.sum())} footprints with no units after the crosswalk:',
                  fp.loc[orphan, 'src_sheet'].tolist(), flush=True)
            fp = fp[~orphan]
    fp['src_id'] = src
    # overlay = a partial layer whose footprint is just its own polygons (e.g. tidal
    # flats, S100 moraines): no sliver halo, so the merge uses d = 0 for it
    fp['overlay'] = fp['overlay'].fillna(0).astype(int) if 'overlay' in fp else 0
    fp = fp[['src_id', 'src_sheet', 'scale_den', 'pub_year', 'tier_rank', 'conf_tier',
             'overlay', 'geometry']]
    os.makedirs(XW, exist_ok=True)
    p = f'{XW}/{src}.gpkg'
    if os.path.exists(p):
        os.remove(p)
    m.to_file(p, layer='units', driver='GPKG')
    fp.to_file(p, layer='footprint', driver='GPKG')
    info = dict(src_id=src, n_units=len(m), n_dropped=nd, km2_dropped=ad,
                n_footprints=len(fp), scale_den=sorted(fp['scale_den'].dropna().unique().tolist()))
    with open(f'{XW}/{src}.json', 'w') as f:
        json.dump(info, f, default=str)
    print(info)


if __name__ == '__main__':
    # one source without a crosswalk entry must not stop the rest (2026-10-01: Labrador
    # 'L11:Municipality' aborted the domain build and left 13 sources stale)
    bad = []
    for s in sys.argv[1:]:
        try:
            build(s)
        except Exception as e:
            print('XW FAILED', s, str(e)[:300], flush=True)
            bad.append(s)
    print('XW FAILED SOURCES', bad)
