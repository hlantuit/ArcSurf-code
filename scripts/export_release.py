#!/usr/bin/env python
"""Release GeoPackages of ArcSurf, split by licence for PANGAEA (H. Lantuit 2026-10-08: the GEUS-derived Greenland
layer was CC BY-SA 4.0 and went into a file of its own; since GEUS granted CC BY 4.0 on 2026-10-22, patch_licence_open.py
marks it open and it is part of the CC BY file, so no CC BY-SA file is written; everything that may be redistributed
is CC BY 4.0; restricted sources are not released, and their areas are marked as not released rather than as unmapped).

Inputs, both after the licence patches (patch_licence_geus.py):
  the release geometry    <dissolve>/final/*.parquet and <dissolve>/piece_asid.parquet (dissolve_release.py)
  the tiled geometry      <tiles>/*.parquet (final_<tag>: pieces cut at the 100 km tiles and at the permafrost-zone
                          and IRYP limits; 'row' in piece_asid = position of the piece in its tile's parquet)

  <out>/<name>_CC-BY-4.0.gpkg
      arcsurf              release geometry: polygons whose source is open (redistribution 'open') and land without
                           a source (class U, no licence)
      arcsurf_tiled        the same polygons in the tiled geometry, with tile_id and the asid of their polygon
      licence_gaps         one polygon per source sheet whose polygons are NOT in this file, with the reason
                           (released under CC BY-SA 4.0 in the Greenland dataset / not released), the citation fields
                           of the source and the area; no geology
  <out>/<name>_Greenland_CC-BY-SA-4.0.gpkg
      arcsurf_greenland, arcsurf_greenland_tiled   the same for redistribution 'open_sa' (GEUS-derived)
  <out>/<name>_full_INTERNAL.gpkg (--full)          every polygon of the release geometry: NOT for distribution
  <out>/release_report.txt                          features and area per file and layer; checks

Columns: Table 4 of the data paper. Left out (they are in the addendum): ice_rich, pf_zone, yedoma, yedoma_conf;
internal to the dissolve: n_pieces, n_tiles, rep_tile, rep_row, khash.
Checks: every polygon and every piece goes to exactly one layer; per file, the asids of the two geometries are the
same set and their areas agree; nothing 'internal_only' or 'unknown' is written to a public file.
usage: export_release.py TAG [--dissolve DIR] [--tiles DIR] [--out DIR] [--name NAME] [--only T1,T2] [--full]
                             [--workers N]"""
import argparse
import glob
import hashlib
import os
import sys
import time
from collections import defaultdict
from multiprocessing import Pool

import numpy as np
import pandas as pd
import geopandas as gpd
import pyarrow.parquet as pq
import pyogrio
import shapely

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
CRS = 'EPSG:6931'
GEOL = ['hclass', 'hclass2', 'texture', 'cover', 'src_id', 'src_sheet', 'src_code', 'src_desc', 'scale_den',
        'pub_year', 'survey_years', 'conf_tier', 'licence', 'xwalk_note']     # 'redistribution' only steers the split
GLAC = ['hclass_under_ice', 'ice_src', 'ice_year', 'ice_note']
REL_COLS = ['asid', 'unit_code'] + GEOL + ['gapfill_km2', 'coastal'] + GLAC + ['area_km2', 'geometry']
TIL_COLS = ['asid', 'unit_code'] + GEOL + ['gapfill', 'coastal'] + GLAC + ['tile_id', 'area_km2', 'geometry']
GAP_COLS = ['src_id', 'src_sheet', 'scale_den', 'pub_year', 'licence', 'redistribution', 'reason', 'n_polygons',
            'area_km2', 'geometry']
INTS = ('scale_den', 'pub_year', 'ice_year')
REASON = {'open_sa': 'released under CC BY-SA 4.0 in the ArcSurf Greenland dataset (derived from GEUS maps)',
          'internal_only': 'not released: the terms of the source do not permit redistribution',
          'unknown': 'not released: the terms of the source are not yet established',
          '': 'not released: no licence recorded'}
