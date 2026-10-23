#!/usr/bin/env python
"""
Polite fetch of geokniga.org Quaternary-map files for a list of map pages.

User-approved (2026-09-29) for the 30 coastal 1:200k sheets in
sources/geokniga_coastal_200k.md. One request stream, a pause between requests,
honest descriptive user agent (the site's filter rejects the word 'harvest'; it
accepts any other descriptive agent incl. plain curl). Per page: the Quaternary-map
PDF(s) under maps/additional/ and the full-size map image(s) under files/maps/
(imagecache previews skipped). Sizes are checked against Content-Length.
Terms: geokniga states materials are for familiarisation only -> internal_only.

usage: download_geokniga.py <pages.txt> [outdir]
  pages.txt: one line per page: <sheet>\t<page url>
"""
import json
import os
import re
import subprocess
import sys
import time

UA = 'AWI-research/1.0 (+https://www.awi.de)'
PAUSE = 5


def curl(args, timeout=900):
    r = subprocess.run(['curl', '-sS', '-L', '-A', UA, '--retry', '3', '--max-time', str(timeout)] + args,
                       capture_output=True)
    return r


def size_of(url):
    h = curl(['-I', url], 120).stdout.decode('latin1')
    cl = [int(m) for m in re.findall(r'(?im)^content-length:\s*(\d+)', h)]
    code = re.findall(r'(?m)^HTTP/\S+\s+(\d+)', h)
    return (cl[-1] if cl else None), (code[-1] if code else None)


def main():
    pages = [l.rstrip('\n').split('\t') for l in open(sys.argv[1], encoding='utf-8') if l.strip()]
    out = sys.argv[2] if len(sys.argv) > 2 else '/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga'
    os.makedirs(out, exist_ok=True)
    manpath = f'{out}/MANIFEST.json'
    man = json.load(open(manpath)) if os.path.exists(manpath) else {}
    for sheet, url in pages:
        if man.get(url, {}).get('done'):
            continue
        html = curl([url], 180).stdout.decode('utf-8', 'ignore')
        time.sleep(PAUSE)
        files = sorted(set(re.findall(r'href="(https://www\.geokniga\.org/[^"]*?maps/additional/[^"]+\.pdf)"', html)))
        files += sorted(set(u for u in re.findall(r'href="(https://www\.geokniga\.org/sites/geokniga/files/maps/[^"]+\.(?:jpg|jpeg|png|tif|tiff))"', html)
                            if 'imagecache' not in u))
        files = [re.sub(r'/sites/geokniga/\.\./\.\./', '/', f) for f in files]
        title = (re.search(r'<title>([^<]*)', html) or [None, ''])[1]
        rec = {'sheet': sheet, 'title': title.strip(), 'files': [], 'done': False}
        d = f'{out}/{re.sub(r"[^A-Za-z0-9,._-]", "_", sheet)}'
        os.makedirs(d, exist_ok=True)
        ok = bool(files)
        for f in files:
            exp, code = size_of(f)
            time.sleep(PAUSE)
            dst = f'{d}/{os.path.basename(f)}'
            if not (os.path.exists(dst) and exp and os.path.getsize(dst) == exp):
                r = curl(['-o', dst, f])
                time.sleep(PAUSE)
            got = os.path.getsize(dst) if os.path.exists(dst) else -1
            good = got > 0 and (exp is None or got == exp)
            ok &= good
            rec['files'].append({'url': f, 'bytes': got, 'content_length': exp, 'http': code, 'ok': good})
            print(sheet, os.path.basename(f), got, exp, 'OK' if good else 'BAD', flush=True)
        rec['done'] = ok
        man[url] = rec
        json.dump(man, open(manpath, 'w'), indent=1, ensure_ascii=False)
        if not files:
            print(sheet, 'NO FILE LINKS on page', url, flush=True)
    n_ok = sum(1 for v in man.values() if v['done'])
    print(f'pages done {n_ok}/{len(pages)}; bytes {sum(f["bytes"] for v in man.values() for f in v["files"] if f["bytes"]>0)/1e6:.0f} MB')


if __name__ == '__main__':
    main()
