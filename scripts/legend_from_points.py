"""Legend CSV from explicit swatch positions (matrix legends). usage:
legend_from_points.py <jpg> <units.csv: x,y,w,index,description_ru,hclass,hclass2,texture,note> <out.csv> [note]
Colour = median of non-dark pixels in a (w-20) x 40 px window centred on x,y."""
import sys

import numpy as np
import pandas as pd
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
from jpg_to_polygons import load_rgb   # CMYK scans through their ICC profile, as the extraction sees them
im = load_rgb(sys.argv[1]).astype(int)
u = pd.read_csv(sys.argv[2], keep_default_na=False)
rows = []
for k, r in u.iterrows():
    hw = int(r.w) // 2 - 10
    win = im[int(r.y) - 20:int(r.y) + 20, int(r.x) - hw:int(r.x) + hw].reshape(-1, 3)
    win = win[win.mean(axis=1) >= 55]
    m = np.median(win, axis=0).astype(int)
    rows.append(dict(k=k, fill='#%02x%02x%02x' % tuple(m), index=r['index'], description_ru=r.description_ru,
                     hclass=r.hclass, hclass2=r.hclass2, texture=r.texture, ice_rich='', note=r.note))
t = pd.DataFrame(rows)
if len(sys.argv) > 4:
    t.loc[0, 'note'] = sys.argv[4] + '; ' + str(t.loc[0, 'note'])
t.to_csv(sys.argv[3], index=False)
print(' '.join(f'{a}:{b}' for a, b in zip(t['index'], t.fill)))
