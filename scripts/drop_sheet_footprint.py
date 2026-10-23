#!/usr/bin/env python
"""Remove one sheet from the merge without re-ingesting its source: delete its rows from the 'footprint' layer of the
source's std and xw GeoPackages, so that the sheet never claims land (its units stay in the file, unused).
First use: merge 45 (2026-10-08), Q-50-51_g2 of ru_vsegei_pdf, the same printed map (Kolpakov 1986) as the USGS
Siberian database sheet Q50,51, whose vector digitisation is better registered (225 m against 1.4 km).
GeoPackage R-tree triggers call GDAL's ST_* SQL functions, which plain sqlite3 lacks: they are dropped for the delete
and re-created verbatim; the R-tree rows of the deleted features are removed with them.
usage: drop_sheet_footprint.py SRC_ID SHEET"""
import sqlite3
import sys

import surflib as S

src, sheet = sys.argv[1:3]
for path in (f'{S.WORK}/std/{src}.gpkg', f'{S.WORK}/xw/{src}.gpkg'):
    con = sqlite3.connect(path)
    col = con.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name = 'footprint'").fetchone()[0]
    fids = [r[0] for r in con.execute('SELECT fid FROM footprint WHERE src_sheet = ?', (sheet,))]
    if not fids:
        print(f'{path}: no footprint row for {sheet}')
        con.close()
        continue
    trig = con.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'footprint'").fetchall()
    for name, _ in trig:
        con.execute(f'DROP TRIGGER "{name}"')
    q = ','.join('?' * len(fids))
    n = con.execute(f'DELETE FROM footprint WHERE fid IN ({q})', fids).rowcount
    rt = f'rtree_footprint_{col}'
    if con.execute("SELECT count(*) FROM sqlite_master WHERE name = ?", (rt,)).fetchone()[0]:
        con.execute(f'DELETE FROM "{rt}" WHERE id IN ({q})', fids)
    for _, sql in trig:
        con.execute(sql)
    con.commit()
    left = con.execute('SELECT count(*) FROM footprint WHERE src_sheet = ?', (sheet,)).fetchone()[0]
    print(f'{path}: deleted {n} footprint rows of {sheet} (left {left}); triggers restored {len(trig)}', flush=True)
    con.close()
