#!/usr/bin/env python
"""Triage every downloaded geokniga PDF: vector or raster? One CSV row per page.
usage: pdf_triage.py <root_dir> <out.csv>"""
import csv
import glob
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402

root, out = sys.argv[1], sys.argv[2]
rows = []
for f in sorted(glob.glob(f'{root}/**/*.pdf', recursive=True)):
    try:
        doc = pymupdf.open(f)
    except Exception as e:
        rows.append(dict(sheet=os.path.basename(os.path.dirname(f)), file=os.path.basename(f), page='', error=repr(e)[:100]))
        continue
    for pno, page in enumerate(doc):
        imgs = page.get_images()
        big = 0
        for im in imgs:
            try:
                w, h = im[2], im[3]
                big += (w * h > 4e6)
            except Exception:
                pass
        try:
            dr = page.get_drawings()
        except Exception:
            dr = []
        fills = sum(1 for d in dr if d.get('fill') is not None)
        cols = len({tuple(round(v, 3) for v in d['fill']) for d in dr if d.get('fill') is not None})
        kind = 'vector' if fills > 500 and big == 0 else ('raster' if big else 'unclear')
        rows.append(dict(sheet=os.path.basename(os.path.dirname(f)), file=os.path.basename(f), page=pno,
                         w_mm=round(page.rect.width / 72 * 25.4), h_mm=round(page.rect.height / 72 * 25.4),
                         n_images=len(imgs), big_images=big, n_fills=fills, n_colours=cols, kind=kind,
                         producer=doc.metadata.get('producer', ''), error=''))
        print(rows[-1], flush=True)
with open(out, 'w', newline='', encoding='utf-8') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['sheet'])
    w.writeheader()
    w.writerows(rows)
print('wrote', out, len(rows))