PUBLIC = {'by': {'open', ''}, 'sa': {'open_sa'}}      # the only redistribution values each public file may hold
A = argparse.Namespace()
PIECE_ASID = {}                     # tile_id -> asid per row of the tile's parquet (filled before the pool forks)


def unit_code(src, sheet, code):
    """= dissolve_release.unit_code = addendum_build.unit_code"""
    return 'U' + hashlib.sha1(f'{src}|{sheet}|{code}'.encode('utf-8')).hexdigest()[:12]


def target(df):
    """'by', 'sa' or 'gap' for every row. Land without a source (class U, no licence) is ArcSurf's own and open, and so
    is glacier ice laid on land without a source (class I, outlines of RGI 6.0 and PROMICE-2022, both CC BY 4.0; merge 46:
    623 polygons, 20,007 km2, mostly ice caps of the Russian Arctic that the sheets leave blank)."""
    red = df['redistribution'].astype('string').fillna('').to_numpy(dtype=object)
    hc = df['hclass'].astype('string').fillna('').to_numpy(dtype=object)
    out = np.full(len(df), 'gap', dtype=object)
    out[red == 'open'] = 'by'
    out[red == 'open_sa'] = 'sa'
    out[(red == '') & ((hc == 'U') | (hc == 'I'))] = 'by'
    return out, red


def typed(df, cols):
    """one schema for every chunk: pyogrio appends BY POSITION, so the column order must never vary"""
    df = df.copy()
    for c in cols:
        if c == 'geometry':
            continue
        if c not in df:
            df[c] = pd.NA
        if c in INTS:
            df[c] = pd.to_numeric(df[c], errors='coerce').round().astype('Int64')
        elif c in ('asid', 'n_polygons'):
            df[c] = df[c].astype(np.int64)
        elif c == 'coastal':
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(np.int16)
        elif c in ('area_km2', 'gapfill_km2'):
            df[c] = pd.to_numeric(df[c], errors='coerce').astype(np.float64)
        else:
            df[c] = df[c].astype('string')
    return gpd.GeoDataFrame(df[cols], geometry='geometry', crs=CRS)


def _union(geoms):
    """union of the polygons of one source sheet (a coverage when the dissolve kept it exact)"""
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return None
    if len(geoms) == 1:
        return geoms[0]
    arr = np.array(geoms, dtype=object)
    try:
        if shapely.coverage_is_valid(arr):
            u = shapely.coverage_union_all(arr)
            if u.is_valid:
                return u
    except Exception:
        pass
    # GEOS can raise a TopologyException on near-coincident edges (merge 45, sheet outlines): ever more robust unions,
    # and as the last resort the parts themselves as one MultiPolygon (an outline layer needs no dissolve)
    for f in (lambda a: shapely.union_all(a, grid_size=0.01),
              lambda a: shapely.union_all(shapely.make_valid(a), grid_size=0.01),
              lambda a: shapely.union_all(shapely.buffer(shapely.make_valid(a), 0.0)),
              lambda a: shapely.union_all(a, grid_size=0.5)):
        try:
            u = f(arr)
            if u is not None and not u.is_empty:
                return u
        except shapely.errors.GEOSException:
            continue
    parts = [p for g in arr for p in shapely.get_parts(g) if p.geom_type == 'Polygon']
    return shapely.multipolygons(parts)


def gap_parts(df, red):
    """per (src_id, src_sheet, redistribution, licence): the union of the rows and their counts"""
    out = []
    keys = ['src_id', 'src_sheet', 'licence']
    d = df[keys + ['scale_den', 'pub_year', 'area_km2']].copy()
    for c in keys:
        d[c] = d[c].astype('string').fillna('')
    d['red'] = red
    d['geom'] = df.geometry.values
    for k, g in d.groupby(keys + ['red'], sort=False):
        u = _union(list(g['geom']))
        if u is None:
            continue
        out.append(dict(src_id=k[0], src_sheet=k[1], licence=k[2], redistribution=k[3],
                        scale_den=pd.to_numeric(g['scale_den'], errors='coerce').max(),
                        pub_year=pd.to_numeric(g['pub_year'], errors='coerce').max(),
                        n_polygons=len(g), area_km2=float(g['area_km2'].sum()), wkb=shapely.to_wkb(u)))
    return out


