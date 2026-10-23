#!/usr/bin/env python
"""
Sheet-edge tools for a seamless Russian layer.

band_snap(units, lonlat_box, band)  - move vertices within `band` metres of a sheet's
    DIGITISED frame onto the EXACT frame (meridians/parallels of the sheet, datum per
    the caller), with the displacement fading linearly to zero at `band` from the
    edge. Only frame sides whose digitised position is within `tol_deg` of a whole
    degree are treated as frame (irregular extents such as the New Siberian Islands
    annex of Bryant S-53-55 are left alone, so no coastline is pulled onto a line).

match_seam(A, B, edge, tol, band) - align unit boundaries that cross a shared edge:
    crossings on each side are paired when they are within `tol` along the edge AND
    the harmonised classes on both sides of the crossing agree; both are moved to the
    midpoint, the shift fading to zero at `band` inland. Unpaired crossings and class
    disagreements along the edge are returned as a conflict table.
"""
import numpy as np
import pandas as pd
import geopandas as gpd
import pyproj
import shapely
from shapely.geometry import LineString

import surflib as S


def exact_frame_lines(lon0, lat0, lon1, lat1, datum=4284, step=0.01):
    """The four frame sides as densified LineStrings in EPSG:6931."""
    t = pyproj.Transformer.from_crs(datum, S.CRS, always_xy=True)

    def line(lons, lats):
        return LineString(np.c_[t.transform(lons, lats)])
    n_lon = int(round((lon1 - lon0) / step)) + 1
    n_lat = int(round((lat1 - lat0) / step)) + 1
    lons, lats = np.linspace(lon0, lon1, n_lon), np.linspace(lat0, lat1, n_lat)
    return {'S': line(lons, np.full(n_lon, lat0)), 'N': line(lons, np.full(n_lon, lat1)),
            'W': line(np.full(n_lat, lon0), lats), 'E': line(np.full(n_lat, lon1), lats)}


def _displace(geoms, field):
    """Apply a vertex displacement field(xy)->dxy to every geometry."""
    return shapely.transform(geoms, lambda xy: xy + field(xy))


def band_snap(units, raw_bounds, datum=4284, band=500.0, tol_deg=0.01, exact=False):
    """units: GeoDataFrame (EPSG:6931) of ONE sheet. raw_bounds: its lon/lat bounds as
    digitised, rounded to whole degrees (1:1M sheets). exact=True: raw_bounds IS the
    nomenclature frame (1:200k sheets have 40' sides) - used as is, all four sides real.
    Returns (snapped units, report)."""
    lo0, la0, lo1, la1 = raw_bounds
    if exact:
        ex = dict(zip(('W', 'S', 'E', 'N'), (lo0, la0, lo1, la1)))
        real = dict.fromkeys(ex, True)
    else:
        ex = {k: round(v) for k, v in zip(('W', 'S', 'E', 'N'), (lo0, la0, lo1, la1))}
        real = {k: abs(v - round(v)) <= tol_deg for k, v in zip(('W', 'S', 'E', 'N'), (lo0, la0, lo1, la1))}
    lines = exact_frame_lines(ex['W'], ex['S'], ex['E'], ex['N'], datum)
    src_edge = shapely.boundary(shapely.union_all(shapely.make_valid(units.geometry.values)))
    sides = [(k, lines[k]) for k in lines if real[k]]
    rep = {'real_sides': [k for k, _ in sides], 'skipped_sides': [k for k in lines if not real[k]]}
    if not sides:
        return units, rep
    # source-edge pieces that ARE the digitised frame (within band of an exact side)
    pieces = [(k, shapely.intersection(src_edge, shapely.buffer(L, band))) for k, L in sides]
    shift_max = []

    def field(xy):
        pts = shapely.points(xy)
        out = np.zeros_like(xy)
        for (k, L), (_, piece) in zip(sides, pieces):
            if piece.is_empty:
                continue
            dist = shapely.distance(pts, piece)
            m = dist < band
            if not m.any():
                continue
            s = shapely.line_interpolate_point(piece, shapely.line_locate_point(piece, pts[m]))
            e = shapely.line_interpolate_point(L, shapely.line_locate_point(L, s))
            v = shapely.get_coordinates(e) - shapely.get_coordinates(s)
            w = (1 - dist[m] / band)[:, None]
            out[m] += v * w
        return out

    touched = shapely.intersects(units.geometry.values,
                                 shapely.union_all([shapely.buffer(L, band) for _, L in sides]))
    snapped = units.copy()
    snapped.loc[touched, 'geometry'] = _displace(units.geometry.values[touched], field)
    snapped['geometry'] = shapely.make_valid(snapped.geometry.values)
    # report: distance from points along each exact side (corners excluded) to the
    # sheet's outer edge, before / after (median and max)
    def outer_edge(geoms):   # make_valid can return collections with lines: keep polygon parts only
        parts = shapely.get_parts(shapely.union_all(shapely.make_valid(geoms)))
        return shapely.boundary(shapely.union_all([p for p in parts if p.geom_type in ('Polygon', 'MultiPolygon')]))
    src_edge = outer_edge(units.geometry.values)
    after_edge = outer_edge(snapped.geometry.values)
    for k, L in sides:
        f = np.linspace(0.03, 0.97, 60)
        pts = shapely.line_interpolate_point(L, f, normalized=True)
        for tag, e in (('before', src_edge), ('after', after_edge)):
            d = shapely.distance(pts, e)
            rep[f'{k}_{tag}_m'] = (round(float(np.median(d)), 1), round(float(d.max()), 1))
    rep['n_touched'] = int(touched.sum())
    return S.polygons_only(snapped), rep


