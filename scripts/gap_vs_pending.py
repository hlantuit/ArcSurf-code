"""Which gap sheets (sources/ca_missing_nts.csv, groups A and C) are overlapped by an unprocessed OSTR product
(out/web/pending.json, NRCan OSTR items)? The gap list's catalogue check used only the GSC footprint index
(sources/canada_gsc_sheets.json); OSTR-only items (A-series maps missing from the index, Memoirs, Papers with map
sheets) are checked here. usage: gap_vs_pending.py"""
import json
import re

import numpy as np
import pandas as pd
import shapely
from pyproj import Transformer

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
pend = json.load(open(f'{ROOT}/out/web/pending.json', encoding='utf-8'))
d = pd.read_csv(f'{ROOT}/sources/ca_missing_nts.csv', keep_default_na=False)
tr = Transformer.from_crs(4326, 6931, always_xy=True)


def nts_poly(b):
    e, w, s, n = map(float, re.match(r'([\d.]+)-([\d.]+)W ([\d.]+)-([\d.]+)N', b).groups())
    lo = np.r_[np.linspace(-w, -e, 20), np.full(20, -e), np.linspace(-e, -w, 20), np.full(20, -w)]
    la = np.r_[np.full(20, s), np.linspace(s, n, 20), np.full(20, n), np.linspace(n, s, 20)]
    x, y = tr.transform(lo, la)
    return shapely.Polygon(np.c_[x, y] / 1000.0)


items = []
for it in pend:
    if it['src'] != 'NRCan OSTR':
        continue
    ps = [shapely.Polygon(r) for r in it['rings'] if len(r) >= 4]
    if ps:
        items.append((it, shapely.make_valid(shapely.union_all(ps))))
out = []
for _, r in d[d.group.isin(['A', 'C'])].iterrows():
    P = nts_poly(r.bbox)
    for it, g in items:
        if g.intersects(P):
            frac = g.intersection(P).area / P.area
            if frac > 0.05:
                out.append(dict(nts=r.nts, group=r.group, coarse_km2=r.coarse_km2, geoscan=it['sheet'], scale=it['scale'],
                                year=it.get('year', ''), note=it['note'], share=round(frac, 2), title=it['title'][:90]))
o = pd.DataFrame(out)
o.to_csv(f'{ROOT}/work/gap_vs_pending.csv', index=False)
print(f'{o.nts.nunique()} of {d.group.isin(["A", "C"]).sum()} group A/C sheets have >= 1 OSTR pending product overlapping > 5 %')
pd.set_option('display.width', 250); pd.set_option('display.max_colwidth', 70)
print(o.sort_values(['nts', 'share'], ascending=[True, False]).to_string(index=False))
