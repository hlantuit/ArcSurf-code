#!/usr/bin/env python
"""ESSD dataset statistics for ArcSurf, merge 41 (attribute-only pass, no geometry read).

Reads work/a0_tiles_m41/*.parquet (hard links to the merge-41 tiles) and writes CSVs + a text
report to work/essd_tables/. Usage: essd_stats.py [N_FILES_FOR_TEST]
"""
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow as pa  # noqa: E402
import pyarrow.compute as pc  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
D = os.environ.get('ESSD_TILES', f'{ROOT}/work/a0_tiles_m41')
O = os.environ.get('ESSD_OUT', f'{ROOT}/work/essd_tables')
TEST = int(sys.argv[1]) if len(sys.argv) > 1 else 0
if TEST:
    O = f'{O}/test'
os.makedirs(O, exist_ok=True)

COLS = ['src_id', 'src_sheet', 'src_code', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich',
        'scale_den', 'pub_year', 'survey_years', 'conf_tier', 'licence', 'redistribution', 'gapfill',
        'coastal', 'pf_zone', 'yedoma', 'yedoma_conf', 'tile_id', 'area_km2']
COUNTRY = {'ca': 'Canada', 'us': 'USA (Alaska)', 'gl': 'Greenland', 'is': 'Iceland', 'no': 'Norway (mainland)',
           'se': 'Sweden', 'fi': 'Finland', 'sj': 'Svalbard & Jan Mayen', 'ru': 'Russia', 'fo': 'Faroe Islands',
           'none': 'no source (gap, hclass U)'}
PORDER = ['ru', 'ca', 'gl', 'us', 'no', 'se', 'is', 'fi', 'sj', 'fo', 'none']
HNAME = {'R': 'Bedrock', 'T': 'Till / morainal', 'GF': 'Glaciofluvial', 'GL': 'Glaciolacustrine',
         'GM': 'Glaciomarine', 'M': 'Marine and littoral', 'F': 'Fluvial / alluvial / deltaic',
         'L': 'Lacustrine (non-glacial)', 'K': 'Thermokarst / alas', 'Y': 'Ice complex / Yedoma',
         'E': 'Eolian', 'C': 'Colluvial / mass-wasting', 'W': 'Residual / weathered regolith',
         'O': 'Organic (peat)', 'V': 'Quaternary volcanic', 'X': 'Anthropogenic', 'I': 'Glacier / perennial ice',
         'Q': 'Quaternary undivided', 'U': 'Unmapped / no data'}
# scale classes exactly as scripts/coverage_map.py (out/coverage_by_country.csv)
SCLS = [('<=1:100k', 0, 100_000), ('1:125k-1:250k', 100_001, 260_000), ('1:500k-1:600k', 260_001, 700_000),
        ('1:1M', 700_001, 1_500_000), ('>=1:2.5M', 1_500_001, 10**12)]
SORDER = [c[0] for c in SCLS] + ['no scale (unmapped)']

t0 = time.time()
REP = open(f'{O}/report.txt', 'w')


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(f'[{time.time() - t0:7.1f}s] {s}', flush=True)
    REP.write(s + '\n')
    REP.flush()


def md(df, floatfmt=None, index=False):
    """Markdown table without tabulate."""
    d = df.reset_index() if index else df
    cols = [str(c) for c in d.columns]
    lines = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join(['---'] * len(cols)) + '|']
    for r in d.itertuples(index=False):
        cells = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                cells.append('' if np.isnan(v) else (f'{v:,.{floatfmt}f}' if floatfmt is not None else f'{v:,.1f}'))
            elif isinstance(v, (int, np.integer)):
                cells.append(f'{v:,}')
            else:
                cells.append('' if v is None or (v is pd.NA) else str(v))
        lines.append('| ' + ' | '.join(cells) + ' |')
    return '\n'.join(lines)


def save(df, name, index=False):
    df.to_csv(f'{O}/{name}.csv', index=index)


def wquant(v, w, q=0.5):
    """Area-weighted quantile (lower), NA dropped."""
    v = np.asarray(v, dtype=float)
    w = np.asarray(w, dtype=float)
    m = ~np.isnan(v)
    v, w = v[m], w[m]
    if not len(v):
        return np.nan
    o = np.argsort(v, kind='stable')
    v, w = v[o], w[o]
    c = np.cumsum(w)
    return float(v[min(np.searchsorted(c, q * c[-1]), len(v) - 1)])


