#!/usr/bin/env python
"""Adds source_type to sources.csv: what kind of map each source dataset is, so that users can tell a surficial map from
a geological map whose bedrock class only means that no Quaternary cover was mapped. Rewrites SOURCES in place; a
source without a type stops the script.
usage: sources_type.py SOURCES.csv"""
import sys

import pandas as pd

SURF, PRED, QUAT, GEOL, SOIL, PROXY = ('surficial map', 'surficial map, predictive (remote sensing)', 'Quaternary map',
                                       'geological map', 'soil survey', 'proxy (topographic, habitat or protection data)')
TYPE = {
    'ca_gsc_cgm': SURF, 'ca_gsc_5m': SURF, 'ca_gsc_scans': SURF, 'ca_gsc_lines': SURF, 'ca_gsc_legacy': SURF,
    'ca_gsc_1814a': SURF, 'ca_gsc_of7289': SURF, 'ca_gsc_of5116': SURF, 'ca_gsc_of7196': SURF, 'ca_gsc_of8651': SURF,
    'ca_gsc_bc_ofs': SURF, 'ca_qc_nord': SURF, 'ca_qc_sigeom': SURF, 'ca_mb_sgcms': SURF, 'ca_sk_250k': SURF,
    'ca_ab_ags': SURF, 'ca_ygs_compilation': SURF, 'ca_bc_ter': SURF, 'ca_nl_labrador': SURF,
    'ca_gsc_of7038': PRED, 'ca_gsc_of7118': PRED, 'ca_bc_soil': SOIL,
    'us_ak_gems': SURF, 'us_usgs_sim3036': SURF, 'us_usgs_sim3388': SURF, 'us_usgs_sim3340': GEOL,
    'gl_geus_g500_v3': GEOL, 'gl_geus_g100_karrat': GEOL,
    'no_ngu_losmasser': SURF, 'se_sgu_jordarter25k': SURF, 'se_sgu_jordarter250k': SURF, 'se_sgu_jordarter1m': SURF,
    'fi_gtk_maapera20k': SURF, 'fi_gtk_maapera200k': SURF,
    'is_natt_j600': GEOL, 'is_natt_n25_coastal': PROXY,
    'sj_npi_g250': GEOL, 'sj_npi_j250_janmayen': GEOL, 'sj_npi_s100_overlay': PROXY,
    'fo_us_lendisslog': PROXY,
    'ru_vsegei_pdf': QUAT, 'ru_vsegei_preview': QUAT, 'ru_vsegei200': QUAT, 'ru_vsegei_q2500': QUAT,
    'ru_bryant_vsegei1m': QUAT, 'ru_veremeeva_r5557': QUAT, 'ru_lena_peter2014': QUAT, 'ru_kytalyk_base': SURF,
}
s = pd.read_csv(sys.argv[1], keep_default_na=False, dtype=str)
miss = sorted(set(s['src_id']) - set(TYPE))
if miss:
    sys.exit(f'no source_type for {miss}')
s['source_type'] = s['src_id'].map(TYPE)
s.to_csv(sys.argv[1], index=False)
a = pd.to_numeric(s['area_km2'], errors='coerce')
print((a.groupby(s['source_type']).sum() / 1e6).round(2).to_string())
