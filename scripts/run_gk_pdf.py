"""Batch pdf_to_polygons.py over vector geokniga 1:200k sheets (sources/gk_pdf_sheets.csv:
sheet,pdf[,water]); frame from nomen.frame, legend sources/legend_<sheet>.csv, output
work/pdfvec/<sheet>.gpkg (+ _qa.json). Prints one line per sheet with the frame RMS.
usage: run_gk_pdf.py [sheet ...]"""
import json
import subprocess
import sys

import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
PY = '/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python'
sys.path.insert(0, f'{ROOT}/scripts')
import nomen  # noqa: E402

cfg = pd.read_csv(f'{ROOT}/sources/gk_pdf_sheets.csv', dtype=str, keep_default_na=False)
only = set(sys.argv[1:])
for _, r in cfg.iterrows():
    if only and r.sheet not in only:
        continue
    # combined sheets 'A_B' (P-58-XXXIV_O-58-IV): union of both frames (stacked, same longitudes)
    fr = [nomen.frame(s) for s in r.sheet.split('_')]
    lon0, lat0 = min(f[0] for f in fr), min(f[1] for f in fr)
    lon1, lat1 = max(f[2] for f in fr), max(f[3] for f in fr)
    out = f'{ROOT}/work/pdfvec/{r.sheet}.gpkg'
    cmd = [PY, '-W', 'ignore', f'{ROOT}/scripts/pdf_to_polygons.py', r.pdf, r.sheet, str(lon0), str(lat0), str(lon1), str(lat1),
           f'{ROOT}/sources/legend_{r.sheet}.csv', out, '--scale', '200000']
    if r.get('water'):
        cmd += ['--water', r.water]
    p = subprocess.run(cmd, capture_output=True, text=True)
    qa = {}
    try:
        qa = json.load(open(out.replace('.gpkg', '_qa.json')))
    except Exception:
        pass
    keep = {k: qa.get(k) for k in ('projection', 'rms_m', 'cover_frac', 'n_polygons', 'unmatched_fills') if k in qa}
    print(r.sheet, 'rc', p.returncode, keep, '' if p.returncode == 0 else p.stderr.strip().splitlines()[-1][:200], flush=True)
