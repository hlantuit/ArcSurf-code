#!/usr/bin/env python
"""Exact extent numbers for the manuscript (H. Lantuit 2026-10-07: "be very precise on the extent chosen, AMAP + Obu
permafrost"). The merged polygons cover the domain land exactly (polygon area = land area, merge 43), so summing
their areas inside / outside the AMAP polygon gives the two parts of the domain without a second land mask.

  per polygon: area inside the AMAP area polygon (exact intersection on tiles that cross the AMAP limit),
  permafrost zone (pf_zone, Obu et al. 2019), country (Natural Earth admin-0 of the representative point, 25 km
  tolerance at the coast), source.
  -> work/essd_tables_m43/extent_by_zone_country.csv, extent_summary.txt (also printed)
Also: whether the Faroe Islands lie inside the AMAP polygon.
usage: domain_extent_stats.py [TILES_DIR]"""
import glob
import os
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
TD = sys.argv[1] if len(sys.argv) > 1 else f'{ROOT}/work/final_m43'
O = os.environ.get('ESSD_OUT', f'{ROOT}/work/essd_tables_m43')
AMAP_SHP = f'{ROOT}/raw/amap/amaplim_lam_poly.shp'
NE = f'{ROOT}/raw/naturalearth/ne_10m_admin_0_countries.shp'
TILE = 100_000
G = {}


def init():
    a = gpd.read_file(AMAP_SHP).to_crs(6931)
    G['amap'] = shapely.make_valid(shapely.union_all(a.geometry.values))
    shapely.prepare(G['amap'])
    ne = gpd.read_file(NE)
    # clip to >= 30N first: Antarctica turns inside-out in the north-polar projection and swallowed every point
    # (first run, 2026-10-07: all area assigned to ATA)
    ne['geometry'] = shapely.intersection(shapely.make_valid(ne.geometry.values), shapely.box(-180, 30, 180, 90))
    ne = ne[~ne.geometry.is_empty].to_crs(6931)
    key = 'ADM0_A3' if 'ADM0_A3' in ne else 'ISO_A3'
    G['ne'] = ne[[key, 'geometry']].rename(columns={key: 'country'})
    G['ne_tree'] = shapely.STRtree(G['ne'].geometry.values)


def country_of(pts):
    """admin-0 code of each point; points off the Natural Earth coast take the nearest country within 25 km"""
    out = np.full(len(pts), '', dtype=object)
    idx_p, idx_c = G['ne_tree'].query(pts, predicate='within')
    out[idx_p] = G['ne']['country'].values[idx_c]
    miss = np.flatnonzero(out == '')
    if len(miss):
        ip, ic = G['ne_tree'].query_nearest(pts[miss], max_distance=25_000)
        out[miss[ip]] = G['ne']['country'].values[ic]
    out[out == ''] = 'none'
    return out


def one(f):
    tid = os.path.basename(f)[:-8]
    tx, ty = (int(v) * 1000 for v in tid.split('_'))
    g = gpd.read_parquet(f, columns=['geometry', 'pf_zone', 'src_id', 'hclass'])
    if g.empty:
        return None
    q = shapely.force_2d(g.geometry.values)
    area = shapely.area(q)
    box = shapely.box(tx, ty, tx + TILE, ty + TILE)
    amap = G['amap']
    if amap.contains(box):
        ina = area
    elif not amap.intersects(box):
        ina = np.zeros(len(g))
    else:
        piece = shapely.intersection(amap, box)
        ina = shapely.area(shapely.intersection(q, piece))
    d = pd.DataFrame({'pf_zone': g['pf_zone'].astype('string').fillna('none').to_numpy(dtype=object),
                      'country': country_of(shapely.point_on_surface(q)),
                      'faroe': (g['src_id'].astype('string').fillna('') == 'fo_us_lendisslog').to_numpy(),
                      'area_km2': area / 1e6, 'in_amap_km2': ina / 1e6})
    return d.groupby(['pf_zone', 'country', 'faroe'], as_index=False)[['area_km2', 'in_amap_km2']].sum()


def main():
    os.makedirs(O, exist_ok=True)
    files = sorted(glob.glob(f'{TD}/*.parquet'))
    with Pool(int(os.environ.get('SLURM_CPUS_PER_TASK', '8')), initializer=init) as pool:
        parts = [p for p in pool.imap_unordered(one, files, chunksize=4) if p is not None]
    t = pd.concat(parts).groupby(['pf_zone', 'country', 'faroe'], as_index=False)[['area_km2', 'in_amap_km2']].sum()
    t['outside_amap_km2'] = t['area_km2'] - t['in_amap_km2']
    t.to_csv(f'{O}/extent_by_zone_country.csv', index=False)
    lines = []
    pr = lambda s: (print(s, flush=True), lines.append(s))              # noqa: E731
    tot, ina = t['area_km2'].sum(), t['in_amap_km2'].sum()
    pr(f'{TD}: {len(files)} tiles')
    pr(f'domain land {tot:,.0f} km2; inside AMAP {ina:,.0f} ({100 * ina / tot:.2f} %); outside AMAP '
       f'{tot - ina:,.0f} ({100 * (tot - ina) / tot:.2f} %)')
    z = t.groupby('pf_zone')[['area_km2', 'in_amap_km2', 'outside_amap_km2']].sum()
    pr('by permafrost zone (km2):\n' + z.round(0).to_string())
    c = t.groupby('country')[['area_km2', 'in_amap_km2', 'outside_amap_km2']].sum().sort_values('area_km2',
                                                                                               ascending=False)
    pr('by country (km2):\n' + c.round(0).to_string())
    pf = t[t['pf_zone'] != 'none']
    pr(f'permafrost zones total {pf["area_km2"].sum():,.0f} km2, of which outside AMAP '
       f'{pf["outside_amap_km2"].sum():,.0f}')
    outside_nopf = t[(t['pf_zone'] == 'none')]['outside_amap_km2'].sum()
    pr(f'outside AMAP but no permafrost zone (should be ~0 apart from the Faroes / edge effects): {outside_nopf:,.1f} km2')
    fo = t[t['faroe']]
    pr(f'Faroe proxy polygons: {fo["area_km2"].sum():,.1f} km2, of which inside AMAP {fo["in_amap_km2"].sum():,.1f}')
    init()
    fo_pt = gpd.GeoSeries([shapely.Point(-6.9, 62.0)], crs=4326).to_crs(6931).values[0]
    pr(f'Torshavn area point inside the AMAP polygon: {G["amap"].contains(fo_pt)}')
    open(f'{O}/extent_summary.txt', 'w').write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
