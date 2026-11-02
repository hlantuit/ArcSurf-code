#!/usr/bin/env python
"""Adds desc_form to sources.csv: for the sheets of the State Geological Map (ru_vsegei_pdf, ru_vsegei_preview),
whether the unit descriptions in src_desc are verbatim Russian, English summaries or mixed, from the language table of
legend_language.py (majority language of the descriptions of each sheet). Other sources are left empty. Rewrites
SOURCES in place; running it again gives the same file.
usage: sources_desc_form.py SOURCES.csv LEGEND_LANGUAGE.csv"""
import sys

import pandas as pd

S, L = sys.argv[1:3]
FORM = {'ru': 'Russian, verbatim', 'en': 'English summary', 'mixed': 'mixed'}
s = pd.read_csv(S, keep_default_na=False, dtype=str)
lang = pd.read_csv(L, keep_default_na=False, dtype=str)
lang = lang[lang['src_id'].isin(['ru_vsegei_pdf', 'ru_vsegei_preview'])]
key = dict(zip(zip(lang['src_id'], lang['src_sheet']), lang['lang'].map(FORM).fillna('')))
s['desc_form'] = [key.get((a, b), '') for a, b in zip(s['src_id'], s['src_sheet'])]
vs = s['src_id'].isin(['ru_vsegei_pdf', 'ru_vsegei_preview'])
if (s.loc[vs, 'desc_form'] == '').any():
    sys.exit(f'no language for {int((s.loc[vs, "desc_form"] == "").sum())} State Geological Map sheets')
s.to_csv(S, index=False)
print(s.loc[vs, 'desc_form'].value_counts().to_string())
