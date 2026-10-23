#!/usr/bin/env python
"""
Nordic + Iceland ingests -> work/std/<src>.gpkg

  no_ngu_losmasser     NGU Løsmasser Detaljert/Lokalt/Regionalt, 5 counties (Møre og
                       Romsdal, Trøndelag, Nordland, Troms, Finnmark); one "sheet" per
                       county x product, scale per polygon from egnetMålestokk
  sj_npi_g250          Svalbard G250 geology + glacier / moraine-on-ice / tidal-flat /
                       lake layers (overlaps resolved: tidal > lake > glacier > moraine-
                       on-ice > geology)
  sj_npi_s100_overlay  Svalbard S100 moraines + river plains (1:100k), partial overlay
  sj_npi_j250_janmayen Jan Mayen J250
  se_sgu_jordarter250k SGU 1:250k Nordligaste Sverige (grundlager)
  se_sgu_jordarter25k  SGU 1:25k-100k (grundlager), north of ~60.8 N (was ~65.6 N until 2026-10-03)
  se_sgu_jordarter1m   SGU 1:1M (1994), national fallback for mountain areas without finer SGU mapping
  fi_gtk_maapera200k   GTK 1:200k (surface class), genesis for textural classes from
                       the GTK 1:1M map by representative point (flagged)
  fi_gtk_maapera20k    GTK 1:20k/1:50k (surface class + TUNNUS), Arctic bbox only
  is_natt_j600         Iceland 1:600k geology
  is_natt_n25_coastal  Iceland tidal flats / salt marsh / Holocene lava (1:25k), overlay

usage: ingest_nordic.py [src ...]   (default: all)
"""
import glob
import os
import sys

import numpy as np
import pandas as pd
import geopandas as gpd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

UNZ = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/nordic'
ICE = '/albedo/scratch/user/hlantuit/arctic_surficial/probe/iceland'
NLOD = 'NLOD 1.0 (Norsk lisens for offentlige data)'
CCBY = 'CC-BY 4.0'


def one(pattern):
    hits = sorted(glob.glob(f'{UNZ}/{pattern}', recursive=True))
    assert hits, pattern
    return hits[0]


