"""Coverage map: finest source scale actually used at each location of the merged layer
(work/tiles), with product footprints outlined, to find where higher-resolution products
are missing. Writes out/coverage_map.png and out/coverage_by_country.csv.

Scale classes (denominator): <=100k, 125k-250k, 500k-600k, 1M, >=2.5M, unmapped.
'Needs finer mapping' = land whose best source is 1:500k or coarser, or none."""
import glob
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

CLASSES = [('<=1:100k', 0, 100_000, '#08306b'), ('1:125k-1:250k', 100_001, 260_000, '#2171b5'),
           ('1:500k-1:600k', 260_001, 700_000, '#fdae6b'), ('1:1M', 700_001, 1_500_000, '#f16913'),
           ('>=1:2.5M', 1_500_001, 10**9, '#a63603'), ('unmapped', None, None, '#bdbdbd')]
COUNTRY = {'ca': 'Canada', 'us': 'Alaska', 'ru': 'Russia', 'gl': 'Greenland', 'no': 'Norway', 'sj': 'Svalbard',
           'se': 'Sweden', 'fi': 'Finland', 'is': 'Iceland'}


def cls_of(s):
    if pd.isna(s):                                     # pd.NA in the Int64 column too
        return 'unmapped'
    for name, lo, hi, _ in CLASSES[:-1]:
        if lo <= s <= hi:
            return name
    return 'unmapped'


RES = 2500.0
CID = {c[0]: i + 1 for i, c in enumerate(CLASSES)}


def one(f):
    import rasterio.features as rf
    from affine import Affine
    g = gpd.read_parquet(f, columns=['src_id', 'scale_den', 'geometry'])
    g['cls'] = [cls_of(v) for v in g['scale_den']]
    g['country'] = g['src_id'].str.split('_').str[0].map(COUNTRY).fillna('unmapped')
    g['km2'] = g.area / 1e6
    area = g.groupby(['country', 'cls']).km2.sum().reset_index()
    x0, y0, x1, y1 = g.total_bounds
    c0, r0 = int(np.floor((x0 - GX0) / RES)), int(np.floor((GY1 - y1) / RES))
    c1, r1 = int(np.ceil((x1 - GX0) / RES)), int(np.ceil((GY1 - y0) / RES))
    tf = Affine(RES, 0, GX0 + c0 * RES, 0, -RES, GY1 - r0 * RES)
    # finest class wins inside a cell: burn coarse first, fine last
    order = sorted(range(len(g)), key=lambda i: -CID[g['cls'].iat[i]] if g['cls'].iat[i] != 'unmapped' else -99)
    arr = rf.rasterize(((g.geometry.iat[i], CID[g['cls'].iat[i]]) for i in order),
                       out_shape=(r1 - r0, c1 - c0), transform=tf, fill=0, dtype='uint8', all_touched=False)
    return area, (r0, c0, arr)


AMAP = gpd.read_file(S.RAW + '/amap/amaplim_lam_poly.shp').to_crs(S.CRS)
GX0, GY0, GX1, GY1 = AMAP.total_bounds
if __import__('os').environ.get('SURF_DOMAIN') == 'domain':      # permafrost-region build: grid over the domain
    GX0, GY0, GX1, GY1 = gpd.read_file(f'{S.WORK}/domain_obu_amap.gpkg', layer='domain').to_crs(S.CRS).total_bounds
NC, NR = int(np.ceil((GX1 - GX0) / RES)), int(np.ceil((GY1 - GY0) / RES))


