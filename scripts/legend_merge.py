"""Merge legend units that share one printed colour (told apart only by labels; legend_dryrun.py shows them as
100 % ambiguous): every unit of a group gets the group's mean fill, so the extraction writes ONE class with the
combined key 'a|b', and the same hclass / hclass2 / texture / ice_rich (ingest_russia.py requires one hclass per
key and takes the first row's attributes).
usage: legend_merge.py <legend.csv> "a+b[+c][=hclass,hclass2,texture]" [...]
       (without '=...' the group takes the first unit's attributes)"""
import sys

import pandas as pd

p = sys.argv[1]
L = pd.read_csv(p, dtype=str, keep_default_na=False)
for spec in sys.argv[2:]:
    names, _, attrs = spec.partition('=')
    names = names.split('+')
    rows = L.index[L['index'].isin(names)]
    assert len(rows) == len(names), f'{spec}: found {L.loc[rows, "index"].tolist()}'
    rgb = [[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in L.loc[rows, 'fill']]
    fill = '#%02x%02x%02x' % tuple(round(sum(c[k] for c in rgb) / len(rgb)) for k in range(3))
    first = L.loc[L['index'] == names[0]].iloc[0]
    hc, h2, tx = attrs.split(',') if attrs else (first.hclass, first.hclass2, first.texture)
    for r in rows:
        others = [n for n in names if n != L.at[r, 'index']]
        L.at[r, 'fill'], L.at[r, 'hclass'], L.at[r, 'hclass2'], L.at[r, 'texture'] = fill, hc, h2, tx
        L.at[r, 'ice_rich'] = first.ice_rich
        L.at[r, 'note'] = (L.at[r, 'note'] + f' ; same printed colour as {"/".join(others)}: one class').strip(' ;')
    print(f'{"|".join(names)}: {fill} {hc} {h2} {tx}')
L.to_csv(p, index=False)
