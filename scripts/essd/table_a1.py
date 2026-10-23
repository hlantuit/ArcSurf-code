#!/usr/bin/env python
"""Appendix Table A1 of the data paper (every source dataset with its citation) and the extra reference entries it
needs, from the per-source statistics of the merge (essd_stats t1_sources.csv) and a citation table.

  citations.tsv  tab-separated, one row per src_id: src_id, name (map or database, short), cite (in-text citation,
                 e.g. "Wilson et al., 2015"), reference (full Copernicus-style entry; several separated by " || "),
                 licence_short (e.g. "OGL-Canada", "CC BY 4.0", "not released")
writes  <parts>/07b_appendix.html, <parts>/refs_tableA1.txt, <out_csv> (src_id, region, name, cite, licence_short)
usage: table_a1.py T1_SOURCES.csv CITATIONS.tsv PARTS_DIR OUT_CSV"""
import html
import sys

import pandas as pd

T1, CIT, PARTS, OUT = sys.argv[1:5]
REGION = {'ru': 'Russia', 'ca': 'Canada', 'gl': 'Greenland', 'us': 'Alaska', 'no': 'Norway', 'se': 'Sweden',
          'is': 'Iceland', 'fi': 'Finland', 'sj': 'Svalbard and Jan Mayen', 'fo': 'Faroe Islands'}
ORDER = list(REGION)

t = pd.read_csv(T1, encoding='utf-8', encoding_errors='replace')
t = t[t['src_id'] != 'none'].copy()
c = pd.read_csv(CIT, sep='\t', dtype=str, keep_default_na=False)
miss = sorted(set(t['src_id']) - set(c['src_id']))
if miss:
    sys.exit(f'no citation for {miss}')
t = t.merge(c, on='src_id', how='left')
t['prefix'] = t['src_id'].str.split('_').str[0]
t['region'] = t['prefix'].map(REGION)
t['rk'] = t['prefix'].map({p: i for i, p in enumerate(ORDER)})
t = t.sort_values(['rk', 'area_km2'], ascending=[True, False])


def scale(r):
    a, b = int(r['scale_min']), int(r['scale_max'])
    f = lambda v: f'1:{v:,}'                       # noqa: E731
    return f(a) if a == b else f'{f(a)}–{f(b)}'


def years(r):
    if pd.isna(r['pub_min']):
        return '–'
    a, b = int(r['pub_min']), int(r['pub_max'])
    return str(a) if a == b else f'{a}–{b}'


rows = []
for reg, g in t.groupby('region', sort=False):
    for i, r in enumerate(g.itertuples(index=False)):
        r = r._asdict()
        cells = ([f'<td rowspan="{len(g)}">{html.escape(reg)}</td>'] if i == 0 else []) + [
            f'<td>{html.escape(r["name"])} ({html.escape(r["cite"])})</td>',
            f'<td>{scale(r)}</td>', f'<td class="num">{years(r)}</td>', f'<td class="num">{int(r["n_sheets"]):,}</td>',
            f'<td class="num">{r["area_km2"] / 1e3:,.1f}</td>']
        rows.append('      <tr>' + ''.join(cells) + '</tr>')
part = ('<section id="appendix">\n'
        '  <h2>Appendix A: Sources</h2>\n'
        '  <div class="tbl wide">\n  <table>\n'
        f'    <caption>Table A1. The {len(t)} source datasets of ArcSurf by region, ordered by the area they contribute. '
        'Scale is the nominal scale of the sheets used; area is the land each source contributes to the map, where '
        'the most detailed source takes precedence. The individual sheets, with their publication years and '
        'references, are listed in Table S1 in the Supplement and in the file sources.csv of the data release.'
        '</caption>\n'
        '    <thead><tr><th>Region</th><th>Map or database</th><th>Scale</th><th class="num">Year</th>'
        '<th class="num">Sheets</th><th class="num">Area (10³ km²)</th></tr></thead>\n'
        '    <tbody>\n' + '\n'.join(rows) + '\n    </tbody>\n  </table>\n  </div>\n</section>\n')
open(f'{PARTS}/07b_appendix.html', 'w', encoding='utf-8', newline='\n').write(part)
refs = []
for v in t['reference']:
    refs.extend(x.strip() for x in str(v).split(' || ') if x.strip())
open(f'{PARTS}/refs_tableA1.txt', 'w', encoding='utf-8', newline='\n').write('\n'.join(refs) + '\n')
t[['src_id', 'region', 'name', 'cite', 'licence_short']].to_csv(OUT, index=False)
print(f'Table A1: {len(t)} sources in {t["region"].nunique()} regions; {len(refs)} reference entries')
