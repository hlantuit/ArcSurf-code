"""File list + sizes for the items in sources/canada_ostr_new_in_domain.csv (OSTR bundles
-> bitstreams; metadata only, one request at a time). Writes
sources/canada_ostr_new_files.json and prints totals (all, Tuk/Delta window) by format."""
import json
import time
import urllib.request

import pandas as pd

API = 'https://ostr-backend-prod.azure.cloud.nrcan-rncan.gc.ca/server/api'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
ROOT = '/albedo/work/user/hlantuit/arctic_surficial'


def get(url):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=90))
        except Exception as e:
            err = e; time.sleep(5 * (i + 1))
    raise err


x = pd.read_csv(f'{ROOT}/sources/canada_ostr_new_in_domain.csv', dtype={'geoscan': str})
out = {}
for _, r in x.iterrows():
    files = []
    try:
        for b in get(f'{API}/core/items/{r.uuid}/bundles')['_embedded']['bundles']:
            if b['name'] != 'ORIGINAL':
                continue
            bs = get(b['_links']['bitstreams']['href'] + '?size=100')['_embedded']['bitstreams']
            files += [dict(name=s['name'], bytes=s['sizeBytes'], url=s['_links']['content']['href']) for s in bs]
    except Exception as e:
        files = [dict(error=str(e)[:100])]
    out[r.geoscan] = dict(title=r.title, scale=int(r.scale), year=r.year, tuk_delta=bool(r.tuk_delta), files=files)
    time.sleep(0.5)
json.dump(out, open(f'{ROOT}/sources/canada_ostr_new_files.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
rows = [dict(geoscan=g, tuk=v['tuk_delta'], ext=f['name'].rsplit('.', 1)[-1].lower(), mb=f['bytes'] / 1e6)
        for g, v in out.items() for f in v['files'] if 'bytes' in f]
d = pd.DataFrame(rows)
print('items', len(out), 'files', len(d), 'GB', round(d.mb.sum() / 1e3, 2))
print(d.groupby('ext').mb.agg(['count', 'sum']).round(0).sort_values('sum', ascending=False).to_string())
print('Tuk/Delta:', d[d.tuk].groupby('geoscan').mb.sum().round(1).to_dict())
