"""Assemble markdown tables from the essd_tables CSVs (local copy) + source metadata. Prints to stdout and
writes the merged T1 CSV (t1_sources_with_meta.csv) next to the inputs for upload."""
import io
import os
import sys

import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
B = os.path.dirname(os.path.abspath(__file__))
E = f'{B}/essd'
meta = pd.read_csv(f'{B}/source_meta.csv', encoding='utf-8')
COUNTRY = {'ca': 'Canada', 'us': 'USA (Alaska)', 'gl': 'Greenland', 'is': 'Iceland', 'no': 'Norway (mainland)',
           'se': 'Sweden', 'fi': 'Finland', 'sj': 'Svalbard & Jan Mayen', 'ru': 'Russia', 'fo': 'Faroe Islands',
           'none': 'no source (U gaps)', 'ALL': 'ALL'}


def sc(d):
    if d is None or (isinstance(d, float) and np.isnan(d)):
        return ''
    d = int(round(d))
    if d >= 1_000_000:
        return f'1:{d / 1e6:g}M'
    if d % 1000 == 0:
        return f'1:{d // 1000}k'
    return f'1:{d:,}'


def yr(v):
    return '' if pd.isna(v) else f'{int(round(v))}'


def km(v, nd=0):
    return '' if pd.isna(v) else f'{v:,.{nd}f}'


def mdt(rows, cols):
    out = ['| ' + ' | '.join(cols) + ' |', '|' + '|'.join(['---'] * len(cols)) + '|']
    for r in rows:
        out.append('| ' + ' | '.join(str(x) for x in r) + ' |')
    return '\n'.join(out)


def section(t):
    print(f'\n### {t}\n')


# ---------------- T1
t1 = pd.read_csv(f'{E}/t1_sources.csv')
m = t1.merge(meta, on='src_id', how='left')
assert m['title'].notna().all(), m.loc[m['title'].isna(), 'src_id'].tolist()
m.to_csv(f'{E}/t1_sources_with_meta.csv', index=False, encoding='utf-8')
section('T1a  Per source: area, polygons, scale, publication year, redistribution (sorted by area)')
rows = []
for i, r in m.iterrows():
    rows.append([i + 1, f'`{r.src_id}`', km(r.area_km2), f'{r.share_pct:.2f}', f'{int(r.n_polygons):,}',
                 int(r.n_sheets), f'{sc(r.scale_min)} / {sc(r.scale_median)} / {sc(r.scale_max)}', sc(r.scale_awmedian),
                 f'{yr(r.pub_min)} / {yr(r.pub_median)} / {yr(r.pub_max)}' if not pd.isna(r.pub_min) else 'n/a',
                 yr(r.pub_awmedian), km(r.pub_missing_km2) if r.pub_missing_km2 > 0.5 else '', r.redistribution if isinstance(r.redistribution, str) else ''])
print(mdt(rows, ['#', 'src_id', 'area km2', 'share %', 'polygons', 'sheets', 'scale min / median / max', 'scale aw-median',
                 'pub_year min / median / max', 'pub_year aw-median', 'pub_year missing km2', 'redistribution']))
section('T1b  Per source: title, publisher, DOI / URL (same order)')
rows = []
for i, r in m.iterrows():
    note = r.meta_note if isinstance(r.meta_note, str) else ''
    rows.append([i + 1, f'`{r.src_id}`', r.title, r.publisher if isinstance(r.publisher, str) else '',
                 r.doi_or_url if isinstance(r.doi_or_url, str) else '', note])
print(mdt(rows, ['#', 'src_id', 'title', 'publisher', 'DOI / URL', 'note']))

section('T1c  By country (src_id prefix)')
b = pd.read_csv(f'{E}/t1b_by_country_prefix.csv')
rows = [[f'`{r.prefix}`', r.country, km(r.area_km2), f'{r.share_pct:.2f}', f'{int(r.n_polygons):,}', int(r.n_sources),
         int(r.n_sheets), sc(r.scale_awmedian), yr(r.pub_awmedian)] for r in b.itertuples()]
rows.append(['**ALL**', '', km(b.area_km2.sum()), '100.00', f'{int(b.n_polygons.sum()):,}', int(b.n_sources.sum()),
             int(b.n_sheets.sum()), '', ''])
print(mdt(rows, ['prefix', 'country', 'area km2', 'share %', 'polygons', 'sources', 'sheets*', 'scale aw-median',
                 'pub_year aw-median']))
