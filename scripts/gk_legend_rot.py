"""Legend reader aid for ROTATED VSEGEI sheet PDFs (map drawn sideways: legend boxes stored
as tall rects, e.g. 20x40 pt, and arranged in ROWS). Picks the most common tall rect size
(w < h) with >= 6 members sharing a y0 row, sorts the swatches along the row (reading
order after rotating the image), writes <pdf>_mainleg.json and renders the legend band
rotated upright as strips <pdf>_strip<k>.png. Rotation direction: --ccw (default) or --cw.
usage: gk_legend_rot.py <pdf> [--cw] [--band 330]"""
import argparse
import collections
import json
import sys

import numpy  # noqa: F401
sys.path.append('/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402
import io  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('pdf'); ap.add_argument('--cw', action='store_true'); ap.add_argument('--band', type=float, default=330)
a = ap.parse_args()
pg = pymupdf.open(a.pdf)[0]
pg.set_rotation(0)
fills = [d for d in pg.get_drawings() if d.get('fill')]
hexc = lambda c: '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c)   # noqa: E731
tall = [d for d in fills if 10 <= d['rect'].width <= 40 and d['rect'].height > 1.4 * d['rect'].width and d['rect'].height <= 60]
sizes = collections.Counter((round(d['rect'].width), round(d['rect'].height)) for d in tall)
best = []
for (w, h), _ in sizes.most_common(5):
    c = [d for d in tall if abs(d['rect'].width - w) <= 1.5 and abs(d['rect'].height - h) <= 1.5]
    rows = collections.Counter(round(d['rect'].y0 / 3) for d in c)
    keep = {r for r, k in rows.items() if k >= 6}
    c = [d for d in c if round(d['rect'].y0 / 3) in keep]
    if len(c) > len(best):
        best = c
# reading order: after rotating ccw, a row read top->bottom = increasing x ... rows ordered by y
best = sorted(best, key=lambda d: (round(d['rect'].y0 / 3) * (-1 if not a.cw else 1), d['rect'].x0 * (1 if not a.cw else -1)))
out, seen = [], set()
for d in best:
    k = (round(d['rect'].x0), round(d['rect'].y0))
    if k in seen:
        continue
    seen.add(k)
    out.append(dict(i=len(out), fill=hexc(d['fill']), x=round(d['rect'].x0), y=round(d['rect'].y0)))
json.dump(dict(rotated=True, swatches=out), open(a.pdf[:-4] + '_mainleg.json', 'w'))
k = 0
for ry in sorted({o['y'] for o in out}, reverse=not a.cw):
    row = [o for o in out if abs(o['y'] - ry) < 4]
    if len(row) < 3:
        continue
    x0, x1 = min(o['x'] for o in row) - 10, max(o['x'] for o in row) + 30
    y0 = ry - (a.band if not a.cw else 0) + (0 if not a.cw else 0)
    clip = pymupdf.Rect(x0, ry - 5, x1, ry + a.band) if not a.cw else pymupdf.Rect(x0, ry - a.band, x1, ry + 45)
    xs = x0
    while xs < x1:
        c2 = pymupdf.Rect(xs, clip.y0, min(xs + 420, x1), clip.y1)
        im = Image.open(io.BytesIO(pg.get_pixmap(matrix=pymupdf.Matrix(2.5, 2.5), clip=c2).tobytes('png')))
        im.rotate(90 if not a.cw else -90, expand=True).save(f'{a.pdf[:-4]}_strip{k}.png')
        k += 1; xs += 410
print(a.pdf, 'rotated swatches', len(out), 'rows', len({o['y'] for o in out}), 'strips', k)
