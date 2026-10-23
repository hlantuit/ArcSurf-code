#!/usr/bin/env python
"""What the two NL GeoAtlas surficial layers contain inside the ArcSurf domain, for the GSNL permission request:
layer 11 (Detailed Surficial Geology) by NTS sheet and Geofile, layer 12 (Regional Surficial Geology) by SOURCE and
REFERENCE. Areas are raw layer areas in EPSG:6931 for the features that touch the domain (before the merge).
usage: sbatch -J labinfo -c 4 --mem=48G -t 1:00:00 run_py.sh lab_layers_info.py"""
import pandas as pd
import pyogrio

import surflib as S

RAWC = f'{S.RAW}/canada'
pd.set_option('display.width', 250)
pd.set_option('display.max_rows', 400)
pd.set_option('display.max_colwidth', 120)

for layer, cols in ((11, ['NTS_map', 'Geofile', 'DateUpd']), (12, ['SOURCE', 'REFERENCE'])):
    g = pyogrio.read_dataframe(f'{RAWC}/labrador_layer{layer}.geojson', columns=cols)
    n_all = len(g)
    g = S.in_amap(g.to_crs(S.CRS))
    g['km2'] = g.geometry.area / 1e6
    print(f'== layer {layer}: {len(g)} of {n_all} features touch the domain, {g.km2.sum():,.0f} km2', flush=True)
    for c in cols:
        g[c] = g[c].astype(str).str.strip()
    if layer == 11:
        t = g.groupby(['NTS_map', 'Geofile'], dropna=False).agg(n=('km2', 'size'), km2=('km2', 'sum'),
                                                                   upd_min=('DateUpd', 'min'),
                                                                   upd_max=('DateUpd', 'max')).reset_index()
        print(t.sort_values('NTS_map').to_string(index=False))
        print('distinct NTS sheets', g.NTS_map.nunique(), 'distinct Geofiles', g.Geofile.nunique())
    else:
        t = g.groupby(['SOURCE', 'REFERENCE'], dropna=False).agg(n=('km2', 'size'), km2=('km2', 'sum')).reset_index()
        print(t.sort_values('km2', ascending=False).to_string(index=False))
print('DONE')