section('T1d  By agency group')
g = m.groupby('agency_group').agg(area_km2=('area_km2', 'sum'), n_polygons=('n_polygons', 'sum'),
                                  n_sources=('src_id', 'nunique'), srcs=('src_id', lambda s: ', '.join(s))).reset_index()
g['share'] = 100 * g['area_km2'] / g['area_km2'].sum()
g = g.sort_values('area_km2', ascending=False)
rows = [[r.agency_group, km(r.area_km2), f'{r.share:.2f}', f'{int(r.n_polygons):,}', r.n_sources if r.agency_group != '(no source)' else 0,
         r.srcs] for r in g.itertuples()]
print(mdt(rows, ['agency group', 'area km2', 'share %', 'polygons', 'sources', 'src_ids']))

# ---------------- T2
section('T2  Area by hclass: all land and coastal==1 polygons')
t2 = pd.read_csv(f'{E}/t2_hclass.csv')
t2['name'] = t2['name'].fillna('')
t2.loc[t2.hclass == 'H', 'name'] = 'Water body (undocumented in LEGEND.md)'
rows = [[r.hclass, r.name, km(r.area_km2), f'{r.share_pct:.2f}', f'{int(r.n_polygons):,}', km(r.coastal_area_km2),
         f'{r.coastal_share_pct:.2f}', f'{int(r.coastal_n_polygons):,}', f'{r.coastal_frac_of_class_pct:.1f}'] for r in t2.itertuples()]
print(mdt(rows, ['hclass', 'name', 'area km2', 'share %', 'polygons', 'coastal km2', 'coastal share %', 'coastal polygons',
                 'coastal / class area %']))

# ---------------- T3
section('T3  Area (km2) by nominal scale class (bins of scripts/coverage_map.py), overall and per country prefix')
t3 = pd.read_csv(f'{E}/t3_scale_class_by_prefix.csv', index_col=0)
p3 = pd.read_csv(f'{E}/t3_scale_class_by_prefix_pct.csv', index_col=0)
cols = list(t3.columns)
rows = []
for p in t3.index:
    rows.append([f'`{p}`' if p != 'ALL' else '**ALL**'] + [f'{km(t3.loc[p, c])} ({p3.loc[p, c]:.1f}%)' if c != 'total' else km(t3.loc[p, c]) for c in cols])
print(mdt(rows, ['prefix'] + cols))
section('T3b  scale_den values in each class')
v = pd.read_csv(f'{E}/t3b_scale_den_values.csv')
rows = [[r.scale_class, sc(r.scale_den) if not pd.isna(r.scale_den) else '(null)', f'{int(r.n_polygons):,}', km(r.area_km2),
         r.srcs] for r in v.itertuples()]
print(mdt(rows, ['class', 'scale_den', 'polygons', 'area km2', 'sources (first 8)']))

# ---------------- T4
section('T4  Area by pub_year decade: all sources and ru_ sources')
t4 = pd.read_csv(f'{E}/t4_decade_overall_ru.csv', index_col=0)
order = ['1950s', '1960s', '1970s', '1980s', '1990s', '2000s', '2010s', '2020s', 'missing', 'TOTAL']
rows = [[d, km(t4.loc[d, 'all_km2']), f"{t4.loc[d, 'all_pct']:.1f}", km(t4.loc[d, 'ru_km2']), f"{t4.loc[d, 'ru_pct']:.1f}"]
        for d in order if d in t4.index]
print(mdt(rows, ['decade', 'all km2', 'all %', 'ru_ km2', 'ru_ %']))
section('T4b  Decade x country prefix (km2)')
d4 = pd.read_csv(f'{E}/t4_decade_by_prefix.csv', index_col=0)
d4 = d4.reindex([o for o in order if o in d4.index])
rows = [[i] + [km(x) for x in r] for i, r in d4.iterrows()]
print(mdt(rows, ['decade'] + list(d4.columns)))

# ---------------- T5
section('T5  Area by redistribution (km2 and row %)')
t5 = pd.read_csv(f'{E}/t5_redistribution_by_prefix.csv', index_col=0)
cols = [c for c in ['open', 'internal_only', 'unknown', '<NA (no source)>'] if c in t5.columns]
rows = []
for p in t5.index:
    tot = t5.loc[p, 'total']
    rows.append([f'`{p}`' if p != 'ALL' else '**ALL**'] + [f'{km(t5.loc[p, c])} ({100 * t5.loc[p, c] / tot:.1f}%)' for c in cols] + [km(tot)])
print(mdt(rows, ['prefix'] + [c.replace('<NA (no source)>', 'null (U gaps)') for c in cols] + ['total']))

