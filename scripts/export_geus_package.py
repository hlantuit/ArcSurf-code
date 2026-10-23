#!/usr/bin/env python
"""The GEUS-derived Greenland layer of ArcSurf and its unit translation table, for GEUS's review (Hugues 2026-10-08:
"extract the greenland layer and the unit translation table so that I can send them directly with the email").

  ArcSurf_Greenland_GEUS-derived.gpkg  the dissolved ArcSurf polygons whose source is a GEUS map (1:500 000 v3.0 and
                                       the three 1:100 000 Karrat sheets), EPSG:6931, licence CC BY-SA 4.0
  units.csv                            one row per GEUS native unit: GEUS label and description, ArcSurf class (for
                                       units now under modern glacier ice: the class of the GEUS unit beneath),
                                       second class, texture, cover, the crosswalk note, area and polygon count
usage: export_geus_package.py DISSOLVE_DIR OUT_DIR"""
import glob
import os
import sys

import pandas as pd
import geopandas as gpd
import pyogrio

SRC = ('gl_geus_g500_v3', 'gl_geus_g100_karrat')
LIC = 'CC BY-SA 4.0 (derived from GEUS data; confirmed by GEUS, email of 2026-10-08)'
NAMES = {'R': 'Bedrock', 'T': 'Till', 'GF': 'Glaciofluvial', 'GL': 'Glaciolacustrine', 'GM': 'Glaciomarine',
         'M': 'Marine and littoral', 'F': 'Fluvial', 'L': 'Lacustrine', 'K': 'Thermokarst and alas',
         'Y': 'Ice complex (Yedoma)', 'E': 'Eolian', 'C': 'Colluvial and mass-wasting', 'W': 'Residual regolith',
         'O': 'Organic', 'V': 'Quaternary volcanic', 'X': 'Anthropogenic', 'I': 'Glacier and perennial ice',
         'Q': 'Quaternary, origin not stated', 'H': 'Water body', 'U': 'No source'}
KEEP = ['src_id', 'src_sheet', 'src_code', 'src_desc', 'hclass', 'hclass_name', 'hclass2', 'texture', 'cover',
        'scale_den', 'pub_year', 'licence', 'xwalk_note', 'hclass_under_ice', 'ice_src', 'ice_year', 'ice_note',
        'coastal', 'area_km2']


def main():
    dd, out = sys.argv[1:3]
    os.makedirs(out, exist_ok=True)
    g = pd.concat([gpd.read_parquet(f) for f in sorted(glob.glob(f'{dd}/final/*.parquet'))], ignore_index=True)
    g = gpd.GeoDataFrame(g, geometry='geometry', crs='EPSG:6931')
    g = g[g['src_id'].astype(str).isin(SRC)].copy()
    g['licence'] = LIC
    g['hclass_name'] = g['hclass'].astype(str).map(NAMES).fillna('')
    g['area_km2'] = g.area / 1e6
    g = g[KEEP + ['geometry']].sort_values(['src_id', 'src_sheet', 'src_code']).reset_index(drop=True)
    for c in g.columns:
        if c != 'geometry' and str(g[c].dtype) in ('string', 'object'):
            g[c] = g[c].astype(object).where(g[c].notna(), None)
    path = f'{out}/ArcSurf_Greenland_GEUS-derived.gpkg'
    if os.path.exists(path):
        os.remove(path)
    pyogrio.write_dataframe(g, path, layer='arcsurf_greenland_geus', driver='GPKG')
    print(f'{path}: {len(g):,} polygons, {g["area_km2"].sum():,.0f} km2, {os.path.getsize(path) / 1e6:.1f} MB',
          flush=True)

    # translation table: one row per GEUS native unit
    d = pd.DataFrame(g.drop(columns='geometry'))
    under = (d['hclass'] == 'I') & d['hclass_under_ice'].fillna('').astype(str).ne('')
    d['arcsurf_class'] = d['hclass'].where(~under, d['hclass_under_ice'])
    d['area_under_ice_km2'] = d['area_km2'].where(d['hclass'] == 'I', 0.0)
    keys = ['src_id', 'src_sheet', 'src_code', 'src_desc']
    for c in keys:
        d[c] = d[c].fillna('').astype(str)
    t = d.groupby(keys, as_index=False).agg(
        arcsurf_class=('arcsurf_class', lambda s: s.mode().iat[0] if len(s.mode()) else ''),
        arcsurf_class2=('hclass2', lambda s: s.dropna().astype(str).mode().iat[0] if len(s.dropna()) else ''),
        texture=('texture', 'first'), cover=('cover', 'first'), crosswalk_note=('xwalk_note', 'first'),
        area_km2=('area_km2', 'sum'), area_under_modern_ice_km2=('area_under_ice_km2', 'sum'),
        n_polygons=('area_km2', 'size'))
    t.insert(5, 'arcsurf_class_name', t['arcsurf_class'].map(NAMES).fillna(''))
    t = t.rename(columns={'src_id': 'geus_dataset', 'src_sheet': 'sheet', 'src_code': 'geus_unit_label',
                          'src_desc': 'geus_description'})
    t['geus_dataset'] = t['geus_dataset'].map({'gl_geus_g500_v3': 'GEUS 1:500 000 v3.0 (doi:10.22008/FK2/FWX5ET)',
                                               'gl_geus_g100_karrat': 'GEUS 1:100 000 Karrat sheets'})
    t = t.sort_values(['geus_dataset', 'sheet', 'arcsurf_class', 'area_km2'], ascending=[True, True, True, False])
    t.to_csv(f'{out}/units.csv', index=False)
    print(f'units.csv: {len(t):,} GEUS units; classes {t.groupby("arcsurf_class")["area_km2"].sum().round(0).to_dict()}',
          flush=True)


if __name__ == '__main__':
    main()
