#!/usr/bin/env python
"""Print years for the 1:1M sheets of ingest_russia that carry the 2013 placeholder (_G1M sheets without an explicit
year: the 3rd-generation '_g3' and Pliocene-Quaternary '_pq' sheets), from the geokniga map page each sheet was
downloaded from (raw/russia_geokniga_1m/MANIFEST.json; the page's 'Карта составлена: <org>, YYYY г.' field; one polite
request per page, 5 s apart, cached in work/year1m_pages.json). Also REPORTS (does not write) the page years of the
preview-derived 1:1M sheets (PREVIEW_SHEETS *_g2pv), whose years are imprint readings or placeholders.
Names are matched after normalisation: manifest 'R-37,38_g3', 'Q-(35)-37_g2', 'O-37(38)_g2' = 'R-37-38', 'Q-35-37',
'O-37-38'; a '_pq' sheet matches a manifest '_pq' entry, else '_g3'.
Writes sources/year1m.csv (sheet, year, how, evidence), merged into the existing file; ingest_russia reads it.
usage: year1m_candidates.py [--fetch]"""
import json
import os
import re
import subprocess
import sys
import time

import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
sys.path.insert(0, f'{ROOT}/scripts')
import ingest_russia as IR  # noqa: E402

UA = 'AWI-research/1.0 (+https://www.awi.de)'
CYR = str.maketrans('АВЕКМНОРСТХаеорсх', 'ABEKMHOPCTXaeopcx')
COMP = re.compile(r'составлена:\s*(?:<[^>]+>[^<]*</[^>]+>\s*,?\s*)*[^<]*?(\d{4})\s*г\.')
fetch = '--fetch' in sys.argv


def norm(s):
    """'Q-(35)-37_g2' -> ('Q-35-37', 'g2'); 'O-37(38)_g2' -> ('O-37-38', 'g2'); 'R-37,38_g3' -> ('R-37-38', 'g3')"""
    s = re.sub(r'\s+', '', str(s).translate(CYR)).upper()
    nom, _, gen = s.partition('_')
    nom = re.sub(r'-+', '-', nom.replace('(', '-').replace(')', '').replace(',', '-'))
    return nom, gen.lower()


man = json.load(open(f'{RAW}/russia_geokniga_1m/MANIFEST.json', encoding='utf-8'))
bykey = {}
for url, rec in man.items():
    bykey.setdefault(norm(rec['sheet']), []).append((url.rstrip('/'), rec.get('title', '')[:90]))
cpath = f'{ROOT}/work/year1m_pages.json'
cache = json.load(open(cpath, encoding='utf-8')) if os.path.exists(cpath) else {}


def page_year(url):
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


def lookup(s):
    nom, gen = norm(s)
    gen = gen.replace('pv', '')                       # 'g2pv' (preview-derived) was downloaded as 'g2'
    hits = bykey.get((nom, gen), []) or (bykey.get((nom, 'g3'), []) if gen == 'pq' else [])
    return hits


rows = []
targets = [(s, 'placeholder') for s in IR.YEAR_PLACEHOLDER_1M] + \
          [(s, f'preview, now {y}') for s, (sc, y) in IR.PREVIEW_SHEETS.items() if sc == 1_000_000]
for s, kind in targets:
    hits = lookup(s)
    ys = sorted({y for y in (page_year(u) for u, _ in hits) if y})
    rows.append(dict(sheet=s, kind=kind, year=ys[0] if len(ys) == 1 else '', page_years='/'.join(ys),
                     pages=';'.join(u for u, _ in hits), title=hits[0][1] if hits else ''))
R = pd.DataFrame(rows)
R.to_csv(f'{ROOT}/work/year1m_candidates.csv', index=False)
for r in R.itertuples():
    print(f'{r.sheet:16s} {r.kind:18s} {r.year or "----":5s} pages={r.page_years or "-":10s} {r.pages[-30:]:30s} {r.title[:50]}')
Y = R[(R.kind == 'placeholder') & (R.year != '')].assign(how='page', evidence=lambda d: 'geokniga page ' + d.pages)
yp = f'{ROOT}/sources/year1m.csv'
old = pd.read_csv(yp, dtype=str, keep_default_na=False) if os.path.exists(yp) else Y.iloc[:0][['sheet', 'year', 'how', 'evidence']]
pd.concat([old, Y[['sheet', 'year', 'how', 'evidence']]]).drop_duplicates('sheet', keep='last').to_csv(yp, index=False)
print(len(R[R.kind == 'placeholder']), 'placeholder sheets |', len(Y), 'resolved ->', yp)
