#!/usr/bin/env python
"""
Russia (beyond Bryant) ingests -> work/std/<src>.gpkg

  ru_veremeeva_r5557   Veremeeva 2021, Yana-Indigirka/Kolyma lowlands R-55-57 (PANGAEA.927292,
                       CC-BY 4.0), Landsat-based, ~1:200k, 6 classes
  ru_lena_peter2014    Peter et al. 2014 Lena Delta stratigraphic classes (PAGE21 D2.1;
                       licence unknown -> 'unknown'); complete 3-class partition, ~1:100k
  ru_kytalyk_base      van Huissteden et al. 2014 Kytalyk geomorphology, base layer (~1:25k);
                       file says EPSG:4326 but coordinates are UTM 55N -> EPSG:32655
  ru_vsegei200         VSEGEI Moscow-branch 1:200k digital models (Gosgeolkarta-200) --
                       so far one sheet, Q-37-XXV,XXVI from the Wayback Machine. No CRS in
                       the file: Pulkovo-1942 geographic (EPSG:4284) ASSUMED, as for VSEGEI
                       digital models generally (~100-150 m from WGS 84 here). Crosswalk key =
                       genetic prefix of the index (ru_index.py); texture from TEXT_G1.
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402
import ru_index as RI  # noqa: E402

PR = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/russia'


def finish(u, fp, src, meta):
    p, m = S.write_std(u, fp, src, meta)
    S.code_table(u).to_csv(f'{S.WORK}/codes_{src}.csv', index=False)
    print(src, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')}, flush=True)


def veremeeva():
    src = 'ru_veremeeva_r5557'
    g = gpd.read_file(f'{PR}/R-55-57_QuaternaryGeologicalMap.geojson').to_crs(S.CRS)
    g['ice'] = (g['QuatDep'].str.startswith('Yedoma')).map({True: 'yes', False: 'unknown'})
    u, _ = S.standardise(g, src_id=src, code='QuatDep', desc='QuatDep', scale_den=200_000,
                         pub_year=2021, survey_years='Landsat 2001-2010', carry=('ice',),
                         licence='CC-BY 4.0 (PANGAEA.927292)', redistribution='open')
    u = u.rename(columns={'ice': 'ice_rich_src'})
    finish(u, S.footprint_from_units(u), src, dict(title='Veremeeva 2021 Quaternary deposits R-55-57'))


def lena():
    src = 'ru_lena_peter2014'
    parts = [gpd.read_file(f).to_crs(S.CRS) for f in sorted(glob.glob(f'{PR}/lena/Lena_Delta/StratClass*.shp'))]
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    g['code'] = g['StratClass'].astype(int).astype(str)
    g['ice'] = (g['code'] == '3').map({True: 'yes', False: 'unknown'})
    u, _ = S.standardise(g, src_id=src, code='code', desc='code', scale_den=100_000, pub_year=2014,
                         carry=('ice',), licence='PAGE21 D2.1 (PANGAEA): licensing unknown, contact PI',
                         redistribution='unknown')
    u = u.rename(columns={'ice': 'ice_rich_src'})
    finish(u, S.footprint_from_units(u), src, dict(title='Lena Delta stratigraphic classes (Peter et al. 2014)',
                                                  note='classes 2+3 geometrically identical to Morgenstern 2011 (CC-BY 3.0)'))


def kytalyk():
    src = 'ru_kytalyk_base'
    g = gpd.read_file(glob.glob(f'{PR}/kytalyk/**/Geomorphology_Base.shp', recursive=True)[0])
    g = g.set_crs(32655, allow_override=True).to_crs(S.CRS)
    g['code'] = g['Descriptio'].str.strip().str.capitalize()
    g['ice'] = g['code'].str.startswith('Yedoma').map({True: 'yes', False: 'unknown'})
    u, _ = S.standardise(g, src_id=src, code='code', desc='Descriptio', scale_den=25_000, pub_year=2014,
                         carry=('ice',), licence='PAGE21 (PANGAEA, unpublished): none stated', redistribution='unknown')
    u = u.rename(columns={'ice': 'ice_rich_src'})
    finish(u, S.footprint_from_units(u), src, dict(title='Kytalyk geomorphology base (van Huissteden 2014)',
                                                  crs_note='file says 4326; coordinates are UTM 55N'))


def vsegei200():
    src = 'ru_vsegei200'
    parts = []
    for f in sorted(glob.glob(f'{PR}/ggk200/**/basea.shp', recursive=True)):
        g = pyogrio.read_dataframe(f, encoding='cp1251')
        if g.crs is None:
            g = g.set_crs(4284)          # ASSUMED Pulkovo-1942 geographic
        g['sheet'] = 'Q-37-XXV,XXVI'
        parts.append(g.to_crs(S.CRS))
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    g['xkey'] = g['INDEX'].map(RI.genetic_prefix)
    g['desc'] = g['TEXT_G1'].fillna('') + ' ' + g['TEXT_G2'].fillna('')
    # TEXT_G1 = '<stratigraphy>. <genetic name>. <lithology> (thickness)': texture from the
    # LAST sentence only, so a stratigraphic word never counts as a material
    g['texture_src'] = g['TEXT_G1'].fillna('').map(lambda t: RI.texture_ru(t.split('. ')[-1]))
    u, _ = S.standardise(g, src_id=src, code='INDEX', desc='desc', xkey='xkey', sheet='sheet',
                         scale_den=200_000, pub_year=2004, carry=('texture_src',),
                         extra=('L_CODE', 'B_CODE'),
                         licence='VSEGEI Gosgeolkarta-200 digital model (via Wayback Machine); terms unknown',
                         redistribution='internal_only')
    finish(u, S.footprint_from_units(u), src, dict(title='VSEGEI Gosgeolkarta-200 digital models',
                                                  crs_note='no CRS in file; EPSG:4284 assumed'))
    # crosswalk from the genetic prefixes actually present
    rows = []
    for p in sorted(u['xkey'].dropna().unique()):
        c = RI.classify_index(p + 'H')
        rows.append([p] + ([c[0], c[1], '', '', '', c[2]] if c else ['Q', '', '', '', '', 'UNKNOWN PREFIX - review']))
    pd.DataFrame(rows, columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']) \
        .to_csv(f'{S.XWALK}/{src}.csv', index=False)
    print(pd.read_csv(f'{S.XWALK}/{src}.csv').to_string(index=False))


PDFVEC = f'{S.WORK}/pdfvec'
# seam_russia.py output (edge-matched copies); ingest prefers it when present
PDFVEC_SEAMED = f'{S.WORK}/pdfvec_seamed'
JPGVEC = f'{S.WORK}/jpgvec'
PDFVEC1M = f'{S.WORK}/pdfvec1m'                 # GGK-1000 sheets (2nd/3rd generation), geokniga census 2026-09-30
VEC_DIRS = (PDFVEC_SEAMED, PDFVEC, JPGVEC, PDFVEC1M)      # search order: seamed copy first
SRCDIR = '/albedo/work/user/hlantuit/arctic_surficial/sources'
# nominal scale and edition year per extracted sheet (from the sheet title block)
# (scale, pub_year). 1:200k geokniga sheets: the PDFs carry no text layer (outlined glyphs), so the
# year is a PLACEHOLDER (2nd edition, ~2000-2020); it only breaks ties between same-scale sources,
# and these footprints do not overlap. Listed in meta['pub_year_placeholder'].
_G200 = ['R-35-XXIX,XXX', 'R-36-XXV,XXVI', 'R-39-XXXV,XXXVI', 'R-40-XXIX,XXX', 'R-40-XXXI,XXXII',
         'R-41-XXVIII,XXIX', 'R-41-XXX', 'R-41-XXXV,XXXVI', 'R-42-XXV,XXVI', 'R-53-XV,XVI',
         'R-54-XXXIII,XXXIV', 'R-59-XXXI,XXXII', 'S-44-XXI,XXII', 'S-44-XXIII,XXIV', 'S-44-XXIX,XXX',
         'S-45-XIX,XX', 'S-45-XXV,XXVI', 'S-46-XXI,XXII', 'S-46-XXIII,XXIV', 'S-48-I,II',
         # 2026-09-30 batch (geokniga 1:200k census; scripts/run_gk_pdf.py, sources/gk_pdf_sheets.csv)
         'R-42-VII,VIII', 'R-42-IX', 'R-42-XIII,XIV',
         'Q-41-XV', 'Q-41-XVII', 'Q-41-XVIII', 'Q-41-IX,X', 'Q-41-XXI,XXII', 'Q-41-XXXIII,XXXIV',
         'Q-49-XXI,XXII', 'Q-52-XXI,XXII', 'Q-52-XXIII,XXIV', 'Q-53-XXXV,XXXVI', 'Q-54-III',
         'Q-55-XXXI,XXXII', 'Q-56-XV,XVI', 'Q-56-XXI,XXII', 'Q-58-XI,XII', 'Q-58-XXXII', 'Q-58-XXXIII,XXXIV',
         'Q-59-XXIX,XXX', 'Q-51-VII,VIII', 'Q-52-XV,XVI', 'Q-39-XXVII,XXVIII', 'Q-39-XXXIII,XXXIV', 'Q-36-XV,XVI', 'P-55-III', 'P-55-IV',
         'P-47-XXVI', 'P-53-XXIV', 'P-53-XXX', 'P-54-XX', 'P-55-XXII', 'P-55-XXIII', 'P-55-XXV', 'P-55-XXVI', 'P-56-XXVI',
         'P-43-VII', 'P-43-XIII', 'P-43-XIV', 'P-43-XV', 'P-36-XII', 'P-38-VI', 'P-39-XIV', 'P-40-VI', 'P-37-XV', 'P-37-XXV',
         'P-36-XVIII', 'P-36-XXXI', 'P-40-XVIII', 'P-40-XXIX', 'P-58-XXXIV_O-58-IV',
         'P-46-XXV', 'P-46-XXXII', 'P-46-XXXIII', 'P-58-XXVIII',
         'O-40-X', 'O-40-XI', 'O-41-VII', 'O-41-XIX', 'O-47-IV', 'O-50-XXVIII', 'O-50-XXXIV', 'O-57-XXXIV',
         'N-45-V', 'N-45-XIII', 'N-45-XXIV', 'N-45-XXXV', 'N-46-III', 'N-46-IX', 'N-46-XXVI', 'N-47-XXIX', 'N-47-XXXV', 'N-47-XXXVI', 'N-49-XVI', 'N-50-XXXII',
         'N-51-X', 'N-52-XXII', 'N-53-XXV', 'N-52-XXX', 'M-50-VI', 'M-50-III',
         'N-45-VII', 'N-44-XVIII', 'N-54-XXXII', 'N-54-XXVII', 'M-49-XI',
         # 2026-10-04 (batch r200a): Q-41-XVI Khordyus, 2nd edition 2009, vector PDF (rms 2.2 m)
         'Q-41-XVI',
         # 2026-10-04 (batch r200c): 2nd-edition 'Neogene/Pliocene-Quaternary' vector PDFs (frame rms 0.2-0.5 m); NOT re-runnable
         # with run_gk_pdf.py: M-50-XV,XXI (explicit printed frame, work/r200c/job_M50XV.sh), N-48-XXXII (neatline from the
         # fills, job_N48.sh), N-45-IX and N-53-XXXIV (hatch units, job_hatch.sh with work/r200c/pdf_to_polygons_hatch.py)
         'M-50-XV,XXI', 'M-49-XVIII,XXIV', 'M-50-XIII', 'N-46-XXXV', 'N-48-XXXII', 'N-53-XXXIV', 'L-53-VI', 'M-45-II', 'N-45-IX',
         # 2026-10-06 (batch r200k): 2nd-edition vector PDFs, frame rms 0.11-0.35 m (work/r200k/NOTES.txt). NOT re-runnable with
         # run_gk_pdf.py: S-47-V,VI (frame not one ring -> neatline from the fills, job_neat.sh), N-54-XXX (cover peat drawn as
         # a line hatch -> composites, job_hatch.sh). P-39-X (Timan 2001/2021) agrees 18.8 % / kappa 0.08 with P-39_g3: shift
         # test peaks at zero and the extraction matches the PDF -> interpretation (Vychegda glaciolacustrine / lake units vs
         # the 1:1M's ground moraine); finest wins, flagged for review. M-52-XXX: W/C split of the slope cover differs (28.8 %)
         'N-53-XXVI', 'N-54-XXXIII', 'M-54-VII', 'M-52-XXX', 'M-54-I', 'P-39-X', 'S-47-V,VI', 'N-54-XXX',
         # 2026-10-06 (batch r200j, work/r200j/NOTES.txt): Transbaikal / Amur 2nd-edition vector PDFs (rows appended to
         # gk_pdf_sheets.csv, run_gk_pdf.py reproduces them; frame rms 0.17-0.20 m). The folder 'N-51-XVIII' holds N-51-XVII
         # (Solov'evsk; title + frame labels 124-125E, 54-54d40'N). M-48-IV: 2,521 km2 of Baikal floor coded H (deposit in
         # hclass2). Neogene/Paleogene suites coded R (Tankhoi, Osinovka); N2-Q surficial units by genesis
         'N-51-XVII', 'N-50-XXIX', 'N-49-XII', 'M-48-IV']
# sheets classified from 300 dpi RASTER scans (jpg_to_polygons.py): colour classes, not
# vector fills - listed in meta['raster_sheets'] and carried in the footprint
_JPG200 = ['T-47-XXXI,XXXII,XXXIII', 'T-47-XXXIV,XXXV,XXXVI', 'R-53-IX,X', 'R-58-XXXV,XXXVI', 'S-47-XIX,XX',
           'S-46-XIX,XX',
           'Q-54-XXIX,XXX', 'Q-54-XXVII,XXVIII', 'Q-41-XI', 'Q-41-XII', 'Q-41-XXV', 'Q-41-XXVI',
           'Q-41-XIX,XX', 'Q-41-I,II', 'Q-39-I,II', 'Q-39-VII,VIII', 'Q-40-XXX', 'Q-40-XXIV',
           'P-43-XVI', 'P-43-XVII', 'P-43-XVIII', 'P-43-XXII', 'P-43-XXIII',
           'P-55-XVII', 'P-55-XVI', 'P-55-XV', 'P-55-IX',
           'O-52-XXVII', 'O-52-XXVI', 'O-53-XII', 'O-52-I', 'O-52-II',
           'P-54-XIV', 'P-54-VIII', 'P-54-XIX',
           'P-57-V', 'P-52-XXXII', 'P-47-XXXIII',
           'N-52-XIII', 'N-52-VII', 'P-55-XII', 'P-50-I', 'P-50-II', 'O-42-VI', 'M-50-VII', 'N-46-XIII', 'N-48-XXXIII', 'O-42-XV', 'M-48-X,XVI', 'N-51-XXIII,XXIX', 'P-43-IX', 'M-48-V',
           # 2026-10-02: the last large in-domain 1:200k rasters (corners measured on frame profiles, --no-snap)
           'N-57-XX', 'M-52-XII', 'O-46-XXXI', 'O-46-XXVIII', 'O-46-XV', 'M-54-XIV', 'M-53-XXXVI', 'P-39-V', 'M-45-III', 'P-39-I',
           # 2026-10-04 (batch r200a): 1st-edition Severo-Uralskaya sheets, 200 dpi full sheets (~25 m/px), heavily hatched;
           # corners + interior graticule / 5' frame-tick ties, leave-one-out error 19-38 m median
           'Q-41-III', 'Q-41-IV', 'Q-41-XIII',
           # 2026-10-04 (batch r200c): full scans; map image forced with RAST_IMG; N-56-VI_N-57-I frame passed with --lonlat
           # (155.5-157 E, 55.333-56 N; nomen.frame cannot parse a two-sheet name); M-50-IX corner rms 36.7 m (scan distortion)
           'M-50-IX', 'M-50-XII', 'N-56-VI_N-57-I', 'P-40-I',
           # 2026-10-06 (batch r200g): full scans, legend + imprint on the sheet; corners + 15'x10' graticule ties (leave-one-out
           # median/max 67/114 m and 10/45 m); P-39-IX aIII confined to the Vym corridor (415 km2 of plain read as aIII otherwise)
           'P-39-IX', 'P-38-IV',
           # 2026-10-06 (batch r200k): Amursk full scan (no PDF on geokniga), 16.9 m/px, corners + 9 graticule ties,
           # leave-one-out median/max 4.7/10.7 m
           'M-53-XVII',
           # 2026-10-06 (batch r200f): Verkhoyansk series sheet 1 of 2 (CMYK 300 dpi, 16.9 m/px, tmerc, rms 5.0 m, leave-one-out
           # 9.9 m); legend sheet not on disk -> rebuilt from the indices on the map + the correlation scheme (94 % of the face
           # matches); gIII4 dropped (26 km2, refs show bedrock); fIII2 kept as printed
           'Q-54-XIX,XX',
           # 2026-10-06 (batch r200j): full scans, ties = interior 15'x10' crossings + graticule-at-frame points, leave-one-out
           # median 3.1-5.1 m; N-51-XXIV / N-51-XXX CMYK -> classified from ICC-converted copies (work/r200j/<S>/rgb.png);
           # N-51-XXX --paper-nodata (the Chinese bank of the Amur is unmapped: Russian bank only, 2,240 km2)
           'M-50-X', 'N-51-XXIV', 'N-51-XXX',
           # 2026-10-06 (batch r200e): the long-deferred Q-37-XXXV,XXXVI (Tikhvin-Onega, signed to print 1.XII.1975): the
           # blue units differ by SCREEN PATTERN, not tint -> windowed-FFT hatch detection (work/r200e/prep_q3735.py: WATER
           # horizontal lines, mIV vertical, almIV diagonal dot grid) painted onto the de-hatched scan; stitched/bent scan ->
           # 60 minute-bar ties (affine rms 158 m, leave-one-out median 19 m); lIV and PREQ dropped
           'Q-37-XXXV,XXXVI',
           # 2026-10-06 (batch r200h): West-Siberian series full scan (~17 m/px, rms 41 m, leave-one-out median 31 m); cover
           # deposits printed as symbols over the base unit -> composites cover/base (cover hclass first); legend typed on 5
           # sheets, no imprint (record has no year, OCR found none) -> 2010 placeholder
           'P-43-XXXI']
# 1:1M sheets from the geokniga 1:1M census (sheet = <nom>_g<generation>; years: _G2YEAR / _YEAR1M below)
_G1M = ['S-50_g3', 'R-46_g3', 'R-48_g3', 'R-51_g3', 'R-53_g3', 'R-54_g3', 'S-47_g3', 'S-44_g3', 'U-41-44_g3',
        'R-47_g3', 'R-44_g3', 'R-43_g3', 'R-50_g3', 'S-51_g3', 'S-46_g3', 'T-41-44_g3',
        'Q-44_g3', 'Q-49_g3', 'Q-50_g3', 'Q-53_g3', 'Q-54_g3', 'Q-55_g3',
        'Q-46_g3', 'Q-45_g3', 'Q-48_g3', 'Q-38_g3', 'Q-60_g3', 'P-55_g3', 'P-58_g3', 'P-57_g3', 'P-52_g3', 'P-53_g3', 'P-47_g3', 'P-44_g3', 'P-45_g3', 'P-37_g3', 'P-38_g3', 'P-39_g3', 'Q-58_g3', 'Q-47_g3', 'R-37-38_g3', 'Q-39_g3', 'P-49_g3',
        'O-51_g3', 'O-52_g3', 'O-44_g3', 'N-44_g3', 'O-54_g3', 'N-54_g3', 'Q-37_g3', 'N-42_g3', 'S-53-54_g3', 'T-45-48_g3',
        # 3rd-generation 'Pliocene-Quaternary' sheets (geokniga term 18916, approved 2026-10-02); *_pq = name of the work output
        'P-42_pq', 'Q-43_pq', 'R-49_pq', 'O-43_pq', 'Q-40_pq', 'P-43_pq', 'O-45_pq', 'O-41_pq', 'N-43_pq', 'S-39-40_pq', 'R-39-40_pq', 'S-41-42_pq', 'R-1-2_pq',
        # 2026-10-06 (batch r1m4, work/r1m4/extract_opts.txt): GGK-1000/3 Baltic series, vector. Q-(35),36 Apatity (frame
        # 27-36E as printed, face stops at the Finnish border; eqdc rms 36 m; supersedes Q-35-37_g2 by year); P-(35),36
        # Petrozavodsk: STEPPED frame (26d20'E south of 60d40'N) -> work/r1m4/pdf_to_polygons_step.py --frame-ll, rms 54 m,
        # only 869 km2 in domain. P-(35)-37_g2 and N-40,(41)_g2 skipped (no in-domain gain / 122 km2)
        'Q-35-36_g3', 'P-35-36_g3',
        'N-49-50_g2', 'N-52-53_g2', 'O-49-50_g2', 'R-40-42_g2', 'M-52-53_g2', 'Q-35-37_g2', 'R-58-60_g2', 'N-50-51_g2', 'P-54-55_g2', 'O-55_g2', 'Q-50-51_g2', 'O-47-48_g2', 'Q-60-1_g2', 'P-60_g2', 'Q-2_g2', 'O-52-53_g2', 'O-53-54_g2', 'O-50-51_g2', 'M-46-47_g2', 'M-47-48_g2', 'M-50-51_g2', 'S-44-46_g2', 'M-53-55_g2', 'R-45-47_g2', 'R-35-37_g2']   # R-52_g3 = existing 'R-52'; S-38 = sea only   # T-45-48_g3: frame fit FAILED (fan layout), not listed
# print years: read from the imprint at extraction (dict below, wins), else the year of the geokniga page the
# sheet was downloaded from ('Карта составлена: <org>, YYYY г.'; sources/year200.csv by scripts/year200_candidates.py,
# 2026-10-06: 168 of the 169 sheets that carried the placeholder); sheets with neither keep the 2010 placeholder
# (YEAR_PLACEHOLDER -> meta pub_year_placeholder; M-45-III: no year on the page, no imprint on the scan)
_YEAR200_PAGE = {r.sheet: int(r.year) for r in pd.read_csv(f'{SRCDIR}/year200.csv', dtype=str).itertuples()} \
    if os.path.exists(f'{SRCDIR}/year200.csv') else {}
_YEAR200_IMPRINT = {'Q-41-XVI': 2009, 'Q-41-III': 1964, 'Q-41-IV': 1962, 'Q-41-XIII': 1971,
            # vector: electronic edition year from the imprint (compiled 1999-2016); raster: print date
            'M-50-XV,XXI': 2015, 'M-49-XVIII,XXIV': 2018, 'M-50-XIII': 2019, 'N-46-XXXV': 2019, 'N-48-XXXII': 2012,
            'N-53-XXXIV': 2015, 'L-53-VI': 2013, 'M-45-II': 2018, 'N-45-IX': 2015,
            'M-50-IX': 2001, 'M-50-XII': 2001, 'N-56-VI_N-57-I': 2005, 'P-40-I': 1971,
            'P-39-IX': 1997, 'P-38-IV': 2002,   # P-39-IX approved 17.03.1987, signed for print 17.12.1997
            # r200k: edition years from the imprints
            'N-53-XXVI': 2015, 'N-54-XXXIII': 2020, 'M-54-VII': 2020, 'M-52-XXX': 2016, 'M-54-I': 2015, 'P-39-X': 2021,
            'S-47-V,VI': 2012, 'N-54-XXX': 2020, 'M-53-XVII': 2016,
            'Q-54-XIX,XX': 2016,   # r200f: imprint '© Роснедра, 2016'
            # r200j: vector = electronic edition year, raster = print year
            'N-51-XVII': 2019, 'N-50-XXIX': 2013, 'N-49-XII': 2019, 'M-48-IV': 2019,
            'M-50-X': 2002, 'N-51-XXIV': 2016, 'N-51-XXX': 2016,
            'Q-37-XXXV,XXXVI': 1975}   # r200e: signed to print 1.XII.1975 (record year 1967)
# the page year is the COMPILATION year (median 6 yr before print, n=78: scripts/year_page_validation.py): the print
# year read by OCR on the sheet (sources/year200_imprint.csv by scripts/imprint_ocr.py: '©' edition line, else 'подписано
# к печати') wins over it, the years read by eye win over both
_YEAR200_OCR = {r.sheet: int(r.year) for r in pd.read_csv(f'{SRCDIR}/year200_imprint.csv', dtype=str).itertuples()} \
    if os.path.exists(f'{SRCDIR}/year200_imprint.csv') else {}
_YEAR200 = {**_YEAR200_PAGE, **_YEAR200_OCR, **_YEAR200_IMPRINT}
# 2nd-generation 1:1M sheets: years read when processing
_G2YEAR = {'N-49-50_g2': 1986, 'N-52-53_g2': 1983, 'O-49-50_g2': 1984, 'R-40-42_g2': 1999, 'M-52-53_g2': 1995, 'Q-35-37_g2': 2003, 'R-58-60_g2': 1998, 'N-50-51_g2': 1987, 'P-54-55_g2': 1999, 'O-55_g2': 1999, 'Q-50-51_g2': 1986, 'O-47-48_g2': 1981, 'Q-60-1_g2': 2001, 'P-60_g2': 2001, 'Q-2_g2': 2001, 'O-52-53_g2': 1981, 'O-53-54_g2': 1982, 'O-50-51_g2': 1972, 'M-46-47_g2': 1976, 'M-47-48_g2': 1969, 'M-50-51_g2': 1999, 'S-44-46_g2': 2000, 'M-53-55_g2': 1995, 'R-45-47_g2': 2000, 'R-35-37_g2': 2000}   # GGK-1000/2 new series, Chita; raster, corner rms 318 m (fold distortion), flagged
# M-50-51_g2 RE-REGISTERED 2026-10-06 (batch r200j): it had been extracted with --lonlat 117,48.666667,121,52 but the
# printed corners sit on 48N (edge-width ratio 0.918 vs cos52/cos48 = 0.920): the map was squeezed N-S by 1/6, error 0 at
# 52N, ~6 km at 51d40' (the 'M-50-VI shift'), ~37 km at 50N, ~74 km at 48N. Re-extracted with 117,48,121,52 (eqdc 47/62):
# corner rms 790 -> 220 m, best shift 0 against the 1:200k sheets, agreement 46-51 -> 60-67 %. Old: jpgvec/old_lat4867/
# the other _G1M sheets (_g3 / _pq): year of the geokniga page the sheet was downloaded from (sources/year1m.csv by
# scripts/year1m_candidates.py, 2026-10-06), else the 2013 placeholder (YEAR_PLACEHOLDER_1M -> meta pub_year_placeholder)
# Page year = the record's 'Карта составлена: <org>, YYYY г.', the compilation/edition year: checked against the print
# years read on the sheets (scripts/year_page_validation.py), the imprint wins where read (S-39,40: page 2020, print 2021)
_YEAR1M_IMPRINT = {'O-43_pq': 2017, 'N-43_pq': 2018, 'O-45_pq': 2021, 'S-39-40_pq': 2021, 'S-41-42_pq': 2022,
                   'Q-35-36_g3': 2012, 'P-35-36_g3': 2015}   # r1m4: signed for print 28.12.2012 / 30.12.2015
_YEAR1M = {**({r.sheet: int(r.year) for r in pd.read_csv(f'{SRCDIR}/year1m.csv', dtype=str).itertuples()}
              if os.path.exists(f'{SRCDIR}/year1m.csv') else {}), **_YEAR1M_IMPRINT}
PDF_SHEETS = {'R-52': (1_000_000, 2016), 'Q-42': (1_000_000, 2014), **{s: (200_000, _YEAR200.get(s, 2010)) for s in _G200 + _JPG200},
              **{s: (1_000_000, _YEAR1M.get(s, 2013)) for s in _G1M},
              **{s: (1_000_000, y) for s, y in _G2YEAR.items()}}
YEAR_PLACEHOLDER = [s for s in _G200 + _JPG200 if s not in _YEAR200]
YEAR_PLACEHOLDER_1M = [s for s in _G1M if s not in _G2YEAR and s not in _YEAR1M]
YEAR_COMPILED = [s for s in _G200 + _JPG200 if s in _YEAR200_PAGE and s not in _YEAR200_OCR and s not in _YEAR200_IMPRINT]
# Q-50-51_g2 left out since merge 45 (2026-10-08): it is the same printed map (Kolpakov 1986) as the USGS Siberian
# database sheet Q50,51 (ru_bryant_vsegei1m), whose vector digitisation (RMS 225 m) beats our 4-corner scan (1.4 km).
RASTER_SHEETS = _JPG200 + ['Q-39_g3', 'P-49_g3', 'N-49-50_g2', 'N-52-53_g2', 'O-49-50_g2', 'R-40-42_g2', 'M-52-53_g2', 'Q-35-37_g2', 'R-58-60_g2', 'N-50-51_g2', 'P-54-55_g2', 'O-55_g2', 'O-47-48_g2', 'Q-60-1_g2', 'P-60_g2', 'Q-2_g2', 'O-52-53_g2', 'O-53-54_g2', 'O-50-51_g2', 'M-46-47_g2', 'M-47-48_g2', 'M-50-51_g2', 'S-44-46_g2', 'M-53-55_g2', 'R-45-47_g2', 'R-35-37_g2', 'T-45-48_g3', 'S-39-40_pq', 'R-39-40_pq', 'S-41-42_pq', 'R-1-2_pq']   # Q-39 kqo1: map face is an embedded raster (jpgvec)


def pdfvec(src='ru_vsegei_pdf', sheets=None, title='VSEGEI Gosgeolkarta sheets extracted from vector PDFs',
           licence='VSEGEI Gosgeolkarta sheet PDF via geokniga.org ("for familiarisation only")'):
    """VSEGEI sheets extracted from vector PDFs (pdf_to_polygons.py). Crosswalk key =
    '<sheet>|<index>' so each sheet keeps its own legend; the crosswalk CSV is built
    from sources/legend_<sheet>.csv (hclass/texture/ice assigned when transcribing)."""
    sheets = PDF_SHEETS if sheets is None else sheets
    parts, fps, xw = [], [], []
    for sheet, (scale, year) in sheets.items():
        f = next((f'{d}/{sheet}.gpkg' for d in VEC_DIRS if os.path.exists(f'{d}/{sheet}.gpkg')), None)
        if f is None:
            print('   MISSING', sheet); continue
        print('  ', sheet, 'SEAMED' if f.startswith(PDFVEC_SEAMED) else 'raw (not seamed)')
        g = gpd.read_file(f, layer='units')
        g['xkey'] = sheet + '|' + g['index']
        g['scale'], g['year'] = scale, year
        u, _ = S.standardise(g, src_id=src, code='index', desc='description_ru', xkey='xkey',
                             sheet='sheet', scale_den='scale', pub_year='year', extra=('fill', 'draw_order'),
                             licence=licence, redistribution='internal_only')
        parts.append(u)
        fp = gpd.read_file(f, layer='neatline').to_crs(S.CRS)
        # the footprint must not CLAIM real gaps (S-46-XXI: 11 km2 strip where units stop
        # short of the frame): frame minus gaps > 0.05 km2, so a coarser source fills them
        # instead of U. Slivers below that stay claimed and are filled from this sheet.
        cover = shapely.buffer(shapely.union_all(shapely.make_valid(u.geometry.values)), 1.0)
        gaps = [p for p in shapely.get_parts(shapely.difference(fp.geometry.values[0], cover)) if p.area > 5e4]
        if gaps:
            fp['geometry'] = [shapely.difference(fp.geometry.values[0], shapely.union_all(gaps))]
            print(f'     footprint minus {len(gaps)} gaps, {sum(p.area for p in gaps) / 1e6:.2f} km2')
        fp['src_id'], fp['src_sheet'] = src, sheet
        fps.append(fp[['src_id', 'src_sheet', 'geometry']])
        leg = pd.read_csv(f'{SRCDIR}/legend_{sheet}.csv', dtype=str, keep_default_na=False)
        # colours shared by two units ('mnH|mH2'): combined key; both must share hclass
        for key in sorted(u['xkey'].unique()):
            idx = key.split('|', 1)[1]
            if idx == 'WATER':
                xw.append([key, 'H', '', '', '', '', 'water body (lake colour)'])
                continue
            r = leg[leg['index'].isin(idx.split('|'))]
            assert len(r) and r['hclass'].nunique() == 1, f'{key}: legend rows {r["index"].tolist()} disagree'
            x = r.iloc[0]
            xw.append([key, x['hclass'], x['hclass2'], x['texture'], '', x['ice_rich'],
                       f'{sheet} legend k={"/".join(r["k"])}: ' + x['note']])
    u = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
    pd.DataFrame(xw, columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']) \
        .to_csv(f'{S.XWALK}/{src}.csv', index=False)
    finish(u, fp, src, dict(title=title, sheets=list(sheets), datum='EPSG:4284 assumed',
                            pub_year_placeholder=[s for s in YEAR_PLACEHOLDER + YEAR_PLACEHOLDER_1M + PREVIEW_YEAR_PLACEHOLDER
                                                  if s in sheets],
                            pub_year_is_compilation_year=[s for s in YEAR_COMPILED + PREVIEW_YEAR_COMPILED if s in sheets],
                            raster_sheets=[s for s in RASTER_SHEETS + list(PREVIEW_SHEETS) if s in sheets]))


# GGK-1000 sheets held only as geokniga ~2000 px PREVIEWS (~0.35 km/px, labels illegible), colour-classified
# with map-calibrated tints (jpg_to_polygons.py --restrict/--class-dE). Own source so that 'preview-derived'
# stays visible in the product; replace by the full scan if one turns up. P-48-49_g2pv = P-48 half only
# (P-49 is held as P-49_g3; the P-49 half validated at 69 % primary / 90 % primary-or-secondary hclass agreement)
PREVIEW_SHEETS = {'P-48-49_g2pv': (1_000_000, 1989),
                  # T-48-50 (o. Bolshevik), VSEGEI 2002: drawn in the Soviet equidistant conic 47/62 N (jpg_to_polygons --proj);
                  # full frame shipped, T-45-48_g3 (newer) wins on T-48 by precedence, the preview fills T-49 (Taymyr NE coast)
                  'T-48-50_g2pv': (1_000_000, 2002),
                  # P-46,47 (Baykit), VSEGEI 1977: P-46 half only (P-47 is P-47_g3); eqdc 47/62 frame fit 117 m. The 2015 P-47_g3
                  # maps most of the 1977 glacial units (gIIs, g,fIIt ...; labels confirmed on the preview) as slope deposits
                  'P-46-47_g2pv': (1_000_000, 1977),
                  # P-40,41 (Severouralsk), VSEGEI 1989: full frame (in-domain land is 97 % fallback, 3 % 1:200k P-40 sheets that
                  # win by scale); 69.7 % primary hclass agreement / kappa 0.63 vs Q2500, 54.5 % vs the 1:200k on the Ural crest;
                  # frame from measured face edges (cream margin) + 44 edge ties; eqdc 47/62 fits this sheet WORSE than a sheet cone
                  # (633 vs 451 m) but with the edge ties the two differ by <= 0.3 px inside the face
                  'P-40-41_g2pv': (1_000_000, 1989),
                  # N-(44),45 (Novosibirsk), SNIIGGiMS 1983: N-45 half only (84-90E; N-44 is N-44_g3); cover-loam (red) and peat
                  # (green) hatch overprints detected by texture (work/n4445/prep_n4445.py) -> composite units pk/*, tf/*; eqdc 47/62
                  # 210 m; N-44 half vs N-44_g3: 61 % primary (E counted = Y) / 83 % either; loessoids coded E (see Y/E seam note)
                  'N-44-45_g2pv': (1_000_000, 1983),
                  # GGK-200 sheets held only as ~2000 px geokniga previews (34 m/px; 60 m/px for O-57-V,VI), units from the
                  # separate legend JPGs (*ql.jpg), fills = map tints (batch r200b, 2026-10-04); years = print date on the
                  # imprint (*qinf.jpg). Sugoy series: e,dIII-H and the till gIII4 share one colour -> group coded W/T
                  'P-56-XII': (200_000, 2007), 'P-56-XVIII': (200_000, 2007), 'O-57-XXX': (200_000, 2006),
                  'O-46-XXI': (200_000, 1964), 'O-57-V,VI': (200_000, 2007),
                  # batch r200a (Urals / Timan / Pechora, 2026-10-04): ~1650 x 2400 px map images (~34 m/px) + separate legend
                  # images; corners + interior graticule / frame-tick ties (leave-one-out 19-35 m median); years = imprint print date
                  'Q-41-VI': (200_000, 1977), 'P-40-III': (200_000, 1972), 'P-40-V': (200_000, 2001), 'P-40-VII': (200_000, 1986),
                  'P-40-IX': (200_000, 1973), 'P-40-X': (200_000, 1971), 'P-40-XIV': (200_000, 1989), 'P-41-XXXVI': (200_000, 1974),
                  # (2026-10-04: P-40-III/V/VII/IX/XIV, Q-41-VI, P-41-XXXVI re-run with frame ticks moved 1 px inward - the colour
                  # edge included the dark frame line; independent check points 24-59 m median, was 36-84 m; old in jpgvec/old_ticks)
                  # R-41 (Severo-Uralskaya, 1st edition, signed for print 11.II.1961), ~44 m/px, legend images fetched 2026-10-04
                  'R-41-XXXI,XXXII': (200_000, 1961), 'R-41-XXXIII,XXXIV': (200_000, 1961),
                  # batch r200d (2026-10-04): 49 GGK-200 sheets from ~2000-px previews (Ishim / West-Siberian / Kulunda-Baraba
                  # series etc.), legends from the *ql images, map-calibrated tints, corners + interior graticule ties (rms 11-121 m);
                  # years = imprint print date. N-44-V: no legend/imprint on geokniga, legend rebuilt from the printed indices + the
                  # N-44-IV/XI series legends, year UNKNOWN (1965 = mid-series placeholder). N-44-X keeps its own 'l+alQ2fd' lake
                  # loams as L (hclass follows the map), against E (cover loams) on all neighbours: a mapping-concept seam
                  'O-42-XXXIV': (200_000, 1974), 'O-42-XXXV': (200_000, 1972), 'O-42-XXXII': (200_000, 1977),
                  'O-42-XXIV': (200_000, 1969), 'O-42-XXXI': (200_000, 1970), 'O-42-I': (200_000, 1999),
                  'O-42-II': (200_000, 1999), 'O-42-III': (200_000, 1999), 'O-42-IV': (200_000, 1999),
                  'O-42-IX': (200_000, 1998), 'O-42-X': (200_000, 1998), 'M-49-XVII': (200_000, 2003),
                  'M-45-XXIII,XXIX': (200_000, 2010), 'M-50-XXII': (200_000, 2001), 'M-45-XXIV': (200_000, 2010),
                  'N-45-XVIII': (200_000, 2000), 'M-50-XXIII': (200_000, 2005), 'N-53-XVII': (200_000, 2001),
                  'M-50-XVIII': (200_000, 2005), 'N-46-XXIX': (200_000, 2003), 'O-40-VI': (200_000, 2010),
                  'N-43-II': (200_000, 1967), 'N-43-V': (200_000, 1977), 'N-43-IV': (200_000, 1990),
                  'N-43-III': (200_000, 1971), 'N-43-I': (200_000, 1964), 'N-44-II': (200_000, 1967),
                  'N-44-VIII': (200_000, 1973), 'N-44-XV': (200_000, 1975), 'N-44-III': (200_000, 1967),
                  'N-44-IV': (200_000, 1970), 'N-44-X': (200_000, 1962), 'N-44-XI': (200_000, 1968),
                  'N-43-VII': (200_000, 1964), 'N-43-VIII': (200_000, 1964), 'N-43-XVI': (200_000, 1976),
                  'N-44-XVI': (200_000, 1975), 'N-44-XVII': (200_000, 1970), 'N-44-XX': (200_000, 1957),
                  'N-44-XXII': (200_000, 1974), 'N-44-XXIII': (200_000, 1977), 'N-43-XIV': (200_000, 1971),
                  'N-43-XV': (200_000, 1977), 'N-44-XIX': (200_000, 1959), 'N-43-XI': (200_000, 2005),
                  'N-44-VII': (200_000, 2001), 'N-44-XIV': (200_000, 2001), 'N-43-XII': (200_000, 2001),
                  'N-44-V': (200_000, 1965),
                  # batch r200g (2026-10-06): map-only ~1650 x 2400 px previews (no legend / imprint on geokniga), legends rebuilt
                  # from the printed indices + the series legend; corners + 15'x10' graticule ties (leave-one-out median 11-53 m).
                  # Years = the geokniga record (COMPILATION) year, no imprint; P-37-VI: no year on the record -> 1987 from its
                  # series neighbours (placeholder). P-37-VI fitted equirectangular (--proj eqc: the preview is stretched, meridians
                  # straight). P-39-XII agrees 3 % / kappa 0.01 with P-39_g3 (1:1M: basal till over the whole sheet) but 85 % with
                  # the independent 1:200k P-40-VII across the seam: the maps disagree, finest wins. P-37-VI / P-39-VIII / P-37-VII,
                  # VIII: lacustrine-glacial / fluvioglacial units where the 1:1M has till, kept as printed; dropped aH (P-37-VII,VIII)
                  'P-37-V': (200_000, 1987), 'P-37-IV': (200_000, 1987), 'P-37-VI': (200_000, 1987),
                  'P-39-XII': (200_000, 1988), 'P-39-VIII': (200_000, 1985), 'P-37-VII,VIII': (200_000, 1991),
                  # batch r200k (2026-10-06): N-54-XXII,XXIII Okha preview (~44 m/px, ql legend + qinf imprint: printed 2009);
                  # printed frame 141d45'-143E x 53d20'-54N passed with --lonlat (= the neatline layer, the footprint);
                  # 4 corners + 11 graticule + 42 frame-tick ties, leave-one-out median/max 23/69 m; lakes carry lH2 (L)
                  'N-54-XXII,XXIII': (200_000, 2009),
                  # batch r200f (2026-10-06): map-only previews (~34-40 m/px; no legend / imprint images on disk) -> legends
                  # rebuilt from the printed indices, tints calibrated on the map; years = geokniga record (compilation) years.
                  # Corners on the inner neatline edge (--no-snap) + 9 interior graticule ties (rms 21-42 m), the ruled O-45
                  # Ketskaya / Kuzbasskaya sheets with 3-4 mid-side ties (rms 27-79 m). They upgrade 1:1M ground, not fallback.
                  # P-42-I kappa -0.10 vs P-42_pq is a systematic swap (1966 alluvial vs 2010s lacustrine-alluvial terraces; 88 %
                  # primary-or-secondary). O-45-XXXI (1960) is the weakest: el+dQ2-3 (962 km2) and eolQ3-4 (1,177 km2) fail both
                  # references where O-45_pq (2021) maps Petrovsk loessoid - registered by the finest rule, FLAGGED for review
                  'R-46-XVII,XVIII': (200_000, 2006), 'P-52-XXVII': (200_000, 1987), 'P-58-XXIX': (200_000, 2002),
                  'P-42-I': (200_000, 1966), 'O-45-XXVII': (200_000, 1962), 'O-45-XXVI': (200_000, 1962),
                  'O-45-XX': (200_000, 1963), 'O-45-XXXI': (200_000, 1960),
                  # batch r200i (2026-10-06): ~2000-px previews with ql legend + qinf imprint (years = print dates); 4 corners
                  # on the inner neatline + 9 interior 15'x10' crossings + 12 graticule-at-frame ties (the minute bar is printed
                  # off-register on these previews: not used); leave-one-out median 15-62 m (work/r200i/notes.txt).
                  # N-42-XI: legend note says the ubiquitous saIII cover (0.5-3 m) was REMOVED from the map -> aI-II (watershed
                  # plains) and PREQ ('under the subaerial cover') recoded E with hclass2 F / R (seams 88 % vs 1-11 % as
                  # printed) - FLAGGED for review. O-44-XXV (2000) maps the plain as Fedosovo lake deposits L/O where O-44-XXXI
                  # (1971) has loess-like cover E (seam 37 %, chance 34 %); O-44-XXIX bogs / lake-bog clays (55 %) conflict
                  # with both references - map interpretation. O-41-XXI not registered (bog vs cover-loam greys inseparable)
                  'N-42-VI': (200_000, 1976), 'N-42-V': (200_000, 1976), 'N-42-III': (200_000, 1977), 'N-42-IV': (200_000, 1978),
                  'N-42-XII': (200_000, 1977), 'N-42-XI': (200_000, 1987), 'O-44-XXV': (200_000, 2000),
                  'O-44-XXXI': (200_000, 1971), 'O-44-XXIX': (200_000, 1970),
                  # batch r200j (2026-10-06): Transbaikal 2nd-edition previews (years = print dates); ties = interior
                  # crossings + graticule-at-frame points (leave-one-out median 10-12 m). On M-50-V / M-50-IV / N-50-XXX the
                  # legend tints were up to 15 dE off the map (units swapped): tints sampled on the map beside printed labels
                  # (label-point leave-one-out 81-94 %). Blue-violet 'PREQ' patches labelled e on M-50-IV -> second e tint
                  'M-50-XI': (200_000, 2006), 'M-50-V': (200_000, 2001), 'M-50-IV': (200_000, 2002),
                  'N-50-XXX': (200_000, 2006), 'N-51-XV': (200_000, 2004), 'N-51-XVI': (200_000, 2004),
                  # batch r200e (2026-10-06): NW Russia (Mezen / Tikhvin-Onega / Kola / Karelian series) map-only previews
                  # (no legend / imprint images): legends from the printed indices, de-hatched (brighter half of a 7x7/9x9
                  # window), tints calibrated on the map; corners + 5' minute-bar ties + interior 30'x10' crossings (independent
                  # interior check 23-62 m median). Years = geokniga record (compilation) years. Q-37-XXII,XXIII,XXIV: the face
                  # is drawn only east of 39d35.3'E -> measured frame 39.588-42E (= its neatline). Q-36-III,IV tH thinned
                  'Q-38-XXIII,XXIV': (200_000, 1988), 'Q-38-XXI,XXII': (200_000, 1988), 'Q-36-III,IV': (200_000, 1999),
                  'Q-38-XIX,XX': (200_000, 1985), 'Q-38-XXIX,XXX': (200_000, 1967), 'Q-37-XXII,XXIII,XXIV': (200_000, 1986),
                  'Q-38-XIII,XIV': (200_000, 1985), 'Q-36-XXXI,XXXII': (200_000, 1981), 'Q-38-VI': (200_000, 1961),
                  # batch r200h (2026-10-06): O-43 previews (~34 m/px), years = print dates from the imprint pages; fit rms
                  # 43-133 m, leave-one-out median 16-42 m. Ishim / Tobolsk 1st editions (1966-71): every unit coloured, the
                  # vertical lithology ruling removed (prep_vlines), fills from map tints at labelled units. West-Siberian
                  # sheets (1997-2000: XXI, XXII, XXX, XXXV): cover deposits only as symbols over a base unit -> composites
                  # cover/base (boundaries +-1 km); their 'eluvial-deluvial' cover coded as worded (W) -> seams with the Ishim /
                  # Tobolsk sheets (cover loams = E) near chance: see the decision on the West-Siberian cover coding.
                  # O-43-XXVII: low floodplain and eolian sands share one cream, split by a line along the Irtysh escarpment
                  'O-43-XIX': (200_000, 1971), 'O-43-XX': (200_000, 1968), 'O-43-XXI': (200_000, 1997),
                  'O-43-XXII': (200_000, 1997), 'O-43-XXV': (200_000, 1970), 'O-43-XXVI': (200_000, 1968),
                  'O-43-XXVII': (200_000, 1966), 'O-43-XXVIII': (200_000, 1970), 'O-43-XXX': (200_000, 2000),
                  'O-43-XXXII': (200_000, 1970), 'O-43-XXXIII': (200_000, 1968), 'O-43-XXXV': (200_000, 1999),
                  'O-43-XXXVI': (200_000, 1970),
                  # batch pv_fe (2026-10-06): the geokniga 'O-56 (Magadan); P-56,57 (Seymchan)' preview holds the FULL P-56,57 frame
                  # (150-162E, 60-64N; fills ~123k km2 of the P-56 gap that had no source) plus an O-56 land block; N-(53),54 is
                  # printed from 135E. Units read on the map (no legend image on geokniga); eqdc 47/62 fits (edge ratio to 1e-5).
                  # Print years not legible: years of the geokniga records (2026-10-06, was a 1985 placeholder): 'O-56; P-56,57'
                  # 43169 1988, N-(53),54 44386 1973. gIII4 / fII / fIII2 on P-56,57 fail validation
                  # (11-41 %) but are kept as printed (interpretation change between generations, as on P-46)
                  'P-56-57_g2pv': (1_000_000, 1988), 'O-56_g2pv': (1_000_000, 1988), 'N-53-54_g2pv': (1_000_000, 1973),
                  # batch pv_ne (2026-10-06): gap halves only (168-174E). Q-58,59: no legend on the image, indices read on the map,
                  # eqdc 47/62 783 m rms; 'Российской Федерации' title -> printed 1992 or later (1999 per the geokniga record 43253;
                  # was a 1995 placeholder). P-58,59 Kamenskoe
                  # (1983): 4 corners + 20 edge ties + 12 graticule ties, eqdc 47/62 303 m. Validation 60-80 % primary vs Q2500 / g3
                  # halves; glacial units (gIII) disagree with the 3rd generation (slope cover over till), kept as printed
                  'Q-58-59_g2pv': (1_000_000, 1999), 'P-58-59_g2pv': (1_000_000, 1983),
                  # batch pv_cs (2026-10-06): printed frames are 90-99E. N-46,(47) Abakan signed for print 20.V.1977, sheet-local cone
                  # (75 m; NOT 47/62), hatch overprints painted as composites (cover loams E, peat O, end-moraine grid T), fII/fIII/gII
                  # dropped (0-22 % agreement); O-46,(47) Krasnoyarsk: no legend/imprint on geokniga (units read on the map), eqdc 47/62
                  # 272 m, 'new series' title -> before 1992; 1971 per the geokniga record 44788 (was a 1980 placeholder)
                  'N-46-47_g2pv': (1_000_000, 1977), 'O-46-47_g2pv': (1_000_000, 1971),
                  # batch pv_ws (2026-10-06): no legend/title/imprint on either preview, legends reconstructed from printed indices +
                  # neighbouring-sheet conventions. O-(41),42 Tyumen printed 63-72E, O-42 part shipped (56.5 % primary vs 13 1:200k
                  # sheets), 'new series' -> before 1992, 1982 per the geokniga record 44525 (was a 1980 placeholder). M-(44),45
                  # printed 81-90E (1970 per the geokniga record,
                  # unverified on the preview); eqdc 47/62 + 4 graticule ties 229 m
                  'O-41-42_g2pv': (1_000_000, 1982), 'M-44-45_g2pv': (1_000_000, 1970)}
# preview years that are not print dates (meta lists): placeholders; 1:200k geokniga record (compilation) years
# (1:1M record years are publication years: 10/12 exact against the imprints)
PREVIEW_YEAR_PLACEHOLDER = ['N-44-V', 'P-37-VI']
PREVIEW_YEAR_COMPILED = ['P-37-V', 'P-37-IV', 'P-39-XII', 'P-39-VIII', 'P-37-VII,VIII',
                         'R-46-XVII,XVIII', 'P-52-XXVII', 'P-58-XXIX', 'P-42-I', 'O-45-XXVII', 'O-45-XXVI', 'O-45-XX', 'O-45-XXXI',
                         'Q-38-XXIII,XXIV', 'Q-38-XXI,XXII', 'Q-36-III,IV', 'Q-38-XIX,XX', 'Q-38-XXIX,XXX', 'Q-37-XXII,XXIII,XXIV',
                         'Q-38-XIII,XIV', 'Q-36-XXXI,XXXII', 'Q-38-VI']


def preview():
    pdfvec('ru_vsegei_preview', PREVIEW_SHEETS,
           'VSEGEI GGK-1000 and GGK-200 sheets colour-classified from geokniga ~2000-px PREVIEWS '
           '(1:1M ~0.35 km/px; 1:200k ~34-60 m/px)',
           'VSEGEI Gosgeolkarta sheet via geokniga.org ("for familiarisation only"); 2000-px preview JPG, colour-classified')


def q2500():
    """VSEGEI 1:2.5M Map of Quaternary Formations of the Russian Federation (2014),
    extracted by q2500_extract.py (legend-chart colours, graticule-fitted conic).
    Backdrop: fills only what no finer Russian source covers."""
    src = 'ru_vsegei_q2500'
    g = gpd.read_file(f'{S.WORK}/q2500/q2500.gpkg', layer='units')
    # uppercase-L ('loess-like') units mean Ice Complex in NE Siberia but loess on the
    # Russian Plain / southern West Siberia: decided by location; the key carries the zone so the
    # crosswalk row can differ. Reviewed 2026-10-04 (Hugues: hclass follows the map's own wording,
    # yedoma status is the separate IRYP column): kept, because the Q2500 legend itself has a
    # 'Лёссовая едомная' (loess-yedoma) formation, mapped in NE Siberia, next to plain 'Лёссовая'
    pt = g.geometry.representative_point().to_crs(4284)
    ne = (pt.x >= 100) & (pt.y >= 60)
    isL = g['index'].str.match(r'^L')
    g.loc[isL & ne, ['hclass', 'hclass2', 'note']] = ['Y', 'L', 'L-unit in NE Siberia (>=100E, >=60N): Ice Complex (provisional rule)']
    g.loc[isL & ~ne, ['hclass', 'hclass2', 'note']] = ['E', '', 'L-unit outside NE Siberia: loess (provisional rule)']
    # 'vlef' / 'vlex' = 'Вулканогенный эффузивный / эксплозивный' in the Q2500 legend (2026-10-06; found by the P-58,59
    # preview validation): Quaternary volcanics, NOT eolian - the bare 'v' prefix rule had made ~78k km2 of lava E.
    # Neogene ones (index ending in N) are pre-Quaternary rock with a volcanic secondary.
    isV = g['index'].str.match(r'^vle[fx]')
    g.loc[isV, ['hclass', 'hclass2', 'note']] = ['V', '', 'vlef/vlex = volcanic effusive / explosive (Q2500 legend)']
    g.loc[isV & g['index'].str.endswith('N'), ['hclass', 'hclass2', 'note']] = ['R', 'V', 'Neogene volcanics (Q2500 vlef/vlex ... N)']
    # Marine / glaciomarine codes (m*, *gm*) inland in southern Siberia (2026-10-06, found by the N-46,(47) preview
    # validation): 321k km2 of 'gmII' / 'm,gmIII' between 60-135E south of 62N (Sayan, Baikal, Yenisei Ridge), far from any
    # coast where no marine Quaternary exists. The colour-vote extraction gave violet mountain tints the glaciomarine label;
    # the true unit is unresolved -> Q (undivided), flagged
    inl = (pt.y < 62) & (pt.x > 60) & (pt.x < 135) & g['index'].str.match(r'^(?:m|[a-z,]*gm)')
    g.loc[inl, ['hclass', 'hclass2', 'note']] = ['Q', '', 'marine/glaciomarine label on an inland southern-Siberian tint (colour-vote '
                                                           'mismatch): unresolved, coded Q']
    # Fill colours whose glaciomarine label (from the colour vote) is contradicted by the finer maps: bedrock / slope /
    # eluvium tints of the mountains (scripts/q2500_bedrock_audit.py, work/q2500/bedrock_audit_mix.csv, 2026-10-06; shares
    # of the area compared with the 1:1M + 1:200k sheets; marine + glaciomarine <= 1 % on each). Applied everywhere the
    # fill occurs, after (and overriding) the inland rule above. Genuinely coastal gm fills (#d5b8d8, #b397c7, #a787be,
    # #bd96c1, #bc8cbe, #a763a8: M+GM 64-86 %) stay as extracted.
    FILLFIX = {'#9f81b5': ('R', 'C', 'bedrock with slope cover (finer maps: R 41 %, C 43 %)'),
               '#d680b5': ('C', 'W', 'mountain-slope cover (C 44 %, W 42 %)'),
               '#cb8fbf': ('W', 'C', 'eluvium (W 54 %, C 35 %)'),
               '#9c85bd': ('C', 'R', 'slope cover over bedrock (C 49 %, R 17 %)'),
               '#ac92c0': ('C', 'W', 'slope cover (C 36 %, W 20 %)'),
               '#b691ba': ('Q', '', 'mixed plains (F 32 %, L 21 %, E 20 %): unresolved'),
               '#c59cc8': ('T', '', 'till (T 54 %)')}
    ffix = g['fill'].isin(list(FILLFIX)) & g['index'].str.contains('gm')
    for f, (h, h2, why) in FILLFIX.items():
        g.loc[ffix & (g['fill'] == f), ['hclass', 'hclass2', 'note']] = [h, h2, f'gm label from the colour vote on fill {f}, but ' + why]
    suffix = np.where(ffix, '|' + g['fill'], np.where(inl, '|INL', ''))
    g['xkey'] = 'Q25|' + g['index'] + np.where(isL, np.where(ne, '|NE', '|W'), '') + suffix
    u, _ = S.standardise(g, src_id=src, code='index', desc='note', xkey='xkey',
                         sheet=pd.Series('Q2500', index=g.index), scale_den=2_500_000, pub_year=2014,
                         extra=('fill',),
                         licence='VSEGEI Map of Quaternary Formations of the RF 1:2.5M (2014), PDF via Wayback Machine',
                         redistribution='internal_only')
    # union_all of 443k detailed polygons ran > 1.5 h: the footprint of a single-sheet
    # backdrop only needs its outline, so union the units COARSENED to 5 km first
    coarse = shapely.buffer(shapely.simplify(u.geometry.values, 2500.0), 2500.0)
    geom = shapely.buffer(shapely.union_all(coarse, grid_size=500.0), -2500.0)
    fp = gpd.GeoDataFrame({'src_id': [src], 'overlay': [0]}, geometry=[shapely.simplify(geom, 2000.0)], crs=S.CRS)
    fp['src_sheet'] = 'Q2500'
    rows = g.drop_duplicates('xkey')[['xkey', 'hclass', 'hclass2']].assign(texture='', cover='', ice_rich='')
    rows['xwalk_note'] = 'Q2500 index ' + g.drop_duplicates('xkey')['index'] + ': ' + g.drop_duplicates('xkey')['note']
    rows[['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']].to_csv(f'{S.XWALK}/{src}.csv', index=False)
    finish(u, fp, src, dict(title='VSEGEI Quaternary Formations of the RF 1:2.5M (2014)', datum='EPSG:4284',
                            projection=json.load(open(f'{S.WORK}/q2500/projection.json'))))


ALL = {'ru_vsegei_q2500': q2500, 'ru_veremeeva_r5557': veremeeva, 'ru_lena_peter2014': lena, 'ru_kytalyk_base': kytalyk,
       'ru_vsegei200': vsegei200, 'ru_vsegei_pdf': pdfvec, 'ru_vsegei_preview': preview}

if __name__ == '__main__':
    for s in (sys.argv[1:] or ALL):
        print('==', s, flush=True)
        ALL[s]()
