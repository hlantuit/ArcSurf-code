"""All legend swatches (size w x h) in an x band [x, x+150] (upright legends with indented
columns), y-ordered, white duplicates skipped. usage: gk_fills_band.py <pdf> <x> [w h]"""
import json, sys
import numpy  # noqa
sys.path.append('/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf
pdf, x = sys.argv[1], float(sys.argv[2]); w, h = (float(sys.argv[3]), float(sys.argv[4])) if len(sys.argv) > 4 else (40, 20)
p = pymupdf.open(pdf)[0]; p.set_rotation(0)
seen = {}
for d in sorted([d for d in p.get_drawings() if d.get('fill') and abs(d['rect'].width - w) < 1.5 and abs(d['rect'].height - h) < 1.5 and x - 5 < d['rect'].x0 < x + 150], key=lambda d: d['rect'].y0):
    k = round(d['rect'].y0); c = '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in d['fill'])
    if k in seen and (c == '#ffffff' or seen[k] != '#ffffff'):
        continue
    seen[k] = c
print(len(seen)); print(json.dumps(list(seen.values())))
