#!/usr/bin/env python
"""Table S1 of the Supplement: every source sheet of ArcSurf with its nominal scale, publication year, licence, area in
the map and reference (pangaea/sources.csv of the release, which PANGAEA also distributes). Years missing in the
release table are filled where the sheet name states them (e.g. 'YGS Open File 2018-20').
usage: table_s1.py SOURCES.csv OUT_BASENAME   -> OUT_BASENAME.xlsx (README + Table S1) and OUT_BASENAME.csv"""
import re
import sys

import pandas as pd

SRC, OUT = sys.argv[1:3]
s = pd.read_csv(SRC)
yr = s['src_sheet'].astype(str).str.extract(r'(?:Open File|OF)\s*((?:19|20)\d\d)')[0]
s['pub_year'] = s['pub_year'].fillna(pd.to_numeric(yr, errors='coerce'))
REL = {'by': 'yes (CC BY 4.0)', 'sa': 'yes (CC BY-SA 4.0)', 'not released': 'no'}
t = pd.DataFrame({
    'Source dataset': s['source_name'],
    'Source ID': s['src_id'],
    'Sheet': s['src_sheet'],
    'Nominal scale (1:)': s['scale_den'].round(0).astype('Int64'),
    'Publication year': s['pub_year'].round(0).astype('Int64'),
    'Licence of the source': s['licence'],
    'Released in the data set': s['released_in'].map(lambda v: REL.get(str(v), str(v))),
    'Polygons in ArcSurf': s['n_polygons'].astype('Int64'),
    'Area in ArcSurf (km²)': s['area_km2'].round(1),
    'Reference of the sheet': s['sheet_reference'].fillna('') if 'sheet_reference' in s else '',
    'Citation of the source dataset': s['citation'],
    'Reference of the source dataset': s['reference'],
}).sort_values(['Source ID', 'Sheet'])
t.to_csv(OUT + '.csv', index=False)
readme = pd.DataFrame({'Column': list(t.columns), 'Content': [
    'Name of the source dataset (Appendix A, Table A1)',
    'Identifier of the source dataset in ArcSurf (attribute src_id)',
    'Map sheet, tile or map of the source dataset (attribute src_sheet)',
    'Denominator of the nominal scale of the sheet',
    'Publication year of the sheet (attribute pub_year); empty where the source does not state it',
    'Licence or terms of use of the source',
    'Whether the polygons of the sheet are in the published data set, and under which licence',
    'Number of polygons of the sheet in the release geometry',
    'Land area that the sheet contributes to ArcSurf, equal-area projection',
    'Full reference of the individual sheet, where the sheet was published on its own',
    'In-text citation of the source dataset',
    'Full reference of the source dataset']})
with pd.ExcelWriter(OUT + '.xlsx', engine='openpyxl') as w:   # pandas 3 picks xlsxwriter, which has no book.properties
    pd.DataFrame({'Table S1': ['Source sheets of ArcSurf version 1.0: every map sheet, tile or map that contributes polygons '
                               'to the map, with its scale, publication year, licence and area.',
                               f'{len(t):,} sheets of {t["Source ID"].nunique()} source datasets.']}).to_excel(
        w, sheet_name='README', index=False)
    readme.to_excel(w, sheet_name='README', index=False, startrow=4)
    t.to_excel(w, sheet_name='Table S1', index=False)
    w.book.properties.creator = 'Hugues Lantuit'
print(f'{len(t):,} sheets, {t["Source ID"].nunique()} sources; years missing: {int(t["Publication year"].isna().sum())}')
print(t.loc[t['Publication year'].isna()].groupby('Source ID').size().to_dict())
