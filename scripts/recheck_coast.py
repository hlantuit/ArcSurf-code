"""Re-run coast_check.py on every sheet in work/gscvec/summary.csv after the 2026-10-02 fix (the build-domain
edge, where the land layer is clipped, had been scored as coast on inland sheets) and recompute the QC gate
(corner rms <= 300 m and coast median <= 1.2 mm at map scale). Keeps the previous values as coast_old / qc_old.
usage: recheck_coast.py [label ...]"""
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
PY = '/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python'
s = pd.read_csv(f'{ROOT}/work/gscvec/summary.csv', dtype=str, keep_default_na=False)
cfg = pd.read_csv(f'{ROOT}/sources/gsc_scan_sheets.csv', dtype=str, keep_default_na=False).set_index('label')
only = set(sys.argv[1:])
todo = [l for l in s.label if (not only or l in only) and s.loc[s.label == l, 'ok'].iloc[0] == 'True']


def run(lab):
    p = subprocess.run([PY, '-W', 'ignore', f'{ROOT}/scripts/coast_check.py', f'{ROOT}/work/gscvec/{lab}.gpkg'],
                       capture_output=True, text=True)
    return lab, p.stdout.strip().splitlines()[-1] if p.stdout.strip() else 'ERROR ' + p.stderr.strip()[-200:]


with ThreadPoolExecutor(16) as ex:
    res = dict(ex.map(run, todo))
import fcntl                                   # runner jobs append rows under the same lock
lk = open(f'{ROOT}/work/gscvec/summary.csv.lock', 'w')
fcntl.flock(lk, fcntl.LOCK_EX)
s = pd.read_csv(f'{ROOT}/work/gscvec/summary.csv', dtype=str, keep_default_na=False)   # re-read under the lock
for c in ('coast_old', 'qc_old'):
    if c not in s:
        s[c] = ''
for i, r in s.iterrows():
    if r.label not in res:
        continue
    cc = res[r.label]
    new = cc.split(': ', 1)[-1] if ': ' in cc else cc
    if not r.coast_old:
        s.at[i, 'coast_old'], s.at[i, 'qc_old'] = r.coast, r.qc
    s.at[i, 'coast'] = new
    m = re.search(r'median (\d+) m', new)
    sc = float((cfg.loc[r.label, 'scale'] if r.label in cfg.index else '') or 250000)
    s.at[i, 'qc'] = 'PASS' if float(r.corner_rms_m) <= 300 and (m is None or int(m.group(1)) <= 0.0012 * sc) else 'FAIL'
    if r.label in cfg.index and cfg.loc[r.label].get('qc_override', '') == 'FAIL':
        s.at[i, 'qc'] = 'FAIL (override)'
    print(f'{r.label}: {s.at[i, "qc_old"]} -> {s.at[i, "qc"]} | old: {s.at[i, "coast_old"][:70]} | new: {new[:70]}', flush=True)
s.to_csv(f'{ROOT}/work/gscvec/summary.csv', index=False)
lk.close()
