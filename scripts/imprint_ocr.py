#!/usr/bin/env python
"""Print (publication) years of 1:200k sheets read by OCR from the sheet itself (tesseract rus+eng, conda env 'ocr').
Why: the geokniga record year is the COMPILATION year, median 6 yr (up to 17 yr) before the print/edition year
(scripts/year_page_validation.py, n=78); PDF text layers are curves; PDF creation dates are export dates.

  run   <shard> <nshards>  OCR the images of every target sheet in the shard -> work/imprint_ocr/txt/<sheet>__<i>.txt
  parse                    rules on the OCR text -> work/imprint_ocr/years.csv; calibration against the years read by
                           eye (ingest_russia._YEAR200_IMPRINT); resolved targets -> sources/year200_imprint.csv

Images: vector sheets (ingest_russia._G200): the extraction PDF (sources/gk_pdf_sheets.csv, else work/gk200_leg/
<sheet>__*.pdf, else the PDFs of the download folder), every page rendered at 150 dpi; raster sheets: every map JPG of
the download folder (run_rast.sh rule: not a legend/section/scheme file) plus the imprint images (*qinf*), downscaled
to <= 6000 px on the long side.
Rules (per sheet, over all its images): 1. '©' lines: latest year (2nd edition: '© Роснедра, 2013' = edition, author
'© <name>, 2003' = compilation); 2. else print lines ('подписано к печати', 'отпечатано', 'напечатано', 'тираж'):
latest year; 3. else unresolved. Targets = sheets of sources/year200.csv (page years) + YEAR_PLACEHOLDER.
usage: imprint_ocr.py run <shard> <nshards> | imprint_ocr.py parse"""
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')   # pymupdf
import pandas as pd  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
OUT = f'{ROOT}/work/imprint_ocr'
TESS = '/albedo/work/user/hlantuit/conda_envs/ocr/bin/tesseract'
sys.path.insert(0, f'{ROOT}/scripts')
import ingest_russia as IR  # noqa: E402

CYR = str.maketrans('АВЕКМНОРСТХаеорсх', 'ABEKMHOPCTXaeopcx')
ADDITIONAL = re.compile(r'(q|p)(l|r|s\d+)(_\d+)?\.jpe?g$|q_(l|r|s\d+)\.jpe?g$', re.I)   # legend/section/scheme (imprint kept)
YR = re.compile(r'(?<!\d)(19[4-9]\d|20[0-2]\d)(?!\d)')
PRINT = re.compile(r'подписан\w*\s+к\s+печат|отпечатан|напечатан|тираж|сдано\s+в\s+печат|в\s+печать', re.I)


def key(s):
    return re.sub(r'\s+', '', str(s).translate(CYR)).upper().replace('_', ',').replace('XXXX', 'XXX')


def folders(s):
    man = json.load(open(f'{RAW}/russia_geokniga/MANIFEST.json', encoding='utf-8'))
    out = set()
    for url, rec in man.items():
        if key(s) in {key(rec['sheet']), key(re.split(r'\s*[(.|]', rec.get('title', ''))[0])}:
            out.add(f'{RAW}/russia_geokniga/' + re.sub(r'[^A-Za-z0-9,._-]', '_', rec['sheet']))
    d = f'{RAW}/russia_geokniga/{s}'
    if os.path.isdir(d):
        out.add(d)
    return sorted(out)


def images(s):
    if s in IR._G200:
        cfg = pd.read_csv(f'{ROOT}/sources/gk_pdf_sheets.csv', dtype=str, keep_default_na=False)
        p = dict(zip(cfg['sheet'], cfg['pdf'])).get(s)
        if p and os.path.exists(p):
            return [p]
        p = sorted(glob.glob(f'{ROOT}/work/gk200_leg/{glob.escape(s)}__*.pdf'))
        return p or [f for d in folders(s) for f in sorted(glob.glob(f'{glob.escape(d)}/*.pdf'))]
    return [f for d in folders(s) for f in sorted(glob.glob(f'{glob.escape(d)}/*.jp*g')) if not ADDITIONAL.search(f)]


def targets():
    t = list(pd.read_csv(f'{ROOT}/sources/year200.csv', dtype=str)['sheet']) + IR.YEAR_PLACEHOLDER
    return sorted(set(t) | set(IR._YEAR200_IMPRINT))


