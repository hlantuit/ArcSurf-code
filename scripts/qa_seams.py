"""QA of seam_russia output: (1) distance from the exact frame to each seamed sheet's
outer edge (the band_snap report prints nan when its union is a collection); (2) the
conflict classes per seam."""
import sys
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import seam  # noqa: E402
import seam_russia as SR  # noqa: E402

for s in [s for s in SR.PDF_SHEETS if __import__('os').path.exists(f'{SR.OUTDIR}/{s}.gpkg')]:
    out = {}
    for tag, fn in (('raw', SR.src_path(s)), ('seamed', f'{SR.OUTDIR}/{s}.gpkg')):
        g = gpd.read_file(fn, layer='units').to_crs(S.CRS)
        polys = shapely.get_parts(shapely.union_all(shapely.make_valid(g.geometry.values)))
        polys = [p for p in polys if p.geom_type in ('Polygon', 'MultiPolygon')]
        edge = shapely.boundary(shapely.union_all(polys))
        L = seam.exact_frame_lines(*SR.frame(s))
        r = []
        for k, line in L.items():
            pts = shapely.line_interpolate_point(line, np.linspace(0.03, 0.97, 80), normalized=True)
            dd = shapely.distance(pts, edge)
            r.append(f'{k} {np.median(dd):.1f}/{dd.max():.0f}')
        out[tag] = ' '.join(r)
    print(f'{s:20s} raw: {out["raw"]:44s} seamed: {out["seamed"]}')
c = gpd.read_file(f'{S.WORK}/ru_seams.gpkg', layer='conflicts')
t = c.groupby(['sheet_a', 'sheet_b', 'class_a', 'class_b']).length_m.sum().div(1e3).round(1)
print(t.sort_values(ascending=False).groupby(level=[0, 1]).head(4).to_string())
