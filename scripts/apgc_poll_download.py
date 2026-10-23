"""Poll the AWI APGC catalogue (down with 502 on 2026-09-30) and, once it answers, download
the georectified GeoTIFF scans of the Bryant et al. Siberian Quaternary database
(dataset quaternary-deposits-maps-siberia). Runs locally (Albedo cannot reach apgc.awi.de).
Checks every 20 min for up to 24 h; one download at a time; size checked against
Content-Length. Writes to raw_bryant_scans/ next to the project."""
import json
import os
import sys
import time
import urllib.request

API = 'https://apgc.awi.de/api/3/action/package_show?id=quaternary-deposits-maps-siberia'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
DEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'raw_bryant_scans')
os.makedirs(DEST, exist_ok=True)


def get(url, timeout=60):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=timeout)


t0 = time.time()
while time.time() - t0 < 24 * 3600:
    try:
        d = json.load(get(API))['result']
        break
    except Exception as e:
        print(time.strftime('%H:%M'), 'APGC not available:', str(e)[:80], flush=True)
        time.sleep(1200)
else:
    sys.exit('APGC still unavailable after 24 h')
print('licence:', d.get('license_title'), d.get('license_id'), flush=True)
res = d['resources']
for r in res:
    print('resource:', r.get('name'), '|', r.get('format'), '|', r.get('url'), flush=True)
pick = [r for r in res if 'tif' in (str(r.get('format')) + str(r.get('name')) + str(r.get('url'))).lower()
        or 'scan' in (str(r.get('name')) + str(r.get('description'))).lower()]
json.dump(d, open(os.path.join(DEST, 'apgc_record.json'), 'w'), indent=1)
for r in pick:
    url = r['url']
    out = os.path.join(DEST, url.rstrip('/').split('/')[-1] or r['id'])
    with get(url, timeout=600) as resp, open(out + '.part', 'wb') as w:
        n = int(resp.headers.get('Content-Length') or 0)
        while True:
            b = resp.read(1 << 20)
            if not b:
                break
            w.write(b)
    os.replace(out + '.part', out)
    sz = os.path.getsize(out)
    print('downloaded', out, sz, 'bytes', 'OK' if (not n or n == sz) else f'SIZE MISMATCH (expected {n})', flush=True)
print('DONE', len(pick), 'files')
