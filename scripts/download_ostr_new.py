"""Download the files of the 407 surficial maps found by the OSTR census and missing from the
GSC index (sources/canada_ostr_new_files.json; Hugues approved 2026-09-30, Tuk/Delta set
first then the rest, ~29.7 GB, Open Government Licence - Canada). One request at a time,
resumable (a file whose size matches is skipped), logged. Destination (scratch):
raw/canada/ostr_new/<geoscan>/<file>. Verification is by manifest (path + byte count).
usage: download_ostr_new.py [tuk|rest|all]"""
import json
import os
import sys
import time
import urllib.request

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
DEST = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/ostr_new'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
which = sys.argv[1] if len(sys.argv) > 1 else 'all'
items = json.load(open(f'{ROOT}/sources/canada_ostr_new_files.json', encoding='utf-8'))
sel = [(g, f) for g, v in sorted(items.items(), key=lambda t: (not t[1]['tuk_delta'], t[1]['scale']))
       if which == 'all' or (which == 'tuk') == v['tuk_delta']
       for f in v['files'] if 'url' in f]
print('files', len(sel), 'GB', round(sum(f['bytes'] for _, f in sel) / 1e9, 2), flush=True)
done, skipped, failed = 0, 0, []
t0 = time.time()
for i, (g, f) in enumerate(sel):
    d = f'{DEST}/{g}'
    os.makedirs(d, exist_ok=True)
    out = f'{d}/{f["name"]}'
    if os.path.exists(out) and os.path.getsize(out) == f['bytes']:
        skipped += 1
        continue
    for attempt in range(3):
        try:
            req = urllib.request.Request(f['url'], headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=300) as r, open(out + '.part', 'wb') as w:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    w.write(b)
            os.replace(out + '.part', out)
            if os.path.getsize(out) != f['bytes']:
                raise IOError(f'size {os.path.getsize(out)} != {f["bytes"]}')
            done += 1
            break
        except Exception as e:
            print('retry', attempt, g, f['name'], str(e)[:120], flush=True)
            time.sleep(10 * (attempt + 1))
    else:
        failed.append(f'{g}/{f["name"]}')
    if i % 20 == 0:
        print(i, len(sel), f'{time.time() - t0:.0f}s', 'done', done, 'skipped', skipped, 'failed', len(failed), flush=True)
    time.sleep(0.5)
bad = [f'{g}/{f["name"]}' for g, f in sel
       if not (os.path.exists(f'{DEST}/{g}/{f["name"]}') and os.path.getsize(f'{DEST}/{g}/{f["name"]}') == f['bytes'])]
print('FINISHED done', done, 'skipped', skipped, 'failed', len(failed), '| manifest mismatches', len(bad), bad[:10])
sys.exit(1 if bad else 0)
