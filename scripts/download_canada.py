#!/usr/bin/env python
"""
Canada harvest -> /albedo/scratch/user/hlantuit/arctic_surficial/raw/canada

1. GSC detailed sheets with vector data (331 of 650 Arctic index sheets; list from
   sources/canada_gsc_sheets.json, built via the OSTR DSpace API). The zips are
   mostly PDF/MXD/JPEG2000, so only the vector members are pulled, by HTTP range
   requests against the zip central directory (RangeFile below). Legacy A-series /
   Open File sheets also keep their PDFs: their legend codes are only decoded there.
   A per-sheet manifest records every member extracted with its CRC-checked size.
2. Seamless/provincial products: GSC index + 1:5M, Yukon compilation, Québec
   SIGÉOM Quaternary, Manitoba SGCMS + legend model, Ontario EDS014.
3. Labrador GeoAtlas layers 11 (detailed) and 12 (regional) paged out of the
   ArcGIS MapServer query endpoint as GeoJSON (maxRecordCount 1000).

usage: download_canada.py [--workers 6] [--only gsc|prov|lab]
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

DST = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada'
SHEETS = '/albedo/work/user/hlantuit/arctic_surficial/sources/canada_gsc_sheets.json'
UA = {'User-Agent': 'AWI-research/1.0 (+https://www.awi.de)'}
VEC_EXT = ('.gdbtable', '.gdbtablx', '.gdbindexes', '.atx', '.spx', '.freelist', '.horizon',
           '.shp', '.shx', '.dbf', '.prj', '.cpg', '.sbn', '.sbx', '.e00', '.xml', '.xls',
           '.xlsx', '.csv', '.txt', '.gpkg')
PROV = {
    'gsc_surficial_geology.gdb.zip': 'https://ftp.maps.canada.ca/pub/nrcan_rncan/Surficial-geology_Geologie-des-depots-meubles/surficial_geology_index_geologie_surface/gsc_surficial_geology.gdb.zip',
    'Surficial_Geology_Polygon.fgdb.zip': 'https://map-data.service.yukon.ca/GeoYukon/Geological/Surficial_Geology_Polygon/Surficial_Geology_Polygon.fgdb.zip',
    'SIGEOM_QC_Geologie_du_Quaternaire_GPKG.zip': 'https://gq.mines.gouv.qc.ca/documents/SIGEOM/TOUTQC/FRA/GPKG/SIGEOM_QC_Geologie_du_Quaternaire_GPKG.zip',
    'SGCMS_1_1Million_2017.zip': 'https://www.manitoba.ca/iem/geo/gis/sgcms/esri/SGCMS_1_1Million_2017.zip',
    'sgcms_legend_datamodel.zip': 'https://www.manitoba.ca/iem/geo/gis/sgcms_legend_datamodel.zip',
    'EDS014-REV.zip': 'https://prd-0420-geoontario-0000-blob-cge0eud7azhvfsf7.z01.azurefd.net/lrc-geology-documents/publication/EDS014-REV/EDS014-REV.zip',
}
LAB = 'https://dnrmaps.gov.nl.ca/arcgis/rest/services/GeoAtlas/Surficial_Geology_All/MapServer'


class RangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP Range requests (enough for zipfile)."""

    def __init__(self, url, size):
        self.url, self.size, self.pos, self.fetched = url, size, 0, 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        for attempt in range(6):
            try:
                req = urllib.request.Request(self.url, headers={**UA, 'Range': f'bytes={self.pos}-{end}'})
                with urllib.request.urlopen(req, timeout=300) as r:
                    if r.status != 206:
                        raise IOError(f'no range support (HTTP {r.status})')
                    data = r.read()
                break
            except IOError:
                if attempt == 5:
                    raise
                time.sleep(5 * (attempt + 1))
        n = len(data)
        b[:n] = data
        self.pos += n
        self.fetched += n
        return n


def want(member, legacy):
    m = member.lower()
    if m.endswith('/'):
        return False
    if '.gdb/' in m:
        return True
    if m.endswith(VEC_EXT) and not m.endswith(('.mxd', '.lyr')):
        return True
    return legacy and m.endswith('.pdf')


def fetch_sheet(sh):
    label = re.sub(r'[^A-Za-z0-9_.-]', '_', sh['label'])
    out = f'{DST}/gsc/{label}'
    done = f'{out}/_MANIFEST.json'
    if os.path.exists(done):
        return label, 'cached', 0
    os.makedirs(out, exist_ok=True)
    legacy = not label.upper().startswith('CGM')
    fetched, rec = 0, []
    for z in sh['zips']:
        rf = RangeFile(z['url'], z['bytes'])
        with zipfile.ZipFile(io.BufferedReader(rf, buffer_size=1 << 20)) as zf:
            for info in zf.infolist():
                if not want(info.filename, legacy):
                    continue
                dest = os.path.join(out, info.filename)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(info) as src, open(dest, 'wb') as dst:   # CRC checked by zipfile
                    while True:
                        chunk = src.read(1 << 22)
                        if not chunk:
                            break
                        dst.write(chunk)
                assert os.path.getsize(dest) == info.file_size, dest
                rec.append({'member': info.filename, 'bytes': info.file_size})
        fetched += rf.fetched
    meta = {k: sh[k] for k in ('geoscan', 'label', 'title', 'tier_from_title', 'scale', 'release',
                               'bbox_wgs84', 'ostr_filetypes', 'ostr_uuid')}
    meta.update(zips=sh['zips'], members=rec, bytes_fetched=fetched)
    json.dump(meta, open(done, 'w'), indent=1)
    return label, f'ok members={len(rec)}', fetched


