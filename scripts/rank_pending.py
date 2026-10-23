"""Rank pending (unprocessed) Canadian products by what they would add to the CURRENT merge: per product
footprint (out/web/pending.json rings, EPSG:6931 km), land cells of out/coverage_class.tif whose finest class is
coarser than the product's scale class. gain_coarse = cells now at >= 1:2.5M; gain = all improvable cells.
usage: rank_pending.py [kind substring, e.g. line]   -> work/pending_rank.csv"""
import json
import sys

import numpy as np
import pandas as pd
import rasterio
import rasterio.features as rf
import shapely

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402

kind = sys.argv[1] if len(sys.argv) > 1 else ''
items = json.load(open(f'{S.OUT}/web/pending.json', encoding='utf-8'))
with rasterio.open(f'{S.OUT}/coverage_class.tif') as r:
    g = r.read(1); tf = r.transform
cell = abs(tf.a * tf.e) / 1e6


def pclass(sc):
    return 1 if sc <= 100_000 else 2 if sc <= 260_000 else 3 if sc <= 700_000 else 4 if sc <= 1_500_000 else 5


rows = []
for it in items:
    if it['src'] != 'NRCan OSTR' or kind not in it.get('note', ''):
        continue
    polys = [shapely.Polygon(np.array(ring) * 1000.0) for ring in it['rings'] if len(ring) >= 4]   # rings = list of outer rings (km)
    if not polys:
        continue
    m = rf.rasterize([(p, 1) for p in polys], out_shape=g.shape, transform=tf, fill=0, dtype='uint8') == 1
    c = g[m]
    pc = pclass(it['scale'] or 10**9)
    rows.append(dict(label=it['sheet'], note=it['note'], status=it['status'], scale=it['scale'], year=it.get('year'),
                     land_km2=round(float((c > 0).sum() * cell)), gain_km2=round(float(((c > pc) & (c > 0)).sum() * cell)),
                     gain_coarse_km2=round(float((c == 5).sum() * cell)), title=it['title'][:90]))
df = pd.DataFrame(rows).sort_values(['gain_coarse_km2', 'gain_km2'], ascending=False)
df.to_csv(f'{S.WORK}/pending_rank.csv', index=False)
print(df.groupby('note')[['gain_km2', 'gain_coarse_km2']].agg(['count', 'sum']).to_string())
print(df.head(45).to_string(index=False))
