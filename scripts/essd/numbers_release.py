#!/usr/bin/env python
"""The numbers of the data paper that come from the dissolve, the addendum v0.2 and the licence patch (manuscript
v0.5: Sects. 4.8, 5.1, 7, 9 and the abstract). Writes a JSON of {token: text} that fill_tokens.py puts into the
manuscript parts, where the tokens stand as <span class="todo">@TOKEN@</span>.

  from <dissolve>/final/*.parquet   N_ASID, MED_ASID_KM2, PCT_SMALL_ASID, PCT_GAPFILL_MERGED, the licence shares
                                    (OPEN_*, INT_*, UNK_*, UNMAPPED_PCT: 'not mapped' = class U or no source, as in
                                    Fig. 11)
  from <dissolve>/report.txt        AREA_DIFF_M2
  from the dissolve check log       N_RESID ('residual same-KEY contacts longer than 1 m: N')
  from <addendum>/                  N_UNITS, N_PCLASS, N_STRAT, TIER1A, TIER1B, PROXY_PCT, A_<TEMPLATE>
usage: numbers_release.py DISSOLVE_DIR ADDENDUM_DIR CHECK_LOG OUT.json"""
import glob
import json
import re
import sys

import numpy as np
import pandas as pd

DD, AD, LOG, OUT = sys.argv[1:5]
COLS = ['asid', 'hclass', 'src_id', 'redistribution', 'gapfill_km2', 'area_km2']


def pct(a, tot, nd=1):
    return f'{100.0 * a / tot:.{nd}f}'


def mkm2(a):
    return f'{a / 1e6:.2f}'


def main():
    T = {}
    F = pd.concat([pd.read_parquet(f, columns=COLS) for f in sorted(glob.glob(f'{DD}/final/*.parquet'))],
                  ignore_index=True)
    tot = float(F['area_km2'].sum())
    T['N_ASID'] = f'{len(F):,}'
    a = np.sort(F['area_km2'].to_numpy())
    cum = np.cumsum(a)
    T['MED_ASID_KM2'] = f'{a[np.searchsorted(cum, cum[-1] / 2.0)]:.1f}'
    T['PCT_SMALL_ASID'] = pct((a < 0.01).sum(), len(a), 0)
    g = F['gapfill_km2'].fillna(0.0).to_numpy()
    only = g >= 0.999 * F['area_km2'].to_numpy()               # polygons that are nothing but filled sliver
    T['PCT_GAPFILL_MERGED'] = pct(g.sum() - g[only].sum(), g.sum(), 0) if g.sum() > 0 else '–'

    hc = F['hclass'].astype('string').fillna('U')
    src = F['src_id'].astype('string').fillna('none')
    red = F['redistribution'].astype('string').fillna('')
    notmap = (hc == 'U') | (src == 'none')
    area = F['area_km2']
    parts = {'OPEN_BY': (~notmap) & (red == 'open'), 'OPEN_SA': (~notmap) & (red == 'open_sa'),
             'INT': (~notmap) & (red == 'internal_only'), 'UNK': (~notmap) & ~red.isin(['open', 'open_sa',
                                                                                      'internal_only'])}
    for k, m in parts.items():
        v = float(area[m].sum())
        T[f'{k}_MKM2'] = mkm2(v)
        T[f'{k}_PCT'] = pct(v, tot)
    T['OPEN_PCT'] = f'{100.0 * float(area[parts["OPEN_BY"] | parts["OPEN_SA"]].sum()) / tot:.0f}'
    T['UNMAPPED_PCT'] = pct(float(area[notmap].sum()), tot)

    # area: pieces -> pass-1 patches (report_p1.tsv, m2; the last 'ok' line of a tile that was run again) and
    # pass-1 patches -> final polygons (report.txt, km2)
    last = {}                                                   # ERROR lines have fewer fields: parse by hand
    for line in open(f'{DD}/report_p1.tsv', errors='replace'):
        f = line.rstrip('\n').split('\t')
        if len(f) >= 12 and f[1] == 'ok':
            last[f[0]] = (float(f[10]), float(f[11]))
    p1 = list(last.values())
    d1 = sum(b - a for a, b in p1)
    rep = open(f'{DD}/report.txt').read()
    m = re.search(r'difference ([+-][\d.]+) km2', rep)
    d2 = float(m.group(1)) * 1e6 if m else float('nan')
    T['AREA_DIFF_M2'] = f'{abs(d1 + d2):,.0f}'
    m = re.search(r'invalid final geometries (\d+)', rep)
    T['_invalid_final'] = m.group(1) if m else '?'          # the text of Sect. 4.8 / Table 6 says none
    T['_p1_tiles_ok'] = f'{len(p1):,}'
    T['_area_diff_p1_m2'] = f'{d1:+,.1f}'
    T['_area_diff_p2_m2'] = f'{d2:+,.1f}'
    m = re.findall(r'residual same-KEY contacts longer than 1 m: ([\d,]+)', open(LOG, errors='replace').read())
    T['N_RESID'] = m[-1] if m else '?'

    u = pd.read_csv(f'{AD}/units.csv', usecols=['unit_code'], keep_default_na=False)
    T['N_UNITS'] = f'{u["unit_code"].nunique():,}'
    pc = pd.read_csv(f'{AD}/parameter_classes.csv', keep_default_na=False)
    T['N_PCLASS'] = f'{len(pc):,}'
    ps = pd.read_parquet(f'{AD}/polygon_strat.parquet', columns=['asid', 'template_id', 'strat_id', 'thk_tier'])
    ps = ps.merge(F[['asid', 'hclass', 'area_km2']], on='asid', how='left')
    if ps['area_km2'].isna().any():
        sys.exit(f'{int(ps["area_km2"].isna().sum())} asids of polygon_strat are not in the dissolve')
    T['N_STRAT'] = f'{ps["strat_id"].nunique():,}'
    tier = ps.groupby(ps['thk_tier'].astype(str))['area_km2'].sum()
    T['TIER1A'] = pct(float(tier.get('1a', 0.0)), tot, 2)
    T['TIER1B'] = pct(float(tier.get('1b', 0.0)), tot, 2)
    h = ps['hclass'].astype('string').fillna('U')
    tid = ps['template_id'].astype(str)
    proxy = h.isin(['GL', 'M', 'GM', 'E', 'Q']) | ((h == 'L') & (tid == 'SILT_PROXY'))
    T['PROXY_PCT'] = pct(float(ps.loc[proxy, 'area_km2'].sum()), tot)
    by_t = ps.groupby(tid)['area_km2'].sum()
    for k, v in by_t.items():
        T[f'A_{k}'] = pct(float(v), tot)
    for k in ('ICE', 'BEDROCK', 'COLL_BOULDERY', 'TILL_THICK', 'TILL_VENEER', 'COLL_FINES', 'COLL_FINES_THIN',
              'REG_BOULDERY', 'REG_FINES', 'PEAT', 'PEAT_THIN', 'FLUV_COARSE', 'SAND_LOWLAND', 'FLUV_FINES',
              'GLACIOFLUVIAL', 'SILT_PROXY', 'MARINE_FINES', 'LAC_UNGLACIATED', 'YEDOMA', 'VOLCANIC', 'NONE'):
        T.setdefault(f'A_{k}', '0.0')
    T['_total_km2'] = f'{tot:,.1f}'
    json.dump(T, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    for k, v in T.items():
        print(f'{k:20s} {v}')


if __name__ == '__main__':
    main()
