"""List an OSTR (NRCan DSpace) record and its files without downloading: metadata (DOI, GID, date, citation)
and every bitstream with its size. usage: ostr_item_files.py <handle e.g. 1845/180864 | item uuid>"""
import json
import subprocess
import sys

UA = 'AWI-research/1.0 (+https://www.awi.de)'
B = 'https://ostr-backend-prod.azure.cloud.nrcan-rncan.gc.ca/server/api'


def get(url):
    return json.loads(subprocess.run(['curl', '-sS', '-L', '-A', UA, url], capture_output=True, text=True).stdout)


ref = sys.argv[1]
d = get(f'{B}/pid/find?id={ref}') if '/' in ref else get(f'{B}/core/items/{ref}')
print('uuid', d.get('uuid'), '|', d.get('name'))
md = d.get('metadata', {})
for k in sorted(md):
    if any(s in k for s in ('doi', 'identifier.gid', 'date.issued', 'citation', 'series', 'relation.haspart', 'relation.ispartof')):
        for v in md[k][:4]:
            print(' ', k, '=', str(v.get('value'))[:240])
u = d.get('uuid')
for bd in get(f'{B}/core/items/{u}/bundles').get('_embedded', {}).get('bundles', []):
    for x in get(f"{B}/core/bundles/{bd['uuid']}/bitstreams?size=100").get('_embedded', {}).get('bitstreams', []):
        print(f"  [{bd['name']}] {x['name']} | {x.get('sizeBytes', 0) / 1e6:.1f} MB | {x['uuid']}")
