"""Survey CGM sheets that have no GEO_POLYS layer: every polygon layer (gdb or shp) with
its feature count and fields, to write a reader for the older CGM/SDM schemas."""
import collections
import glob
import json
import os
import sys

import pyogrio

GSC = '/albedo/work/user/hlantuit/arctic_surficial/raw/canada/gsc'
sheets = sys.argv[1].split(',')
schemas = collections.Counter()
out = {}
for s in sheets:
    d = f'{GSC}/{s}'
    rows = []
    srcs = [g for g in glob.glob(f'{d}/**/*.gdb', recursive=True)] + glob.glob(f'{d}/**/*.shp', recursive=True)
    for g in srcs:
        if 'carto' in g.lower() or 'topo' in g.lower() or 'base.gdb' in g.lower():
            continue
        try:
            layers = pyogrio.list_layers(g)
        except Exception:
            continue
        for name, gtype in layers:
            if gtype is None or 'Polygon' not in str(gtype):
                continue
            try:
                i = pyogrio.read_info(g, layer=name)
            except Exception:
                continue
            if i['features'] == 0:
                continue
            f = tuple(sorted(i['fields']))
            rows.append(dict(src=g.replace(d + '/', ''), layer=name, n=i['features'], fields=list(i['fields'])[:25]))
    big = sorted(rows, key=lambda r: -r['n'])[:4]
    out[s] = big
    title = json.load(open(f'{d}/_MANIFEST.json')).get('title', '')[:70]
    print(f'## {s} {title}')
    for r in big:
        print(f'   {r["n"]:6d} {r["src"]} :: {r["layer"]}  fields={r["fields"][:14]}')
json.dump(out, open('/albedo/work/user/hlantuit/arctic_surficial/work/cgm_old_survey.json', 'w'), indent=1)
