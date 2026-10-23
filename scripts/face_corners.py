"""Approximate map-face corners of a clean colour scan (digital-era GSC sheets): the face is the
largest connected region of coloured pixels (saturation > 40) inside a search box; its extreme
points in x+y / x-y give TL, TR, BR, BL. Feed the result to --corners (jpg_to_polygons snaps
within 15 px) and check the corner residual.
usage: face_corners.py <img> x0,y0,x1,y1   (search box, excludes legend column and index maps)"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

Image.MAX_IMAGE_PIXELS = None
x0, y0, x1, y1 = (int(v) for v in sys.argv[2].split(','))
im = Image.open(sys.argv[1]).convert('RGB').crop((x0, y0, x1, y1))
f = 4
small = np.asarray(im.reduce(f)).astype(int)
sat = small.max(axis=2) - small.min(axis=2)
m = ndi.binary_closing(sat > 40, iterations=3)
lab, n = ndi.label(m)
k = np.argmax(np.bincount(lab.ravel())[1:]) + 1
yy, xx = np.nonzero(lab == k)
pts = {'TL': np.argmin(xx + yy), 'TR': np.argmax(xx - yy), 'BR': np.argmax(xx + yy), 'BL': np.argmin(xx - yy)}
out = []
for kk in ('TL', 'TR', 'BR', 'BL'):
    i = pts[kk]
    out.append(f'{x0 + xx[i] * f},{y0 + yy[i] * f}')
print(';'.join(out))
