#!/usr/bin/env python
"""Display footprints of the Russian sheets in the release geometry (Fig. 3): for every sheet of ru_vsegei_pdf,
ru_vsegei_preview and ru_bryant_vsegei1m, the land it holds in the map, simplified by 500 m and dissolved.
usage: ru_sheet_footprints.py DISSOLVE_DIR OUT.gpkg"""
import glob
import sys
from multiprocessing import Pool

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

DD, OUT = sys.argv[1:3]
SRC = ('ru_vsegei_pdf', 'ru_vsegei_preview', 'ru_bryant_vsegei1m')


def one(f):
    g = gpd.read_parquet(f, columns=['src_id', 'src_sheet', 'area_km2', 'geometry'])
    g = g[g['src_id'].astype(str).isin(SRC)]
    if g.empty:
        return []
    out = []
    for (s, sh), sub in g.groupby(['src_id', 'src_sheet']):
        geom = shapely.union_all(shapely.simplify(sub.geometry.values, 500.0), grid_size=100.0)
        out.append((s, sh, float(sub['area_km2'].sum()), shapely.to_wkb(geom)))
    return out


def main():
    files = sorted(glob.glob(f'{DD}/final/*.parquet'))
    parts = {}
    with Pool(4) as pool:
        for res in pool.imap_unordered(one, files, chunksize=8):
            for s, sh, a, wkb in res:
                parts.setdefault((s, sh), [0.0, []])
                parts[(s, sh)][0] += a
                parts[(s, sh)][1].append(shapely.from_wkb(wkb))
    rows = [dict(src_id=s, src_sheet=sh, area_km2=a, geometry=shapely.union_all(np.array(gs), grid_size=100.0))
            for (s, sh), (a, gs) in parts.items()]
    gdf = gpd.GeoDataFrame(pd.DataFrame(rows), geometry='geometry', crs='EPSG:6931')
    gdf.to_file(OUT, driver='GPKG')
    print(len(gdf), 'sheets;', gdf.groupby('src_id').size().to_dict())


if __name__ == '__main__':
    main()
