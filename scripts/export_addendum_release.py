#!/usr/bin/env python
"""Release files of the ArcSurf addendum (version 1.0), split like the geology (export_release.py): the rows of the
polygons published under CC BY 4.0 go into the addendum dataset, the rows of polygons under CC BY-SA 4.0 into a
separate part (none since the GEUS permission of 2026-10-22 for the Greenland polygons: that folder is then not
written); rows of polygons that are not released are left out. The polygon sets are taken from the release geometry
with the same rule as export_release.target().

  <out>/addendum_CC-BY-4.0/
      polygon_context.parquet, polygon_strat.parquet, piece_context.parquet   (rows of the CC BY polygons)
      units.csv                     the native units that occur in them
      stratigraphies.csv, cryogrid_templates.csv, parameter_classes.csv     (complete; no source content)
      README.md                     addendum/README_addendum.md
  <out>/addendum_Greenland_CC-BY-SA-4.0/   the same tables for CC BY-SA polygons, if any (+ stratigraphies, templates)
  <out>/addendum_release_report.txt
usage: export_addendum_release.py DISSOLVE_DIR ADDENDUM_DIR OUT_DIR"""
import glob
import os
import shutil
import sys

import numpy as np
import pandas as pd

DD, AD, OUT = sys.argv[1:4]
README = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'addendum', 'README_addendum.md')


def targets():
    F = pd.concat([pd.read_parquet(f, columns=['asid', 'hclass', 'redistribution'])
                   for f in sorted(glob.glob(f'{DD}/final/*.parquet'))], ignore_index=True)
    red = F['redistribution'].astype('string').fillna('').to_numpy(dtype=object)
    hc = F['hclass'].astype('string').fillna('').to_numpy(dtype=object)
    t = np.full(len(F), 'gap', dtype=object)
    t[red == 'open'] = 'by'
    t[red == 'open_sa'] = 'sa'
    t[(red == '') & ((hc == 'U') | (hc == 'I'))] = 'by'     # as export_release.target: no-source land and its ice
    return pd.Series(t, index=F['asid'].to_numpy())


def main():
    T = targets()
    lines = [f'release geometry: {len(T):,} polygons; ' +
             ', '.join(f'{k} {v:,}' for k, v in T.value_counts().items())]
    pc = pd.read_parquet(f'{AD}/polygon_context.parquet')
    ps = pd.read_parquet(f'{AD}/polygon_strat.parquet')
    pp = pd.read_parquet(f'{AD}/piece_context.parquet')
    units = pd.read_csv(f'{AD}/units.csv', keep_default_na=False, low_memory=False)
    for name, df in (('polygon_context', pc), ('polygon_strat', ps), ('piece_context', pp)):
        missing = ~df['asid'].isin(T.index)
        if missing.any():
            sys.exit(f'{name}: {int(missing.sum())} rows whose asid is not in the release geometry')
    for key, sub in (('by', 'addendum_CC-BY-4.0'), ('sa', 'addendum_Greenland_CC-BY-SA-4.0')):
        keep = set(T.index[T.to_numpy() == key])
        if key == 'sa' and not keep:        # GEUS granted CC BY (2026-10-22): no CC BY-SA part, no empty folder
            lines.append(f'{sub}: no rows, not written')
            continue
        d = f'{OUT}/{sub}'
        os.makedirs(d, exist_ok=True)
        a = pc[pc['asid'].isin(keep)]
        b = ps[ps['asid'].isin(keep)]
        c = pp[pp['asid'].isin(keep)]
        u = units[units['unit_code'].isin(set(a['unit_code']))]
        if key == 'by' and a['redistribution'].astype('string').fillna('').isin(['internal_only', 'unknown',
                                                                                  'open_sa']).any():
            sys.exit('restricted rows in the CC BY addendum')
        a.to_parquet(f'{d}/polygon_context.parquet', index=False)
        b.to_parquet(f'{d}/polygon_strat.parquet', index=False)
        c.to_parquet(f'{d}/piece_context.parquet', index=False)
        u.to_csv(f'{d}/units.csv', index=False)
        for f in ('stratigraphies.csv', 'cryogrid_templates.csv'):
            shutil.copy(f'{AD}/{f}', f'{d}/{f}')
        if key == 'by':
            shutil.copy(f'{AD}/parameter_classes.csv', f'{d}/parameter_classes.csv')
        if os.path.exists(README):
            shutil.copy(README, f'{d}/README.md')
        lines.append(f'{sub}: {len(a):,} polygons ({a["area_km2"].sum():,.0f} km2), {len(b):,} stratigraphy rows, '
                     f'{len(c):,} pieces, {len(u):,} unit rows ({u["unit_code"].nunique():,} units)')
    open(f'{OUT}/addendum_release_report.txt', 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)


if __name__ == '__main__':
    main()
