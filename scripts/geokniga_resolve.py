"""Resolve geokniga map-page URLs for the Quaternary 1:200k sheets of the permafrost rows
(sources/geokniga_q200_target.json, from the site's map table) by reading their series
pages (/mapgroups/N, all pages of each). Matches on the nomenclature in the link title.
Polite: one request at a time, 3 s pause. Writes sources/geokniga_q200_pages.txt
(<sheet>\t<url>, only sheets NOT already downloaded) and geokniga_q200_resolved.json."""
import html
import json
import os
import re
import subprocess
import time

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
# usage: geokniga_resolve.py [target.json tag]  (default: the 221 permafrost-row sheets)
import sys
TGT = sys.argv[1] if len(sys.argv) > 2 else f'{ROOT}/sources/geokniga_q200_target.json'
TAG = sys.argv[2] if len(sys.argv) > 2 else 'q200'
T = json.load(open(TGT, encoding='utf-8'))
HAVE = {d.replace('_', '').replace(' ', '') for d in os.listdir('/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga')}


def get(url):
    r = subprocess.run(['curl', '-sS', '-L', '-A', UA, '--retry', '3', '--max-time', '120', url], capture_output=True)
    time.sleep(3)
    return r.stdout.decode('utf-8', 'replace')


norm = lambda s: re.sub(r'\s+', '', s).upper()   # noqa: E731
links = {}
for g in sorted({t['group'] for t in T if t['group']}):
    page = 0
    while page < 30:
        h = get(f'https://www.geokniga.org{g}' + (f'?page={page}' if page else ''))
        found = re.findall(r'<a href="(/maps/\d+)"[^>]*>([^<]+)</a>', h)
        for u, title in found:
            links.setdefault(norm(html.unescape(title)), []).append((u, html.unescape(title)))
        if f'page={page + 1}' not in h:
            break
        page += 1
    print(g, 'pages', page + 1, 'links so far', len(links), flush=True)
res, lines = [], []
for t in T:
    key = norm(t['title'])
    cand = links.get(key) or [v for k, vs in links.items() if k.startswith(norm(t['nom']) + '.') or k.startswith(norm(t['nom']) + '(')
                              for v in vs if re.search(r'(?<!до)четвертичн', v[1], re.I)]
    url = ('https://www.geokniga.org' + cand[0][0]) if cand else ''
    have = norm(t['nom']).replace(',', ',') in {h.upper() for h in HAVE}
    res.append(dict(t, page=url, have=have))
    if url and not have:
        lines.append(f"{t['nom'].replace(' ', '')}\t{url}")
json.dump(res, open(f'{ROOT}/sources/geokniga_{TAG}_resolved.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
open(f'{ROOT}/sources/geokniga_{TAG}_pages.txt', 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
print('target', len(T), '| resolved', sum(1 for r in res if r['page']), '| already have', sum(r['have'] for r in res),
      '| to download', len(lines))
