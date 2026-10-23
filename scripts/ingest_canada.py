#!/usr/bin/env python
"""
Canada ingests -> work/std/<src>.gpkg

  ca_gsc_cgm   every Canadian Geoscience Map sheet (GSC Surficial Data Model) in
               raw/canada/gsc/CGM*: GEO_POLYS, crosswalk key = UTYPE1_DID (national
               SDM domain), second component UTYPE2_DID -> hclass2 through the same
               table, one footprint per sheet, scale / tier / year from the OSTR record.
  (provincial products: see ingest_canada_prov.py)

Legacy A-series / Open File sheets (91) are NOT ingested: their shapefiles carry
map-specific legend codes decoded only in each sheet's PDF (phase 2).
"""
import glob
import json
import os
import sys

import pandas as pd
import geopandas as gpd
import pyogrio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S
import cgm_old as CO  # noqa: E402

GSC = f'{S.RAW}/canada/gsc'
OGL = 'Open Government Licence - Canada'


def one_sheet(d):
    """Ingest one CGM sheet directory -> (units, footprint, log line). Runs in a worker."""
    src = 'ca_gsc_cgm'
    x = S.load_xwalk(src).set_index('xkey')['hclass']
    man = json.load(open(f'{d}/_MANIFEST.json'))
    gdbs = [g for g in glob.glob(f'{d}/**/*.gdb', recursive=True)
            if 'carto' not in os.path.basename(g).lower()]
    # CGM396/449 ship stray copies in Data/XML ('New File Geodatabase_1.gdb') next to the
    # real Data/GDB one: reading both duplicated every polygon (5,743 km2 in one tile)
    in_gdb_dir = [g for g in gdbs if '/Data/GDB/' in g]
    if in_gdb_dir:
        gdbs = in_gdb_dir
    gp = []
    for g in gdbs:
        try:
            if 'GEO_POLYS' in [n for n, _ in pyogrio.list_layers(g)]:
                gp.append(g)
        except Exception:
            pass
    # two gdbs over the SAME extent are alternative versions, not panels (CGM172-174:
    # generalised -1 with ~1k polygons and detailed -2 with ~15k): keep the richer one.
    # True multi-panel maps (_p1, _p2) have disjoint extents and are all kept.
    if len(gp) > 1:
        info = []
        for g in gp:
            i = pyogrio.read_info(g, layer='GEO_POLYS')
            x0, y0, x1, y1 = i['total_bounds']
            info.append((g, i['features'], (x0, y0, x1, y1)))
        info.sort(key=lambda t: -t[1])
        kept = []
        for g, n, b in info:
            area = max((b[2] - b[0]) * (b[3] - b[1]), 1e-9)
            dup = False
            for _, _, k in kept:
                ix = max(0, min(b[2], k[2]) - max(b[0], k[0])) * max(0, min(b[3], k[3]) - max(b[1], k[1]))
                if ix / area > 0.5:
                    dup = True
                    break
            if not dup:
                kept.append((g, n, b))
        gp = [g for g, _, _ in kept]
    if not gp:
        return one_sheet_old(d, man)
    parts = []
    for g in gp:      # multi-panel maps ship one gdb per panel (_p1, _p2 ...)
        df = pyogrio.read_dataframe(g, layer='GEO_POLYS')
        if df.crs is None:
            continue
        # older SDM versions lack some fields: add them empty rather than crash
        # oldest SDM (CGM295/297/298): UTYPE_DID is a dummy 'x'; the unit is only in the
        # GSC terrain symbols label1/label2 (Tv, Cx, GLb ...) -> key 'LBL:<genetic caps>'
        lc = {c.lower(): c for c in df.columns}
        # SDM 2.5 (CGM465/466, 2025): unit type / label / subcategory are subtype fields *_SID holding
        # the same national codes as the old *_DID domains (checked code by code against the crosswalk)
        for a, b in (('UTYPE1_SID', 'UTYPE1_DID'), ('ULABEL1_SID', 'ULABEL1_DID'), ('USUBCAT1_SID', 'USUBCAT1_DID')):
            if b not in df and a in df:
                df[b] = df[a]
        if 'UTYPE1_DID' not in df and 'label1' in lc:
            gen = lambda s: s.astype(str).str.extract(r'^[a-z]*([A-Z]{1,2})')[0]   # noqa: E731  (lowercase texture prefix: pO, fpO)
            l1, l2 = df[lc['label1']], df[lc['label2']] if 'label2' in lc else pd.Series(None, index=df.index)
            df['UTYPE1_DID'], df['UTYPE2_DID'] = 'LBL:' + gen(l1), 'LBL:' + gen(l2)
            df['ULABEL1_DID'], df['ULABEL2_DID'] = l1, l2
        # predictive Landsat OFs (OF7108, OF7233): single UTYPE_DID holding the terrain
        # symbol itself (GFc, Tb, GLd ...) -> same 'LBL:<genetic caps>' key
        if 'UTYPE1_DID' not in df and 'UTYPE_DID' in df and \
                df['UTYPE_DID'].astype(str).str.match(r'^[a-z]*[A-Z]').mean() > 0.5:
            u0 = df['UTYPE_DID'].astype(str)
            df['UTYPE1_DID'] = 'LBL:' + u0.str.extract(r'^[a-z]*([A-Z]{1,2})')[0]
            df['ULABEL1_DID'] = u0
        for c in ('CONTROL1_SID', 'UTYPE1_DID', 'UTYPE2_DID', 'URELATION_DID', 'ULABEL1_DID', 'ULABEL2_DID',
                  'USUBCAT1_DID', 'EVENT1_PID', 'ORIG_CODE_PID'):
            if c not in df:
                df[c] = None
        try:
            st = pyogrio.read_dataframe(g, layer='M_SUBTYPES', read_geometry=False)
            st = st[st['S_FC'] == 'GEO_POLYS'].drop_duplicates('S_CODE')
            lut = dict(zip(st['S_CODE'].astype(str), st['S_VALUE_EN']))
        except Exception:
            lut = {}
        key = pd.to_numeric(df['CONTROL1_SID'], errors='coerce').astype('Int64').astype(str)
        df['desc'] = key.map(lut).fillna(key)
        if not lut and 'UTYPE1_SID' in df:      # SDM 2.5: M_SUBTYPES has no GEO_POLYS rows; names are in M_DOMAINS
            try:
                dm = pyogrio.read_dataframe(g, layer='M_DOMAINS', read_geometry=False)
                dm = dm[dm['D_FIELD'].astype(str).str.upper() == 'UTYPE1_SID']
                df['desc'] = df['UTYPE1_SID'].astype(str).map(dict(zip(dm['D_CODE'].astype(str), dm['D_DESC_EN']))).fillna(df['desc'])
            except Exception:
                pass
        parts.append(df.to_crs(S.CRS))
    if not parts:
        return None, None, (man['label'], 'no CRS in any GEO_POLYS')
    df = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    df = S.in_amap(df)
    if df.empty:
        return None, None, (man['label'], 'outside AMAP')
    def did(c):     # numeric DIDs, or the 'LBL:' symbol keys of the oldest schema
        # NB pandas >= 3: Int64 -> str keeps MISSING values (not the text '<NA>'), so test isna()
        n = pd.to_numeric(df[c], errors='coerce').astype('Int64').astype('string')
        raw = df[c].astype('string')
        lbl = raw.where(raw.str.startswith('LBL:', na=False))
        return n.where(n.notna(), lbl)
    t1, t2 = did('UTYPE1_DID'), did('UTYPE2_DID')
    df['xkey'] = t1.fillna('NULL')
    df['hclass2_src'] = t2.map(x).fillna('')
    rel = df['URELATION_DID'].fillna('_').replace('_', ' ')
    df['code'] = (df['ULABEL1_DID'].fillna('') + rel + df['ULABEL2_DID'].fillna('')).str.strip()
    tier = (man.get('tier_from_title') or '').capitalize()
    yr = int(str(man.get('release') or '0')[:4]) or None
    u, _ = S.standardise(df, src_id=src, code='code', desc='desc', xkey='xkey',
                         sheet=pd.Series(man['label'], index=df.index),
                         extra=('URELATION_DID', 'USUBCAT1_DID', 'EVENT1_PID', 'ORIG_CODE_PID'),
                         carry=('hclass2_src',), scale_den=man['scale'], pub_year=yr,
                         conf_tier=tier, licence=OGL, redistribution='open')
    f = S.footprint_from_units(u)
    f['src_sheet'] = man['label']
    return u, f, (man['label'], f'{len(u)} polys, 1:{man["scale"]}, {tier}, {yr}')


