#!/usr/bin/env python
"""
Canadian territorial / provincial / national ingests -> work/std/<src>.gpkg

  ca_ygs_compilation  Yukon Surficial Geology Compilation (2023): TCS MATERIAL_A +
                      QUALFIER_A key, texture from TEXTURE_1A, cover from EXPRSSN_1A,
                      scale per polygon (MAP_SCALE), one footprint per source map.
                      PRECEDENCE OVERRIDE: Rampton 1982 GSC Map 1503A (Yukon Coastal
                      Plain, field-based) gets conf_tier 'Surficial' so it outranks the
                      equal-scale CGM249 (2017 release of 1970 reconnaissance mapping).
  ca_qc_sigeom        Québec SIGÉOM zones morpho-sédimentologiques (Nunavik); scale not
                      stated by the source -> nominal 1:100,000 (unverified)
  ca_mb_sgcms         Manitoba SGCMS 2017 (compiled 1:50k-1:250k) -> 1:250,000
  ca_on_eds014        Ontario OGS EDS014 Quaternary 1:1,000,000 (internal: MNDM terms)
  ca_gsc_5m           GSC Surficial geology of Canada 1:5,000,000 (backdrop)
  ca_nl_labrador      NL GeoAtlas detailed surficial layer (GSNL 1:50k; internal: GeoAtlas terms)
  ca_gsc_1814a        GSC Map 1814A (Klassen et al. 1992) 1:1M, Labrador and eastern Quebec, GSC release (OGL)
"""
import glob
import os
import sys

import pandas as pd
import geopandas as gpd
import pyogrio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

UNZ = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/canada'
RAWC = f'{S.RAW}/canada'
OGL = 'Open Government Licence - Canada'


def one(p):
    h = sorted(glob.glob(f'{UNZ}/{p}', recursive=True))
    assert h, p
    return h[0]


def per_sheet_fp(u):
    fps = []
    for k, part in u.groupby('src_sheet'):
        f = S.footprint_from_units(part)
        f['src_sheet'] = k
        fps.append(f)
    return gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)


