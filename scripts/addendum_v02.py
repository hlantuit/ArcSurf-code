#!/usr/bin/env python
"""CryoGrid addendum v0.2: keyed by the persistent polygon id `asid` of the dissolved release (dissolve_release.py)
instead of the provisional tile:row keys of v0.1 (addendum_build.py, whose per-tile function this reuses).

A dissolved polygon can cross permafrost-zone, IRYP and deglaciation limits (the tiled version is cut along the first
two), so the interpretive context becomes AREA SHARES per asid, computed exactly from the tiled pieces:

  polygon_context.parquet  one row per asid: unit_code, area_km2, n_pieces, provenance (src_id, src_sheet, scale_den,
                           pub_year, conf_tier, redistribution), ice_rich (source-mapped ground ice; constant on an
                           asid), strat_index;
                           pf_continuous / pf_discontinuous / pf_sporadic / pf_isolated / pf_none (Obu et al. 2019) and
                           pf_zone_major; yed_yes / yed_uncertain / yed_no / yed_not_assessed (IRYP v2) and
                           yedoma_major; deglac_dated_share, deglac_ka_min / _max / _wmean over the dated part (ages at
                           the pieces' representative points, NADI-1 / DATED-1), deglac_status_major; lgm_ice_share
                           (Batchelor et al. 2019). A polygon split off by a snap-rounded union holds no piece and takes
                           the context of its representative piece (rep_tile, rep_row).
  piece_context.parquet    one row per piece of the tiled version: tile_id, row, asid, area_km2, pf_zone, yedoma,
                           yedoma_conf, deglac_ka, deglac_status, lgm_ice (the tiled version's link to the addendum)
  units.csv                as v0.1, n_polygons = number of asids
  parameter_classes.csv    as v0.1 (the rows CryoGrid stratigraphies are assigned to), n_polygons = asids
  summary.txt, README.txt
usage: addendum_v02.py TILES_DIR DISSOLVE_DIR OUT_DIR"""
import glob
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addendum_build as AB  # noqa: E402

TD, DD, OUT = sys.argv[1:4]
PF = ['continuous', 'discontinuous', 'sporadic', 'isolated', 'none']
YED = ['yes', 'uncertain', 'no', 'not_assessed']
FIRST = ['unit_code', 'src_id', 'src_sheet', 'scale_den', 'pub_year', 'conf_tier', 'redistribution', 'ice_rich',
         'strat_index']


def one(f):
    tid = os.path.basename(f)[:-8]
    r = AB.one(f)
    if r is None:
        return None
    ctx, units = r
    pa = pq.read_table(f'{DD}/piece_asid.parquet', columns=['row', 'asid'],
                       filters=[('tile_id', '==', tid)]).to_pandas().sort_values('row')
    if len(pa) != len(ctx) or (pa['row'].to_numpy() != np.arange(len(ctx))).any():
        raise RuntimeError(f'{tid}: piece_asid has {len(pa)} rows for {len(ctx)} pieces')
    ctx.insert(0, 'tile_id', tid)
    ctx.insert(1, 'row', np.arange(len(ctx), dtype=np.int64))
    ctx.insert(2, 'asid', pa['asid'].to_numpy())
    ctx = ctx.drop(columns=['pkey'])
    units = units.assign(tile_id=tid)
    return ctx, units