def one_sheet_old(d, man, src='ca_gsc_cgm', skip_numeric=False):
    """Sheets with no GEO_POLYS gdb (70 of 240: older SDM, shapefile-only, PMF/Apps gdbs):
    unit layer and keys from cgm_old (SDM symbol group 'SYM:XX', else terrain label 'LBL:X')."""
    p, lyr = CO.find_units(d)
    if p is None:
        return None, None, (man['label'], 'no unit layer (old schema)')
    df = pyogrio.read_dataframe(p, layer=lyr)
    if df.crs is None:
        # legacy A/OF shapefiles ship no .prj; the FGDC metadata (meta/meta<n>.txt) states
        # UTM_Zone_Number and the datum -> NAD27 UTM = EPSG:267zz, NAD83 UTM = EPSG:269zz
        epsg = legacy_crs(d)
        if epsg is None:
            return None, None, (man['label'], f'no CRS: {os.path.basename(p)}')
        df = df.set_crs(epsg)
    df = S.in_amap(S.polygons_only(df.to_crs(S.CRS)))
    if df.empty:
        return None, None, (man['label'], 'outside AMAP')
    key, code, desc, used = CO.keys(df)
    if skip_numeric and used.get('numbered'):
        if True:
            # map-specific numbered units (1a, 4b, 7a): meaningless without the PDF legend
            return None, None, (man['label'], 'numbered legend units - needs PDF legend keying')
    df['xkey'], df['code'], df['desc'] = key.fillna('NULL'), code, desc
    df['hclass2_src'] = ''
    tier = (man.get('tier_from_title') or '').capitalize()
    yr = int(str(man.get('release') or '0')[:4]) or None
    u, _ = S.standardise(df, src_id=src, code='code', desc='desc', xkey='xkey',
                         sheet=pd.Series(man['label'], index=df.index),
                         carry=('hclass2_src',), scale_den=man['scale'], pub_year=yr,
                         conf_tier=tier, licence=OGL, redistribution='open')
    f = S.footprint_from_units(u)
    f['src_sheet'] = man['label']
    rel = p.split(man['label'] + '/')[-1]
    return u, f, (man['label'], f'{len(u)} polys, 1:{man["scale"]}, {tier}, {yr} [old schema {rel}:{lyr or ""} {used}]')


