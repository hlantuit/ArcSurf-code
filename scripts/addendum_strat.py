#!/usr/bin/env python
"""CryoGrid stratigraphies for every polygon of the dissolved release (addendum v0.2, step 2; parameters and rules in
addendum_params.py). Runs after addendum_v02.py, on its polygon_context.parquet (for the LGM ice share) and on the
dissolved polygons (for the geology and the legend text).

  cryogrid_templates.csv  the templates, one row per layer: template_id, name, layer, top_m, class, waterIce, mineral,
                          organic, soil_type, field_capacity, satHydraulicConductivity, Xice, Xice_published, base
                          (1 = the boundary a unit thickness controls), sources, confidence, note
  stratigraphies.csv      every distinct realized stratigraphy (template + thickness), one row per layer, keyed by
                          strat_id ('<template>@<depth m>' or '<template>' for the published profile)
  polygon_strat.parquet   one row per asid: template_id, strat_id, thk_min_m, thk_max_m, thk_depth_m, thk_tier
                          (1a unit legend text or GSC Map 1814A legend / 1b cover term of the legend system /
                          2 template default), thk_basis (the quote or the rule), confidence
  parameter_classes.csv   the v0.2 table with template_id and the area by thickness tier filled in
  strat_summary.txt
usage: addendum_strat.py DISSOLVE_DIR ADDENDUM_DIR"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import addendum_params as P  # noqa: E402

DD, AD = sys.argv[1:3]
KEYC = ['src_id', 'src_code', 'src_desc', 'hclass', 'hclass2', 'texture', 'cover']


def templates_table():
    rows = []
    for tid, t in P.TEMPLATES.items():
        k = P.THK_LAYER.get(tid, t['base'])
        for i, x in enumerate(t['layers']):
            rows.append(dict(template_id=tid, name=t['name'], layer=i + 1, top_m=x['top_m'], **{
                c: x[c] for c in ('waterIce', 'mineral', 'organic', 'soil_type', 'field_capacity',
                                  'satHydraulicConductivity', 'Xice', 'Xice_published')},
                class_=x['cls'], thickness_controls=int(k is not None and i == k), sources=t['sources'],
                confidence=t['confidence'], note=t.get('note', '')))
    return pd.DataFrame(rows).rename(columns={'class_': 'class'})


def main():
    fin = pd.concat([pd.read_parquet(f, columns=['asid', 'area_km2'] + KEYC)
                     for f in sorted(glob.glob(f'{DD}/final/*.parquet'))], ignore_index=True)
    ctx = pd.read_parquet(f'{AD}/polygon_context.parquet', columns=['asid', 'lgm_ice_share'])
    fin = fin.merge(ctx, on='asid', how='left')
    for c in KEYC:
        fin[c] = fin[c].astype('string').fillna('').astype(object)
    fin['lgm'] = (fin['lgm_ice_share'].fillna(0.0) >= 0.5)
    print(f'{len(fin):,} polygons', flush=True)
    # one evaluation per distinct (geology, legend text, LGM flag)
    u = fin[KEYC + ['lgm']].drop_duplicates().reset_index(drop=True)
    rec = []
    for r in u.itertuples(index=False):
        tid = P.assign(r.hclass, r.hclass2, r.texture, r.cover, 1.0 if r.lgm else 0.0)
        lo, hi, depth, tier, basis = P.thickness(tid, r.src_id, r.src_code, r.src_desc, r.cover, r.hclass2, r.hclass)
        sid = tid if depth is None else f'{tid}@{depth:g}'
        rec.append((tid, sid, lo, hi, depth, tier, basis, P.TEMPLATES[tid]['confidence']))
    u = pd.concat([u, pd.DataFrame(rec, index=u.index, columns=[
        'template_id', 'strat_id', 'thk_min_m', 'thk_max_m', 'thk_depth_m', 'thk_tier', 'thk_basis', 'confidence'])],
        axis=1)
    print(f'{len(u):,} distinct geology / legend-text combinations', flush=True)
    ps = fin.merge(u, on=KEYC + ['lgm'], how='left')
    out = ps[['asid', 'template_id', 'strat_id', 'thk_min_m', 'thk_max_m', 'thk_depth_m', 'thk_tier', 'thk_basis',
              'confidence']].copy()
    for c in ('template_id', 'strat_id', 'thk_tier', 'thk_basis', 'confidence'):
        out[c] = out[c].astype('category')
    out.sort_values('asid').to_parquet(f'{AD}/polygon_strat.parquet', index=False)

    templates_table().to_csv(f'{AD}/cryogrid_templates.csv', index=False)
    srows = []
    for sid in sorted(u['strat_id'].unique()):
        tid, _, d = sid.partition('@')
        for i, x in enumerate(P.realize(tid, float(d) if d else None)):
            srows.append(dict(strat_id=sid, template_id=tid, layer=i + 1, top_m=x['top_m'], **{
                c: x[c] for c in ('waterIce', 'mineral', 'organic', 'soil_type', 'field_capacity',
                                  'satHydraulicConductivity', 'Xice')}, cls=x['cls']))
    pd.DataFrame(srows).rename(columns={'cls': 'class'}).to_csv(f'{AD}/stratigraphies.csv', index=False)

    # parameter classes: the template and the area per thickness tier
    pc = pd.read_csv(f'{AD}/parameter_classes.csv', keep_default_na=False)
    keys = ['hclass', 'hclass2', 'texture', 'cover']
    ps['area'] = ps['area_km2']
    tt = ps.groupby(keys + ['template_id'], observed=True)['area'].sum().reset_index() \
        .sort_values('area', ascending=False).drop_duplicates(keys)
    tier = ps.pivot_table(index=keys, columns='thk_tier', values='area', aggfunc='sum', fill_value=0.0,
                          observed=True).reset_index()
    tier.columns = [c if c in keys else f'area_tier{c}_km2' for c in tier.columns]
    for c in keys:
        pc[c] = pc[c].astype(str)
        tt[c] = tt[c].astype(str)
        tier[c] = tier[c].astype(str)
    drop = [c for c in pc.columns if c in ('top_m', 'waterIce', 'mineral', 'organic', 'field_capacity', 'soil_type',
                                           'satHydraulicConductivity', 'Xice', 'source', 'confidence')]
    pc = pc.drop(columns=drop).merge(tt[keys + ['template_id']], on=keys, how='left').merge(tier, on=keys, how='left')
    pc['template_confidence'] = pc['template_id'].map({k: v['confidence'] for k, v in P.TEMPLATES.items()})
    pc.to_csv(f'{AD}/parameter_classes.csv', index=False)

    tot = ps['area'].sum()
    lines = []
    pr = lambda t: (print(t, flush=True), lines.append(t))                         # noqa: E731
    pr(f'polygons {len(ps):,}; area {tot:,.0f} km2; distinct stratigraphies {len(set(u["strat_id"])):,}')
    by_t = ps.groupby('template_id', observed=True)['area'].sum().sort_values(ascending=False)
    pr('area by template (%): ' + ', '.join(f'{k} {100 * v / tot:.1f}' for k, v in by_t.items()))
    by_tier = ps.groupby('thk_tier', observed=True)['area'].sum()
    pr('area by thickness tier (%): ' + ', '.join(f'{k} {100 * v / tot:.2f}' for k, v in by_tier.items()))
    proxy = ps['confidence'].astype(str).str.contains('proxy')
    pr(f'area on proxy templates: {100 * ps.loc[proxy, "area"].sum() / tot:.1f} %; on NONE: '
       f'{100 * ps.loc[ps["template_id"] == "NONE", "area"].sum() / tot:.1f} %')
    open(f'{AD}/strat_summary.txt', 'w').write('\n'.join(lines) + '\n')
    # the dataset's metadata (column definitions, tiers, sources, gaps): kept in the repository, shipped with the data
    readme = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'addendum', 'README_addendum.md')
    if os.path.exists(readme):
        open(f'{AD}/README.md', 'w', encoding='utf-8').write(open(readme, encoding='utf-8').read())


if __name__ == '__main__':
    main()
