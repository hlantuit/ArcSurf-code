"""pages.txt for download_geokniga.py: match target sheets (json list with 'nom'/'title') to
geokniga map pages from sources/geokniga_quat_label_all.json by nomenclature at the start of
the title (whitespace-insensitive) and a Quaternary (not pre-Quaternary) title.
usage: geokniga_match_pages.py <target.json> <out_pages.txt>"""
import json
import re
import sys

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
T = json.load(open(sys.argv[1], encoding='utf-8'))
L = json.load(open(f'{ROOT}/sources/geokniga_quat_label_all.json', encoding='utf-8'))
norm = lambda s: re.sub(r'\s+', '', s).upper()   # noqa: E731
idx = {}
for x in L:
    if re.search(r'дочетвертичн', x['title'], re.I):
        continue
    head = norm(re.split(r'[.(]', x['title'])[0])
    idx.setdefault(head, []).append(x['url'])
out, miss = [], []
for t in T:
    k = norm(t['nom'])
    u = idx.get(k) or idx.get(k.replace(';', ','))
    (out if u else miss).append((t['nom'].replace(' ', ''), u[0] if u else ''))
open(sys.argv[2], 'w', encoding='utf-8').write(''.join(f'{n}\t{u}\n' for n, u in out))
print('targets', len(T), '| matched', len(out), '| unmatched', len(miss), [m[0] for m in miss][:30])
