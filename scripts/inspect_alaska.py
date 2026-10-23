#!/usr/bin/env python
"""Targeted Alaska inspection: polygon layers + fields, map-unit tables, per-file
timeout (signal.alarm) so a single bad file cannot hang the run. Writes
work/alaska_inventory.json and prints a summary."""
import glob
import json
import os
import signal

import pyogrio

U = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/alaska'
OUT = '/albedo/work/user/hlantuit/arctic_surficial/work/alaska_inventory.json'
UNIT_FIELDS = ('MapUnit', 'MAPUNIT', 'QCLASS', 'UNITLABEL', 'UNIT', 'LABEL', 'ESI', 'SOURCECLAS')


class TO(Exception):
    pass


def alarm(*_):
    raise TO()


signal.signal(signal.SIGALRM, alarm)
inv = {}
paths = sorted(set(glob.glob(f'{U}/**/*.gdb', recursive=True) + glob.glob(f'{U}/**/*.shp', recursive=True)))
paths = [p for p in paths if not any(p.startswith(g + '/') for g in paths if g.endswith('.gdb'))]
for p in paths:
    key = p.replace(U + '/', '')
    signal.alarm(120)
    try:
        layers = pyogrio.list_layers(p)
        rec = {}
        for name, gt in layers:
            info = pyogrio.read_info(p, layer=name)
            f = list(info['fields'])
            r = {'geom': str(gt), 'n': int(info['features']), 'crs': str(info['crs'])[:60], 'fields': f[:40]}
            uf = [c for c in f if c in UNIT_FIELDS]
            if uf and 'Polygon' in str(gt) and info['features'] < 500000:
                df = pyogrio.read_dataframe(p, layer=name, columns=uf, read_geometry=False)
                r['units'] = {c: df[c].astype(str).value_counts().head(80).to_dict() for c in uf}
            if name.lower().startswith('descriptionofmapunits') or 'dmu' in name.lower():
                df = pyogrio.read_dataframe(p, layer=name, read_geometry=False)
                cols = [c for c in df.columns if c.lower() in ('mapunit', 'name', 'fullname', 'label')]
                r['dmu'] = df[cols].astype(str).head(120).to_dict('records')
            rec[name] = r
        inv[key] = rec
    except TO:
        inv[key] = {'error': 'timeout'}
    except Exception as e:
        inv[key] = {'error': repr(e)[:200]}
    finally:
        signal.alarm(0)
    print(key, {k: (v.get('geom'), v.get('n')) if isinstance(v, dict) else v for k, v in inv[key].items()} if isinstance(inv[key], dict) else inv[key], flush=True)
json.dump(inv, open(OUT, 'w'), indent=1, default=str)
print('wrote', OUT)
