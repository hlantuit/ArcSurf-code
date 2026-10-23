#!/usr/bin/env python
"""
Vector-PDF Quaternary map sheet -> georeferenced polygons (GeoPackage).

For VSEGEI Gosgeolkarta sheets exported to PDF (text converted to outlines, units as
filled paths). Steps:
 1. frame: largest white fill; its INNER ring is the neatline (sheet corners).
 2. control points on the neatline's two parallels (top = lat1, bottom = lat0),
    longitude by arc-length fraction (on a conic parallel arc length is linear in
    longitude); + the four corners.
 3. fit page->projected affine for candidate conic projections (eqdc, lcc; standard
    parallels at 1/6 and 5/6 of the sheet), keep the smallest residual (metres).
 4. polygons from fills whose colour is a legend swatch colour (or a water colour);
    painter's order resolved (later draws on top); text/symbols/hatching ignored.
 5. clip to the neatline, transform to lon/lat (datum ASSUMED Pulkovo-1942,
    EPSG:4284) and to EPSG:6931; write units + QA stats.

usage: pdf_to_polygons.py <pdf> <sheet> <lon0> <lat0> <lon1> <lat1> <legend.csv> <out.gpkg>
                          [--water '#c7eafb,...']
"""
import argparse
import collections
import json
import math
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pymupdf  # noqa: E402
import pyproj  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Polygon  # noqa: E402

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402


def hexc(c):
    return '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) if c else None


def bez(p0, p1, p2, p3, n=8):
    t = np.linspace(0, 1, n + 1)[1:]
    x = (1-t)**3*p0.x + 3*(1-t)**2*t*p1.x + 3*(1-t)*t**2*p2.x + t**3*p3.x
    y = (1-t)**3*p0.y + 3*(1-t)**2*t*p1.y + 3*(1-t)*t**2*p2.y + t**3*p3.y
    return list(zip(x, y))


ROT = 0     # --rot: page content drawn sideways (R-47 etc.); points rotated before use


def _r(pts):
    if ROT == 90:
        return [(-y, x) for x, y in pts]
    if ROT == 270:
        return [(y, -x) for x, y in pts]
    if ROT == 180:
        return [(-x, -y) for x, y in pts]
    return pts


def subpaths(items):
    """Split a drawing's items into closed point rings (curves flattened), rotated by ROT."""
    return [_r(r) for r in _subpaths(items)]


def _subpaths(items):
    rings, cur, last = [], [], None
    for it in items:
        op = it[0]
        if op == 're':
            r = it[1]
            if cur:
                rings.append(cur)
            rings.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)])
            cur, last = [], None
            continue
        if op == 'qu':
            q = it[1]
            if cur:
                rings.append(cur)
            rings.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)])
            cur, last = [], None
            continue
        p0 = it[1]
        if last is None or abs(p0.x - last.x) > 1e-3 or abs(p0.y - last.y) > 1e-3:
            if cur:
                rings.append(cur)
            cur = [(p0.x, p0.y)]
        if op == 'l':
            cur.append((it[2].x, it[2].y))
            last = it[2]
        elif op == 'c':
            cur.extend(bez(it[1], it[2], it[3], it[4]))
            last = it[4]
    if cur:
        rings.append(cur)
    return [r for r in rings if len(r) >= 3]


