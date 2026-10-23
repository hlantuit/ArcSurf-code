#!/usr/bin/env python
"""Follow-up checks for the ESSD statistics (merge 41): hclass H (water) units, SIM 3340 QCLASS 90,
empty-string vs null encodings, rule-classified units. Attribute columns only."""
import glob
import os
import sys
import time

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.compute as pc  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
D = os.environ.get('ESSD_TILES', f'{ROOT}/work/a0_tiles_m41')
O = os.environ.get('ESSD_OUT', f'{ROOT}/work/essd_tables')
t0 = time.time()
pd.set_option('display.width', 250)
pd.set_option('display.max_colwidth', 110)


def log(*a):
    print(f'[{time.time() - t0:7.1f}s]', *a, flush=True)


files = sorted(glob.glob(f'{D}/*.parquet'))
H, S90, RC, small = [], [], [], []
for i, f in enumerate(files):
    t = pq.read_table(f, columns=['src_id', 'src_sheet', 'src_code', 'src_desc', 'hclass', 'hclass2', 'conf_tier',
                                  'xwalk_note', 'area_km2', 'tile_id'])
    h = t.filter(pc.equal(t['hclass'], 'H'))
    if h.num_rows:
        H.append(h.select(['src_id', 'src_code', 'src_desc', 'xwalk_note', 'area_km2']))
    s = t.filter(pc.and_(pc.equal(t['src_id'], 'us_usgs_sim3340'), pc.equal(t['src_code'], '90')))
    if s.num_rows:
        S90.append(s.select(['src_id', 'src_code', 'hclass', 'tile_id', 'area_km2']))
    xn = pc.fill_null(pc.match_substring(t['xwalk_note'], 'rule-classified'), False)
    r = t.filter(xn)
    if r.num_rows:
        RC.append(r.select(['src_id', 'src_code', 'src_desc', 'hclass', 'xwalk_note', 'area_km2']))
    # encodings: '' vs null for conf_tier / hclass2 / src_sheet
    small.append(pa.table({
        'src_id': t['src_id'],
        'conf_tier_enc': pc.if_else(pc.is_null(t['conf_tier']), 'null',
                                    pc.if_else(pc.equal(t['conf_tier'], ''), 'empty', 'value')),
        'hclass2_enc': pc.if_else(pc.is_null(t['hclass2']), 'null',
                                  pc.if_else(pc.equal(t['hclass2'], ''), 'empty', 'value')),
        'sheet_enc': pc.if_else(pc.is_null(t['src_sheet']), 'null',
                                pc.if_else(pc.equal(t['src_sheet'], ''), 'empty', 'value')),
        'area_km2': t['area_km2']}))
    if i % 500 == 0:
        log('read', i)

h = pa.concat_tables(H).to_pandas()
g = h.groupby(['src_id', 'src_code', 'src_desc', 'xwalk_note'], dropna=False)['area_km2'].agg(['sum', 'size']).reset_index()
g = g.sort_values('sum', ascending=False)
g.to_csv(f'{O}/fu_hclass_H_units.csv', index=False)
log('hclass H by src_id (km2):\n' + h.groupby('src_id')['area_km2'].sum().sort_values(ascending=False).round(0).to_string())
log('top 40 H units:\n' + g.head(40).round(1).to_string())
sus = g[~g['xwalk_note'].fillna('').str.contains('water|lake|river|lagoon|vatn|vesi|vatten|vann|hydro|LAKE|RIVER|WATER|Lake',
                                                  case=False, regex=True)
        | g['src_desc'].fillna('').str.contains('DRIFT|drift|deposit|till', regex=True)]
log('H units whose note/desc do not look like water or that mention drift/deposit/till:\n' + sus.head(40).round(1).to_string())
log('H km2 with "rule-classified from name; water body" note:',
    round(float(g.loc[g['xwalk_note'].fillna('').str.contains('rule-classified from name; water body'), 'sum'].sum()), 1))

s = pa.concat_tables(S90).to_pandas() if S90 else pd.DataFrame()
if len(s):
    log('SIM3340 QCLASS 90: n', len(s), 'km2', round(s['area_km2'].sum(), 1), 'by hclass',
        s.groupby('hclass')['area_km2'].sum().round(1).to_dict(), 'tiles', s['tile_id'].nunique())
    s.groupby('tile_id')['area_km2'].sum().round(1).to_csv(f'{O}/fu_sim3340_qclass90_by_tile.csv')

r = pa.concat_tables(RC).to_pandas()
rg = r.groupby(['src_id', 'hclass'])['area_km2'].agg(['sum', 'size']).reset_index()
log('rule-classified units by src x hclass:\n' + rg.round(1).to_string())
r.groupby(['src_id', 'src_code', 'src_desc', 'hclass', 'xwalk_note'])['area_km2'].sum().reset_index() \
    .sort_values('area_km2', ascending=False).to_csv(f'{O}/fu_rule_classified_units.csv', index=False)

e = pa.concat_tables(small).to_pandas()
for c in ['conf_tier_enc', 'hclass2_enc', 'sheet_enc']:
    x = e.pivot_table(index='src_id', columns=c, values='area_km2', aggfunc='sum', observed=True).fillna(0)
    x.round(1).to_csv(f'{O}/fu_{c}.csv')
    log(c + ' (km2):\n' + x.round(0).to_string())
log('done')
