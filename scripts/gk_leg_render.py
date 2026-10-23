"""Render a VSEGEI sheet's main legend for transcription, given its swatch size and the
row / column the swatches sit on (found by tallying fill sizes). Writes
<pdf>_L<k>.png strips (upright text) and <pdf>_fills.json (fills in READING order).
  upright legend (w > h): swatches in a column at x = LINE; strips down the column.
  sideways legend (h > w): swatches in a row at y = LINE; page rotation 90 -> text on the
  low-y side, image rotated -90, reading order = increasing x; otherwise (0 / 270) text
  on the high-y side, rotated +90, reading order = decreasing x (R-43, R-44, S-51 ...).
usage: gk_leg_render.py <pdf> <w> <h> <line> [--flip]"""
import io
import json
import sys

import numpy  # noqa: F401
sys.path.append('/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402

pdf, w, h, line = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
flip = '--flip' in sys.argv
pg = pymupdf.open(pdf)[0]
rot = pg.rotation
pg.set_rotation(0)
sw = [d for d in pg.get_drawings() if d.get('fill') and abs(d['rect'].width - w) < 1.5 and abs(d['rect'].height - h) < 1.5]
hexc = lambda c: '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c)   # noqa: E731
upright = w > h
if upright:
    sw = [d for d in sw if abs(d['rect'].x0 - line) < 4]
    sw.sort(key=lambda d: d['rect'].y0)
else:
    sw = [d for d in sw if abs(d['rect'].y0 - line) < 4]
    inc = (rot == 90) != flip
    sw.sort(key=lambda d: d['rect'].x0 * (1 if inc else -1))
fills, seen = [], set()
for d in sw:
    k = (round(d['rect'].x0), round(d['rect'].y0))
    if k in seen:
        continue
    seen.add(k)
    fills.append(hexc(d['fill']))
json.dump(fills, open(pdf[:-4] + '_fills.json', 'w'))
k = 0
if upright:
    y0, y1 = min(d['rect'].y0 for d in sw) - 8, max(d['rect'].y1 for d in sw) + 8
    y = y0
    while y < y1:
        c = pymupdf.Rect(line - 6, y, min(line + 440, pg.rect.width), min(y + 420, y1))
        pg.get_pixmap(matrix=pymupdf.Matrix(2.4, 2.4), clip=c).save(f'{pdf[:-4]}_L{k}.png'); k += 1; y += 410
else:
    x0, x1 = min(d['rect'].x0 for d in sw) - 8, max(d['rect'].x1 for d in sw) + 8
    text_low = (rot == 90) != flip
    cy = (line - 340, line + h + 5) if text_low else (line - 5, line + 340)
    # strips in reading order
    starts = []
    x = x0
    while x < x1:
        starts.append(x); x += 410
    if not text_low:
        starts = starts[::-1]
    for xs in starts:
        c = pymupdf.Rect(xs, cy[0], min(xs + 420, x1), cy[1])
        im = Image.open(io.BytesIO(pg.get_pixmap(matrix=pymupdf.Matrix(2.4, 2.4), clip=c).tobytes('png')))
        im.rotate(-90 if text_low else 90, expand=True).save(f'{pdf[:-4]}_L{k}.png'); k += 1
print(pdf, 'rot', rot, 'swatches', len(fills), 'strips', k)
print(fills)