def poly_from_drawing(d):
    geom = None
    for r in subpaths(d['items']):
        p = shapely.make_valid(Polygon(r))
        if p.is_empty:
            continue
        geom = p if geom is None else shapely.symmetric_difference(geom, p)   # even-odd
    return geom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf'); ap.add_argument('sheet')
    ap.add_argument('lon0', type=float); ap.add_argument('lat0', type=float)
    ap.add_argument('lon1', type=float); ap.add_argument('lat1', type=float)
    ap.add_argument('legend'); ap.add_argument('out')
    ap.add_argument('--water', default='#c7eafb')
    ap.add_argument('--page', type=int, default=0)
    ap.add_argument('--scale', type=float, default=1_000_000, help='nominal scale denominator of the sheet')
    ap.add_argument('--neat-from-units', action='store_true',
                    help='if no frame ring matches, use the outline of the union of unit fills')
    ap.add_argument('--rot', type=int, default=0, help='rotate page content 90/180/270 deg before fitting')
    a = ap.parse_args()
    global ROT
    ROT = a.rot

    page = pymupdf.open(a.pdf)[a.page]
    dr = page.get_drawings()
    leg = pd.read_csv(a.legend, dtype=str, keep_default_na=False)
    colours = set(leg['fill'].str.lower())
    water = set(c.strip().lower() for c in a.water.split(',') if c.strip())

    # 1. neatline. Expected page size of the frame from the nomenclature and nominal
    # scale; the neatline is the closed ring (fill OR stroke, any colour) whose bbox
    # matches it within 5%. Falls back to the inner ring of the largest white fill
    # (R-52 layout) when no ring matches.
    lon_c0 = (a.lon0 + a.lon1) / 2
    eq = pyproj.Transformer.from_crs(4284, f'+proj=eqdc +lat_1={a.lat0} +lat_2={a.lat1} +lon_0={lon_c0} +ellps=krass', always_xy=True)
    xs, ys = eq.transform([a.lon0, a.lon1, a.lon0, a.lon1, lon_c0], [a.lat0, a.lat0, a.lat1, a.lat1, a.lat0])
    exp_w = (max(xs) - min(xs)) / a.scale * 1000 / 25.4 * 72
    exp_h = (max(ys) - min(ys)) / a.scale * 1000 / 25.4 * 72
    neat, best_err = None, 0.05
    for d in dr:
        r = d['rect']
        if max(r.width, r.height) < 0.5 * min(exp_w, exp_h):
            continue
        for ring in subpaths(d['items']):
            P_ = np.array(ring)
            w_, h_ = np.ptp(P_[:, 0]), np.ptp(P_[:, 1])
            err = max(abs(w_ / exp_w - 1), abs(h_ / exp_h - 1))
            if err < best_err:
                neat, best_err = ring, err
    if neat is None and a.neat_from_units:
        # frame drawn as loose segments: where units fill the whole frame (sea mapped
        # as offshore units), the outline of the union of unit fills IS the neatline
        polys = []
        for d in dr:
            if hexc(d.get('fill')) in colours:
                g = poly_from_drawing(d)
                if g is not None and not g.is_empty:
                    polys.append(g)
        U_ = shapely.union_all(polys)
        U_ = max(shapely.get_parts(U_), key=lambda p: p.area) if U_.geom_type != 'Polygon' else U_
        neat = list(shapely.simplify(Polygon(U_.exterior.coords), 0.3).exterior.coords)
        P_ = np.array(neat)
        print(f'neatline: from union of unit fills, bbox {np.ptp(P_[:, 0]):.0f} x {np.ptp(P_[:, 1]):.0f} pt '
              f'(expected at 1:{a.scale:,.0f}: {exp_w:.0f} x {exp_h:.0f})')
    if neat is None:
        white = max((d for d in dr if hexc(d.get('fill')) == '#ffffff'),
                    key=lambda d: d['rect'].width * d['rect'].height)
        rings = sorted(subpaths(white['items']), key=lambda r: -Polygon(r).area)
        neat = rings[1] if len(rings) > 1 and Polygon(rings[1]).area > 0.8 * Polygon(rings[0]).area else rings[0]
        print('neatline: fallback to largest white fill')
    else:
        print(f'neatline: ring matching expected {exp_w:.0f} x {exp_h:.0f} pt within {best_err:.1%}')
    neat_poly = shapely.make_valid(Polygon(neat))
    P = np.array(neat)
    tl = P[np.argmin(P[:, 0] + P[:, 1])]; br = P[np.argmax(P[:, 0] + P[:, 1])]
    tr = P[np.argmax(P[:, 0] - P[:, 1])]; bl = P[np.argmin(P[:, 0] - P[:, 1])]
    ymid = (tl[1] + bl[1]) / 2

    # 2. control points: split the ring IN ORDER at its four corners, so each edge is
    # exactly the vertex run between two corners (a 'lower half' rule mis-assigned
    # side-edge vertices to the bottom parallel on sheets whose meridians carry vertices)
    Pc = P[:-1] if np.allclose(P[0], P[-1]) else P
    ci = {k: int(np.argmin(np.hypot(*(Pc - c).T))) for k, c in (('tl', tl), ('tr', tr), ('br', br), ('bl', bl))}

    def run(i0, i1):
        n = len(Pc)
        idx = [i0]
        while idx[-1] != i1:
            idx.append((idx[-1] + 1) % n)
        return Pc[idx]
    fwd_top = run(ci['tl'], ci['tr'])
    if len(fwd_top) > len(Pc) / 2 + 1:          # ring runs anticlockwise on the page
        Pc = Pc[::-1]
        ci = {k: len(Pc) - 1 - v for k, v in ci.items()}
    edges = {'top': run(ci['tl'], ci['tr']), 'right': run(ci['tr'], ci['br']),
             'bottom': run(ci['br'], ci['bl'])[::-1], 'left': run(ci['bl'], ci['tl'])[::-1]}

    def along(pts):
        seg = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
        return seg / seg[-1]
    cps = []
    for name, lat in (('top', a.lat1), ('bottom', a.lat0)):      # parallels: lon by arc fraction
        e = edges[name]
        for p, f in zip(e, along(e)):
            cps.append((p[0], p[1], a.lon0 + f * (a.lon1 - a.lon0), lat))
    cps = np.array(cps)
    print('edges (vertices): ' + ', '.join(f'{k}={len(v)}' for k, v in edges.items()))

    # 3. fit page -> projected affine for candidate conics
    lon_c = (a.lon0 + a.lon1) / 2
    dl = (a.lat1 - a.lat0) / 6
    best = None
    for kind in ('eqdc', 'lcc'):
        crs = pyproj.CRS.from_proj4(f'+proj={kind} +lat_1={a.lat0 + dl} +lat_2={a.lat1 - dl} '
                                    f'+lat_0={(a.lat0 + a.lat1) / 2} +lon_0={lon_c} +ellps=krass +units=m +no_defs')
        fwd = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4284), crs, always_xy=True)
        E, N = fwd.transform(cps[:, 2], cps[:, 3])
        A = np.c_[cps[:, 0], cps[:, 1], np.ones(len(cps))]
        cx, *_ = np.linalg.lstsq(A, E, rcond=None)
        cy, *_ = np.linalg.lstsq(A, N, rcond=None)
        res = np.hypot(A @ cx - E, A @ cy - N)
        print(f'{kind}: n={len(cps)} rms={np.sqrt((res**2).mean()):.1f} m max={res.max():.1f} m')
        if best is None or res.max() < best[0]:
            best = (res.max(), kind, crs, cx, cy, float(np.sqrt((res**2).mean())))
    maxres, kind, crs, cx, cy, rms = best
    scale = math.hypot(cx[0], cy[0])   # metres per pt
    print(f'chosen {kind}: rms {rms:.1f} m, max {maxres:.1f} m; {scale:.1f} m/pt -> nominal 1:{scale/0.000352778:,.0f}')

    # 4. polygons, painter's order
    recs = []
    other = collections.Counter()
    shapely.prepare(neat_poly)
    for i, d in enumerate(dr):
        c = hexc(d.get('fill'))
        if c is None:
            continue
        if c not in colours and c not in water:
            if shapely.intersects(neat_poly, shapely.box(*d['rect'])):
                other[c] += d['rect'].width * d['rect'].height
            continue
        g = poly_from_drawing(d)
        if g is None or g.is_empty:
            continue
        g = shapely.intersection(g, neat_poly)
        if g.is_empty or g.area <= 0:
            continue
        recs.append((i, c, g))
    print(f'{len(recs)} unit/water fills inside the neatline')
    # top-most first: each fill loses what later (higher) fills cover
    recs.sort(key=lambda r: -r[0])
    kept, done = [], []          # done = geometries already placed (all drawn later)
    tree, n_tree = None, 0       # STRtree over done[:n_tree], rebuilt every 200 adds
    for i, c, g in recs:
        hits = []
        if tree is not None:
            hits = [done[j] for j in tree.query(g, predicate='intersects')]
        hits += [h for h in done[n_tree:] if shapely.intersects(h, g)]
        if hits:
            g = shapely.difference(g, shapely.union_all(hits))
        if g.is_empty or g.area <= 1e-3:
            continue
        kept.append((i, c, g))
        done.append(g)
        if len(done) - n_tree >= 200:
            tree, n_tree = shapely.STRtree(done), len(done)
    cover = shapely.union_all([g for _, _, g in kept])
    gap = shapely.difference(neat_poly, cover)
    print(f'neatline area {neat_poly.area:,.0f} pt2; covered {cover.area/neat_poly.area:.4%}; gap {gap.area/neat_poly.area:.4%}')
    print('non-legend colours inside frame (bbox-area pt2, top 12):', other.most_common(12))

    # 5. transform page -> projected -> Pulkovo lon/lat -> EPSG:6931
    inv = pyproj.Transformer.from_crs(crs, pyproj.CRS.from_epsg(4284), always_xy=True)
    to6931 = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4284), pyproj.CRS.from_epsg(S.CRS), always_xy=True)

    # Frame snapping: the affine leaves 10-30 m residuals on the neatline, enough to
    # open slivers between neighbouring sheets. A thin-plate-spline correction pinned
    # at the neatline control points (fitted -> exact projected position) puts the
    # frame EXACTLY on its meridians/parallels and decays smoothly into the interior.
    from scipy.interpolate import RBFInterpolator
    fwd = pyproj.Transformer.from_crs(pyproj.CRS.from_epsg(4284), crs, always_xy=True)
    # side edges (meridians): latitude linear along the straight edge (exact for eqdc,
    # sub-metre for lcc over 4 deg), 20 pins per side
    side_page, side_ll = [], []
    for name, lon in (('left', a.lon0), ('right', a.lon1)):
        e = edges[name]                               # ordered top -> bottom
        if name == 'right' and e[0][1] > e[-1][1]:
            e = e[::-1]
        if name == 'left' and e[0][1] > e[-1][1]:
            e = e[::-1]
        L_ = LineString(e)
        for f in np.linspace(0, 1, 22)[1:-1]:
            q = L_.interpolate(f, normalized=True)
            side_page.append((q.x, q.y))
            side_ll.append((lon, a.lat1 + f * (a.lat0 - a.lat1)))
    ctrl_page = np.r_[cps[:, :2], np.array(side_page)]
    ctrl_ll = np.r_[cps[:, 2:4], np.array(side_ll)]
    _, uniq = np.unique(np.round(ctrl_page, 2), axis=0, return_index=True)   # corners appear twice
    ctrl_page, ctrl_ll = ctrl_page[np.sort(uniq)], ctrl_ll[np.sort(uniq)]
    Ex, Nx = fwd.transform(ctrl_ll[:, 0], ctrl_ll[:, 1])
    Ef = cx[0] * ctrl_page[:, 0] + cx[1] * ctrl_page[:, 1] + cx[2]
    Nf = cy[0] * ctrl_page[:, 0] + cy[1] * ctrl_page[:, 1] + cy[2]
    corr = RBFInterpolator(np.c_[Ef, Nf], np.c_[Ex - Ef, Nx - Nf], kernel='thin_plate_spline', smoothing=0.0)

    def tf(x, y):
        x, y = np.asarray(x), np.asarray(y)
        E = cx[0] * x + cx[1] * y + cx[2]
        N = cy[0] * x + cy[1] * y + cy[2]
        d = corr(np.c_[E, N])
        lo, la = inv.transform(E + d[:, 0], N + d[:, 1])
        return to6931.transform(lo, la)

    # FOLD CHECK (R-44_g3, 2026-10-07): the spline folded the western band of the sheet. Unit areas summed to 147 %
    # of the frame, yet the frame itself sat within 3 m, so RMS and Hausdorff passed. Sample the transform on a grid
    # of cells inside the neatline. If any cell flips orientation, drop the spline and keep the affine (frame residual
    # 10-30 m; the merge's 0.5 mm claim buffer absorbs it).
    nb = neat_poly.bounds
    gxs, gys = np.meshgrid(np.linspace(nb[0], nb[2], 81), np.linspace(nb[1], nb[3], 81))
    X, Y = tf(gxs.ravel(), gys.ravel())
    X, Y = np.asarray(X).reshape(gxs.shape), np.asarray(Y).reshape(gxs.shape)
    cross = ((X[:-1, 1:] - X[:-1, :-1]) * (Y[1:, :-1] - Y[:-1, :-1])
             - (Y[:-1, 1:] - Y[:-1, :-1]) * (X[1:, :-1] - X[:-1, :-1]))
    ins = shapely.contains_xy(neat_poly, gxs, gys)
    cell_in = ins[:-1, :-1] & ins[:-1, 1:] & ins[1:, :-1] & ins[1:, 1:]
    sgn = np.sign(np.median(cross[cell_in])) if cell_in.any() else 1.0
    n_fold = int(((np.sign(cross) != sgn) & cell_in).sum())
    if n_fold:
        print(f'FOLD: {n_fold} of {int(cell_in.sum())} grid cells flip under the frame spline -> spline dropped, '
              f'affine kept')
        corr = lambda pts: np.zeros((len(pts), 2))          # noqa: E731  (tf looks corr up at call time)

    # exact sheet frame (densified meridians/parallels) in EPSG:6931, used to clip
    frame_ll = shapely.segmentize(shapely.box(a.lon0, a.lat0, a.lon1, a.lat1), 0.01)
    fx, fy = np.array(frame_ll.exterior.coords).T
    exact_frame = Polygon(np.c_[to6931.transform(fx, fy)])

    lut = leg.set_index(leg['fill'].str.lower())
    rows = []
    shapely.prepare(exact_frame)
    for i, c, g in kept:
        try:
            gg = shapely.transform(g, lambda xy: np.c_[tf(xy[:, 0], xy[:, 1])])
        except shapely.errors.GEOSException:
            # R-49 (2026-10-02): a degenerate ring (repeated/collinear vertices) came back
            # unclosed from the per-vertex transform; clean it and retry, else skip it
            try:
                g2 = shapely.make_valid(shapely.set_precision(g, 0.01))
                gg = shapely.transform(g2, lambda xy: np.c_[tf(xy[:, 0], xy[:, 1])])
            except shapely.errors.GEOSException:
                n_skipped = globals().get('n_skipped', 0) + 1
                globals()['n_skipped'] = n_skipped
                continue
        # after snapping, units along the frame are clipped to the EXACT sheet frame so
        # neighbouring sheets share one boundary; interior slivers < snapping residual
        gg = shapely.intersection(shapely.make_valid(gg), exact_frame)
        if gg.is_empty:
            continue
        if c in water and c not in lut.index:
            rows.append(dict(draw_order=i, fill=c, k='', index='WATER', description_ru='водоём', geometry=gg))
            continue
        r = lut.loc[[c]]
        # a colour shared by two legend units (e.g. R-52 mnH / mH2): keep both indices
        rows.append(dict(draw_order=i, fill=c, k='|'.join(r['k']), index='|'.join(r['index']),
                         description_ru=' || '.join(r['description_ru']), geometry=gg))
    out = gpd.GeoDataFrame(rows, crs=S.CRS)
    out['sheet'] = a.sheet
    # printers split large fills into bands: dissolve touching pieces of the same unit
    n_before = len(out)
    out = out.dissolve(by=['index', 'fill'], aggfunc={'draw_order': 'min', 'k': 'first',
                                                        'description_ru': 'first', 'sheet': 'first'}).reset_index()
    out = S.polygons_only(out)
    print(f'dissolved {n_before} fill pieces -> {len(out)} unit polygons')
    out.to_file(a.out, layer='units', driver='GPKG')
    fp = gpd.GeoDataFrame({'sheet': [a.sheet]}, geometry=[exact_frame], crs=S.CRS)
    # snapping QA: how far the snapped neatline sits from the exact frame (should be ~0)
    snapped = shapely.transform(neat_poly, lambda xy: np.c_[tf(xy[:, 0], xy[:, 1])])
    hd = shapely.hausdorff_distance(shapely.boundary(snapped), shapely.boundary(exact_frame))
    print(f'frame snapping: Hausdorff(snapped neatline, exact frame) = {hd:.1f} m')
    fp.to_file(a.out, layer='neatline', driver='GPKG')
    qa = dict(sheet=a.sheet, projection=kind, rms_m=rms, max_res_m=float(maxres), m_per_pt=scale,
              frame_hausdorff_after_snap_m=float(hd),
              n_polygons=len(out), area_km2=float(out.area.sum() / 1e6),
              neatline_km2=float(fp.area.sum() / 1e6), gap_frac=float(gap.area / neat_poly.area),
              area_by_index={k: round(v / 1e6, 1) for k, v in out.groupby('index').apply(lambda x: x.area.sum()).items()},
              non_legend_colours=other.most_common(20), datum='EPSG:4284 assumed',
              fold_cells=n_fold, spline_dropped=bool(n_fold),
              area_excess_frac=float(out.area.sum() / fp.area.sum() - 1.0))
    if qa['area_excess_frac'] > 0.01:
        print(f"WARNING: units sum to {100 * (1 + qa['area_excess_frac']):.1f} % of the frame - overlapping output")
    json.dump(qa, open(a.out.replace('.gpkg', '_qa.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in qa.items() if k != 'area_by_index'}, ensure_ascii=False))
    print('area by index (km2):', qa['area_by_index'])


if __name__ == '__main__':
    main()
