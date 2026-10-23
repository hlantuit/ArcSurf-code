#!/usr/bin/env python
"""For the cross-country legend decisions: per harmonised class x country, the area in
the MERGED layer and the native units (src_desc) that make it up, largest first.
Also: ice_rich / texture 'unknown' shares per country (the flags are only as complete
as each legend), and Q/U shares. Writes work/legend_audit.json + legend_audit.csv.

Null space: shows what each class CONTAINS per country; whether two countries' units
are the same thing is the judgement this table is for, not something it establishes."""
import glob
import json
import sys
from multiprocessing import Pool

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402

COUNTRY = {'ca': 'Canada', 'us': 'Alaska', 'ru': 'Russia', 'gl': 'Greenland', 'no': 'Norway',
           'sj': 'Svalbard/JanMayen', 'se': 'Sweden', 'fi': 'Finland', 'is': 'Iceland', 'none': 'unmapped'}


def one(f):
    g = gpd.read_parquet(f, columns=['src_id', 'src_desc', 'hclass', 'hclass2', 'texture', 'ice_rich', 'coastal', 'geometry'])
    g['km2'] = g.area / 1e6
    return pd.DataFrame(g.drop(columns='geometry'))


def main():
    with Pool(32) as p:
        d = pd.concat(p.map(one, sorted(glob.glob(f'{S.WORK}/tiles/*.parquet'))), ignore_index=True)
    d['country'] = d['src_id'].str.split('_').str[0].map(COUNTRY).fillna('?')
    d['src_desc'] = d['src_desc'].fillna('').astype(str).str.slice(0, 90)
    rows = []
    for (h, c), sub in d.groupby(['hclass', 'country']):
        top = sub.groupby(['src_id', 'src_desc']).km2.sum().sort_values(ascending=False).head(6)
        rows.append(dict(hclass=h, country=c, km2=round(sub.km2.sum()), coastal_km2=round(sub.loc[sub.coastal == 1, 'km2'].sum()),
                         top_units=' || '.join(f'{s}: {t} ({v:,.0f})' for (s, t), v in top.items())))
    t = pd.DataFrame(rows).sort_values(['hclass', 'km2'], ascending=[True, False])
    t.to_csv(f'{S.WORK}/legend_audit.csv', index=False)
    c = d.groupby('country').km2.sum()
    flags = {}
    for k in ('ice_rich', 'texture'):
        flags[k] = (d[d[k].fillna('unknown') == 'unknown'].groupby('country').km2.sum() / c).round(3).to_dict()
    flags['Q'] = (d[d.hclass == 'Q'].groupby('country').km2.sum() / c).round(4).to_dict()
    flags['ice_rich_yes'] = (d[d.ice_rich == 'yes'].groupby('country').km2.sum() / c).round(4).to_dict()
    flags['Y'] = (d[d.hclass == 'Y'].groupby('country').km2.sum() / c).round(4).to_dict()
    json.dump(dict(country_km2=c.round().to_dict(), unknown_or_share=flags), open(f'{S.WORK}/legend_audit.json', 'w'), indent=1)
    print(json.dumps(dict(country_km2=c.round().to_dict(), shares=flags), indent=1))
    pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 170)
    print(t[['hclass', 'country', 'km2', 'coastal_km2', 'top_units']].to_string(index=False))


if __name__ == '__main__':
    main()
