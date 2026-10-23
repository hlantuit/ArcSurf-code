"""Inventory (metadata only, no downloads) of the scan files of the 315 legacy GSC surficial
sheets that have no vector data: per sheet, the PDF / JPEG2000 bitstreams with sizes, from
the OSTR DSpace REST API (same route as download_canada.py). Polite: one request at a time.
Writes sources/canada_legacy_scans.json and prints totals."""
import json
import sys
import time
import urllib.request

API = 'https://ostr-backend-prod.azure.cloud.nrcan-rncan.gc.ca/server/api'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
SRC = sys.argv[1]
OUT = sys.argv[2]


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


sheets = json.load(open(SRC, encoding='utf-8'))['sheets']
todo = [x for x in sheets if not x['label'].startswith('CGM') and not x['vector'] and x.get('ostr_uuid')]
res = []
for i, x in enumerate(todo):
    try:
        b = get(f'{API}/core/items/{x["ostr_uuid"]}/bundles?embed=bitstreams')
        files = []
        for bd in b['_embedded']['bundles']:
            if bd['name'] != 'ORIGINAL':
                continue
            for bs in bd['_embedded']['bitstreams']['_embedded']['bitstreams']:
                files.append(dict(name=bs['name'], bytes=bs.get('sizeBytes'),
                                  href=bs['_links']['content']['href']))
        res.append(dict(label=x['label'], title=x['title'], scale=x['scale'], release=x.get('release'),
                        bbox=x.get('bbox_wgs84'), files=files))
    except Exception as e:
        res.append(dict(label=x['label'], error=str(e)[:200]))
    if i % 25 == 0:
        print(i, len(todo), flush=True)
    time.sleep(0.5)
json.dump(res, open(OUT, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
ext = lambda n: n.rsplit('.', 1)[-1].lower() if '.' in n else ''   # noqa: E731
tot = {}
for r in res:
    for f in r.get('files', []):
        e = ext(f['name'])
        tot.setdefault(e, [0, 0])
        tot[e][0] += 1
        tot[e][1] += f['bytes'] or 0
print('errors', sum('error' in r for r in res), '| per type (n, GB):', {k: (v[0], round(v[1] / 1e9, 1)) for k, v in sorted(tot.items(), key=lambda kv: -kv[1][1])})
