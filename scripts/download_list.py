#!/usr/bin/env python
"""
Generic size-checked downloader.

usage: download_list.py <region> <list.json>
  list.json = [{"src": ..., "url": ...}, ...]; files land in
  /albedo/scratch/user/hlantuit/arctic_surficial/raw/<region>/<src>/<basename>
Each file is checked against Content-Length (when sent) and, for zips, by testzip;
tar.gz by a full listing. Writes MANIFEST.json (path, bytes, check) and exits
non-zero if anything failed.
"""
import json
import os
import re
import subprocess
import sys
import tarfile
import zipfile

UA = 'AWI-research/1.0 (+https://www.awi.de)'


def fetch(url, out):
    hdr = subprocess.run(['curl', '-sIL', '--max-time', '60', '-A', UA, url],
                         capture_output=True, text=True).stdout
    cl = [int(m) for m in re.findall(r'(?im)^content-length:\s*(\d+)', hdr)]
    exp = cl[-1] if cl and cl[-1] > 0 else None
    if not (os.path.exists(out) and exp and os.path.getsize(out) == exp):
        r = subprocess.run(['curl', '-sSL', '--retry', '5', '--max-time', '7200', '-A', UA, '-o', out, url])
        if r.returncode:
            raise RuntimeError(f'curl rc {r.returncode}')
    got = os.path.getsize(out)
    if exp and got != exp:
        raise RuntimeError(f'size expected {exp} got {got}')
    if out.endswith('.zip'):
        with zipfile.ZipFile(out) as z:
            bad = z.testzip()
            assert bad is None, f'bad member {bad}'
        chk = 'zip_ok'
    elif out.endswith(('.tar.gz', '.tgz')):
        with tarfile.open(out) as t:
            t.getmembers()
        chk = 'tar_ok'
    else:
        chk = 'size_only'
    return got, exp, chk


def main():
    region, lst = sys.argv[1], json.load(open(sys.argv[2]))
    root = f'/albedo/scratch/user/hlantuit/arctic_surficial/raw/{region}'
    man, fails = [], []
    for it in lst:
        d = f'{root}/{it["src"]}'
        os.makedirs(d, exist_ok=True)
        out = f'{d}/{os.path.basename(it["url"].split("?")[0])}'
        try:
            got, exp, chk = fetch(it['url'], out)
            man.append({'src': it['src'], 'file': out, 'bytes': got, 'content_length': exp, 'check': chk})
            print('ok', got, chk, out, flush=True)
        except Exception as e:
            fails.append({'src': it['src'], 'url': it['url'], 'error': repr(e)[:300]})
            print('FAIL', it['url'], repr(e)[:300], flush=True)
    json.dump({'files': man, 'failures': fails}, open(f'{root}/MANIFEST.json', 'w'), indent=1)
    print(f'{len(man)} ok, {len(fails)} failed; {sum(m["bytes"] for m in man)/1e9:.2f} GB')
    sys.exit(1 if fails else 0)


if __name__ == '__main__':
    main()
