#!/usr/bin/env python
"""IRYP v2 yedoma polygons diced on the merge's 100 km tile grid, for the `yedoma` column of the
merged product (Hugues 2026-10-04: keep each source's own class and description, e.g. 'loessoid',
and add a column saying whether the ground is yedoma according to Strauss et al.).

Input: Database of Ice-Rich Yedoma Permafrost v2 (IRYP v2; Strauss et al. 2021, Front. Earth Sci.;
data PANGAEA doi:10.1594/PANGAEA.940078), layer IRYP_v2_yedoma_confidence (confidence =
confirmed / likely / uncertain). IRYP maps north of 60 N only.
Overlaps between confidence classes are resolved confirmed > likely > uncertain.
Writes work/iryp_by_tile.gpkg, layer 'iryp_by_tile' (conf, tile_id, geometry; EPSG:6931),
read by merge_tiles.split_by_yedoma()."""
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

IRYP = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/russia/iryp/IRYP_v2_yedoma_confidence.shp'
OUT = f'{S.WORK}/iryp_by_tile.gpkg'
g = gpd.read_file(IRYP).to_crs(S.CRS)
g['conf'] = g['confidence'].astype(str).str.strip().str.lower()
done = shapely.Polygon()
classes = []
for c in ('confirmed', 'likely', 'uncertain'):
    u = shapely.make_valid(shapely.union_all(shapely.make_valid(g[g.conf == c].geometry.values)))
    u = shapely.make_valid(shapely.difference(u, done))
    done = shapely.union_all([done, u])
    classes.append((c, u))
    print(c, round(u.area / 1e6), 'km2', flush=True)
T = 100_000.0
dice = []
for c, geom in classes:
    parts = shapely.get_parts(geom)
    parts = parts[[p.geom_type in ('Polygon', 'MultiPolygon') for p in parts]]
    tree = shapely.STRtree(parts)
    x0, y0, x1, y1 = geom.bounds
    for x in np.arange(np.floor(x0 / T) * T, x1, T):
        for y in np.arange(np.floor(y0 / T) * T, y1, T):
            b = shapely.box(x, y, x + T, y + T)
            idx = tree.query(b, predicate='intersects')
            if len(idx):
                gg = shapely.make_valid(shapely.intersection(shapely.union_all(parts[idx]), b))
                if not gg.is_empty and gg.area > 1.0:
                    dice.append(dict(conf=c, tile_id=f'{int(x // 1000):+06d}_{int(y // 1000):+06d}', geometry=gg))
    print('diced', c, len(dice), flush=True)
gpd.GeoDataFrame(dice, crs=S.CRS).to_file(OUT, layer='iryp_by_tile', driver='GPKG')
print('wrote', OUT, len(dice), 'tile pieces')