def _init(piece_asid, args):
    """worker state; with fork the arguments are inherited, not copied"""
    global PIECE_ASID
    PIECE_ASID = piece_asid
    A.__dict__.update(args)


def one(rep_tile):
    """the release polygons whose representative point lies in rep_tile, and the pieces of the tiled geometry in
    the tile of the same name"""
    res = {'tile': rep_tile, 'rel': {}, 'til': {}, 'gaps': [], 'n_rel': 0, 'n_til': 0, 'a_rel': 0.0, 'a_til': 0.0,
           'norec': 0, 'full': None}
    f = f'{A.dissolve}/final/{rep_tile}.parquet'
    if os.path.exists(f):
        g = gpd.read_parquet(f)
        if len(g):
            g['area_km2'] = pd.to_numeric(g['area_km2'], errors='coerce')
            tgt, red = target(g)
            res['n_rel'], res['a_rel'] = len(g), float(g['area_km2'].sum())
            res['norec'] += int(((red == '') & (tgt == 'gap')).sum())
            for t in ('by', 'sa'):
                m = tgt == t
                if m.any():
                    res['rel'][t] = typed(g[m], REL_COLS)
                    bad = set(red[m]) - PUBLIC[t]
                    if bad:
                        raise RuntimeError(f'{rep_tile}: redistribution {bad} would go into the {t} file')
            if (tgt == 'gap').any() or (tgt == 'sa').any():
                m = tgt != 'by'
                res['gaps'] = gap_parts(g[m], red[m])
            if A.full:
                res['full'] = typed(g, REL_COLS)
    f = f'{A.tiles}/{rep_tile}.parquet'
    if os.path.exists(f):
        p = gpd.read_parquet(f)
        if len(p):
            asid = PIECE_ASID.get(rep_tile)
            if asid is None or len(asid) != len(p):
                raise RuntimeError(f'{rep_tile}: {len(p)} pieces but {0 if asid is None else len(asid)} asids')
            p['asid'] = asid
            s = p[['src_id', 'src_sheet', 'src_code']].astype('string')
            p['unit_code'] = [unit_code(a, b, c) for a, b, c in zip(
                s['src_id'].fillna('none'), s['src_sheet'].fillna(''), s['src_code'].fillna(''))]
            p['tile_id'] = rep_tile
            p['area_km2'] = p.area / 1e6
            tgt, red = target(p)
            res['n_til'], res['a_til'] = len(p), float(p['area_km2'].sum())
            for t in ('by', 'sa'):
                m = tgt == t
                if m.any():
                    res['til'][t] = typed(p[m], TIL_COLS)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('--dissolve')
    ap.add_argument('--tiles')
    ap.add_argument('--out')
    ap.add_argument('--name')
    ap.add_argument('--only')
    ap.add_argument('--full', action='store_true')
    ap.add_argument('--workers', type=int, default=int(os.environ.get('SLURM_CPUS_PER_TASK', '8')))
    ap.parse_args(namespace=A)
    A.dissolve = A.dissolve or f'{ROOT}/work/dissolve_{A.tag}'
    A.tiles = A.tiles or f'{ROOT}/work/final_{A.tag}'
    A.out = A.out or f'{ROOT}/work/release_{A.tag}'
    A.name = A.name or f'ArcSurf_{A.tag}'
    os.makedirs(A.out, exist_ok=True)
    t0 = time.time()

    pa_t = pq.read_table(f'{A.dissolve}/piece_asid.parquet').to_pandas()
    pa_t['tile_id'] = pa_t['tile_id'].astype(str)
    for tid, sub in pa_t.groupby('tile_id', sort=False):
        arr = np.full(int(sub['row'].max()) + 1, -1, np.int64)
        arr[sub['row'].to_numpy()] = sub['asid'].to_numpy()
        if (arr < 0).any():
            sys.exit(f'{tid}: piece_asid has gaps in its rows')
        PIECE_ASID[tid] = arr
    n_pieces_total = len(pa_t)
    del pa_t
    tiles = sorted({os.path.basename(f)[:-8] for f in glob.glob(f'{A.dissolve}/final/*.parquet')} |
                   {os.path.basename(f)[:-8] for f in glob.glob(f'{A.tiles}/*.parquet')})
    if A.only:
        keep = set(A.only.split(','))
        tiles = [t for t in tiles if t in keep]
    print(f'{len(tiles)} tiles; {n_pieces_total:,} pieces in piece_asid ({time.time() - t0:.0f} s)', flush=True)

    files = {'by': f'{A.out}/{A.name}_CC-BY-4.0.gpkg', 'sa': f'{A.out}/{A.name}_Greenland_CC-BY-SA-4.0.gpkg',
             'full': f'{A.out}/{A.name}_full_INTERNAL.gpkg'}
    layers = {('by', 'rel'): 'arcsurf', ('by', 'til'): 'arcsurf_tiled', ('sa', 'rel'): 'arcsurf_greenland',
              ('sa', 'til'): 'arcsurf_greenland_tiled', ('full', 'rel'): 'arcsurf_full'}
    for f in files.values():
        if os.path.exists(f):
            os.remove(f)
    created = set()
    cnt = defaultdict(int)
    area = defaultdict(float)
    asids = defaultdict(list)
    pairs = defaultdict(list)
    gaps = defaultdict(list)
    n_rel = n_til = norec = 0
    a_rel = a_til = 0.0

    def write(df, fkey, gkey):
        lay = layers[(fkey, gkey)]
        pyogrio.write_dataframe(df, files[fkey], layer=lay, driver='GPKG', promote_to_multi=False,
                                append=(fkey, lay) in created)
        created.add((fkey, lay))
        cnt[(fkey, lay)] += len(df)
        area[(fkey, lay)] += float(df['area_km2'].sum())
        a = df['asid'].to_numpy(dtype=np.int64)
        asids[(fkey, gkey)].append(a)
        # fingerprint of the (asid, unit_code) pairs: the unit code must agree between the two geometries
        hu = pd.util.hash_array(df['unit_code'].astype(str).to_numpy(dtype=object)).astype(np.uint64)
        pairs[(fkey, gkey)].append(np.unique(hu ^ (a.astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15))))

    with Pool(A.workers, initializer=_init, initargs=(PIECE_ASID, dict(vars(A)))) as pool:
        for k, r in enumerate(pool.imap(one, tiles, chunksize=4)):
            n_rel += r['n_rel']
            n_til += r['n_til']
            a_rel += r['a_rel']
            a_til += r['a_til']
            norec += r['norec']
            for t, df in r['rel'].items():
                write(df, t, 'rel')
            for t, df in r['til'].items():
                write(df, t, 'til')
            if r['full'] is not None:
                write(r['full'], 'full', 'rel')
            for x in r['gaps']:
                gaps[(x['src_id'], x['src_sheet'], x['licence'], x['redistribution'])].append(x)
            if k % 200 == 0:
                print(f'  {k}/{len(tiles)} tiles; release {n_rel:,}, tiled {n_til:,} ({time.time() - t0:.0f} s)',
                      flush=True)

    # licence gaps: one polygon per source sheet not in the CC BY file
    rows = []
    for (src, sheet, lic, red), parts in gaps.items():
        u = _union([shapely.from_wkb(x['wkb']) for x in parts])
        rows.append(dict(src_id=src, src_sheet=sheet, licence=lic, redistribution=red,
                         reason=REASON.get(red, f'not released: redistribution {red!r}'),
                         scale_den=max((x['scale_den'] for x in parts if pd.notna(x['scale_den'])), default=pd.NA),
                         pub_year=max((x['pub_year'] for x in parts if pd.notna(x['pub_year'])), default=pd.NA),
                         n_polygons=sum(x['n_polygons'] for x in parts),
                         area_km2=sum(x['area_km2'] for x in parts), geometry=u))
    if rows:
        G = typed(pd.DataFrame(rows).sort_values(['redistribution', 'src_id', 'src_sheet']), GAP_COLS)
        pyogrio.write_dataframe(G, files['by'], layer='licence_gaps', driver='GPKG', promote_to_multi=True,
                                append=False)
        cnt[('by', 'licence_gaps')] = len(G)
        area[('by', 'licence_gaps')] = float(G['area_km2'].sum())

    # checks
    lines = [f'{A.name}: release geometry {n_rel:,} polygons, {a_rel:,.1f} km2; tiled geometry {n_til:,} pieces, '
             f'{a_til:,.1f} km2 ({n_pieces_total:,} in piece_asid)']
    for (fk, lay), n in sorted(cnt.items()):
        lines.append(f'  {os.path.basename(files[fk])} / {lay}: {n:,} features, {area[(fk, lay)]:,.1f} km2')
    ok = True
    U = {k: np.unique(np.concatenate(v)) if v else np.zeros(0, np.int64) for k, v in asids.items()}
    # release polygons that hold no piece (parts split off by the 1 cm snap, reported by the dissolve) exist only in the
    # release geometry; the two geometries must agree on every other polygon
    piece_ids = np.unique(np.concatenate(list(PIECE_ASID.values()))) if PIECE_ASID else np.zeros(0, np.int64)
    for t in ('by', 'sa'):
        a, b = U.get((t, 'rel'), np.zeros(0, np.int64)), U.get((t, 'til'), np.zeros(0, np.int64))
        pieceless = np.setdiff1d(a, piece_ids)
        same = bool(np.array_equal(np.setdiff1d(a, pieceless), b))
        if A.only is None:                  # a test on some tiles cuts polygons whose pieces lie in other tiles
            ok &= same
        lines.append(f'  check {t}: asids of the two geometries identical apart from {len(pieceless):,} release polygons '
                     f'without a piece: {same} ({len(a):,} vs {len(b):,})')
        pr = [np.unique(np.concatenate(pairs[(t, g)])) if pairs.get((t, g)) else np.zeros(0, np.uint64)
              for g in ('rel', 'til')]
        same_uc = bool(np.isin(pr[1], pr[0]).all()) and len(pr[0]) - len(pr[1]) == len(pieceless)
        if A.only is None:
            ok &= same_uc
        lines.append(f'  check {t}: unit codes of the two geometries agree: {same_uc}')
        dup = sum(len(x) for x in asids.get((t, 'rel'), [])) - len(a)
        ok &= dup == 0
        lines.append(f'  check {t}: release polygons written once: {dup == 0}')
        ar = area[(t, layers[(t, 'rel')])] if (t, layers[(t, 'rel')]) in area else 0.0
        at = area[(t, layers[(t, 'til')])] if (t, layers[(t, 'til')]) in area else 0.0
        lines.append(f'  check {t}: area release {ar:,.3f} km2, tiled {at:,.3f} km2, difference {ar - at:+.3f} km2')
    if A.only is None:
        ok &= n_til == n_pieces_total
        lines.append(f'  check: every piece exported or withheld exactly once: {n_til == n_pieces_total}')
    leaked = np.intersect1d(U.get(('by', 'rel'), np.zeros(0, np.int64)), U.get(('sa', 'rel'), np.zeros(0, np.int64)))
    ok &= len(leaked) == 0
    lines.append(f'  check: no polygon in both public files: {len(leaked) == 0}')
    gap_area = area.get(('by', 'licence_gaps'), 0.0)
    pub = area.get(('by', 'arcsurf'), 0.0) + area.get(('sa', 'arcsurf_greenland'), 0.0)
    lines.append(f'  public {pub:,.1f} km2 ({100 * pub / a_rel if a_rel else 0:.2f} %), of it CC BY-SA '
                 f'{area.get(("sa", "arcsurf_greenland"), 0.0):,.1f} km2; licence gaps incl. Greenland '
                 f'{gap_area:,.1f} km2; rows without a licence record {norec:,}')
    for f in files.values():
        if os.path.exists(f):
            lines.append(f'  {os.path.basename(f)}: {os.path.getsize(f) / 1e9:.2f} GB')
    lines.append(f'checks {"PASSED" if ok else "FAILED"}; time {time.time() - t0:.0f} s')
    open(f'{A.out}/release_report.txt', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)
    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
