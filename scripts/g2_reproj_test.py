#!/usr/bin/env python
"""Re-test the 2nd-generation (_g2) Russian 1:1M rasters with the USSR-wide 1:1M projection
(equidistant conic, standard parallels 47/62 N; reference_soviet_1m_new_series_projection).

The extract commands are not stored with the outputs, so they are recovered from Slurm:
sacct SubmitLine of the last COMPLETED `jpg_to_polygons*.py extract` job per output gpkg.
For each sheet: the affine residual over its control points (4 corners + ties, exactly as in
the run) under the projection the run chose vs under eqdc 47/62. Writes
work/g2_redo/commands.tsv (sheet, old rms, 47/62 rms, old command, new command with --proj
and the output redirected to work/g2_redo/<sheet>.gpkg) so improved sheets can be re-extracted
without touching the merged outputs.

usage: g2_reproj_test.py [--since 2026-10-01] [--pattern _g2]"""
import argparse
import contextlib
import io
import os
import re
import shlex
import subprocess

import pandas as pd

import jpg_to_polygons as J

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
ap = argparse.ArgumentParser()
ap.add_argument('--since', default='2026-10-01'); ap.add_argument('--pattern', default='_g2')
a = ap.parse_args()
out = subprocess.run(['sacct', '-u', 'hlantuit', '-S', a.since, '-E', 'now', '-X', '-n', '-P',
                      '-o', 'JobID,State,SubmitLine%4000'], capture_output=True, text=True).stdout
last = {}
for ln in out.splitlines():
    p = ln.split('|', 2)
    if len(p) < 3 or p[1] != 'COMPLETED' or 'jpg_to_polygons' not in p[2] or ' extract ' not in p[2]:
        continue
    w = re.search(r'--wrap[= ](.*)$', p[2])
    if not w:
        continue
    cmd = w.group(1)
    cmd = cmd[cmd.index('jpg_to_polygons'):]
    try:
        tok = shlex.split(cmd)
    except ValueError:
        continue
    # extract <img> <sheet> <legend> <out.gpkg> [options]
    if len(tok) < 6 or tok[1] != 'extract':
        continue
    sheet = tok[3]
    if a.pattern not in sheet:
        continue
    last[sheet] = (int(p[0].split('_')[0]), tok)       # sacct is in submit order: keep the last


def opt(tok, name):
    for i, t in enumerate(tok):
        if t == name and i + 1 < len(tok):
            return tok[i + 1]
        if t.startswith(name + '='):
            return t.split('=', 1)[1]
    return None


rows = []
for sheet, (jid, tok) in sorted(last.items()):
    ll = opt(tok, '--lonlat'); co = opt(tok, '--corners'); ti = opt(tok, '--ties')
    datum = int(opt(tok, '--datum') or 4284)
    if not ll or not co:
        rows.append(dict(sheet=sheet, job=jid, note='no --lonlat/--corners (auto frame): skipped')); continue
    lo0, la0, lo1, la1 = map(float, ll.split(','))
    pts = [tuple(map(float, q.split(','))) for q in co.split(';')]
    ties = [tuple(map(float, q.split(','))) for q in ti.split(';')] if ti else None
    prj = f'+proj=eqdc +lat_1=47 +lat_2=62 +lon_0={(lo0 + lo1) / 2:g}'
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _, f0 = J.corner_fit(pts, lo0, la0, lo1, la1, datum, ties, opt(tok, '--proj'))
        _, f1 = J.corner_fit(pts, lo0, la0, lo1, la1, datum, ties, prj)
    new = list(tok)
    i = new.index('extract')
    new[i + 4] = f'../work/g2_redo/{sheet}.gpkg'
    if '--proj' in new:
        new[new.index('--proj') + 1] = prj
    else:
        new += ['--proj', prj]
    rows.append(dict(sheet=sheet, job=jid, n_ctrl=4 + (len(ties) if ties else 0), proj_old=f0['projection'],
                     rms_old=round(f0['rms_m']), max_old=round(f0['max_res_m']), rms_4762=round(f1['rms_m']),
                     max_4762=round(f1['max_res_m']), gain=round(1 - f1['rms_m'] / max(f0['rms_m'], 1e-9), 2),
                     old_cmd=shlex.join(tok), new_cmd=shlex.join(new)))
os.makedirs(f'{ROOT}/work/g2_redo', exist_ok=True)
df = pd.DataFrame(rows)
df.to_csv(f'{ROOT}/work/g2_redo/commands.tsv', sep='\t', index=False)
cols = [c for c in ('sheet', 'job', 'n_ctrl', 'proj_old', 'rms_old', 'max_old', 'rms_4762', 'max_4762', 'gain', 'note') if c in df.columns]
print(df[cols].to_string(index=False))
