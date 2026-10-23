#!/usr/bin/env python
"""Print years for the 1:200k sheets of ingest_russia that still carry the 2010 placeholder
(ingest_russia.YEAR_PLACEHOLDER). Sources, in order of trust:
  page  - the geokniga map page the sheet was DOWNLOADED from (raw/russia_geokniga/MANIFEST.json: sheet -> page url):
          its 'Карта составлена: <org>, YYYY г.' field. Taken from the record tables when the page is listed there
          (sources/geokniga_q200_resolved.json / _target.json, field 'year'); otherwise read from the page itself with
          --fetch (one polite request per page, 5 s apart; cached in work/year200_pages.json)
  geo   - 'year' of any geokniga record with the same nomenclature (Cyrillic look-alikes mapped to Latin); ambiguous
          when the sheet had two editions (e.g. 1960 and 2017)
  note  - years in the sheet's legend notes, our own 2026 dates excluded
A vector sheet (ingest_russia._G200) with two downloaded editions takes the year of the page that holds a PDF.
Writes work/year200_candidates.csv with 'year' = page year, else the single geo year, else the single note year, and
the resolved rows to sources/year200.csv (sheet, year, how, evidence), which ingest_russia reads into _YEAR200.
usage: year200_candidates.py [--fetch]"""
import json
import os
import re
import subprocess
import sys
import time

import numpy as np
import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
sys.path.insert(0, f'{ROOT}/scripts')
import ingest_russia as IR  # noqa: E402

UA = 'AWI-research/1.0 (+https://www.awi.de)'
CYR = str.maketrans('АВЕКМНОРСТХаеорсх', 'ABEKMHOPCTXaeopcx')
YR = re.compile(r'(?<!\d)(19[2-9]\d|20[0-2]\d)(?!\d)')
COMP = re.compile(r'составлена:\s*(?:<[^>]+>[^<]*</[^>]+>\s*,?\s*)*[^<]*?(\d{4})\s*г\.')
fetch = '--fetch' in sys.argv


def key(s):
    # commas are kept ('Q-41-I,II' must not become 'Q-41-III'); '_' joins two-sheet names ('P-58-XXXIV_O-58-IV');
    # 'XXXX' is a title typo (T-47-XXXI,XXXII,XXXXIII): sheet numerals stop at XXXVI
    return re.sub(r'\s+', '', str(s).translate(CYR)).upper().replace('_', ',').replace('XXXX', 'XXX')


geo, bypage = {}, {}
for f in ('geokniga_q200_resolved.json', 'geokniga_q200_target.json'):
    for x in json.load(open(f'{ROOT}/sources/{f}', encoding='utf-8')):
        if not x.get('year'):
            continue
        if x.get('page'):
            bypage[x['page'].rstrip('/')] = str(x['year'])
        for k in {key(x.get('nom', '')), key(x.get('sheets', ''))}:
            if k:
                geo.setdefault(k, set()).add(str(x['year']))
pages, has_pdf = {}, set()
for d in ('russia_geokniga', 'russia_geokniga_1m'):
    mf = f'{RAW}/{d}/MANIFEST.json'
    if os.path.exists(mf):
        for url, rec in json.load(open(mf, encoding='utf-8')).items():
            # the manifest 'sheet' is the census key ('S-44-XXI, XXII', 'T-47-XXXI,XXXII' for T-47-XXXI,XXXII,XXXIII):
            # match on it AND on the nomenclature that opens the record title
            for k in {key(rec['sheet']), key(re.split(r'\s*[(.|]', rec.get('title', ''))[0])}:
                pages.setdefault(k, set()).add(url.rstrip('/'))
            if any(f['url'].lower().endswith('.pdf') for f in rec.get('files', [])):
                has_pdf.add(url.rstrip('/'))
cpath = f'{ROOT}/work/year200_pages.json'
cache = json.load(open(cpath, encoding='utf-8')) if os.path.exists(cpath) else {}


def page_year(url):
    if url in bypage:
        return bypage[url]
    if url in cache:
        return cache[url]
    if not fetch:
        return ''
    r = subprocess.run(['curl', '-sS', '-L', '--http1.1', '-A', UA, '--max-time', '90', url], capture_output=True)
    time.sleep(5)
    m = COMP.search(r.stdout.decode('utf-8', 'ignore'))
    cache[url] = m.group(1) if m else ''
    json.dump(cache, open(cpath, 'w', encoding='utf-8'), indent=1)
    return cache[url]


rows = []
for s in IR.YEAR_PLACEHOLDER:
    pg = sorted(pages.get(key(s), set()))
    py = sorted({y for y in (page_year(u) for u in pg) if y})
    vec = s in IR._G200
    if len(py) > 1 and vec:
        # two editions downloaded (e.g. 1960 JPG + 2017 PDF): a vector sheet was extracted from the edition with the PDF
        py = sorted({y for y in (page_year(u) for u in pg if u in has_pdf) if y}) or py
    g = sorted(geo.get(key(s), set()) | geo.get(key(s.replace('_', ',')), set()))
    notes = []
    lf = f'{ROOT}/sources/legend_{s}.csv'
    if os.path.exists(lf):
        L = pd.read_csv(lf, dtype=str, keep_default_na=False)
        for c in [c for c in ('note', 'description_ru') if c in L.columns]:
            for t in L[c]:
                for m in YR.finditer(t):
                    if m.group(1) != '2026':
                        notes.append((m.group(1), t[max(0, m.start() - 50):m.end() + 25].replace('\n', ' ')))
    ny = sorted({y for y, _ in notes})
    year, how = ((py[0], 'page') if len(py) == 1 else (g[0], 'geo') if len(g) == 1 and not py
                 else (ny[0], 'note') if len(ny) == 1 and not py and not g else ('', 'ambiguous' if py or g or ny else 'none'))
    rows.append(dict(sheet=s, year=year, how=how, page_years='/'.join(py), geo_years='/'.join(g), note_years='/'.join(ny),
                     pages=';'.join(pg), note_ctx=' || '.join(sorted({c for _, c in notes}))[:300]))
R = pd.DataFrame(rows)
R.to_csv(f'{ROOT}/work/year200_candidates.csv', index=False)
# resolved rows -> sources/year200.csv, read by ingest_russia (_YEAR200; years read from an imprint stay in the code)
Y = R[R.year != ''].assign(evidence=lambda d: np.where(d.how == 'page', 'geokniga page ' + d.pages,
                                                       np.where(d.how == 'geo', 'geokniga record (same nomenclature)',
                                                                'legend note: ' + d.note_ctx)))
# MERGED into the existing file: sheets resolved earlier are no longer in YEAR_PLACEHOLDER (ingest_russia reads this file)
yp = f'{ROOT}/sources/year200.csv'
old = pd.read_csv(yp, dtype=str, keep_default_na=False) if os.path.exists(yp) else Y.iloc[:0]
pd.concat([old, Y[['sheet', 'year', 'how', 'evidence']]]).drop_duplicates('sheet', keep='last').to_csv(yp, index=False)
for r in R.itertuples():
    print(f'{r.sheet:24s} {r.year or "----":5s} {r.how:9s} page={r.page_years or "-":10s} geo={r.geo_years or "-":10s} '
          f'note={r.note_years or "-":10s} {r.pages[:60]}')
print(len(R), 'placeholder sheets |', R.how.value_counts().to_dict())
