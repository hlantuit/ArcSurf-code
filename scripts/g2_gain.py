"""Rank full-resolution GGK-1000/2 scans (raw/russia_geokniga_1m/*_g2, JPG >= 5000 px) by the
domain area their frames add beyond sheets already in ingest_russia._G1M (+ R-52, Q-42).
Area in EASE-Grid North km2. Writes work/g2_gain.csv."""
import glob
import os
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import geopandas as gpd  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from PIL import Image  # noqa: E402
import nomen  # noqa: E402
import surflib as S  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
R = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga_1m'
src = open('/albedo/work/user/hlantuit/arctic_surficial/scripts/ingest_russia.py', encoding='utf-8').read()
g1m = src[src.index('_G1M ='):]; g1m = g1m[:g1m.index(']') + 1]
done = [re.sub(r'_g\d$', '', s) for s in re.findall(r"'([A-U]-[0-9A-Z,()\-]+_g\d)'", g1m)] + ['R-52', 'Q-42']


def frames(code):
    """1:1M frames of a (possibly multi-sheet) code: 'N-49,(50)', 'O-(50),51', 'R-45-(47)', 'P-35-37'."""
    m = re.match(r'([A-U])-(.*)', code.replace('_', '').replace('(', '').replace(')', ''))
    row, rest = m.group(1), m.group(2)
    if re.fullmatch(r'\d+-\d+', rest):                    # range 45-47
        a, b = map(int, rest.split('-'))
        nums = list(range(a, b + 1)) if b >= a else list(range(a, 61)) + list(range(1, b + 1))
    else:
        nums = [int(n) for n in re.split(r'[,\-]', rest) if n.isdigit()]
    out = []
    for n in nums:
        try:
            lo0, la0, lo1, la1 = nomen.frame(f'{row}-{n}')
            if lo1 > lo0:
                out.append(shapely.box(lo0, la0, lo1, la1))
        except Exception:
            pass
    return out


dom = gpd.read_file(f'{S.WORK}/domain_obu_amap.gpkg').to_crs(4326).union_all()
have = shapely.union_all([f for c in done for f in frames(c)])
rows = []
for d in sorted(glob.glob(f'{R}/*_g2')):
    jp = sorted(glob.glob(f'{d}/*.jpg'), key=os.path.getsize)
    if not jp:
        continue
    w, h = Image.open(jp[-1]).size
    if max(w, h) < 5000:
        continue
    code = re.sub(r'_g2$', '', os.path.basename(d))
    fr = frames(code)
    if not fr:
        rows.append((code, w, h, None, None)); continue
    sheet = shapely.union_all(fr)
    new = shapely.intersection(shapely.difference(sheet, have), dom)
    to_km2 = lambda g: gpd.GeoSeries([g], crs=4326).to_crs(S.CRS).area.iloc[0] / 1e6 if not g.is_empty else 0.0   # noqa: E731
    rows.append((code, w, h, round(to_km2(shapely.intersection(sheet, dom))), round(to_km2(new))))
t = pd.DataFrame(rows, columns=['sheet', 'w', 'h', 'domain_km2', 'gain_km2']).sort_values('gain_km2', ascending=False)
t.to_csv(f'{S.WORK}/g2_gain.csv', index=False)
print(t.to_string(index=False))
