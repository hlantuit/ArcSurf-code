#!/usr/bin/env python
"""Licence status for the CC BY 4.0 release of 2026-10 (H. Lantuit, after the review by the AWI legal office and the
editor of ESSD): the Russian sources and the Labrador 1:50k layer (GSNL permission of 2026-10-13) are released, and so
are the two research maps of PAGE21, which are PANGAEA data sets, and the GEUS-derived Greenland layer (GEUS granted
CC BY 4.0 for it on 2026-10-22, correspondence/2026-10-22_GEUS_CC-BY_permission_received.txt; the licence text carries
the statement GEUS asked for). --no-greenland leaves Greenland CC BY-SA. Written, without a re-merge, into every copy
that carries the fields (the licence is uniform within each source, so the dissolve groups do not change):
  work/std and work/xw GeoPackages of the sources, the tiles of work/final_<tag> (rewritten in place: final_<tag> is
  the merge output itself), and, when they exist, work/dissolve_<tag>/final/*.parquet and <addendum>/polygon_context.
usage: patch_licence_open.py <tag> [--addendum DIR] [--no-greenland]"""
import argparse
import glob
import os

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import patch_licence as PL

RU = 'State Geological Map (VSEGEI); derived data released under CC BY 4.0'
NL = ('Geological Survey of Newfoundland and Labrador; reproduced with permission (2026-10-13); '
      'conditions in the dataset metadata')
PAGE21 = 'PANGAEA data set (PAGE21)'
GEUS = ('Geological Survey of Denmark and Greenland (GEUS); the GEUS-derived component of ArcSurf is published under '
        'CC BY 4.0 with separate permission from GEUS (2026-10-22); the original GEUS datasets remain available from '
        'GEUS Dataverse under CC BY-SA 4.0')
RULES = [('ru_vsegei_pdf', None, RU, 'open'), ('ru_vsegei_preview', None, RU, 'open'),
         ('ru_vsegei200', None, RU, 'open'), ('ru_vsegei_q2500', None, RU, 'open'),
         ('ca_nl_labrador', 'layer11', NL, 'open'),
         ('ru_lena_peter2014', None, PAGE21, 'open'), ('ru_kytalyk_base', None, PAGE21, 'open')]
W = PL.W


def rewrite(f, src):
    ids = pq.read_table(f, columns=['src_id']).column('src_id').to_pylist()
    if not any(s in src for s in ids):
        return 0
    t = pq.read_table(f)
    meta = t.schema.metadata
    d = t.to_pandas()
    for c in ('licence', 'redistribution'):
        if str(d[c].dtype) == 'category':
            d[c] = d[c].astype(str)
    n = PL.patch_frame(d)
    if n:
        nt = pa.Table.from_pandas(d, preserve_index=False).replace_schema_metadata(meta)
        pq.write_table(nt, f + '.tmp')
        os.replace(f + '.tmp', f)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('--addendum')
    ap.add_argument('--no-greenland', action='store_true')
    a = ap.parse_args()
    PL.RULES = RULES + ([] if a.no_greenland else
                        [('gl_geus_g500_v3', None, GEUS, 'open'), ('gl_geus_g100_karrat', None, GEUS, 'open')])
    src = {r[0] for r in PL.RULES}
    for s in sorted(src):
        for f in (f'{W}/std/{s}.gpkg', f'{W}/xw/{s}.gpkg'):
            if os.path.exists(f):
                PL.patch_gpkg(f)
    for label, pattern in (('tiles', f'{W}/final_{a.tag}/*.parquet'),
                           ('dissolved files', f'{W}/dissolve_{a.tag}/final/*.parquet')):
        n = t = 0
        for f in sorted(glob.glob(pattern)):
            k = rewrite(f, src)
            n += k
            t += k > 0
        print(f'{label} patched: {t} ({n:,} rows)', flush=True)
    if a.addendum and os.path.exists(f'{W}/{a.addendum}/polygon_context.parquet'):
        pc = f'{W}/{a.addendum}/polygon_context.parquet'
        d = pd.read_parquet(pc)
        d['redistribution'] = d['redistribution'].astype(str)
        for s, sheet, lic, red in PL.RULES:
            m = d['src_id'].astype(str) == s
            if sheet and 'src_sheet' in d:
                m &= d['src_sheet'].astype(str) == sheet
            d.loc[m, 'redistribution'] = red
        d.to_parquet(pc + '.tmp', index=False)
        os.replace(pc + '.tmp', pc)
        print('addendum polygon_context patched', flush=True)


if __name__ == '__main__':
    main()
