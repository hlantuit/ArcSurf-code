"""Coverage class grid only (no plot): the coverage_map.py grid of the CURRENT work/tiles (finest source
class per 2.5 km cell) written to out/coverage_class_<tag>.tif, for gap lists between merges.
Band 2 = 1 where the polygon that set the cell's class is water (hclass H): OSM land polygons include inland
lakes, and a lake that only the 1:5M map draws would otherwise count as a >= 1:2.5M gap.
usage: SURF_DOMAIN=domain coverage_grid.py <tag>"""
import glob
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from affine import Affine  # noqa: E402
import surflib as S  # noqa: E402
import coverage_map as CM  # noqa: E402

def one_w(f):
    import geopandas as gpd
    import rasterio.features as rf
    g = gpd.read_parquet(f, columns=['src_id', 'scale_den', 'hclass', 'geometry'])
    g['cls'] = [CM.cls_of(v) for v in g['scale_den']]
    x0, y0, x1, y1 = g.total_bounds
    c0, r0 = int(np.floor((x0 - CM.GX0) / CM.RES)), int(np.floor((CM.GY1 - y1) / CM.RES))
    c1, r1 = int(np.ceil((x1 - CM.GX0) / CM.RES)), int(np.ceil((CM.GY1 - y0) / CM.RES))
    tf = Affine(CM.RES, 0, CM.GX0 + c0 * CM.RES, 0, -CM.RES, CM.GY1 - r0 * CM.RES)
    order = sorted(range(len(g)), key=lambda i: -CM.CID[g['cls'].iat[i]] if g['cls'].iat[i] != 'unmapped' else -99)
    shp = (r1 - r0, c1 - c0)
    arr = rf.rasterize(((g.geometry.iat[i], CM.CID[g['cls'].iat[i]]) for i in order), out_shape=shp, transform=tf,
                       fill=0, dtype='uint8')
    wat = rf.rasterize(((g.geometry.iat[i], 2 if g['hclass'].iat[i] == 'H' else 1) for i in order), out_shape=shp,
                       transform=tf, fill=0, dtype='uint8')
    return None, (r0, c0, arr, wat)


if __name__ == '__main__':
    tag = sys.argv[1]
    files = sorted(glob.glob(f'{S.WORK}/tiles/*.parquet'))
    with Pool(32) as p:
        res = p.map(one_w, files)
    grid = np.zeros((CM.NR, CM.NC), np.uint8)
    water = np.zeros((CM.NR, CM.NC), np.uint8)
    for _, (r0, c0, arr, wat) in res:
        h, w = arr.shape
        rs, cs = max(r0, 0), max(c0, 0)
        sl = (slice(rs - r0, min(h, CM.NR - r0)), slice(cs - c0, min(w, CM.NC - c0)))
        sub, subw = arr[sl], wat[sl]
        tgt = grid[rs:rs + sub.shape[0], cs:cs + sub.shape[1]]
        tgw = water[rs:rs + sub.shape[0], cs:cs + sub.shape[1]]
        np.copyto(tgt, sub, where=sub > 0)
        np.copyto(tgw, (subw == 2).astype(np.uint8), where=sub > 0)
    with rasterio.open(f'{S.OUT}/coverage_class_{tag}.tif', 'w', driver='GTiff', height=CM.NR, width=CM.NC, count=2,
                       dtype='uint8', crs=S.CRS, transform=Affine(CM.RES, 0, CM.GX0, 0, -CM.RES, CM.GY1),
                       compress='deflate') as dst:
        dst.write(grid, 1)
        dst.write(water, 2)
        dst.update_tags(classes=';'.join(f'{i + 1}={c[0]}' for i, c in enumerate(CM.CLASSES)))
    print('tiles', len(files), 'cells by class', {CM.CLASSES[k - 1][0]: int((grid == k).sum()) for k in range(1, 7)})