# ---------------- T6
section('T6a  pf_zone (Obu et al. 2019)')
for c in ['pf_zone', 'yedoma', 'yedoma_conf']:
    x = pd.read_csv(f'{E}/t6_{c}.csv', index_col=0)
    x.index = [('(empty)' if (isinstance(i, float) or i == '') else i) for i in x.index]
    rows = [[i, km(r['sum']), f"{r['pct']:.2f}", f"{int(r['size']):,}"] for i, r in x.iterrows()]
    print(f'\n{c}:\n')
    print(mdt(rows, [c, 'area km2', '%', 'polygons']))
section('T6b  hclass Y (ice complex / Yedoma) x IRYP yedoma flag (km2)')
x = pd.read_csv(f'{E}/t6_hclassY_x_yedoma.csv', index_col=0)
cols = [c for c in ['yes', 'uncertain', 'no', 'not_assessed', 'total'] if c in x.columns]
rows = [[i] + [km(x.loc[i, c]) for c in cols] for i in x.index]
print(mdt(rows, [''] + cols))
x = pd.read_csv(f'{E}/t6_hclassY_by_src_x_yedoma.csv', index_col=0)
cols = [c for c in ['yes', 'uncertain', 'no', 'total'] if c in x.columns]
rows = [[f'`{i}`'] + [km(x.loc[i, c]) for c in cols] for i in x.sort_values('total', ascending=False).index]
print('\nhclass Y by source:\n')
print(mdt(rows, ['src_id'] + cols))
x = pd.read_csv(f'{E}/t6_yedoma_yes_by_hclass.csv', index_col=0)
print('\nIRYP yedoma == yes, by hclass (km2): ' + '; '.join(f'{i} {km(v)}' for i, v in x.iloc[:, 0].items()))

# ---------------- T7
section('T7a  Completeness by country prefix')
t7 = pd.read_csv(f'{E}/t7_completeness_by_prefix.csv', index_col=0)
rows = [[f'`{p}`' if p != 'ALL' else '**ALL**', km(r.area_km2), f'{km(r.U_km2)} ({r.U_pct:.2f}%)', f'{km(r.Q_km2)} ({r.Q_pct:.2f}%)',
         f"{km(r['fallback_ge2.5M_km2'])} ({r.fallback_pct:.2f}%)", f'{km(r.U_or_Q_or_fallback_km2)} ({r.U_or_Q_or_fallback_pct:.2f}%)']
        for p, r in t7.iterrows()]
print(mdt(rows, ['prefix', 'area km2', 'U km2 (%)', 'Q km2 (%)', 'fallback >=1:2.5M km2 (%)', 'U or Q or fallback km2 (%)']))
section('T7b  Completeness by territory (point-on-surface in Natural Earth 10m admin-0; Norway split at 74N / Jan Mayen)')
t = pd.read_csv(f'{E}/geo_t7_by_territory.csv', index_col=0)
t = t[t['total'] > 1]
rows = [[i, km(r.total), f'{km(r.U)} ({r.U_pct:.2f}%)', f'{km(r.Q)} ({r.Q_pct:.2f}%)',
         f"{km(r['fallback_ge2.5M'])} ({r['fallback_ge2.5M_pct']:.2f}%)"] for i, r in t.iterrows()]
print(mdt(rows, ['territory', 'area km2', 'U km2 (%)', 'Q km2 (%)', 'fallback km2 (%)']))
section('T7c  Source prefix x territory (km2)')
x = pd.read_csv(f'{E}/geo_prefix_x_territory.csv', index_col=0)
x = x.loc[:, (x.loc['ALL'] > 1)]
rows = [[f'`{i}`'] + [km(v) for v in r] for i, r in x.iterrows()]
print(mdt(rows, ['prefix'] + list(x.columns)))

# ---------------- polygons
section('Polygon size distribution (km2)')
p = pd.read_csv(f'{E}/polygon_size.csv')
rows = [[r.subset, f'{int(r.n):,}', f'{r.p10:.5f}', f'{r.median:.4f}', f'{r.p90:.3f}', f'{r.mean:.3f}', f'{r.area_weighted_median:,.1f}']
        for r in p.itertuples()]
print(mdt(rows, ['subset', 'n', 'p10', 'median', 'p90', 'mean', 'area-weighted median']))
s = pd.read_csv(f'{E}/summary.csv')
print('\nsummary.csv:')
for r in s.itertuples():
    print(f'- {r.metric}: {r.value}')
