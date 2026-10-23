#!/usr/bin/env python
"""
Legend for a sheet HALF printed without one (A1871a/A1867a north halves: mg1/mn02 have no
legend and a darker print), calibrated across the seam with the extracted other half:
points 40-110 m inside the legend-less half along the shared parallel get their print colour;
the unit of the extracted half 250 m across the seam (past its ~212 m frame-band strip; pair
distance 290-360 m) is the label. Colours
are clustered (k-means in Lab); each cluster gets its majority unit, with purity and n.
Same map, same authors: units continue across the seam, so the pairing is the measurement.
usage: seam_calibrate.py <north_image> <corners TL;TR;BR;BL> <lon0,lat0,lon1,lat1> <south_label>
       <south_legend.csv> <out_legend.csv> [k]"""
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import jpg_to_polygons as J  # noqa: E402
import surflib as S  # noqa: E402

img, corners, ll, south, sleg, out = sys.argv[1:7]
k = int(sys.argv[7]) if len(sys.argv) > 7 else 24
TL, TR, BR, BL = [np.array([float(v) for v in c.split(',')]) for c in corners.split(';')]
lon0, lat0, lon1, lat1 = map(float, ll.split(','))
a = J.load_rgb(img)
u = gpd.read_file(f'{S.WORK}/gscvec/{south}.gpkg', layer='units').to_crs(4326)
leg = pd.read_csv(f'{S.ROOT}/sources/{sleg}')
idx_col = 'index' if 'index' in u.columns else [c for c in u.columns if c not in ('geometry',)][0]
tree = shapely.STRtree(u.geometry.values)


def px(s, t):
    """pixel at fractional frame position s (W->E), t (N->S), bilinear in the corners."""
    top = TL + s * (TR - TL); bot = BL + s * (BR - BL)
    return top + t * (bot - top)


H = abs(BL[1] - TL[1])
m_per_px = (lat1 - lat0) * 111_000 / H
rows = []
for s in np.linspace(0.005, 0.995, 4000):
    lon = lon0 + s * (lon1 - lon0)
    for d_in in (40, 70, 110):                         # metres inside the legend-less half (polygons are ~0.5 km: stay close)
        t = 1 - d_in / ((lat1 - lat0) * 111_000)
        x, y = px(s, t).round().astype(int)
        w = a[y - 1:y + 2, x - 1:x + 2].reshape(-1, 3)
        rgb = np.median(w, 0)
        if rgb.min() > 235:                            # paper / water
            continue
        lat_s = lat0 - 250 / 111_000                   # just past the extracted half's 150 m edge strip (frame line reads as a unit there)
        hit = tree.query(shapely.points(lon, lat_s), predicate='within')
        if len(hit) == 0:
            continue
        rows.append((*rgb, u.iloc[hit[0]][idx_col]))
d = pd.DataFrame(rows, columns=['r', 'g', 'b', 'unit'])
print('paired points', len(d), 'units', d.unit.value_counts().to_dict())
lab = J.to_lab(d[['r', 'g', 'b']].to_numpy(np.uint8)[None])[0]
from scipy.cluster.vq import kmeans2  # noqa: E402
np.random.seed(0)
cent, lbl = kmeans2(lab.astype(float), k, minit='++', seed=0)
d['c'] = lbl
res = []
for c, g in d.groupby('c'):
    vc = g.unit.value_counts()
    rgb = np.median(g[['r', 'g', 'b']], 0).astype(int)
    res.append(dict(cluster=c, n=len(g), fill='#%02x%02x%02x' % tuple(rgb), unit=vc.index[0], purity=round(vc.iloc[0] / len(g), 2),
                    second=(vc.index[1] if len(vc) > 1 else ''), L=round(float(cent[c][0]), 1)))
r = pd.DataFrame(res).sort_values('n', ascending=False)
print(r.to_string(index=False))
# legend: per unit, the clusters it wins with purity >= 0.6 and n >= 25 (several fills per unit allowed)
keep = r[(r.purity >= 0.6) & (r.n >= 25)]
L = leg.set_index('index')
rowsL = []
for i, x in enumerate(keep.itertuples()):
    base = L.loc[x.unit]
    rowsL.append(dict(k=i, fill=x.fill, index=x.unit, description_ru=base['description_ru'], hclass=base['hclass'], hclass2=base.get('hclass2', ''),
                      texture=base['texture'], ice_rich=base.get('ice_rich', ''),
                      note=(f'SEAM-CALIBRATED against {south}: cluster n={x.n}, purity {x.purity}' if i else
                            f'Legend-less half; fills calibrated across the seam against the extracted {south} (k-means k={k} on print colours 40-110 m inside, units 250 m across); cluster n={x.n}, purity {x.purity}')))
pd.DataFrame(rowsL).to_csv(f'{S.ROOT}/sources/{out}', index=False)
print('wrote', out, len(rowsL), 'fills for units', sorted(keep.unit.unique()), '| clusters rejected', len(r) - len(keep))
