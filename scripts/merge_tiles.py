#!/usr/bin/env python
"""
Precedence merge of all crosswalked sources into one pan-Arctic layer.

Per 100 km tile (work/land_amap.gpkg:tiles):
  1. land_t   = dissolved OSM land in the tile (AMAP-clipped already)
     coast_t  = boundary(land_t) minus the tile edge  (true coastline only)
  2. every source footprint row (a sheet) touching the tile, ranked by
     (prec_scale asc, tier_rank asc, pub_year desc) -- finest first; prec_scale = scale_den except
     for non-geological sources (PREC_SCALE: soil surveys sort as 1:2M, below every surficial map)
  3. for each in rank order:
       claim  = (footprint buffered by d) & land_t - covered,  d = 0.5 mm at map scale
       take   = that sheet's units & claim
       rest   = claim - take ; parts of `rest` THINNER than 2d (buffer(-d) empty)
                are coastal/edge slivers between the source's linework and OSM's:
                they get the nearest unit's attributes, gapfill='sliver_nearest'.
                Thicker parts are genuinely unmapped here and fall to coarser sources.
       covered |= take + slivers
  4. land_t - covered  ->  hclass 'U'
  5. coastal = 1 where a polygon is within 1 m of coast_t
  5b. ice (ice_apply.apply_ice, work/ice_by_tile.gpkg): the unified glacier / ice-sheet outlines replace what lies under
     them (source class kept in hclass_under_ice; ice_src, ice_year), thin geology along the ice edge joins its
     neighbour (no slivers), source ice outside the outlines becomes 'U' with ice_note 'source_ice_outside_outline'
  6. polygons split by permafrost zone (pf_zone, Obu et al. 2019) and by the IRYP v2 yedoma
     polygons (yedoma, yedoma_conf; Strauss et al.), see split_by_zone / split_by_yedoma
Each tile is written to work/tiles/<tile_id>.parquet; --collect concatenates
them into out/arctic_surficial_geology.gpkg.

usage: merge_tiles.py <src_id,...> [--workers N] [--only TILE_ID] | --collect
"""
import argparse
import glob
import json
import os
import sys
import time
import traceback
from multiprocessing import Pool

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402
import ice_apply as IA  # noqa: E402

LAND = f'{S.WORK}/land_amap.gpkg'
XW = f'{S.WORK}/xw'
TDIR = os.environ.get('MERGE_TDIR', f'{S.WORK}/tiles')     # MERGE_TDIR: test runs (--only) that must not touch
TEST = 'MERGE_TDIR' in os.environ                          # work/tiles, merge_tiles.log or merge_sources.json
OUTP = f'{S.OUT}/arctic_surficial_geology.gpkg'
ATTR = ['src_id', 'src_sheet', 'src_code', 'src_desc', 'hclass', 'hclass2', 'texture',
        'cover', 'ice_rich', 'scale_den', 'pub_year', 'survey_years', 'conf_tier',
        'licence', 'redistribution', 'xwalk_note']
MIN_AREA = 1.0   # m2; drop numerical dust from overlays
BIG_WINNER = 10_000   # vertices: in _planarize such a winner is subtracted on its own, never unioned

SOURCES = []
FOOT = None
# Precedence scale for sources that are NOT surficial-geology maps (Hugues 2026-10-04: "surficial geology maps should
# outrank" soil surveys). They sort as if they were 1:2,000,000: after every surficial / Quaternary geology map of any
# scale (finest 1:1M), before the >= 1:2.5M fallbacks, so they only fill ground that would otherwise fall to the 1:5M.
# Only the SORT changes; scale_den (and the 0.5 mm claim buffer) stay the source's own.
PREC_SCALE = {'ca_bc_soil': 2_000_000}


def _init(sources):
    global SOURCES, FOOT
    SOURCES = sources
    fps = [pyogrio.read_dataframe(f'{XW}/{s}.gpkg', layer='footprint') for s in sources]
    FOOT = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
    FOOT['pub_year'] = FOOT['pub_year'].fillna(0)
    FOOT['d'] = 0.0005 * FOOT['scale_den'].astype(float)
    FOOT['prec_scale'] = FOOT['scale_den'].astype(float)
    for s, v in PREC_SCALE.items():
        FOOT.loc[FOOT['src_id'] == s, 'prec_scale'] = float(v)
    if 'overlay' in FOOT:
        FOOT.loc[FOOT['overlay'].fillna(0).astype(int) == 1, 'd'] = 0.0


