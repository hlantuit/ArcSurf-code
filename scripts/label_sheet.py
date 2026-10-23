"""Label crops of line-map regions (from line_to_polygons.py <prefix>_regions.json):
(a) numbered contact sheets for reading by a person or a multimodal language model, (b) a tesseract first guess per
crop (OCR env), written to <prefix>_labels_ocr.csv.
usage: label_sheet.py <image> <prefix> [--per 40] [--first N]"""
import argparse
import json
import subprocess

import numpy as np
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
TESS = '/albedo/work/user/hlantuit/conda_envs/ocr/bin/tesseract'
ap = argparse.ArgumentParser()
ap.add_argument('image'); ap.add_argument('prefix')
ap.add_argument('--per', type=int, default=40); ap.add_argument('--first', type=int, default=0)
a = ap.parse_args()
im = Image.open(a.image).convert('RGB')
R = json.load(open(a.prefix + '_regions.json'))
regs = [r for r in R['regions'] if r['label_box'] and r.get('water_frac', 0) < 0.5]
if a.first:
    regs = regs[:a.first]
rows = []
crops = []
for r in regs:
    x0, y0, x1, y1 = r['label_box']
    p = 12
    c = im.crop((x0 - p, y0 - p, x1 + p, y1 + p))
    crops.append((r['id'], c))
    g = c.convert('L').resize((c.width * 3, c.height * 3))
    f = f'/tmp/lbl_{r["id"]}.png'
    g.save(f)
    out = subprocess.run([TESS, f, '-', '--psm', '7', '-c', 'tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'],
                         capture_output=True, text=True).stdout.strip()
    rows.append((r['id'], out))
import csv  # noqa: E402
with open(a.prefix + '_labels_ocr.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['id', 'ocr']); w.writerows(rows)
# contact sheets: grid of crops with their id
for s in range(0, len(crops), a.per):
    part = crops[s:s + a.per]
    cw, ch = 260, 120
    cols = 5
    sheet = Image.new('RGB', (cols * cw, ((len(part) + cols - 1) // cols) * ch), 'white')
    d = ImageDraw.Draw(sheet)
    for i, (rid, c) in enumerate(part):
        c = c.copy(); c.thumbnail((cw - 10, ch - 26))
        x, y = (i % cols) * cw, (i // cols) * ch
        sheet.paste(c, (x + 5, y + 22))
        d.text((x + 5, y + 4), f'#{rid}  ocr:{dict(rows).get(rid, "")}', fill=(200, 0, 0))
    sheet.save(f'{a.prefix}_sheet_{s // a.per:03d}.png')
print('crops', len(crops), 'sheets', (len(crops) + a.per - 1) // a.per)
