#!/usr/bin/env python
"""References of the individual Russian sheets (ru_vsegei_pdf, ru_vsegei_preview) from their geokniga.org records.

1. sheet -> geokniga record: sources/year200.csv, year1m.csv, geokniga_coastal_pages.txt, geokniga_pq1000_pages.txt,
   geokniga_q1000.json and record numbers in the legend notes; the rest by the geokniga site search
2. every record page is fetched once (cache work_local/refs/pages/<id>.html, one request per 1.5 s) and parsed:
   title, compiler and year ('Карта составлена'), authors, editors, series, scale, sheets on the map
3. a record counts only if its title or 'sheets on this map' names the sheet
4. references in Copernicus style (original title, English rendering in brackets, '(in Russian)'); the year is the
   publication year of the release table (= Table S1)
usage: ru_sheet_refs.py SOURCES.csv OUT_DIR   -> ru_sheet_refs.csv, ru_sheet_refs.ris"""
import glob
import html
import json
import os
import re
import sys
import time
import urllib.parse

import pandas as pd
import requests

SRC, OUT = sys.argv[1:3]
CACHE = f'{OUT}/pages'
os.makedirs(CACHE, exist_ok=True)
UA = {'User-Agent': 'AWI-research/1.0 (+https://www.awi.de)'}
BASE = 'https://www.geokniga.org'


def norm(s):
    return re.sub(r'\s+', '', str(s)).replace('(', '').replace(')', '').upper()


def node(u):
    m = re.search(r'/maps/(\d+)', str(u))
    return m.group(1) if m else None


# --- 1. sheet -> record ----------------------------------------------------------------------------------------------
rec = {}
for f in ['sources/year200.csv', 'sources/year1m.csv']:
    for line in open(f, encoding='utf-8'):
        p = line.rstrip('\n').split(',', 3)
        if len(p) == 4 and 'geokniga' in p[3] and node(p[3]):
            rec.setdefault(norm(p[0]), node(p[3]))
for f in ['sources/geokniga_coastal_pages.txt', 'sources/geokniga_pq1000_pages.txt']:
    for line in open(f, encoding='utf-8'):
        if '\t' in line and node(line):
            rec.setdefault(norm(line.split('\t')[0]), node(line))
for r in json.load(open('sources/geokniga_q1000.json', encoding='utf-8')):
    cols = r.get('cols') or []
    if not cols or not node(r.get('url')):
        continue
    name = f"{r['row']}-{cols[0]}" + (f"-{cols[-1]}" if len(cols) > 1 else '')
    for suf in ('', 'PV'):
        rec.setdefault(norm(f"{name}_g{r.get('gen', '')}{suf}"), node(r['url']))
for f in glob.glob('sources/legend_*.csv'):
    sh = os.path.basename(f)[7:-4]
    try:
        notes = ' '.join(pd.read_csv(f, dtype=str, keep_default_na=False).get('note', pd.Series(dtype=str)))
    except Exception:
        continue
    m = re.search(r'geokniga\s+(?:record\s+|maps/|node\s+|page\s+|)(\d{4,6})(?![x\d])', notes)
    if m:
        rec.setdefault(norm(sh), m.group(1))

S = pd.read_csv(SRC)
S = S[S['src_id'].isin(['ru_vsegei_pdf', 'ru_vsegei_preview'])].copy()
S['node'] = [rec.get(norm(s)) for s in S['src_sheet']]
print(f'{len(S)} Russian sheets; record known locally for {S["node"].notna().sum()}', flush=True)

sess = requests.Session()
sess.headers.update(UA)
last = [0.0]


def get(url):
    wait = 1.5 - (time.time() - last[0])
    if wait > 0:
        time.sleep(wait)
    last[0] = time.time()
    for k in range(3):
        try:
            r = sess.get(url, timeout=60)
            r.encoding = 'utf-8'
            return r.text
        except requests.RequestException:
            time.sleep(5 * (k + 1))
    return ''


def page(n):
    f = f'{CACHE}/{n}.html'
    if not os.path.exists(f):
        t = get(f'{BASE}/maps/{n}')
        if t:
            open(f, 'w', encoding='utf-8').write(t)
        return t
    return open(f, encoding='utf-8').read()


def base_name(s):
    """'O-52-53_g2' -> 'O-52-53'; 'R-35-XXIX,XXX' stays"""
    return re.sub(r'_(g\d+|pq|g\dpv|pv)$', '', s, flags=re.I)


