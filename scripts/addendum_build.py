#!/usr/bin/env python
"""CryoGrid addendum v0.1 (H. Lantuit 2026-10-07: "now is the time, please add the addendum"): the keys and the
context that permafrost modelling needs, built from the final merge (work/final_m43), WITHOUT parameter values
(those come from the literature / the InICE sample database in later versions, keyed to what is built here).

  units.csv              one row per native unit: unit_code (stable: 'U' + 12 hex of sha1(src_id|src_sheet|
                         src_code); same native unit -> same code in every release), the harmonised atomic
                         attributes (hclass genesis, hclass2, texture, cover), source-mapped ground ice, source
                         scale and year, area and polygon count                                   (requirements 1, 2)
  polygon_context.parquet one row per polygon of the release: pkey (tile_id:row, provisional until persistent
                         polygon ids exist), unit_code, area, provenance (source, sheet, scale, year, confidence,
                         redistribution), deglaciation age at the polygon's representative point (NADI-1 OPTIMAL,
                         Dalton et al. 2023; DATED-1 most credible, Hughes et al. 2016) with its status, LGM ice
                         (Batchelor et al. 2019), and the interpretive context moved out of the geology: permafrost
                         zone (Obu et al. 2019), ice_rich as mapped by the source, IRYP v2 Yedoma; plus the
                         native stratigraphic index of Russian units (src_code)               (requirements 5, 6, 7)
  parameter_classes.csv  the distinct (hclass, hclass2, texture, cover) combinations with their area, ranked:
                         the rows to which CryoGrid stratigraphies are assigned; value columns left empty
  summary.txt            coverage of every field by area (printed too)
usage: addendum_build.py [TILES_DIR] [OUT_DIR]"""
import glob
import hashlib
import os
import re
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
TD = sys.argv[1] if len(sys.argv) > 1 else f'{ROOT}/work/final_m43'
OUT = sys.argv[2] if len(sys.argv) > 2 else f'{ROOT}/work/addendum_v01'
BM = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/basemap'
LGM_SHP = f'{BM}/lgm/LGM_best_estimate.shp'
TILE = 100_000
G = {}
# native stratigraphic index of Russian units: Roman stage (I-IV, with sub-stage digits) or H (Holocene), as written
RU_INDEX = re.compile(r'(IV|III|II|I)(\d(?:-\d)?)?(?:-(IV|III|II|I)(\d)?)?|(?<![A-Za-z])H(?![a-z])')


def unit_code(src, sheet, code):
    return 'U' + hashlib.sha1(f'{src}|{sheet}|{code}'.encode('utf-8')).hexdigest()[:12]


def _read(p):
    """isochrone / LGM shapefile -> one prepared geometry in EPSG:6931 (raw WKB, unclosed rings repaired)"""
    meta, _, wkb, _ = pyogrio.raw.read(p, read_geometry=True)
    geoms = shapely.from_wkb(wkb, on_invalid='fix')
    s = gpd.GeoSeries(geoms[[q is not None for q in geoms]], crs=meta['crs']).to_crs(6931)
    parts = shapely.get_parts(shapely.make_valid(shapely.force_2d(s.values)))
    g = shapely.union_all([q for q in parts if q.geom_type in ('Polygon', 'MultiPolygon')], grid_size=1.0)
    shapely.prepare(g)
    return g


def init():
    sl = []
    for p in glob.glob(f'{BM}/deglac/nadi1/*/*ka_cal_OPTIMAL_NADI-1_Dalton_etal_QSR.shp'):
        sl.append((float(os.path.basename(p).split('ka_cal')[0]), p))
    for p in glob.glob(f'{BM}/deglac/dated1/*/TS*_mc.shp'):
        m = re.match(r'TS(\d+)_mc\.shp$', os.path.basename(p))
        if m:
            sl.append((float(m.group(1)), p))
    G['slices'] = [(t, _read(p)) for t, p in sorted(sl, key=lambda s: -s[0])]      # oldest first
    G['lgm'] = _read(LGM_SHP) if os.path.exists(LGM_SHP) else None


def ru_index(code):
    m = RU_INDEX.search(code or '')
    return m.group(0) if m else ''


