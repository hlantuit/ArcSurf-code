#!/usr/bin/env python
"""
Bryant / USGS "Siberian Database" -- digitised VSEGEI 1:1,000,000 Quaternary sheets
(11 sheets, Yakutia 96-162E, 60-77N). Already on Albedo (arcticbeach/data).

Native structure
  GeologicPolygon<sheet>_open.shp : GeneticTyp (age-qualified symbol, e.g. a6N2-Q1),
                                    ClastSize1..5 (clast-type names), Yedoma flag
  GeneticTypeSymbol.dbf           : (Map, Symbol) -> GeneticTyp name + Age

Crosswalk key: the GENETIC TYPE NAME from the lookup (~96 names), not the symbol
(412 symbols) -- age qualifiers do not change hclass.

Texture: from ClastSize1..5. One texture category -> that category; several ->
'mixed'. Ice: 'yes' where the Yedoma flag is set or an ice clast symbol is mapped;
otherwise 'unknown' (an absent symbol is not a measurement of absence).
Licence recorded as the source states it: "Not Specified" -> internal_only.
"""
import glob
import os
import re
import sys

import pandas as pd
import pyogrio
import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S
import seam  # noqa: E402

SRC = 'ru_bryant_vsegei1m'
D = '/albedo/work/user/hlantuit/arcticbeach/data/bryant_siberia/SiberianDatabase-open'

CLAST_TEX = {
    'Sand': 'sand', 'Eolian sand': 'sand', 'Eolian Sand': 'sand',
    'Rounded pebbles': 'gravel', 'Unrounded pebbles': 'gravel',
    'Rounded gravel': 'gravel', 'Unrounded gravel': 'gravel', 'Ventifacts': 'gravel',
    'Boulders': 'bouldery', 'Unrounded rocks': 'bouldery',
    'Silt': 'fines', 'Loam': 'fines', 'Clay': 'fines', 'Loam (Alevrit)': 'fines',
    'Alevrit': 'fines', 'Clay (Alevritic clay)': 'fines', 'Alevritic clay': 'fines',
    'Clay Without Layering': 'fines', 'Clay Varved': 'fines', 'Mud': 'fines',
    'Silt (sandy Alevrit)': 'fines', 'Silt (sandy alevrit)': 'fines', 'Loess': 'fines',
    'Peat': 'organic',
}
CLAST_ICE = {'Ice Rich Ground', 'Massive ground ice'}
CLAST_IGNORE = {'Effusive volcanics: mafic', 'Effusive volcanics: silicic',
                'Buried soils', 'Glacier'}


def sheet_code(fname):
    m = re.search(r'GeologicPolygon([A-Z])(\d{2})(\d{2})_open', fname)
    return f'{m.group(1)}{m.group(2)},{m.group(3)}'   # matches lookup 'Map' field


def texture_ice(row):
    vals = [row[f'ClastSize{i}'] for i in range(1, 6)]
    vals = [v.strip() for v in vals if isinstance(v, str) and v.strip()]
    unknown = [v for v in vals if v not in CLAST_TEX and v not in CLAST_ICE
               and v not in CLAST_IGNORE]
    assert not unknown, f'unmapped clast types {unknown}'
    tex = {CLAST_TEX[v] for v in vals if v in CLAST_TEX}
    texture = tex.pop() if len(tex) == 1 else ('mixed' if tex else 'unknown')
    ice = 'yes' if (row['Yedoma'] == 'Yedoma' or any(v in CLAST_ICE for v in vals)) else 'unknown'
    return pd.Series({'texture_src': texture, 'ice_src': ice, 'clasts': '|'.join(vals)})


# publication year of the VSEGEI map each sheet digitises, from the source information of the USGS metadata
# (<srcinfo> of GeologicPolygon<sheet>_open.shp.xml, read 2026-10-08). Without it the sheets sorted as year 0 in
# the merge, and a colour-classified scan of the same printed map (Q-50-51_g2, Kolpakov 1986) took the Q-51 half of
# Q50,51 (merge 44; fixed in merge 45).
YEARS = {'P5051': 1987, 'P5253': 1992, 'Q5051': 1986, 'Q5253': 1982, 'Q5455': 1985, 'Q5657': 1986, 'R5355': 1990,
         'R5557': 1998, 'S4749': 1988, 'S5052': 2000, 'S5355': 1995}


