#!/usr/bin/env python
"""ESSD statistics for ArcSurf merge 41 - geometry passes.

  essd_geo.py country   territory (Natural Earth 10m admin-0) of every polygon -> area by src prefix x territory,
                        U / Q / fallback area by territory (U gaps have src_id 'none' and no prefix)
  essd_geo.py overlap   tiles whose output area exceeds their land area (work/merge_tiles.log, merge 41):
                        union vs sum of polygon areas, attributed to sources and to the pf_zone / IRYP splits
Reads work/a0_tiles_m41 only; writes to work/essd_tables/.
"""
import glob
import json
import os
import re
import sys
import time
import traceback
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
D = os.environ.get('ESSD_TILES', f'{ROOT}/work/a0_tiles_m41')
O = os.environ.get('ESSD_OUT', f'{ROOT}/work/essd_tables')
CRS = 6931
MODE = sys.argv[1]
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 0
t0 = time.time()


def log(*a):
    print(f'[{time.time() - t0:7.1f}s]', *a, flush=True)


# ------------------------------------------------------------------ country
NEP = f'{ROOT}/raw/naturalearth/ne_10m_admin_0_countries.shp'
G = {}


def _init_country():
    import geopandas as gpd
    import pyogrio
    import pyproj
    ne = gpd.read_file(NEP)
    key = 'ADM0_A3' if 'ADM0_A3' in ne else 'ISO_A3'
    ne = ne[[key, 'ADMIN', 'geometry']].rename(columns={key: 'a3'})
    ne['geometry'] = shapely.intersection(shapely.make_valid(ne.geometry.values), shapely.box(-180, 40, 180, 90))
    ne = ne[~ne.geometry.is_empty].to_crs(CRS).explode(index_parts=False).reset_index(drop=True)
    ne = ne[ne.geom_type == 'Polygon'].reset_index(drop=True)
    G['ne_geom'] = ne.geometry.values
    G['ne_a3'] = ne['a3'].to_numpy()
    G['tree'] = shapely.STRtree(G['ne_geom'])
    G['to_ll'] = pyproj.Transformer.from_crs(CRS, 4326, always_xy=True)
    tiles = pyogrio.read_dataframe(f'{ROOT}/work/land_amap.gpkg', layer='tiles')
    G['tiles'] = dict(zip(tiles['tile_id'], tiles.geometry.values))


def _terr(a3, x, y):
    """Territory label; Norway split into Svalbard / Jan Mayen / mainland by position."""
    a3 = np.asarray(a3, dtype=object).copy()
    nor = a3 == 'NOR'
    if nor.any():
        lon, lat = G['to_ll'].transform(np.asarray(x)[nor], np.asarray(y)[nor])
        lab = np.where(lat >= 74.0, 'SJ_Svalbard', np.where(lon < -5.0, 'SJ_JanMayen', 'NOR'))
        a3[nor] = lab
    return a3


