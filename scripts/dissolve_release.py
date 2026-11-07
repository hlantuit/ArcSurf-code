#!/usr/bin/env python
"""Dissolved release geometry with persistent polygon identifiers (H. Lantuit 2026-10-07: "Then do the dissolved
version").

The merge (merge_tiles.py) cuts the geology along lines that are not geology: the 100 km tile edges, the
permafrost-zone limits (split_by_zone) and the IRYP v2 and 60 N limits (split_by_yedoma). Here the pieces that are
identical in every geology attribute (KEY) and share an edge are merged again, so that every polygon is one continuous
patch of one source unit. Each polygon gets the ArcSurf polygon identifier asid (integer, assigned once and never
reused; a later release carries it forward through a lineage table), and every piece of the tiled version keeps the
asid of the polygon it belongs to.

  pass 1 (per tile, parallel)  pieces with the same KEY within TOL of each other -> connected components -> union
                               with TOL snap-rounding -> patches (single polygons); a piece belongs to the patch that
                               holds its representative point
  pass 2 (whole domain)        patches within EDGE of their tile's edge are joined to patches of OTHER tiles with the
                               same KEY within TOL -> components -> union -> final polygons
  closing (both passes)        parts of one union that still run along each other within TOL for more than CONTACT
                               (a micro-gap: the boundaries touch only at points) are joined one way, the smaller part
                               snapped onto the larger one's vertices (merge 48 left 76,433 such pairs; see _close)
  ids                          final polygons sorted by the tile that holds their representative point, then y
                               descending, then x -> asid 1..N (the same input gives the same ids)

Not in the geology of the release (H. Lantuit 2026-10-07, they go to the addendum): pf_zone, yedoma, yedoma_conf (the
pieces are cut along them, so the addendum gets exact area shares per asid) and ice_rich (source-mapped ground ice; it
IS in KEY, so it is constant on every asid). Aggregated: coastal (any piece), gapfill_km2 (area filled by
'sliver_nearest'), n_pieces, n_tiles.

OUT (default work/dissolve_m43):
  p1/<tile>.parquet          pass-1 patches: tile_id, pidx, khash, KEY, coastal, gapfill_km2, n_pieces, edge, rx, ry,
                             area_km2, geometry
  p1/<tile>.map.parquet      piece -> patch (row = position of the piece in the tile's parquet)
  final/<tile>.parquet       final polygons whose representative point lies in <tile>, sorted by asid:
                             asid, unit_code, KEY, coastal, gapfill_km2, n_pieces, n_tiles, area_km2, rep_tile,
                             rep_row (the tiled piece that represents the polygon: its largest piece, or for a part
                             split off by a snap-rounded union the piece it overlaps most), geometry
  piece_asid.parquet         tile_id, row, asid for every piece of the tiled version
  report_p1.tsv, report.txt  counts, area conservation, components, validity
usage: dissolve_release.py [--tiles DIR] [--out DIR] [--only T1,T2] [--step 1|2|all] [--workers N]"""
import argparse
import glob
import hashlib
import os
import sys
import time
import traceback
from multiprocessing import Pool

import numpy as np
import pandas as pd
import geopandas as gpd
import pyarrow as pa
import pyarrow.parquet as pq
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
CRS = 'EPSG:6931'
KEY = ['src_id', 'src_sheet', 'src_code', 'src_desc', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich',
       'scale_den', 'pub_year', 'survey_years', 'conf_tier', 'licence', 'redistribution', 'xwalk_note',
       'hclass_under_ice', 'ice_src', 'ice_year', 'ice_note']
INTS = ('scale_den', 'pub_year', 'ice_year')
TOL = 0.01       # m: contact tolerance and snap-rounding grid (the merge's own GRID_M)
EDGE = 1.0       # m: a patch this close to its tile's edge may continue in the next tile
SNAP_MAX = 5e9   # vertex pairs a group's snap may compare (GEOS snap is all-pairs); beyond: the 1 cm grid union
CONTACT = 1.0    # m: parts of one union that run along each other within TOL for longer than this are joined (the
                 # release check, dissolve_check.py, counts the pairs over 1 m)
TILE = 100_000
NA = '\x00'      # missing value inside the key (distinct from '')
A = argparse.Namespace()


def tile_box(tid):
    tx, ty = (int(v) * 1000 for v in tid.split('_'))
    return shapely.box(tx, ty, tx + TILE, ty + TILE)


def tile_of(x, y):
    tx = (np.floor(np.asarray(x) / TILE).astype(np.int64) * 100).tolist()
    ty = (np.floor(np.asarray(y) / TILE).astype(np.int64) * 100).tolist()
    return np.array([f'{a:+06d}_{b:+06d}' for a, b in zip(tx, ty)], dtype=object)


def unit_code(src, sheet, code):
    """= addendum_build.unit_code: the same native unit gets the same code in every release"""
    return 'U' + hashlib.sha1(f'{src}|{sheet}|{code}'.encode('utf-8')).hexdigest()[:12]