# ------------------------------------------------------------------ seam matching
def crossings(units, edge, cls='hclass', eps=60.0):
    """Points where unit boundaries meet `edge`, with the class on either side, ordered
    by position along the edge. Returns DataFrame(pos, x, y, left, right)."""
    near = units[shapely.dwithin(units.geometry.values, edge, eps)]
    # classes along the edge, sampled at 25 m, give the interval sequence
    L = edge.length
    s = np.arange(0, L, 25.0)
    pts = shapely.line_interpolate_point(edge, s)
    tree = shapely.STRtree(near.geometry.values)
    idx = tree.query_nearest(pts, max_distance=eps, return_distance=False)
    lab = np.full(len(s), None, dtype=object)
    lab[idx[0]] = near[cls].values[idx[1]]
    rows = []
    for i in range(1, len(s)):
        if lab[i] != lab[i - 1]:
            p = (s[i] + s[i - 1]) / 2
            q = shapely.line_interpolate_point(edge, p)
            rows.append(dict(pos=p, x=q.x, y=q.y, left=lab[i - 1], right=lab[i]))
    return pd.DataFrame(rows), pd.DataFrame(dict(pos=s, cls=lab))


def match_seam(A, B, edge, tol=1000.0, band=3000.0, cls='hclass'):
    """Pair crossings on both sides of the shared `edge` and warp both sheets so paired
    crossings coincide. Returns (A2, B2, pairs, conflicts)."""
    ca, sa = crossings(A, edge, cls)
    cb, sb = crossings(B, edge, cls)
    pairs, used = [], set()
    for i, r in ca.iterrows():
        cand = cb[(abs(cb['pos'] - r['pos']) <= tol) & (cb['left'] == r['left']) & (cb['right'] == r['right'])]
        cand = cand[~cand.index.isin(used)]
        if len(cand):
            j = (cand['pos'] - r['pos']).abs().idxmin()
            used.add(j)
            pairs.append(dict(pos_a=r['pos'], pos_b=cb.loc[j, 'pos'], left=r['left'], right=r['right']))
    pairs = pd.DataFrame(pairs)
    # displacement along the edge: piecewise-linear in position, zero at the edge ends
    def along_field(sheet_pos_col):
        if pairs.empty:
            return lambda xy: np.zeros_like(xy)
        p_src = np.r_[0, pairs[sheet_pos_col].values, edge.length]
        mid = (pairs['pos_a'].values + pairs['pos_b'].values) / 2
        shift = np.r_[0, mid - pairs[sheet_pos_col].values, 0]
        o = np.argsort(p_src)
        p_src, shift = p_src[o], shift[o]

        def f(xy):
            pts = shapely.points(xy)
            d = shapely.distance(pts, edge)
            m = d < band
            out = np.zeros_like(xy)
            if not m.any():
                return out
            pos = shapely.line_locate_point(edge, pts[m])
            ds = np.interp(pos, p_src, shift) * (1 - d[m] / band)
            p0 = shapely.get_coordinates(shapely.line_interpolate_point(edge, pos))
            p1 = shapely.get_coordinates(shapely.line_interpolate_point(edge, np.clip(pos + ds, 0, edge.length)))
            out[m] = p1 - p0          # tangential shift only: the edge stays on the edge
            return out
        return f

    def warp(U, f):
        t = shapely.dwithin(U.geometry.values, edge, band)
        U = U.copy()
        U.loc[t, 'geometry'] = shapely.make_valid(_displace(U.geometry.values[t], f))
        return S.polygons_only(U)

    A2, B2 = warp(A, along_field('pos_a')), warp(B, along_field('pos_b'))
    # conflicts: after warping, sample classes on both sides and report disagreements
    _, sa2 = crossings(A2, edge, cls)
    _, sb2 = crossings(B2, edge, cls)
    n = min(len(sa2), len(sb2))
    dis = sa2['cls'].values[:n] != sb2['cls'].values[:n]
    conf = pd.DataFrame(dict(pos=sa2['pos'].values[:n], a=sa2['cls'].values[:n], b=sb2['cls'].values[:n]))[dis]
    stats = dict(crossings_a=len(ca), crossings_b=len(cb), paired=len(pairs),
                 edge_km=edge.length / 1e3, disagree_km=float(dis.sum() * 25 / 1e3),
                 agree_frac=float(1 - dis.mean()) if n else None)
    return A2, B2, pairs, conf, stats
