#!/usr/bin/env python
"""Second pass of geokniga_match_pages.py for targets it left unmatched: the record titles of many 2nd-edition
sheets write the nomenclature with Cyrillic look-alike letters ('М-48-IV', 'Н-...'), so the plain
whitespace-insensitive key misses them. Same index (sources/geokniga_quat_label_all.json, pre-Quaternary titles
skipped), key = nomenclature with Cyrillic homoglyphs mapped to Latin. Appends matches to <pages.txt>.
usage: geokniga_match_pages_cyr.py <target.json> <pages.txt>"""
import json
import re
import sys

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
T = json.load(open(sys.argv[1], encoding='utf-8'))
pages = sys.argv[2]
L = json.load(open(f'{ROOT}/sources/geokniga_quat_label_all.json', encoding='utf-8'))
have = {ln.split('\t')[0] for ln in open(pages, encoding='utf-8') if '\t' in ln}
CYR = str.maketrans('АВЕКМНОРСТХаеорсх', 'ABEKMHOPCTXaeopcx')


def key(s):
    return re.sub(r'\s+', '', s.translate(CYR)).upper()


idx = {}
for x in L:
    if re.search(r'дочетвертичн', x['title'], re.I):
        continue
    idx.setdefault(key(re.split(r'[.(]', x['title'])[0]), []).append((x['url'], x['title'][:80]))
add, miss = [], []
for t in T:
    if t['nom'] in have:
        continue
    hits = idx.get(key(t['nom']))
    if hits:
        add.append(t['nom'] + '\t' + hits[0][0])
        print('match', t['nom'], hits[0][0], '|', hits[0][1])
    else:
        miss.append(t['nom'])
with open(pages, 'a', encoding='utf-8') as f:
    f.write(''.join(a + '\n' for a in add))
print('added', len(add), 'still missing', miss)