def key_strings(df):
    cols = []
    for c in KEY:
        if c not in df:
            cols.append(np.full(len(df), NA, object))
            continue
        s = df[c]
        if c in INTS:              # 2014, never '2014.0' (a float column would hash differently in another tile)
            s = pd.to_numeric(s, errors='coerce').round().astype('Int64')
        cols.append(s.astype('string').fillna(NA).to_numpy(dtype=object))
    return ['\x1f'.join(v) for v in zip(*cols)]


def khash(df):
    return np.array([int.from_bytes(hashlib.blake2b(s.encode('utf-8'), digest_size=8).digest(), 'little',
                                    signed=True) for s in key_strings(df)], dtype=np.int64)


def _polys(g):
    """polygonal parts of any geometry, flattened"""
    out = []
    for p in shapely.get_parts(g):
        if p.geom_type == 'Polygon':
            if p.area > 0:
                out.append(p)
        elif p.geom_type in ('MultiPolygon', 'GeometryCollection'):
            out.extend(_polys(p))
    return out


def _area_ok(parts, total):
    """a union of non-overlapping pieces is valid and keeps their area (a GEOS 3.14 overlay can return a phantom
    result for touching inputs, see merge_tiles)"""
    return bool(parts) and all(p.is_valid for p in parts) and \
        abs(sum(p.area for p in parts) - total) <= 1.0 + 1e-7 * total


def _snap_to_neighbours(geoms, nbr):
    """every piece snapped to the pieces it lies within TOL of (nbr[i]: local indices of i's neighbours). A snap
    moves the piece's vertices onto the neighbours' vertices and inserts the neighbours' vertices into its segments;
    done on both sides of a contact it leaves the same vertices on both, so the union closes the micro-gap. Only
    vertices within TOL of a neighbour can move, and each piece is snapped to its neighbours only, not to the whole
    group (snapping every piece to the group's union cost minutes on large groups).
    GEOS compares every vertex of the piece with every vertex of the reference, so the reference is cut down to the
    neighbours' vertices within 2 TOL of the piece, in the order they have in the neighbours (merge 44: a piece of
    1.2 million vertices in the Hudson Bay Lowland ran for > 6 h). Farther vertices never snap, so the result is the
    same. Returns None when even the reduced snap would compare more than SNAP_MAX vertex pairs: the caller then
    goes straight to the 1 cm grid union."""
    geoms = np.asarray(geoms, dtype=object)
    out = np.empty(len(geoms), dtype=object)
    if not any(len(x) for x in nbr):
        out[:] = geoms
        return out
    xy, owner = shapely.get_coordinates(geoms, return_index=True)
    vidx = np.arange(len(xy))
    pts = shapely.points(xy)
    tree = shapely.STRtree(pts)
    nv = shapely.get_num_coordinates(geoms)
    x0, y0, x1, y1 = shapely.bounds(geoms).T
    r = 2 * TOL
    rank = np.full(len(geoms), -1, np.int64)
    refs = []                                           # first the reduced references and the cost, then the snaps
    cost = 0.0
    for i, g in enumerate(geoms):
        j = np.asarray(nbr[i], dtype=np.int64)
        if len(j) == 0:
            refs.append(None)
            continue
        cand = tree.query(shapely.box(x0[i] - r, y0[i] - r, x1[i] + r, y1[i] + r))
        rank[j] = np.arange(len(j))
        cand = cand[rank[owner[cand]] >= 0]
        if len(cand):
            shapely.prepare(g)
            cand = cand[shapely.dwithin(g, pts[cand], r)]
        if len(cand):
            cand = cand[np.lexsort((vidx[cand], rank[owner[cand]]))]   # neighbour order, then vertex order
            cost += float(nv[i]) * len(cand)
        rank[j] = -1
        refs.append(cand if len(cand) else None)
    if cost > SNAP_MAX:
        return None
    for i, (g, cand) in enumerate(zip(geoms, refs)):
        out[i] = g if cand is None else shapely.snap(g, shapely.multipoints(xy[cand]), TOL)
    return out


def _contact(a, b):
    """length (m) along which b's boundary runs within TOL of a's (as dissolve_check._contact): both boundaries are
    clipped to the pair's common box grown by TOL + 1 m before the buffer"""
    ax0, ay0, ax1, ay1 = a.bounds
    bx0, by0, bx1, by1 = b.bounds
    box = (max(ax0, bx0) - TOL - 1.0, max(ay0, by0) - TOL - 1.0, min(ax1, bx1) + TOL + 1.0, min(ay1, by1) + TOL + 1.0)
    try:
        ca = shapely.clip_by_rect(shapely.boundary(a), *box)
        cb = shapely.clip_by_rect(shapely.boundary(b), *box)
        return float(shapely.length(shapely.intersection(cb, shapely.buffer(ca, TOL))))
    except shapely.errors.GEOSException:          # unknown: offer the join, which keeps only one valid polygon
        return float('inf')


