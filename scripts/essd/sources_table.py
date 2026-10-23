#!/usr/bin/env python
"""Every source sheet of the ArcSurf release geometry: dataset, sheet, nominal scale, publication year, licence,
redistribution, area and number of polygons, and the PANGAEA dataset its polygons are released in (CC BY, CC BY-SA
Greenland, or not released). The citations of the source datasets (Appendix Table A1) are joined later on src_id.
usage: sources_table.py DISSOLVE_DIR OUT.csv"""
import glob
import sys

import numpy as np
import pandas as pd

DD, OUT = sys.argv[1:3]
cols = ['src_id', 'src_sheet', 'scale_den', 'pub_year', 'licence', 'redistribution', 'hclass', 'area_km2']
F = pd.concat([pd.read_parquet(f, columns=cols) for f in sorted(glob.glob(f'{DD}/final/*.parquet'))], ignore_index=True)
for c in ('src_id', 'src_sheet', 'licence', 'redistribution', 'hclass'):
    F[c] = F[c].astype('string').fillna('')
F = F[F['src_id'] != '']
red = F['redistribution'].to_numpy(dtype=object)
F['released_in'] = np.where(red == 'open', 'ArcSurf geology (CC BY 4.0)',
                            np.where(red == 'open_sa', 'ArcSurf Greenland (CC BY-SA 4.0)', 'not released'))
g = F.groupby(['src_id', 'src_sheet'], dropna=False).agg(
    scale_den=('scale_den', 'max'), pub_year=('pub_year', 'max'), licence=('licence', 'first'),
    redistribution=('redistribution', 'first'), released_in=('released_in', 'first'),
    n_polygons=('area_km2', 'size'), area_km2=('area_km2', 'sum')).reset_index()
g['area_km2'] = g['area_km2'].round(3)
g = g.sort_values(['src_id', 'src_sheet'])
g.to_csv(OUT, index=False)
print(f'{len(g):,} sheets of {g["src_id"].nunique()} datasets; area {g["area_km2"].sum():,.0f} km2')
print(g.groupby('released_in')['area_km2'].sum().round(0).to_string())