def one(f):
    tid = os.path.basename(f)[:-8]
    tx, ty = (int(v) * 1000 for v in tid.split('_'))
    g = gpd.read_parquet(f)
    if g.empty:
        return None
    s = lambda c, d='': g[c].astype('string').fillna(d).to_numpy(dtype=object) if c in g else \
        np.full(len(g), d, dtype=object)                                              # noqa: E731
    src, sheet, code = s('src_id', 'none'), s('src_sheet'), s('src_code')
    q = shapely.force_2d(g.geometry.values)
    pt = shapely.point_on_surface(q)
    x, y = shapely.get_x(pt), shapely.get_y(pt)
    box = shapely.box(tx, ty, tx + TILE, ty + TILE)
    age = np.zeros(len(g))
    for t, sg in G['slices']:                                   # younger slices overwrite older ones
        if sg.intersects(box):
            age[shapely.contains_xy(sg, x, y)] = t
    lgm = shapely.contains_xy(G['lgm'], x, y) if G['lgm'] is not None and G['lgm'].intersects(box) else \
        np.zeros(len(g), bool)
    hc = s('hclass', 'U')
    status = np.where(age > 0, 'dated', np.where(lgm, 'lgm_ice_undated', 'ice_free_at_lgm')).astype(object)
    status[hc == 'I'] = 'ice_today'
    is_ru = np.array([v.startswith('ru_') for v in src])
    uc = np.array([unit_code(a, b, c) for a, b, c in zip(src, sheet, code)], dtype=object)
    ctx = pd.DataFrame({
        'pkey': [f'{tid}:{i}' for i in range(len(g))], 'unit_code': uc,
        'area_km2': pd.to_numeric(g['area_km2'], errors='coerce').astype('float64').to_numpy(),
        'src_id': src, 'src_sheet': sheet,
        'scale_den': pd.to_numeric(g['scale_den'], errors='coerce').astype('float64').to_numpy(),
        'pub_year': pd.to_numeric(g['pub_year'], errors='coerce').astype('float64').to_numpy(),
        'conf_tier': s('conf_tier'), 'redistribution': s('redistribution'),
        'deglac_ka': np.where(age > 0, age, np.nan), 'deglac_status': status, 'lgm_ice': lgm,
        'pf_zone': s('pf_zone', 'none'), 'ice_rich': s('ice_rich'), 'yedoma': s('yedoma'),
        'yedoma_conf': s('yedoma_conf'),
        'strat_index': np.where(is_ru, [ru_index(c) for c in code], '').astype(object)})
    units = pd.DataFrame({'unit_code': uc, 'src_id': src, 'src_sheet': sheet, 'src_code': code,
                          'src_desc': s('src_desc'), 'hclass': hc, 'hclass2': s('hclass2'), 'texture': s('texture'),
                          'cover': s('cover'), 'ice_rich': s('ice_rich'), 'scale_den': ctx['scale_den'],
                          'pub_year': ctx['pub_year'], 'area_km2': ctx['area_km2'], 'n_polygons': 1})
    units = units.groupby(['unit_code', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich'], as_index=False).agg(
        src_id=('src_id', 'first'), src_sheet=('src_sheet', 'first'), src_code=('src_code', 'first'),
        src_desc=('src_desc', 'first'), scale_den=('scale_den', 'min'), pub_year=('pub_year', 'max'),
        area_km2=('area_km2', 'sum'), n_polygons=('n_polygons', 'sum'))
    return ctx, units


def main():
    os.makedirs(OUT, exist_ok=True)
    files = sorted(glob.glob(f'{TD}/*.parquet'))
    print(TD, len(files), 'tiles', flush=True)
    ctxs, units = [], []
    with Pool(int(os.environ.get('SLURM_CPUS_PER_TASK', '8')), initializer=init) as pool:
        for i, r in enumerate(pool.imap_unordered(one, files, chunksize=4)):
            if r is not None:
                ctxs.append(r[0]); units.append(r[1])
            if i % 500 == 0:
                print(i, flush=True)
    ctx = pd.concat(ctxs, ignore_index=True)
    for c in ('unit_code', 'src_id', 'src_sheet', 'conf_tier', 'redistribution', 'deglac_status', 'pf_zone',
              'ice_rich', 'yedoma', 'yedoma_conf', 'strat_index'):
        ctx[c] = ctx[c].astype('category')
    ctx.to_parquet(f'{OUT}/polygon_context.parquet', index=False)
    u = pd.concat(units, ignore_index=True)
    # a native unit keeps its harmonised attributes; where they differ between polygons (ice override: hclass I;
    # sliver fills) the unit is listed once per attribute set, flagged
    u = u.groupby(['unit_code', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich'], as_index=False).agg(
        src_id=('src_id', 'first'), src_sheet=('src_sheet', 'first'), src_code=('src_code', 'first'),
        src_desc=('src_desc', 'first'), scale_den=('scale_den', 'min'), pub_year=('pub_year', 'max'),
        area_km2=('area_km2', 'sum'), n_polygons=('n_polygons', 'sum'))
    u['n_attribute_sets'] = u.groupby('unit_code')['unit_code'].transform('size')
    u = u.sort_values(['src_id', 'src_sheet', 'src_code', 'area_km2'], ascending=[True, True, True, False])
    u.to_csv(f'{OUT}/units.csv', index=False)
    # collision check: one (src_id, src_sheet, src_code) per unit_code
    ident = u.groupby('unit_code')[['src_id', 'src_sheet', 'src_code']].nunique().max(axis=1)
    pc = u.groupby(['hclass', 'hclass2', 'texture', 'cover'], as_index=False).agg(
        area_km2=('area_km2', 'sum'), n_units=('unit_code', 'nunique'), n_polygons=('n_polygons', 'sum'))
    pc = pc.sort_values('area_km2', ascending=False)
    pc['cum_share'] = pc['area_km2'].cumsum() / pc['area_km2'].sum()
    for col in ('top_m', 'waterIce', 'mineral', 'organic', 'field_capacity', 'soil_type',
                'satHydraulicConductivity', 'Xice', 'source', 'confidence'):
        pc[col] = ''
    pc.to_csv(f'{OUT}/parameter_classes.csv', index=False)
    tot = ctx['area_km2'].sum()
    lines = []
    pr = lambda t: (print(t, flush=True), lines.append(t))                         # noqa: E731
    pr(f'polygons {len(ctx):,}  area {tot:,.0f} km2  native units {u["unit_code"].nunique():,}  '
       f'unit-code collisions {int((ident > 1).sum())}  units with >1 attribute set '
       f'{int((u.groupby("unit_code").size() > 1).sum()):,}')
    pr('deglaciation status by area (%): ' + ', '.join(
        f'{k} {100 * v / tot:.1f}' for k, v in ctx.groupby('deglac_status', observed=True)['area_km2'].sum().items()))
    d = ctx[ctx['deglac_status'] == 'dated']
    if len(d):
        w = d['area_km2'].to_numpy()
        a = d['deglac_ka'].to_numpy()
        o = np.argsort(a)
        med = a[o][np.searchsorted(np.cumsum(w[o]), w.sum() / 2)]
        pr(f'dated area {w.sum():,.0f} km2, area-weighted median deglaciation {med:.1f} ka, range {a.min():.1f}-{a.max():.1f}')
    pr(f'LGM ice by area: {100 * ctx.loc[ctx["lgm_ice"], "area_km2"].sum() / tot:.1f} %')
    ri = ctx[ctx['strat_index'] != '']
    rus = ctx[ctx['src_id'].astype(str).str.startswith('ru_')]
    pr(f'Russian area with a native stratigraphic index: {100 * ri["area_km2"].sum() / rus["area_km2"].sum():.1f} % '
       f'({ri["strat_index"].nunique()} distinct tokens)')
    pr(f'parameter classes {len(pc):,}; classes covering 80 / 90 / 95 % of the area: '
       + ' / '.join(str(int((pc['cum_share'] < p).sum()) + 1) for p in (0.8, 0.9, 0.95)))
    open(f'{OUT}/summary.txt', 'w').write('\n'.join(lines) + '\n')
    open(f'{OUT}/README.txt', 'w').write(__doc__)


if __name__ == '__main__':
    main()