def _clean(geoms):
    g = shapely.make_valid(np.asarray(geoms))
    # keep polygonal parts only (overlays can emit lines/points)
    out = []
    for x in g:
        if x is None or x.is_empty:
            out.append(None)
            continue
        if x.geom_type in ('Polygon', 'MultiPolygon'):
            out.append(x)
        else:
            polys = [p for p in shapely.get_parts(x) if p.geom_type in ('Polygon', 'MultiPolygon')]
            out.append(shapely.union_all(polys) if polys else None)
    return np.array(out, dtype=object)


GRID_M = 0.01


def _poly_or_empty(arr):
    """_clean returns None for empty / non-polygonal results; overlays need geometries"""
    return np.array([g if g is not None else shapely.Polygon() for g in arr], dtype=object)


def _robust(op):
    """GEOS overlay with a fallback: on TopologyException ('Ring edge missing', tile -02400_+02200) retry after
    make_valid + set_precision, polygonal parts only. Pass grid_size=GRID_M for snap-rounding where a phantom result
    must be excluded (the take intersection, below). NOT the default: snap-rounding on every overlay made the
    Svalbard tile +00300_-01200 run for hours (a 665,000-vertex land-mask coastline), 2026-10-07."""
    def f(*args, **kw):
        try:
            return op(*args, **kw)
        except shapely.errors.GEOSException:
            # make_valid BEFORE set_precision too: set_precision itself raises on an invalid
            # input ('side location conflict', tiles -01900_+01600/+01700, merge 10); keep POLYGONAL parts only:
            # the snap-rounding overlay rejects mixed-dimension input ('Overlay input is mixed-dimension',
            # Svalbard tile +00300_-01200, 2026-10-07: make_valid / snapping had left lines next to polygons)
            snap = []
            for x in args:
                if isinstance(x, shapely.Geometry) or hasattr(x, '__len__'):
                    arr = np.asarray([x] if isinstance(x, shapely.Geometry) else list(x), dtype=object)
                    y = _clean(shapely.set_precision(_poly_or_empty(_clean(arr)), GRID_M))
                    y = _poly_or_empty(y)
                    snap.append(y[0] if isinstance(x, shapely.Geometry) else y)
                else:
                    snap.append(x)
            return op(*snap, **kw)
    return f


_sinter = _robust(shapely.intersection)
_sdiff = _robust(shapely.difference)
_sunion = _robust(shapely.union_all)


DOM = f'{S.WORK}/domain_obu_amap.gpkg'


def split_by_zone(out, tid, tgeom):
    """Hugues 2026-09-30: a polygon crossed by a permafrost-zone limit becomes several
    polygons, each with pf_zone = continuous / discontinuous / sporadic / isolated / none
    (Obu et al. 2019, work/domain_obu_amap.gpkg:zones_by_tile), so a permafrost-only map is
    a filter on pf_zone. Area-conserving up to MIN_AREA slivers."""
    try:
        z = pyogrio.read_dataframe(DOM, layer='zones_by_tile', where=f"tile_id = '{tid}'")
    except Exception:
        z = None
    if z is None or z.empty:
        out['pf_zone'] = 'none'
        return out
    parts, anyz = [], []
    for zone, zz in z.groupby('zone'):
        zg = shapely.make_valid(_sunion(zz.geometry.values))
        anyz.append(zg)
        shapely.prepare(zg)
        hit = shapely.intersects(out.geometry.values, zg)
        if not hit.any():
            continue
        p = out[hit].copy()
        p['geometry'] = _clean(_sinter(p.geometry.values, zg))
        p['pf_zone'] = zone
        parts.append(p)
    allz = _sunion(anyz)
    rest = out.copy()
    rest['geometry'] = _clean(_sdiff(out.geometry.values, allz))
    rest['pf_zone'] = 'none'
    parts.append(rest)
    res = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry='geometry', crs=S.CRS)
    res = res[res.geometry.notna() & ~res.geometry.is_empty].explode(index_parts=False)
    res = res[res.geom_type == 'Polygon']
    return res[res.area >= MIN_AREA].reset_index(drop=True)


IRYP_T = f'{S.WORK}/iryp_by_tile.gpkg'
# one ice layer per tile (scripts/ice_build.py: RGI 6.0 per glacier + PROMICE 2022, gaps < 60 m closed), applied by
# ice_apply.apply_ice after precedence (decisions H. Lantuit 2026-10-01 / 2026-10-06: the ice everywhere, the source's
# class kept in hclass_under_ice, NO slivers between the ice and the geology)
ICE_T = f'{S.WORK}/ice_by_tile.gpkg'
_N60 = []


