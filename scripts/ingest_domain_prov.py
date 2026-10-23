#!/usr/bin/env python
"""
Provincial sources for the permafrost domain south of AMAP (downloaded 2026-09-30 to
raw/canada/domain_prov, unzipped to unz/canada/domain_prov) -> work/std/<src>.gpkg and
xwalk/<src>.csv (written here from the source's own genetic class, so the unattended build
needs no hand-made crosswalk; each row notes the rule that produced it).

  ca_qc_nord   Québec MFFP 'Dépôts de surface du Nord québécois' (5 m RapidEye, MMU 100 ha,
               2010-13, pub. 2016), north of ~53N; key = CLASSE_DEP|TYPE_DEPOT; water dropped.
               Nominal 1:125,000 (MMU 100 ha). CC-BY 4.0.
  ca_on_fnpmp  OGS Far North Predictive Mapping 2021 (remote predictive, 67 1:100k tiles
               2011-18); key = OriginName. OGS terms (internal_only until checked).
  ca_sk_250k   Saskatchewan Geological Survey 250K surficial geology (SRC 1984-88 maps,
               merged 2008, v2017); key = MAIN_ENVIR. Sask. Standard Unrestricted Use v2.0.
  ca_ab_ags    Alberta AGS DIG 2013-0001 surficial mosaic (ungeneralised; 1:50k-1:250k
               sources); key = MAP_LABEL; nominal 1:250,000. OGL-Alberta.
usage: ingest_domain_prov.py [src ...]
"""
import os
import sys

import pandas as pd
import pyogrio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

U = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/canada/domain_prov'


