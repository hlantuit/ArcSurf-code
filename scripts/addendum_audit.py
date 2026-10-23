#!/usr/bin/env python
"""Audit of the merged map against the seven requirements of the CryoGrid parameter addendum (H. Lantuit 2026-10-06:
unit codes, atomic attributes, numeric thickness, persistent ids, provenance, joinable chronology, no interpretation in
the geology). Measures by AREA what the build already provides and what the addendum keys would have to be built
from. One pass over a merged tile set (default work/a0_tiles_m43); first step of the addendum work, run after the
final merge.

  coverage.csv        per field: share of the area with a known value, overall and per source prefix
  values_<field>.csv  area and polygon count per value (hclass, hclass2, texture, cover, ice_rich, conf_tier, ...)
  cover_by_source.csv cover terms per source: the thickness semantics differ by source legend system (requirement 3)
  native_units.csv    (src_id, src_code, hclass): the native units the addendum could be keyed to (requirement 1)
  chronology.csv      area per source whose src_code / src_desc carries an age (index or keyword) (requirement 6)
  seams.csv           polygons cut by the 100 km tile seams, per source (requirement 4: persistent ids)

usage: addendum_audit.py [TILES_DIR]   ->  work/addendum_audit/<tiles>/*.csv; summary printed (markdown)"""
import glob
import os
import re
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
TD = sys.argv[1] if len(sys.argv) > 1 else f'{ROOT}/work/a0_tiles_m43'
OUT = f'{ROOT}/work/addendum_audit/{os.path.basename(os.path.normpath(TD))}'
TILE = 100_000
FIELDS = ['hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'conf_tier', 'redistribution', 'pf_zone', 'yedoma',
          'yedoma_conf', 'ice_src', 'ice_note', 'gapfill', 'coastal']
UNKNOWN = {'', 'unknown', 'none', 'nan', '<NA>'}
# age carried by the native unit: VSEGEI-style indices (genesis letters + Roman stage + optional sub-stage,
# e.g. aIII3, gII, mIV, QH) in src_code; stratigraphic keywords (EN / RU / NO / SV / FI / DA) in src_desc
AGE_CODE = re.compile(r'(^|[^A-Za-z])[a-zA-Z]{0,4}(IV|III|II|I|H)\d{0,2}([^A-Za-z]|$)|Q[1-4HIV]', re.U)
AGE_DESC = re.compile(r'holocen|pleistocen|wisconsin|weichsel|late.?glacial|postglacial|preboreal|younger dryas|'
                      r'quaternary|tertiary|neogene|paleogene|cretaceous|jurassic|triassic|permian|devonian|'
                      r'cambrian|precambrian|archean|proterozoic|ka\b|kyr|\bbp\b|'
                      r'голоцен|плейстоцен|неоплейстоцен|четвертичн|верхн|средн|нижн|позднеледник|'
                      r'holosen|pleistosen|weichsel|senglasial|postglasial|holoseeni|pleistoseeni', re.I | re.U)


def s(g, c, d=''):
    return g[c].astype('string').fillna(d).to_numpy(dtype=object) if c in g else np.full(len(g), d, dtype=object)


