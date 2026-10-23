#!/usr/bin/env python
"""
GEUS Greenland: seamless 1:500,000 v3 (doi:10.22008/FK2/FWX5ET) and the three
2022 digital 1:100,000 sheets (Pannertooq, Nuugaatsiaq, Maarmorilik; Karrat).

Crosswalk key: gm_label for QUATERNARY / MISC units; every pre-Quaternary unit
collapses to xkey 'BEDROCK' (a surficial map needs 'bedrock', not 479 lithologies;
the native label stays in src_code).

CRS: Pannertooq.gpkg carries NO CRS. Its coordinates match the neighbouring
Nuugaatsiaq sheet (GR96 / UTM 22N, EPSG:3182) in both magnitude and overlap, so
3182 is assigned -- recorded in the source json.
Licence (all GEUS): internal use only; no derived maps to third parties without
GEUS written consent.
"""
import os
import sys

import pandas as pd
import geopandas as gpd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

D = f'{S.RAW}/greenland'
# 2026-10-08: GEUS confirmed by email (correspondence/2026-10-08_GEUS_reply_received.txt) that the applicable licence
# is CC BY-SA 4.0; the "internal use only" terms still shown on GEUS Dataverse are older portal conditions. Derived
# GEUS layers keep CC BY-SA 4.0 ('open_sa': released as their own share-alike dataset).
LIC = 'CC BY-SA 4.0 (GEUS; confirmed by GEUS, email of 2026-10-08)'
RED = 'open_sa'
G100 = {'Pannertooq': 2022, 'Nuugaatsiaq': 2022, 'Maarmorilik': 2022}


def g500():
    src = 'gl_geus_g500_v3'
    g = gpd.read_file(f'{D}/geus500k_v3.gpkg', layer='Geology_polygon')
    q = g['Header'].fillna('').str.upper().isin(['QUATERNARY', 'MISC (NOT IN LEGEND)'])
    g['xkey'] = g['gm_label'].where(q, 'BEDROCK')
    g['desc'] = g['Header'].fillna('') + ' | ' + g['Description'].fillna('')
    u, _ = S.standardise(g, src_id=src, code='gm_label', desc='desc', xkey='xkey',
                         scale_den=500_000, pub_year=2023, licence=LIC,
                         redistribution=RED)
    fp = S.footprint_from_units(u, simplify=200.0)
    S.write_std(u, fp, src, dict(title='GEUS seamless 1:500 000 geological map of Greenland v3',
                                 doi='10.22008/FK2/FWX5ET'))
    S.code_table(u).to_csv(f'{S.WORK}/codes_{src}.csv', index=False)
    print(src, len(u), u.area.sum() / 1e6)


def g100():
    src = 'gl_geus_g100_karrat'
    parts, fps = [], []
    for sh, yr in G100.items():
        g = gpd.read_file(f'{D}/{sh}.gpkg', layer='Geology polygons')
        crs_note = ''
        if g.crs is None:
            g = g.set_crs(3182)
            crs_note = 'no CRS in file; assigned EPSG:3182 (GR96/UTM 22N) as for the adjacent sheet'
        q = g['Heading'].fillna('Quarternary deposits').str.startswith('Quar')
        g['xkey'] = g['gm_label'].where(q, 'BEDROCK')
        g['desc'] = g['Heading'].fillna('') + ' | ' + g['short_description'].fillna('')
        u, _ = S.standardise(g, src_id=src, code='gm_label', desc='desc', xkey='xkey',
                             sheet=pd.Series(sh, index=g.index), scale_den=100_000,
                             pub_year=yr, licence=LIC, redistribution=RED)
        fp = S.footprint_from_units(u)
        fp['src_sheet'] = sh
        parts.append(u)
        fps.append(fp)
        print(sh, len(u), round(u.area.sum() / 1e6), crs_note)
    u = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
    S.write_std(u, fp, src, dict(title='GEUS 1:100 000 geological map sheets, Karrat (2022 digital)',
                                 sheets=list(G100), crs_note='Pannertooq assigned EPSG:3182'))
    S.code_table(u).to_csv(f'{S.WORK}/codes_{src}.csv', index=False)


if __name__ == '__main__':
    g500()
    g100()