def _north60():
    """Land north of 60 N in EASE-Grid 2.0 North (polar LAEA: parallels are circles about the pole)."""
    if not _N60:
        import pyproj
        x, y = pyproj.Transformer.from_crs(4326, S.CRS, always_xy=True).transform(0.0, 60.0)
        _N60.append(shapely.Point(0.0, 0.0).buffer(float(np.hypot(x, y)), quad_segs=2048))
    return _N60[0]


def split_by_yedoma(out, tid, tgeom):
    """Hugues 2026-10-04: keep each source's own class and description (e.g. 'loessoid') and add a
    column saying whether the ground is yedoma according to the Database of Ice-Rich Yedoma
    Permafrost v2 (IRYP v2, Strauss et al. 2021/2022; work/iryp_by_tile.gpkg from iryp_tiles.py):
      yedoma = 'yes'          IRYP confirmed or likely
               'uncertain'    IRYP uncertain
               'no'           north of 60 N, outside the IRYP polygons
               'not_assessed' south of 60 N (IRYP maps north of 60 N only: absence there is not 'no')
      yedoma_conf = IRYP's own class (confirmed / likely / uncertain), '' elsewhere.
    A polygon crossed by an IRYP limit is split. Area-conserving up to MIN_AREA slivers."""
    parts, anyz = [], []
    try:
        z = pyogrio.read_dataframe(IRYP_T, layer='iryp_by_tile', where=f"tile_id = '{tid}'")
    except Exception:
        z = None
    if z is not None and not z.empty:
        for conf, zz in z.groupby('conf'):
            zg = shapely.make_valid(_sunion(zz.geometry.values))
            anyz.append(zg)
            shapely.prepare(zg)
            hit = shapely.intersects(out.geometry.values, zg)
            if not hit.any():
                continue
            p = out[hit].copy()
            p['geometry'] = _clean(_sinter(p.geometry.values, zg))
            p['yedoma'] = 'yes' if conf in ('confirmed', 'likely') else 'uncertain'
            p['yedoma_conf'] = conf
            parts.append(p)
    rest = out.copy()
    if anyz:
        rest['geometry'] = _clean(_sdiff(out.geometry.values, _sunion(anyz)))
        rest = rest[rest.geometry.notna()]
    rest['yedoma_conf'] = ''
    n60 = _sinter(_north60(), tgeom)
    if n60.is_empty:
        rest['yedoma'] = 'not_assessed'
        parts.append(rest)
    elif abs(n60.area - tgeom.area) < 1.0:
        rest['yedoma'] = 'no'
        parts.append(rest)
    elif len(rest):
        shapely.prepare(n60)
        north = rest.copy()
        north['geometry'] = _clean(_sinter(rest.geometry.values, n60))
        north['yedoma'] = 'no'
        south = rest.copy()
        south['geometry'] = _clean(_sdiff(rest.geometry.values, n60))
        south['yedoma'] = 'not_assessed'
        parts += [north, south]
    res = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), geometry='geometry', crs=S.CRS)
    res = res[res.geometry.notna() & ~res.geometry.is_empty].explode(index_parts=False)
    res = res[res.geom_type == 'Polygon']
    return res[res.area >= MIN_AREA].reset_index(drop=True)


