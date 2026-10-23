#!/usr/bin/env python
"""
GSC Open File 7038 (2012): Predictive surficial geological mapping of Hall Peninsula and
Foxe Basin Plateau, Baffin Island, from Landsat 7 + CDED DEM, 1:500 000, NAD83 LCC
(unz/canada/of7038/data/gdb/of7038.gdb, layer Surficial_Units_Classification, field CODE;
footprint = layer Map_Area) -> work/std/ca_gsc_of7038.gpkg + xwalk/ca_gsc_of7038.csv.
Legend (of7038_Classification_Map.pdf): Mn marine littoral sand/gravel, Mb marine blanket
silt/clay, GF glaciofluvial, Tv till veneer < 1-2 m, Tb till blanket > 1-2 m, T carbonate
till, O organic, R crystalline bedrock, U undifferentiated (wet ground from Landsat band 4 or
slopes >= 8 deg) -> DROPPED so a coarser source fills it (42 % of the map area).
Glaciers are a separate layer (not units): left to the ice override. Conf tier Predictive.
"""
import os
import sys

import pandas as pd
import pyogrio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

SRC = 'ca_gsc_of7038'
G = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/canada/of7038/data/gdb/of7038.gdb'
XW = [('Mn', 'M', '', 'gravel', 'unknown', 'marine littoral: sand and gravel, raised beaches'),
      ('Mb', 'M', '', 'fines', 'blanket', 'marine blanket: silt, clay, mud'),
      ('GF', 'GF', '', 'gravel', 'unknown', 'glaciofluvial sand and gravel (may include fluvial)'),
      ('Tv', 'T', 'R', 'diamicton', 'veneer', 'till veneer < 1-2 m with outcrop'),
      ('Tb', 'T', '', 'diamicton', 'blanket', 'till blanket > 1-2 m'),
      ('T', 'T', '', 'diamicton', 'unknown', 'carbonate till, undifferentiated'),
      ('O', 'O', '', 'organic', 'unknown', 'organic deposits: fen, bog'),
      ('R', 'R', '', 'unknown', 'unknown', 'crystalline bedrock, rubble; patches of till veneer'),
      ('U', 'DROP', '', 'unknown', 'unknown', 'undifferentiated (wet ground / slopes >= 8 deg): dropped so a coarser source fills it')]


def main():
    g = pyogrio.read_dataframe(G, layer='Surficial_Units_Classification')
    g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
    g['CODE'] = g['CODE'].astype(str).str.strip()
    u, _ = S.standardise(g, src_id=SRC, code='CODE', desc='CODE', xkey='CODE', scale_den=500_000, pub_year=2012,
                         conf_tier='Predictive', licence='Open Government Licence - Canada', redistribution='open')
    fp = pyogrio.read_dataframe(G, layer='Map_Area').to_crs(S.CRS)[['geometry']]
    fp = S.in_amap(fp)
    fp['src_id'] = SRC
    fp['overlay'] = 0
    p, m = S.write_std(u, fp, SRC, dict(title='GSC OF 7038 Predictive surficial geology, Hall Peninsula and Foxe Basin Plateau (Landsat + DEM)',
                                        scale_note='1:500 000'))
    pd.DataFrame([[k, h, h2, t, c, 'unknown', f'OF7038 {k}: {n}'] for k, h, h2, t, c, n in XW],
                 columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(f'{S.XWALK}/{SRC}.csv', index=False)
    print(SRC, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')})


if __name__ == '__main__':
    main()
