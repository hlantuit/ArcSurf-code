"""Batch extraction of legacy GSC scans from sources/gsc_scan_sheets.csv (one row per
sheet: frame lon/lat read from the corner labels, datum, approximate corners, exclusion
boxes, legend file), followed by the OSM coastline check. Writes work/gscvec/<label>.gpkg
and work/gscvec/summary.csv (frame fit + coast check per sheet).
usage: run_gsc_scans.py [label ...]   (default: all rows)"""
import glob
import json
import subprocess
import sys

import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
PY = '/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python'
cfg = pd.read_csv(f'{ROOT}/sources/gsc_scan_sheets.csv', dtype=str, keep_default_na=False)
only = set(sys.argv[1:])
rows = []
for _, r in cfg.iterrows():
    if only and r.label not in only:
        continue
    # multi-panel sheets: one row per panel, 'file' names the image (label = sheet_panel)
    sheet = r.label.split('_')[0] if r.get('file') else r.label
    img = (f'{ROOT}/raw/canada/gsc_scans/{sheet}/{r.file}' if r.get('file') else
           sorted(glob.glob(f'{ROOT}/raw/canada/gsc_scans/{r.label}/*'), key=lambda p: -__import__('os').path.getsize(p))[0])
    out = f'{ROOT}/work/gscvec/{r.label}.gpkg'
    cmd = [PY, '-W', 'ignore', f'{ROOT}/scripts/jpg_to_polygons.py', 'extract', img, r.label,
           f'{ROOT}/sources/{r.legend}', out, f'--lonlat={r.lonlat}', '--datum', r.datum or '4267',
           '--corners', r.corners, '--paper-nodata']
    if r.exclude:
        cmd += ['--exclude', r.exclude]
    if r.get('no_snap'):
        cmd += ['--no-snap']
    if r.get('exclude_lonlat'):
        cmd += [f'--exclude-lonlat={r.exclude_lonlat}']     # '=': the value starts with '-' (argparse)
    if r.get('thin_units'):
        cmd += ['--thin-units', r.thin_units]
    if r.get('min_L'):
        cmd += ['--min-L', r.min_L]
    if r.get('grid'):
        cmd += ['--grid', r.grid]
    if r.get('pattern'):
        cmd += ['--pattern', r.pattern]
    if r.get('paper_rgb'):
        cmd += ['--paper-rgb', r.paper_rgb]
    if r.get('paper_close'):
        cmd += ['--paper-close', r.paper_close]
    if r.get('main_region'):
        cmd += ['--main-region', r.main_region]
    p = subprocess.run(cmd, capture_output=True, text=True)
    ok = p.returncode == 0
    rep = json.load(open(out.replace('.gpkg', '.json'))) if ok else {}
    cc = subprocess.run([PY, '-W', 'ignore', f'{ROOT}/scripts/coast_check.py', out], capture_output=True, text=True).stdout.strip() if ok else ''
    row = dict(label=r.label, ok=ok, projection=rep.get('projection'), corner_rms_m=round(rep.get('rms_m', float('nan')), 1),
               m_per_px=round(rep.get('m_per_px', float('nan')), 2), unassigned=rep.get('unassigned_before_fill'),
               km2=round(rep.get('area_km2', 0)), coast=cc.split(': ', 1)[-1] if cc else '',
               error='' if ok else p.stderr.strip().splitlines()[-1][:200])
    # QC gate (A1686a passed silently with a mis-read corner: 1.5 km corner rms, 629 m coast)
    import re
    m = re.search(r'median (\d+) m', row['coast'])
    scale = next((int(x) for x in re.findall(r'1:(\d+)', rep.get('sheet', '')) if x), None)
    lim = 0.0012 * (float(r.get("scale") or 0) or 250000)          # 1.2 mm at map scale (relaxed from 0.8 mm 2026-10-02)
    # corner rms gate: 300 m, or 0.45 mm at map scale for small-scale sheets (1:1M Map 24-1987: symmetric 300-420 m
    # residuals from 0.1 % paper anisotropy, spline-pinned corners; 300 m is 0.3 mm there)
    rms_lim = max(300.0, 0.00045 * (float(r.get('scale') or 0) or 250000))
    row['qc'] = 'PASS' if ok and row['corner_rms_m'] <= rms_lim and (m is None or int(m.group(1)) <= lim) else 'FAIL'
    if r.get('qc_override') == 'FAIL':                                # known defect the gate cannot see (qc_note)
        row['qc'] = 'FAIL (override)'
    print(row, flush=True)
    rows.append(row)
s = pd.DataFrame(rows)
old = f'{ROOT}/work/gscvec/summary.csv'
import fcntl
with open(old + '.lock', 'w') as lk:        # several runner jobs may finish together
    fcntl.flock(lk, fcntl.LOCK_EX)
    try:
        prev = pd.read_csv(old)
        s = pd.concat([prev[~prev.label.isin(s.label)], s], ignore_index=True)
    except FileNotFoundError:
        pass
    s.to_csv(old, index=False)
