"""Census of NRCan OSTR items that are surficial / Quaternary / terrain / geomorphology
MAPS inside the Arctic domain (AMAP + Obu permafrost; Canada = north of 54N here as a
coarse prefilter, then the domain polygon), compared with the 650-sheet inventory built
from the GSC surficial index (sources/canada_gsc_sheets.json), which missed many maps
(e.g. Tuktoyaktuk Peninsula 1:250k 1987, Mackenzie Delta 1:250k 1981/1987, Tuktoyaktuk
1:25k 1975). Metadata only; one request at a time.
Writes sources/canada_ostr_census.json and prints the new items by scale."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

API = 'https://ostr-backend-prod.azure.cloud.nrcan-rncan.gc.ca/server/api'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
QUERIES = ['surficial geology', 'surficial materials', 'Quaternary geology', 'terrain classification',
           'terrain sensitivity', 'surficial deposits map', 'landforms map', 'geomorphic feature mapping',
           'permafrost terrain map', 'glacial geology map', 'surficial geology and landforms', 'terrain inventory']


def get(url):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=90))
        except Exception as e:
            time.sleep(5 * (i + 1)); err = e
    raise err


inv = {str(x['geoscan']) for x in json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']}
CK = f'{ROOT}/work/ostr_census_ck.json'           # checkpoint per finished query (resume)
try:
    ck = json.load(open(CK, encoding='utf-8')); seen, done = ck['seen'], set(ck['done'])
except FileNotFoundError:
    seen, done = {}, set()
for q in QUERIES:
    if q in done:
        continue
    page = 0
    while True:
        url = f'{API}/discover/search/objects?' + urllib.parse.urlencode(dict(query=q, dsoType='ITEM', size=100, page=page))
        d = get(url)
        sr = d['_embedded']['searchResult']
        objs = sr['_embedded']['objects']
        for o in objs:
            it = o['_embedded']['indexableObject']; m = it['metadata']
            g = lambda k: (m.get(k) or [{}])[0].get('value', '')   # noqa: E731
            gid = g('dc.identifier.gid')
            if not gid or gid in seen:
                continue
            bbox = g('geospatial.bbox')
            seen[gid] = dict(geoscan=gid, uuid=it['uuid'], title=g('dc.title'), map=g('nrcan.map'), year=g('dc.date.issued')[:4],
                             filetype=g('nrcan.filetype'), bbox=bbox, in_inventory=gid in inv)
        tot = sr['page']['totalPages']
        print(q, 'page', page + 1, '/', tot, 'items', len(seen), flush=True)
        page += 1
        if page >= min(tot, 40):
            break
        time.sleep(1)
    done.add(q)
    json.dump(dict(seen=seen, done=sorted(done)), open(CK, 'w', encoding='utf-8'))


def parse_bbox(s):
    nums = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', s or '')]
    return nums[:4] if len(nums) >= 4 else None


keep = []
for x in seen.values():
    mp = (x['map'] or '').lower()
    if not re.search(r'surficial|quaternary|terrain|geomorph|landform|glacial|permafrost', mp + ' ' + x['title'].lower()):
        continue
    if not re.search(r'\d:\d', mp):                      # a MAP (has a scale), not a report
        continue
    b = parse_bbox(x['bbox'])
    x['bbox_n'] = b
    if b:
        lats = [v for v in b if -90 <= v <= 90]
        # OSTR bbox order varies; accept if any latitude-like corner is >= 54N and a longitude is in Canada
        lons = [v for v in b if v < -50]
        if not lons or max(v for v in b if 40 <= abs(v) <= 90) < 54:
            continue
    m = re.search(r'1:\s*([\d ,]+)', mp)
    x['scale'] = int(re.sub(r'\D', '', m.group(1))) if m else None
    keep.append(x)
json.dump(keep, open(f'{ROOT}/sources/canada_ostr_census.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
new = [x for x in keep if not x['in_inventory']]
print('surficial-type maps north of 54N:', len(keep), '| already in inventory:', len(keep) - len(new), '| NEW:', len(new))
import collections  # noqa: E402
print('new by scale:', sorted(collections.Counter(x['scale'] for x in new).items(), key=lambda t: (t[0] is None, t[0] or 0)))
for x in sorted(new, key=lambda x: (x['scale'] or 9e9))[:60]:
    print(f"  {x['geoscan']:>7} 1:{x['scale'] or '?':<8} {x['year']} {x['filetype'][:25]:25s} {x['title'][:90]}")
