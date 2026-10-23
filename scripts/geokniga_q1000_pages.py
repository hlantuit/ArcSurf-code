"""pages.txt for download_geokniga.py from sources/geokniga_q1000.json (the 1:1M Quaternary
census; Hugues approved the 1:1M download 2026-09-30). Label = nomenclature head of the title
+ '_g2'/'_g3' so the two generations of one sheet never share a folder. Arctic rows first."""
import json
import re

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
d = json.load(open(f'{ROOT}/sources/geokniga_q1000.json', encoding='utf-8'))
order = 'UTSRQPONMLKJ'
d.sort(key=lambda x: (order.find(x['row']) if x['row'] in order else 99, x['cols']))
with open(f'{ROOT}/sources/geokniga_q1000_pages.txt', 'w', encoding='utf-8') as f:
    for x in d:
        lab = re.sub(r'[^A-Za-z0-9,()\-]', '', x['title'].split(' ')[0]) + f"_g{x['gen']}"
        f.write(f"{lab}\t{x['url']}\n")
print(len(d), 'pages')
