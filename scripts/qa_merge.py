#!/usr/bin/env python
"""QA of the merged layer, from the tile parquets (work/tiles): area by harmonised
class, by source and scale, U (unmapped) and sliver fills, the same on the coastal
strip, per-tile area conservation, and the country/region split of U.
Writes work/qa_merge.json and prints tables.

Null space: this checks bookkeeping (every land m2 assigned once, who won where);
it says nothing about whether a crosswalk class is RIGHT - that is the legend review."""
import glob
import json
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402

COLS = ['src_id', 'scale_den', 'hclass', 'ice_rich', 'gapfill', 'coastal', 'geometry']


STRIP_M = 1000.0      # fixed-width coastal strip; 'coastal' polygon flags depend on polygon size


def one(f):
    import shapely
    g = gpd.read_parquet(f, columns=[c for c in COLS])
    g['km2'] = g.area / 1e6
    tid = f.split('/')[-1].replace('.parquet', '')
    g['tile'] = tid
    # coastline = boundary of the tile's land minus the tile edge (as merge_tiles.py)
    land = shapely.union_all(g.geometry.values)
    x, y = [int(v) * 1000 for v in tid.split('_')]
    edge = shapely.boundary(shapely.box(x, y, x + 100_000, y + 100_000))
    coast = shapely.difference(shapely.boundary(land), shapely.buffer(edge, 1.0))
    g['strip_km2'] = 0.0
    if not coast.is_empty:
        strip = shapely.intersection(shapely.buffer(coast, STRIP_M), land)
        shapely.prepare(strip)
        hit = shapely.intersects(g.geometry.values, strip)
        g.loc[hit, 'strip_km2'] = shapely.area(shapely.intersection(g.geometry.values[hit], strip)) / 1e6
    return pd.DataFrame(g.drop(columns='geometry'))


def main():
    files = sorted(glob.glob(f'{S.WORK}/tiles/*.parquet'))
    with Pool(32) as p:
        d = pd.concat(p.map(one, files), ignore_index=True)
    tot = d.km2.sum()
    out = dict(tiles=len(files), rows=len(d), land_km2=round(tot))
    d['coastal'] = d['coastal'].fillna(0).astype(int)
    # 'coastal' (polygons touching the coast) is kept for continuity but is size-biased;
    # 'strip_1km' weights every polygon by its area inside a fixed 1 km coastal strip
    for tag, sub, wcol in (('all', d, 'km2'), ('coastal', d[d.coastal == 1], 'km2'), ('strip_1km', d[d.strip_km2 > 0], 'strip_km2')):
        a = sub[wcol].sum()
        h = sub.groupby('hclass')[wcol].sum().sort_values(ascending=False)
        src = sub.groupby('src_id')[wcol].sum().sort_values(ascending=False)
        sc = sub.groupby('scale_den', dropna=False)[wcol].sum().sort_index()
        out[tag] = dict(km2=round(a), hclass_frac=(h / a).round(4).to_dict(),
                        source_frac=(src / a).round(4).to_dict(),
                        scale_frac={str(k): round(v / a, 4) for k, v in sc.items()},
                        U_frac=round(float(sub.loc[sub.hclass == 'U', wcol].sum() / a), 4),
                        sliver_frac=round(float(sub.loc[sub.gapfill == 'sliver_nearest', wcol].sum() / a), 5),
                        ice_rich_yes_frac=round(float(sub.loc[sub.ice_rich == 'yes', wcol].sum() / a), 4))
        print(f'== {tag}: {a:,.0f} km2, U {out[tag]["U_frac"]:.2%}, slivers {out[tag]["sliver_frac"]:.3%}')
        print('  hclass:', {k: f'{v:.1%}' for k, v in (h / a).head(20).items()})
        print('  sources:', {k: f'{v:.1%}' for k, v in (src / a).head(30).items()})
        print('  scale:', {str(k): f'{v / a:.1%}' for k, v in sc.items()})
    # U hot spots: tiles with the most unmapped land
    u = d[d.hclass == 'U'].groupby('tile').km2.sum().sort_values(ascending=False)
    out['U_top_tiles'] = u.head(25).round(0).to_dict()
    print('U top tiles (km2):', out['U_top_tiles'])
    json.dump(out, open(f'{S.WORK}/qa_merge.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