def expand(s):
    """component sheets: 'M-53-55_g2' -> {M-53, M-54, M-55}; 'Q-39-I,II' -> {Q-39-I, Q-39-II};
    'N-56-VI_N-57-I' -> {N-56-VI, N-57-I}; free text: every nomenclature it contains"""
    out = set()
    for part in re.split(r'_(?=[A-U]-)', base_name(str(s))):
        m = re.match(r'^([A-U])-\(?(\d+)\)?((?:[-,]\s*\(?\d+\)?)*)$', part.strip())
        if m:
            cols = [int(m.group(2))] + [int(x) for x in re.findall(r'\d+', m.group(3))]
            span = '-' in m.group(3) and max(cols) - min(cols) <= 4      # 'Q-60-1' crosses 180 E: a list
            out |= {f'{m.group(1)}-{c}' for c in range(min(cols), max(cols) + 1)} if span else \
                {f'{m.group(1)}-{c}' for c in cols}
            continue
        m = re.match(r'^([A-U])-(\d+)-([IVXL,\s()]+)$', part.strip())
        if m:
            out |= {f'{m.group(1)}-{m.group(2)}-{r}' for r in re.findall(r'[IVXL]+', m.group(3))}
    if not out:
        for m in re.finditer(r'\b([A-U])-\(?(\d{1,2})\)?(?:-([IVXL]+(?:\s*,\s*[IVXL]+)*))?(?:\s*,\s*\(?(\d{1,2})\)?)*', str(s)):
            if m.group(3):
                out |= {f'{m.group(1)}-{m.group(2)}-{r}' for r in re.findall(r'[IVXL]+', m.group(3))}
            else:
                out |= {f'{m.group(1)}-{c}' for c in re.findall(r'\d{1,2}', m.group(0)[2:])}
    return out


# --- search for the rest ---------------------------------------------------------------------------------------------
for i in S.index[S['node'].isna()]:
    want = expand(S.at[i, 'src_sheet'])
    first = sorted(want)[0] if want else base_name(S.at[i, 'src_sheet'])
    t = get(f'{BASE}/search/node/' + urllib.parse.quote(first))
    best = None
    for m in re.finditer(r'href="(?:https://www\.geokniga\.org)?/maps/(\d+)"[^>]*>(.*?)</a>', t, flags=re.S):
        title = html.unescape(re.sub(r'<[^>]+>', '', m.group(2)))
        if want and want <= expand(title) and re.search(r'четвертичн', title, flags=re.I):
            best = m.group(1)
            break
    S.at[i, 'node'] = best
print(f'after search: record for {S["node"].notna().sum()} of {len(S)}', flush=True)


# --- 2. parse ----------------------------------------------------------------------------------------------------------
def fields(t):
    d = {}
    for m in re.finditer(r'<legend>(.*?)</legend>(.*?)</fieldset>', t, flags=re.S):
        lab = re.sub(r'<[^>]+>', '', m.group(1)).strip().rstrip(':')
        d[lab] = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', m.group(2)))).strip()
    m = re.search(r'<title>(.*?)</title>', t, flags=re.S)
    d['title'] = html.unescape(m.group(1)).split(' | ')[0].strip() if m else ''
    return d


TR = dict(zip('абвгдеёжзийклмнопрстуфхцчшщъыьэюя',
              ['a', 'b', 'v', 'g', 'd', 'e', 'e', 'zh', 'z', 'i', 'y', 'k', 'l', 'm', 'n', 'o', 'p', 'r', 's', 't', 'u',
               'f', 'kh', 'ts', 'ch', 'sh', 'shch', '', 'y', "'", 'e', 'yu', 'ya']))


def tr(s):
    out = []
    for c in s:
        lo = c.lower()
        if lo in TR:
            v = TR[lo]
            out.append(v.capitalize() if c != lo and v else v)
        else:
            out.append(c)
    return ''.join(out)


def person(p):
    """'Васькин А.Ф.' -> "Vas'kin, A. F." """
    p = p.strip().strip(',;')
    m = re.match(r'^([^\s.]+(?:-[^\s.]+)?)\s+((?:[^\s.]\.\s*-?)+)$', p)
    if not m:
        return tr(p)
    ini = ' '.join(x + '.' for x in re.findall(r'([^\s.\-])\.', m.group(2)))
    return f'{tr(m.group(1))}, {tr(ini)}'


def people(s):
    return [person(x) for x in re.split(r'\s*[,;]\s*(?=[А-ЯЁA-Z])', s or '') if x.strip()]


ORG = {'ВСЕГЕИ': 'VSEGEI', 'Роснедра': 'Rosnedra', 'СНИИГГиМС': 'SNIIGGiMS', 'ВНИИОкеангеология': 'VNIIOkeangeologiya'}


def org(s):
    s = re.sub(r',?\s*\d{4}\s*г\.?', '', s or '').strip(' ,')
    for k, v in ORG.items():
        if k in s:
            return v
    return tr(re.sub(r'[«»"]', '', s)).strip()


