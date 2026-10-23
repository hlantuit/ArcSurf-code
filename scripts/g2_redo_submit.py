#!/usr/bin/env python
"""Submit re-extractions of _g2 sheets with the eqdc 47/62 projection (commands from
g2_reproj_test.py -> work/g2_redo/commands.tsv). Per sheet one Slurm job: the new extract
command (output work/g2_redo/<sheet>.gpkg), the lake fixes recorded in the old
work/jpgvec/<sheet>.gpkg.fixes.txt re-applied (fix_lake_units.py), then coast_check.py on the
OLD and the NEW gpkg (independent test of the registration where the sheet has sea coast).
The merged outputs in work/jpgvec are not touched.

usage: g2_redo_submit.py <min_gain> [sheet ...]   (no sheets = every sheet with gain >= min_gain)"""
import re
import shlex
import subprocess
import sys

import pandas as pd

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
PY = '/albedo/work/user/hlantuit/conda_envs/arcticbeach/bin/python'
min_gain = float(sys.argv[1]); only = set(sys.argv[2:])
df = pd.read_csv(f'{ROOT}/work/g2_redo/commands.tsv', sep='\t')
df = df[df.new_cmd.notna()]
sel = df[df.sheet.isin(only)] if only else df[df.gain >= min_gain]
for _, r in sel.iterrows():
    tok = shlex.split(r.new_cmd)
    tok[0] = 'jpg_to_polygons.py'                      # the _ties work copy was merged into it
    for bad in ('>', '2>&1;'):                         # trailing shell redirections caught by the parser (O-55)
        if bad in tok:
            tok = tok[:tok.index(bad)]
    new = f'../work/g2_redo/{r.sheet}.gpkg'
    old = f'../work/jpgvec/{r.sheet}.gpkg'
    steps = [f'{PY} -W ignore {shlex.join(tok)}']
    try:
        for ln in open(f'{ROOT}/work/jpgvec/{r.sheet}.gpkg.fixes.txt'):
            m = re.match(r'(\S+) in ([-\d.,]+) >= ([\d.]+) km2 -> WATER', ln.strip())
            if m:
                steps.append(f'{PY} -W ignore fix_lake_units.py {new} {m.group(1)} {m.group(2)} {m.group(3)}')
    except FileNotFoundError:
        pass
    steps.append(f'echo OLD; {PY} -W ignore coast_check.py {old}; echo NEW; {PY} -W ignore coast_check.py {new}')
    wrap = f'cd {ROOT}/scripts && ' + ' && '.join(steps[:-1]) + '; ' + steps[-1]
    cmd = ['sbatch', '--parsable', '--export=ALL,SURF_DOMAIN=domain', '-A', 'perm_ag_coas.perm_ag_coas', '-p', 'smp',
           '--qos=12h', '-c', '32', '--mem=160G', '--time=01:00:00', '-J', 'g2r_' + r.sheet.replace('_g2', '').replace('-', ''),
           '-o', f'{ROOT}/work/g2_redo/{r.sheet}.log', '--wrap', wrap]
    jid = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()
    print(r.sheet, r.gain, jid)