def main():
    files = sorted(glob.glob(f'{S.WORK}/tiles/*.parquet'))
    with Pool(32) as p:
        res = p.map(one, files)
    area = pd.concat([r[0] for r in res]).groupby(['country', 'cls']).km2.sum().unstack(fill_value=0)
    area = area[[c[0] for c in CLASSES if c[0] in area.columns]]
    area.round().to_csv(f'{S.OUT}/coverage_by_country.csv')
    print(area.round(-2).to_string())
    grid = np.zeros((NR, NC), np.uint8)
    for _, (r0, c0, arr) in res:
        h, w = arr.shape
        rs, cs = max(r0, 0), max(c0, 0)
        sub = arr[rs - r0:min(h, NR - r0), cs - c0:min(w, NC - c0)]
        tgt = grid[rs:rs + sub.shape[0], cs:cs + sub.shape[1]]
        np.copyto(tgt, sub, where=sub > 0)
    # class grid as a GeoTIFF for scripts/gap_audit.py (0 = no land, 1..6 = CLASSES order, 6 = unmapped)
    import rasterio
    from affine import Affine
    with rasterio.open(f'{S.OUT}/coverage_class.tif', 'w', driver='GTiff', height=NR, width=NC, count=1, dtype='uint8',
                       crs=S.CRS, transform=Affine(RES, 0, GX0, 0, -RES, GY1), compress='deflate') as dst:
        dst.write(grid, 1)
        dst.update_tags(classes=';'.join(f'{i + 1}={c[0]}' for i, c in enumerate(CLASSES)))
    # product footprints (one outline per source)
    fps = []
    for f in sorted(glob.glob(f'{S.WORK}/xw/*.gpkg')):
        try:
            fp = gpd.read_file(f, layer='footprint')
        except Exception:
            continue
        src = f.split('/')[-1][:-5]
        fps.append(dict(src=src, geometry=shapely.simplify(shapely.union_all(fp.to_crs(S.CRS).geometry.values), 5000)))
    fps = gpd.GeoDataFrame(fps, crs=S.CRS)
    amap = AMAP

    fig = plt.figure(figsize=(18, 13), dpi=150)
    ax = fig.add_axes([0.01, 0.03, 0.66, 0.94])
    ax.set_facecolor('#eaf2f7')
    colours = {c[0]: c[3] for c in CLASSES}
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(['#eaf2f7'] + [c[3] for c in CLASSES])
    ext = (GX0, GX0 + NC * RES, GY1 - NR * RES, GY1)
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=len(CLASSES), extent=ext, interpolation='nearest')
    need = np.isin(grid, [CID['1:500k-1:600k'], CID['1:1M'], CID['>=1:2.5M'], CID['unmapped']])
    yy, xx = np.indices(grid.shape)
    stripe = need & (((xx + yy) % 10) < 2)
    ax.imshow(np.ma.masked_where(~stripe, stripe), cmap=ListedColormap(['#67000d']), extent=ext, interpolation='nearest')
    fps.boundary.plot(ax=ax, color='#111111', linewidth=0.35, alpha=0.6)
    amap.boundary.plot(ax=ax, color='#1d6a73', linewidth=0.8, linestyle='--')
    for _, r in fps.iterrows():
        if r.geometry is None or r.geometry.is_empty or r.geometry.area < 3e10:
            continue
        pt = r.geometry.representative_point()
        ax.annotate(r.src, (pt.x, pt.y), fontsize=6.5, ha='center', color='#111111',
                    bbox=dict(boxstyle='round,pad=0.15', fc='white', ec='none', alpha=0.7))
    b = amap.total_bounds
    ax.set_xlim(b[0], b[2]); ax.set_ylim(b[1], b[3]); ax.set_aspect('equal'); ax.set_axis_off()
    ax.set_title('Finest source scale used in the merged layer (run 6) - hatched: needs finer mapping (best >= 1:500k or none)', fontsize=12, loc='left')
    handles = [Patch(color=c[3], label=c[0]) for c in CLASSES] + [Patch(facecolor='none', edgecolor='#67000d', hatch='////', label='needs finer mapping'),
               Patch(facecolor='none', edgecolor='#111111', label='product footprint'), Patch(facecolor='none', edgecolor='#1d6a73', linestyle='--', label='AMAP boundary')]
    ax.legend(handles=handles, loc='lower left', fontsize=9, frameon=True)
    # bars
    bx = fig.add_axes([0.72, 0.30, 0.26, 0.50])
    a = area.drop(index='unmapped', errors='ignore')
    a = a.loc[a.sum(1).sort_values().index] / 1e6
    left = np.zeros(len(a))
    for name in a.columns:
        bx.barh(a.index, a[name], left=left, color=colours[name], label=name)
        left += a[name].values
    u = area.loc['unmapped'].sum() / 1e6 if 'unmapped' in area.index else 0
    bx.set_xlabel('land area, million km$^2$')
    bx.set_title(f'Best available scale by country (+ {u:.2f} M km$^2$ unmapped)', fontsize=10, loc='left')
    bx.spines[['top', 'right']].set_visible(False)
    fig.savefig(f'{S.OUT}/coverage_map.png')
    print('wrote', f'{S.OUT}/coverage_map.png')


if __name__ == '__main__':
    main()