def finish(u, src, meta, xw):
    p, m = S.write_std(u, S.footprint_from_units(u, coarse=1000.0), src, meta)
    pd.DataFrame(xw, columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']) \
        .drop_duplicates('xkey').to_csv(f'{S.XWALK}/{src}.csv', index=False)
    print(src, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')}, flush=True)


def kw(text, rules, default=('Q', '', 'unknown', '')):
    t = str(text).lower()
    for keys, val in rules:
        if any(k in t for k in keys):
            return val
    return default


# (keywords) -> (hclass, hclass2, texture, cover); first match wins, so specific before generic
QC = [(('eau profonde',), ('M', 'GM', 'fines', '')), (("eau peu profonde",), ('M', '', 'sand', '')),
      (('littoral',), ('M', '', 'sand', '')), (('marins',), ('M', '', 'fines', '')),
      (('fluvioglaciaire', 'esker', 'kame', 'delta'), ('GF', '', 'gravel', '')),
      (('till mince', 'placage'), ('T', 'R', 'diamicton', 'veneer')),
      (('till', 'moraine', 'drumlin', 'glaciaire', 'profilées'), ('T', '', 'diamicton', '')),
      (('roc',), ('R', '', '', '')), (('substrat',), ('R', '', '', '')),
      (('organique',), ('O', '', 'organic', '')), (('fluviati', 'alluvi'), ('F', '', 'mixed', '')),
      (('lacust',), ('L', '', 'fines', '')), (('éolien',), ('E', '', 'sand', '')),
      (('pente', 'altération', 'colluv', 'éboul'), ('C', 'W', 'bouldery', '')), (('anthrop',), ('X', '', 'mixed', ''))]
ON = [(('ocean', 'water'), ('DROP', '', '', '')), (('organic',), ('O', '', 'organic', '')),
      (('salt marsh',), ('M', 'O', 'fines', '')), (('mudflat', 'marine basin'), ('M', '', 'fines', '')),
      (('marine beach', 'near-shore'), ('M', '', 'sand', '')), (('glaciolacustrine',), ('GL', '', 'fines', '')),
      (('glaciofluvial',), ('GF', '', 'gravel', '')), (('glacial deposits and bedrock',), ('T', 'R', 'diamicton', 'veneer')),
      (('glacial',), ('T', '', 'diamicton', '')), (('fluvial',), ('F', '', 'mixed', '')), (('lacustrine',), ('L', '', 'fines', '')),
      (('eolian', 'aeolian'), ('E', '', 'sand', '')), (('colluv',), ('C', '', '', '')), (('rock',), ('R', '', '', ''))]
SK = [(('water', 'lake'), ('DROP', '', '', '')), (('glaciolacustrine',), ('GL', '', 'fines', '')),
      (('glaciofluvial',), ('GF', '', 'gravel', '')), (('morainal veneer', 'till veneer'), ('T', 'R', 'diamicton', 'veneer')),
      (('morainal', 'moraine', 'till'), ('T', '', 'diamicton', '')),
      (('organic',), ('O', '', 'organic', '')), (('eolian', 'aeolian'), ('E', '', 'sand', '')),
      (('alluvial', 'fluvial'), ('F', '', 'mixed', '')), (('lacustrine',), ('L', '', 'fines', '')),
      (('colluv', 'landslide'), ('C', '', '', '')), (('rock', 'bedrock'), ('R', '', '', ''))]
AB = {'O': ('O', '', 'organic', ''), 'M': ('T', '', 'diamicton', ''), 'MS': ('T', '', 'diamicton', ''),
      'MF': ('T', '', 'diamicton', ''), 'MT': ('T', '', 'diamicton', ''), 'LG': ('GL', '', 'fines', ''),
      'FG': ('GF', '', 'gravel', ''), 'F': ('F', '', 'mixed', ''), 'C': ('C', '', '', ''), 'R': ('R', '', '', ''),
      'E': ('E', '', 'sand', ''), 'L': ('L', '', 'fines', ''), 'G': ('I', '', '', ''), 'Lake': ('DROP', '', '', '')}


def qc_nord():
    src = 'ca_qc_nord'
    g = pyogrio.read_dataframe(f'{U}/qc_DEP_CN_GDB/DEP_NORD_PROV.gdb', layer='DEP_CN')
    g = g[g['CO_TER'].fillna('').str.strip() != 'EAU']
    g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
    g['xkey'] = g['CLASSE_DEP'].fillna('').str.strip() + '|' + g['TYPE_DEPOT'].fillna('').str.strip()
    xw = []
    for k in sorted(g['xkey'].unique()):
        h = kw(k.split('|')[1] + ' ' + k.split('|')[0], QC)
        xw.append([k, *h, '', f'keyword rule on CLASSE_DEP|TYPE_DEPOT ({k})'])
    u, _ = S.standardise(g, src_id=src, code='GEOL_QC', desc='TYPE_DEPOT', xkey='xkey', scale_den=125_000, pub_year=2016,
                         extra=('DEP_SUR', 'CLASSE_DEP'), licence='CC-BY 4.0 (Gouvernement du Québec, MFFP/MRNF)', redistribution='open')
    finish(u, src, dict(title='Dépôts de surface du Nord québécois (MFFP, RapidEye 5 m, MMU 100 ha)',
                        scale_note='nominal 1:125,000 from the 100 ha minimum mapping unit'), xw)


def on_fnpmp():
    src = 'ca_on_fnpmp'
    g = pyogrio.read_dataframe(f'{U}/on_fnpmp_2021/FNPMP_2021/FNPMP_2021.gdb', layer='geology')
    g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
    g['xkey'] = g['OriginName'].fillna('?').str.strip()
    xw = [[k, *kw(k, ON), '', f'keyword rule on OriginName ({k})'] for k in sorted(g['xkey'].unique())]
    u, _ = S.standardise(g, src_id=src, code='Sub_Unit', desc='Mat_Des', xkey='xkey', scale_den=100_000, pub_year=2021,
                         extra=('Prin_Mat', 'Dep_Env'), conf_tier='Predictive',
                         licence='Ontario Geological Survey terms of use', redistribution='internal_only')
    finish(u, src, dict(title='OGS Far North Predictive Mapping 2021 (remote predictive surficial)'), xw)


def sk_250k():
    src = 'ca_sk_250k'
    g = pyogrio.read_dataframe(f'{U}/sk_250k_surficial_shp/250K_Surficial_Geology.shp')
    g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
    g['xkey'] = g['MAIN_ENVIR'].fillna('?').str.strip()
    xw = [[k, *kw(k, SK), '', f'keyword rule on MAIN_ENVIR ({k})'] for k in sorted(g['xkey'].unique())]
    u, _ = S.standardise(g, src_id=src, code='CODE', desc='MAIN_ENVIR', xkey='xkey', scale_den=250_000, pub_year=2017,
                         licence='Saskatchewan Standard Unrestricted Use Data Licence v2.0', redistribution='open')
    finish(u, src, dict(title='Saskatchewan 250K Surficial Geology (SGS/SRC)'), xw)


def ab_ags():
    src = 'ca_ab_ags'
    g = pyogrio.read_dataframe(f'{U}/ab_DIG_2013_0001/surfmosaic_py_ll.shp')
    g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
    g['xkey'] = g['MAP_LABEL'].fillna('?').str.strip()
    xw = [[k, *AB.get(k, kw(k, SK)), '', f'MAP_LABEL {k} (AGS genetic group)'] for k in sorted(g['xkey'].unique())]
    u, _ = S.standardise(g, src_id=src, code='SRC_ABBR', desc='SRC_LABEL', xkey='xkey', sheet='REF_SRC', scale_den=250_000,
                         pub_year=2013, extra=('SRC_GENET', 'GENETIC_GR'),
                         licence='Open Government Licence - Alberta', redistribution='open')
    u['src_sheet'] = u['src_sheet'].fillna('')
    finish(u, src, dict(title='AGS DIG 2013-0001 Surficial Geology of Alberta, ungeneralised mosaic'), xw)


ALL = {'ca_qc_nord': qc_nord, 'ca_on_fnpmp': on_fnpmp, 'ca_sk_250k': sk_250k, 'ca_ab_ags': ab_ags}
if __name__ == '__main__':
    bad = []
    for s in (sys.argv[1:] or ALL):
        print('==', s, flush=True)
        try:
            ALL[s]()
        except Exception as e:                    # one failing source must not stop the others
            import traceback
            traceback.print_exc()
            bad.append(s)
    print('FAILED', bad)