def shares(ctx, col, cats, prefix):
    t = ctx.pivot_table(index='asid', columns=col, values='area_km2', aggfunc='sum', fill_value=0.0, observed=True)
    t = t.reindex(columns=cats, fill_value=0.0)
    tot = t.sum(axis=1).replace(0, np.nan)
    s = t.div(tot, axis=0).fillna(0.0)
    s.columns = [f'{prefix}{c}' for c in cats]
    s[f'{col}_major'] = t.idxmax(axis=1).where(tot.notna(), '')
    return s


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(f'{TD}/*.parquet'))
    print(TD, len(files), 'tiles', flush=True)
    ctxs, units = [], []
    with Pool(int(os.environ.get('SLURM_CPUS_PER_TASK', '8')), initializer=AB.init) as pool:
        for i, r in enumerate(pool.imap_unordered(one, files, chunksize=4)):
            if r is not None:
                ctxs.append(r[0])
                units.append(r[1])
            if i % 500 == 0:
                print(i, flush=True)
    ctx = pd.concat(ctxs, ignore_index=True)
    piece_cols = ['tile_id', 'row', 'asid', 'area_km2', 'pf_zone', 'yedoma', 'yedoma_conf', 'deglac_ka',
                  'deglac_status', 'lgm_ice']
    pc = ctx[piece_cols].copy()
    for c in ('tile_id', 'pf_zone', 'yedoma', 'yedoma_conf', 'deglac_status'):
        pc[c] = pc[c].astype('category')
    pc.to_parquet(f'{OUT}/piece_context.parquet', index=False)
    print(f'piece_context: {len(pc):,} pieces', flush=True)

    # per asid
    g = ctx.groupby('asid', sort=True)
    P = g[FIRST].first()
    P['area_km2'] = g['area_km2'].sum()
    P['n_pieces'] = g.size()
    P = P.join(shares(ctx, 'pf_zone', PF, 'pf_')).join(shares(ctx, 'yedoma', YED, 'yed_'))
    d = ctx[ctx['deglac_status'] == 'dated']
    dg = d.assign(w=d['area_km2'] * d['deglac_ka']).groupby('asid')
    P['deglac_dated_share'] = (dg['area_km2'].sum() / P['area_km2']).reindex(P.index).fillna(0.0)
    P['deglac_ka_min'] = dg['deglac_ka'].min().reindex(P.index)
    P['deglac_ka_max'] = dg['deglac_ka'].max().reindex(P.index)
    P['deglac_ka_wmean'] = (dg['w'].sum() / dg['area_km2'].sum()).reindex(P.index)
    st = ctx.pivot_table(index='asid', columns='deglac_status', values='area_km2', aggfunc='sum', fill_value=0.0,
                         observed=True)
    P['deglac_status_major'] = st.idxmax(axis=1).reindex(P.index)
    P['lgm_ice_share'] = (ctx[ctx['lgm_ice']].groupby('asid')['area_km2'].sum() / P['area_km2']) \
        .reindex(P.index).fillna(0.0)
    P = P.reset_index()

    # polygons without a piece (split off by a snap-rounded union): context of their representative piece
    fin = pd.concat([pd.read_parquet(f, columns=['asid', 'n_pieces', 'area_km2', 'rep_tile', 'rep_row'])
                     for f in sorted(glob.glob(f'{DD}/final/*.parquet'))], ignore_index=True)
    orph = fin[~fin['asid'].isin(P['asid'])]
    if len(orph):
        key = ctx.set_index(['tile_id', 'row'])
        rows = []
        for a, area, rt, rr in zip(orph['asid'], orph['area_km2'], orph['rep_tile'], orph['rep_row']):
            s = key.loc[(rt, int(rr))]
            rec = {c: s[c] for c in FIRST}
            rec.update(asid=a, area_km2=area, n_pieces=0, pf_zone_major=s['pf_zone'], yedoma_major=s['yedoma'],
                       deglac_status_major=s['deglac_status'], lgm_ice_share=float(bool(s['lgm_ice'])),
                       deglac_dated_share=float(s['deglac_status'] == 'dated'),
                       deglac_ka_min=s['deglac_ka'], deglac_ka_max=s['deglac_ka'], deglac_ka_wmean=s['deglac_ka'])
            for z in PF:
                rec[f'pf_{z}'] = float(s['pf_zone'] == z)
            for y in YED:
                rec[f'yed_{y}'] = float(s['yedoma'] == y)
            rows.append(rec)
        P = pd.concat([P, pd.DataFrame(rows)], ignore_index=True).sort_values('asid').reset_index(drop=True)
    missing = int((~fin['asid'].isin(P['asid'])).sum())
    for c in ('unit_code', 'src_id', 'src_sheet', 'conf_tier', 'redistribution', 'ice_rich', 'strat_index',
              'pf_zone_major', 'yedoma_major', 'deglac_status_major'):
        P[c] = P[c].astype('category')
    P.to_parquet(f'{OUT}/polygon_context.parquet', index=False)

    # units and parameter classes (n_polygons = asids)
    u = pd.concat(units, ignore_index=True)
    u = u.groupby(['unit_code', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich'], as_index=False).agg(
        src_id=('src_id', 'first'), src_sheet=('src_sheet', 'first'), src_code=('src_code', 'first'),
        src_desc=('src_desc', 'first'), scale_den=('scale_den', 'min'), pub_year=('pub_year', 'max'),
        area_km2=('area_km2', 'sum'))
    n_asid = ctx.groupby('unit_code')['asid'].nunique()
    u['n_polygons'] = u['unit_code'].map(n_asid).fillna(0).astype(int)
    u['n_attribute_sets'] = u.groupby('unit_code')['unit_code'].transform('size')
    u = u.sort_values(['src_id', 'src_sheet', 'src_code', 'area_km2'], ascending=[True, True, True, False])
    u.to_csv(f'{OUT}/units.csv', index=False)
    pcl = u.groupby(['hclass', 'hclass2', 'texture', 'cover'], as_index=False).agg(
        area_km2=('area_km2', 'sum'), n_units=('unit_code', 'nunique'), n_polygons=('n_polygons', 'sum'))
    pcl = pcl.sort_values('area_km2', ascending=False)
    pcl['cum_share'] = pcl['area_km2'].cumsum() / pcl['area_km2'].sum()
    for col in ('top_m', 'waterIce', 'mineral', 'organic', 'field_capacity', 'soil_type',
                'satHydraulicConductivity', 'Xice', 'source', 'confidence'):
        pcl[col] = ''
    pcl.to_csv(f'{OUT}/parameter_classes.csv', index=False)

    tot = P['area_km2'].sum()
    lines = []
    pr = lambda t: (print(t, flush=True), lines.append(t))                         # noqa: E731
    pr(f'asids {len(P):,} (of {len(fin):,} dissolved polygons; {missing} without context); pieces {len(ctx):,}; '
       f'area {tot:,.0f} km2; native units {u["unit_code"].nunique():,}')
    pr('polygons crossing a permafrost-zone limit: '
       f'{int((P[[f"pf_{z}" for z in PF]].max(axis=1) < 0.999).sum()):,}; crossing an IRYP limit: '
       f'{int((P[[f"yed_{y}" for y in YED]].max(axis=1) < 0.999).sum()):,}')
    pr('permafrost zone by area (%): ' + ', '.join(
        f'{z} {100 * (P[f"pf_{z}"] * P["area_km2"]).sum() / tot:.1f}' for z in PF))
    pr(f'dated deglaciation by area: {100 * (P["deglac_dated_share"] * P["area_km2"]).sum() / tot:.1f} %; '
       f'LGM ice by area: {100 * (P["lgm_ice_share"] * P["area_km2"]).sum() / tot:.1f} %')
    pr(f'parameter classes {len(pcl):,}; classes covering 80 / 90 / 95 % of the area: '
       + ' / '.join(str(int((pcl['cum_share'] < p).sum()) + 1) for p in (0.8, 0.9, 0.95)))
    open(f'{OUT}/summary.txt', 'w').write('\n'.join(lines) + '\n')
    open(f'{OUT}/README.txt', 'w').write(__doc__)


if __name__ == '__main__':
    main()