def one(f):
    tid = os.path.basename(f)[:-8]
    tx, ty = (int(v) * 1000 for v in tid.split('_'))
    g = gpd.read_parquet(f)
    if g.empty:
        return None
    a = pd.to_numeric(g['area_km2'], errors='coerce').astype('float64').fillna(0.0).to_numpy()
    src = s(g, 'src_id', 'none')
    d = pd.DataFrame({'src_id': src, 'prefix': [x.split('_')[0] for x in src], 'area_km2': a, 'n': 1})
    for c in FIELDS:
        d[c] = s(g, c)
    d['pub_year_known'] = pd.to_numeric(g['pub_year'], errors='coerce').notna().to_numpy() if 'pub_year' in g else False
    d['survey_years_known'] = ~pd.Series(s(g, 'survey_years')).str.strip().str.lower().isin(UNKNOWN).to_numpy()
    d['scale_known'] = pd.to_numeric(g['scale_den'], errors='coerce').notna().to_numpy()
    code, desc = s(g, 'src_code'), s(g, 'src_desc')
    d['age_in_code'] = [x_src.startswith('ru_') and bool(AGE_CODE.search(x))     # Roman stage indices: Russian
                        for x, x_src in zip(code, src)]                          # legends only (GSC 'I' = ice)
    d['age_in_desc'] = [bool(AGE_DESC.search(x)) for x in desc]
    seam = shapely.boundary(shapely.box(tx, ty, tx + TILE, ty + TILE)).buffer(1.0)
    shapely.prepare(seam)
    d['on_seam'] = shapely.intersects(shapely.force_2d(g.geometry.values), seam)
    out = {}
    out['fields'] = d.groupby(['prefix', 'src_id'] + FIELDS + ['pub_year_known', 'survey_years_known', 'scale_known'],
                              as_index=False)[['area_km2', 'n']].sum()
    nu = pd.DataFrame({'src_id': src, 'src_code': code, 'hclass': d['hclass'], 'area_km2': a, 'n': 1,
                       'src_desc': desc})
    nu = nu.groupby(['src_id', 'src_code', 'hclass'], as_index=False).agg(area_km2=('area_km2', 'sum'),
                                                                         n=('n', 'sum'), src_desc=('src_desc', 'first'))
    out['units'] = nu
    out['chron'] = d.groupby(['src_id', 'age_in_code', 'age_in_desc'], as_index=False)[['area_km2', 'n']].sum()
    out['seams'] = d.groupby(['src_id', 'on_seam'], as_index=False)[['area_km2', 'n']].sum()
    return out


def known(v):
    return ~v.astype(str).str.strip().str.lower().isin(UNKNOWN)


