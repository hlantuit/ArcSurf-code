"""Status report of the unattended permafrost-region build and the background downloads ->
work/DOMAIN_BUILD_STATUS.txt (read this first when coming back)."""
import glob
import json
import os
import subprocess

W = '/albedo/work/user/hlantuit/arctic_surficial/work'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw'
out = []
q = subprocess.run(['sacct', '-u', os.environ.get('USER', 'hlantuit'), '-S', 'now-5days', '-X', '-n', '-P', '-o', 'JobID,JobName,State,Elapsed,End'],
                   capture_output=True, text=True).stdout
keep = ('dom_', 'ing_', 'dl_', 'gk_', 'mk_ocr', 'triage')
out.append('== jobs (last 5 days)')
out += [l for l in q.splitlines() if any(l.split('|')[1].startswith(k) for k in keep)]
for f, lab in [('qa_merge.json', 'QA'), ]:
    try:
        out.append(f'== {lab}: ' + json.dumps(json.load(open(f'{W}/{f}')), default=str)[:1500])
    except Exception as e:
        out.append(f'== {lab}: n/a ({e})')
try:
    out.append('== coverage by country (km2)\n' + open('/albedo/work/user/hlantuit/arctic_surficial/out/coverage_by_country.csv').read())
except Exception:
    pass
try:
    errs = [l for l in open(f'{W}/merge_tiles.log') if 'ERROR' in l]
    out.append(f'== merge tile errors: {len(errs)}' + ''.join('\n  ' + e[:200] for e in errs[:10]))
except Exception:
    pass
for d in ['russia_geokniga', 'russia_geokniga_1m', 'canada/domain_prov', 'canada/ostr_new']:
    p = f'{RAW}/{d}'
    n = sum(len(fs) for _, _, fs in os.walk(p)) if os.path.exists(p) else 0
    out.append(f'== raw/{d}: {n} files')
for f in ['dl_gk1000.out', 'dl_gk200dom.out', 'dl_domain_prov.out', 'gk_match_dom.out', 'mk_ocr_env.out']:
    try:
        t = open(f'{W}/{f}').read().splitlines()
        out.append(f'== {f}: ' + ' | '.join(t[-3:])[:400])
    except Exception:
        pass
open(f'{W}/DOMAIN_BUILD_STATUS.txt', 'w').write('\n'.join(out) + '\n')
print('\n'.join(out))
