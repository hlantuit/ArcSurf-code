"""Main-legend reader aid for VSEGEI 1:1M / 1:200k vector PDFs: the main Quaternary legend
is the swatch column(s) right of (or left of) the LARGEST map frame. Finds that frame (largest
filled rect-like drawing with many fills inside), collects small filled rectangles (8-60 pt)
in a band beside it, keeps the band with most swatches, sorts swatches by y, writes
<pdf>_mainleg.json [{i, fill, y, x}] and renders the band as strips (<pdf>_strip<k>.png,
~420 pt tall each) for transcription.
usage: gk_legend_strips.py <pdf> [--side right|left] [--width 430]"""
import argparse
import collections
import json
import sys

import numpy  # noqa: F401
sys.path.append('/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402


def hexc(c):
    return '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) if c else None


ap = argparse.ArgumentParser()
ap.add_argument('pdf'); ap.add_argument('--sheet'); ap.add_argument('--side', default='auto'); ap.add_argument('--width', type=float, default=430); ap.add_argument('--anywhere', action='store_true')
a = ap.parse_args()
pg = pymupdf.open(a.pdf)[0]
dr = pg.get_drawings()
# map frame: the bbox with the most filled drawings inside, among large rects
fills = [d for d in dr if d.get('fill')]
cand = sorted({(round(d['rect'].x0), round(d['rect'].y0), round(d['rect'].x1), round(d['rect'].y1))
               for d in dr if d['rect'].width > pg.rect.width * 0.25 and d['rect'].height > pg.rect.height * 0.25},
              key=lambda r: -(r[2] - r[0]) * (r[3] - r[1]))[:12]
import math
ratio = None
if a.sheet:
    sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
    import re
    import nomen
    lo0, la0, lo1, la1 = nomen.frame(re.sub(r'_g\d$', '', a.sheet).replace('(', '').replace(')', ''))
    ratio = (lo1 - lo0) * math.cos(math.radians((la0 + la1) / 2)) / (la1 - la0)
best, bs = None, -1e9
cand = cand or [(round(pg.rect.x0), round(pg.rect.y0), round(pg.rect.x1), round(pg.rect.y1))]
for r in cand:
    R = pymupdf.Rect(*r)
    n = sum(1 for d in fills if R.contains(d['rect']) and d['rect'].width < R.width * 0.5)
    sc = math.log(n + 1) - (3 * abs(math.log((R.width / R.height) / ratio)) if ratio else 0)
    if sc > bs:
        best, bs = R, sc
fr = best
sw = [d for d in fills if 8 <= d['rect'].width <= 60 and 5 <= d['rect'].height <= 40 and not fr.intersects(d['rect'])
      and fr.y0 - 40 <= d['rect'].y0 <= fr.y1 + 40]
res = {}
for side in (['right', 'left'] if a.side == 'auto' else [a.side]):
    if side == 'right':
        band = pymupdf.Rect(fr.x1 + 2, fr.y0 - 40, fr.x1 + 2 + a.width, fr.y1 + 40)
    else:
        band = pymupdf.Rect(fr.x0 - 2 - a.width, fr.y0 - 40, fr.x0 - 2, fr.y1 + 40)
    s = [d for d in sw if band.contains(d['rect'])]
    # keep the most common swatch size (the legend boxes), +-2 pt
    sz = collections.Counter((round(d['rect'].width), round(d['rect'].height)) for d in s).most_common(1)
    if sz:
        w, h = sz[0][0]
        s = [d for d in s if abs(d['rect'].width - w) <= 2 and abs(d['rect'].height - h) <= 2]
    res[side] = (band, s)
side = max(res, key=lambda k: len(res[k][1]))
band, s = res[side]
if a.anywhere or len(s) < 8:
    # legend not beside the frame (below it, rotated page...): the swatch population =
    # the most common small rect size anywhere outside the frame, in columns of >= 6
    allsw = [d for d in fills if 14 <= d['rect'].width <= 60 and 8 <= d['rect'].height <= 40
             and (a.anywhere or not fr.intersects(d['rect']))]
    sizes = collections.Counter((round(d['rect'].width), round(d['rect'].height)) for d in allsw)
    best_s = []
    for (w, h), n in sizes.most_common(6):
        cand_ = [d for d in allsw if abs(d['rect'].width - w) <= 1.5 and abs(d['rect'].height - h) <= 1.5]
        cols = collections.Counter(round(d['rect'].x0 / 3) for d in cand_)
        keep = set()
        for c, k in cols.items():
            if k < 6:
                continue
            ys = sorted(d['rect'].y0 for d in cand_ if round(d['rect'].x0 / 3) == c)
            gaps = [y2 - y1 for y1, y2 in zip(ys, ys[1:]) if y2 - y1 > 1]
            # legend columns: regular vertical pitch (median gap < 3 swatch heights)
            if gaps and sorted(gaps)[len(gaps) // 2] < 3 * h:
                keep.add(c)
        cand_ = [d for d in cand_ if round(d['rect'].x0 / 3) in keep]
        if len(cand_) > len(best_s):
            best_s = cand_
    if len(best_s) > len(s):
        s, side = best_s, 'anywhere'
s = sorted(s, key=lambda d: (round(d['rect'].x0 / 40), round(d['rect'].y0), d['rect'].x0))
# de-duplicate swatches drawn twice (fill + pattern)
out, seen = [], set()
for d in s:
    k = (round(d['rect'].x0), round(d['rect'].y0))
    if k in seen:
        continue
    seen.add(k)
    out.append(dict(i=len(out), fill=hexc(d['fill']), x=round(d['rect'].x0), y=round(d['rect'].y0)))
json.dump(dict(frame=[fr.x0, fr.y0, fr.x1, fr.y1], side=side, swatches=out), open(a.pdf[:-4] + '_mainleg.json', 'w'))
if out and side == 'anywhere':
    # one strip per swatch column
    k = 0
    for cx in sorted({o['x'] for o in out}):
        col = [o for o in out if abs(o['x'] - cx) < 4]
        if len(col) < 3:
            continue
        y0, y1 = min(o['y'] for o in col) - 10, max(o['y'] for o in col) + 40
        y = y0
        while y < y1:
            clip = pymupdf.Rect(cx - 6, y, min(cx - 6 + a.width, pg.rect.width), min(y + 420, y1))
            pg.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=clip).save(f'{a.pdf[:-4]}_strip{k}.png')
            k += 1; y += 410
elif out:
    x0 = min(o['x'] for o in out) - 6
    y0, y1 = min(o['y'] for o in out) - 10, max(o['y'] for o in out) + 40
    k, y = 0, y0
    while y < y1:
        clip = pymupdf.Rect(x0, y, min(x0 + a.width, pg.rect.width), min(y + 420, y1))
        pg.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=clip).save(f'{a.pdf[:-4]}_strip{k}.png')
        k += 1; y += 410
print(a.pdf, 'frame', [round(v) for v in fr], 'side', side, 'swatches', len(out), 'strips', k if out else 0)