def country_tile(f):
    tid = os.path.basename(f)[:-8]
    try:
        tb = G['tiles'].get(tid)
        cols = ['src_id', 'hclass', 'scale_den', 'area_km2']
        hit = G['tree'].query(shapely.buffer(tb, 2000.0), predicate='intersects') if tb is not None else []
        a3s = sorted(set(G['ne_a3'][hit])) if len(hit) else []
        if len(a3s) == 1:
            t = pq.read_table(f, columns=cols).to_pandas()
            c = shapely.centroid(tb)
            t['terr'] = _terr([a3s[0]], [c.x], [c.y])[0]
            how = 'tile'
        else:
            t = pq.read_table(f, columns=cols + ['geometry']).to_pandas()
            g = shapely.from_wkb(t.pop('geometry').to_numpy())
            p = shapely.point_on_surface(g)
            idx = G['tree'].query(p, predicate='within')
            a3 = np.full(len(t), None, dtype=object)
            # first hit per point
            seen = np.zeros(len(t), bool)
            for i, j in zip(idx[0], idx[1]):
                if not seen[i]:
                    a3[i] = G['ne_a3'][j]
                    seen[i] = True
            miss = np.where(~seen)[0]
            if len(miss):
                nn = G['tree'].query_nearest(p[miss], max_distance=200_000.0, return_distance=False, all_matches=False)
                for i, j in zip(nn[0], nn[1]):
                    a3[miss[i]] = G['ne_a3'][j]
            a3 = np.where(pd.isna(a3), 'NONE', a3)
            t['terr'] = _terr(a3, shapely.get_x(p), shapely.get_y(p))
            how = 'poly'
        t['hc'] = np.where(t['hclass'] == 'U', 'U', np.where(t['hclass'] == 'Q', 'Q', 'other'))
        t['fb'] = (t['scale_den'].astype('float64') >= 2_500_000).fillna(False)
        t['src_id'] = t['src_id'].fillna('NULL')
        agg = t.groupby(['src_id', 'terr', 'hc', 'fb'], dropna=False)['area_km2'].agg(['sum', 'size']).reset_index()
        agg['tile_id'] = tid
        agg['how'] = how
        return agg
    except Exception:
        return pd.DataFrame([dict(tile_id=tid, how='ERROR ' + traceback.format_exc()[-500:])])