def _planarize(take, prio):
    """Remove overlaps between the units of ONE source sheet. Merge-41 statistics (2026-10-07): 81,000 km2 counted
    twice, almost all within a sheet:
      - R-44_g3 (52,068 km2): extracted units never cut against each other (a 5,494 km2 moraine on top of a
        glaciolimnic unit);
      - scans / previews (0.3-0.6 % of each sheet): polygons simplified one by one, so neighbours overlap along
        shared edges.
    Each overlap goes to the SMALLER source unit (the detail drawn on a big unit that lacks its hole); ties by
    position. Only interior overlaps are found (overlaps / contains / within), so touching neighbours cost nothing.
    Area is conserved: the union is unchanged."""
    if len(take) < 2:
        return take
    g = take.geometry.values
    tree = shapely.STRtree(g)
    pairs = set()
    for pred in ('overlaps', 'contains', 'within'):
        a_, b_ = tree.query(g, predicate=pred)
        for x, y in zip(a_.tolist(), b_.tolist()):
            if x != y:
                pairs.add((min(x, y), max(x, y)))
    if not pairs:
        return take
    beats = {}                                   # loser -> [winners]
    for x, y in pairs:
        win, lose = (x, y) if (prio[x], x) < (prio[y], y) else (y, x)
        beats.setdefault(lose, []).append(win)
    # Exact, and fast for both shapes of the problem (tile -01900_-00300, merge 43: a 207,000-vertex bedrock polygon
    # with 2,999 holes, overlapped along its edges by thousands of small units of the same scan):
    #   - small winners are unioned and subtracted in ONE difference (the giant as a loser: one pass over it, not
    #     one per winner - subtracting them one by one ran > 25 min);
    #   - BIG winners are never unioned (union with the giant cost 1.6 s per small loser: hours) but subtracted one
    #     by one (6 ms: OverlayNG clips the big input to the loser's envelope), after a prepared covers() test
    #     (0.1 ms) that drops a loser lying wholly inside.
    # Not clip_by_rect: its 'dirty' output lost 0.5 km2 / 23 polygons on that tile (2026-10-07).
    nco = shapely.get_num_coordinates(g)
    big = nco >= BIG_WINNER
    for i in np.flatnonzero(big):
        shapely.prepare(g[i])
    newg = g.copy()
    for lose, wins in beats.items():
        x = g[lose]
        bw = [w for w in wins if big[w]]
        sw = [w for w in wins if not big[w]]
        if any(shapely.covers(g[w], x) for w in bw):
            newg[lose] = None
            continue
        if sw:
            x = _sdiff(x, g[sw[0]] if len(sw) == 1 else _sunion(g[sw]))
        for w in bw:
            if x is None or x.is_empty:
                break
            x = _sdiff(x, g[w])
        newg[lose] = _clean([x])[0] if x is not None and not x.is_empty else None
    out = take.assign(geometry=newg)
    out = out[out.geometry.notna() & ~shapely.is_empty(out.geometry.values)]
    return out[shapely.area(out.geometry.values) >= MIN_AREA]


