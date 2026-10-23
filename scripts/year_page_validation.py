#!/usr/bin/env python
"""How good is the geokniga PAGE year ('Карта составлена: <org>, YYYY г.') as the publication year of a sheet?
Compared with the print years READ ON THE SHEETS (imprint / 'signed for print') at extraction:
  200k: ingest_russia._YEAR200_IMPRINT and the 1:200k PREVIEW_SHEETS (all imprint readings except N-44-V)
  1M:   ingest_russia._YEAR1M_IMPRINT and the 1:1M previews whose year was read on the sheet (listed below)
  g2:   ingest_russia._G2YEAR (2nd-generation 1:1M years noted when processing; provenance not recorded) - reported apart
Page lookup as in year200_candidates.py / year1m_candidates.py (download manifests; page years cached in
work/year200_pages.json, work/year1m_pages.json; --fetch reads missing pages politely, 5 s apart).
Prints per group: n, exact, |d| <= 1, |d| <= 3, median (page - imprint), and every |d| > 3.
--sheets 'A;B;C' instead prints the page year of the named sheets (1:200k names; for registering new previews).
usage: year_page_validation.py [--fetch] [--sheets 'S1;S2']"""
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
COMP = re.compile(r'составлена:\s*(?:<[^>]+>[^<]*</[^>]+>\s*,?\s*)*[^<]*?(\d{4})\s*г\.')
fetch = '--fetch' in sys.argv
PREVIEW1M_READ = {'P-48-49_g2pv': 1989, 'T-48-50_g2pv': 2002, 'P-46-47_g2pv': 1977, 'P-40-41_g2pv': 1989,
                  'N-44-45_g2pv': 1983, 'P-58-59_g2pv': 1983, 'N-46-47_g2pv': 1977}


def key200(s):
    return re.sub(r'\s+', '', str(s).translate(CYR)).upper().replace('_', ',').replace('XXXX', 'XXX')


def key1m(s):
    s = re.sub(r'\s+', '', str(s).translate(CYR)).upper()
    nom, _, gen = s.partition('_')
    return re.sub(r'-+', '-', nom.replace('(', '-').replace(')', '').replace(',', '-')), gen.lower().replace('pv', '')


def manifest(d):
    p = f'{RAW}/{d}/MANIFEST.json'
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else {}


P200, HASPDF = {}, set()
for url, rec in manifest('russia_geokniga').items():
    for k in {key200(rec['sheet']), key200(re.split(r'\s*[(.|]', rec.get('title', ''))[0])}:
        P200.setdefault(k, set()).add(url.rstrip('/'))
    if any(f['url'].lower().endswith('.pdf') for f in rec.get('files', [])):
        HASPDF.add(url.rstrip('/'))
P1M = {}
for url, rec in manifest('russia_geokniga_1m').items():
    P1M.setdefault(key1m(rec['sheet']), set()).add(url.rstrip('/'))
BYPAGE = {}
for f in ('geokniga_q200_resolved.json', 'geokniga_q200_target.json'):
    for x in json.load(open(f'{ROOT}/sources/{f}', encoding='utf-8')):
        if x.get('year') and x.get('page'):
            BYPAGE[x['page'].rstrip('/')] = str(x['year'])
CACHES = {c: (json.load(open(f'{ROOT}/work/{c}', encoding='utf-8')) if os.path.exists(f'{ROOT}/work/{c}') else {})
          for c in ('year200_pages.json', 'year1m_pages.json')}


def page_year(url, cache):
    if url in BYPAGE:
        return BYPAGE[url]
    for c in CACHES.values():
        if url in c:
            return c[url]
    if not fetch:
        return ''
    r = subprocess.run(['curl', '-sS', '-L', '--http1.1', '-A', UA, '--max-time', '90', url], capture_output=True)
    time.sleep(5)
    m = COMP.search(r.stdout.decode('utf-8', 'ignore'))
    CACHES[cache][url] = m.group(1) if m else ''
    json.dump(CACHES[cache], open(f'{ROOT}/work/{cache}', 'w', encoding='utf-8'), indent=1)
    return CACHES[cache][url]


def years(s, scale, vector=False):
    if scale == 200_000:
        urls = sorted(P200.get(key200(s), set()))
        ys = sorted({y for y in (page_year(u, 'year200_pages.json') for u in urls) if y})
        if len(ys) > 1 and vector:
            ys = sorted({y for y in (page_year(u, 'year200_pages.json') for u in urls if u in HASPDF) if y}) or ys
    else:
        nom, gen = key1m(s)
        urls = sorted(P1M.get((nom, gen), set()) or (P1M.get((nom, 'g3'), set()) if gen == 'pq' else set()))
        ys = sorted({y for y in (page_year(u, 'year1m_pages.json') for u in urls) if y})
    return ys, urls


if '--sheets' in sys.argv:
    for s in sys.argv[sys.argv.index('--sheets') + 1].split(';'):
        ys, urls = years(s, 200_000)
        print(f'{s:22s} page year {"/".join(ys) or "-":10s} {" ".join(urls)}')
    sys.exit()

ref = [(s, y, '200k', 200_000) for s, y in IR._YEAR200_IMPRINT.items()] + \
      [(s, y, '200k', 200_000) for s, (sc, y) in IR.PREVIEW_SHEETS.items() if sc == 200_000 and s != 'N-44-V'] + \
      [(s, y, '1M', 1_000_000) for s, y in {**IR._YEAR1M_IMPRINT, **PREVIEW1M_READ}.items()] + \
      [(s, y, 'g2', 1_000_000) for s, y in IR._G2YEAR.items()]
rows = []
for s, y, grp, sc in ref:
    ys, urls = years(s, sc, vector=s in IR._G200)
    rows.append(dict(sheet=s, group=grp, imprint=y, page='/'.join(ys), d=(int(ys[0]) - y) if len(ys) == 1 else np.nan,
                     pages=' '.join(urls)))
R = pd.DataFrame(rows)
R.to_csv(f'{ROOT}/work/year_page_validation.csv', index=False)
for g, G in R.groupby('group', sort=False):
    d = G.d.dropna()
    print(f'{g:5s} n={len(G)} matched={len(d)} exact={int((d == 0).sum())} |d|<=1={int((d.abs() <= 1).sum())} '
          f'|d|<=3={int((d.abs() <= 3).sum())} median(page-imprint)={d.median() if len(d) else float("nan"):+.1f}')
    for r in G[(G.d.abs() > 3) | G.d.isna()].itertuples():
        print(f'      {r.sheet:22s} imprint {r.imprint} page {r.page or "-"} {r.pages[:70]}')
