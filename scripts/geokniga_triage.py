"""Triage downloaded geokniga sheets (raw/russia_geokniga[_1m]/<sheet>/*): per file, VECTOR
PDF (page has >= 2000 vector drawing ops and no page-size image), RASTER PDF (one big image),
or JPG with its pixel size. A sheet is usable when it has a vector PDF, or a raster of
>= 6000 px on the long side (1:200k 300 dpi scans are 6000-12000 px; the 2000-px previews
failed). Writes work/geokniga_triage[_1m].csv and prints per-sheet verdicts.
usage: geokniga_triage.py [1m]"""
import glob
import os
import sys

import numpy  # noqa: F401  (conda libstdc++ before pymupdf)
from PIL import Image
import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
sys.path.append(f'{ROOT}/pylib')
import pymupdf  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
tag = '_1m' if len(sys.argv) > 1 and sys.argv[1] == '1m' else ''
RAW = f'/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga{tag}'
rows = []
for d in sorted(glob.glob(f'{RAW}/*/')):
    sheet = os.path.basename(d.rstrip('/'))
    for f in sorted(glob.glob(f'{d}*')):
        ext = f.rsplit('.', 1)[-1].lower()
        r = dict(sheet=sheet, file=os.path.basename(f), mb=round(os.path.getsize(f) / 1e6, 1))
        try:
            if ext == 'pdf':
                doc = pymupdf.open(f)
                pg = doc[0]
                imgs = pg.get_images()
                big = max([x[2] * x[3] for x in imgs] + [0])
                nd = len(pg.get_drawings()) if len(imgs) < 3 else 0
                r.update(pages=len(doc), n_draw=nd, img_px=big,
                         kind='vector_pdf' if nd >= 2000 else ('raster_pdf' if big else 'pdf_other'),
                         long_px=int(max([max(x[2], x[3]) for x in imgs] + [0])))
            elif ext in ('jpg', 'jpeg', 'png', 'tif', 'tiff', 'djvu'):
                w, h = Image.open(f).size
                r.update(kind='raster', long_px=max(w, h), w=w, h=h)
            else:
                r.update(kind='other')
        except Exception as e:
            r.update(kind='error', err=str(e)[:80])
        rows.append(r)
t = pd.DataFrame(rows)
t.to_csv(f'{ROOT}/work/geokniga_triage{tag}.csv', index=False)
t['long_px'] = t.get('long_px', 0).fillna(0)


def verdict(g):
    if (g.kind == 'vector_pdf').any():
        return 'vector'
    if ((g.kind.isin(['raster', 'raster_pdf'])) & (g.long_px >= 6000)).any():
        return 'raster_full'
    if ((g.kind.isin(['raster', 'raster_pdf'])) & (g.long_px >= 4000)).any():
        return 'raster_mid'
    return 'preview_only'


v = t.groupby('sheet').apply(verdict)
v.rename('verdict').to_csv(f'{ROOT}/work/geokniga_verdict{tag}.csv')
print(v.value_counts().to_dict())
for k in ['vector', 'raster_full', 'raster_mid', 'preview_only']:
    print(k, ':', ' '.join(v[v == k].index))