def _snap_onto(p, u, tol):
    """p with its vertices snapped onto u's vertices within tol (and those vertices inserted into its segments). The
    reference is u's boundary near p only: GEOS snap compares every vertex pair, and u can hold a million vertices"""
    x0, y0, x1, y1 = p.bounds
    r = 2 * tol
    ref = shapely.get_coordinates(shapely.clip_by_rect(shapely.boundary(u), x0 - r, y0 - r, x1 + r, y1 + r))
    return shapely.snap(p, shapely.multipoints(ref), tol) if len(ref) else p


def _snap_near(u, p, tol):
    """the reverse of _snap_onto: u snapped onto p's vertices within tol (inserted into u's segments, u's vertices moved
    onto them). Needed where p's vertices lie within tol of u's SEGMENTS but of none of u's vertices (merge 48 test:
    small quadrilaterals 1-9 m wide along long edges), which a snap of p onto u cannot close. Only p's vertices within
    2 tol of u are offered"""
    xy = shapely.get_coordinates(p)
    bd = shapely.boundary(u)
    shapely.prepare(bd)
    near = shapely.dwithin(bd, shapely.points(xy), 2 * tol)
    return shapely.snap(u, shapely.multipoints(xy[near]), tol) if near.any() else u


def _close(parts):
    """Parts of one union that still run along each other within TOL for more than CONTACT are joined. Their
    boundaries touch only at points (relate FF2F01212) and are otherwise apart by a micro-gap of < 1 cm: the coverage
    union keeps them apart, and so can the snap to neighbours (each side snapped to the OTHER side's original vertices,
    so the two can miss each other again). Merge 48 left 76,433 such pairs (96 % with a sliver of <= 6 vertices; the
    longest 25.8 km). A one-way snap closes them: the smaller part is snapped onto the vertices of the growing union
    (TOL, then 2 TOL), so the larger part keeps its boundary, and the two are unioned. A join is kept only as one valid
    polygon with their area. On 52 sampled pairs of merge 48, 1 cm closed 51 and 2 cm all, with area changes of at most
    0.05 m2; the 1 cm grid union closed 58 % and changed the area by up to 144 m2. Where that fails (the smaller part's
    vertices lie on the union's segments, not near its vertices), the union is snapped onto the part's vertices instead
    (_snap_near; moves union vertices by <= 2 TOL, so the area may change by up to 2 m2 or 1e-7 of it). Parts are
    visited from the largest along the contacts, so each one is offered to a union it touches.
    Returns (parts, joined, left): left = parts with a long contact that would not join"""
    if len(parts) < 2:
        return parts, 0, 0
    g = np.asarray(parts, dtype=object)
    x0, y0, x1, y1 = shapely.bounds(g).T
    a, b = shapely.STRtree(g).query(shapely.box(x0 - TOL, y0 - TOL, x1 + TOL, y1 + TOL))
    m = a < b
    a, b = a[m], b[m]
    if len(a):
        m = shapely.dwithin(g[a], g[b], TOL)
        a, b = a[m], b[m]
    if len(a):
        m = np.array([_contact(g[i], g[j]) > CONTACT for i, j in zip(a, b)], dtype=bool)
        a, b = a[m], b[m]
    if not len(a):
        return parts, 0, 0
    nc, lab = _components(a, b, len(g))
    adj = [[] for _ in range(len(g))]
    for i, j in zip(a.tolist(), b.tolist()):
        adj[i].append(j)
        adj[j].append(i)
    area = shapely.area(g)
    out, joined, left = [], 0, 0
    for c in range(nc):
        mem = np.flatnonzero(lab == c)
        if len(mem) == 1:
            out.append(g[mem[0]])
            continue
        start = int(mem[np.lexsort((mem, -area[mem]))[0]])     # the largest part (ties: the first)
        order, seen, k = [start], {start}, 0
        while k < len(order):                                  # breadth first along the contacts, larger first
            for j in sorted(adj[order[k]], key=lambda t: (-area[t], t)):
                if j not in seen:
                    seen.add(j)
                    order.append(j)
            k += 1
        u, rest = g[start], []
        for j in order[1:]:
            p, ok = g[j], False
            tot = u.area + p.area
            for tol, fwd in ((TOL, True), (2 * TOL, True), (TOL, False), (2 * TOL, False)):
                try:
                    v = _polys(shapely.union(u, _snap_onto(p, u, tol)) if fwd else
                               shapely.union(_snap_near(u, p, tol), p))
                except shapely.errors.GEOSException:
                    continue
                if len(v) == 1 and (_area_ok(v, tot) if fwd else
                                    v[0].is_valid and abs(v[0].area - tot) <= max(2.0, 1e-7 * tot)):
                    u, ok = v[0], True
                    break
            joined += ok
            if not ok:
                rest.append(p)
        out.append(u)
        out.extend(rest)
        left += len(rest)
    return out, joined, left


