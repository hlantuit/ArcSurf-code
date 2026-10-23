#!/usr/bin/env python
"""References of the individual GSC maps (ca_gsc_cgm, ca_gsc_legacy, ca_gsc_scans): sheet label -> GEOSCAN number
(sources/canada_gsc_sheets.json) -> DOI 10.4095/<number> -> authors, title and year from Crossref (cached in
OUT_DIR/crossref/; one request per 0.5 s). Without a Crossref record the reference is built from the GEOSCAN title.
usage: gsc_sheet_refs.py SOURCES.csv OUT_DIR   -> gsc_sheet_refs.csv, gsc_sheet_refs.ris"""
import json
import os
import re
import sys
import time

import pandas as pd
import requests

SRC, OUT = sys.argv[1:3]
CACHE = f'{OUT}/crossref'
os.makedirs(CACHE, exist_ok=True)
G = {x['label'].upper(): x for x in json.load(open('sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']}
sess = requests.Session()
sess.headers.update({'User-Agent': 'AWI-research/1.0 (+https://www.awi.de)'})


def lookup(label):
    k = str(label).upper()
    cands = [k, re.sub(r'^A(\d+)A$', r'M\1A', k), re.sub(r'^CGM0*', 'CGM', k)]
    return next((G[c] for c in cands if c in G), None)


def crossref(doi):
    f = f'{CACHE}/{doi.replace("/", "_")}.json'
    if os.path.exists(f):
        return json.load(open(f, encoding='utf-8'))
    time.sleep(0.5)
    try:
        r = sess.get(f'https://api.crossref.org/works/{doi}', timeout=60)
        d = r.json()['message'] if r.status_code == 200 else {}
    except (requests.RequestException, ValueError):
        d = {}
    json.dump(d, open(f, 'w', encoding='utf-8'))
    return d


def series(label):
    m = re.match(r'^CGM0*(\d+)$', label, flags=re.I)
    if m:
        return f'Canadian Geoscience Map {m.group(1)}'
    m = re.match(r'^[AM](\d+)A$', label, flags=re.I)
    if m:
        return f'"A" Series Map {m.group(1)}A'
    m = re.match(r'^OF(\d+)$', label, flags=re.I)
    return f'Open File {m.group(1)}' if m else label


S = pd.read_csv(SRC)
S = S[S['src_id'].isin(['ca_gsc_cgm', 'ca_gsc_legacy', 'ca_gsc_scans'])]
rows = []
for _, r in S.iterrows():
    g = lookup(r['src_sheet'])
    if not g:
        rows.append(dict(src_id=r['src_id'], src_sheet=r['src_sheet'], geoscan='', doi='', authors='', title='',
                         year=r['pub_year'], reference='', ok=False))
        continue
    doi = f"10.4095/{g['geoscan']}"
    c = crossref(doi)
    au = [f"{a.get('family', '')}, {' '.join(x + '.' for x in re.findall(r'([A-ZÀ-Ý])[a-zà-ÿ]*', a.get('given', '')))}".strip(', ')
          for a in c.get('author', []) if a.get('family')]
    title = (c.get('title') or [g.get('title', '')])[0].strip().rstrip('.')
    year = int(r['pub_year']) if pd.notna(r['pub_year']) else int(str(g.get('release', ''))[:4] or 0)
    sc = f", scale 1:{int(g['scale']):,}" if g.get('scale') else ''
    who = (', '.join(au[:-1]) + (', and ' if len(au) > 1 else '') + au[-1]) if au else 'Geological Survey of Canada'
    ref = f"{who}: {title}, Geological Survey of Canada, {series(g['label'])}{sc}, https://doi.org/{doi}, {year}."
    rows.append(dict(src_id=r['src_id'], src_sheet=r['src_sheet'], geoscan=g['geoscan'], doi=doi, authors='; '.join(au),
                     title=title, year=year, reference=ref, ok=bool(c)))
R = pd.DataFrame(rows)
R.to_csv(f'{OUT}/gsc_sheet_refs.csv', index=False)
with open(f'{OUT}/gsc_sheet_refs.ris', 'w', encoding='utf-8') as w:
    for x in R[R['geoscan'] != ''].itertuples():
        w.write('TY  - MAP\n' + ''.join(f'AU  - {a}\n' for a in (x.authors.split('; ') if x.authors else [])) +
                f'TI  - {x.title}\nPY  - {x.year}\nPB  - Geological Survey of Canada\nDO  - {x.doi}\n'
                f'N1  - ArcSurf sheet {x.src_sheet}\nER  - \n')
print(f'{len(R)} GSC sheets: GEOSCAN number for {(R.geoscan != "").sum()}, Crossref record for {R.ok.sum()}, '
      f'authors for {(R.authors != "").sum()}')
print('without GEOSCAN number:', R.loc[R.geoscan == '', 'src_sheet'].tolist())
