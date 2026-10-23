"""Independent check of a georeferenced raster/vector sheet against the OSM coastline:
points every 250 m along the OSM coastline inside the sheet frame; for each, distance to
the coast of the sheet's extracted units (boundary of their union) where that boundary is
within 5 km. Reports median / p75 / p90 and the share of points within 250 m.
Null space: tests the coast only (where the map's land units meet the sea); inland
distortion and legend reading are not tested. The edge of the build domain (where the land layer is
clipped) is removed from the coast. Shore points within 1 km of the sheet's 'excluded'
layer (unmapped parts, legend panels; written by jpg_to_polygons) are skipped.

usage: coast_check.py <sheet.gpkg> [<sheet.gpkg> ...]"""
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402

LAND = f'{S.WORK}/land_amap.gpkg'
DOM = f'{S.WORK}/domain_obu_amap.gpkg'
lyr = pyogrio.list_layers(LAND)[0][0]
for path in [p for p in sys.argv[1:] if not p.startswith('--')]:
    u = gpd.read_file(path, layer='units').to_crs(S.CRS)
    fr = gpd.read_file(path, layer='neatline').to_crs(S.CRS).geometry.values[0]
    inner = shapely.buffer(fr, -2000)          # stay clear of the frame edges
    land = pyogrio.read_dataframe(LAND, layer=lyr, bbox=tuple(fr.bounds))
    L = shapely.union_all(land.geometry.values)
    coast = shapely.intersection(shapely.boundary(L), inner)
    # the land layer is clipped to the build domain (AMAP + Obu permafrost): its edge is not a coast. Inland
    # sheets near the permafrost limit (Manitoba-Ontario series) were scored against it (2026-10-02)
    bb = shapely.buffer(shapely.box(*fr.bounds), 10000)
    dom = pyogrio.read_dataframe(DOM, layer='domain', bbox=tuple(bb.bounds)).to_crs(S.CRS)
    if len(dom):
        dedge = shapely.intersection(shapely.boundary(shapely.union_all(shapely.make_valid(dom.geometry.values))), bb)
        coast = shapely.difference(coast, shapely.buffer(dedge, 1000))
    if coast.is_empty:
        print(path, 'no coast in frame'); continue
    unit_edge = shapely.boundary(shapely.union_all(shapely.make_valid(u.geometry.values)))
    shapely.prepare(unit_edge)
    n = max(int(coast.length / 250), 10)
    pts = shapely.line_interpolate_point(coast, np.linspace(0, coast.length, n)) if coast.geom_type == 'LineString' else \
        shapely.points(shapely.get_coordinates(shapely.segmentize(coast, 250)))
    if 'excluded' in pyogrio.list_layers(path)[:, 0]:
        # partly mapped sheets: shore points within 1 km of the excluded area (unmapped side, legend
        # panels) would be scored against the mapping limit or nothing
        exl = shapely.buffer(gpd.read_file(path, layer='excluded').to_crs(S.CRS).geometry.values[0], 1000)
        shapely.prepare(exl)
        pts = pts[~shapely.intersects(pts, exl)]
    d = shapely.distance(pts, unit_edge)
    d = d[d < 5000]                            # only where the sheet maps this coast
    if len(d) == 0:
        print(path, 'sheet does not map the coast within 5 km'); continue
    msg = (f'{path.split("/")[-1]}: {len(d)} coast points; median {np.median(d):.0f} m, p75 {np.percentile(d, 75):.0f} m, '
           f'p90 {np.percentile(d, 90):.0f} m, within 250 m {np.mean(d < 250):.0%}')
    print(msg)