def do_tile(row):
    tid, tgeom = row
    outp = f'{TDIR}/{tid}.parquet'
    if os.path.exists(outp):
        return tid, 'exists'
    try:
        bb = tgeom.bounds
        land = pyogrio.read_dataframe(LAND, layer='land', bbox=bb)
        if land.empty:
            return tid, 'noland'
        land_t = _sinter(_sunion(land.geometry.values), tgeom)
        land_t = shapely.make_valid(land_t)
        if land_t.is_empty:
            return tid, 'noland'
        coast_t = _sdiff(shapely.boundary(land_t),
                                     shapely.buffer(shapely.boundary(tgeom), 1.0))

        fps = FOOT[shapely.intersects(FOOT.geometry.values, tgeom)].copy()
        fps = fps.sort_values(['prec_scale', 'tier_rank', 'pub_year'],
                              ascending=[True, True, False])
        covered = shapely.Polygon()
        pieces = []
        cache = {}
        for _, f in fps.iterrows():
            d = float(f['d'])
            local = _sinter(f.geometry, shapely.buffer(tgeom, 2 * d + 1))
            claim = _sinter(shapely.buffer(local, d), land_t)
            claim = _sdiff(claim, covered)
            if claim.is_empty or claim.area < MIN_AREA:
                continue
            if not claim.is_valid:              # an INVALID claim (built from many unions / differences) made GEOS
                claim = shapely.make_valid(claim)   # return pieces OUTSIDE it: +01100_+02300 kept a 265 km2 Bryant
                claim = _clean([claim])[0]          # polygon lying in the next tile (merge 42)
                if claim is None:
                    continue
            key = f['src_id']
            if key not in cache:
                cache[key] = pyogrio.read_dataframe(
                    f'{XW}/{key}.gpkg', layer='units',
                    bbox=shapely.buffer(tgeom, 2000).bounds)
            u = cache[key]
            if f['src_sheet']:
                u = u[u['src_sheet'] == f['src_sheet']]
            u = u[shapely.intersects(u.geometry.values, claim)]
            if u.empty:
                continue
            shapely.prepare(claim)
            # 1 cm snap-rounding HERE: the floating-point overlay of GEOS 3.14.1 returned a PHANTOM 630 km2
            # intersection for a valid Bryant polygon x a valid claim that only TOUCH (+01100_+02300, merge 42):
            # 265 km2 outside the tile, ~1,100 km2 overlapping other sources across the merge
            g = _clean(_sinter(u.geometry.values, claim, grid_size=GRID_M))
            take = u.assign(geometry=g)
            take = take[take.geometry.notna()]
            take = take[shapely.area(take.geometry.values) >= MIN_AREA]
            # one sheet's own units must not overlap: priority = area of the FULL source unit (same order in every tile)
            prio = pd.Series(shapely.area(u.geometry.values), index=u.index).loc[take.index].values
            take = _planarize(take, prio)
            take['gapfill'] = ''
            took = _sunion(take.geometry.values)
            rest = _sdiff(claim, took)
            filled = []
            if not rest.is_empty and d > 0:
                parts = [p for p in shapely.get_parts(rest) if p.area >= MIN_AREA]
                thin = [p for p in parts if shapely.buffer(p, -d).is_empty]
                if thin:
                    tree = shapely.STRtree(take.geometry.values)
                    tgt = tree.query_nearest(thin, max_distance=d * 2, return_distance=False)
                    # tgt: [input_idx, tree_idx]; first hit per sliver
                    seen = {}
                    for i, j in zip(tgt[0], tgt[1]):
                        seen.setdefault(int(i), int(j))
                    if seen:
                        sl = take.iloc[[seen[i] for i in sorted(seen)]].copy()
                        sl['geometry'] = [thin[i] for i in sorted(seen)]
                        sl['gapfill'] = 'sliver_nearest'
                        filled.append(sl)
            pieces.append(take)
            pieces.extend(filled)
            covered = _sunion([covered, took] + [x for s in filled for x in s.geometry.values])
        gaps = _sdiff(land_t, covered)
        gparts = [p for p in shapely.get_parts(gaps) if p.area >= MIN_AREA] if not gaps.is_empty else []
        if gparts:
            gp = gpd.GeoDataFrame({c: None for c in ATTR}, index=range(len(gparts)),
                                  geometry=gparts, crs=S.CRS)
            gp['hclass'] = 'U'
            gp['src_id'] = 'none'
            gp['gapfill'] = ''
            pieces.append(gp)
        if not pieces:
            return tid, 'empty'
        out = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), geometry='geometry', crs=S.CRS)
        # footprint claims are disjoint by construction, yet ~1,100 km2 overlapped BETWEEN sources in merge 41 (a union
        # of invalid takes can come out short, and the next claim then reaches into it). The pieces are in rank order,
        # so the earlier-ranked piece keeps the overlap; U gaps come last.
        # nothing may leave the tile (safety net for any remaining overlay phantom)
        inside = shapely.within(out.geometry.values, shapely.buffer(tgeom, 0.5))
        if not inside.all():
            gg = np.array(out.geometry.values, dtype=object)
            gg[~inside] = _clean(_sinter(gg[~inside], tgeom, grid_size=GRID_M))
            out = out.assign(geometry=gg)
            out = out[out.geometry.notna()]
        out = _planarize(out, np.arange(len(out), dtype=float))
        out = out[[c for c in ATTR if c in out] + ['gapfill', 'geometry']]
        out = out.explode(index_parts=False)
        out = out[out.geom_type == 'Polygon']
        out = out[out.area >= MIN_AREA].reset_index(drop=True)
        shapely.prepare(coast_t)
        out['coastal'] = shapely.dwithin(out.geometry.values, coast_t, 1.0).astype('int8') \
            if not coast_t.is_empty else np.int8(0)
        ice_msg = ''
        if os.path.exists(ICE_T):
            ice = pyogrio.read_dataframe(ICE_T, layer='ice', where=f"tile_id = '{tid}'")
            if not ice.empty or (out['hclass'] == 'I').any():     # also tiles with source ice but no inventory ice
                try:
                    out, _irep = IA.apply_ice(out, tgeom, ice)
                except Exception:          # keep the tile without the override, flagged (never lose a tile)
                    out['ice_note'] = 'ice_override_failed'
                    ice_msg = ' ICE_ERROR ' + traceback.format_exc().replace(chr(10), ' | ')[-300:]
        for c in IA.ICE_COLS:
            if c not in out:
                out[c] = pd.NA if c == 'ice_year' else ''
        out = split_by_zone(out, tid, tgeom)
        out = split_by_yedoma(out, tid, tgeom)
        out['tile_id'] = tid
        out['area_km2'] = out.area / 1e6
        # attribute dtypes consistent across tiles
        for c in ATTR + ['gapfill', 'pf_zone', 'yedoma', 'yedoma_conf'] + IA.ICE_COLS:
            if c in ('scale_den', 'pub_year', 'ice_year'):
                out[c] = pd.to_numeric(out[c], errors='coerce').astype('Int64')
            else:
                out[c] = out[c].astype('string')
        out = out[_ordered(out.columns)]
        tmp = outp + '.tmp'
        out.to_parquet(tmp)
        os.replace(tmp, outp)
        land_a, got = land_t.area, out.area.sum()
        return tid, f'ok n={len(out)} land={land_a/1e6:.1f} out={got/1e6:.1f} diff={100*(got-land_a)/land_a:+.3f}%{ice_msg}'
    except Exception:
        return tid, 'ERROR ' + traceback.format_exc().replace('\n', ' | ')[-800:]