def finish(u, fp, src, meta):
    p, m = S.write_std(u, fp, src, meta)
    S.code_table(u).to_csv(f'{S.WORK}/codes_{src}.csv', index=False)
    print(src, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')}, flush=True)


YTEX = {'a': 'bouldery', 'b': 'bouldery', 'r': 'bouldery', 'k': 'gravel', 'p': 'gravel',
        'g': 'gravel', 'x': 'gravel', 's': 'sand', 'z': 'fines', 'c': 'fines', 'm': 'fines',
        'd': 'mixed', 'e': 'organic', 'u': 'organic', 'h': 'organic'}
YCOV = {'b': 'blanket', 'v': 'veneer'}


def ygs():
    src = 'ca_ygs_compilation'
    g = pyogrio.read_dataframe(one('Surficial_Geology_Polygon.fgdb/*.gdb'), layer='Surficial_Geology_Polygon')
    g = S.in_amap(g.to_crs(S.CRS))
    g['xkey'] = g['MATERIAL_A'].fillna('') + '|' + g['QUALFIER_A'].fillna('')
    g['texture_src'] = g['TEXTURE_1A'].map(YTEX).fillna('unknown')
    g['cover_src'] = g['EXPRSSN_1A'].map(YCOV).fillna('unknown')
    g['scale'] = pd.to_numeric(g['MAP_SCALE'], errors='coerce').fillna(250_000)
    g['year'] = pd.to_numeric(g['MAP_ORIG'].str.extract(r',\s*(\d{4})')[0], errors='coerce')
    g['tier'] = g['MAP_ORIG'].fillna('').str.contains('GSC Map 1503A').map({True: 'Surficial', False: ''})
    u, _ = S.standardise(g, src_id=src, code='LABEL_FNL', desc='LABEL_SIMP', xkey='xkey',
                         sheet='MAP_ORIG', scale_den='scale', pub_year='year', conf_tier='tier',
                         extra=('TEXTURE_1A', 'EXPRSSN_1A', 'PROCESS_A', 'COMP_B'),
                         carry=('texture_src', 'cover_src'),
                         licence='Open Government Licence - Yukon', redistribution='open')
    finish(u, per_sheet_fp(u), src, dict(title='Yukon Surficial Geology Compilation (YGS 2023)',
                                         override='Rampton 1982 GSC Map 1503A conf_tier=Surficial'))


def qc():
    # Two layers, same code scheme. The detailed zones cover only ~19,000 km2 inside
    # AMAP; the generalised province-wide layer (~100,000 km2 inside AMAP) is the base.
    # Neither states a scale: nominal 1:100k (detailed) and 1:250k (generalised).
    src = 'ca_qc_sigeom'
    gp = one('SIGEOM*/**/*.gpkg')
    parts = []
    for lyr, sheet, sc in (('F10E15_ZONE_MORPH_SEDIM', 'detailed', 100_000),
                           ('SGM_ZONE_MORPH_QC_SO', 'generalised', 250_000)):
        g = pyogrio.read_dataframe(gp, layer=lyr, bbox=(-80, 51, -55, 63))
        g = S.in_amap(g.to_crs(S.CRS))
        g['sheet'], g['scale'] = sheet, sc
        g['desc'] = g['NOTE_DEPOT_MORP_SEDM'] if 'NOTE_DEPOT_MORP_SEDM' in g else ''
        parts.append(g)
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    g['code'] = g['CODE_DEPOT_MORP_SEDM'].astype(str).str.strip()
    g['year'] = pd.to_numeric(g['DATE_PREM_DIFS'].astype(str).str[:4], errors='coerce')
    u, _ = S.standardise(g, src_id=src, code='code', desc='desc', sheet='sheet',
                         scale_den='scale', pub_year='year', extra=('NUMR_INTER',),
                         licence='CC-BY 4.0 (Données Québec)', redistribution='open')
    finish(u, per_sheet_fp(u), src,
           dict(title='SIGÉOM Géologie du Quaternaire, zones morpho-sédimentologiques (detailed + generalised)',
                scale_note='source does not state scale; nominal 1:100k detailed / 1:250k generalised (unverified)'))


def mb():
    src = 'ca_mb_sgcms'
    g = pyogrio.read_dataframe(one('SGCMS_1_1Million_2017/*.shp'))
    g = S.in_amap(g.to_crs(S.CRS))
    u, _ = S.standardise(g, src_id=src, code='DERVD_LEG', desc='Link', xkey='DERVD_LEG',
                         sheet='NTS_250', scale_den=250_000, pub_year=2017,
                         extra=('Original_M', 'Original_U'),
                         licence='OpenMB Information and Data Use Licence v1.0 (Government of Manitoba); GSC-derived '
                                 'parts Open Government Licence - Canada', redistribution='open')   # H.L. 2026-10-07
    u['src_sheet'] = u['src_sheet'].fillna('')
    finish(u, S.footprint_from_units(u), src, dict(title='Manitoba Surficial Geology Compilation Map Series 2017'))


def on():
    src = 'ca_on_eds014'
    g = pyogrio.read_dataframe(one('EDS014*/**/Quaternary/geology_ll.shp'))
    g = S.in_amap(g.to_crs(S.CRS))
    un = g['UNIT_NAME'].fillna('Lake')
    g['xkey'] = un.where(~un.str.contains(r'\bTill$') | (un == 'Till'), 'NAMED_TILL')
    mat = g['MATERIAL'].fillna('').str.lower()
    g['texture_src'] = 'unknown'
    g.loc[mat.str.startswith('silt and clay'), 'texture_src'] = 'fines'
    g.loc[mat.str.startswith(('gravel and sand', 'sand, gravelly')), 'texture_src'] = 'mixed'
    g.loc[mat.str.startswith('peat'), 'texture_src'] = 'organic'
    u, _ = S.standardise(g, src_id=src, code='NUMBER', desc='MATERIAL', xkey='xkey',
                         scale_den=1_000_000, pub_year=2010, extra=('AGE', 'UNIT_NAME'),
                         carry=('texture_src',),
                         licence='Ontario MNDM terms of use (not an open licence)', redistribution='internal_only')
    finish(u, S.footprint_from_units(u), src, dict(title='OGS EDS014 Quaternary geology of Ontario 1:1M'))


def gsc5m():
    src = 'ca_gsc_5m'
    g = pyogrio.read_dataframe(one('gsc_surficial_geology.gdb/**/*.gdb'), layer='geology')
    g = S.in_amap(g.to_crs(S.CRS))
    u, _ = S.standardise(g, src_id=src, code='label', desc='description_en', scale_den=5_000_000,
                         pub_year=2014, licence=OGL, redistribution='open')
    finish(u, S.footprint_from_units(u, simplify=500.0), src, dict(title='GSC Surficial geology of Canada 1:5M'))


def lab():
    """GSNL 1:50k 'Detailed Surficial Geology' (GeoAtlas layer 11) only. The GeoAtlas regional layer (12) was GSC
    Map 1814A; since 2026-10-07 that map comes from the GSC's own release (gsc1814, source ca_gsc_1814a), because the
    GeoAtlas terms forbid passing on digital copies of either layer."""
    src = 'ca_nl_labrador'
    g = pyogrio.read_dataframe(f'{RAWC}/labrador_layer11.geojson')
    g = S.in_amap(g.to_crs(S.CRS))
    g['scale'], g['sheet'] = 50_000, 'layer11'
    # 1:50k: terrain label (Tv/Rc/O) + a clean LEGEND class (Till Veneer, Rock Concealed...)
    g['code'] = g['Label'].astype(str).str.strip()
    g['desc'] = g['LEGEND'].astype(str).str.strip() + ' | ' + g['DESCRIPTN'].astype(str).str[:200]
    g['xkey'] = 'L11:' + g['LEGEND'].astype(str).str.strip()
    print(f'   layer 11: {len(g)} in the domain', g['xkey'].value_counts().to_dict())
    u, _ = S.standardise(g, src_id=src, code='code', desc='desc', xkey='xkey', sheet='sheet',
                         scale_den='scale', pub_year=2015,
                         licence='NL GeoAtlas, GSNL 1:50k layer: no digital reproduction to third parties '
                                 '(permission required)', redistribution='internal_only')
    finish(u, per_sheet_fp(u), src, dict(title='NL GeoAtlas Detailed Surficial Geology (GSNL 1:50k), Labrador'))


def gsc1814():
    """GSC Map 1814A, Klassen, Paradis, Bolduc and Thomas (1992), Glacial landforms and deposits, Labrador,
    Newfoundland and eastern Quebec, 1:1,000,000 (doi:10.4095/183872), from the GSC release as_1814.zip
    (Open Government Licence - Canada; downloaded 2026-10-07). Units = CODE of geoGSC_poly; the GEO_PAT
    landform overprint (hummocky / ribbed moraine, crevasse filling) is kept in the description. The one 'unknown'
    polygon is dropped, so its ground falls through to the next source."""
    src = 'ca_gsc_1814a'
    g = pyogrio.read_dataframe(f'{RAWC}/gsc_1814a/data/shape/geology/geoGSC_poly.shp')
    g = S.in_amap(g.to_crs(S.CRS))
    g['code'] = g['CODE'].astype(str).str.strip()
    pat = g['GEO_PAT'].fillna('').astype(str).str.strip().replace('<Null>', '')
    g['desc'] = g['code'] + pat.map(lambda s: f' | overprint: {s}' if s else '')
    print(f'   {src}: {len(g)} in the domain', g['code'].value_counts().to_dict())
    u, _ = S.standardise(g, src_id=src, code='code', desc='desc', xkey='code', sheet=lambda d: pd.Series(
                         'Map 1814A', index=d.index), scale_den=1_000_000, pub_year=1992, drop_codes=('unknown',),
                         licence=OGL, redistribution='open')
    finish(u, per_sheet_fp(u), src, dict(title='GSC Map 1814A, Glacial landforms and deposits, Labrador, '
                                                'Newfoundland and eastern Quebec (Klassen et al. 1992), 1:1M'))


ALL = {'ca_ygs_compilation': ygs, 'ca_qc_sigeom': qc, 'ca_mb_sgcms': mb, 'ca_on_eds014': on,
       'ca_gsc_5m': gsc5m, 'ca_nl_labrador': lab, 'ca_gsc_1814a': gsc1814}

if __name__ == '__main__':
    for s in (sys.argv[1:] or [k for k in ALL if k not in ('ca_nl_labrador', 'ca_gsc_1814a')]):
        print('==', s, flush=True)
        ALL[s]()
