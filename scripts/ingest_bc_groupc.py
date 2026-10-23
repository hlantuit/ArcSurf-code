#!/usr/bin/env python
"""
British Columbia, CA_MISSING group C: 44 NTS 1:250k areas of the permafrost domain (~173k km2) that only the GSC
1:5M fallback covered. Downloads approved by H. Lantuit 2026-10-04, staged under raw/canada/groupC/<item>/
(MANIFEST.tsv = file, bytes, sha256, url). Three new sources:

  ca_gsc_bc_ofs    GSC surficial-geology maps, one src_sheet per map (conf_tier Surficial, as the other GSC maps):
                     093N 1:250k OF D2270 (Plouffe & Williams 2001) = Map 1987A (Plouffe 2000), NAD27 UTM 10;
                          hclass from its DEPOSIT field
                     094A+093P 1:250k BC Energy Open File 2011-2 (Hickin & Fournier 2011), compilation of the GSC maps;
                          GSC terrain symbols (no legend table shipped), 'A_B' composites split into hclass/hclass2
                   The 14 094P/094I OFs (Bednarski 1:50k OF 4825 4846 5479 5480 5481 5505 5506 6562; Smith 1:50k
                   OF 5305-5307 5309; 1:100k OF 5540, 5527) turned out to be ALREADY merged in ca_gsc_legacy (staged as
                   raw/canada/gsc/<OF> by the OSTR census): not re-ingested (BCG_KEEP_LEGACY_DUPS=1 forces it).
                   'legacy_compare' classifies them here (sheet legend per component; 'Combined unit' codes A-B / A/B
                   split into hclass from A, hclass2 from B) and compares with ca_gsc_legacy, whose composites fall
                   back to the terrain-symbol key (LBL:L for Lb-O = glaciolacustrine read as lacustrine).
  ca_bc_tem_extra  Sustut-Takla bioterrain (EcoCat r1496, BAPID 4048, Geowest/Timberline 2003-04, 1:20k, TSIL D) and
                   Muskwa-Kechika PEM areas 1-2 (r1866, BAPID 4016, EBA 2002, 1:50k). e00 arcs polygonised here (GDAL's
                   AVCE00 PAL reader took > 5 min for a 17 MB file), faces take the attributes of their label point,
                   joined to the attribute CSVs on the tag. BC Terrain Classification System materials SURFM_1/_2 decoded
                   with the ca_bc_ter tables (ingest_bc_ter.MAT/TEX): xkey 'm1|m2', texture/cover from the first
                   component's TTEX/SURF_E letters. 'N' (not classified / non-terrain; PEM FCODE XX00000000, mostly
                   water) is DROPped, as in ca_bc_ter.
  ca_bc_soil       BC soil surveys (openmaps WFS pub:WHSE_TERRESTRIAL_ECOLOGY.STE_SOIL_SURVEYS_MVW), clipped to the
                   group-C boxes. hclass from MDEP_1 (mode of deposition of the dominant soil's parent material),
                   hclass2 from MDEP_2; scale from the survey name '(1:NNNNN)'; src_sheet = survey (PROJ_NAME).

Lakes keep hclass H where the source maps them as water (LEGEND.md; ca_gsc_legacy maps WATER -> H). Units a source
labels not classified / not mapped are DROPped so coarser sources fill them.

usage: SURF_DOMAIN=domain ingest_bc_groupc.py gsc | tem | soil
       ingest_bc_groupc.py gain [src ...]      (after build_xw)  -> work/bcgroupc/gain_*.csv
       ingest_bc_groupc.py stats               (after build_xw)  -> work/bcgroupc/stats_*.csv|json
       ingest_bc_groupc.py validate            (after build_xw)  -> work/bcgroupc/validate_*.csv
"""
import glob
import json
import os
import re
import sys
import time

os.environ.setdefault('SURF_DOMAIN', 'domain')        # the permafrost-region build domain (2026-09-30 on)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyogrio  # noqa: E402
import shapely  # noqa: E402
import cgm_old as CO  # noqa: E402
import legacy_legend as LL  # noqa: E402
from ingest_canada import legacy_crs  # noqa: E402   (UTM zone + datum from the OF meta*.txt)
from ingest_bc_ter import MAT, TEX  # noqa: E402    (BC Terrain Classification System, as ca_bc_ter)

G = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/groupC'
WB = f'{S.WORK}/bcgroupc'
XWCOLS = ['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']
OGL_CA = 'Open Government Licence - Canada'
OGL_BC = 'Open Government Licence - British Columbia'
BC_COPY = ('Copyright Province of British Columbia; no open licence with the download (gov.bc.ca copyright: '
           'reproduction or redistribution needs written permission)')

# CA_MISSING group C (merge 33): NTS 1:250k code, west lon, south lat (sheets are 2 x 1 deg), km2 on the 1:5M fallback
GROUPC = """094K -126 58 11020|094E -128 57 10390|094L -128 58 9620|104I -130 58 9020|094J -124 58 8640|094N -126 59 8350|
094D -128 56 7970|104H -130 57 7270|094F -126 57 6830|082N -118 51 6690|083D -120 52 6480|094P -122 59 6330|093I -122 54 5440|
082K -118 50 5360|094H -122 57 4790|094M -128 59 4730|094B -124 56 4080|094A -122 56 3760|094C -126 56 3690|093H -122 53 3490|
082J -116 50 3220|094I -122 58 3130|104A -130 56 3120|093O -124 55 3030|092N -126 51 2740|092J -124 50 2000|083E -120 53 1990|
092O -124 51 1960|082M -120 51 1940|094G -124 57 1920|093M -128 55 1890|093A -122 52 1800|093N -126 55 1660|082F -118 49 1530|
082G -116 49 1210|093L -128 54 1210|083C -118 52 1090|093C -126 52 950|093E -128 53 630|103P -130 55 440|082L -120 50 430|
093P -122 55 390|092I -122 50 380|093D -128 52 320"""
GC = pd.DataFrame([r.split() for r in GROUPC.replace('\n', '').split('|')], columns=['nts', 'lon0', 'lat0', 'fallback_km2'])
GC[['lon0', 'lat0', 'fallback_km2']] = GC[['lon0', 'lat0', 'fallback_km2']].astype(float)


def box_geom(lon0, lat0, w=2.0, h=1.0, n=40):
    """lon/lat box densified (edges are curves in EASE / BC Albers)."""
    t = np.linspace(0, 1, n)
    lon = np.r_[lon0 + w * t, np.full(n, lon0 + w), lon0 + w - w * t, np.full(n, lon0)]
    lat = np.r_[np.full(n, lat0), lat0 + h * t, np.full(n, lat0 + h), lat0 + h - h * t]
    return shapely.Polygon(np.c_[lon, lat])


def groupc_boxes(crs):
    g = gpd.GeoDataFrame(GC, geometry=[box_geom(a, b) for a, b in zip(GC.lon0, GC.lat0)], crs=4326)
    return g.to_crs(crs)


