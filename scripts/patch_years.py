#!/usr/bin/env python
"""Attribute patch of publication years that the source records contradict (checked against DOI registries and agency
catalogues, 2026-10-08): work/std and work/xw GeoPackages (units and footprint layers, SQL UPDATE, geometry untouched)
and the merged tiles of work/tiles. Run after a merge and before its snapshot. Years only: the precedence of the
merge is not recomputed (none of these sources competes with a source of the same scale and tier whose year lies
between the old and the new value).
usage: patch_years.py"""
import glob
import os
import sqlite3

import geopandas as gpd
import pandas as pd

import surflib as S

YEARS = {'ca_on_eds014': 2000,          # EDS 14 Revised, 2000 (original 1997)
         'us_usgs_sim3036': 2011,       # USGS SIM 3036, 2011
         'fi_gtk_maapera200k': 2010,    # GTK superficial deposits 1:200 000, 2010
         'sj_npi_s100_overlay': 2014,   # Norwegian Polar Institute, DOI year 2014
         'sj_npi_j250_janmayen': 2023,  # Norwegian Polar Institute, DOI year 2023
         'is_natt_n25_coastal': 2019,   # Icelandic Institute of Natural History, 1st edition 2019
         'ru_vsegei200': 2013,          # Gosgeolkarta-200 digital model, electronic edition 2013
         'ca_nl_labrador': 2024}        # GSNL 1:50 000 surficial layer, last update 2024


def patch_gpkg(path, src, year):
    con = sqlite3.connect(path)
    n_all = 0
    for layer in ('units', 'footprint'):
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{layer}")')]
        if 'pub_year' not in cols or 'src_id' not in cols:
            continue
        trig = con.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = ?",
                           (layer,)).fetchall()
        for name, _ in trig:
            con.execute(f'DROP TRIGGER "{name}"')
        n_all += con.execute(f'UPDATE "{layer}" SET pub_year = ? WHERE src_id = ?', (year, src)).rowcount
        for _, sql in trig:
            con.execute(sql)
    con.commit()
    con.close()
    return n_all


def main():
    for src, year in YEARS.items():
        for path in (f'{S.WORK}/std/{src}.gpkg', f'{S.WORK}/xw/{src}.gpkg'):
            if os.path.exists(path):
                print(f'{path}: pub_year -> {year} on {patch_gpkg(path, src, year)} rows', flush=True)
    n_tiles = n_rows = 0
    for f in sorted(glob.glob(f'{S.WORK}/tiles/*.parquet')):
        ids = pd.read_parquet(f, columns=['src_id'])['src_id'].astype('string')
        if not ids.isin(list(YEARS)).any():              # most tiles: no patched source, no full read
            continue
        g = gpd.read_parquet(f)
        if 'src_id' not in g or g.empty:
            continue
        m = g['src_id'].astype('string').isin(list(YEARS))
        if not m.any():
            continue
        new = g['src_id'].astype('string').map(YEARS)
        g.loc[m, 'pub_year'] = new[m].astype('Int64').to_numpy()
        g['pub_year'] = pd.to_numeric(g['pub_year'], errors='coerce').astype('Int64')
        tmp = f + '.tmp'
        g.to_parquet(tmp)
        os.replace(tmp, f)                  # a new file: snapshots made earlier keep their own links
        n_tiles += 1
        n_rows += int(m.sum())
    print(f'tiles patched {n_tiles} ({n_rows:,} pieces)', flush=True)


if __name__ == '__main__':
    main()