def _union(geoms, nbr):
    """Exact first, so that a merged polygon keeps its boundary vertices and still fits its unmerged neighbours:
    ('cov', parts)    the pieces form a valid coverage (shared edges match vertex for vertex): coverage union
    ('float', parts)  otherwise the floating-point overlay union
                      Both are accepted only as ONE polygon of the pieces' area. Several parts mean the pieces met
                      at points or across micro-gaps; telling the two apart pair by pair (snap + relate on large
                      polygons) cost up to 15 min per tile, so a multi-part result goes to the next step.
    ('snapto', parts) every piece snapped to its neighbours, then the float union; any number of parts is accepted
                      once _close has joined the parts that still run along each other (micro-gaps); the rest met
                      only at points, as in any single-part dissolve
    ('snap', parts)   1 cm snap-rounded union (moves the merged polygon's vertices by < 1 cm), then _close
    ('keep', geoms)   last resort: nothing merges cleanly, the pieces stay as they are (no area is lost), then _close
    Returns (mode, parts, joined, left), joined / left as from _close."""
    geoms = np.asarray(geoms, dtype=object)
    total = float(shapely.area(geoms).sum())
    try:
        if shapely.coverage_is_valid(geoms):
            parts = _polys(shapely.coverage_union_all(geoms))
            if len(parts) == 1 and _area_ok(parts, total):
                return 'cov', parts, 0, 0
        else:
            parts = _polys(shapely.union_all(geoms))
            if len(parts) == 1 and _area_ok(parts, total):
                return 'float', parts, 0, 0
    except shapely.errors.GEOSException:
        pass
    try:
        snapped = _snap_to_neighbours(geoms, nbr)
        if snapped is not None:
            parts = _polys(shapely.union_all(snapped))
            if _area_ok(parts, total):
                return ('snapto',) + _close(parts)
    except shapely.errors.GEOSException:
        pass
    try:
        u = shapely.union_all(geoms, grid_size=TOL)
    except shapely.errors.GEOSException:
        u = shapely.union_all(shapely.make_valid(geoms), grid_size=TOL)
    parts = _polys(u)
    # snap-rounding moves boundaries by < 1 cm, so allow a little more area change than the exact paths; if even this
    # union fails (merge 44: groups of mm-thin slivers in British Columbia collapsed to nothing), keep the pieces
    if parts and all(p.is_valid for p in parts) and \
            abs(sum(p.area for p in parts) - total) <= max(100.0, 1e-6 * total):
        return ('snap',) + _close(parts)
    return ('keep',) + _close(list(geoms))


def _assign(members, parts):
    """index into parts for every member geometry: the part holding its representative point (nearest part if the
    1 cm snap moved the point outside)"""
    if len(parts) == 1:
        return np.zeros(len(members), np.int64)
    pts = shapely.point_on_surface(np.asarray(members, dtype=object))
    tree = shapely.STRtree(parts)
    idx = np.full(len(pts), -1, np.int64)
    qi, ti = tree.query(pts, predicate='intersects')
    idx[qi] = ti
    miss = np.flatnonzero(idx < 0)
    if len(miss):
        qi, ti = tree.query_nearest(pts[miss])
        idx[miss[qi]] = ti
    return idx


def _neighbours(a, b, n, groups):
    """local neighbour lists for every group from the near pairs (a, b) (indices 0..n-1): all neighbours of a
    member lie in its own group, because the groups are the connected components of these pairs"""
    if len(a) == 0:
        return [[np.zeros(0, np.int64) for _ in mem] for mem in groups]
    adj = coo_matrix((np.ones(2 * len(a), np.int8), (np.concatenate([a, b]), np.concatenate([b, a]))),
                     shape=(n, n)).tocsr()
    out = []
    for mem in groups:
        pos = {int(g): i for i, g in enumerate(mem)}
        out.append([np.array([pos[int(j)] for j in adj.indices[adj.indptr[g]:adj.indptr[g + 1]]], dtype=np.int64)
                    for g in mem])
    return out


def _rep_members(members, parts, idx):
    """for every part, the member that represents it (and carries its context into the addendum): the largest
    member it holds, or, for a part split off by the snap and holding no member's point, the member it overlaps
    most"""
    members = np.asarray(members, dtype=object)
    rep = np.full(len(parts), -1, np.int64)
    o = np.argsort(shapely.area(members), kind='stable')
    rep[idx[o]] = o                                  # ascending: the largest member is written last
    miss = np.flatnonzero(rep < 0)
    if len(miss):
        tree = shapely.STRtree(members)                 # (intersecting every member with every orphan: hours)
        for q in miss:
            c = np.sort(tree.query(parts[q]))
            a = shapely.area(shapely.intersection(members[c], parts[q])) if len(c) else np.zeros(0)
            rep[q] = int(c[np.argmax(a)]) if len(a) and a.max() > 0 else 0
    return rep


