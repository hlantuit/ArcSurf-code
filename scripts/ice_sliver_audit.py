#!/usr/bin/env python
"""Post-merge check of the glacier override: ice_apply.sliver_check on every merged tile that has ice (what apply_ice
must leave at zero), plus ice area by source and the ice_note counts. Writes work/ice_sliver_audit.csv and prints a
summary. usage: ice_sliver_audit.py [TILES_DIR] [--workers N]"""
import glob
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import pyogrio  # noqa: E402
import surflib as S  # noqa: E402
import ice_apply as IA  # noqa: E402

TG = None


def _init(tg):
    global TG
    TG = tg


def one(f):
    tid = os.path.basename(f)[:-8]
    a = pq.read_table(f, columns=['hclass', 'ice_src', 'ice_note', 'area_km2']).to_pandas()
    row = dict(tile_id=tid, ice_km2=float(a.loc[a['hclass'] == 'I', 'area_km2'].sum()),
               note_outside_km2=float(a.loc[a['ice_note'] == 'source_ice_outside_outline', 'area_km2'].sum()),
               note_failed=int((a['ice_note'] == 'ice_override_failed').sum()))
    for src, v in a[a['hclass'] == 'I'].groupby(a['ice_src'].astype(str).str[:6])['area_km2'].sum().items():
        row[f'ice_{src}'] = float(v)
    if row['ice_km2'] == 0:
        return row
    t = gpd.read_parquet(f)
    try:
        r = IA.sliver_check(t, TG[tid])
        row.update(sl_n=r['n'], sl_km2=r['km2'], sl_app_km2=r['app_km2'])
    except Exception as e:                      # report, do not stop the audit
        row.update(sl_error=str(e)[:200])
    return row


def main():
    a = sys.argv[1:]
    tiles_dir = a[0] if a and not a[0].startswith('--') else f'{S.WORK}/tiles'
    workers = int(a[a.index('--workers') + 1]) if '--workers' in a else 32
    tl = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer='tiles')
    key = 'tile_id' if 'tile_id' in tl else tl.columns[0]
    tg = dict(zip(tl[key].astype(str), tl.geometry.values))
    files = sorted(glob.glob(f'{tiles_dir}/*.parquet'))
    with Pool(workers, initializer=_init, initargs=(tg,)) as p:
        rows = p.map(one, files, chunksize=4)
    d = pd.DataFrame(rows).fillna(0)
    d.to_csv(f'{S.WORK}/ice_sliver_audit.csv', index=False)
    ice = d[d['ice_km2'] > 0]
    print('tiles', len(d), 'with ice', len(ice), 'ice km2', round(ice['ice_km2'].sum(), 1))
    for c in [c for c in d.columns if c.startswith('ice_') and c != 'ice_km2']:
        print(' ', c, round(d[c].sum(), 1))
    print('source ice outside outline km2', round(d['note_outside_km2'].sum(), 1), '| override failed polygons',
          int(d['note_failed'].sum()))
    if 'sl_n' in d:
        print('residual slivers: tiles with n>0', int((d['sl_n'] > 0).sum()), '| n', int(d['sl_n'].sum()), '| km2',
              round(d['sl_km2'].sum(), 4), '| appendage km2', round(d['sl_app_km2'].sum(), 4))
        print(d.sort_values('sl_app_km2', ascending=False).head(8)[['tile_id', 'ice_km2', 'sl_n', 'sl_km2', 'sl_app_km2']]
              .to_string(index=False))
    if 'sl_error' in d:
        print('errors', int((d['sl_error'] != 0).sum()))


if __name__ == '__main__':
    main()
