#!/usr/bin/env python
"""
Stage OSTR census items that ship GIS geology (work/ostrvec/gis_survey.csv) as sheet dirs
under raw/canada/gsc/<label>/ (unzipped, with _MANIFEST.json), so ingest_canada.py picks
them up: CGM ('cgm_0105_p1.zip' -> CGM105; GEO_POLYS) and legacy A-series / Open File
('as_1919.zip' -> A1919a, 'of_4484.zip' -> OF4484; geology/geo*_ply.shp).
Skipped: labels already staged; items whose only polygons are predictive GEM_POLYS,
bases, isopachs or field-station layers (listed with the reason).
usage: stage_ostr_gis.py [--dry]
"""
import json
import os
import re
import subprocess
import sys
import zipfile

import pandas as pd

R = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada'
OSTR, GSC = f'{R}/ostr_new', f'{R}/gsc'
ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
dry = '--dry' in sys.argv
t = pd.read_csv(f'{ROOT}/work/ostrvec/gis_survey.csv', dtype=str, keep_default_na=False)
oc = pd.read_csv(f'{ROOT}/sources/canada_ostr_new_in_domain.csv', dtype={'geoscan': str}).set_index('geoscan')
have = set(os.listdir(GSC))
done, skip = [], []
for _, r in t.iterrows():
    z = f'{OSTR}/{r.geoscan}/{r.zip}'
    try:
        names = zipfile.ZipFile(z).namelist()
    except Exception as e:
        skip.append((r.geoscan, r.zip, f'bad zip {e}')); continue
    low = [n.lower() for n in names]
    cgm = re.search(r'cgm_0*(\d+)', r.zip) or next((re.search(r'cgm_0*(\d+)', n) for n in low if re.search(r'cgm_0*\d+', n)), None)
    if any(n.endswith('geo_polys.shp') for n in low) or any('geo_polys' in n for n in low if '.gdb/' in n):
        if not cgm:
            skip.append((r.geoscan, r.zip, 'GEO_POLYS but no CGM number')); continue
        label = f'CGM{int(cgm.group(1))}'
    elif any(re.search(r'geology/geo\d+_ply\.shp$', n) for n in low):
        m = re.match(r'(as|of|a)_0*(\d+)', r.zip)
        if not m:
            skip.append((r.geoscan, r.zip, 'legacy layout, unknown label')); continue
        label = f'A{int(m.group(2))}a' if m.group(1) in ('as', 'a') else f'OF{int(m.group(2))}'
    else:
        skip.append((r.geoscan, r.zip, 'no GEO_POLYS / geo*_ply (predictive GEM_POLYS, bases or other)')); continue
    if label in have:
        skip.append((r.geoscan, r.zip, f'{label} already staged')); continue
    m = oc.loc[r.geoscan] if r.geoscan in oc.index else None
    title = str(m.title) if m is not None else r.title
    tl = title.lower()
    tier = 'predictive' if 'predictive' in tl else ('reconnaissance' if 'reconnaissance' in tl else 'surficial')
    man = dict(geoscan=int(r.geoscan), label=label, title=title, tier_from_title=tier,
               scale=int(float(m.scale)) if m is not None else int(float(r.scale or 0)),
               release=f'{int(float(m.year))}-01-01' if m is not None and str(m.year) not in ('', 'nan') else '',
               bbox_wgs84=[float(v) for v in str(m.bbox).split(',')] if m is not None else None,
               zips=[dict(name=r.zip, bytes=os.path.getsize(z))], staged_by='stage_ostr_gis.py 2026-10-01')
    done.append((label, r.geoscan, man['scale'], tier, title[:60]))
    if dry:
        continue
    d = f'{GSC}/{label}'
    os.makedirs(d, exist_ok=True)
    subprocess.run(['unzip', '-q', '-o', '-DD', z, '-d', d], check=False)
    json.dump(man, open(f'{d}/_MANIFEST.json', 'w'), indent=1)
    have.add(label)
print('STAGED', len(done))
for x in done:
    print('  ', *x)
print('SKIPPED', len(skip))
for x in skip:
    print('  ', *x)
