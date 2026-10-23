"""Download the scans of the 315 legacy GSC surficial sheets that have no vector data
(sources/canada_legacy_scans_selected.json: JPEG2000 where available, else PDF, else the
zip). One request at a time, resumable (a file whose size matches is skipped), logged.
Destination: raw/canada/gsc_scans/<label>/<file>. Verification is by manifest: every
selected file must end with the expected byte count."""
import json
import os
import sys
import time
import urllib.request

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SEL = json.load(open(f'{ROOT}/sources/canada_legacy_scans_selected.json', encoding='utf-8'))
DEST = f'{ROOT}/raw/canada/gsc_scans'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
done, skipped, failed = 0, 0, []
t0 = time.time()
for i, f in enumerate(SEL):
    d = f'{DEST}/{f["label"]}'
    os.makedirs(d, exist_ok=True)
    out = f'{d}/{f["name"]}'
    if os.path.exists(out) and f['bytes'] and os.path.getsize(out) == f['bytes']:
        skipped += 1
        continue
    for attempt in range(3):
        try:
            req = urllib.request.Request(f['href'], headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=300) as r, open(out + '.part', 'wb') as w:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    w.write(b)
            os.replace(out + '.part', out)
            if f['bytes'] and os.path.getsize(out) != f['bytes']:
                raise IOError(f'size {os.path.getsize(out)} != {f["bytes"]}')
            done += 1
            break
        except Exception as e:
            print('retry', attempt, f['label'], f['name'], str(e)[:120], flush=True)
            time.sleep(10 * (attempt + 1))
    else:
        failed.append(f['name'])
    if i % 20 == 0:
        print(i, len(SEL), f'{time.time() - t0:.0f}s', 'done', done, 'skipped', skipped, 'failed', len(failed), flush=True)
    time.sleep(0.5)
# manifest check
bad = [f['name'] for f in SEL if not (os.path.exists(f'{DEST}/{f["label"]}/{f["name"]}')
       and (not f['bytes'] or os.path.getsize(f'{DEST}/{f["label"]}/{f["name"]}') == f['bytes']))]
print('FINISHED done', done, 'skipped', skipped, 'failed', len(failed), '| manifest mismatches', len(bad), bad[:10])
sys.exit(1 if bad else 0)
