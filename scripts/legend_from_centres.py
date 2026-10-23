"""Legend CSV for a scanned sheet from known swatch centres (when box detection fails).
usage: legend_from_centres.py <jpg> <units.csv> <out legend.csv> <x_left_top> <y_top> <x_left_bottom> <y_bottom> <box_w> [note]
units.csv: yc,xoff,index,description_ru,hclass,hclass2,texture,note. Box left edge interpolated
linearly in y between the two given points (scan skew); the sample = median of non-dark pixels in
the box interior (+-28 px in y, 15 px in from the box sides), shifted by xoff (split boxes)."""
import sys

import numpy as np
import pandas as pd
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
jpg, units, out = sys.argv[1:4]
xl0, y0, xl1, y1, bw = (int(v) for v in sys.argv[4:9])
note = sys.argv[9] if len(sys.argv) > 9 else ''
from jpg_to_polygons import load_rgb   # CMYK scans through their ICC profile, as the extraction sees them
im = load_rgb(jpg).astype(int)
u = pd.read_csv(units, dtype={'xoff': int}, keep_default_na=False)
rows = []
for k, r in u.iterrows():
    yc = int(r.yc)
    xl = xl0 + (xl1 - xl0) * (yc - y0) / (y1 - y0)
    cx = int(xl + bw / 2 + r.xoff)
    half = int(bw / 2 - 15) if r.xoff == 0 else int(abs(r.xoff) - 15)
    w = im[yc - 28:yc + 28, cx - half:cx + half].reshape(-1, 3)
    w = w[w.mean(axis=1) >= 55]
    m = np.median(w, axis=0).astype(int)
    rows.append(dict(k=k, fill='#%02x%02x%02x' % tuple(m), index=r['index'], description_ru=r.description_ru,
                     hclass=r.hclass, hclass2=r.hclass2, texture=r.texture, ice_rich='', note=r.note))
t = pd.DataFrame(rows)
t.loc[0, 'note'] = note + ('; ' if note else '') + str(t.loc[0, 'note'])
t.to_csv(out, index=False)
print(' '.join(f"{a}:{b}" for a, b in zip(t['index'], t.fill)))
