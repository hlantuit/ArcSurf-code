#!/usr/bin/env python
"""Unzip every Nordic archive into scratch/unz/nordic/<stem>/ and print, for each
vector file: layers, feature counts, CRS, fields, and the value counts of the
likely unit-code fields. Output goes to the job log; used to write the ingests."""
import glob
import os
import zipfile

import pyogrio

RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/nordic'
UNZ = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/nordic'
CODE_HINTS = ('jg2', 'jg2_tx', 'PINTAMAALAJI', 'PINTAMAALAJI_KOODI', 'GEO_CODE', 'geo_code',
              'løsmassetype', 'KOHDELUOKKA', 'TUNNUS', 'OBJTYPE', 'objtype', 'NAME', 'Name',
              'MAALAJI', 'SYMBOLI', 'jl2', 'jl2_tx')

for z in sorted(glob.glob(f'{RAW}/*.zip')):
    stem = os.path.basename(z)[:-4]
    d = f'{UNZ}/{stem}'
    if not os.path.isdir(d):
        os.makedirs(d)
        with zipfile.ZipFile(z) as f:
            f.extractall(d)
    # nested zips (NPI bundles)
    for zz in glob.glob(f'{d}/**/*.zip', recursive=True):
        dd = zz[:-4]
        if not os.path.isdir(dd):
            os.makedirs(dd)
            with zipfile.ZipFile(zz) as f:
                f.extractall(dd)

skip = ('Losmasser_FGDB',)  # older flattened NGU product: gapfill only, not inspected
vec = []
for pat in ('**/*.gpkg', '**/*.gdb', '**/*.shp', '**/*.geojson'):
    vec += [p for p in glob.glob(f'{UNZ}/{pat}', recursive=True) if not any(s in p for s in skip)]
for p in sorted(set(vec)):
    if p.endswith('.shp') and any(p.startswith(g) for g in vec if g.endswith('.gdb')):
        continue
    print('\n###', p.replace(UNZ + '/', ''))
    try:
        layers = pyogrio.list_layers(p)
    except Exception as e:
        print('   cannot open', e)
        continue
    for name, gt in layers:
        if gt is None or 'Polygon' not in str(gt):
            print(f'   - {name} {gt}')
            continue
        info = pyogrio.read_info(p, layer=name)
        print(f'   * {name} {gt} n={info["features"]} crs={info["crs"]}')
        print('     fields:', list(info['fields']))
        cols = [c for c in info['fields'] if c in CODE_HINTS]
        if cols and info['features'] < 3_000_000:
            df = pyogrio.read_dataframe(p, layer=name, columns=cols, read_geometry=False)
            for c in cols:
                vc = df[c].value_counts(dropna=False)
                print(f'     {c}: {len(vc)} values; top {vc.head(40).to_dict()}')
print('\nINSPECT DONE')
