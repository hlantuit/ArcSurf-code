#!/usr/bin/env python
"""What thickness information do the source maps carry? Scans the native units of the addendum (units.csv) for
  (a) numeric thickness statements in the unit description (src_desc) and code, in the languages of the sources
      (Russian 'мощность', English 'thick', French 'épaisseur', Scandinavian 'mektighet / mäktighet', Finnish
      'paksuus'), and
  (b) cover terms (veneer / blanket / discontinuous, harmonised in the 'cover' column),
and reports, per source, the share of the area each kind of information covers, with examples.
usage: addendum_thickness_scan.py UNITS_CSV [OUT_CSV]"""
import re
import sys

import pandas as pd

NUM = r'(\d+(?:[.,]\d+)?)'
RNG = rf'{NUM}(?:\s*(?:-|–|—|to|до|à|a|til|till)\s*{NUM})?'
PATTERNS = [
    ('ru', re.compile(rf'мощн\w*\.?\s*(?:[\w.,]+\s+){{0,3}}?(?:(?:от|до|свыше|более|менее|около)\s*)?{RNG}\s*(см|м)\b',
                      re.I)),
    ('en', re.compile(rf'(?:(?:up to|less than|greater than|more than|over|under|<|>|≤|≥)\s*)?{RNG}\s*(cm|m)\s*'
                      rf'(?:or more\s*)?(?:thick|in thickness|deep)', re.I)),
    ('en2', re.compile(rf'thick(?:ness)?\w*\s*(?:of|is|up to|less than|greater than|>|<)?\s*{RNG}\s*(cm|m)\b', re.I)),
    ('fr', re.compile(rf'épaisseur\w*\s*(?:de|inférieure à|supérieure à|moyenne de|<|>)?\s*{RNG}\s*(cm|m)\b', re.I)),
    ('no_se', re.compile(rf'm(?:e|ä)ktighet\w*\s*(?:på|på over|over|under|<|>)?\s*{RNG}\s*(cm|m)\b', re.I)),
    ('fi', re.compile(rf'paksu\w*\s*{RNG}\s*(cm|m)\b', re.I)),
    ('sym', re.compile(rf'(?:<|>|≤|≥)\s*{NUM}\s*(cm|m)\b(?!\w)')),
]


def find(text):
    if not isinstance(text, str) or not text:
        return None
    for lang, p in PATTERNS:
        m = p.search(text)
        if m:
            return lang, m.group(0)
    return None


def main():
    u = pd.read_csv(sys.argv[1], keep_default_na=False, low_memory=False)
    out = sys.argv[2] if len(sys.argv) > 2 else None
    hits = [find(f'{d} {c}') for d, c in zip(u['src_desc'], u['src_code'])]
    u['thk_lang'] = [h[0] if h else '' for h in hits]
    u['thk_text'] = [h[1] if h else '' for h in hits]
    u['area_km2'] = pd.to_numeric(u['area_km2'], errors='coerce').fillna(0.0)
    tot = u['area_km2'].sum()
    has_t = u['thk_lang'] != ''
    has_c = u['cover'].isin(['veneer', 'blanket', 'discontinuous'])
    print(f'native units {u["unit_code"].nunique():,} (rows {len(u):,}), area {tot:,.0f} km2')
    print(f'numeric thickness in the unit text: {int(has_t.sum()):,} rows, {u.loc[has_t, "area_km2"].sum():,.0f} km2 '
          f'({100 * u.loc[has_t, "area_km2"].sum() / tot:.1f} %)')
    print(f'cover term (veneer / blanket / discontinuous): {u.loc[has_c, "area_km2"].sum():,.0f} km2 '
          f'({100 * u.loc[has_c, "area_km2"].sum() / tot:.1f} %); either: '
          f'{100 * u.loc[has_t | has_c, "area_km2"].sum() / tot:.1f} %')
    g = u.assign(t_km2=u['area_km2'].where(has_t, 0.0), c_km2=u['area_km2'].where(has_c, 0.0)).groupby('src_id').agg(
        area_km2=('area_km2', 'sum'), thk_km2=('t_km2', 'sum'), cover_km2=('c_km2', 'sum'),
        thk_units=('thk_lang', lambda s: int((s != '').sum())), langs=('thk_lang', lambda s: ','.join(sorted(set(s) - {''}))))
    g['thk_pct'] = 100 * g['thk_km2'] / g['area_km2']
    g['cover_pct'] = 100 * g['cover_km2'] / g['area_km2']
    pd.set_option('display.width', 220)
    print(g.sort_values('area_km2', ascending=False).round(1).to_string())
    print('== examples per language')
    for lang in sorted(set(u['thk_lang']) - {''}):
        ex = u[u['thk_lang'] == lang].sort_values('area_km2', ascending=False).head(6)
        for _, r in ex.iterrows():
            print(f'  [{lang}] {r["src_id"]} {r["hclass"]} {r["area_km2"]:,.0f} km2: "{r["thk_text"]}" | '
                  f'{str(r["src_desc"])[:150]}')
    print('== cover terms by source (km2)')
    print(u[has_c].pivot_table(index='src_id', columns='cover', values='area_km2', aggfunc='sum', fill_value=0)
          .round(0).to_string())
    if out:
        u[has_t][['unit_code', 'src_id', 'src_sheet', 'src_code', 'hclass', 'cover', 'area_km2', 'thk_lang', 'thk_text',
                  'src_desc']].to_csv(out, index=False)


if __name__ == '__main__':
    main()
