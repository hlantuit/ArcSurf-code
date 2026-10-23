#!/usr/bin/env python
"""Licence corrections of 2026-10-07 (H. Lantuit), written into every layer that carries them, without a re-merge:
  ca_mb_sgcms     -> open: OpenMB Information and Data Use Licence v1.0 (gov.mb.ca site-wide copyright page)
  ca_nl_labrador  layer11 (GSNL 1:50k, NL GeoAtlas: no digital reproduction to third parties) -> internal_only
                  layer12 (= GSC Map 1814A, OGL-Canada at source; taken from the GeoAtlas) stays unknown until the
                  layer is replaced by the GSC release (as_1814.zip)
Patched: work/std and work/xw source GeoPackages (SQL UPDATE, geometry untouched), the merged tiles of work/tiles
(rewritten to a new file and renamed in place, then re-linked into work/final_m43), and the addendum's
polygon_context.parquet. usage: patch_licence.py"""
import glob
import os
import sqlite3
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

W = '/albedo/work/user/hlantuit/arctic_surficial/work'
MB_LIC = ('OpenMB Information and Data Use Licence v1.0 (Government of Manitoba); GSC-derived parts '
          'Open Government Licence - Canada')
LAB11_LIC = 'NL GeoAtlas, GSNL 1:50k layer: no digital reproduction to third parties (permission required)'
RULES = [('ca_mb_sgcms', None, MB_LIC, 'open'), ('ca_nl_labrador', 'layer11', LAB11_LIC, 'internal_only')]


def patch_gpkg(path):
    """attribute-only UPDATE. The GeoPackage R-tree triggers call GDAL's ST_* SQL functions, which plain sqlite3
    lacks, so they are dropped for the update and re-created verbatim afterwards; geometries are not touched, so
    the spatial index stays valid."""
    con = sqlite3.connect(path)
    trig = con.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'units'").fetchall()
    for name, _ in trig:
        con.execute(f'DROP TRIGGER "{name}"')
    for src, sheet, lic, red in RULES:
        q = 'UPDATE units SET licence = ?, redistribution = ? WHERE src_id = ?'
        args = [lic, red, src]
        if sheet:
            q += ' AND src_sheet = ?'
            args.append(sheet)
        n = con.execute(q, args).rowcount
        if n:
            print(f'{path}: {src} {sheet or ""} -> {red}: {n} rows', flush=True)
    for _, sql in trig:
        con.execute(sql)
    con.commit()
    left = con.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger' AND tbl_name = 'units'").fetchone()[0]
    print(f'{path}: triggers restored {left}/{len(trig)}', flush=True)
    con.close()


def patch_frame(d):
    n = 0
    for src, sheet, lic, red in RULES:
        m = d['src_id'] == src
        if sheet:
            m &= d['src_sheet'] == sheet
        if m.any():
            d.loc[m, 'licence'] = lic
            d.loc[m, 'redistribution'] = red
            n += int(m.sum())
    return n


def main():
    for f in (f'{W}/std/ca_mb_sgcms.gpkg', f'{W}/std/ca_nl_labrador.gpkg', f'{W}/xw/ca_mb_sgcms.gpkg',
              f'{W}/xw/ca_nl_labrador.gpkg'):
        if os.path.exists(f):
            patch_gpkg(f)
    tiles = 0
    for f in sorted(glob.glob(f'{W}/tiles/*.parquet')):
        ids = pq.read_table(f, columns=['src_id']).column('src_id').to_pylist()
        if not any(s in ('ca_mb_sgcms', 'ca_nl_labrador') for s in ids):
            continue
        t = pq.read_table(f)
        meta = t.schema.metadata                         # keep the GeoParquet metadata
        d = t.to_pandas()
        n = patch_frame(d)
        if n:
            import pyarrow as pa
            nt = pa.Table.from_pandas(d, preserve_index=False).replace_schema_metadata(meta)
            tmp = f + '.tmp'
            pq.write_table(nt, tmp)
            os.replace(tmp, f)                           # new inode in work/tiles
            fin = f'{W}/final_m43/{os.path.basename(f)}'
            if os.path.exists(fin):
                os.remove(fin)
                os.link(f, fin)                          # final_m43 follows the corrected tile
            tiles += 1
    print('tiles patched', tiles, flush=True)
    pc = f'{W}/addendum_v01/polygon_context.parquet'
    if os.path.exists(pc):
        d = pd.read_parquet(pc)
        d['redistribution'] = d['redistribution'].astype(str)
        d['src_sheet_s'] = d['src_sheet'].astype(str)
        n = 0
        for src, sheet, lic, red in RULES:
            m = d['src_id'].astype(str) == src
            if sheet:
                m &= d['src_sheet_s'] == sheet
            d.loc[m, 'redistribution'] = red
            n += int(m.sum())
        d = d.drop(columns='src_sheet_s')
        d['redistribution'] = d['redistribution'].astype('category')
        d.to_parquet(pc + '.tmp', index=False)
        os.replace(pc + '.tmp', pc)
        print('addendum rows patched', n, flush=True)


if __name__ == '__main__':
    main()
