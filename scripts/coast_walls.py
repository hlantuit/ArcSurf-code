#!/usr/bin/env python
"""OSM land mask in the page-pixel window of a scanned line map, for line_to_polygons.py --osm-land.

Black line maps (GSC 1970s-80s Open Files: OF 1275 Bathurst Island, OF 48, OF 635) draw the coast as a THIN line next
to a light sea screen. The bold-line filter (--thick) drops it, and the screen's tone is too close to the paper to
detect, so the sea joins every coastal unit into one region. Here the coast comes from OSM instead: page px ->
EPSG:6931 through the sheet's corner fit (jpg_to_polygons.corner_fit: projection + thin-plate spline pinned at the
four graticule corners, optional interior ties), land tested on a raster of work/land_amap.gpkg (layer 'land',
OSM land clipped to the build domain, no inland lakes).

Output: <out>.npy = np.packbits of the boolean land mask (window shape, row-major), and <out>.json (window, shape,
fit report). OSM and the map's own coastline differ by generalisation (~100-200 m at 1:250k); the merge clips every
source to the same OSM land, so slivers between the two lines do not reach the product.
usage: coast_walls.py <image> <x0,y0,x1,y1> "TL;TR;BR;BL" <lon0,lat0,lon1,lat1> <datum EPSG> <out_prefix>
       [--ties lon,lat,x,y;...] [--step 4] [--res 40]"""
import argparse
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402  (first: PROJ fix)
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import rasterio.features as rf  # noqa: E402
from affine import Affine  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
import jpg_to_polygons as J  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('image'); ap.add_argument('window'); ap.add_argument('corners'); ap.add_argument('lonlat')
ap.add_argument('datum', type=int); ap.add_argument('out')
ap.add_argument('--ties', default='')
ap.add_argument('--step', type=int, default=4, help='page-px sampling step of the transform (mask upsampled)')
ap.add_argument('--res', type=float, default=40.0, help='m, raster resolution of the OSM land mask')
a = ap.parse_args()
x0, y0, x1, y1 = map(int, a.window.split(','))
pts = [tuple(map(float, c.split(','))) for c in a.corners.split(';')]
lon0, lat0, lon1, lat1 = map(float, a.lonlat.split(','))
ties = [tuple(float(v) for v in t.split(',')) for t in a.ties.split(';') if t.strip()] or None
tf, fit = J.corner_fit(pts, lon0, lat0, lon1, lat1, a.datum, ties)
print('fit', {k: fit[k] for k in ('projection', 'rms_m', 'max_res_m', 'm_per_px')}, flush=True)

# page grid (every `step` px, cell centres) -> map coordinates
xs = np.arange(x0, x1, a.step) + a.step / 2
ys = np.arange(y0, y1, a.step) + a.step / 2
X, Y = np.meshgrid(xs, ys)
E = np.empty(X.shape); N = np.empty(X.shape)
for r in range(0, X.shape[0], 200):                 # rows in chunks: the spline evaluates all points at once
    q = tf(np.c_[X[r:r + 200].ravel(), Y[r:r + 200].ravel()])
    E[r:r + 200] = q[:, 0].reshape(-1, X.shape[1]); N[r:r + 200] = q[:, 1].reshape(-1, X.shape[1])
# OSM land rasterised on a map grid covering the window's footprint
e0, e1, n0, n1 = E.min() - 2000, E.max() + 2000, N.min() - 2000, N.max() + 2000
land = gpd.read_file(f'{S.WORK}/land_amap.gpkg', layer='land', bbox=(e0, n0, e1, n1))
W_ = int(np.ceil((e1 - e0) / a.res)); H_ = int(np.ceil((n1 - n0) / a.res))
tr = Affine(a.res, 0, e0, 0, -a.res, n1)
geoms = [g for g in shapely.make_valid(land.geometry.values) if g is not None and not g.is_empty]
L = rf.rasterize([(g, 1) for g in geoms], out_shape=(H_, W_), transform=tr, dtype=np.uint8) if geoms else np.zeros((H_, W_), np.uint8)
ci = np.clip(((E - e0) / a.res).astype(int), 0, W_ - 1)
ri = np.clip(((n1 - N) / a.res).astype(int), 0, H_ - 1)
m = L[ri, ci].astype(bool)
# back to the full window (nearest), then a light opening/closing against single-cell noise
full = np.repeat(np.repeat(m, a.step, 0), a.step, 1)[:y1 - y0, :x1 - x0]
full = ndi.binary_closing(ndi.binary_opening(full, iterations=1), iterations=1)
np.save(a.out + '.npy', np.packbits(full))
json.dump(dict(window=[x0, y0, x1, y1], shape=list(full.shape), land_frac=round(float(full.mean()), 4),
               fit={k: (v if not isinstance(v, (np.floating,)) else float(v)) for k, v in fit.items()},
               corners=a.corners, lonlat=a.lonlat, datum=a.datum, n_osm_polygons=len(geoms)),
          open(a.out + '.json', 'w'), indent=1, default=float)
print('land fraction of window', round(float(full.mean()), 3), '| shape', full.shape, flush=True)
