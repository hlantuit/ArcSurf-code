"""Provincial / regional surficial products for the permafrost domain outside AMAP (Hugues
asked 2026-09-30 to download the permafrost-region tiles on the HPC). Sources checked by HEAD
from Albedo; open licences (CC-BY 4.0 Quebec, OGL-Alberta, Sask. unrestricted use, OGS terms,
OGL-Yukon). One request at a time, resumable, size-checked against Content-Length.
Destination: raw/canada/domain_prov/<file>."""
import os
import subprocess
import sys

DST = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/domain_prov'
UA = 'AWI-research/1.0 (+https://www.awi.de)'
FILES = {
    'qc_DEP_CN_GDB.zip': 'https://diffusion.mffp.gouv.qc.ca/Diffusion/DonneeGratuite/Foret/DONNEES_FOR_ECO_NORD/Depots_surface_Nord/02-Donnees/PROV/DEP_CN_GDB.zip',
    'ab_DIG_2013_0001.zip': 'https://static.ags.aer.ca/files/document/DIG/DIG_2013_0001.zip',
    'sk_250k_surficial_shp.zip': 'https://geohub.saskatchewan.ca/api/download/v1/items/9f6fe7422fc545a485d4a3254cff585c/shapefile?layers=1',
    'on_fnpmp_2021.zip': 'https://www.geologyontario.mines.gov.on.ca/mmd/mines/data/fnpmp/fnpmp_2021.zip',
    'yt_Surficial_Geology_Polygon_2026-09-29.fgdb.zip': 'https://map-data.service.yukon.ca/GeoYukon/Geological/Surficial_Geology_Polygon/Surficial_Geology_Polygon.fgdb.zip',
}
os.makedirs(DST, exist_ok=True)
bad = []
for name, url in FILES.items():
    out = f'{DST}/{name}'
    h = subprocess.run(['curl', '-sSIL', '-A', UA, '--max-time', '120', url], capture_output=True, text=True).stdout
    size = [int(l.split(':')[1]) for l in h.splitlines() if l.lower().startswith('content-length')]
    size = size[-1] if size else None
    if os.path.exists(out) and size and os.path.getsize(out) == size:
        print('skip', name); continue
    r = subprocess.run(['curl', '-sS', '-L', '-A', UA, '--retry', '3', '--max-time', '7200', '-o', out + '.part', url])
    if r.returncode == 0:
        os.replace(out + '.part', out)
    got = os.path.getsize(out) if os.path.exists(out) else -1
    ok = r.returncode == 0 and (size is None or got == size)
    print(name, 'bytes', got, 'expected', size, 'OK' if ok else 'FAIL', flush=True)
    if not ok:
        bad.append(name)
print('FINISHED failures', bad)
sys.exit(1 if bad else 0)
