"""Survey of the VSEGEI 1:2.5M Quaternary map PDF (Quart_2500.pdf, 740 MB vector):
page geometry, text labels (unit indices + graticule degree labels with positions),
fill-colour population, and long thin strokes that may be the graticule.
Writes work/q2500/survey.json and text.parquet, prints a summary."""
import collections
import json
import os
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402,F401  (before pymupdf: GLIBCXX)
import pandas as pd  # noqa: E402
import pymupdf  # noqa: E402

PDF = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/russia_hunt/Quart_2500.pdf'
OUT = '/albedo/work/user/hlantuit/arctic_surficial/work/q2500'
os.makedirs(OUT, exist_ok=True)


def hexc(c):
    return '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) if c else None


doc = pymupdf.open(PDF)
print('pages', len(doc), [tuple(round(v) for v in p.rect) for p in doc][:5], flush=True)
page = doc[0]
# text: every span with bbox
rows = []
for b in page.get_text('dict')['blocks']:
    for l in b.get('lines', []):
        for s in l['spans']:
            t = s['text'].strip()
            if t:
                x0, y0, x1, y1 = s['bbox']
                rows.append(dict(t=t, x0=x0, y0=y0, x1=x1, y1=y1, size=round(s['size'], 1), font=s['font'], color=s['color']))
tx = pd.DataFrame(rows)
tx.to_parquet(f'{OUT}/text.parquet')
deg = tx[tx.t.str.contains(r'^\d{1,3}\s*°', regex=True)]
print('text spans', len(tx), '| degree-like', len(deg), deg.t.value_counts().head(30).to_dict(), flush=True)
print('font sizes', tx['size'].value_counts().head(12).to_dict())
print('sample index-like', tx[tx.t.str.match(r'^[a-z]{1,4}[A-Z]{1,3}')].t.value_counts().head(40).to_dict(), flush=True)
# drawings
dr = page.get_drawings()
fills = collections.Counter()
strokes = collections.Counter()
long_lines = []
for i, d in enumerate(dr):
    r = d['rect']
    if d.get('fill') is not None:
        fills[hexc(d['fill'])] += 1
    if d.get('color') is not None and d.get('fill') is None:
        key = (hexc(d['color']), round(d.get('width') or 0, 2))
        strokes[key] += 1
        if max(r.width, r.height) > 0.25 * max(page.rect.width, page.rect.height):
            long_lines.append(dict(i=i, color=key[0], width=key[1], x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1, n_items=len(d['items'])))
print('drawings', len(dr), '| fill colours', len(fills), fills.most_common(15), flush=True)
print('stroke (colour,width) top', strokes.most_common(15))
ll = pd.DataFrame(long_lines)
print('long strokes', len(ll), ll.groupby(['color', 'width']).size().sort_values(ascending=False).head(10).to_dict() if len(ll) else {})
json.dump(dict(page=list(page.rect), n_text=len(tx), n_draw=len(dr), fills=fills.most_common(400),
               strokes=[[list(k), v] for k, v in strokes.most_common(60)], long=long_lines[:2000]),
          open(f'{OUT}/survey.json', 'w'))
# preview
pix = page.get_pixmap(matrix=pymupdf.Matrix(1500 / page.rect.width, 1500 / page.rect.width))
pix.save(f'{OUT}/preview.png')
print('saved preview', pix.width, pix.height)
