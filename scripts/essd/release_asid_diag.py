#!/usr/bin/env python
"""Diagnosis of the failed asid check of export_release.py (release45b): release polygons without pieces, piece asids
without a polygon, and pieces whose release target (by / sa / gap) differs from that of their polygon (a withheld
polygon with released pieces would put restricted content into the tiled layer).
usage: release_asid_diag.py DISSOLVE_DIR TILES_DIR"""
import glob
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from export_release import target  # noqa: E402

DD, TD = sys.argv[1:3]


def tile(args):
    tid, rows, asid = args
    f = f'{TD}/{tid}.parquet'
    cols = [c for c in ('redistribution', 'hclass', 'area_km2') if c in pq.read_schema(f).names]
    p = pd.read_parquet(f, columns=cols)
    t, _ = target(p)
    a = p['area_km2'].to_numpy(float) if 'area_km2' in p else np.full(len(p), np.nan)
    return asid, t[rows], a[rows]


def main():
    F = pd.concat([pd.read_parquet(f, columns=['asid', 'redistribution', 'hclass', 'src_id', 'area_km2'])
                   for f in sorted(glob.glob(f'{DD}/final/*.parquet'))], ignore_index=True)
    F['t'], _ = target(F)
    print(f'{len(F):,} polygons, {F["asid"].nunique():,} asids', flush=True)
    PA = pd.read_parquet(f'{DD}/piece_asid.parquet')
    print('piece_asid', list(PA.columns), f'{len(PA):,} rows', flush=True)
    jobs = [(tid, g['row'].to_numpy(), g['asid'].to_numpy()) for tid, g in PA.groupby('tile_id', sort=False)]
    with Pool(4) as pool:
        res = pool.map(tile, jobs, chunksize=16)
    T = pd.DataFrame({'asid': np.concatenate([r[0] for r in res]), 'pt': np.concatenate([r[1] for r in res]),
                      'parea': np.concatenate([r[2] for r in res])})
    T['polyt'] = F.set_index('asid')['t'].reindex(T['asid']).to_numpy()
    nop = F[~F['asid'].isin(T['asid'])]
    print(f'\nrelease polygons without pieces: {len(nop):,}')
    if len(nop):
        print(nop.groupby('t')['area_km2'].agg(['size', 'sum', 'max']).to_string())
        print('area quantiles (m2):', (nop['area_km2'] * 1e6).quantile([.5, .9, .99, 1]).round(3).to_dict())
        print('src_id:', nop['src_id'].value_counts().head(8).to_dict())
    print(f'\npieces whose asid has no polygon: {int(T["polyt"].isna().sum()):,}')
    mis = T[T['polyt'].notna() & (T['pt'] != T['polyt'])]
    print(f'pieces whose target differs from their polygon: {len(mis):,}')
    if len(mis):
        print(mis.groupby(['pt', 'polyt'])['parea'].agg(['size', 'sum']).to_string())
    for t in ('by', 'sa'):
        a, b = set(F.loc[F['t'] == t, 'asid']), set(T.loc[T['pt'] == t, 'asid'])
        print(f'{t}: release {len(a):,}, tiled {len(b):,}, release-only {len(a - b):,}, tiled-only {len(b - a):,}')


if __name__ == '__main__':
    main()
