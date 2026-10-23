#!/usr/bin/env python
"""
Fetch the Nordic sources not already in the probe folder, into
/albedo/scratch/user/hlantuit/arctic_surficial/raw/nordic (raw = regenerable ->
scratch; work/raw/nordic is a symlink to it).

- NGU Løsmasser Detaljert / Lokalt / Regionalt for Trøndelag (50) and Møre og
  Romsdal (15): the AMAP boundary reaches 62-64N in western Norway. Links are
  re-parsed from the ATOM feeds each run because NGU's file ids change on
  republication. UTM 33 variants (same as the northern counties).
- NPI S100 Kartdata (moraines, river plains, glaciers at 1:100k)
- SGU Jordarter 25k-100k (national, 3.38 GB)
- GTK Maaperä 1:20k/50k and 1:1M
Every file is checked against Content-Length when the server sends one, and
against a zip integrity test always. A manifest (path, bytes) is written.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

import urllib.request

DST = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/nordic'
PROBE = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/nordic'
FEEDS = {'Detaljert': 'b8cf02c7-b01b-498f-8e90-1fc9bc46056b',
         'Region': 'e5847c27-0c30-44b6-9198-a797c177fa20',
         'Lokalt': '4d50a95c-e220-44c5-8bed-393c38fff6d4'}
COUNTIES = {'Trøndelag': '50_Trondelag', 'Møre og Romsdal': '15_More_og_Romsdal'}
DIRECT = {
    'NP_S100_SHP.zip': 'https://public.data.npolar.no/kartdata/NP_S100_SHP.zip',
    'jordarter25k-100k.zip': 'https://resource.sgu.se/data/oppnadata/jordarter25k-100k/jordarter25k-100k.zip',
    'maapera_20_50k_epsg3067_gdb.zip': 'https://tupa.gtk.fi/paikkatieto/maapera_20_50k_epsg3067_gdb.zip',
    'maapera_1m_etrs_tm35fin_gdb.zip': 'https://tupa.gtk.fi/paikkatieto/maapera_1m_etrs_tm35fin_gdb.zip',
}


def curl(url, out):
    hdr = subprocess.run(['curl', '-sIL', '--max-time', '60', url], capture_output=True, text=True).stdout
    cl = [int(m) for m in re.findall(r'(?im)^content-length:\s*(\d+)', hdr)]
    exp = cl[-1] if cl and cl[-1] > 0 else None
    if os.path.exists(out) and exp and os.path.getsize(out) == exp:
        return out, exp, 'cached'
    r = subprocess.run(['curl', '-sSL', '--retry', '5', '--max-time', '7200', '-o', out, url])
    if r.returncode:
        raise RuntimeError(f'curl {r.returncode} {url}')
    got = os.path.getsize(out)
    if exp and got != exp:
        raise RuntimeError(f'SIZE {out}: expected {exp} got {got}')
    return out, exp, 'downloaded'


def ngu_links():
    links = {}
    for prod, uid in FEEDS.items():
        x = urllib.request.urlopen(f'https://nedlasting.ngu.no/api/atom/{uid}', timeout=60).read().decode('utf-8')
        for e in re.findall(r'<entry>(.*?)</entry>', x, re.S):
            t = ' '.join(re.findall(r'<title[^>]*>([^<]*)</title>', e))
            href = [h for h in re.findall(r'href="([^"]+)"', e) if 'fileproxy' in h]
            for cname, tag in COUNTIES.items():
                if f'fylke-{cname}-UTM Sone 33' in t and 'GPKG' in t and href:
                    links[f'Geologi_{tag}_25833_Losmasse{prod}_GPKG.zip'] = href[0]
    return links


def main():
    os.makedirs(DST, exist_ok=True)
    # reuse probe files (move, not copy: same filesystem)
    for f in os.listdir(PROBE):
        if f.endswith('.zip') and not os.path.exists(f'{DST}/{f}'):
            shutil.move(f'{PROBE}/{f}', f'{DST}/{f}')
    todo = dict(DIRECT)
    ngu = ngu_links()
    print('NGU feed entries found:', sorted(ngu))
    todo.update(ngu)
    for name, url in todo.items():
        out, exp, how = curl(url, f'{DST}/{name}')
        print(name, how, os.path.getsize(out), 'expected', exp, flush=True)
    man = []
    for f in sorted(os.listdir(DST)):
        p = f'{DST}/{f}'
        ok = None
        if f.endswith('.zip'):
            try:
                with zipfile.ZipFile(p) as z:
                    ok = z.testzip() is None
            except zipfile.BadZipFile:
                ok = False
        man.append({'file': f, 'bytes': os.path.getsize(p), 'zip_ok': ok})
    json.dump(man, open(f'{DST}/MANIFEST.json', 'w'), indent=1)
    bad = [m for m in man if m['zip_ok'] is False]
    print(json.dumps(man, indent=0))
    if bad:
        print('BAD ZIPS', bad)
        sys.exit(1)
    missing = [c for c in COUNTIES.values() for p in FEEDS if f'Geologi_{c}_25833_Losmasse{p}_GPKG.zip' not in ngu]
    print('NGU county/product combos NOT in feed:', missing)
    print('DONE')


if __name__ == '__main__':
    main()
