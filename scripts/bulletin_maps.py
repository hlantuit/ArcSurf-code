"""Map identifiers cited in a GSC report PDF (Bulletin 611 ch. 5 'Status of surficial geology mapping in northern
Canada' lists the GEM surficial maps), compared with our catalogue (sources/canada_gsc_sheets.json) and with the
merged sources (xw/ca_*.gpkg footprints). Writes <pdf>.maps.csv.
usage: bulletin_maps.py <pdf>"""
import glob
import json
import re
import sys

from PIL import Image  # noqa: F401  (before fitz on Albedo)
import fitz
import geopandas as gpd
import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
doc = fitz.open(sys.argv[1])
txt = '\n'.join(p.get_text() for p in doc)
open(sys.argv[1] + '.txt', 'w', encoding='utf-8').write(txt)
t = re.sub(r'\s+', ' ', txt)
ids = {}
for m in re.finditer(r'(?:Canadian Geoscience Map|CGM)\s*(\d{1,3})\b', t):
    ids.setdefault(f'CGM{int(m.group(1))}', m.start())
for m in re.finditer(r'Open File\s*(\d{2,4})\b', t):
    ids.setdefault(f'OF{int(m.group(1))}', m.start())
for m in re.finditer(r'\bMap\s*(\d{3,4})A\b', t):
    ids.setdefault(f'A{int(m.group(1))}a', m.start())
cat = {s['label']: s for s in json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']}
done = set()
for f in glob.glob(f'{ROOT}/work/xw/ca_*.gpkg'):
    try:
        done |= set(gpd.read_file(f, layer='footprint', ignore_geometry=True)['src_sheet'].astype(str).str.split('_').str[0])
    except Exception:
        pass
rows = []
for k, pos in sorted(ids.items(), key=lambda kv: kv[1]):
    ctx = t[max(0, pos - 120):pos + 160]
    rows.append(dict(id=k, in_catalogue=k in cat, merged=k in done,
                     title=(cat[k]['title'][:80] if k in cat else ''), context=ctx))
df = pd.DataFrame(rows)
df.to_csv(sys.argv[1] + '.maps.csv', index=False)
n_a = int(df.id.str.match(r'A[0-9]').sum())
print(f'pages {len(doc)}; cited map ids {len(df)}: CGM {df.id.str.startswith("CGM").sum()}, OF {df.id.str.startswith("OF").sum()}, '
      f'A-series {n_a}')
print(df.groupby([df.id.str.extract(r'^(CGM|OF|A)')[0], 'in_catalogue', 'merged']).size().to_string())
miss = df[~df.in_catalogue]
print(f'\nNOT in our catalogue ({len(miss)}):')
for _, r in miss.iterrows():
    print(f"  {r.id:8s} ...{r.context[60:250]}...")
