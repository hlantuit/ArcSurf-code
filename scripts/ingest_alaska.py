#!/usr/bin/env python
"""
Alaska ingests -> work/std/<src>.gpkg

  us_usgs_sim3340   Geologic Map of Alaska (Wilson et al. 2015), detailed layer
                    AKStategeol_poly, nominal 1:250,000; crosswalk key QCLASS
  us_usgs_sim3388   Dillingham surficial (Wilson 2018), 1:250,000, QCLASS (same key
                    as SIM 3340; its crosswalk is SIM 3340's). Tier 'Surficial'.
  us_usgs_sim3036   Noatak surficial (Hamilton 2010), 1:250,000, UNITLABEL + noa_poly4_lut.
                    Tier 'Surficial' (dedicated surficial map outranks the compilation).
  us_ak_gems        every GeMS-format DGGS/USGS map package (incl. Giesche 2024):
                    MapUnitPolys + DescriptionOfMapUnits.csv; crosswalk key
                    '<package>|<MapUnit>', rule-classified from each map's own unit
                    name/description (classify_units.py) -> xwalk/us_ak_gems.csv, which
                    is REVIEWED before merging. Scale 1:63,360 unless stated.
"""
import glob
import os
import re
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402
import classify_units as CU  # noqa: E402

U = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/alaska'
PD = 'US federal public domain (USGS)'


