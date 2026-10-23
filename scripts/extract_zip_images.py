"""Extract the embedded scan image of every PDF inside a GSC sheet's OSTR zip(s) to PNG next
to the zip (<pdf stem>.png, the largest image on page 1), plus a 1400 px thumbnail in
work/gscvec/zipthumbs/. The PDFs are single-image wrappers of the scans (A1849a mg1 =
13861 x 11933), so the image is the full-resolution raster, not a re-render.
usage: extract_zip_images.py <label> [label ...]"""
import glob
import os
import sys
import zipfile

import numpy  # noqa: F401  (conda libstdc++ before pymupdf from pylib)
from PIL import Image

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
sys.path.append(f'{ROOT}/pylib')
import pymupdf  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
os.makedirs(f'{ROOT}/work/gscvec/zipthumbs', exist_ok=True)
for lab in sys.argv[1:]:
    d = f'{ROOT}/raw/canada/gsc_scans/{lab}'
    for zf in glob.glob(f'{d}/*.zip'):
        z = zipfile.ZipFile(zf)
        for n in z.namelist():
            if not n.lower().endswith('.pdf'):
                continue
            out = f'{d}/{os.path.basename(n)[:-4]}.png'
            if not os.path.exists(out):
                doc = pymupdf.open(stream=z.read(n), filetype='pdf')
                imgs = doc[0].get_images()
                if not imgs:
                    print(lab, n, 'no image (vector PDF)'); continue
                x = max(imgs, key=lambda t: t[2] * t[3])
                pix = pymupdf.Pixmap(doc, x[0])
                if pix.n - pix.alpha >= 4:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                pix.save(out)
            im = Image.open(out)
            print(lab, os.path.basename(out), im.size, flush=True)
            im = im.convert('RGB'); im.thumbnail((1400, 1400))
            im.save(f'{ROOT}/work/gscvec/zipthumbs/{lab}__{os.path.basename(out)}')
