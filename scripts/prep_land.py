#!/usr/bin/env python
"""
Land mask for the build: OSM land polygons (split, EPSG:4326) inside the AMAP
area, reprojected to EPSG:6931, plus a 100 km tile index.

The OSM 'split' product has ARTIFICIAL cut lines (polygons are diced into
<=100k-vertex pieces), so land piece boundaries are not all coastline. The
coastline is therefore NOT derived here; merge_tiles.py dissolves land per tile
before taking its boundary.

Outputs  work/land_amap.gpkg  layers: land (pieces), tiles (id, geometry, land_km2)
Licence: OSM land polygons (c) OpenStreetMap contributors, ODbL 1.0.
"""
import os
import sys
import time

import numpy as np
import geopandas as gpd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

OSM = f'{S.RAW}/osm_land/land-polygons-split-4326/land_polygons.shp'
AMAP = f'{S.RAW}/amap/amaplim_lam_poly.shp'
OUTP = f'{S.WORK}/land_amap.gpkg'
TILE = 100_000.0


def main():
    t0 = time.time()
    amap_geom = S.amap_geom()      # the build domain (AMAP, or AMAP + Obu with SURF_DOMAIN=domain)
    # lat-lon prefilter: AMAP reaches ~51N (James Bay); the permafrost domain ~42N (Russian Far East)
    lat0 = 40 if os.environ.get('SURF_DOMAIN') == 'domain' else 45
    land = pyogrio.read_dataframe(OSM, bbox=(-180, lat0, 180, 90))
    print(f'read {len(land)} OSM pieces north of {lat0}N in {time.time()-t0:.0f}s')
    land = land.to_crs(S.CRS)
    shapely.prepare(amap_geom)
    inside = shapely.intersects(amap_geom, land.geometry.values)
    land = land[inside].copy()
    within = shapely.within(land.geometry.values, amap_geom)
    edge = ~within
    land.loc[edge, 'geometry'] = shapely.intersection(land.geometry.values[edge], amap_geom)
    land = S.polygons_only(land[['geometry']])
    print(f'{len(land)} land pieces in AMAP, {land.area.sum()/1e6:,.0f} km2 '
          f'({int(edge.sum())} clipped at the AMAP edge) {time.time()-t0:.0f}s')

    x0, y0, x1, y1 = land.total_bounds
    xs = np.arange(np.floor(x0 / TILE) * TILE, x1, TILE)
    ys = np.arange(np.floor(y0 / TILE) * TILE, y1, TILE)
    boxes = [shapely.box(x, y, x + TILE, y + TILE) for x in xs for y in ys]
    ids = [f'{int(x//1000):+06d}_{int(y//1000):+06d}' for x in xs for y in ys]
    tiles = gpd.GeoDataFrame({'tile_id': ids}, geometry=boxes, crs=S.CRS)
    tree = shapely.STRtree(land.geometry.values)
    ti, li = tree.query(tiles.geometry.values, predicate='intersects')
    area = np.zeros(len(tiles))
    inter = shapely.area(shapely.intersection(tiles.geometry.values[ti], land.geometry.values[li]))
    np.add.at(area, ti, inter)
    tiles['land_km2'] = area / 1e6
    tiles = tiles[tiles['land_km2'] > 0].reset_index(drop=True)
    print(f'{len(tiles)} tiles with land; tile land sum {tiles.land_km2.sum():,.0f} km2')

    if os.path.exists(OUTP):
        os.remove(OUTP)
    land.to_file(OUTP, layer='land', driver='GPKG')
    tiles.to_file(OUTP, layer='tiles', driver='GPKG')
    print(f'wrote {OUTP} in {time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
