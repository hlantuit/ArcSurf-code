"""Census of geokniga 1:1M Quaternary maps (2nd AND 3rd generation), from the label page
'Карта четвертичных отложений' (/taxonomy/term/1193/0, ~115 pages; it also lists
'образований', Plio-/Neogene-Quaternary maps). The 1:200k census missed them (map table
filtered to 1:200k). Metadata only, one request every 3 s. A title is 1:1M when its
nomenclature has no Roman-numeral 1:200k part: R-(40)-42, R-45-(47), Q-60,1, R-52, S-47.
Generation: 'Третье поколение' / '(третье поколение)' in the title -> 3, else 2 ('Новая
серия', 'СССР'). Writes sources/geokniga_q1000.json and prints the Arctic rows (P-U)."""
import html
import json
import sys
import re
import subprocess
import time

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
UA = 'AWI-research/1.0 (+https://www.awi.de)'


def get(url):
    for _ in range(3):
        r = subprocess.run(['curl', '-sS', '-L', '-A', UA, '--http1.1', '--max-time', '120', url], capture_output=True)
        time.sleep(3)
        h = r.stdout.decode('utf-8', 'replace')
        if '/maps/' in h:
            return h
    return h


items, page = {}, 0
while True:
    h = get(f'https://www.geokniga.org/taxonomy/term/1193/0?page={page}')
    for u, t in re.findall(r'<a href="(/maps/\d+)"[^>]*>([^<]+)</a>', h):
        items[u] = html.unescape(t).strip()
    last = max([int(x) for x in re.findall(r'page=(\d+)', h)] + [0])
    print('page', page, '/', last, 'items', len(items), flush=True)
    if page >= last:
        break
    page += 1

# every label item at every scale (used to resolve 1:200k pages without series links)
json.dump([dict(url='https://www.geokniga.org' + u, title=t) for u, t in items.items()],
          open(f'{ROOT}/sources/geokniga_quat_label_all.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
if len(sys.argv) > 1 and sys.argv[1] == 'all_only':
    sys.exit(0)
NOM = re.compile(r'^\s*([A-U])-\(?(\d{1,2})\)?((?:\s*[-,;]\s*\(?\d{1,2}\)?)*)(?![-\s]*[IVX])')
out = []
for u, t in items.items():
    head = re.split(r'[.(]\s*(?:Государств|Геологическ)', t)[0]
    if re.search(r'-[IVX]', head.split('(')[0] if '(' in head else head):
        continue                                                  # 1:200k nomenclature
    m = NOM.match(t)
    if not m:
        continue
    row = m.group(1)
    nums = [int(x) for x in re.findall(r'\d{1,2}', m.group(2) + m.group(3))]
    gen = 3 if re.search(r'трет\w* поколен', t, re.I) else 2
    out.append(dict(url='https://www.geokniga.org' + u, title=t, row=row, cols=nums, gen=gen))
json.dump(out, open(f'{ROOT}/sources/geokniga_q1000.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('label items', len(items), '| 1:1M', len(out), '| gen2', sum(x['gen'] == 2 for x in out), '| gen3', sum(x['gen'] == 3 for x in out))
for x in sorted(out, key=lambda x: (x['row'], x['cols'])):
    if x['row'] in 'PQRSTU':
        print(f"  gen{x['gen']} {x['row']}-{x['cols']}  {x['title'][:120]}  {x['url']}")