COLS = ATTR + ['gapfill', 'coastal', 'pf_zone', 'yedoma', 'yedoma_conf', 'hclass_under_ice', 'ice_src', 'ice_year', 'ice_note',
               'tile_id', 'area_km2']


def _ordered(cols):
    """One fixed column order for every tile: pyogrio's GPKG append maps fields BY POSITION, so a tile
    whose columns come in another order writes its values into the wrong fields (merge 36: split_by_yedoma
    created yedoma / yedoma_conf in either order, and 'yedoma' came out 'confirmed' or '' on half the tiles)."""
    cols = list(cols)
    return [c for c in COLS if c in cols] + sorted(c for c in cols if c not in COLS and c != 'geometry') + ['geometry']


def collect():
    files = sorted(glob.glob(f'{TDIR}/*.parquet'))
    print(f'collecting {len(files)} tiles')
    if os.path.exists(OUTP):
        os.remove(OUTP)
    os.makedirs(S.OUT, exist_ok=True)
    n = 0
    schema = None
    for i, f in enumerate(files):
        g = gpd.read_parquet(f)
        g = g[_ordered(g.columns)]
        if schema is None:
            schema = list(g.columns)
        # every tile must match the first tile's columns exactly (same names, same order)
        g = g.reindex(columns=schema)
        pyogrio.write_dataframe(g, OUTP, layer='surficial', driver='GPKG',
                                append=os.path.exists(OUTP), promote_to_multi=False)
        n += len(g)
        if i % 200 == 0:
            print(i, n, flush=True)
    print('rows', n)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('sources', nargs='?')
    ap.add_argument('--workers', type=int, default=32)
    ap.add_argument('--only')
    ap.add_argument('--collect', action='store_true')
    a = ap.parse_args()
    if a.collect:
        collect()
        return
    sources = a.sources.split(',')
    # preflight: a missing crosswalked source made EVERY worker crash per tile for
    # 1 h 40 (build_xw had failed; run_py.sh then masked the exit code). Refuse to start.
    missing = [s for s in sources if not os.path.exists(f'{S.WORK}/xw/{s}.gpkg')]
    if missing:
        sys.exit(f'merge_tiles: no work/xw/<src>.gpkg for {missing} - run build_xw.py first')
    os.makedirs(TDIR, exist_ok=True)
    tiles = pyogrio.read_dataframe(LAND, layer='tiles')
    if a.only:
        tiles = tiles[tiles['tile_id'].isin(a.only.split(','))]
    rows = list(zip(tiles['tile_id'], tiles.geometry.values))
    # big tiles first so the tail of the pool is short
    order = np.argsort(-tiles['land_km2'].values)
    rows = [rows[i] for i in order]
    t0 = time.time()
    log = open(f'{TDIR}/merge_tiles.log' if TEST else f'{S.WORK}/merge_tiles.log', 'a')
    stat = {}
    with Pool(a.workers, initializer=_init, initargs=(sources,)) as pool:
        for k, (tid, msg) in enumerate(pool.imap_unordered(do_tile, rows, chunksize=1)):
            log.write(f'{tid} {msg}\n')
            log.flush()
            stat[msg.split()[0]] = stat.get(msg.split()[0], 0) + 1
            if k % 100 == 0:
                print(k, len(rows), f'{time.time()-t0:.0f}s', stat, flush=True)
    print('done', stat, f'{time.time()-t0:.0f}s')
    if not TEST:
        with open(f'{S.WORK}/merge_sources.json', 'w') as f:
            json.dump(sources, f)


if __name__ == '__main__':
    main()
