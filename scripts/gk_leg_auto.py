"""Auto-locate the main legend swatch line of a VSEGEI sheet PDF and render it via
gk_leg_render.py: among fill-rect sizes of 14-45 pt, the (size, line) with the most swatches
on one column (w>h, same x0) or row (h>w, same y0), >= 10 swatches.
usage: gk_leg_auto.py <pdf> [...]"""
import collections
import subprocess
import sys

import numpy  # noqa: F401
sys.path.append('/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402

for pdf in sys.argv[1:]:
    pg = pymupdf.open(pdf)[0]
    pg.set_rotation(0)
    fills = [d['rect'] for d in pg.get_drawings() if d.get('fill')]
    best = (0, None)
    sizes = collections.Counter((round(r.width), round(r.height)) for r in fills if 14 <= r.width <= 45 and 8 <= r.height <= 45 and r.width != r.height)
    for (w, h), n in sizes.most_common(10):
        rs = [r for r in fills if abs(r.width - w) < 1.5 and abs(r.height - h) < 1.5]
        key = (lambda r: round(r.x0 / 3) * 3) if w > h else (lambda r: round(r.y0 / 3) * 3)
        line, k = collections.Counter(key(r) for r in rs).most_common(1)[0]
        if k > best[0]:
            best = (k, (w, h, line))
    if best[0] < 10:
        print(pdf, 'NO LEGEND LINE FOUND', best); continue
    w, h, line = best[1]
    r = subprocess.run(['/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python', '/albedo/work/user/hlantuit/arctic_surficial/scripts/gk_leg_render.py',
                        pdf, str(w), str(h), str(line)], capture_output=True, text=True)
    print(pdf, 'size', (w, h), 'line', line, '|', r.stdout.strip().splitlines()[0] if r.stdout else r.stderr[-200:], flush=True)
