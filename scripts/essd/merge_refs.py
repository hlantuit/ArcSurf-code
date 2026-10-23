#!/usr/bin/env python
"""One reference per source sheet for Table S1 and the PANGAEA metadata. Preference: verified geokniga record
(ru_sheet_refs_reviewed.csv), GSC record (gsc_sheet_refs.csv), checked colleague record (checked_refs.csv, when present), else
the reference of the source dataset (Appendix A). Writes:
  pangaea/sources.csv               + column sheet_reference (= Table S1, distributed with the data)
  pangaea/ArcSurf_source_references.ris   every distinct reference (datasets and individual sheets) for import
usage: merge_refs.py [work_local/refs]"""
import os
import re
import sys

import pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else 'work_local/refs'
S = pd.read_csv('pangaea/sources.csv')
ref = {}
r = pd.read_csv(f'{D}/ru_sheet_refs_reviewed.csv', dtype=str, keep_default_na=False)
ref.update({(a, b): c for a, b, c, ok in zip(r.src_id, r.src_sheet, r.reference, r.record_ok) if ok == 'True' and c})
g = pd.read_csv(f'{D}/gsc_sheet_refs.csv', dtype=str, keep_default_na=False)
ref.update({(a, b): c for a, b, c in zip(g.src_id, g.src_sheet, g.reference) if c})
if os.path.exists(f'{D}/checked_refs.csv'):
    k = pd.read_csv(f'{D}/checked_refs.csv', dtype=str, keep_default_na=False)
    ref.update({(a, b): c for a, b, c in zip(k.src_id, k.src_sheet, k.reference) if c})
S['sheet_reference'] = [ref.get((a, str(b)), '') for a, b in zip(S.src_id, S.src_sheet)]
S.to_csv('pangaea/sources.csv', index=False)


def ris_from_text(t):
    """minimal RIS record from a formatted reference 'Authors: Title, ..., Year.'"""
    m = re.match(r'^(.*?):\s(.*)$', t)
    who, rest = (m.group(1), m.group(2)) if m else ('', t)
    yr = re.search(r'(\d{4})[a-z]?\.?\s*(?:\(in [A-Za-z]+\)\.)?$', t)
    doi = re.search(r'https://doi\.org/(\S+?)[,.]?(?:\s|$)', t)
    url = re.search(r'(https?://(?!doi\.org)\S+?)[,]?(?:\s|$)', t)
    out = ['TY  - MAP' if re.search(r'map|карта|sheet', t, flags=re.I) else 'TY  - DATA']
    authors = re.split(r',\s(?:and\s)?(?=[^,]+,\s(?:[A-Z]\.\s?)+)|\sand\s', who) if re.search(r',\s[A-Z]\.', who) else [who]
    out += [f'AU  - {a.strip().strip(",")}' for a in authors if a.strip()]
    out += [f'TI  - {rest}', f'PY  - {yr.group(1)[:4]}' if yr else '']
    out += [f'DO  - {doi.group(1)}' if doi else '', f'UR  - {url.group(1)}' if url else '', 'ER  - ']
    return '\n'.join(x for x in out if x)


refs = list(dict.fromkeys([x for x in S['sheet_reference'] if x] +
                          [x for x in S['reference'].dropna() for x in str(x).split(' | ') if x]))
with open('pangaea/ArcSurf_source_references.ris', 'w', encoding='utf-8') as w:
    w.write('\n'.join(ris_from_text(x) for x in refs) + '\n')
n_sheet = (S['sheet_reference'] != '').sum()
print(f'{len(S):,} sheets: own reference for {n_sheet:,}; dataset reference only for {len(S) - n_sheet:,}; '
      f'{len(refs):,} distinct references in pangaea/ArcSurf_source_references.ris')
print(S.loc[S['sheet_reference'] == ''].groupby('src_id').size().sort_values(ascending=False).head(12).to_dict())