def cat_map(s, f):
    codes = s.cat.codes.to_numpy()
    vals = np.array([f(c) for c in s.cat.categories] + [f(None)], dtype=object)
    return pd.Series(vals[codes], index=s.index).astype('category')


# ------------------------------------------------------------------ read
files = sorted(glob.glob(f'{D}/*.parquet'))
if TEST:
    files = files[::max(1, len(files) // TEST)][:TEST]
log('files', len(files))
schemas, tabs, bad_tile, nrows_meta = {}, [], [], 0
for i, f in enumerate(files):
    pf = pq.ParquetFile(f)
    s = pf.schema_arrow
    key = tuple((n, str(s.field(n).type)) for n in s.names)
    schemas.setdefault(key, []).append(os.path.basename(f))
    nrows_meta += pf.metadata.num_rows
    t = pf.read(columns=COLS)
    stem = os.path.basename(f)[:-8]
    u = pc.unique(t['tile_id']).to_pylist()
    if u != [stem] and len(t):
        bad_tile.append((stem, u[:5]))
    tabs.append(t)
    if i % 500 == 0:
        log('read', i, nrows_meta)
log('schemas', len(schemas))
for k, v in schemas.items():
    log('  schema used by', len(v), 'files, e.g.', v[:2], ':', ', '.join(f'{n}:{ty}' for n, ty in k))
log('tile_id != filename:', len(bad_tile), bad_tile[:5])
tab = pa.concat_tables(tabs, promote_options='default')
del tabs
log('rows', tab.num_rows, 'metadata rows', nrows_meta)
df = tab.to_pandas(strings_to_categorical=True,
                   types_mapper=lambda ty: pd.Int64Dtype() if ty == pa.int64() else None)
del tab
for c in df.columns:
    if c not in ('area_km2', 'scale_den', 'pub_year', 'coastal') and not isinstance(df[c].dtype, pd.CategoricalDtype):
        df[c] = df[c].astype('category')
log('pandas', df.shape, df.memory_usage(deep=True).sum() / 1e9, 'GB')
for c in df.columns:
    log('  dtype', c, df[c].dtype, 'nulls', int(df[c].isna().sum()))

df['prefix'] = cat_map(df['src_id'], lambda c: 'NULL' if c is None else c.split('_')[0])
df['country'] = cat_map(df['prefix'], lambda c: COUNTRY.get(c, c))
sd = df['scale_den'].astype('float64').to_numpy()
cls = np.full(len(df), 'no scale (unmapped)', dtype=object)
for name, lo, hi in SCLS:
    cls[(sd >= lo) & (sd <= hi)] = name
df['scls'] = pd.Categorical(cls, categories=SORDER)
py = df['pub_year'].astype('float64').to_numpy()
dec = np.where(np.isnan(py) | (py <= 0), -1, (np.floor(py / 10) * 10))
df['decade'] = dec.astype(int)
A = df['area_km2'].to_numpy()
TOT = float(np.nansum(A))
N = len(df)

# ------------------------------------------------------------------ anomalies
log('\n## Anomaly checks')
na_area = int(np.isnan(A).sum())
log('area_km2: NA', na_area, '| <=0', int((A <= 0).sum()), '| <0', int((A < 0).sum()),
    '| < 1e-6 km2 (MIN_AREA 1 m2)', int((A < 1e-6).sum()), '| min', np.nanmin(A), '| max', np.nanmax(A))
big = df.nlargest(5, 'area_km2')[['src_id', 'hclass', 'tile_id', 'area_km2']]
log('largest polygons:\n' + md(big, 2))
for c in ['hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'conf_tier', 'redistribution', 'gapfill',
          'coastal', 'pf_zone', 'yedoma', 'yedoma_conf']:
    vc = df.groupby(c, observed=True, dropna=False)['area_km2'].agg(['size', 'sum']).sort_values('sum', ascending=False)
    vc.index = vc.index.astype(object).fillna('<NA>') if hasattr(vc.index, 'astype') else vc.index
    log(f'values of {c} (n, km2):', '; '.join(f'{k!s}: {int(r["size"]):,} / {r["sum"]:,.0f}' for k, r in vc.iterrows()))
unk_h = sorted(set(df['hclass'].dropna().unique()) - set(HNAME))
log('hclass values outside LEGEND.md:', unk_h)
x = pd.crosstab(df['src_id'].astype(object).fillna('<NA>') == 'none', df['hclass'].astype(object).fillna('<NA>') == 'U',
                values=df['area_km2'], aggfunc='sum')
log('crosstab src_id==none (rows) x hclass==U (cols), km2:\n' + x.round(0).to_string())
u_src = df[(df['hclass'] == 'U') & (df['src_id'] != 'none')].groupby('src_id', observed=True)['area_km2'].agg(['size', 'sum'])
log('hclass U polygons that DO carry a source (n, km2):\n' + u_src.sort_values('sum', ascending=False).round(1).to_string())
nn = df[df['src_id'] != 'none']
g = nn.groupby('src_id', observed=True)
chk = pd.DataFrame({
    'n': g.size(),
    'scale_na_n': g['scale_den'].apply(lambda s: int(s.isna().sum())),
    'scale_le0_n': g['scale_den'].apply(lambda s: int((s.fillna(1) <= 0).sum())),
    'pub_na_n': g['pub_year'].apply(lambda s: int(s.isna().sum())),
    'pub_le0_n': g['pub_year'].apply(lambda s: int((s.fillna(1) <= 0).sum())),
    'pub_na_km2': g.apply(lambda s: float(s.loc[s['pub_year'].isna() | (s['pub_year'].fillna(1) <= 0), 'area_km2'].sum())),
    'pub_min': g['pub_year'].min(), 'pub_max': g['pub_year'].max(),
    'redistrib_na_n': g['redistribution'].apply(lambda s: int(s.isna().sum())),
    'licence_na_n': g['licence'].apply(lambda s: int(s.isna().sum())),
    'coastal_na_n': g['coastal'].apply(lambda s: int(s.isna().sum())),
})
log('per-source NA / placeholder checks:\n' + chk.to_string())
fy = df['pub_year'].astype('float64')
log('pub_year < 1900 or > 2026 (n, km2):', int(((fy < 1900) | (fy > 2026)).sum()),
    float(df.loc[(fy < 1900) | (fy > 2026), 'area_km2'].sum()))
odd = df.loc[(fy < 1900) | (fy > 2026)].groupby(['src_id', 'pub_year'], observed=True)['area_km2'].agg(['size', 'sum'])
if len(odd):
    log('odd pub_year values:\n' + odd.to_string())
srcs = json.load(open(f'{ROOT}/work/merge_sources.json'))
present = set(df['src_id'].dropna().unique()) - {'none'}
log('merge_sources.json:', len(srcs), '| present in tiles:', len(present),
    '| in json but absent:', sorted(set(srcs) - present), '| in tiles but not json:', sorted(present - set(srcs)))
# merge log land vs out
try:
    L = [ln.split() for ln in open(f'{ROOT}/work/merge_tiles.log') if ' ok n=' in ln]
    land = sum(float(re.search(r'land=([\d.]+)', ' '.join(x)).group(1)) for x in L)
    out = sum(float(re.search(r'out=([\d.]+)', ' '.join(x)).group(1)) for x in L)
    diffs = [float(re.search(r'diff=([-+\d.]+)%', ' '.join(x)).group(1)) for x in L]
    log(f'merge_tiles.log (m41): tiles {len(L)}, land {land:,.0f} km2, out {out:,.0f} km2, '
        f'tile diff% min {min(diffs):+.3f} max {max(diffs):+.3f}')
except Exception as e:  # noqa: BLE001
    log('merge log parse failed', e)

# ------------------------------------------------------------------ summary
log('\n## Summary')
nsheet_pairs = df[['src_id', 'src_sheet']].drop_duplicates()
summ = {
    'n_polygons': N,
    'total_area_km2': TOT,
    'n_tiles': len(files),
    'n_src_id_incl_none': int(df['src_id'].nunique()),
    'n_src_id_sources': len(present),
    'n_distinct_src_sheet_values (non-null, non-empty)': int(df.loc[df['src_sheet'].astype(object).fillna('') != '', 'src_sheet'].nunique()),
    'n_distinct_(src_id,src_sheet)_pairs (null sheet counts once per source, excl. none)':
        int(len(nsheet_pairs[nsheet_pairs['src_id'] != 'none'])),
    'n_distinct_(src_id,src_code)_native_units (excl. none)':
        int(len(df.loc[df['src_id'] != 'none', ['src_id', 'src_code']].drop_duplicates())),
    'poly_area_km2_p10': float(np.nanquantile(A, 0.1)),
    'poly_area_km2_median': float(np.nanmedian(A)),
    'poly_area_km2_p90': float(np.nanquantile(A, 0.9)),
    'poly_area_km2_mean': float(np.nanmean(A)),
    'poly_area_km2_p99': float(np.nanquantile(A, 0.99)),
    'poly_area_km2_max': float(np.nanmax(A)),
    'area_weighted_median_poly_area_km2': wquant(A, A, 0.5),
    'n_polygons_lt_0.01km2 (1 ha)': int((A < 0.01).sum()),
    'area_km2_of_polys_lt_0.01km2': float(A[A < 0.01].sum()),
    'n_gapfill_sliver_nearest': int((df['gapfill'] == 'sliver_nearest').sum()),
    'area_km2_gapfill_sliver_nearest': float(df.loc[df['gapfill'] == 'sliver_nearest', 'area_km2'].sum()),
    'n_coastal_polys': int((df['coastal'] == 1).sum()),
    'area_km2_coastal_polys': float(df.loc[df['coastal'] == 1, 'area_km2'].sum()),
}
for k, v in summ.items():
    log(f'  {k}: {v:,.4f}' if isinstance(v, float) else f'  {k}: {v:,}')
save(pd.DataFrame(list(summ.items()), columns=['metric', 'value']), 'summary')
# polygon size distribution by country prefix and excluding U
rows = []
for lab, m in [('all', np.ones(N, bool)), ('excl. hclass U', (df['hclass'] != 'U').to_numpy())] + \
        [(f'prefix {p}', (df['prefix'] == p).to_numpy()) for p in PORDER]:
    a = A[m]
    if not len(a):
        continue
    rows.append(dict(subset=lab, n=int(len(a)), p10=np.quantile(a, .1), median=np.median(a), p90=np.quantile(a, .9),
                     mean=a.mean(), area_weighted_median=wquant(a, a)))
psz = pd.DataFrame(rows)
save(psz, 'polygon_size')
log('polygon size distribution (km2):\n' + md(psz, 4))

# ------------------------------------------------------------------ T1 per source
log('\n## T1 per src_id')
rows = []
for sid, gg in df.groupby('src_id', observed=True):
    a = gg['area_km2'].to_numpy()
    s_ = gg['scale_den'].astype('float64').to_numpy()
    y_ = gg['pub_year'].astype('float64').to_numpy()
    y_ = np.where(y_ <= 0, np.nan, y_)
    rd = gg.groupby('redistribution', observed=True)['area_km2'].sum()
    lic = gg['licence'].dropna().unique()
    rows.append(dict(
        src_id=sid, prefix=sid.split('_')[0], area_km2=a.sum(), share_pct=100 * a.sum() / TOT, n_polygons=len(gg),
        n_sheets=int(gg['src_sheet'].nunique()), n_native_codes=int(gg['src_code'].nunique()),
        scale_min=np.nanmin(s_) if (~np.isnan(s_)).any() else np.nan,
        scale_median=np.nanmedian(s_) if (~np.isnan(s_)).any() else np.nan,
        scale_max=np.nanmax(s_) if (~np.isnan(s_)).any() else np.nan,
        scale_awmedian=wquant(s_, a),
        pub_min=np.nanmin(y_) if (~np.isnan(y_)).any() else np.nan,
        pub_median=np.nanmedian(y_) if (~np.isnan(y_)).any() else np.nan,
        pub_max=np.nanmax(y_) if (~np.isnan(y_)).any() else np.nan,
        pub_awmedian=wquant(y_, a),
        pub_missing_km2=float(a[np.isnan(y_)].sum()),
        redistribution='; '.join(f'{k}' for k in rd.index) if len(rd) else '',
        redistribution_km2='; '.join(f'{k}={v:,.0f}' for k, v in rd.items()),
        n_licences=len(lic), licence=' || '.join(str(x) for x in lic[:3]),
        conf_tiers='; '.join(sorted(str(x) for x in gg['conf_tier'].dropna().unique())[:6]),
        coastal_km2=float(gg.loc[gg['coastal'] == 1, 'area_km2'].sum()),
        U_km2=float(gg.loc[gg['hclass'] == 'U', 'area_km2'].sum()),
        Q_km2=float(gg.loc[gg['hclass'] == 'Q', 'area_km2'].sum()),
        sliver_km2=float(gg.loc[gg['gapfill'] == 'sliver_nearest', 'area_km2'].sum()),
    ))
t1 = pd.DataFrame(rows).sort_values('area_km2', ascending=False).reset_index(drop=True)
save(t1, 't1_sources')
log(md(t1[['src_id', 'area_km2', 'share_pct', 'n_polygons', 'n_sheets', 'n_native_codes', 'scale_min', 'scale_median',
           'scale_max', 'scale_awmedian', 'pub_min', 'pub_median', 'pub_max', 'pub_awmedian', 'pub_missing_km2',
           'redistribution']], 2))
log(md(t1[['src_id', 'redistribution_km2', 'n_licences', 'licence', 'conf_tiers', 'U_km2', 'Q_km2', 'sliver_km2']], 1))

# by country prefix
rows = []
for p, gg in df.groupby('prefix', observed=True):
    a = gg['area_km2'].to_numpy()
    rows.append(dict(prefix=p, country=COUNTRY.get(p, p), area_km2=a.sum(), share_pct=100 * a.sum() / TOT,
                     n_polygons=len(gg), n_sources=int(gg['src_id'].nunique()) if p != 'none' else 0,
                     n_sheets=int(gg[['src_id', 'src_sheet']].drop_duplicates().shape[0]) if p != 'none' else 0,
                     scale_awmedian=wquant(gg['scale_den'].astype('float64').to_numpy(), a),
                     pub_awmedian=wquant(np.where(gg['pub_year'].astype('float64') <= 0, np.nan,
                                                  gg['pub_year'].astype('float64')), a),
                     median_poly_km2=float(np.median(a))))
t1b = pd.DataFrame(rows)
t1b['o'] = t1b['prefix'].map({p: i for i, p in enumerate(PORDER)})
t1b = t1b.sort_values('o').drop(columns='o').reset_index(drop=True)
save(t1b, 't1b_by_country_prefix')
log(md(t1b, 2))
# by country prefix + agency token
df['agency'] = cat_map(df['src_id'], lambda c: 'NULL' if c is None else '_'.join(c.split('_')[:2]))
t1c = df.groupby(['prefix', 'agency'], observed=True).agg(area_km2=('area_km2', 'sum'), n_polygons=('area_km2', 'size'),
                                                           n_sources=('src_id', 'nunique')).reset_index()
t1c['share_pct'] = 100 * t1c['area_km2'] / TOT
t1c = t1c.sort_values('area_km2', ascending=False)
save(t1c, 't1c_by_agency_token')
log(md(t1c, 2))

# ------------------------------------------------------------------ T2 hclass
log('\n## T2 hclass')
coast = df['coastal'] == 1
t2 = pd.DataFrame({
    'area_km2': df.groupby('hclass', observed=True)['area_km2'].sum(),
    'n_polygons': df.groupby('hclass', observed=True).size(),
    'coastal_area_km2': df[coast].groupby('hclass', observed=True)['area_km2'].sum(),
    'coastal_n_polygons': df[coast].groupby('hclass', observed=True).size(),
}).fillna(0)
t2['share_pct'] = 100 * t2['area_km2'] / t2['area_km2'].sum()
t2['coastal_share_pct'] = 100 * t2['coastal_area_km2'] / t2['coastal_area_km2'].sum()
t2['coastal_frac_of_class_pct'] = 100 * t2['coastal_area_km2'] / t2['area_km2']
t2.index.name = 'hclass'
t2 = t2.reset_index()
t2.insert(1, 'name', t2['hclass'].map(HNAME))
t2 = t2.sort_values('area_km2', ascending=False)
t2 = t2[['hclass', 'name', 'area_km2', 'share_pct', 'n_polygons', 'coastal_area_km2', 'coastal_share_pct',
         'coastal_n_polygons', 'coastal_frac_of_class_pct']]
tot_row = pd.DataFrame([dict(hclass='TOTAL', name='', area_km2=t2['area_km2'].sum(), share_pct=100.0,
                             n_polygons=int(t2['n_polygons'].sum()), coastal_area_km2=t2['coastal_area_km2'].sum(),
                             coastal_share_pct=100.0, coastal_n_polygons=int(t2['coastal_n_polygons'].sum()),
                             coastal_frac_of_class_pct=100 * t2['coastal_area_km2'].sum() / t2['area_km2'].sum())])
t2 = pd.concat([t2, tot_row], ignore_index=True)
save(t2, 't2_hclass')
log(md(t2, 2))
t2b = df.pivot_table(index='hclass', columns='prefix', values='area_km2', aggfunc='sum', observed=True).fillna(0)
t2b = t2b[[p for p in PORDER if p in t2b.columns]]
save(t2b, 't2b_hclass_by_prefix', index=True)
log('hclass x prefix (km2):\n' + md(t2b.round(0), 0, index=True))
t2c = df.pivot_table(index='hclass', columns='coastal', values='area_km2', aggfunc='sum', observed=True).fillna(0)
save(t2c, 't2c_hclass_by_coastal', index=True)

# ------------------------------------------------------------------ T3 scale class
log('\n## T3 scale class')
t3 = df.pivot_table(index='prefix', columns='scls', values='area_km2', aggfunc='sum', observed=False).fillna(0)
t3 = t3.reindex([p for p in PORDER if p in t3.index])
t3.loc['ALL'] = t3.sum()
t3['total'] = t3.sum(axis=1)
save(t3, 't3_scale_class_by_prefix', index=True)
log(md(t3.round(0), 0, index=True))
t3s = (100 * t3.div(t3['total'], axis=0)).round(2)
save(t3s, 't3_scale_class_by_prefix_pct', index=True)
log('row %:\n' + md(t3s, 2, index=True))
t3v = df.groupby(['scls', 'scale_den'], observed=True, dropna=False)['area_km2'].agg(['size', 'sum']).reset_index()
t3v.columns = ['scale_class', 'scale_den', 'n_polygons', 'area_km2']
t3v['srcs'] = [', '.join(sorted(df.loc[(df['scale_den'] == s) if not pd.isna(s) else df['scale_den'].isna(), 'src_id']
                                .astype(str).unique())[:8]) for s in t3v['scale_den']]
save(t3v, 't3b_scale_den_values')
log(md(t3v, 0))

# ------------------------------------------------------------------ T4 pub_year decade
log('\n## T4 decades')
t4 = df.pivot_table(index='decade', columns='prefix', values='area_km2', aggfunc='sum', observed=True).fillna(0)
t4 = t4[[p for p in PORDER if p in t4.columns]]
t4['ALL'] = t4.sum(axis=1)
t4.index = ['missing' if d == -1 else f'{d}s' for d in t4.index]
save(t4, 't4_decade_by_prefix', index=True)
t4o = pd.DataFrame({'all_km2': t4['ALL'], 'all_pct': 100 * t4['ALL'] / t4['ALL'].sum(),
                    'ru_km2': t4.get('ru', 0), 'ru_pct': 100 * t4.get('ru', 0) / t4.get('ru', 0).sum()})
t4o.loc['TOTAL'] = t4o.sum()
save(t4o, 't4_decade_overall_ru', index=True)
log(md(t4o, 1, index=True))
log('decade x prefix (km2):\n' + md(t4.round(0), 0, index=True))
# missing pub_year: which sources
miss = df[df['decade'] == -1].groupby('src_id', observed=True)['area_km2'].agg(['size', 'sum'])
log('missing pub_year by src_id:\n' + miss.sort_values('sum', ascending=False).to_string())
ruy = df[df['prefix'] == 'ru'].groupby(['src_id', 'pub_year'], observed=True, dropna=False)['area_km2'].sum().reset_index()
save(ruy, 't4c_ru_pub_year_values')

# ------------------------------------------------------------------ T5 redistribution
log('\n## T5 redistribution')
df['redis'] = cat_map(df['redistribution'], lambda c: '<NA (no source)>' if c is None else c)
t5 = df.pivot_table(index='prefix', columns='redis', values='area_km2', aggfunc='sum', observed=True).fillna(0)
t5 = t5.reindex([p for p in PORDER if p in t5.index])
t5.loc['ALL'] = t5.sum()
t5['total'] = t5.sum(axis=1)
save(t5, 't5_redistribution_by_prefix', index=True)
log(md(t5.round(0), 0, index=True))
t5o = df.groupby('redis', observed=True)['area_km2'].agg(['sum', 'size'])
t5o['pct'] = 100 * t5o['sum'] / TOT
log('overall:\n' + md(t5o, 2, index=True))
save(t5o, 't5_redistribution_overall', index=True)

# ------------------------------------------------------------------ T6 pf_zone / yedoma
log('\n## T6 pf_zone / yedoma')
for c in ['pf_zone', 'yedoma', 'yedoma_conf']:
    v = df.groupby(df[c].astype(object).fillna('<NA>'))['area_km2'].agg(['sum', 'size'])
    v['pct'] = 100 * v['sum'] / TOT
    v = v.sort_values('sum', ascending=False)
    save(v, f't6_{c}', index=True)
    log(c + ':\n' + md(v, 2, index=True))
isy = np.where(df['hclass'] == 'Y', 'hclass Y', 'hclass not Y')
t6x = df.pivot_table(index=isy, columns='yedoma', values='area_km2', aggfunc='sum', observed=True).fillna(0)
t6x['total'] = t6x.sum(axis=1)
t6x.loc['total'] = t6x.sum()
save(t6x, 't6_hclassY_x_yedoma', index=True)
log('hclass Y x yedoma (km2):\n' + md(t6x.round(0), 0, index=True))
t6y = df[df['hclass'] == 'Y'].pivot_table(index='src_id', columns='yedoma', values='area_km2', aggfunc='sum',
                                          observed=True).fillna(0)
t6y['total'] = t6y.sum(axis=1)
save(t6y, 't6_hclassY_by_src_x_yedoma', index=True)
log('hclass Y by src x yedoma:\n' + md(t6y.round(0), 0, index=True))
t6z = df.pivot_table(index='pf_zone', columns='yedoma', values='area_km2', aggfunc='sum', observed=True).fillna(0)
save(t6z, 't6_pfzone_x_yedoma', index=True)
log('pf_zone x yedoma:\n' + md(t6z.round(0), 0, index=True))
t6p = df.pivot_table(index='prefix', columns='pf_zone', values='area_km2', aggfunc='sum', observed=True).fillna(0)
t6p = t6p.reindex([p for p in PORDER if p in t6p.index])
save(t6p, 't6_pfzone_by_prefix', index=True)
log('pf_zone x prefix:\n' + md(t6p.round(0), 0, index=True))
t6r = df[df['yedoma'] == 'yes'].groupby('hclass', observed=True)['area_km2'].sum().sort_values(ascending=False)
save(t6r, 't6_yedoma_yes_by_hclass', index=True)
log('yedoma==yes area by hclass:\n' + t6r.round(0).to_string())

# ------------------------------------------------------------------ T7 completeness
log('\n## T7 completeness')
fb = (df['scale_den'].astype('float64') >= 2_500_000).fillna(False).to_numpy()
df['_U'] = np.where(df['hclass'] == 'U', A, 0.0)
df['_Q'] = np.where(df['hclass'] == 'Q', A, 0.0)
df['_FB'] = np.where(fb, A, 0.0)
df['_FBQ'] = np.where(fb & (df['hclass'] == 'Q').to_numpy(), A, 0.0)
t7 = df.groupby('prefix', observed=True)[['area_km2', '_U', '_Q', '_FB', '_FBQ']].sum()
t7 = t7.reindex([p for p in PORDER if p in t7.index])
t7.loc['ALL'] = t7.sum()
t7.columns = ['area_km2', 'U_km2', 'Q_km2', 'fallback_ge2.5M_km2', 'fallback_and_Q_km2']
t7['U_pct'] = 100 * t7['U_km2'] / t7['area_km2']
t7['Q_pct'] = 100 * t7['Q_km2'] / t7['area_km2']
t7['fallback_pct'] = 100 * t7['fallback_ge2.5M_km2'] / t7['area_km2']
df['_UQF'] = np.where(fb | df['hclass'].isin(['U', 'Q']).to_numpy(), A, 0.0)
uqf = df.groupby('prefix', observed=True)['_UQF'].sum()
uqf.loc['ALL'] = uqf.sum()
t7['U_or_Q_or_fallback_km2'] = uqf.reindex(t7.index)
t7['U_or_Q_or_fallback_pct'] = 100 * t7['U_or_Q_or_fallback_km2'] / t7['area_km2']
save(t7, 't7_completeness_by_prefix', index=True)
log(md(t7, 1, index=True))
fbs = df[fb].groupby('src_id', observed=True)['area_km2'].sum()
log('fallback (>=1:2.5M) by src:\n' + fbs.round(0).to_string())
mid = df[(df['scale_den'].astype('float64') > 1_500_000) & (df['scale_den'].astype('float64') < 2_500_000)]
log('scale_den in (1.5M, 2.5M):', len(mid), float(mid['area_km2'].sum()), sorted(mid['src_id'].astype(str).unique()))
log('done')
REP.close()
