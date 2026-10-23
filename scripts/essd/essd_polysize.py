#!/usr/bin/env python
"""Polygon size distribution of merge 41 with and without the sliver fills (gapfill == 'sliver_nearest').
Attribute columns only; writes work/essd_tables/polygon_size_nosliver.csv."""
import glob
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

D = os.environ.get('ESSD_TILES', '/albedo/work/user/hlantuit/arctic_surficial/work/a0_tiles_m41')
O = os.environ.get('ESSD_OUT', '/albedo/work/user/hlantuit/arctic_surficial/work/essd_tables')
t = pa.concat_tables([pq.read_table(f, columns=['src_id', 'hclass', 'gapfill', 'area_km2'])
                      for f in sorted(glob.glob(f'{D}/*.parquet'))]).to_pandas(strings_to_categorical=True)
A = t['area_km2'].to_numpy()
sl = (t['gapfill'] == 'sliver_nearest').to_numpy()
pre = t['src_id'].astype(str).str.split('_').str[0].to_numpy()


def wq(a, q=0.5):
    o = np.sort(a)
    c = np.cumsum(o)
    return float(o[min(np.searchsorted(c, q * c[-1]), len(o) - 1)])


rows = []
for lab, m in [('all', np.ones(len(t), bool)), ('slivers only (gapfill=sliver_nearest)', sl),
               ('excl. slivers', ~sl), ('excl. slivers and hclass U', ~sl & (t['hclass'] != 'U').to_numpy())] + \
        [(f'excl. slivers, prefix {p}', ~sl & (pre == p)) for p in ['ru', 'ca', 'gl', 'us', 'no', 'se', 'is', 'fi', 'sj', 'fo', 'none']]:
    a = A[m]
    if not len(a):
        continue
    rows.append(dict(subset=lab, n=int(len(a)), area_km2=float(a.sum()), p10=float(np.quantile(a, .1)),
                     median=float(np.median(a)), p90=float(np.quantile(a, .9)), mean=float(a.mean()),
                     area_weighted_median=wq(a), n_lt_1ha=int((a < 0.01).sum())))
r = pd.DataFrame(rows)
r.to_csv(f'{O}/polygon_size_nosliver.csv', index=False)
pd.set_option('display.width', 250)
print(r.to_string())
# slivers by source
s = t[sl].groupby('src_id', observed=True)['area_km2'].agg(['size', 'sum'])
s['share_of_src_polys_pct'] = 100 * s['size'] / t.groupby('src_id', observed=True).size().reindex(s.index)
s = s.sort_values('size', ascending=False)
s.to_csv(f'{O}/sliver_by_source.csv')
print(s.head(20).round(2).to_string())