def english(title, scale, series):
    t = title
    base = ('State Geological Map of the Russian Federation' if 'Российской Федерации' in t else
            'State Geological Map of the USSR' if 'Государственная геологическая карта СССР' in t else
            'Geological Map of the USSR')
    ed = ('2nd edition' if 'Издание второе' in t else '3rd generation' if 'Третье поколение' in t.title() or 'третье поколение' in t
          else 'new series' if re.search(r'нов(ая|ой) сери', t, flags=re.I) else '1st edition' if 'Издание первое' in t else '')
    kind = ('Pliocene–Quaternary' if re.search(r'плиоцен-четвертичн', t, flags=re.I) else
            'Neogene–Quaternary' if re.search(r'неоген-четвертичн', t, flags=re.I) else
            'Paleogene–Quaternary' if re.search(r'палеоген-четвертичн', t, flags=re.I) else 'Quaternary')
    what = 'deposits' if re.search(r'четвертичных отложений', t, flags=re.I) else 'formations'
    sheet = re.match(r'^\s*([^.(]+?)\s*(?:\(([^)]*)\))?\.', t)
    place = f' ({tr(sheet.group(2))})' if sheet and sheet.group(2) else ''
    parts = [base, f'scale {scale}' if scale else '', ed, f'{tr(series)} series' if series else '',
             f'sheet {sheet.group(1).strip()}{place}' if sheet else '', f'map of {kind} {what}']
    return ', '.join(p for p in parts if p)


rows = []
for _, r in S.iterrows():
    n = r['node']
    d = fields(page(n)) if isinstance(n, str) and n else {}
    title = d.get('title', '')
    on = d.get('Листы на этой карте', '')
    want = expand(r['src_sheet'])
    ok = bool(title) and (norm(base_name(r['src_sheet'])) in norm(title + ' ' + on)
                          or bool(want and want <= (expand(on) | expand(title))))
    comp = d.get('Карта составлена', '')
    yr_page = re.search(r'(\d{4})', comp)
    auth = people(d.get('Автор(ы)', '') or d.get('Авторы', ''))
    eds = people(d.get('Редактор(ы)', ''))
    scale = d.get('Масштаб', '').replace('1:', '1:').replace('000000', ' 000 000').replace('200000', '200 000')
    series = d.get('Серии карт', '')
    year = int(r['pub_year']) if pd.notna(r['pub_year']) else (int(yr_page.group(1)) if yr_page else None)
    who = (', '.join(auth[:-1]) + (', and ' if len(auth) > 1 else '') + auth[-1]) if auth else \
        ((', '.join(eds) + (' (Eds.)' if len(eds) > 1 else ' (Ed.)')) if eds else (org(comp) or 'VSEGEI'))
    ref = (f'{who}: {title} [{english(title, scale, series)}], {org(comp) or "VSEGEI"}, '
           f'{BASE}/maps/{n}, {year} (in Russian).') if ok else ''
    rows.append(dict(src_id=r['src_id'], src_sheet=r['src_sheet'], node=n, record_ok=ok, title=title,
                     sheets_on_map=on, compiler=comp, authors='; '.join(auth), editors='; '.join(eds), series=series,
                     scale=scale, year=year, page_year=yr_page.group(1) if yr_page else '', reference=ref))
R = pd.DataFrame(rows)
R.to_csv(f'{OUT}/ru_sheet_refs.csv', index=False)
with open(f'{OUT}/ru_sheet_refs.ris', 'w', encoding='utf-8') as w:
    for x in R[R['record_ok']].itertuples():
        w.write('TY  - MAP\n')
        for a in (x.authors.split('; ') if x.authors else []):
            w.write(f'AU  - {a}\n')
        for e in (x.editors.split('; ') if x.editors and not x.authors else []):
            w.write(f'A2  - {e}\n')
        w.write(f'TI  - {english(x.title, x.scale, x.series)}\nT2  - {x.title}\nPY  - {x.year}\n'
                f'PB  - {org(x.compiler) or "VSEGEI"}\nLA  - ru\nUR  - {BASE}/maps/{x.node}\nN1  - ArcSurf sheet {x.src_sheet}\nER  - \n')
print(f'records verified: {R.record_ok.sum()} of {len(R)}; with authors {(R.authors != "").sum()}, '
      f'with editors {(R.editors != "").sum()}; page year differs from release year: '
      f'{((R.page_year != "") & (R.page_year != R.year.astype(str))).sum()}')
print('without a verified record:', R.loc[~R.record_ok, 'src_sheet'].tolist()[:60])
