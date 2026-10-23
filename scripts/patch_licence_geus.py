#!/usr/bin/env python
"""Licence correction of 2026-10-08 (H. Lantuit; GEUS email in correspondence/2026-10-08_GEUS_reply_received.txt): the
GEUS maps are CC BY-SA 4.0, so their derived layer is open with share-alike (redistribution 'open_sa'), not
internal_only. Written into every copy that carries the field, without a re-merge (geometry untouched; the licence is
uniform within each source, so the dissolve groups are unchanged):
  work/std and work/xw GeoPackages of gl_geus_g500_v3 and gl_geus_g100_karrat (patch_licence.patch_gpkg),
  the tiles of work/tiles (rewritten, then re-linked into the snapshot work/final_<tag>),
  the dissolved polygons work/dissolve_<tag>/final/*.parquet, and the addendum's polygon_context.parquet.
usage: patch_licence_geus.py <tag, e.g. m44> <addendum dir name, e.g. addendum_v02>"""
import glob
import os
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

import patch_licence as PL

LIC = 'CC BY-SA 4.0 (GEUS; confirmed by GEUS, email of 2026-10-08)'
SRC = ('gl_geus_g500_v3', 'gl_geus_g100_karrat')
PL.RULES = [(s, None, LIC, 'open_sa') for s in SRC]
W = PL.W


def rewrite(f, link_dirs=()):
    """patch one parquet in place (new inode, GeoParquet metadata kept); re-link it into the snapshot dirs"""
    ids = pq.read_table(f, columns=['src_id']).column('src_id').to_pylist()
    if not any(s in SRC for s in ids):
        return 0
    t = pq.read_table(f)
    meta = t.schema.metadata
    d = t.to_pandas()
    n = PL.patch_frame(d)
    if n:
        nt = pa.Table.from_pandas(d, preserve_index=False).replace_schema_metadata(meta)
        pq.write_table(nt, f + '.tmp')
        os.replace(f + '.tmp', f)
        for ld in link_dirs:
            fin = f'{ld}/{os.path.basename(f)}'
            if os.path.exists(fin):
                os.remove(fin)
                os.link(f, fin)
    return n


def main():
    tag, add = sys.argv[1], sys.argv[2]
    for s in SRC:
        for f in (f'{W}/std/{s}.gpkg', f'{W}/xw/{s}.gpkg'):
            if os.path.exists(f):
                PL.patch_gpkg(f)
    n = t = 0
    for f in sorted(glob.glob(f'{W}/tiles/*.parquet')):
        k = rewrite(f, (f'{W}/final_{tag}',))
        n += k
        t += k > 0
    print(f'tiles patched {t} ({n:,} pieces), re-linked into final_{tag}', flush=True)
    n = t = 0
    for f in sorted(glob.glob(f'{W}/dissolve_{tag}/final/*.parquet')):
        k = rewrite(f)
        n += k
        t += k > 0
    print(f'dissolved files patched {t} ({n:,} polygons)', flush=True)
    pc = f'{W}/{add}/polygon_context.parquet'
    if os.path.exists(pc):
        d = pd.read_parquet(pc)
        m = d['src_id'].astype(str).isin(SRC)
        d['redistribution'] = d['redistribution'].astype(str)
        d.loc[m, 'redistribution'] = 'open_sa'
        d['redistribution'] = d['redistribution'].astype('category')
        d.to_parquet(pc + '.tmp', index=False)
        os.replace(pc + '.tmp', pc)
        print(f'addendum polygons patched {int(m.sum()):,}', flush=True)


if __name__ == '__main__':
    main()