def finish(units, fps, src, meta):
    units = gpd.GeoDataFrame(pd.concat(units, ignore_index=True), crs=S.CRS) if isinstance(units, list) else units
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS) if isinstance(fps, list) else fps
    p, m = S.write_std(units, fp, src, meta)
    S.code_table(units).to_csv(f'{S.WORK}/codes_{src}.csv', index=False)
    print(src, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')}, flush=True)


# ---------------------------------------------------------------- Norway
def ngu():
    src = 'no_ngu_losmasser'
    default = {'Detaljert': 20000, 'Lokalt': 50000, 'Region': 250000}
    units, fps = [], []
    for z in sorted(glob.glob(f'{UNZ}/Geologi_*_25833_Losmasse*_GPKG')):
        tag = os.path.basename(z)
        county = tag.split('_25833_')[0].replace('Geologi_', '')
        prod = tag.split('_Losmasse')[1].split('_GPKG')[0]
        gp = glob.glob(f'{z}/**/*.gpkg', recursive=True)[0]
        g = pyogrio.read_dataframe(gp, layer='LøsmasseFlate')
        g = g.to_crs(S.CRS)
        g = S.in_amap(g)
        if g.empty:
            print('  ', tag, 'outside AMAP')
            continue
        sc = pd.to_numeric(g['egnetMålestokk'], errors='coerce')
        g['scale'] = sc.where(sc > 0, default[prod])
        g['sheet'] = f'{county}_{prod}'
        u, _ = S.standardise(g, src_id=src, code='løsmassetype', desc='løsmassetypeNavn',
                             sheet='sheet', scale_den='scale', pub_year=2026,
                             extra=('egnetMålestokk', 'oppdateringsdato'),
                             licence=NLOD, redistribution='open')
        u['xkey'] = u['src_code'].str.replace(r'\.0$', '', regex=True)
        fp = S.footprint_from_units(u)
        fp['src_sheet'] = f'{county}_{prod}'
        units.append(u)
        fps.append(fp)
        print('  ', tag, len(u), round(u.area.sum() / 1e6), flush=True)
    finish(units, fps, src, dict(title='NGU Løsmasser detaljert/lokalt/regionalt (2026)',
                                 note='scale per polygon from egnetMålestokk; 0 -> product default'))


# ---------------------------------------------------------------- Svalbard
def g250():
    src = 'sj_npi_g250'
    d = os.path.dirname(one('**/G250 Shape files/g250_Geology.shp'))
    layers = [('g250_Tidal_flats', 'TIDAL_FLAT', 0), ('g250_Lake_polygon', 'LAKE', 1),
              ('g250_Glacier_polygon', 'GLACIER', 2), ('g250_Moraine_on_ice', 'MORAINE_ON_ICE', 3),
              ('g250_Geology', None, 4)]
    parts = []
    for lyr, key, prio in layers:
        g = gpd.read_file(f'{d}/{lyr}.shp').to_crs(S.CRS)
        if key is None:
            q = g['GEO_CODE'].isin([1010, 1020, 1030, 1090, 1110, 1113])
            g['xkey'] = g['GEO_CODE'].astype(int).astype(str).where(q, 'BEDROCK')
            g['desc'] = g['NAME']
        else:
            g['xkey'], g['desc'] = key, key.lower()
        g['prio'] = prio
        g['code'] = g['GEO_CODE'].astype('Int64').astype(str)
        parts.append(g[['xkey', 'desc', 'prio', 'code', 'geometry']])
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    g, removed = S.resolve_overlaps(S.polygons_only(g), 'prio')
    print(f'   G250 overlap removed: {removed:,.1f} km2')
    u, _ = S.standardise(g, src_id=src, code='code', desc='desc', xkey='xkey',
                         scale_den=250_000, pub_year=2016, licence=CCBY, redistribution='open')
    finish(u, S.footprint_from_units(u), src, dict(title='NPI Geological map of Svalbard 1:250 000 (G250)',
                                                  overlap_removed_km2=removed))


def close_rings(geom):
    from shapely.geometry import MultiPolygon, Polygon
    if geom is None or geom.is_empty:
        return geom
    def fix(p):
        return Polygon(list(p.exterior.coords), [list(i.coords) for i in p.interiors])  # constructor closes rings
    if geom.geom_type == 'Polygon':
        return fix(geom)
    if geom.geom_type == 'MultiPolygon':
        return MultiPolygon([fix(p) for p in geom.geoms])
    return geom


def s100():
    src = 'sj_npi_s100_overlay'
    d = os.path.dirname(one('**/S100_Morener_f.shp'))
    parts = []
    for lyr, key in (('S100_Morener_f', 'MORENE'), ('S100_Elvesletter_f', 'ELVESLETTE')):
        g = gpd.read_file(f'{d}/{lyr}.shp')
        # S100 is PolygonZ with rings closed in 2D but not in Z: to_crs keeps Z and GEOS then
        # rejects the ring ('not closed'). Drop Z, then close any truly open ring.
        g['geometry'] = shapely.force_2d(g.geometry.values)
        g['geometry'] = g.geometry.apply(close_rings)
        g = g.to_crs(S.CRS)
        print('   ', lyr, 'JORDART', g['JORDART'].value_counts(dropna=False).head(10).to_dict())
        g['xkey'] = key
        g['desc'] = key.lower() + ' | JORDART ' + g['JORDART'].astype(str)
        g['prio'] = 0 if key == 'MORENE' else 1
        parts.append(g[['xkey', 'desc', 'prio', 'geometry']])
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    g, removed = S.resolve_overlaps(S.polygons_only(g), 'prio')
    u, _ = S.standardise(g, src_id=src, code='xkey', desc='desc', xkey='xkey', scale_den=100_000,
                         pub_year=2020, licence=CCBY, redistribution='open')
    finish(u, S.footprint_from_units(u, overlay=True), src,
           dict(title='NPI Kartdata Svalbard S100: moraines and river plains (topographic)', overlay=True,
                overlap_removed_km2=removed))


def j250():
    src = 'sj_npi_j250_janmayen'
    g = gpd.read_file(one('**/NP_J250_Geologi_f.geojson')).to_crs(S.CRS)
    q = g['geo_code'].isin([1020, 1090, 1160, 1161, 1162, 1163, 1164, 1165, 1170, 1180])
    g['xkey'] = g['geo_code'].astype(int).astype(str).where(q, 'BEDROCK')
    u, _ = S.standardise(g, src_id=src, code='geo_code', desc='Name', xkey='xkey', scale_den=250_000,
                         pub_year=2021, licence=CCBY, redistribution='open')
    finish(u, S.footprint_from_units(u), src, dict(title='NPI Jan Mayen geology 1:250 000'))


# ---------------------------------------------------------------- Sweden
def sgu(which):
    if which == '1m':
        # SGU Jordarter 1:1M (1994, compiled from older material): national fallback for the Swedish mountain areas that
        # neither the 1:25k-100k nor the 1:250k product covers (6.6k km2 of the build domain had no source)
        src, gp, bbox, scale = 'se_sgu_jordarter1m', one('jordarter1miljon/*.gpkg'), None, 1_000_000
    elif which == '250k':
        src, gp, bbox, scale = 'se_sgu_jordarter250k', one('jordarter250k/*.gpkg'), None, 250_000
    else:
        src, gp, scale = 'se_sgu_jordarter25k', one('jordarter25k-100k/*.gpkg'), None
        # SWEREF99 TM north of ~60.8 N (2026-10-03; was 7_280_000 = ~65.6 N): the build domain includes the mountain
        # permafrost of Jamtland, Harjedalen and the Dalarna fjall, which were left with no source at all (22.7k km2)
        bbox = (200_000, 6_750_000, 1_000_000, 7_800_000)
    g = pyogrio.read_dataframe(gp, layer='grundlager', bbox=bbox)
    cov = pyogrio.read_dataframe(gp, layer='tackningskarta', bbox=bbox)
    g, cov = g.to_crs(S.CRS), cov.to_crs(S.CRS)
    g, cov = S.in_amap(g), S.in_amap(cov)
    # scale per mapping unit from the coverage map (rek_skala), joined by kartering
    if which == '1m':
        g['scale'], g['year'] = scale, 1994
    elif which != '250k':
        sc = cov[['kartering', 'rek_skala', 'avslut_ar']].drop_duplicates('kartering')
        g = g.merge(sc, on='kartering', how='left')
        g['scale'] = pd.to_numeric(g['rek_skala'], errors='coerce').fillna(100_000)
        g['year'] = pd.to_numeric(g['avslut_ar'], errors='coerce')
    else:
        g['scale'], g['year'] = scale, 2019
    u, _ = S.standardise(g, src_id=src, code='jg2', desc='jg2_tx', sheet='kartering',
                         scale_den='scale', pub_year='year', licence='CC0 1.0', redistribution='open')
    u['xkey'] = u['src_code'].str.replace(r'\.0$', '', regex=True)
    u['src_sheet'] = u['src_sheet'].fillna('')
    fps = []
    for k, part in u.groupby('src_sheet'):
        f = S.footprint_from_units(part)
        f['src_sheet'] = k
        fps.append(f)
    finish(u, fps, src, dict(title=f'SGU Jordarter {which}', bbox=bbox))


# ---------------------------------------------------------------- Finland
GTK1M_GEN = {  # GTK 1:1M TUNNUS -> genetic hclass donated to textural 200k classes
    'Mr': 'T', 'KM': 'T', 'SiMr': 'T', 'Mr/HM': 'T', 'HM': 'GF', 'SHM': 'GF',
    'SrHk': 'GF', 'LSHk': 'M', 'Jk': 'F', 'Sa': 'Q', 'KSa': 'Q',
}
GTK1M_NOTE = {'LSHk': 'littoral gravel-sand (1:1M) - shoreline of Baltic stages',
              'Sa': 'homogeneous clay-silt (1:1M): marine or lacustrine not stated',
              'KSa': 'laminated clay-silt (1:1M): glaciolacustrine/marine not stated'}


def gtk200():
    src = 'fi_gtk_maapera200k'
    gdb = one('maapera_200k*/*.gdb')
    g = pyogrio.read_dataframe(gdb, layer='mp200k_maalajit', bbox=(0, 7_280_000, 800_000, 7_800_000))
    g = S.in_amap(g.to_crs(S.CRS))
    g['code'] = pd.to_numeric(g['PINTAMAALAJI_KOODI'], errors='coerce').astype('Int64').astype(str)
    # genesis donor: GTK 1:1M, by representative point, only for the textural classes
    m1 = pyogrio.read_dataframe(one('maapera_1m*/*.gdb'), layer='mp1m_kerrostuma_muodostuma',
                                bbox=(0, 7_280_000, 800_000, 7_800_000)).to_crs(S.CRS)
    textural = g['code'].isin(['195210', '195310', '195410', '195413'])
    pts = gpd.GeoDataFrame(geometry=g.loc[textural].representative_point(), crs=S.CRS)
    j = gpd.sjoin(pts, m1[['TUNNUS', 'geometry']], how='left', predicate='within')
    j = j[~j.index.duplicated()]
    don = j['TUNNUS'].map(GTK1M_GEN)
    g['hclass_src'] = ''
    g.loc[don.index, 'hclass_src'] = don.fillna('').values
    g['gtk1m'] = ''
    g.loc[j.index, 'gtk1m'] = j['TUNNUS'].fillna('').values
    print('   genesis donated from 1:1M:', g['hclass_src'].value_counts().to_dict())
    u, _ = S.standardise(g, src_id=src, code='code', desc='PINTAMAALAJI', scale_den=200_000,
                         pub_year=2015, extra=('POHJAMAALAJI', 'gtk1m'), carry=('hclass_src',),
                         licence='CC-BY 4.0 (GTK)', redistribution='open')
    finish(u, S.footprint_from_units(u), src, dict(title='GTK Maaperä 1:200 000 + genesis from 1:1M'))


def gtk20():
    src = 'fi_gtk_maapera20k'
    gdb = one('maapera_20_50k*/*.gdb')
    parts = []
    for lyr, sc in (('mp20k_maalajit', 20_000), ('mp50k_maalajit', 50_000)):
        g = pyogrio.read_dataframe(gdb, layer=lyr, bbox=(0, 7_280_000, 800_000, 7_800_000))
        g = S.in_amap(g.to_crs(S.CRS))
        g['scale'], g['sheet'] = sc, lyr
        parts.append(g)
        print('  ', lyr, len(g))
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    g['code'] = pd.to_numeric(g['PINTAMAALAJI_KOODI'], errors='coerce').astype('Int64').astype(str)
    u, _ = S.standardise(g, src_id=src, code='code', desc='PINTAMAALAJI', sheet='sheet',
                         scale_den='scale', pub_year=2015,
                         extra=('TUNNUS', 'POHJAMAALAJI', 'MUODOSTUMA'),
                         licence='CC-BY 4.0 (GTK)', redistribution='open')
    fps = []
    for k, part in u.groupby('src_sheet'):
        f = S.footprint_from_units(part)
        f['src_sheet'] = k
        fps.append(f)
    finish(u, fps, src, dict(title='GTK Maaperä 1:20 000 / 1:50 000'))


# ---------------------------------------------------------------- Iceland
def j600():
    src = 'is_natt_j600'
    g = pyogrio.read_dataframe(f'{ICE}/NI_J600v_berg_2.utg.gdb', layer='j600v_jardlog_2utg_fl')
    g = g.to_crs(S.CRS)
    g['code'] = g['FLOKKUR_1'].fillna(g['FLOKKUR']).astype(str)
    g['desc'] = g['jardsogulegurAldur'].fillna('') + ' | ' + g['jardmLandmJardefna'].fillna('')
    u, _ = S.standardise(g, src_id=src, code='code', desc='desc', scale_den=600_000, pub_year=2014,
                         licence=CCBY, redistribution='open')
    finish(u, S.footprint_from_units(u), src, dict(title='NÍ Jarðfræðikort af Íslandi 1:600 000, 2. útg.'))


def n25():
    src = 'is_natt_n25_coastal'
    parts = []
    for key, f, prio in (('leirur', 'ni_n50v_serstok_vernd_1_n25v_leirur_fl.json', 0),
                         ('sjavarfitjar', 'ni_n50v_serstok_vernd_1_n25v_sjavarfitjar_fl.json', 1),
                         ('hraun_nutima', 'ni_n50v_serstok_vernd_1_n25v_hraun_nutima_fl.json', 2)):
        g = pyogrio.read_dataframe(f'{ICE}/{f}').to_crs(S.CRS)
        g['xkey'], g['prio'] = key, prio
        parts.append(g[['xkey', 'prio', 'geometry']])
    g = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
    g, removed = S.resolve_overlaps(S.polygons_only(g), 'prio')
    u, _ = S.standardise(g, src_id=src, code='xkey', desc='xkey', xkey='xkey', scale_den=25_000,
                         pub_year=2020, licence=CCBY, redistribution='open')
    finish(u, S.footprint_from_units(u, overlay=True), src,
           dict(title='NÍ sérstök vernd: leirur, sjávarfitjar, nútímahraun (1:25k)', overlay=True,
                overlap_removed_km2=removed))


ALL = {'no_ngu_losmasser': ngu, 'sj_npi_g250': g250, 'sj_npi_s100_overlay': s100,
       'sj_npi_j250_janmayen': j250, 'se_sgu_jordarter250k': lambda: sgu('250k'),
       'se_sgu_jordarter25k': lambda: sgu('25k'), 'se_sgu_jordarter1m': lambda: sgu('1m'), 'fi_gtk_maapera200k': gtk200,
       'fi_gtk_maapera20k': gtk20, 'is_natt_j600': j600, 'is_natt_n25_coastal': n25}

if __name__ == '__main__':
    for s in (sys.argv[1:] or ALL):
        print('==', s, flush=True)
        ALL[s]()
