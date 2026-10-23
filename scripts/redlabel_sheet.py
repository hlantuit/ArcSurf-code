"""Contact sheets of EVERY label cluster of a redline_to_polygons.py (or line_to_polygons.py) run, not only the
largest per region: each tile renders the red ink only (or, with --ink black:T, the ink darker than T) (black on white, so the black base-map lettering does not clutter it),
numbered '<region>.<k>' = region id and cluster index within that region (order of all_label_boxes).
Writes <prefix>_redlbl_NNN.png and <prefix>_redlbl.csv (region, k, box). Transcriptions go to a labels CSV with
columns region,k,label.
usage: redlabel_sheet.py <image> <prefix> [--per 48] [--red-t 35]"""
import argparse
import csv
import json

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser()
ap.add_argument('image'); ap.add_argument('prefix')
ap.add_argument('--per', type=int, default=48); ap.add_argument('--red-t', type=int, default=35)
ap.add_argument('--ink', default='red', help="'red' (red overlay maps) or 'black:T' (gray < T, black line maps)")
ap.add_argument('--skip-regions', default='', help='region ids (comma list) left out of the sheets, e.g. the unmapped '
                'background of a partly mapped sheet (OF 189): its clusters are written to the CSV with skip=1')
a = ap.parse_args()
SKIP = {int(v) for v in a.skip_regions.split(',') if v.strip()}
im = Image.open(a.image).convert('RGB')
R = json.load(open(a.prefix + '_regions.json'))
items = [(r['id'], k, b) for r in R['regions'] for k, b in enumerate(r['all_label_boxes'])]
with open(a.prefix + '_redlbl.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['region', 'k', 'x0', 'y0', 'x1', 'y1'])
    for rid, k, b in items:
        w.writerow([rid, k, *b])
TW, TH, COLS = 230, 150, 6
items = [it for it in items if it[0] not in SKIP]
for s in range(0, len(items), a.per):
    chunk = items[s:s + a.per]
    rows = (len(chunk) + COLS - 1) // COLS
    sheet = Image.new('RGB', (COLS * TW, rows * TH), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (rid, k, (x0, y0, x1, y1)) in enumerate(chunk):
        p = 10
        c = np.asarray(im.crop((x0 - p, y0 - p, x1 + p, y1 + p))).astype(np.int16)
        if a.ink == 'red':
            red = (c[..., 0] - np.maximum(c[..., 1], c[..., 2]) > a.red_t) & (c[..., 0] > 110)
        else:
            red = c.mean(-1) < int(a.ink.split(':')[1])
        t = Image.fromarray(np.where(red, 0, 255).astype(np.uint8)).convert('RGB')
        sc = min((TW - 10) / t.width, (TH - 26) / t.height, 2.0)
        t = t.resize((max(1, int(t.width * sc)), max(1, int(t.height * sc))))
        cx, cy = (i % COLS) * TW, (i // COLS) * TH
        sheet.paste(t, (cx + 5, cy + 22))
        d.rectangle([cx, cy, cx + TW - 1, cy + TH - 1], outline=(180, 180, 180))
        d.text((cx + 4, cy + 3), f'{rid}.{k}', fill=(0, 0, 255))
    sheet.save(f'{a.prefix}_redlbl_{s // a.per:03d}.png')
print(len(items), 'clusters on', (len(items) + a.per - 1) // a.per, 'sheets')