def run_country():
    files = sorted(glob.glob(f'{D}/*.parquet'))
    if LIMIT:
        files = files[::max(1, len(files) // LIMIT)][:LIMIT]
    out = []
    with Pool(4, initializer=_init_country) as pool:
        for k, r in enumerate(pool.imap_unordered(country_tile, files, chunksize=4)):
            out.append(r)
            if k % 250 == 0:
                log('country', k, len(files))
    res = pd.concat(out, ignore_index=True)
    err = res[res['how'].astype(str).str.startswith('ERROR')]
    log('errors', len(err))
    for e in err.itertuples():
        log(e.tile_id, e.how)
    res = res[~res['how'].astype(str).str.startswith('ERROR')]
    sfx = '_test' if LIMIT else ''
    res.to_csv(f'{O}/geo_country_by_tile{sfx}.csv.gz', index=False)
    log('tiles by how', res.groupby('how')['tile_id'].nunique().to_dict())
    res['prefix'] = res['src_id'].str.split('_').str[0]
    m = res.pivot_table(index='prefix', columns='terr', values='sum', aggfunc='sum').fillna(0)
    m['total'] = m.sum(axis=1)
    m.loc['ALL'] = m.sum()
    m.round(1).to_csv(f'{O}/geo_prefix_x_territory{sfx}.csv')
    log('prefix x territory km2\n' + m.round(0).to_string())
    t = res.pivot_table(index='terr', columns='hc', values='sum', aggfunc='sum').fillna(0)
    t['fallback_ge2.5M'] = res[res['fb']].groupby('terr')['sum'].sum()
    t['total'] = res.groupby('terr')['sum'].sum()
    t = t.fillna(0)
    t.loc['ALL'] = t.sum()
    for c in ['U', 'Q', 'fallback_ge2.5M']:
        if c in t:
            t[c + '_pct'] = 100 * t[c] / t['total']
    t.round(2).to_csv(f'{O}/geo_t7_by_territory{sfx}.csv')
    log('U / Q / fallback by territory\n' + t.round(1).to_string())
    n = res[res['src_id'] == 'none'].groupby('terr')['sum'].agg(['sum']).rename(columns={'sum': 'none_U_km2'})
    n['n_polys'] = res[res['src_id'] == 'none'].groupby('terr')['size'].sum()
    n.round(1).to_csv(f'{O}/geo_none_gaps_by_territory{sfx}.csv')
    log('src_id none (U gaps) by territory\n' + n.round(1).to_string())


# ------------------------------------------------------------------ overlap
def _u(geoms):
    geoms = [x for x in geoms if x is not None and not x.is_empty]
    if not geoms:
        return 0.0
    try:
        return shapely.union_all(geoms).area / 1e6
    except shapely.errors.GEOSException:
        gg = shapely.make_valid(shapely.set_precision(shapely.make_valid(np.asarray(geoms, dtype=object)), 0.01))
        return shapely.union_all(gg).area / 1e6


def overlap_tile(args):
    tid, land = args
    try:
        f = f'{D}/{tid}.parquet'
        t = pq.read_table(f, columns=['src_id', 'src_sheet', 'pf_zone', 'yedoma_conf', 'area_km2', 'geometry']).to_pandas()
        g = shapely.from_wkb(t.pop('geometry').to_numpy())
        nvalid = int((~shapely.is_valid(g)).sum())
        tot = float(t['area_km2'].sum())
        u_all = _u(g)
        rows = []
        for sid, idx in t.groupby('src_id', dropna=False).indices.items():
            s_sum = float(t['area_km2'].to_numpy()[idx].sum())
            u_s = _u(g[idx])
            # split groups inside the source: pf_zone x IRYP class
            sub = t.iloc[idx]
            u_groups, w_groups = 0.0, 0.0
            for _, jdx in sub.groupby(['pf_zone', 'yedoma_conf'], dropna=False).indices.items():
                gi = g[idx][jdx]
                ug = _u(gi)
                u_groups += ug
                w_groups += float(sub['area_km2'].to_numpy()[jdx].sum()) - ug
            sheets = []
            u_sheets = 0.0
            for sh, kdx in sub.groupby('src_sheet', dropna=False).indices.items():
                ush = _u(g[idx][kdx])
                u_sheets += ush
                ssum = float(sub['area_km2'].to_numpy()[kdx].sum())
                if ssum - ush > 0.01:
                    sheets.append(dict(sheet=None if pd.isna(sh) else str(sh), sum_km2=ssum, self_overlap_km2=ssum - ush))
            rows.append(dict(src_id=sid, n=len(idx), sum_km2=s_sum, union_km2=u_s,
                             self_overlap_km2=s_sum - u_s,
                             within_group_overlap_km2=w_groups,          # overlap among polygons of one zone/IRYP group
                             cross_group_overlap_km2=u_groups - u_s,     # same ground in two zone/IRYP groups
                             cross_sheet_overlap_km2=u_sheets - u_s,     # same ground in two sheets of the source
                             sheets=sheets))
        return dict(tile_id=tid, land_km2=land, n=len(t), invalid=nvalid, sum_km2=tot, union_km2=u_all,
                    excess_vs_union_km2=tot - u_all, excess_vs_land_km2=tot - land,
                    inter_source_overlap_km2=sum(r['union_km2'] for r in rows) - u_all, sources=rows)
    except Exception:
        return dict(tile_id=tid, error=traceback.format_exc()[-800:])


def run_overlap():
    L = []
    for ln in open(f'{ROOT}/work/merge_tiles.log'):
        m = re.match(r'(\S+) ok n=(\d+) land=([\d.]+) out=([\d.]+) diff=([-+\d.]+)%', ln.strip())
        if m:
            L.append((m.group(1), float(m.group(3)), float(m.group(4)), float(m.group(5))))
    todo = sorted([x for x in L if x[3] > 0.01], key=lambda x: -(x[2] - x[1]))
    if LIMIT:
        todo = todo[:LIMIT]
    log('tiles to analyse', len(todo), 'excess in them', round(sum(o - l for _, l, o, _ in todo)))
    sfx = '_test' if LIMIT else ''
    fo = open(f'{O}/geo_overlap_tiles{sfx}.jsonl', 'w')
    with Pool(4) as pool:
        for k, r in enumerate(pool.imap(overlap_tile, [(x[0], x[1]) for x in todo], chunksize=1)):
            fo.write(json.dumps(r) + '\n')
            fo.flush()
            if k % 50 == 0:
                log('overlap', k, len(todo), r.get('tile_id'), round(r.get('excess_vs_union_km2', -1), 1))
    fo.close()
    log('done')


if __name__ == '__main__':
    if MODE == 'country':
        run_country()
    elif MODE == 'overlap':
        run_overlap()
