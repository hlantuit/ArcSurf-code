#!/usr/bin/env python
"""Years printed in the text layer of a sheet's vector PDF(s), with their context, plus the PDF metadata dates - to read
the imprint year of 1:200k vector sheets without looking at them (the geokniga record year is the COMPILATION year,
median 6 yr before print: scripts/year_page_validation.py).
PDFs: the 'pdf' path in sources/gk_pdf_sheets.csv, else every PDF in the sheet's download folder(s)
(raw/russia_geokniga/MANIFEST.json, matched like year200_candidates.py). Output one line per year occurrence:
sheet | file | year | context. --summary prints per sheet the years seen in imprint-like context (see IMPRINT).
usage: pdf_imprint_years.py [--summary] [--out work/pdf_imprint_years.csv] SHEET [SHEET ...] | --placeholder-vector"""
import json
import os
import re
import sys

sys.path.insert(0, "/albedo/work/user/hlantuit/arctic_surficial/pylib")   # pymupdf lives here (as in pdf_to_polygons.py)
import pandas as pd
import pymupdf

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
sys.path.insert(0, f'{ROOT}/scripts')
CYR = str.maketrans('АВЕКМНОРСТХаеорсх', 'ABEKMHOPCTXaeopcx')
YR = re.compile(r'(?<!\d)(19[4-9]\d|20[0-2]\d)(?!\d)')
IMPRINT = re.compile(r'издан|печат|подготовлен|изготовлен|картфабрик|картографическ|санкт-петербург|спб|москва|©|'
                     r'электронн|цифров|тираж|заказ|подписан', re.I)


def key(s):
    return re.sub(r'\s+', '', str(s).translate(CYR)).upper().replace('_', ',').replace('XXXX', 'XXX')


cfg = pd.read_csv(f'{ROOT}/sources/gk_pdf_sheets.csv', dtype=str, keep_default_na=False)
CFG = dict(zip(cfg['sheet'], cfg['pdf']))
DIRS = {}
man = json.load(open(f'{RAW}/russia_geokniga/MANIFEST.json', encoding='utf-8'))
for url, rec in man.items():
    d = f'{RAW}/russia_geokniga/' + re.sub(r'[^A-Za-z0-9,._-]', '_', rec['sheet'])
    for k in {key(rec['sheet']), key(re.split(r'\s*[(.|]', rec.get('title', ''))[0])}:
        DIRS.setdefault(k, set()).add(d)


def pdfs(s):
    if s in CFG and os.path.exists(CFG[s]):
        return [CFG[s]]
    out = []
    for d in sorted(DIRS.get(key(s), set())):
        if os.path.isdir(d):
            out += [f'{d}/{f}' for f in sorted(os.listdir(d)) if f.lower().endswith('.pdf')]
    return out


args = [a for a in sys.argv[1:] if not a.startswith('--')]
outp = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else None
if outp in args:
    args.remove(outp)
if '--placeholder-vector' in sys.argv:
    import ingest_russia as IR
    args = [s for s in IR._G200 if s not in IR._YEAR200_IMPRINT]
rows = []
for s in args:
    fs = pdfs(s)
    if not fs:
        rows.append(dict(sheet=s, file='', where='-', year='', imprint_ctx=False, ctx='NO PDF'))
    for f in fs:
        try:
            doc = pymupdf.open(f)
        except Exception as e:
            rows.append(dict(sheet=s, file=os.path.basename(f), where='-', year='', imprint_ctx=False, ctx=f'ERR {e}'))
            continue
        md = doc.metadata or {}
        for k in ('creationDate', 'modDate'):
            m = YR.search(md.get(k) or '')
            if m:
                rows.append(dict(sheet=s, file=os.path.basename(f), where='meta:' + k, year=m.group(1), imprint_ctx=False,
                                 ctx=f"{md.get('producer', '')} | {md.get('creator', '')}"[:80]))
        for pno, page in enumerate(doc):
            txt = page.get_text('text')
            for m in YR.finditer(txt):
                c = txt[max(0, m.start() - 70):m.end() + 40].replace('\n', ' ')
                rows.append(dict(sheet=s, file=os.path.basename(f), where=f'p{pno}', year=m.group(1),
                                 imprint_ctx=bool(IMPRINT.search(c)), ctx=c))
R = pd.DataFrame(rows)
if outp:
    R.to_csv(outp, index=False)
if '--summary' in sys.argv:
    for s, G in R.groupby('sheet', sort=False):
        imp = sorted(set(G[G.imprint_ctx].year))
        meta = sorted(set(G[G.where.str.startswith('meta')].year))
        allp = sorted(set(G[G.where.str.startswith('p')].year))
        print(f'{s:22s} imprint-ctx {"/".join(imp) or "-":20s} meta {"/".join(meta) or "-":10s} all {"/".join(allp)[:60]}')
else:
    for r in R.itertuples():
        print(f'{r.sheet:18s} {r.where:16s} {r.year:5s} {"*" if r.imprint_ctx else " "} {r.ctx[:150]}')