def _near_pairs(geoms, kh, other=None):
    """pairs (a < b) of geometries with the same key hash within TOL of each other. The STRtree is queried with
    the envelopes grown by TOL (cheap); the exact distance test runs only on the same-key candidates. Querying with
    predicate='dwithin' computed a polygon distance for every envelope overlap, which took most of the time on
    tiles of large, detailed polygons (Hudson Bay Lowland: 50 s before any union). other: optional array that must
    DIFFER between the two members (pass 2: the tile)."""
    x0, y0, x1, y1 = shapely.bounds(geoms).T
    boxes = shapely.box(x0 - TOL, y0 - TOL, x1 + TOL, y1 + TOL)
    a, b = shapely.STRtree(geoms).query(boxes)
    m = (a < b) & (kh[a] == kh[b])
    if other is not None:
        m &= other[a] != other[b]
    a, b = a[m], b[m]
    if len(a):
        shapely.prepare(geoms)                          # indexed distance: the plain test is all-pairs on vertices
        ok = shapely.dwithin(geoms[a], geoms[b], TOL)
        a, b = a[ok], b[ok]
    return a, b


def _components(a, b, n):
    if n == 0:
        return 0, np.zeros(0, np.int64)
    m = coo_matrix((np.ones(len(a), np.int8), (a, b)), shape=(n, n))
    return connected_components(m, directed=False)


def _groups(lab, nc):
    """members of every component with more than one member"""
    order = np.argsort(lab, kind='stable')
    counts = np.bincount(lab, minlength=nc)
    ends = np.cumsum(counts)
    return [order[e - c:e] for c, e in zip(counts, ends) if c > 1]


# ---------------------------------------------------------------- pass 1
def pass1(f):
    tid = os.path.basename(f)[:-8]
    outp = f'{A.out}/p1/{tid}.parquet'
    if os.path.exists(outp):
        return tid, 'exists'
    try:
        t0 = time.time()
        g = gpd.read_parquet(f)
        n = len(g)
        geoms = np.asarray(shapely.force_2d(g.geometry.values), dtype=object)
        kh = khash(g)
        area_in = float(shapely.area(geoms).sum())
        a, b = _near_pairs(geoms, kh)
        nc, lab = _components(a, b, n)
        piece_patch = np.full(n, -1, np.int64)
        single = np.bincount(lab, minlength=nc)[lab] == 1
        sidx = np.flatnonzero(single)
        pg = list(geoms[sidx])                       # patch geometries: singletons first, unchanged
        psrc = list(sidx)                            # the patch's representative piece (carries its KEY)
        piece_patch[sidx] = np.arange(len(sidx))
        worst = 0.0
        groups = _groups(lab, nc)
        nbrs = _neighbours(a, b, n, groups)
        nfloat = nsnapto = nsnap = nkeep = njoin = nleft = 0
        for mem, nbr in zip(groups, nbrs):
            mode, parts, nj, nl = _union(geoms[mem], nbr)
            nfloat += mode == 'float'
            nsnapto += mode == 'snapto'
            nsnap += mode == 'snap'
            nkeep += mode == 'keep'
            njoin += nj
            nleft += nl
            idx = _assign(geoms[mem], parts)
            piece_patch[mem] = len(pg) + idx
            d = abs(sum(p.area for p in parts) - float(shapely.area(geoms[mem]).sum()))
            worst = max(worst, d)
            pg.extend(parts)
            psrc.extend(mem[_rep_members(geoms[mem], parts, idx)])
        npatch = len(pg)
        pg = np.asarray(pg, dtype=object)
        p = g.iloc[psrc][KEY].reset_index(drop=True)
        for c in KEY:
            if c not in INTS:
                p[c] = p[c].astype('string')
        p.insert(0, 'tile_id', tid)
        p.insert(1, 'pidx', np.arange(npatch, dtype=np.int64))
        p.insert(2, 'khash', kh[psrc])
        area_km2 = pd.to_numeric(g['area_km2'], errors='coerce').fillna(0).to_numpy()
        gap = np.where(g['gapfill'].astype('string').fillna('').to_numpy(dtype=object) == 'sliver_nearest',
                       area_km2, 0.0)
        gc = g['coastal'].fillna(0).astype(np.int8).to_numpy()
        coastal = np.zeros(npatch, np.int8)
        np.maximum.at(coastal, piece_patch, gc)
        npc = np.bincount(piece_patch, minlength=npatch).astype(np.int64)
        orphan = npc == 0                            # a part split off by the 1 cm snap, holding no piece's point
        coastal[orphan] = gc[np.asarray(psrc, dtype=np.int64)[orphan]]
        p['coastal'] = coastal
        p['gapfill_km2'] = np.bincount(piece_patch, weights=gap, minlength=npatch)
        p['n_pieces'] = npc
        p['rep_row'] = np.asarray(psrc, dtype=np.int64)
        bnd = shapely.boundary(tile_box(tid))
        p['edge'] = shapely.dwithin(pg, bnd, EDGE)
        rp = shapely.point_on_surface(pg)
        p['rx'], p['ry'] = shapely.get_x(rp), shapely.get_y(rp)
        p['area_km2'] = shapely.area(pg) / 1e6
        out = gpd.GeoDataFrame(p, geometry=pg, crs=CRS)
        tmp = outp + '.tmp'
        out.to_parquet(tmp)
        pd.DataFrame({'row': np.arange(n, dtype=np.int64), 'pidx': piece_patch}).to_parquet(
            f'{A.out}/p1/{tid}.map.parquet', index=False)
        os.replace(tmp, outp)
        area_out = float(p['area_km2'].sum() * 1e6)
        return tid, (f'ok\t{n}\t{npatch}\t{len(groups)}\t{nfloat}\t{nsnapto}\t{nsnap}\t{int(orphan.sum())}\t{int(p["edge"].sum())}\t'
                     f'{area_in:.1f}\t{area_out:.1f}\t{worst:.3f}\t{time.time() - t0:.1f}\t{nkeep}\t{njoin}\t{nleft}')
    except Exception:
        return tid, 'ERROR\t' + traceback.format_exc().replace('\n', ' | ')[-800:]