def curl(url, out):
    hdr = subprocess.run(['curl', '-sIL', '--max-time', '60', '-A', UA['User-Agent'], url],
                         capture_output=True, text=True).stdout
    cl = [int(m) for m in re.findall(r'(?im)^content-length:\s*(\d+)', hdr)]
    exp = cl[-1] if cl and cl[-1] > 0 else None
    if os.path.exists(out) and exp and os.path.getsize(out) == exp:
        return 'cached', exp
    r = subprocess.run(['curl', '-sSL', '--retry', '5', '--max-time', '7200', '-A', UA['User-Agent'],
                        '-o', out, url])
    got = os.path.getsize(out) if os.path.exists(out) else -1
    if r.returncode or (exp and got != exp):
        raise RuntimeError(f'{out}: curl rc {r.returncode}, expected {exp} got {got}')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None, out
    return 'downloaded', got


def page_layer(layer, out):
    """Page an ArcGIS MapServer layer to one GeoJSON FeatureCollection (native SR)."""
    q = f'{LAB}/{layer}/query'

    def get(params):
        # the GeoAtlas server answers HTTP 500 to urllib's default 'Python-urllib'
        # user agent (and 200 to anything else), so the UA header is REQUIRED here
        for attempt in range(6):
            try:
                req = urllib.request.Request(f'{q}?{urllib.parse.urlencode(params)}', headers=UA)
                return json.load(urllib.request.urlopen(req, timeout=300))
            except Exception:
                time.sleep(10 * (attempt + 1))
        raise RuntimeError(f'layer {layer} query failed: {params}')

    # page by OBJECTID ranges up to max(OBJECTID); returnIdsOnly (97k ids) keeps
    # failing on this server, while count and max statistics are cheap
    n = get({'where': '1=1', 'returnCountOnly': 'true', 'f': 'json'})['count']
    stat = json.dumps([{'statisticType': 'max', 'onStatisticField': 'OBJECTID', 'outStatisticFieldName': 'mx'}])
    mx = int(get({'where': '1=1', 'outStatistics': stat, 'f': 'json'})['features'][0]['attributes']['mx'])
    feats = []

    def fetch_range(lo, hi):
        """Heavy polygons make some 1000-record pages fail server-side (error JSON,
        no 'features'): split the range in half until it succeeds."""
        fc = get({'where': f'OBJECTID>={lo} AND OBJECTID<={hi}', 'outFields': '*', 'f': 'geojson'})
        if 'features' in fc:
            return fc['features']
        if hi == lo:
            skipped.append(lo)          # the server cannot serve this object at all
            return []
        mid = (lo + hi) // 2
        return fetch_range(lo, mid) + fetch_range(mid + 1, hi)

    skipped = []
    for lo in range(1, mx + 1, 1000):
        feats += fetch_range(lo, lo + 999)
    # object ids may have gaps: a skipped id may not exist at all; count what exists
    json.dump({'layer': layer, 'server_failed_ids': skipped, 'count_reported': n, 'got': len(feats)},
              open(out.replace('.geojson', '_skipped.json'), 'w'))
    assert len(feats) + len(skipped) >= n, f'layer {layer}: got {len(feats)} + {len(skipped)} skipped of {n}'
    json.dump({'type': 'FeatureCollection', 'features': feats}, open(out, 'w'))
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=6)
    ap.add_argument('--only')
    a = ap.parse_args()
    os.makedirs(f'{DST}/gsc', exist_ok=True)
    if a.only in (None, 'prov'):
        for name, url in PROV.items():
            print(name, *curl(url, f'{DST}/{name}'), flush=True)
    if a.only in (None, 'gsc'):
        sheets = [s for s in json.load(open(SHEETS))['sheets'] if s['vector'] and s['zips']]
        tot_zip = sum(z['bytes'] for s in sheets for z in s['zips'])
        print(f'{len(sheets)} vector sheets, {tot_zip/1e9:.1f} GB of zips', flush=True)
        got, fails = 0, []
        with ThreadPoolExecutor(a.workers) as ex:
            futs = {ex.submit(fetch_sheet, s): s['label'] for s in sheets}
            for i, f in enumerate(as_completed(futs)):
                try:
                    label, msg, n = f.result()
                    got += n
                    print(i, label, msg, f'{n/1e6:.1f} MB', flush=True)
                except Exception as e:
                    fails.append((futs[f], repr(e)[:300]))
                    print(i, futs[f], 'FAIL', repr(e)[:300], flush=True)
        print(f'fetched {got/1e9:.2f} GB of {tot_zip/1e9:.1f} GB; failures {len(fails)}')
        json.dump(fails, open(f'{DST}/gsc_failures.json', 'w'), indent=1)
    if a.only in (None, 'lab'):
        # last and non-fatal: the GeoAtlas count query has returned HTTP 500
        for layer in (11, 12):
            try:
                print('labrador layer', layer, page_layer(layer, f'{DST}/labrador_layer{layer}.geojson'), flush=True)
            except Exception as e:
                print('labrador layer', layer, 'FAILED', repr(e)[:300], flush=True)
    print('DONE')


if __name__ == '__main__':
    main()
