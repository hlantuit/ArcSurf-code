"""Approximate inner-frame corners of a raster map sheet from the extent of LEGEND-coloured
pixels (dE<12 to any legend fill) inside x < xmax: top/bottom rows = first/last rows with
>40% coloured, left/right x on those rows. Prints TL;TR;BR;BL for run_rast.sh (the extractor
snaps within 15 px).  usage: rast_corners.py <image> <legend.csv> <xmax> [ymax]"""
import sys
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np, pandas as pd
import jpg_to_polygons as J
img, leg, xmax = sys.argv[1], sys.argv[2], int(sys.argv[3])
a = J.load_rgb(img)
ymax = int(sys.argv[4]) if len(sys.argv) > 4 else a.shape[0]
s = 4
sub = a[:ymax:s, :xmax:s]
lab = J.to_lab(sub)
f = pd.read_csv(leg)['fill'].unique()
fl = J.to_lab(np.array([J.hex2rgb(x) for x in f])[None])[0]
m = np.zeros(lab.shape[:2], bool)
for c in fl:
    m |= np.sqrt(((lab - c) ** 2).sum(-1)) < 12
# largest dense block of rows
fr = m.mean(1)
rows = np.where(fr > 0.4 * fr.max())[0]
# keep the longest run
runs = np.split(rows, np.where(np.diff(rows) > 5)[0] + 1); r = max(runs, key=len)
y0, y1 = r[0], r[-1]
def xr(ya, yb):
    # columns coloured in >50% of a 60-row band: stray margin symbols are sparse
    cf = m[ya:yb].mean(0)
    xs = np.where(cf > 0.5)[0]
    sp = np.split(xs, np.where(np.diff(xs) > 6)[0] + 1); sp = max(sp, key=len)
    return sp[0], sp[-1]
(a0, a1), (b0, b1) = xr(y0 + 1, y0 + 16), xr(y1 - 15, y1)
print(f"{a0*s},{y0*s};{a1*s},{y0*s};{b1*s},{y1*s};{b0*s},{y1*s}")