def year_of(sh):
    k = re.sub(r'\W', '', sh)
    for key, y in YEARS.items():
        if key in k:
            return y
    raise KeyError(f'no publication year for Bryant sheet {sh!r}')


def main():
    lut = pyogrio.read_dataframe(f'{D}/GeneticTypeSymbol.dbf', read_geometry=False)
    lut = lut.rename(columns={'Symbol': 'sym', 'GeneticTyp': 'gen_name', 'Age': 'age'})
    lut['sym'] = lut['sym'].str.strip()
    lut = lut.drop_duplicates(['Map', 'sym'])

    units, fps, stats = [], [], []
    for f in sorted(glob.glob(f'{D}/GeologicPolygon*_open.shp')):
        sh = sheet_code(f)
        g = gpd.read_file(f)
        # the .prj says WGS84, but the sheets are VSEGEI Pulkovo-1942 compilations: the
        # project decision (coast test on R-52; seam test vs R-52) is EPSG:4284 for ALL
        # VSEGEI-derived sheets, so neighbouring 1:200k PDF sheets share one datum
        g = g.set_crs(4284, allow_override=True)
        raw_bounds = g.total_bounds
        g['Map'] = sh
        g['sym'] = g['GeneticTyp'].astype('string').str.strip()
        g = g.merge(lut[['Map', 'sym', 'gen_name', 'age']], on=['Map', 'sym'], how='left')
        nomatch = g['gen_name'].isna()
        stats.append((sh, len(g), int(nomatch.sum()),
                      sorted(g.loc[nomatch, 'sym'].dropna().unique().tolist())[:15]))
        g['gen_name'] = g['gen_name'].fillna('__NO_LOOKUP__')
        g = pd.concat([g, g.apply(texture_ice, axis=1)], axis=1)
        g['desc'] = g['gen_name'] + ' | ' + g['age'].fillna('')
        # only the Yedoma FLAG makes a polygon Y; ice clast symbols on e.g. marine
        # terraces mark ice-rich ground but not an ice complex
        g['hclass_src'] = (g['Yedoma'] == 'Yedoma').map({True: 'Y', False: ''})
        u, _ = S.standardise(
            g, src_id=SRC, code='sym', desc='desc', sheet='Map', xkey='gen_name',
            extra=('clasts', 'Yedoma', 'Color'),
            carry=('texture_src', 'ice_src', 'hclass_src'),
            scale_den=1_000_000, pub_year=year_of(sh),
            licence='US public domain (USGS Director-approved release, access constraints none; Grosse et al. 2017, doi:10.5066/F7VT1Q89)',
            redistribution='open')
        u = u.rename(columns={'ice_src': 'ice_rich_src'})
        # onto the exact 1:1M frame (whole-degree sides only; irregular annexes untouched)
        u, rep = seam.band_snap(u, raw_bounds, datum=4284, band=500.0)
        print('  ', sh, 'band_snap', rep)
        units.append(u)
        fp = S.footprint_from_units(u)
        fp['src_sheet'] = sh
        fps.append(fp)

    units = gpd.GeoDataFrame(pd.concat(units, ignore_index=True), crs=S.CRS)
    footprint = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
    for sh, n, nm, ex in stats:
        print(f'{sh}: {n} polygons, {nm} with no lookup match {ex}')
    p, meta = S.write_std(units, footprint, SRC, dict(
        title='USGS Siberian Database: VSEGEI 1:1M Quaternary deposits (11 sheets)', datum='EPSG:4284 assumed (prj says WGS84)',
        path=D, sheets=[s[0] for s in stats],
        lookup_misses={s[0]: s[2] for s in stats}))
    print(meta)
    S.code_table(units).to_csv(f'{S.WORK}/codes_{SRC}.csv', index=False)
    print('texture', units['texture_src'].value_counts().to_dict())
    print('ice', units['ice_rich_src'].value_counts().to_dict())
    print('wrote', p)


if __name__ == '__main__':
    main()