def write_source(src, u, xw_rows, meta, coarse=None):
    """std gpkg (units incl. DROP rows, so build_xw counts them) + one footprint per src_sheet built from the
    units the crosswalk KEEPS (a dropped unit must not be claimed) + xwalk/<src>.csv."""
    xw = pd.DataFrame(xw_rows, columns=XWCOLS).drop_duplicates('xkey').sort_values('xkey')
    bad = set(xw['hclass']) - set(S.HCLASS) - {'DROP'}
    assert not bad, bad
    drop = set(xw.loc[xw['hclass'] == 'DROP', 'xkey'])
    keep = u[~u['xkey'].isin(drop)]
    fps = []
    for name, grp in keep.groupby('src_sheet'):
        f = S.footprint_from_units(grp, coarse=coarse) if coarse else S.footprint_from_units(grp)
        f['src_sheet'] = name
        fps.append(f)
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), geometry='geometry', crs=S.CRS)
    fp['geometry'] = shapely.make_valid(fp.geometry.values)
    p, m = S.write_std(u, fp, src, meta)
    xw.to_csv(f'{S.XWALK}/{src}.csv', index=False)
    miss = sorted(set(u['xkey']) - set(xw['xkey']))
    print(src, {k: m.get(k) for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')},
          '| xkeys without crosswalk row:', miss[:10], flush=True)
    a = u.assign(a=u.area / 1e6, h=u['xkey'].map(xw.set_index('xkey')['hclass']))
    print(' km2 by hclass', a.groupby('h')['a'].sum().round(1).sort_values(ascending=False).to_dict())
    print(' km2 by sheet', a.groupby('src_sheet')['a'].sum().round(1).to_dict(), flush=True)
    return m


# --------------------------------------------------------------------------------------------------- GSC maps
GSC_OFS = [  # label, dir, scale, year, map, NTS
    ('OF4825', 'of4825', 50_000, 2005, 'Estsine Lake', '094P/13'),
    ('OF4846', 'of4846', 50_000, 2005, 'Gote Creek', '094P/12'),
    ('OF5505', 'of5505', 50_000, 2007, 'Kimea Creek', '094P/10'),
    ('OF5506', 'of5506', 50_000, 2007, 'Etset Lake', '094P/11'),
    ('OF5479', 'of5479', 50_000, 2008, 'Thinahtea Lake', '094P/09'),
    ('OF5480', 'of5480', 50_000, 2008, 'June Lake', '094P/16'),
    ('OF5481', 'of5481', 50_000, 2008, 'Pesh Creek', '094P/08'),
    ('OF6562', 'of6562', 50_000, 2011, 'Kwokullie Lake', '094P/07'),
    ('OF5305', 'of5305', 50_000, 2009, 'Gunnell Creek', '094I/13'),
    ('OF5306', 'of5306', 50_000, 2009, 'Nogah Creek', '094I/12'),
    ('OF5307', 'of5307', 50_000, 2009, 'Kyklo Creek', '094I/11'),
    ('OF5309', 'of5309', 50_000, 2009, 'Lichen Creek', '094I/14'),
    ('OF5540', 'of5540', 100_000, 2009, 'Kahntah River', '094I/01,02,07,08'),
    ('OF5527', 'of5527', 100_000, 2007, 'Dazo Creek', '094I/03-06'),
]
# symbol fallback for a component absent from every legend of this NE-BC series (never needed if the legends are complete)
FAMILY_SYM = [('AN', 'X'), ('A', 'F'), ('C', 'C'), ('E', 'E'), ('G', 'GF'), ('L1', 'L'), ('L', 'GL'), ('O', 'O'),
              ('R', 'R'), ('T', 'T')]
GSC_SYM = {'A': 'F', 'C': 'C', 'E': 'E', 'G': 'GF', 'GF': 'GF', 'GL': 'GL', 'GM': 'GM', 'L': 'L', 'M': 'M', 'O': 'O',
           'R': 'R', 'T': 'T', 'I': 'I'}
DEP2270 = {'Organic': 'O', 'Till': 'T', 'Glaciofluvial': 'GF', 'Bedrock': 'R', 'Colluvial': 'C',
           'Alluvial (Fluvial)': 'F', 'Glaciolacustrine': 'GL', 'Lacustrine': 'L', 'Eolian': 'E'}


def split_code(code, sep='-'):
    """'Lb-O' -> ('Lb','O'); 'O1/Gt' -> ('O1','Gt') (upper/lower); 'Lb-Tr/Ts' -> ('Lb','Tr'); 'Tb' -> ('Tb', None)."""
    parts = [p for p in str(code).strip().split(sep) if p]
    first = parts[0].split('/')
    sec = parts[1].split('/')[0] if len(parts) > 1 else (first[1] if len(first) > 1 else None)
    return first[0], sec


def heading_fix(e):
    """An entry that opens with its own capitalised heading ('LACUSTRINE DEPOSITS: sand, silt ... deposited in a former
    lake') names the unit's genesis; it beats a contradicting LEVEL (OF6562 files L1 under LEVEL_5 'ALLUVIAL
    DEPOSITS', so legacy_legend's deepest-level rule read the post-glacial lake sediments as fluvial)."""
    entry = e.get('desc', '').split(' | ', 1)[-1]
    m = re.match(r'^([A-Z][A-Z \-]{5,}):', entry)
    if not m:
        return e, ''
    h, _ = LL.classify_text([], m.group(1))
    if h and h != e['hclass']:
        return dict(e, hclass=h, note=f'entry heading "{m.group(1)}" (LEVEL said {e["hclass"]})'), ' [heading fix]'
    return e, ''


def legend_comp(c, leg, fam):
    """one map-unit component -> (legend entry dict, how). A sheet legend whose text names no genesis term
    (OF5481 'Av' = 'Alluvium veneer': legacy_legend matches ALLUVIAL, not ALLUVIUM) defers to the series legend."""
    if c in leg and not leg[c]['note'].startswith('UNCLASSIFIED'):
        e, fx = heading_fix(leg[c])
        return e, 'legend' + fx
    if c in fam and not fam[c]['note'].startswith('UNCLASSIFIED'):
        e, fx = heading_fix(fam[c])
        return e, 'series legend' + (' (own legend unclassified)' if c in leg else '') + fx
    for pre, h in FAMILY_SYM:
        if c.startswith(pre):
            return dict(hclass=h, texture='unknown', cover='veneer' if c[len(pre):].startswith('v') else 'unknown',
                        ice_rich='unknown', desc='', note=f'symbol {pre}'), 'SYMBOL (not in any legend)'
    return dict(hclass='Q', texture='unknown', cover='unknown', ice_rich='unknown', desc='', note='?'), 'UNRESOLVED'


def gsc_legacy(fam, ofs=GSC_OFS):
    units, rows, log = [], {}, []
    for label, d, scale, year, name, nts in ofs:
        d = f'{G}/{d}'
        p = sorted(glob.glob(f'{d}/data/shp/**/geo*_ply.shp', recursive=True))[0]
        df = pyogrio.read_dataframe(p)
        epsg = legacy_crs(d)
        df = df.set_crs(epsg, allow_override=True)
        if 'GEO_TYPE' in df:
            df = df[df['GEO_TYPE'].astype(str).str.upper().str.strip() == 'GEO']
        leg = LL.read_legend(d)
        code = df['CODE'].astype(str).str.strip()
        hows = {}
        for c in code.unique():
            k = f'{label}|{c}'
            w = LL.word_class(c)
            if w:
                rows[k] = [k, w, '', 'unknown', 'unknown', 'unknown', f'{label} {c}: whole-word label']
                continue
            a, b = split_code(c)
            e1, how1 = legend_comp(a, leg, fam)
            h2 = legend_comp(b, leg, fam)[0]['hclass'] if b else ''
            hows[c] = how1
            note = f'{label} {c}: {a} -> {e1["hclass"]} ({how1}: {e1["note"][:70]})'
            if b:
                note += f'; 2nd component {b} -> {h2}'
            if re.search(r'ground ice|permafrost', e1.get('desc', ''), re.I):
                note += '; legend: may be underlain by ground ice / permafrost'
            if re.search(r'thermokarst', e1.get('desc', ''), re.I):
                note += '; legend: thermokarst terrain'
            rows[k] = [k, e1['hclass'], '' if h2 == e1['hclass'] else h2, e1['texture'], e1['cover'],
                       e1['ice_rich'], note.replace(',', ';')]
        df['xkey'] = label + '|' + code
        df['code'] = code
        df['desc'] = [(rows[k][6] if k in rows else '') for k in df['xkey']]
        df['scale'], df['year'], df['sheet'] = scale, year, label
        df = S.in_amap(S.polygons_only(df.to_crs(S.CRS)))
        units.append(df)
        nleg = sum(1 for c in code.unique() if hows.get(c) == 'legend')
        odd = {c: h for c, h in hows.items() if h != 'legend'}
        log.append(f'{label} {name} {nts} 1:{scale} {year}: {len(df)} polys in domain, EPSG:{epsg}, '
                   f'{len(leg)} legend units, {nleg}/{code.nunique()} codes primary-from-own-legend, other {odd}')
        print(log[-1], flush=True)
    return units, rows, log


def gsc_series_legend():
    """union of the 14 NE-BC legends (same unit scheme); a classified entry beats an unclassified one."""
    fam = {}
    for _, d, *_ in GSC_OFS:
        for k, v in LL.read_legend(f'{G}/{d}').items():
            if k not in fam or (fam[k]['note'].startswith('UNCLASSIFIED') and not v['note'].startswith('UNCLASSIFIED')):
                fam[k] = v
    return fam


def gsc_of2270():
    """OF D2270 93N surficial geology (SGNP93N = Map 1987A, 1:250k), NAD27 UTM 10 (DOC/HTML/PARA_D.HTM)."""
    p = f'{G}/of2270/DATA/SHP/NTS93N/SGNP93N.SHP'
    df = pyogrio.read_dataframe(p).set_crs(26710, allow_override=True)
    rows = {}
    for (c, dep, nm, tx, cp), _ in df.groupby(['CODE', 'DEPOSIT', 'NAME', 'TEXTURE', 'COMP'], dropna=False):
        k = f'OF2270|{c}'
        # texture / cover from the unit NAME + TEXTURE field only: COMP mentions capping veneers and minor
        # components ('Au ... with lesser silt and diamicton', 'At ... overlain by a veneer of sand and silt')
        tex, cov, ice = LL.attrs(f'{nm}: {tx}' + ('; peat' if re.search(r'peat|muck', str(cp)) else ''))
        h = DEP2270.get(str(dep).strip())
        assert h, (c, dep)
        rows.setdefault(k, [k, h, '', tex, cov, ice,
                            f'OF D2270 93N {c} {nm}: DEPOSIT {dep}; texture {tx}'.replace(',', ';')])
    df['xkey'] = 'OF2270|' + df['CODE'].astype(str).str.strip()
    df['code'] = df['CODE'].astype(str).str.strip()
    df['desc'] = (df['NAME'].astype(str) + ' | ' + df['TEXTURE'].astype(str) + ' | ' + df['COMP'].astype(str) + ' | '
                  + df['DEPOSIT'].astype(str))
    df['scale'], df['year'], df['sheet'] = 250_000, 2001, 'OF2270_093N'
    df = S.in_amap(S.polygons_only(df.to_crs(S.CRS)))
    print(f'OF2270_093N 1:250k (Map 1987A, Plouffe 2000; OF D2270 2001): {len(df)} polys in domain, '
          f'{df["CODE"].nunique()} codes', flush=True)
    return df, rows


def gsc_eof2011():
    """BC Energy OF 2011-2: GSC terrain symbols (Ap, GLv, GFp, Tv, R, 'Er_T', 'GLv_Tb', Lake, River), EPSG:26910."""
    df = pyogrio.read_dataframe(f'{G}/eof2011-2/Spatial/Shapes_geology/geology_polygons.shp')
    code = df['MAP_CODE'].astype(str).str.strip()
    rows = {}
    for c in code.unique():
        k = f'EOF2011-2|{c}'
        if c.upper() in ('LAKE', 'RIVER', 'WATER'):
            rows[k] = [k, 'H', '', 'unknown', 'unknown', 'unknown', f'EOF 2011-2 {c}: water body']
            continue
        a, b = split_code(c, sep='_')
        g1 = CO.gen_caps(a)
        h1 = GSC_SYM.get(g1)
        h2 = GSC_SYM.get(CO.gen_caps(b), '') if b else ''
        assert h1, c
        suf = a[len(g1):]
        cov = 'veneer' if suf.startswith('v') else ('blanket' if suf.startswith('b') else 'unknown')
        tex = {'E': 'sand', 'O': 'organic'}.get(h1, 'unknown')
        rows[k] = [k, h1, '' if h2 == h1 else h2, tex, cov, 'unknown',
                   f'EOF 2011-2 {c}: GSC terrain symbol {g1} (genetic) + {suf or "-"}'
                   + (f'; 2nd component {b} -> {h2}' if b else '')]
    df['xkey'] = 'EOF2011-2|' + code
    df['code'] = code
    df['desc'] = [rows[k][6] for k in df['xkey']]
    df['scale'], df['year'], df['sheet'] = 250_000, 2011, 'EOF2011-2'
    df = S.in_amap(S.polygons_only(df.to_crs(S.CRS)))
    print(f'EOF2011-2 (094A+093P) 1:250k: {len(df)} polys in domain, {code.nunique()} codes', flush=True)
    return df, rows


def in_legacy(label):
    """the 14 NE-BC OF packages were ALREADY staged as raw/canada/gsc/<label> by the OSTR census and are merged in
    ca_gsc_legacy (ingest_canada.legacy): re-ingesting them here would duplicate those sheets."""
    return os.path.isdir(f'{S.RAW}/canada/gsc/{label}')


def gsc():
    src = 'ca_gsc_bc_ofs'
    fam = gsc_series_legend()
    keep = os.environ.get('BCG_KEEP_LEGACY_DUPS') == '1'
    dup = [lab for lab, *_ in GSC_OFS if in_legacy(lab)]
    print('already in ca_gsc_legacy (raw/canada/gsc/<label>), NOT re-ingested:' if not keep else
          'already in ca_gsc_legacy, re-ingested anyway (BCG_KEEP_LEGACY_DUPS=1):', dup, flush=True)
    units, rows, log = gsc_legacy(fam, [o for o in GSC_OFS if keep or o[0] not in dup])
    d2, r2 = gsc_of2270()
    d3, r3 = gsc_eof2011()
    rows.update(r2)
    rows.update(r3)
    parts = []
    for df in units + [d2, d3]:
        if df.empty:
            continue
        lic = BC_COPY if df['sheet'].iat[0] == 'EOF2011-2' else OGL_CA
        red = 'internal_only' if lic == BC_COPY else 'open'
        u, _ = S.standardise(df, src_id=src, code='code', desc='desc', sheet='sheet', xkey='xkey',
                             scale_den='scale', pub_year='year', conf_tier='Surficial',
                             licence=lic, redistribution=red)
        parts.append(u)
    u = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    used = set(u['xkey'])
    write_source(src, u, [r for r in rows.values() if r[0] in used],
                 dict(title='GSC surficial geology maps, central / NE BC: 093N (OF D2270 = Map 1987A) and 094A+093P '
                            '(BC Energy OF 2011-2)',
                      scale_note='1:250k (093N OF D2270; 094A+093P BC EOF 2011-2)'
                                 + ('; + 1:50k/1:100k 094P/094I OFs' if keep else ''),
                      log=log, not_reingested_in_ca_gsc_legacy=dup if not keep else []))


def legacy_compare():
    """The 14 094P/094I OFs, classified here (legend per component, composite codes split) vs ca_gsc_legacy as
    merged (composite 'A-B' / 'A/B' codes are absent from the legend tables -> terrain-symbol key LBL:<caps>:
    'Lb-O', 'Lv-Tr' -> LBL:L = lacustrine, though Lb/Lv are GLACIOLACUSTRINE in this legend; hclass2 lost).
    Writes work/bcgroupc/legacy_compare.csv (per sheet+code) and legacy_composite_fix.csv (proposed rows)."""
    fam = gsc_series_legend()
    _, rows, _ = gsc_legacy(fam)
    mine = pd.DataFrame(list(rows.values()), columns=XWCOLS)
    mine[['src_sheet', 'src_code']] = mine['xkey'].str.split('|', n=1, expand=True)
    labs = [lab for lab, *_ in GSC_OFS]
    L = pyogrio.read_dataframe(f'{S.WORK}/xw/ca_gsc_legacy.gpkg', layer='units',
                               columns=['src_sheet', 'src_code', 'hclass', 'hclass2', 'xwalk_note'],
                               where='src_sheet IN (' + ','.join(f"'{x}'" for x in labs) + ')')
    L['km2'] = L.area / 1e6
    g = (L.groupby(['src_sheet', 'src_code', 'hclass', 'hclass2'], dropna=False)['km2'].agg(['size', 'sum'])
         .reset_index().rename(columns={'size': 'n', 'sum': 'km2'}))
    m = g.merge(mine[['src_sheet', 'src_code', 'hclass', 'hclass2', 'xwalk_note']], on=['src_sheet', 'src_code'],
                how='left', suffixes=('_legacy', '_here'))
    m['composite'] = m['src_code'].str.contains(r'[-/]')
    m['agree'] = m['hclass_legacy'] == m['hclass_here']
    m.sort_values('km2', ascending=False).to_csv(f'{WB}/legacy_compare.csv', index=False)
    tot = m['km2'].sum()
    print(f'14 OFs as merged in ca_gsc_legacy: {tot:.0f} km2 (H/water excluded from nothing); primary hclass agreement '
          f'{(m.km2 * m.agree).sum() / tot:.3f}; composite codes {m.loc[m.composite, "km2"].sum():.0f} km2, '
          f'of which agreeing {(m.km2 * m.agree)[m.composite].sum() / max(m.loc[m.composite, "km2"].sum(), 1):.3f}')
    dis = m[~m.agree].groupby(['hclass_legacy', 'hclass_here'])['km2'].sum().sort_values(ascending=False).round(1)
    print('disagreements (legacy -> here) km2:', dis.to_dict())
    print('hclass2 set here for composite codes:', round(m.loc[m.composite & m.hclass2_here.fillna('').ne(''), 'km2'].sum()), 'km2')
    bad = set(zip(m.loc[~m.agree, 'src_sheet'], m.loc[~m.agree, 'src_code']))
    fix = mine[mine['src_code'].str.contains(r'[-/]')
               | pd.Series([(a, b) in bad for a, b in zip(mine['src_sheet'], mine['src_code'])], index=mine.index)]
    fix[XWCOLS].to_csv(f'{WB}/legacy_composite_fix.csv', index=False)
    print(f'proposed rows for xwalk/ca_gsc_legacy.csv (composites + disagreeing codes; NOT applied): {len(fix)} -> '
          f'{WB}/legacy_composite_fix.csv')


# --------------------------------------------------------------------------------------------------- TEM / PEM
def e00_uncompress(src, dst):
    """Compressed E00 ('EXP  1': e00compr levels 1-2, which GDAL's AVCE00 driver refuses) -> plain E00.
    Port of e00compr's _UncompressNextLine (e00read.c): physical line breaks are not data; '~}' = end of line,
    '~ c' = (c - 32) spaces, '~~' / '~-' = escaped char, '~c d1 d2 ...' = number (c - 33: decimal position % 15,
    exponent sign (c - 33) // 15 % 3, odd digit count (c - 33) // 45; each d = two digits, '}' + d for 92..99);
    after a number a '~' that starts no code only terminates it."""
    with open(src, 'rb') as f:
        head = f.readline()
        data = f.read().replace(b'\r', b'').replace(b'\n', b'')
    out = bytearray(head.rstrip(b'\r\n').replace(b'EXP  1', b'EXP  0', 1) + b'\n')
    n, i, prev_num = len(data), 0, False
    find = data.find
    while i < n:
        j = find(b'~', i)
        if j < 0:
            j = n
        if j > i:
            out += data[i:j]
            prev_num = False
            i = j
            continue
        if i + 1 >= n:
            break
        c = data[i + 1]
        i += 2
        if c == 32:                              # '~ ' + space count
            if i >= n:
                break
            out += b' ' * (data[i] - 32)
            i += 1
            prev_num = False
        elif c == 125:                           # '~}' end of line
            out += b'\n'
            prev_num = False
        elif prev_num:                           # '~' only ended the previous number
            out.append(c)
            prev_num = False
        elif c in (126, 45):                     # '~~', '~-'
            out.append(c)
        elif 33 <= c <= 122:                     # numeric code
            m = c - 33
            dec, odd, e = m % 15, m // 45, (m // 15) % 3
            dg, cur = bytearray(), 0
            while i < n and data[i] != 32 and data[i] != 126:
                v = data[i] - 33
                i += 1
                if v == 92 and i < n:
                    v += data[i] - 33
                    i += 1
                for dd in (v // 10, v % 10):
                    dg.append(48 + dd)
                    cur += 1
                    if cur == dec:
                        dg.append(46)
            prev_num = i < n
            if odd:
                del dg[-1]
            if e:
                dg[-2:-2] = b'E+' if e == 1 else b'E-'
            out += dg
        else:
            raise ValueError(f'{src}: bad E00 code {c!r} at byte {i}')
    with open(dst, 'wb') as f:
        f.write(out)
    tail = bytes(out[-200:]).split(b'\n')
    assert any(t.startswith(b'EOS') for t in tail), f'{dst}: no EOS line'
    print(f'  uncompressed {os.path.basename(src)} -> {os.path.basename(dst)}: {len(out) / 1e6:.0f} MB, '
          f'{out.count(10)} lines', flush=True)
    return dst


def e00_plain(path):
    with open(path, 'rb') as f:
        h = f.read(6)
    if h != b'EXP  1':
        return path
    dst = path[:-4] + '.unc.e00'
    if not (os.path.exists(dst) and os.path.getmtime(dst) > os.path.getmtime(path)):
        e00_uncompress(path, dst)
    return dst


def e00_polygons(path):
    """e00 coverage -> polygons with the label-point (PAT) attributes: shapely polygonize of the ARC layer, each face
    takes the attributes of the LAB point it contains. Checked against the PAT AREA of every polygon."""
    t0 = time.time()
    path = e00_plain(path)
    arcs = pyogrio.read_dataframe(path, layer='ARC', columns=['LPOLY_', 'RPOLY_'])
    lab = pyogrio.read_dataframe(path, layer='LAB')
    crs = arcs.crs
    faces = np.asarray(shapely.get_parts(shapely.polygonize(arcs.geometry.values)))
    tree = shapely.STRtree(faces)
    li, fi = tree.query(lab.geometry.values, predicate='within')
    # a label point on the boundary of two faces is not 'within' either: nearest face for those
    hit = pd.Series(fi, index=li)
    nolab = np.setdiff1d(np.arange(len(lab)), li)
    if len(nolab):
        ni, nf = tree.query_nearest(lab.geometry.values[nolab], all_matches=False)
        hit = pd.concat([hit, pd.Series(nf, index=nolab[ni])])
    hit = hit[~hit.index.duplicated()]
    g = lab.drop(columns='geometry').iloc[hit.index].copy()
    g['face'] = hit.values
    dup = int(g['face'].duplicated().sum())
    g = g.drop_duplicates('face')
    g = gpd.GeoDataFrame(g, geometry=faces[g['face'].values], crs=crs)
    a = g.geometry.area
    rel = (a - g['AREA']).abs() / g['AREA'].clip(lower=1)
    unl = float(shapely.area(faces[np.setdiff1d(np.arange(len(faces)), g['face'].values)]).sum() / 1e6)
    print(f'  {os.path.basename(path)}: {len(arcs)} arcs, {len(faces)} faces, {len(lab)} labels, {len(g)} labelled '
          f'faces ({dup} faces with >1 label), unlabelled faces {unl:.2f} km2; face/PAT area: median rel err '
          f'{rel.median():.2e}, >1% for {int((rel > 0.01).sum())}; {time.time() - t0:.0f} s', flush=True)
    return g


def ter_label(r, i):
    """BC TCS component label from the CSV fields, e.g. '6zsFGAt'."""
    f = lambda c: str(r.get(c, '') or '').strip()  # noqa: E731
    s = (f(f'TTEX_{i}A') + f(f'TTEX_{i}B') + f(f'TTEX_{i}C') + f(f'SURFM_{i}') + f(f'SURFM_Q{i}')
         + f(f'SURF_E{i}A') + f(f'SURF_E{i}B') + f(f'SURF_E{i}C'))
    return (f(f'TDEC_{i}') + s) if s else ''


def norm_mat(m):
    m = str(m or '').strip()
    if not m:
        return ''
    if m in MAT:
        return m
    return m[0] if m[0] in MAT else '?'


def tem_frame(e00, csvs, sheet_of_csv, scale, year, survey_years, extra_cols):
    g = e00_polygons(e00)
    tagc = [c for c in g.columns if c.upper().endswith('_TAG')][0]
    g[tagc] = g[tagc].astype(str).str.strip()
    parts = []
    for c in csvs:
        d = pd.read_csv(c, dtype=str, keep_default_na=False)
        k = [x for x in d.columns if x.endswith('_TAG')][0]
        d = d.rename(columns={k: tagc})
        d['sheet'] = sheet_of_csv[os.path.basename(c)]
        parts.append(d)
    d = pd.concat(parts, ignore_index=True)
    ndup = int(d[tagc].duplicated().sum())
    d = d.drop_duplicates(tagc)
    m = g.merge(d, on=tagc, how='left')
    nmiss = int(m['sheet'].isna().sum())
    amiss = float(m.loc[m['sheet'].isna()].area.sum() / 1e6)
    print(f'  join: {len(m) - nmiss}/{len(m)} polygons matched a CSV row ({nmiss} unmatched, {amiss:.1f} km2 '
          f'dropped); {ndup} duplicate tags across CSVs', flush=True)
    m = m[m['sheet'].notna()].copy()
    m['m1'] = m['SURFM_1'].map(norm_mat)
    m['m2'] = m['SURFM_2'].map(norm_mat)
    m.loc[m['m1'] == '', 'm1'] = 'N'
    m['xkey'] = m['m1'] + '|' + m['m2']
    m['texture_src'] = m['TTEX_1A'].map(lambda s: TEX.get(str(s).strip()[:1], 'unknown') if str(s).strip() else 'unknown')
    m['cover_src'] = m['SURF_E1A'].map(lambda s: 'veneer' if str(s).strip()[:1] in ('v', 'x')
                                       else ('blanket' if str(s).strip()[:1] == 'b' else 'unknown'))
    recs = m.to_dict('records')
    m['code'] = [' / '.join(x for x in (ter_label(r, 1), ter_label(r, 2), ter_label(r, 3)) if x) for r in recs]
    m['desc'] = [f'BC TCS: {r["m1"]} ({r.get("TDEC_1", "")}/10)' + (f', {r["m2"]} ({r.get("TDEC_2", "")}/10)'
                                                                     if r['m2'] else '') for r in recs]
    m['scale'], m['year'], m['survey_years'] = scale, year, survey_years
    for c in extra_cols:
        if c not in m:
            m[c] = ''
    m = S.in_amap(S.polygons_only(m.to_crs(S.CRS)))
    return m


def tem():
    src = 'ca_bc_tem_extra'
    ex = ['FCODE', 'TDEC_1', 'TDEC_2', 'SURFM_3', 'SURFM_Q1', 'MAPSH_NBR', 'FLDCHKTP', 'SOURCE']
    st = tem_frame(f'{G}/sustut_takla_4048/tem_4048_ecp.e00',
                   sorted(glob.glob(f'{G}/sustut_takla_4048/tem_4048_ecp0?.csv')),
                   {'tem_4048_ecp01.csv': 'TEM4048 Sustut', 'tem_4048_ecp02.csv': 'TEM4048 Sustut',
                    'tem_4048_ecp03.csv': 'TEM4048 Takla'}, 20_000, 2004, '2003-2004', ex)
    mk = []
    for i in (1, 2):
        mk.append(tem_frame(f'{G}/mk_pem_4016/pem_4016_ecp0{i}.e00', [f'{G}/mk_pem_4016/pem_4016_ecp0{i}.csv'],
                            {f'pem_4016_ecp0{i}.csv': f'PEM4016 MK area {i}'}, 50_000, 2002, None, ex))
    df = gpd.GeoDataFrame(pd.concat([st] + mk, ignore_index=True), crs=S.CRS)
    u, _ = S.standardise(df, src_id=src, code='code', desc='desc', sheet='sheet', xkey='xkey', scale_den='scale',
                         pub_year='year', survey_years='survey_years', extra=tuple(ex),
                         carry=('texture_src', 'cover_src'), licence=BC_COPY, redistribution='internal_only')
    rows = []
    for k in sorted(u['xkey'].unique()):
        a, b = k.split('|')
        h, t = MAT.get(a, ('DROP', 'unknown'))
        h2 = MAT.get(b, ('', ''))[0] if b else ''
        h2 = '' if h2 in ('DROP', h) else h2
        note = f'BC TCS material {a} (2nd component {b or "-"})'
        if a == 'N':
            note += (' - not classified (non-terrain; in the PEM e00 these carry FCODE XX00000000; mostly water): '
                     'dropped as in ca_bc_ter')
        rows.append([k, h, h2, t, 'unknown', 'unknown', note])
    write_source(src, u, rows, dict(title='BC bioterrain/PEM terrain: Sustut-Takla TEM (BAPID 4048, 1:20k) + '
                                          'Muskwa-Kechika PEM areas 1-2 (BAPID 4016, 1:50k)',
                                    scale_note='1:20k Sustut-Takla bioterrain (TSIL D); 1:50k MK PEM'), coarse=250.0)


# --------------------------------------------------------------------------------------------------- soil surveys
# BC soil 'mode of deposition' of the component's parent material (SIFT codes present in the group-C download;
# organic codes checked against the soil great groups: FNPT/SPPT/UNDO carry Mesisols/Fibrisols, UNDM Regosols)
MDEP = {
    'TILL': ('T', 'till (morainal)'), 'COLL': ('C', 'colluvium'), 'FLUV': ('F', 'fluvial'),
    'GLFL': ('GF', 'glaciofluvial'), 'GLLC': ('GL', 'glaciolacustrine'), 'LACU': ('L', 'lacustrine'),
    'EOLI': ('E', 'eolian'), 'FNPT': ('O', 'fen peat'), 'SPPT': ('O', 'sphagnum peat'),
    'UNDO': ('O', 'undifferentiated organic'), 'UNDM': ('Q', 'undifferentiated mineral'),
    'VOLC': ('V', 'volcanic (tephra)'), 'ANTH': ('X', 'anthropogenic'),
    'MARI': ('M', 'marine'), 'GLMA': ('GM', 'glaciomarine'),
}
# MDEP_1 null or '-': the dominant 'soil' is a miscellaneous land type named in SOILNAME_1
SOILNAME_CLASS = [(r'OPEN WATER|^LAKE|^RIVER|^POND|^WATER', 'H'),
                  (r'BEDROCK|^ROCK', 'R'), (r'GLACIER|^ICE|ICEFIELD|SNOW', 'I'),
                  (r'ANTHROPOGENIC|GRAVEL PIT|CUT AND FILL|URBAN', 'X'), (r'^TALU?S?$|TALUS', 'C'),
                  (r'^MARL$', 'L'), (r'RECENT BARS', 'F')]
SOIL_SCALE_FIX = {'Peace River Area Soil Maps (unpublished) (1:None)': 250_000}   # no scale stated: ranked as 1:250k


def soil():
    src = 'ca_bc_soil'
    fs = sorted(glob.glob(f'{G}/bc_soil_wfs/*_p*.geojson'))
    parts = [pyogrio.read_dataframe(f) for f in fs]
    df = gpd.GeoDataFrame(pd.concat([p for p in parts if len(p)], ignore_index=True), crs=parts[0].crs)
    if df.crs is None or df.crs.to_epsg() != 3005:
        df = df.set_crs(3005, allow_override=True)
    n0 = len(df)
    df = df.drop_duplicates('OBJECTID')
    print(f'soil: {len(fs)} pages, {n0} features, {len(df)} unique OBJECTID, {df["PROJ_NAME"].nunique()} surveys',
          flush=True)
    for i in (1, 2, 3):
        df[f'MDEP_{i}'] = df[f'MDEP_{i}'].fillna('').astype(str).str.strip().str.upper().replace('-', '')
        df[f'SOILNAME_{i}'] = df[f'SOILNAME_{i}'].fillna('').astype(str).str.strip()
    # series lookup (whole download, before the clip): a soil series (first 5 chars of the symbol, BCxxx) whose
    # every other SIFT polygon (>= 3) carries ONE mode of deposition lends it to its MDEP-less polygons
    s5 = df['SOILSYM_1'].fillna('').astype(str).str.strip().str[:5]
    kn = df[(df['MDEP_1'] != '') & (s5.str.len() == 5)].assign(s5=s5)
    st = kn.groupby('s5')['MDEP_1'].agg(['nunique', 'size', 'first'])
    look = st[(st['nunique'] == 1) & (st['size'] >= 3)]['first'].to_dict()
    df['s5'] = s5
    boxes = groupc_boxes(3005)
    clip = shapely.union_all(boxes.geometry.values)
    df['geometry'] = shapely.make_valid(df.geometry.values)
    df = df[shapely.intersects(df.geometry.values, clip)].copy()
    df['geometry'] = shapely.intersection(df.geometry.values, clip)
    df = S.polygons_only(df)
    sc = df['PROJ_NAME'].astype(str).str.extract(r'1\s*:\s*([\d,\s]+)\)?')[0].str.replace(r'[,\s]', '', regex=True)
    df['scale'] = pd.to_numeric(sc, errors='coerce').fillna(df['PROJ_NAME'].map(SOIL_SCALE_FIX))
    assert df['scale'].notna().all(), df.loc[df['scale'].isna(), 'PROJ_NAME'].unique()
    # pub_year: the latest year named in the survey title (most titles name none -> 0 in the merge ranking)
    yrs = df['PROJ_NAME'].astype(str).str.findall(r'\b(19[4-9]\d|20[0-2]\d)\b')
    df['year'] = yrs.map(lambda v: max(int(x) for x in v) if len(v) else np.nan)
    print(' scale from PROJ_NAME:', df['scale'].value_counts(dropna=False).to_dict(),
          '| years:', df['year'].value_counts(dropna=False).to_dict(), flush=True)
    nm = df['SOILNAME_1'].str.upper()

    def key1(m, s, n):
        if m:
            return m
        if s in look:
            return 'SERIES>' + look[s]
        for pat, h in SOILNAME_CLASS:
            if re.search(pat, n):
                return 'NAME>' + h
        return 'NOMDEP'
    df['k1'] = [key1(m, s, n) for m, s, n in zip(df['MDEP_1'], df['s5'], nm)]
    df['xkey'] = df['k1'] + '|' + df['MDEP_2']
    df['code'] = df['SOILSYM_1'].fillna('').astype(str).str.strip()
    f = lambda v: '' if v is None or (isinstance(v, float) and np.isnan(v)) else str(v)  # noqa: E731
    df['desc'] = [f'{a} {f(p1)}% {m1 or "-"} {f(t1)}' + (f'; {b} {f(p2)}% {m2 or "-"} {f(t2)}' if b else '')
                  for a, p1, m1, t1, b, p2, m2, t2 in zip(df['SOILNAME_1'], df['PERCENT_1'], df['MDEP_1'],
                                                           df['TEXTURE_1'], df['SOILNAME_2'], df['PERCENT_2'],
                                                           df['MDEP_2'], df['TEXTURE_2'])]
    df['sheet'] = df['PROJ_NAME'].astype(str)
    df = S.in_amap(S.polygons_only(df.to_crs(S.CRS)))
    ex = ('BAPID', 'SIFT_ID', 'PROJ_TYPE', 'PERCENT_1', 'TEXTURE_1', 'DRAIN_1', 'COFRAG_1', 'DEV_1', 'MDEP_3',
          'LEGEND_URL')
    u, _ = S.standardise(df, src_id=src, code='code', desc='desc', sheet='sheet', xkey='xkey', scale_den='scale',
                         pub_year='year', extra=ex, licence=OGL_BC, redistribution='open')
    rows, unk = [], {}
    for k in sorted(u['xkey'].unique()):
        a, b = k.split('|')
        h2 = MDEP.get(b, ('', ''))[0] if b else ''
        if a == 'NOMDEP':
            rows.append([k, 'DROP', '', 'unknown', 'unknown', 'unknown',
                         'no mode of deposition for the dominant soil and no land-type name: not classified; dropped'])
            continue
        if a.startswith('NAME>'):
            h = a[5:]
            rows.append([k, h, '' if h2 == h else h2, 'unknown', 'unknown', 'unknown',
                         f'no MDEP_1; miscellaneous land type named in SOILNAME_1 -> {h}'])
            continue
        via = ''
        if a.startswith('SERIES>'):
            a, via = a[7:], '; MDEP_1 missing: mode of deposition of the same soil series in all its other SIFT polygons'
        h, nm1 = MDEP.get(a, (None, None))
        if h is None:
            unk[a] = int((u['xkey'] == k).sum())
            h, nm1 = 'Q', 'UNMAPPED CODE'
        rows.append([k, h, '' if h2 == h else h2, 'organic' if h == 'O' else 'unknown', 'unknown', 'unknown',
                     f'soil survey MDEP_1 {a} ({nm1})' + (f'; MDEP_2 {b} -> {h2}' if b else '') + via])
    if unk:
        print(' MDEP codes NOT in the MDEP table (set to Q, FIX):', unk, flush=True)
    write_source(src, u, rows, dict(title='BC soil surveys (SIFT, STE_SOIL_SURVEYS_MVW), group-C NTS boxes',
                                    scale_note='per survey, from the survey name (1:NNNNN)'), coarse=250.0)


# --------------------------------------------------------------------------------------------------- gain
def cls_of(s):
    return np.select([s <= 100_000, s <= 260_000, s <= 700_000, s <= 1_500_000], [1, 2, 3, 4], 5)


def nts250(lon, lat):
    """NTS 1:250k code south of 68 N (ca_missing_nts.nts)."""
    W, N = -np.asarray(lon, float), np.asarray(lat, float)
    col = np.floor((W - 48) / 8).astype(int)
    row = np.floor((N - 40) / 4).astype(int)
    ri = np.floor(N - np.floor(N / 4) * 4).astype(int)
    ce = np.floor((W - (48 + 8 * col)) / 2).astype(int)
    k = np.choose(ri, [ce, 4 + (3 - ce), 8 + ce, 12 + (3 - ce)])
    return np.char.add(np.char.zfill((col * 10 + row).astype(str), 3), np.array(list('ABCDEFGHIJKLMNOP'))[k])


def gain(srcs):
    import rasterio
    import rasterio.features as rf
    from affine import Affine
    from pyproj import Transformer
    srcs = srcs or ['ca_gsc_bc_ofs', 'ca_bc_tem_extra', 'ca_bc_soil']
    r = rasterio.open(f'{S.OUT}/coverage_class.tif')
    cls = r.read(1)
    tf = r.transform
    F, cell = 10, abs(tf.a * tf.e) / 1e6                  # 250 m sub-pixels on the 2.5 km class grid
    us = {s: gpd.read_file(f'{S.WORK}/xw/{s}.gpkg', layer='units') for s in srcs}
    x0, y0, x1, y1 = np.array([u.total_bounds for u in us.values()]).T
    c0, r0 = int(np.floor((x0.min() - tf.c) / tf.a)) - 1, int(np.floor((tf.f - y1.max()) / -tf.e)) - 1
    c1, r1 = int(np.ceil((x1.max() - tf.c) / tf.a)) + 1, int(np.ceil((tf.f - y0.min()) / -tf.e)) + 1
    c0, r0, c1, r1 = max(c0, 0), max(r0, 0), min(c1, cls.shape[1]), min(r1, cls.shape[0])
    sub = cls[r0:r1, c0:c1]
    ftf = Affine(tf.a / F, 0, tf.c + c0 * tf.a, 0, tf.e / F, tf.f + r0 * tf.e)
    shp = ((r1 - r0) * F, (c1 - c0) * F)
    rr, cc = np.mgrid[r0:r1, c0:c1]
    xs, ys = tf.c + (cc + 0.5) * tf.a, tf.f + (rr + 0.5) * tf.e
    lon, lat = Transformer.from_crs(S.CRS, 4326, always_xy=True).transform(xs, ys)
    nts = nts250(lon, lat)
    newcls = {}
    rows = []
    for s, u in us.items():
        u = u[u.geometry.notna()].copy()
        sd = pd.to_numeric(u['scale_den']).astype(float)
        assert sd.notna().all(), f'{s}: units without scale_den'
        u['sc'] = cls_of(sd.values)
        best = np.zeros(shp, np.uint8)
        for k in sorted(u['sc'].unique(), reverse=True):     # coarse first, finer overwrite
            b = rf.rasterize(((g, 1) for g in u.loc[u['sc'] == k].geometry.values), out_shape=shp, transform=ftf,
                             fill=0, dtype='uint8')
            best[b == 1] = k
        newcls[s] = best
        rows += tally(s, best, sub, nts, F, cell)
        print(s, 'rasterised', flush=True)
    allb = np.zeros(shp, np.uint8)
    for b in newcls.values():
        m = (b > 0) & ((allb == 0) | (b < allb))
        allb[m] = b[m]
    rows += tally('ALL_NEW', allb, sub, nts, F, cell)
    t = pd.DataFrame(rows)
    t['groupC'] = t['nts'].isin(GC['nts'])
    t.to_csv(f'{WB}/gain_by_sheet.csv', index=False)
    tot = t.groupby('src')[['total_km2', 'in_domain_km2', 'gap_km2', 'upgrade_km2', 'unmapped_km2']].sum().round(0)
    tot_c = t[t.groupC].groupby('src')[['in_domain_km2', 'gap_km2', 'upgrade_km2']].sum().round(0)
    tot = tot.join(tot_c.add_prefix('groupC_'))
    tot.to_csv(f'{WB}/gain_by_source.csv')
    pd.set_option('display.width', 250)
    print(tot.to_string())
    piv = t[t.groupC].pivot_table(index='nts', columns='src', values='gap_km2', aggfunc='sum').fillna(0).round(0)
    piv = piv.join(GC.set_index('nts')['fallback_km2']).sort_values('fallback_km2', ascending=False)
    piv.to_csv(f'{WB}/gain_gap_groupC.csv')
    print(piv.to_string())


def tally(src, best, sub, nts, F, cell):
    """km2 per NTS sheet: total, in the domain (class grid > 0), on class-5 cells (gap), on cells coarser than the
    new unit's own class (upgrade; unmapped class 6 included), on class-6 cells."""
    nr, nc = sub.shape
    out = []
    frac = {}
    for k in (1, 2, 3, 4, 5):
        m = (best == k).reshape(nr, F, nc, F).sum((1, 3)) / F ** 2
        if m.any():
            frac[k] = m
    if not frac:
        return out
    tot = sum(frac.values())
    up = sum(f * (sub > k) for k, f in frac.items())
    dfm = pd.DataFrame(dict(nts=nts.ravel(), total=tot.ravel() * cell, dom=(tot * (sub > 0)).ravel() * cell,
                            gap=(tot * (sub == 5)).ravel() * cell, upg=up.ravel() * cell,
                            unm=(tot * (sub == 6)).ravel() * cell))
    dfm = dfm[dfm.total > 0].groupby('nts').sum()
    for n, r in dfm.iterrows():
        out.append(dict(src=src, nts=n, total_km2=r.total, in_domain_km2=r.dom, gap_km2=r.gap, upgrade_km2=r.upg,
                        unmapped_km2=r.unm))
    return out


# --------------------------------------------------------------------------------------------------- stats
def stats():
    """per new source: polygons, km2 (all / inside the build domain), scale range, hclass shares (domain km2),
    dropped units (std rows the crosswalk drops)."""
    dom = S.amap_geom()
    out = []
    for s in ('ca_gsc_bc_ofs', 'ca_bc_tem_extra', 'ca_bc_soil'):
        u = gpd.read_file(f'{S.WORK}/xw/{s}.gpkg', layer='units')
        st = gpd.read_file(f'{S.STD}/{s}.gpkg', layer='units', columns=['xkey', 'src_sheet'])
        xw = S.load_xwalk(s).set_index('xkey')['hclass']
        drop = st[st['xkey'].map(xw).eq('DROP')]
        g = u.geometry.values
        inside = shapely.within(g, dom)
        a_in = np.where(inside, shapely.area(g), 0.0)
        part = ~inside
        if part.any():
            a_in[part] = shapely.area(shapely.intersection(g[part], dom))
        u['km2_dom'] = a_in / 1e6
        u['km2'] = shapely.area(g) / 1e6
        tot = u['km2_dom'].sum()
        sh = (u.groupby('hclass')['km2_dom'].sum() / tot * 100).round(1).sort_values(ascending=False)
        by = u.groupby('src_sheet').agg(n=('km2', 'size'), km2=('km2', 'sum'), km2_dom=('km2_dom', 'sum'),
                                        scale=('scale_den', 'max'), year=('pub_year', 'max')).round(1)
        rec = dict(src=s, n_polygons=len(u), n_in_domain=int((u['km2_dom'] > 0).sum()), km2=round(u['km2'].sum(), 1),
                   km2_domain=round(tot, 1), scale_min=int(u['scale_den'].min()), scale_max=int(u['scale_den'].max()),
                   n_dropped_std=len(drop), km2_dropped_std=round(float(drop.area.sum() / 1e6), 1),
                   hclass_pct_domain=sh.to_dict())
        out.append(rec)
        print(json.dumps(rec), flush=True)
        pd.set_option('display.width', 250)
        print(by.to_string(), flush=True)
        by.to_csv(f'{WB}/stats_{s}_by_sheet.csv')
    json.dump(out, open(f'{WB}/stats_sources.json', 'w'), indent=1)


# --------------------------------------------------------------------------------------------------- validation
BROAD = {'GF': 'F', 'GL': 'L', 'GM': 'M', 'W': 'C'}


def validate():
    new = ['ca_gsc_bc_ofs', 'ca_bc_tem_extra', 'ca_bc_soil']
    ref = ['ca_bc_ter', 'ca_ab_ags', 'ca_gsc_cgm', 'ca_gsc_legacy', 'ca_ygs_compilation', 'ca_gsc_scans',
           'ca_gsc_lines'] + new
    cols = ['src_id', 'src_sheet', 'hclass', 'hclass2', 'scale_den', 'geometry']
    U = {s: gpd.read_file(f'{S.WORK}/xw/{s}.gpkg', layer='units', columns=cols[:-1]) for s in new}
    out, conf = [], []
    for a in new:
        ua = U[a]
        bb = shapely.box(*ua.total_bounds)
        for b in ref:
            if b == a:
                continue
            p = f'{S.WORK}/xw/{b}.gpkg'
            if not os.path.exists(p):
                continue
            ub = U[b] if b in U else pyogrio.read_dataframe(p, layer='units', columns=cols[:-1],
                                                             bbox=tuple(float(v) for v in ua.total_bounds))
            ub = ub[shapely.intersects(ub.geometry.values, bb)]
            if ub.empty:
                continue
            # only overlaps where the reference is finer or equal in scale (or both new: report both directions)
            ia, ib = shapely.STRtree(ub.geometry.values).query(ua.geometry.values, predicate='intersects')
            if not len(ia):
                continue
            g = shapely.intersection(ua.geometry.values[ia], ub.geometry.values[ib])
            ar = shapely.area(g) / 1e6
            d = pd.DataFrame(dict(sa=ua['src_sheet'].values[ia], ha=ua['hclass'].values[ia],
                                  h2a=ua['hclass2'].fillna('').values[ia], scale_a=ua['scale_den'].values[ia],
                                  sb=ub['src_sheet'].values[ib], hb=ub['hclass'].values[ib],
                                  h2b=ub['hclass2'].fillna('').values[ib], scale_b=ub['scale_den'].values[ib], km2=ar))
            d = d[(d.km2 > 0) & (d.ha != 'H') & (d.hb != 'H')]
            if d.km2.sum() < 1:
                continue
            d['agree'] = d.ha == d.hb
            d['agree12'] = d.agree | (d.ha == d.h2b) | (d.h2a == d.hb)
            d['agree_broad'] = d.ha.map(lambda x: BROAD.get(x, x)) == d.hb.map(lambda x: BROAD.get(x, x))
            for (sa, sb), q in d.groupby(['sa', 'sb']):
                if q.km2.sum() < 1:
                    continue
                out.append(dict(new=a, new_sheet=sa, ref=b, ref_sheet=sb, km2=q.km2.sum(),
                                scale_new=int(q.scale_a.max()), scale_ref=int(q.scale_b.max()),
                                agree=(q.km2 * q.agree).sum() / q.km2.sum(),
                                agree12=(q.km2 * q.agree12).sum() / q.km2.sum(),
                                agree_broad=(q.km2 * q.agree_broad).sum() / q.km2.sum()))
            c = d.groupby(['ha', 'hb'])['km2'].sum().reset_index()
            c.insert(0, 'ref', b)
            c.insert(0, 'new', a)
            conf.append(c)
            print(a, 'vs', b, round(d.km2.sum(), 1), 'km2: primary agreement', round((d.km2 * d.agree).sum()
                                                                                    / d.km2.sum(), 3),
                  'primary-or-secondary', round((d.km2 * d.agree12).sum() / d.km2.sum(), 3), flush=True)
    o = pd.DataFrame(out).round(3)
    o.to_csv(f'{WB}/validate_pairs.csv', index=False)
    pd.concat(conf).round(2).to_csv(f'{WB}/validate_confusion.csv', index=False)
    pd.set_option('display.width', 250)
    print(o.to_string())


if __name__ == '__main__':
    cmd = sys.argv[1]
    {'gsc': gsc, 'tem': tem, 'soil': soil, 'validate': validate, 'stats': stats, 'legacy_compare': legacy_compare,
     'gain': lambda: gain(sys.argv[2:])}[cmd]()
