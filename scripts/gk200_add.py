"""Register a 1:200k vector sheet: legend from sources/legspec/<sheet>.txt (mk_legend format),
pdf from work/gk200_leg/<sheet>__<pdf>; updates sources/gk_pdf_sheets.csv.
usage: gk200_add.py <sheet> <pdf filename> [water hexes]"""
import subprocess, sys
import pandas as pd
s, pdf = sys.argv[1], sys.argv[2]
subprocess.run([sys.executable, 'scripts/mk_legend.py', s, f'sources/legspec/{s}.txt'], check=True)
D = '/albedo/work/user/hlantuit/arctic_surficial/work/gk200_leg'
p = 'sources/gk_pdf_sheets.csv'; d = pd.read_csv(p, dtype=str, keep_default_na=False)
d = pd.concat([d, pd.DataFrame([dict(sheet=s, pdf=f'{D}/{s}__{pdf}', water=sys.argv[3] if len(sys.argv) > 3 else '')])]).drop_duplicates('sheet', keep='last')
d.to_csv(p, index=False)