def main():
    files = sorted(glob.glob(f'{TD}/*.parquet'))
    os.makedirs(OUT, exist_ok=True)
    print(TD, len(files), 'tiles', flush=True)
    parts = {k: [] for k in ('fields', 'units', 'chron', 'seams')}
    with Pool(int(os.environ.get('SLURM_CPUS_PER_TASK', '8'))) as pool:
        for i, r in enumerate(pool.imap_unordered(one, files, chunksize=4)):
            if r is None:
                continue
            for k, v in r.items():
                parts[k].append(v)
            if i % 500 == 0:
                print(i, flush=True)
    F = pd.concat(parts['fields'])
    F = F.groupby([c for c in F.columns if c not in ('area_km2', 'n')], as_index=False)[['area_km2', 'n']].sum()
    U = pd.concat(parts['units']).groupby(['src_id', 'src_code', 'hclass'], as_index=False).agg(
        area_km2=('area_km2', 'sum'), n=('n', 'sum'), src_desc=('src_desc', 'first'))
    C = pd.concat(parts['chron']).groupby(['src_id', 'age_in_code', 'age_in_desc'], as_index=False)[['area_km2', 'n']].sum()
    S = pd.concat(parts['seams']).groupby(['src_id', 'on_seam'], as_index=False)[['area_km2', 'n']].sum()
    tot = F['area_km2'].sum()
    mapped = F[(F['hclass'] != 'U') & (F['src_id'] != 'none')]
    tm = mapped['area_km2'].sum()
    # coverage of each field by area (mapped area only), overall and per prefix
    rows = []
    checks = {c: known(mapped[c]) for c in ('hclass2', 'texture', 'cover', 'ice_rich', 'conf_tier', 'survey_years_known')}
    checks['hclass2'] = known(mapped['hclass2']) & (mapped['hclass2'] != mapped['hclass'])
    checks['survey_years_known'] = mapped['survey_years_known'].astype(bool)
    checks['pub_year_known'] = mapped['pub_year_known'].astype(bool)
    checks['scale_known'] = mapped['scale_known'].astype(bool)
    for c, m in checks.items():
        rows.append(dict(field=c, prefix='ALL', known_km2=mapped.loc[m, 'area_km2'].sum(), mapped_km2=tm))
        for p, sub in mapped.groupby('prefix'):
            rows.append(dict(field=c, prefix=p, known_km2=sub.loc[m[sub.index], 'area_km2'].sum(),
                             mapped_km2=sub['area_km2'].sum()))
    cov = pd.DataFrame(rows)
    cov['known_pct'] = 100 * cov['known_km2'] / cov['mapped_km2']
    cov.to_csv(f'{OUT}/coverage.csv', index=False)
    for c in FIELDS:
        v = F.groupby(c, as_index=False)[['area_km2', 'n']].sum().sort_values('area_km2', ascending=False)
        v['pct'] = 100 * v['area_km2'] / tot
        v.to_csv(f'{OUT}/values_{c}.csv', index=False)
    cb = mapped.groupby(['src_id', 'cover'], as_index=False)['area_km2'].sum()
    cb.pivot(index='src_id', columns='cover', values='area_km2').fillna(0).round(1).to_csv(f'{OUT}/cover_by_source.csv')
    U.sort_values(['src_id', 'area_km2'], ascending=[True, False]).to_csv(f'{OUT}/native_units.csv', index=False)
    C.to_csv(f'{OUT}/chronology.csv', index=False)
    S.to_csv(f'{OUT}/seams.csv', index=False)

    # summary (markdown, printed)
    pr = lambda *x: print(*x, flush=True)                                  # noqa: E731
    pr(f'# Addendum audit, {os.path.basename(TD)}\n')
    pr(f'Total {tot / 1e6:.3f} M km2, mapped (hclass != U, with a source) {tm / 1e6:.3f} M km2, '
       f'{int(F["n"].sum()):,} polygons.\n')
    nu = U[(U['hclass'] != 'U') & (U['src_id'] != 'none')]
    pr('## 1 Unit codes')
    pr(f'- hclass values: {sorted(F["hclass"].unique())}')
    pr(f'- native units (src_id, src_code, hclass): {len(nu):,}; (src_id, src_code): '
       f'{nu.groupby(["src_id", "src_code"]).ngroups:,}; native codes mapped to >1 hclass: '
       f'{int((nu.groupby(["src_id", "src_code"])["hclass"].nunique() > 1).sum()):,}')
    q = nu.sort_values('area_km2', ascending=False)['area_km2'].cumsum() / nu['area_km2'].sum()
    for p in (0.5, 0.8, 0.9, 0.95, 0.99):
        pr(f'- {int(p * 100)} % of the mapped area lies in the largest {int((q < p).sum()) + 1:,} native units')
    pr('\n## 2 Atomic attributes and 5 provenance (share of the mapped area with a known value)')
    for c in checks:
        r = cov[(cov['field'] == c) & (cov['prefix'] == 'ALL')].iloc[0]
        pr(f'- {c}: {r["known_pct"]:.1f} %')
    pr('\n## 3 Cover terms by source (thickness semantics differ by legend system)')
    pr(mapped.groupby('cover')['area_km2'].sum().div(1e6).round(3).to_string())
    pr('\n## 4 Persistent ids')
    pr('- no id column in the build: ' + str(not any(c in ('uuid', 'poly_id', 'id') for c in F.columns)))
    sm = S.groupby('on_seam')[['area_km2', 'n']].sum()
    pr(f'- polygons touching a 100 km tile seam: {int(sm.loc[True, "n"]) if True in sm.index else 0:,} of '
       f'{int(sm["n"].sum()):,} ({100 * sm.loc[True, "area_km2"] / sm["area_km2"].sum() if True in sm.index else 0:.1f} % '
       'of the area): each is a fragment of a source unit cut by the merge')
    pr('\n## 6 Chronology in the native unit')
    cc = C[~C['src_id'].isin(['none'])]
    a_code = cc.loc[cc['age_in_code'], 'area_km2'].sum()
    a_any = cc.loc[cc['age_in_code'] | cc['age_in_desc'], 'area_km2'].sum()
    pr(f'- age index in src_code: {100 * a_code / tm:.1f} % of the mapped area; index or keyword in src_code / '
       f'src_desc: {100 * a_any / tm:.1f} % (indicative regex, to be checked per source)')
    pr('\n## 7 Interpretation in the geology attributes')
    for c in ('pf_zone', 'ice_rich', 'yedoma'):
        pr(f'- {c}: ' + ', '.join(f'{k} {v / 1e6:.2f}' for k, v in
                                    F.groupby(c)['area_km2'].sum().sort_values(ascending=False).items()) + ' (M km2)')
    pr(f'- hclass Y (ice complex) {F.loc[F["hclass"] == "Y", "area_km2"].sum() / 1e6:.3f} M km2, '
       f'K (thermokarst) {F.loc[F["hclass"] == "K", "area_km2"].sum() / 1e6:.3f} M km2')
    pr('\n## Redistribution (what each product could publish)')
    pr(F.groupby('redistribution')['area_km2'].sum().div(1e6).round(3).to_string())
    pr(f'\ntables: {OUT}')


if __name__ == '__main__':
    main()
