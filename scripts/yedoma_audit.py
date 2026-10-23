#!/usr/bin/env python
"""Audit the hclass Y (ice complex / yedoma) coding of the Russian sources against the
Database of Ice-Rich Yedoma Permafrost v2 (IRYP v2; Strauss et al. 2021/2022, PANGAEA
doi:10.1594/PANGAEA.940078; layer IRYP_v2_yedoma_confidence: confirmed / likely / uncertain,
mapped north of 60 N only).

Per source (crosswalked layers work/xw/<src>.gpkg): km2 of hclass Y split by
  kind  = 'L-loessoid' (src_code starts with L, description without yedoma / ice-complex words)
          or 'explicit' (description names yedoma / ice complex / едома / ледов)
  zone  = IRYP confirmed+likely / IRYP uncertain / outside IRYP polygons
and, the other way round, how much IRYP confirmed+likely area each source maps as some
class other than Y (what a yedoma column would add).
Null space: IRYP has no polygons south of 60 N, so 'outside IRYP' there means 'not
assessed by IRYP', not 'no yedoma'.

usage: yedoma_audit.py [src ...]"""
import re
import sys

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

IRYP = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/russia/iryp/IRYP_v2_yedoma_confidence.shp'
EXPL = re.compile(r'yedoma|ice[ -]complex|едом|ледов|ледяно', re.I)
srcs = sys.argv[1:] or ['ru_vsegei_pdf', 'ru_vsegei200', 'ru_vsegei_q2500', 'ru_bryant_vsegei1m', 'ru_vsegei_preview']
ir = gpd.read_file(IRYP).to_crs(S.CRS)
ir['conf'] = ir['confidence'].astype(str)
yes = shapely.union_all(shapely.make_valid(ir[ir.conf.isin(['confirmed', 'likely'])].geometry.values))
unc = shapely.difference(shapely.union_all(shapely.make_valid(ir[ir.conf == 'uncertain'].geometry.values)), yes)
print('IRYP confirmed+likely km2', round(yes.area / 1e6), ' uncertain km2', round(unc.area / 1e6), flush=True)
rows = []
for src in srcs:
    u = pyogrio.read_dataframe(f'{S.WORK}/xw/{src}.gpkg', layer='units', columns=['src_sheet', 'src_code', 'src_desc', 'hclass'])
    u['geometry'] = shapely.make_valid(u.geometry.values)
    y = u[u.hclass == 'Y'].copy()
    y['kind'] = ['explicit' if EXPL.search(str(d) or '') else ('L-loessoid' if str(c).startswith('L') else 'other-Y')
                 for c, d in zip(y.src_code, y.src_desc)]
    for kind, g in y.groupby('kind'):
        geom = shapely.union_all(g.geometry.values)
        a_yes = shapely.intersection(geom, yes).area / 1e6
        a_unc = shapely.intersection(geom, unc).area / 1e6
        rows.append(dict(src=src, what=f'Y {kind}', km2=round(geom.area / 1e6), in_iryp=round(a_yes), in_uncertain=round(a_unc),
                         outside=round(geom.area / 1e6 - a_yes - a_unc)))
    # IRYP yes area that this source maps as something else (by class)
    near = u[u.intersects(shapely.envelope(yes))]
    oth = near[near.hclass != 'Y']
    inter = gpd.GeoDataFrame(dict(hclass=oth.hclass.values), geometry=shapely.intersection(oth.geometry.values, yes), crs=S.CRS)
    inter['km2'] = inter.area / 1e6
    top = inter.groupby('hclass').km2.sum().sort_values(ascending=False).round().head(8).to_dict()
    rows.append(dict(src=src, what='IRYP yes mapped as non-Y', km2=round(inter.km2.sum()), in_iryp=None, in_uncertain=None,
                     outside=None, by_class=top))
    print(src, 'done', flush=True)
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 120)
print(pd.DataFrame(rows).to_string(index=False))