def legacy_crs(d):
    import re
    # a CRS pinned in the manifest wins: OF4484's Baffin 1:50k set (OF1598-1613) states
    # geographic NAD83 in its metadata, but its shapefiles are UTM 17 metres (x ~500 km at 81W)
    pin = json.load(open(f'{d}/_MANIFEST.json')).get('crs_epsg') if os.path.exists(f'{d}/_MANIFEST.json') else None
    if pin:
        return int(pin)
    for m in glob.glob(f'{d}/**/meta*.txt', recursive=True):
        t = open(m, encoding='latin-1').read()
        z = re.search(r'UTM_Zone_Number:\s*(\d+)', t)
        dt = re.search(r'Horizontal_Datum_Name:\s*(.+)', t)
        if z and dt:
            zone = int(z.group(1))
            if '1983' in dt.group(1):
                return 26900 + zone
            if '1927' in dt.group(1):
                return 26700 + zone
    return None


def one_legacy(d):
    """One legacy A/OF sheet -> (units, footprint, log, crosswalk rows). Units are keyed
    '<sheet>|<CODE>' and classified from the sheet's own legend table (legacy_legend);
    whole-word labels (GLACIER, SNOW, WATER, UNMAPPED) and codes absent from the legend
    fall back to the terrain-symbol key of the old CGM reader."""
    import legacy_legend as LL
    man = json.load(open(f'{d}/_MANIFEST.json'))
    sheet = man['label']
    p, lyr = CO.find_units(d)
    if p is None:
        return None, None, (sheet, 'no unit layer'), []
    df = pyogrio.read_dataframe(p, layer=lyr)
    if df.crs is None:
        epsg = legacy_crs(d)
        if epsg is None:
            return None, None, (sheet, f'no CRS: {os.path.basename(p)}'), []
        df = df.set_crs(epsg)
    df = S.in_amap(S.polygons_only(df.to_crs(S.CRS)))
    if df.empty:
        return None, None, (sheet, 'outside AMAP'), []
    key, code, desc, used = CO.keys(df)
    # the legend table is keyed on CODE: use that field when present (the reader may have
    # picked another label field)
    cc = next((c for c in df.columns if c.upper() == 'CODE'), None)
    if cc is not None:
        code = df[cc].astype('string').str.strip().fillna('')
    leg = LL.read_legend(d)
    xkey, dsc, rows, n_leg = [], [], {}, 0
    for c, k0, d0 in zip(code, key, desc):
        w = LL.word_class(c)
        if w == 'DROP':
            xkey.append('NULL'); dsc.append(c)
        elif w:
            xkey.append({'I': 'LBL:I', 'H': 'LBL:W'}[w]); dsc.append(c)
        elif c in leg and leg[c]['note'].startswith('UNCLASSIFIED') and isinstance(k0, str) and k0.startswith(('LBL:', 'SYM:')):
            # legend text names no genesis (A1896a 'Mb', 'R'): the terrain symbol decides
            xkey.append(k0); dsc.append(leg[c]['desc'])
        elif c in leg:
            k = f'{sheet}|{c}'
            xkey.append(k); dsc.append(leg[c]['desc']); n_leg += 1
            if k not in rows:
                L = leg[c]
                rows[k] = [k, L['hclass'], '', L['texture'], L['cover'], L['ice_rich'], f'{sheet} {c}: {L["note"]}']
        elif '-' in c and c.split('-')[0] in leg and leg[c.split('-')[0]]['hclass'] and \
                not leg[c.split('-')[0]]['note'].startswith('UNCLASSIFIED'):
            # combined labels 'Lb-O', 'Tb-Lb', 'Ap-O-L1' (2026-10-04, BC group-C check: 482 km2 of glaciolacustrine
            # Lb-* came out L from the terrain symbol, and the second class was lost on ~2.8k km2): first component
            # from the legend gives hclass/texture/cover, the first later component of another class gives hclass2
            parts = c.split('-')
            L0 = leg[parts[0]]
            k = f'{sheet}|{c}'
            xkey.append(k); dsc.append(' / '.join(leg[q]['desc'] if q in leg else q for q in parts)); n_leg += 1
            if k not in rows:
                h2 = next((leg[q]['hclass'] for q in parts[1:] if q in leg and leg[q]['hclass'] not in ('', L0['hclass'])), '')
                rows[k] = [k, L0['hclass'], h2, L0['texture'], L0['cover'], L0['ice_rich'],
                           f'{sheet} {c}: combined label; {parts[0]} -> {L0["hclass"]} ({L0["note"]})'
                           + (f'; 2nd component -> {h2}' if h2 else '')]
        else:
            xkey.append(k0 if isinstance(k0, str) else 'NULL'); dsc.append(d0)
    df['xkey'], df['code'], df['desc'] = xkey, code, dsc
    df['hclass2_src'] = ''
    tier = (man.get('tier_from_title') or '').capitalize()
    yr = int(str(man.get('release') or '0')[:4]) or None
    u, _ = S.standardise(df, src_id='ca_gsc_legacy', code='code', desc='desc', xkey='xkey',
                         sheet=pd.Series(sheet, index=df.index),
                         carry=('hclass2_src',), scale_den=man['scale'], pub_year=yr,
                         conf_tier=tier, licence=OGL, redistribution='open')
    f = S.footprint_from_units(u)
    f['src_sheet'] = sheet
    msg = (f'{len(u)} polys, 1:{man["scale"]}, {tier}, {yr}; legend-keyed {n_leg}/{len(df)} '
           f'({len(leg)} legend units)' + ('' if leg else ' NO LEGEND TABLE'))
    return u, f, (sheet, msg), list(rows.values())