def finish(u, fp, src, meta):
    p, m = S.write_std(u, fp, src, meta)
    S.code_table(u).to_csv(f'{S.WORK}/codes_{src}.csv', index=False)
    print(src, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')}, flush=True)


def sim3340():
    src = 'us_usgs_sim3340'
    g = pyogrio.read_dataframe(glob.glob(f'{U}/sim3340_gdb/**/AKStategeol.gdb', recursive=True)[0],
                               layer='AKStategeol_poly')
    g = S.in_amap(g.to_crs(S.CRS))
    g['code'] = pd.to_numeric(g['QCLASS'], errors='coerce').fillna(0).astype(int).astype(str)
    desc = [c for c in ('STATE_UNIT', 'STATE_LABE', 'NSACLASS', 'SOURCECLAS') if c in g]
    g['desc'] = g[desc].astype(str).agg(' | '.join, axis=1) if desc else ''
    u, _ = S.standardise(g, src_id=src, code='code', desc='desc', scale_den=250_000, pub_year=2015,
                         extra=tuple(c for c in ('SOURCE', 'SOURCECLAS') if c in g),
                         licence=PD, redistribution='open')
    finish(u, S.footprint_from_units(u, simplify=200.0), src, dict(title='USGS SIM 3340 Geologic Map of Alaska (detailed)'))


def sim3388():
    src = 'us_usgs_sim3388'
    g = pyogrio.read_dataframe(glob.glob(f'{U}/SIM3388_database/**/di_surf.gdb', recursive=True)[0], layer='disurf_poly')
    g = S.in_amap(g.to_crs(S.CRS))
    g['code'] = pd.to_numeric(g['QCLASS'], errors='coerce').fillna(0).astype(int).astype(str)
    u, _ = S.standardise(g, src_id=src, code='code', desc='UNITLABEL', scale_den=250_000, pub_year=2018,
                         conf_tier='Surficial', licence=PD, redistribution='open')
    # same QCLASS key as SIM 3340 -> reuse its crosswalk verbatim
    x = pd.read_csv(f'{S.XWALK}/us_usgs_sim3340.csv', dtype=str, keep_default_na=False)
    x.to_csv(f'{S.XWALK}/{src}.csv', index=False)
    finish(u, S.footprint_from_units(u), src, dict(title='USGS SIM 3388 Surficial geology, Dillingham quadrangle'))


def sim3036():
    src = 'us_usgs_sim3036'
    gdb = glob.glob(f'{U}/sim3036-Vector_Noatak/**/noa2.gdb', recursive=True)[0]
    g = pyogrio.read_dataframe(gdb, layer='noa_geo_polygon')
    if g.crs is None:
        raise SystemExit('Noatak: no CRS')
    g = S.in_amap(g.to_crs(S.CRS))
    lut = None
    for name, _ in pyogrio.list_layers(gdb):
        if 'lut' in name.lower():
            lut = pyogrio.read_dataframe(gdb, layer=name, read_geometry=False)
    g['code'] = g['UNITLABEL'].astype(str).str.strip()
    names = {}
    if lut is not None:
        kc = [c for c in lut.columns if c.upper() == 'UNITLABEL']
        nc = [c for c in lut.columns if c.upper() in ('UNITNAME', 'NAME', 'UNIT_NAME')]
        if kc and nc:
            names = dict(zip(lut[kc[0]].astype(str).str.strip(), lut[nc[0]].astype(str)))
    g['desc'] = g['code'].map(names).fillna(g.get('UNITNAME', ''))
    g['xkey'] = 'noatak|' + g['code']
    u, _ = S.standardise(g, src_id=src, code='code', desc='desc', xkey='xkey', scale_den=250_000,
                         pub_year=2010, conf_tier='Surficial', licence=PD, redistribution='open')
    rows = []
    for k, d in u[['xkey', 'src_desc']].drop_duplicates('xkey').itertuples(index=False):
        c = CU.classify(str(d), '')
        rows.append(dict(xkey=k, **{f: c[f] for f in ('hclass', 'hclass2', 'texture', 'cover', 'ice_rich')},
                         xwalk_note=f'{d} :: {c["xwalk_note"]}'))
    n = apply_manual(rows, lambda r: 'noatak', lambda r: r['xkey'].split('|', 1)[1],
                     lambda r: r['xwalk_note'].split(' :: ')[0])
    print('manual overrides applied:', n, '| still unclassified:', sum('UNCLASSIFIED' in r['xwalk_note'] for r in rows))
    pd.DataFrame(rows).to_csv(f'{S.XWALK}/{src}.csv', index=False)
    finish(u, S.footprint_from_units(u), src, dict(title='USGS SIM 3036 Surficial geology, Noatak National Preserve'))


MANUAL = f'{S.XWALK}/us_ak_manual.csv'


def apply_manual(rows, pkg_of, code_of, name_of):
    """Overrides from xwalk/us_ak_manual.csv, applied after the rules. match forms:
    '<map>:<code>' (map = substring of the package/xkey prefix), '<map>:*' (only for
    rows still UNCLASSIFIED), 'name:<unit name>' (case-insensitive), 'unit:<code>|<name part>'."""
    m = pd.read_csv(MANUAL, dtype=str, keep_default_na=False)
    n = 0
    for r in rows:
        pkg, code, name = pkg_of(r).lower(), code_of(r), (name_of(r) or '').strip()
        for x in m.itertuples(index=False):
            kind, _, key = x.match.partition(':')
            hit = False
            if kind == 'name':
                hit = name.casefold() == key.casefold()
            elif kind == 'unit':
                c, _, nm = key.partition('|')
                hit = code == c and nm.casefold() in name.casefold()
            elif key == '*':
                hit = kind in pkg and 'UNCLASSIFIED' in r['xwalk_note']
            else:
                hit = kind in pkg and code == key
            if hit:
                r.update(hclass=x.hclass, hclass2=x.hclass2, texture=x.texture or 'unknown',
                         cover=x.cover or 'unknown', ice_rich=x.ice_rich or 'unknown',
                         xwalk_note=f'{name[:100]} :: {x.xwalk_note}')
                n += 1
                break
    return n


def year_of(pkg):
    m = re.match(r'[a-z]+(\d{4})_', pkg)
    return int(m.group(1)) if m else None


def gems():
    src = 'us_ak_gems'
    units, fps, xw, log = [], [], [], []
    for dmu in sorted(glob.glob(f'{U}/**/DescriptionOfMapUnits.csv', recursive=True)):
        pkg = dmu.replace(U + '/', '').split('/')[0]
        root = dmu.split('/data/')[0] if '/data/' in dmu else os.path.dirname(dmu)
        cands = [p for p in glob.glob(f'{U}/{pkg}/**/*MapUnitPolys*.shp', recursive=True)]
        cands = [(p, pyogrio.read_info(p)['features']) for p in cands]
        cands = [c for c in cands if c[1] > 0]
        if not cands:
            log.append((pkg, 'no non-empty MapUnitPolys'))
            continue
        shp = max(cands, key=lambda c: c[1])[0]
        g = pyogrio.read_dataframe(shp)
        if g.crs is None:
            log.append((pkg, 'no CRS'))
            continue
        g = S.in_amap(g.to_crs(S.CRS))
        if g.empty:
            log.append((pkg, 'outside AMAP'))
            continue
        d = pd.read_csv(dmu, dtype=str, keep_default_na=False, encoding_errors='replace')
        mu = next(c for c in d.columns if c.lower() == 'mapunit')
        nm = next((c for c in d.columns if c.lower() in ('name', 'fullname')), None)
        ds = next((c for c in d.columns if c.lower() in ('description', 'descr')), None)
        d = d[d[mu].str.strip() != ''].drop_duplicates(mu)
        names = dict(zip(d[mu].str.strip(), d[nm] if nm else ''))
        descs = dict(zip(d[mu].str.strip(), d[ds] if ds else ''))
        g['code'] = g['MapUnit'].astype(str).str.strip()
        g['desc'] = g['code'].map(names).fillna('')
        g['xkey'] = pkg + '|' + g['code']
        sc = 63_360 if 'giesche' in pkg or 'ri19' in pkg else 63_360
        u, _ = S.standardise(g, src_id=src, code='code', desc='desc', xkey='xkey',
                             sheet=pd.Series(pkg, index=g.index), scale_den=sc, pub_year=year_of(pkg),
                             licence='Alaska DGGS / USGS public data (CC0 for Giesche 2024)', redistribution='open')
        units.append(u)
        f = S.footprint_from_units(u)
        f['src_sheet'] = pkg
        fps.append(f)
        for code in sorted(u['src_code'].unique()):
            c = CU.classify(names.get(code, ''), descs.get(code, '')[:600])
            xw.append(dict(xkey=f'{pkg}|{code}', **{k: c[k] for k in ('hclass', 'hclass2', 'texture', 'cover', 'ice_rich')},
                           xwalk_note=f'{names.get(code, "")[:120]} :: {c["xwalk_note"]}'))
        log.append((pkg, f'{len(u)} polys, {u["src_code"].nunique()} units, {os.path.basename(shp)}'))
        print(log[-1], flush=True)
    u = gpd.GeoDataFrame(pd.concat(units, ignore_index=True), crs=S.CRS)
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
    n = apply_manual(xw, lambda r: r['xkey'].split('|')[0], lambda r: r['xkey'].split('|', 1)[1],
                     lambda r: r['xwalk_note'].split(' :: ')[0])
    print('manual overrides applied:', n)
    x = pd.DataFrame(xw)
    x.to_csv(f'{S.XWALK}/{src}.csv', index=False)
    print('rule-classified:', x['hclass'].value_counts().to_dict(),
          '| UNCLASSIFIED:', int(x['xwalk_note'].str.contains('UNCLASSIFIED').sum()))
    finish(u, fp, src, dict(title='Alaska GeMS surficial maps (DGGS, USGS, Giesche 2024)', log=log))


ALL = {'us_usgs_sim3340': sim3340, 'us_usgs_sim3388': sim3388, 'us_usgs_sim3036': sim3036, 'us_ak_gems': gems}

if __name__ == '__main__':
    for s in (sys.argv[1:] or ALL):
        print('==', s, flush=True)
        ALL[s]()
