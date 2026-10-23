"""List the embedded images of scanned-map PDFs (size, format, colour space) and optionally extract the largest
image of page 1 at native resolution.
usage: pdf_images.py <pdf> [...] [--extract <outdir>]"""
import os
import sys

from PIL import Image  # noqa: F401  (PIL before fitz: GLIBCXX clash on Albedo)
import fitz

args = sys.argv[1:]
out = None
if '--extract' in args:
    i = args.index('--extract'); out = args[i + 1]; args = args[:i] + args[i + 2:]
for f in args:
    d = fitz.open(f)
    pg = d[0]
    ims = pg.get_images(full=True)
    info = []
    best = None
    for im in ims:
        x = d.extract_image(im[0])
        info.append(f"{x['width']}x{x['height']} {x['ext']} cs={x.get('colorspace')} bpc={x.get('bpc')}")
        if best is None or x['width'] * x['height'] > best['width'] * best['height']:
            best = x
    print(f"{os.path.basename(f)}: pages {len(d)}, page {pg.rect.width:.0f}x{pg.rect.height:.0f} pt, images {len(ims)}: {info[:3]}")
    if out and best:
        os.makedirs(out, exist_ok=True)
        p = os.path.join(out, os.path.splitext(os.path.basename(f))[0] + '.' + best['ext'])
        open(p, 'wb').write(best['image'])
        print('  ->', p)
