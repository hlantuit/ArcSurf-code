#!/usr/bin/env python
"""ArcSurf v1.0 release as one GeoPackage per geometry. PANGAEA takes files of less than 15 GB, and the export of
export_release.py holds both geometries in one file of 37 GB (release geometry 14.5 GB, tiled geometry 22.5 GB with
their spatial indexes). Each output is a copy of that file with the other layer deleted by GDAL (which also removes
its spatial index, triggers and GeoPackage metadata), written compactly by VACUUM INTO, so feature ids, rows and layer
metadata stay those of the export; the tiled geometry is then zipped. Checks: GeoPackage application id and version as
in the export; for each layer, the row count and an MD5 over all rows in fid order (every column, geometry blobs as
bytes) equal those of the export; the zip passes unzip -t.

  OUT_DIR/ArcSurf_v1.0_release_CC-BY-4.0.gpkg        layer arcsurf
  OUT_DIR/ArcSurf_v1.0_tiled_CC-BY-4.0.gpkg.zip      holds ArcSurf_v1.0_tiled_CC-BY-4.0.gpkg, layer arcsurf_tiled
  OUT_DIR/split_report.txt
usage: split_release_by_geometry.py SRC.gpkg OUT_DIR TMP_DIR"""
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from multiprocessing import Pool

from osgeo import ogr

ogr.UseExceptions()
# layer kept, layer deleted, output name, zipped
PARTS = [('arcsurf', 'arcsurf_tiled', 'ArcSurf_v1.0_release_CC-BY-4.0.gpkg', False),
         ('arcsurf_tiled', 'arcsurf', 'ArcSurf_v1.0_tiled_CC-BY-4.0.gpkg', True)]


def header(path):
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    h = tuple(con.execute(f'PRAGMA {p}').fetchone()[0] for p in ('application_id', 'user_version', 'page_size'))
    con.close()
    return h


def layer_digest(path, layer):
    """row count and MD5 over all rows of a layer in fid order"""
    con = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    pk = [r[1] for r in con.execute(f'PRAGMA table_info("{layer}")') if r[5]][0]
    h, n = hashlib.md5(), 0
    for row in con.execute(f'SELECT * FROM "{layer}" ORDER BY "{pk}"'):
        for v in row:
            h.update(v if isinstance(v, bytes) else repr(v).encode())
            h.update(b'\x1f')
        h.update(b'\x1e')
        n += 1
    con.close()
    return n, h.hexdigest()


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 24), b''):
            h.update(b)
    return h.hexdigest()


def main():
    src, out, tmp_dir = sys.argv[1:4]
    os.makedirs(tmp_dir, exist_ok=True)
    lines = [f'export {src}: {os.path.getsize(src) / 1e9:.2f} GB, header {header(src)}']
    print(lines[0], flush=True)
    made = []
    for keep, drop, name, zipped in PARTS:
        t0 = time.time()
        dst = os.path.join(tmp_dir if zipped else out, name)
        if os.path.exists(dst) or os.path.exists(os.path.join(out, name + '.zip')):
            sys.exit(f'exists already: {name}')
        tmp = os.path.join(tmp_dir, f'{keep}_copy.gpkg')
        shutil.copyfile(src, tmp)
        ds = ogr.Open(tmp, 1)
        names = [ds.GetLayerByIndex(i).GetName() for i in range(ds.GetLayerCount())]
        ds.DeleteLayer(names.index(drop))
        ds = None
        con = sqlite3.connect(tmp)
        con.execute("VACUUM INTO '" + dst.replace("'", "''") + "'")
        con.close()
        os.remove(tmp)
        ds = ogr.Open(dst)
        got = [(ds.GetLayerByIndex(i).GetName(), ds.GetLayerByIndex(i).GetFeatureCount())
               for i in range(ds.GetLayerCount())]
        ds = None
        if [g[0] for g in got] != [keep] or header(dst) != header(src):
            sys.exit(f'{name}: layers {got}, header {header(dst)}')
        made.append((keep, dst, name, zipped))
        lines.append(f'{name}: layer {keep}, {got[0][1]:,} features, {os.path.getsize(dst) / 1e9:.2f} GB '
                     f'({time.time() - t0:.0f} s)')
        print(lines[-1], flush=True)
    with Pool(4) as p:
        res = p.starmap(layer_digest, [(src, k) for k, *_ in made] + [(d, k) for k, d, *_ in made])
    ok = True
    for i, (keep, dst, name, zipped) in enumerate(made):
        a, b = res[i], res[i + len(made)]
        ok &= a == b
        lines.append(f'check {keep}: export {a[0]:,} rows md5 {a[1]}; {name} {b[0]:,} rows md5 {b[1]}: '
                     f'{"identical" if a == b else "DIFFERENT"}')
        print(lines[-1], flush=True)
    if not ok:
        open(os.path.join(out, 'split_report.txt'), 'w').write('\n'.join(lines + ['FAILED']) + '\n')
        sys.exit('rows differ')
    for keep, dst, name, zipped in made:
        if zipped:
            z = os.path.join(out, name + '.zip')
            inner = md5(dst)
            subprocess.run(['zip', '-q', '-6', '-j', z, dst], check=True)
            subprocess.run(['unzip', '-tq', z], check=True)
            lines.append(f'{name}.zip: {os.path.getsize(z) / 1e9:.2f} GB, unzip -t passed; '
                         f'unzipped {name}: {os.path.getsize(dst) / 1e9:.2f} GB, md5 {inner}')
            print(lines[-1], flush=True)
    lines.append('checks PASSED')
    open(os.path.join(out, 'split_report.txt'), 'w').write('\n'.join(lines) + '\n')
    print('checks PASSED', flush=True)


if __name__ == '__main__':
    main()