# ---------------------------------------------------------------- pass 2
def _union_job(job):
    cid, wkbs, nbr = job
    geoms = shapely.from_wkb(wkbs)
    mode, parts, nj, nl = _union(geoms, nbr)
    idx = _assign(geoms, parts)
    rep = _rep_members(geoms, parts, idx)
    rp = shapely.point_on_surface(np.asarray(parts, dtype=object))
    d = abs(sum(p.area for p in parts) - float(shapely.area(geoms).sum()))
    return (cid, shapely.to_wkb(np.asarray(parts, dtype=object)), idx, shapely.get_x(rp), shapely.get_y(rp), d, mode,
            rep, nj, nl)


def _p1_files():
    fs = sorted(f for f in glob.glob(f'{A.out}/p1/*.parquet') if not f.endswith('.map.parquet'))
    if A.only:
        keep = set(A.only.split(','))
        fs = [f for f in fs if os.path.basename(f)[:-8] in keep]
    return fs


def pass2():
    t0 = time.time()
    files = _p1_files()
    light = ['tile_id', 'pidx', 'khash', 'edge', 'rx', 'ry', 'coastal', 'gapfill_km2', 'n_pieces', 'area_km2']
    meta = pd.concat([pd.read_parquet(f, columns=light) for f in files], ignore_index=True)
    print(f'pass 2: {len(files)} tiles, {len(meta):,} patches, {int(meta.edge.sum()):,} at a tile edge '
          f'({time.time() - t0:.0f} s)', flush=True)
    # edge patches with geometry and KEY
    parts_e = []
    for f in files:
        t = pq.read_table(f, columns=['tile_id', 'pidx', 'khash', 'coastal', 'gapfill_km2', 'n_pieces', 'rep_row',
                                      'geometry'] + KEY, filters=[('edge', '==', True)])
        if t.num_rows:
            parts_e.append(t.to_pandas())
    E = pd.concat(parts_e, ignore_index=True)
    eg = shapely.from_wkb(E['geometry'].to_numpy())
    print(f'edge patches loaded: {len(E):,} ({time.time() - t0:.0f} s)', flush=True)
    kh, tl = E['khash'].to_numpy(), E['tile_id'].to_numpy(dtype=object)
    a, b = _near_pairs(eg, kh, other=tl)
    nc, lab = _components(a, b, len(E))
    groups = _groups(lab, nc)
    nbrs = _neighbours(a, b, len(E), groups)
    print(f'cross-tile contacts {len(a):,} -> {len(groups):,} components of {sum(len(g) for g in groups):,} '
          f'patches; largest {max((len(g) for g in groups), default=0)} ({time.time() - t0:.0f} s)', flush=True)
    # union, biggest first
    nv = shapely.get_num_coordinates(eg)
    jobs = sorted(range(len(groups)), key=lambda i: -int(nv[groups[i]].sum()))
    wk = E['geometry'].to_numpy()
    res = {}
    worst = (0.0, -1)
    nfloat = nsnapto = nsnap = nkeep = njoin = nleft = 0
    with Pool(A.workers) as pool:
        for k, (cid, pw, idx, rx, ry, d, mode, rep, nj, nl) in enumerate(
                pool.imap_unordered(_union_job, ((i, list(wk[groups[i]]), nbrs[i]) for i in jobs), chunksize=1)):
            res[cid] = (pw, idx, rx, ry, rep)
            nfloat += mode == 'float'
            nsnapto += mode == 'snapto'
            nsnap += mode == 'snap'
            nkeep += mode == 'keep'
            njoin += nj
            nleft += nl
            if d > worst[0]:
                worst = (d, cid)
            if k % 20000 == 0:
                print(f'  unions {k:,}/{len(groups):,} ({time.time() - t0:.0f} s)', flush=True)
    del eg
    # every edge patch in a multi-patch component -> (cid, part q)
    cid_e = np.full(len(E), -1, np.int64)
    q_e = np.full(len(E), -1, np.int64)
    rows_b = []
    for cid, mem in enumerate(groups):
        pw, idx, rx, ry, _ = res[cid]
        cid_e[mem] = cid
        q_e[mem] = idx
        rows_b.extend((cid, q, rx[q], ry[q]) for q in range(len(pw)))
    E['cid'], E['q'] = cid_e, q_e
    EM = E.loc[cid_e >= 0, ['tile_id', 'pidx', 'cid', 'q']]
    # final table: (a) patches not in a multi-patch component, (b) union parts
    meta = meta.merge(EM, on=['tile_id', 'pidx'], how='left')
    merged = meta['cid'].notna().to_numpy()
    fa = meta.loc[~merged, ['tile_id', 'pidx', 'rx', 'ry']].copy()
    fa['cid'], fa['q'] = -1, -1
    fb = pd.DataFrame(rows_b, columns=['cid', 'q', 'rx', 'ry'])
    fb['tile_id'], fb['pidx'] = '', -1
    F = pd.concat([fa, fb], ignore_index=True)
    F['rep_tile'] = tile_of(F['rx'].to_numpy(), F['ry'].to_numpy())
    F = F.sort_values(['rep_tile', 'ry', 'rx'], ascending=[True, False, True], kind='mergesort').reset_index(drop=True)
    F['asid'] = np.arange(1, len(F) + 1, dtype=np.int64)
    print(f'final polygons {len(F):,} (kept {len(fa):,}, from unions {len(fb):,}) ({time.time() - t0:.0f} s)',
          flush=True)
    FB = F[F.cid >= 0]
    # patch -> asid, for every pass-1 patch
    pa_a = F.loc[F.cid < 0, ['tile_id', 'pidx', 'asid']]
    pa_b = EM.merge(FB[['cid', 'q', 'asid']], on=['cid', 'q'], how='left')[['tile_id', 'pidx', 'asid']]
    patch_asid = pd.concat([pa_a, pa_b], ignore_index=True)
    # attributes of union parts from their member patches
    EB = E[cid_e >= 0]
    agg = EB.groupby(['cid', 'q']).agg(coastal=('coastal', 'max'), gapfill_km2=('gapfill_km2', 'sum'),
                                        n_pieces=('n_pieces', 'sum'), n_tiles=('tile_id', 'nunique'))
    # write final/<rep_tile>.parquet in asid order
    os.makedirs(f'{A.out}/final', exist_ok=True)
    byrep_b = {t: grp for t, grp in FB.groupby('rep_tile')}
    byrep_a = {t: grp for t, grp in F[F.cid < 0].groupby('rep_tile')}
    tiles_out = sorted(set(byrep_a) | set(byrep_b))
    n_invalid, area_final, n_written = 0, 0.0, 0
    for t in tiles_out:
        frames = []
        if t in byrep_a:
            for st, sub in byrep_a[t].groupby('tile_id'):
                pp = gpd.read_parquet(f'{A.out}/p1/{st}.parquet').set_index('pidx').loc[sub['pidx'].to_numpy()]
                pp = pp.reset_index()
                pp['asid'] = sub['asid'].to_numpy()
                pp['n_tiles'] = 1
                pp['rep_tile'] = st
                frames.append(pp)
        if t in byrep_b:
            recs, geo = [], []
            for cid, q, asid in zip(byrep_b[t]['cid'], byrep_b[t]['q'], byrep_b[t]['asid']):
                cid, q = int(cid), int(q)
                fi = int(groups[cid][res[cid][4][q]])        # the part's representative member patch
                rec = {c: E.at[fi, c] for c in KEY}
                if (cid, q) in agg.index:
                    s = agg.loc[(cid, q)]
                    rec.update(coastal=int(s['coastal']), gapfill_km2=float(s['gapfill_km2']),
                               n_pieces=int(s['n_pieces']), n_tiles=int(s['n_tiles']))
                else:                  # part holding no member's point
                    rec.update(coastal=int(E.at[fi, 'coastal']), gapfill_km2=0.0, n_pieces=0, n_tiles=0)
                rec.update(asid=asid, khash=E.at[fi, 'khash'], rep_tile=E.at[fi, 'tile_id'],
                           rep_row=int(E.at[fi, 'rep_row']))
                recs.append(rec)
                geo.append(shapely.from_wkb(res[cid][0][q]))
            frames.append(gpd.GeoDataFrame(pd.DataFrame(recs), geometry=geo, crs=CRS))
        out = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry='geometry', crs=CRS)
        out = out.sort_values('asid').reset_index(drop=True)
        out['area_km2'] = out.area / 1e6
        s = out[KEY].astype('string').fillna('')
        out.insert(1, 'unit_code', [unit_code(a, b, c) for a, b, c in zip(
            out['src_id'].astype('string').fillna('none'), s['src_sheet'], s['src_code'])])
        for c in KEY:
            if c in INTS:
                out[c] = pd.to_numeric(out[c], errors='coerce').astype('Int64')
            else:
                out[c] = out[c].astype('string')
        out['coastal'] = out['coastal'].astype(np.int8)
        out['rep_tile'] = out['rep_tile'].astype('string')
        out['rep_row'] = out['rep_row'].astype(np.int64)
        # rep_tile / rep_row: the piece of the tiled version that represents the polygon (internal, for the addendum)
        cols = ['asid', 'unit_code'] + KEY + ['coastal', 'gapfill_km2', 'n_pieces', 'n_tiles', 'area_km2',
                                              'rep_tile', 'rep_row', 'geometry']
        out = out[cols]
        n_invalid += int((~shapely.is_valid(out.geometry.values)).sum())
        area_final += float(out['area_km2'].sum())
        n_written += len(out)
        out.to_parquet(f'{A.out}/final/{t}.parquet')
    print(f'written {n_written:,} polygons in {len(tiles_out)} files; invalid {n_invalid} '
          f'({time.time() - t0:.0f} s)', flush=True)
    # piece -> asid
    lut = {t: sub for t, sub in patch_asid.groupby('tile_id')}
    pa_parts = []
    for f in files:
        tid = os.path.basename(f)[:-8]
        mp = pd.read_parquet(f'{A.out}/p1/{tid}.map.parquet')
        if mp.empty:
            continue
        sub = lut[tid]
        arr = np.full(int(sub['pidx'].max()) + 1, -1, np.int64)
        arr[sub['pidx'].to_numpy(dtype=np.int64)] = sub['asid'].to_numpy(dtype=np.int64)
        asid = arr[mp['pidx'].to_numpy()]
        if (asid < 0).any():
            raise RuntimeError(f'{tid}: {int((asid < 0).sum())} pieces without asid')
        pa_parts.append(pa.table({'tile_id': pa.array([tid] * len(asid)).dictionary_encode(),
                                  'row': pa.array(mp['row'].to_numpy()), 'asid': pa.array(asid)}))
    PT = pa.concat_tables(pa_parts)
    pq.write_table(PT, f'{A.out}/piece_asid.parquet')
    area_p1 = float(meta['area_km2'].sum())
    n_used = len(np.unique(PT.column('asid').to_numpy()))
    p1c, tids = {}, {os.path.basename(f)[:-8] for f in files}     # pass-1 joins: the last 'ok' line of each tile
    for line in open(f'{A.out}/report_p1.tsv', errors='replace'):
        f = line.rstrip('\n').split('\t')
        if len(f) >= 17 and f[1] == 'ok' and f[0] in tids:
            p1c[f[0]] = (int(f[15]), int(f[16]))
    lines = [f'tiles {len(files)}', f'pieces {PT.num_rows:,}', f'pass-1 patches {len(meta):,}',
             f'final polygons {n_written:,} (asid 1..{len(F):,})',
             f'polygons holding at least one piece {n_used:,} (the rest are parts split off by the 1 cm snap)',
             f'cross-tile components {len(groups):,}; largest {max((len(g) for g in groups), default=0)} patches; '
             f'unions: {len(groups) - nfloat - nsnapto - nsnap:,} coverage, {nfloat:,} floating-point, '
             f'{nsnapto:,} snapped to the group, {nsnap:,} 1 cm snap-rounded, {nkeep:,} kept as pieces',
             f'micro-gap joins (_close): pass 1 {sum(v[0] for v in p1c.values()):,} joined, '
             f'{sum(v[1] for v in p1c.values()):,} left apart; pass 2 {njoin:,} joined, {nleft:,} left apart',
             f'area pass-1 {area_p1:,.3f} km2, final {area_final:,.3f} km2, '
             f'difference {area_final - area_p1:+.6f} km2',
             f'worst union area change {worst[0]:.3f} m2 (component {worst[1]})',
             f'invalid final geometries {n_invalid}', f'time {time.time() - t0:.0f} s']
    open(f'{A.out}/report.txt', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tiles', default=f'{ROOT}/work/final_m43')
    ap.add_argument('--out', default=f'{ROOT}/work/dissolve_m43')
    ap.add_argument('--only')
    ap.add_argument('--step', default='all', choices=['1', '2', 'all'])
    ap.add_argument('--workers', type=int, default=32)
    ap.parse_args(namespace=A)
    os.makedirs(f'{A.out}/p1', exist_ok=True)
    if A.step in ('1', 'all'):
        files = sorted(glob.glob(f'{A.tiles}/*.parquet'))
        if A.only:
            keep = set(A.only.split(','))
            files = [f for f in files if os.path.basename(f)[:-8] in keep]
        # big tiles first so the tail of the pool is short
        files.sort(key=lambda f: -os.path.getsize(f))
        t0 = time.time()
        rep = open(f'{A.out}/report_p1.tsv', 'a')
        stat = {}
        with Pool(A.workers) as pool:
            for k, (tid, msg) in enumerate(pool.imap_unordered(pass1, files, chunksize=1)):
                rep.write(f'{tid}\t{msg}\n')
                rep.flush()
                stat[msg.split()[0]] = stat.get(msg.split()[0], 0) + 1
                if k % 200 == 0:
                    print(f'pass 1: {k}/{len(files)} {time.time() - t0:.0f}s {stat}', flush=True)
        print(f'pass 1 done {stat} {time.time() - t0:.0f}s', flush=True)
        if stat.get('ERROR'):
            sys.exit('pass 1 had errors: see report_p1.tsv')
    if A.step in ('2', 'all'):
        pass2()


if __name__ == '__main__':
    main()
