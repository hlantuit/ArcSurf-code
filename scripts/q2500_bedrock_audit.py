#!/usr/bin/env python
"""Which 1:2.5M (Q2500) fill colours are really pre-Quaternary bedrock?

The Q2500 extraction (q2500_extract.py) names each fill colour by a vote of the unit labels printed on
it. Bedrock outcrops carry no label in the PDF's text layer, so their violet tints took the labels of
neighbouring marine / glaciomarine units ('m,gmIII', 'gmII'): batch reports 2026-10-06 (M-(44),45 and
N-46,(47) previews) found those tints on mountain ridges that the 1:200k sheets map as PREQ.

Independent test: rasterise (1 km, EASE-Grid 2.0 N) the Q2500 fill colour and, from the finer Russian
sources (work/xw/ru_vsegei_pdf + ru_vsegei_preview + ru_vsegei200, i.e. 1:1M and 1:200k sheets,
registered independently), whether the ground is mapped R (bedrock / pre-Quaternary) or anything else.
Per Q2500 (index, fill): km2 compared and the share mapped R, plus the leading other class.
Null space: a fill can be R-dominated only where the finer maps exist (mostly south of 70 N and the
mountain belts); a fill never compared stays as extracted.

Writes work/q2500/bedrock_audit.csv. usage: q2500_bedrock_audit.py [--cell 1000]"""
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
from rasterio.features import rasterize
from rasterio.transform import from_origin

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

CELL = float(sys.argv[sys.argv.index('--cell') + 1]) if '--cell' in sys.argv else 1000.0
q = gpd.read_file(f'{S.WORK}/q2500/q2500.gpkg', layer='units')
q = q[q['index'] != 'WATER']
x0, y0, x1, y1 = q.total_bounds
W, H = int(np.ceil((x1 - x0) / CELL)), int(np.ceil((y1 - y0) / CELL))
tf = from_origin(x0, y1, CELL, CELL)
keys = (q['index'] + '|' + q['fill']).values
uk = pd.Index(sorted(set(keys)))
qid = rasterize(zip(q.geometry.values, uk.get_indexer(keys) + 1), out_shape=(H, W), transform=tf, fill=0, dtype='int32')
print('q2500 raster', qid.shape, len(uk), 'index|fill keys', flush=True)
HC = ['R', 'T', 'GF', 'GL', 'GM', 'M', 'F', 'L', 'K', 'Y', 'E', 'C', 'W', 'O', 'V', 'X', 'I', 'Q', 'H', 'U']
code = {h: i + 1 for i, h in enumerate(HC)}
fine = np.zeros((H, W), 'uint8')
for src in ('ru_vsegei_preview', 'ru_vsegei_pdf', 'ru_vsegei200'):          # later sources overwrite: pdf/200 win over previews
    u = pyogrio.read_dataframe(f'{S.WORK}/xw/{src}.gpkg', layer='units', columns=['hclass'], bbox=(x0, y0, x1, y1))
    u = u[u['hclass'].isin(HC)]
    r = rasterize(zip(u.geometry.values, u['hclass'].map(code).values), out_shape=(H, W), transform=tf, fill=0, dtype='uint8')
    fine[r > 0] = r[r > 0]
    print(src, len(u), 'units rasterised', flush=True)
m = (qid > 0) & (fine > 0) & (fine != code['H'])
df = pd.DataFrame({'k': qid[m], 'h': fine[m]})
ct = df.groupby(['k', 'h']).size().unstack(fill_value=0)
km2c = CELL * CELL / 1e6
tot_q = pd.Series(np.bincount(qid.ravel(), minlength=len(uk) + 1)[1:] * km2c, index=range(1, len(uk) + 1))
rows = []
for k in ct.index:
    c = ct.loc[k]
    n = c.sum()
    other = c.drop(labels=[code['R']], errors='ignore')
    top = HC[int(other.idxmax()) - 1] if other.sum() else ''
    idx, fill = uk[k - 1].split('|', 1)
    rows.append(dict(index=idx, fill=fill, q2500_km2=round(tot_q[k]), compared_km2=round(n * km2c),
                     share_R=round(float(c.get(code['R'], 0)) / n, 3), top_other=top,
                     share_top_other=round(float(other.max()) / n, 3) if other.sum() else 0.0))
out = pd.DataFrame(rows).sort_values('compared_km2', ascending=False)
out.to_csv(f'{S.WORK}/q2500/bedrock_audit.csv', index=False)
# full class mix per key (shares of the compared area), for the decision table
mix = (ct.div(ct.sum(axis=1), axis=0).round(3)).rename(columns=lambda h: HC[int(h) - 1])
mix.index = [uk[k - 1] for k in mix.index]
mix.insert(0, 'compared_km2', (ct.sum(axis=1).values * km2c).round())
mix.to_csv(f'{S.WORK}/q2500/bedrock_audit_mix.csv')
sel = mix[mix.index.str.contains('gm')].sort_values('compared_km2', ascending=False)
print(sel.loc[:, (sel.max() >= 0.05) | (sel.columns == 'compared_km2')].to_string())
pd.set_option('display.width', 200)
print(out[(out.compared_km2 >= 500) & (out.share_R >= 0.3)].to_string(index=False))
print('\nall gm / m keys:')
print(out[out['index'].str.contains(r'gm|^m', regex=True)].head(30).to_string(index=False))
