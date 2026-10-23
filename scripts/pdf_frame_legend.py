#!/usr/bin/env python
"""Find the legend swatches of a vector Quaternary-map PDF, layout-independently.

Swatches = small filled rectangles of one common size, stacked in aligned columns.
Candidates are grouped by (width, height) rounded to 1 pt; the size class with the
most members wins, keeping only columns (same x0 within 2 pt) of >= 5 swatches.
Rectangles inside the map frame (if --frame given as x0,y0,x1,y1 in pt) are ignored.
Writes <pdf>_legend.json (order, fill, bbox per swatch, sorted by column then y) and
renders each legend column at 3x for reading the labels (label text is outlines).

usage: pdf_frame_legend.py <file.pdf> [--page N] [--frame x0,y0,x1,y1] [--label-width 330]
"""
import argparse
import collections
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402


def hexc(c):
    return '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) if c else None


ap = argparse.ArgumentParser()
ap.add_argument('pdf')
ap.add_argument('--page', type=int, default=0)
ap.add_argument('--frame')
ap.add_argument('--label-width', type=float, default=330)
ap.add_argument('--region', help='only swatches inside x0,y0,x1,y1 (pt), e.g. the map-legend column')
a = ap.parse_args()
page = pymupdf.open(a.pdf)[a.page]
fr = pymupdf.Rect(*map(float, a.frame.split(','))) if a.frame else None
rg = pymupdf.Rect(*map(float, a.region.split(','))) if a.region else None
cand = []
for i, d in enumerate(page.get_drawings()):
    c = hexc(d.get('fill'))
    r = d['rect']
    if c in (None, '#ffffff', '#231f20', '#000000'):
        continue
    if not (10 < r.width < 70 and 5 < r.height < 40):
        continue
    if fr is not None and fr.contains(r):
        continue
    if rg is not None and not rg.contains(r):
        continue
    if len(d['items']) > 6:          # a swatch is a simple rectangle (1 're' or 4-5 lines)
        continue
    cand.append(dict(order=i, fill=c, bbox=[round(v, 1) for v in r], w=round(r.width), h=round(r.height), x0=r.x0))
size = collections.Counter((c['w'], c['h']) for c in cand)
if not size:
    sys.exit('no swatch candidates')
(w0, h0), _ = size.most_common(1)[0]
sw = [c for c in cand if abs(c['w'] - w0) <= 1 and abs(c['h'] - h0) <= 1]
cols = collections.defaultdict(list)
for c in sw:
    key = next((k for k in cols if abs(k - c['x0']) < 2), c['x0'])
    cols[key].append(c)
cols = {k: sorted(v, key=lambda c: c['bbox'][1]) for k, v in cols.items() if len(v) >= 5}
out = []
for ci, (k, v) in enumerate(sorted(cols.items())):
    for c in v:
        out.append(dict(k=len(out), col=ci, order=c['order'], fill=c['fill'], bbox=c['bbox']))
print(f'swatch size {w0}x{h0} pt; {len(cols)} column(s); {len(out)} swatches')
for s in out:
    print(s['k'], s['col'], s['fill'], s['bbox'])
json.dump({'swatches': out}, open(a.pdf.replace('.pdf', f'_p{a.page}_legend.json'), 'w'), indent=1)
# renders: per column, split into chunks of ~20 swatches for legibility
for ci in sorted({s['col'] for s in out}):
    col = [s for s in out if s['col'] == ci]
    for j in range(0, len(col), 20):
        chunk = col[j:j + 20]
        x0 = chunk[0]['bbox'][0] - 4
        clip = pymupdf.Rect(x0, chunk[0]['bbox'][1] - 4, x0 + a.label_width, chunk[-1]['bbox'][3] + 4)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip)
        o = a.pdf.replace('.pdf', f'_p{a.page}_legend_c{ci}_{j // 20}.png')
        pix.save(o)
        print('saved', o, pix.width, pix.height)
