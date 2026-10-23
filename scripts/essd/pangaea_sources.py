#!/usr/bin/env python
"""sources.csv of the PANGAEA geology datasets: every source sheet of the release (sources_table.py) with the citation of
its source dataset (Appendix Table A1, citations.tsv).
usage: pangaea_sources.py RELEASE_SOURCES.csv CITATIONS.tsv OUT.csv"""
import sys

import pandas as pd

S, C, OUT = sys.argv[1:4]
s = pd.read_csv(S, keep_default_na=False)
s = s[~s['src_id'].isin(['none', ''])]                     # land without a source is no source sheet
c = pd.read_csv(C, sep='\t', keep_default_na=False)[['src_id', 'name', 'cite', 'reference']]
c = c.rename(columns={'name': 'source_name', 'cite': 'citation', 'reference': 'reference'})
m = s.merge(c, on='src_id', how='left')
miss = sorted(set(m.loc[m['citation'] == '', 'src_id']) | set(m.loc[m['citation'].isna(), 'src_id']))
if miss:
    sys.exit(f'no citation for {miss}')
m['reference'] = m['reference'].str.replace(' || ', ' | ', regex=False)
cols = ['src_id', 'src_sheet', 'source_name', 'scale_den', 'pub_year', 'licence', 'released_in', 'n_polygons',
        'area_km2', 'citation', 'reference']
m[cols].to_csv(OUT, index=False)
print(f'{len(m):,} sheets of {m["src_id"].nunique()} sources -> {OUT}')
print(m.groupby('released_in')['area_km2'].sum().round(0).to_string())
