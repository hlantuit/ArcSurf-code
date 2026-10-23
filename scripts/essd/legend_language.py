#!/usr/bin/env python
"""Language of the unit descriptions (src_desc) of the Russian sheets in the release geometry: per sheet and by area,
Russian verbatim (Cyrillic) or an English summary (Latin), so the paper states what the data hold.
usage: legend_language.py DISSOLVE_DIR OUT.csv"""
import glob
import re
import sys

import pandas as pd

DD, OUT = sys.argv[1:3]
cols = ['src_id', 'src_sheet', 'src_code', 'src_desc', 'area_km2']
F = pd.concat([pd.read_parquet(f, columns=cols) for f in sorted(glob.glob(f'{DD}/final/*.parquet'))], ignore_index=True)
F = F[F['src_id'].astype(str).str.startswith('ru_')].copy()
d = F['src_desc'].astype('string').fillna('')
cyr = d.str.count('[А-Яа-яЁё]')
lat = d.str.count('[A-Za-z]')
F['lang'] = 'none'
F.loc[(cyr > 0) & (cyr >= 3 * lat), 'lang'] = 'ru'
F.loc[(lat > 0) & (lat >= 3 * cyr), 'lang'] = 'en'
F.loc[(cyr > 0) & (lat > 0) & (cyr < 3 * lat) & (lat < 3 * cyr), 'lang'] = 'mixed'
# per sheet: the language of most of its area
s = F.groupby(['src_id', 'src_sheet', 'lang'])['area_km2'].sum().reset_index()
top = s.sort_values('area_km2', ascending=False).drop_duplicates(['src_id', 'src_sheet'])
units = F.groupby(['src_id', 'src_sheet'])['src_code'].nunique().rename('n_units').reset_index()
top = top.merge(units, on=['src_id', 'src_sheet'])
area_sheet = F.groupby(['src_id', 'src_sheet'])['area_km2'].sum().rename('sheet_km2').reset_index()
top = top.drop(columns='area_km2').merge(area_sheet, on=['src_id', 'src_sheet'])
top.to_csv(OUT, index=False)
print('by polygon area (km2):')
print(F.groupby(['src_id', 'lang'])['area_km2'].sum().round(0).to_string())
print('\nsheets by majority language:')
print(top.groupby(['src_id', 'lang']).agg(sheets=('src_sheet', 'size'), units=('n_units', 'sum'),
                                          km2=('sheet_km2', 'sum')).round(0).to_string())
