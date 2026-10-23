"""Which CMYK raster sheets have legend fills sampled in the wrong colour space? jpg_to_polygons classifies the
ICC-converted image (load_rgb); legend tools before 2026-10-02 sampled PIL's naive CMYK->RGB. Per sheet: the
median distance of face pixels to their nearest legend fill, and the share within dE 14, under both
conversions. A legend that fits the naive conversion clearly better was sampled naive and is mismatched.
usage: audit_cmyk_legends.py <sheet> [...]"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jpg_to_polygons import load_rgb, to_lab  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
WK = '/albedo/work/user/hlantuit/arctic_surficial'
SC = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga'
for s in sys.argv[1:]:
    f = sorted(glob.glob(f'{SC}/{s}/*.jp*g'), key=os.path.getsize)[-1]
    fit = json.load(open(f'{WK}/work/jpgvec/{s}.json'))
    P = np.array([c['snapped'] for c in fit['corners']], float)
    x0, y0 = P.min(0); x1, y1 = P.max(0)
    dx, dy = (x1 - x0) * 0.08, (y1 - y0) * 0.08
    box = (int(x0 + dx), int(y0 + dy), int(x1 - dx), int(y1 - dy))
    L = pd.read_csv(f'{WK}/sources/legend_{s}.csv', dtype=str, keep_default_na=False)
    fills = list(dict.fromkeys(L.fill.str.lower()))
    cl = to_lab(np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in fills], np.uint8)[None])[0]
    out = []
    for name, rgb in (('icc', load_rgb(f)), ('naive', np.asarray(Image.open(f).convert('RGB')))):
        sub = ndi.median_filter(rgb[box[1]:box[3], box[0]:box[2]], size=(5, 5, 1))[::8, ::8]
        lab = to_lab(sub).reshape(-1, 3)
        lab = lab[lab[:, 0] >= 38]
        d = np.sqrt(((lab[:, None, :] - cl[None]) ** 2).sum(-1)).min(1)
        out.append(f'{name}: median {np.median(d):5.1f} dE, within 14 {np.mean(d <= 14):5.1%}')
    print(f'{s:22s} ' + ' | '.join(out), flush=True)