def run(shard, n):
    import pymupdf
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    os.makedirs(f'{OUT}/txt', exist_ok=True)
    os.makedirs(f'{OUT}/png', exist_ok=True)
    for s in targets()[shard::n]:
        for i, f in enumerate(images(s)):
            base = f'{OUT}/txt/{s}__{i}'
            if os.path.exists(base + '.txt'):
                continue
            png = f'{OUT}/png/{s}__{i}.png'
            try:
                if f.lower().endswith('.pdf'):
                    doc = pymupdf.open(f)
                    pages = [p.get_pixmap(dpi=150) for p in doc]
                    if len(pages) == 1:
                        pages[0].save(png)
                    else:     # stack pages vertically
                        ims = [Image.frombytes('RGB', (p.width, p.height), p.samples) for p in pages]
                        W = max(im.width for im in ims)
                        canvas = Image.new('RGB', (W, sum(im.height for im in ims)), 'white')
                        y = 0
                        for im in ims:
                            canvas.paste(im, (0, y)); y += im.height
                        canvas.save(png)
                else:
                    im = Image.open(f).convert('RGB')
                    k = 6000 / max(im.size)
                    if k < 1:
                        im = im.resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
                    im.save(png)
                r = subprocess.run([TESS, png, base, '-l', 'rus+eng', '--psm', '11'], capture_output=True,
                                   env={**os.environ, 'OMP_THREAD_LIMIT': '4'})
                with open(base + '.src', 'w') as fh:
                    fh.write(f + '\n')
                print(s, i, os.path.basename(f)[:60], 'ok' if r.returncode == 0 else r.stderr.decode()[-200:], flush=True)
            except Exception as e:
                print(s, i, os.path.basename(f)[:60], 'ERROR', e, flush=True)
            finally:
                if os.path.exists(png):
                    os.remove(png)


def parse():
    rows = []
    for s in targets():
        cop, prn, src = [], [], []
        for t in sorted(glob.glob(f'{OUT}/txt/{glob.escape(s)}__*.txt')):
            src.append(os.path.basename(open(t[:-4] + '.src').read().strip()) if os.path.exists(t[:-4] + '.src') else '')
            for ln in open(t, encoding='utf-8', errors='ignore'):
                ys = [int(y) for y in YR.findall(ln)]
                if not ys:
                    continue
                if '©' in ln:
                    cop += [(y, ln.strip()[:90]) for y in ys]
                elif PRINT.search(ln):
                    prn += [(y, ln.strip()[:90]) for y in ys]
        if cop:
            y, how, ctx = max(c[0] for c in cop), 'copyright', ' | '.join(sorted({c[1] for c in cop}))
        elif prn:
            y, how, ctx = max(p[0] for p in prn), 'print', ' | '.join(sorted({p[1] for p in prn}))
        else:
            y, how, ctx = None, 'none' if src else 'no text', ''
        rows.append(dict(sheet=s, ocr_year=y, how=how, known=IR._YEAR200_IMPRINT.get(s), files=';'.join(src), ctx=ctx[:300]))
    R = pd.DataFrame(rows)
    R.to_csv(f'{OUT}/years.csv', index=False)
    C = R[R.known.notna()]
    ok = C[C.ocr_year.notna()]
    print(f'calibration: {len(C)} sheets with years read by eye | OCR resolved {len(ok)} | exact {int((ok.ocr_year == ok.known).sum())}')
    for r in C.itertuples():
        print(f'   {r.sheet:22s} eye {int(r.known)} ocr {r.ocr_year if r.ocr_year == r.ocr_year else "-"} ({r.how}) {r.ctx[:110]}')
    T = R[R.known.isna()]
    print(f'targets: {len(T)} | ' + ' '.join(f'{k}={v}' for k, v in T.how.value_counts().items()))
    Y = T[T.ocr_year.notna()].assign(year=lambda d: d.ocr_year.astype(int), evidence=lambda d: 'OCR ' + d.how + ': ' + d.ctx)
    # print cannot precede compilation: an OCR year BEFORE the record (compilation) year means only the authors' '©'
    # lines were read (R-40-XXXI,XXXII '© Затульская, 1999' vs record 2015) -> keep the record year
    page = pd.read_csv(f'{ROOT}/sources/year200.csv', dtype=str).set_index('sheet')['year'].astype(int)
    pg = Y.sheet.map(page)
    low = pg.notna() & (Y.year < pg)
    Y.loc[low, 'evidence'] = 'record year ' + pg[low].astype(int).astype(str) + ' kept: OCR ' + Y.loc[low, 'year'].astype(str) + \
        ' read only compilation lines (' + Y.loc[low, 'ctx'] + ')'
    Y.loc[low, 'how'] = 'record>ocr'
    Y.loc[low, 'year'] = pg[low].astype(int)
    print('OCR year before the record year -> record year kept:', list(Y.loc[low, 'sheet']))
    Y[['sheet', 'year', 'how', 'evidence']].to_csv(f'{ROOT}/sources/year200_imprint.csv', index=False)
    print('->', f'{ROOT}/sources/year200_imprint.csv', len(Y))


if __name__ == '__main__':
    if sys.argv[1] == 'run':
        run(int(sys.argv[2]), int(sys.argv[3]))
    else:
        parse()