def legacy(workers=16):
    """Legacy GSC A-series / Open File vector sheets (91 downloaded), classified from each
    sheet's legend table. Writes the generated per-sheet crosswalk rows next to the static
    SYM/LBL rows in xwalk/ca_gsc_legacy.csv."""
    from multiprocessing import Pool
    src = 'ca_gsc_legacy'
    dirs = sorted(d for d in glob.glob(f'{GSC}/*') if not os.path.basename(d).startswith('CGM'))
    units, fps, log, xw = [], [], [], []
    with Pool(workers) as pool:
        for u, f, msg, rows in pool.imap_unordered(one_legacy, dirs):
            log.append(msg)
            print(msg, flush=True)
            xw += rows
            if u is not None:
                units.append(u)
                fps.append(f)
    u = gpd.GeoDataFrame(pd.concat(units, ignore_index=True), crs=S.CRS)
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
    static = pd.read_csv(f'{S.XWALK}/{src}.csv', dtype=str, keep_default_na=False)
    static = static[~static['xkey'].str.contains('|', regex=False)]
    gen = pd.DataFrame(xw, columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note'])
    pd.concat([static, gen], ignore_index=True).to_csv(f'{S.XWALK}/{src}.csv', index=False)
    print('generated rows', len(gen), gen['hclass'].value_counts().to_dict(),
          '| UNCLASSIFIED', int(gen['xwalk_note'].str.contains('UNCLASSIFIED').sum()))
    x = S.load_xwalk(src).set_index('xkey')['hclass']
    print('xkeys not in crosswalk:', sorted(set(u['xkey']) - set(x.index)))
    S.write_std(u, fp, src, dict(title='GSC legacy A-series / Open File surficial sheets (vector)', log=log))
    print('sheets', len(fps), 'polys', len(u), 'km2', round(u.area.sum() / 1e6))


def cgm(workers=16):
    from multiprocessing import Pool
    src = 'ca_gsc_cgm'
    x = S.load_xwalk(src).set_index('xkey')['hclass']
    dirs = sorted(glob.glob(f'{GSC}/CGM*'))
    units, fps, log = [], [], []
    with Pool(workers) as pool:
        for u, f, msg in pool.imap_unordered(one_sheet, dirs):
            log.append(msg)
            print(msg, flush=True)
            if u is not None:
                units.append(u)
                fps.append(f)
    u = gpd.GeoDataFrame(pd.concat(units, ignore_index=True), crs=S.CRS)
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
    miss = sorted(set(u['xkey']) - set(x.index))
    print('xkeys not in crosswalk:', miss)
    S.write_std(u, fp, src, dict(title='GSC Canadian Geoscience Maps (SDM), vector sheets', log=log))
    S.code_table(u).to_csv(f'{S.WORK}/codes_{src}.csv', index=False)
    print('sheets', len(fps), 'polys', len(u), 'km2', round(u.area.sum() / 1e6))


if __name__ == '__main__':
    {'cgm': cgm, 'legacy': legacy}[sys.argv[1] if len(sys.argv) > 1 else 'cgm']()
