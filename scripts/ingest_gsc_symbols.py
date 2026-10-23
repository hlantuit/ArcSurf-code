#!/usr/bin/env python
"""
GSC Open Files whose unit polygons carry only a GSC terrain SYMBOL (no SDM schema), with a
crosswalk written here by parsing the symbol grammar:
  [texture lowercase] GENETIC CAPS [qualifier lowercase] { '.' | '/' second component }
  first component -> hclass (GF/GL/GM recognised as pairs; else the first capital:
  T till, R rock, A alluvial, M marine, G glaciofluvial, L lacustrine, O organic, E eolian,
  C colluvial, W marine); a second capital in the first component (AM, TM) or a second
  component -> hclass2; qualifier v -> veneer, b -> blanket.
Sources:
  ca_gsc_of5153  OF 5153 (2006) Predictive mapping of surficial materials, Schultz Lake area
                 (NTS 66A), Radarsat-1 + Landsat 7, 1:250 000; field Unit; shapefile ships no
                 .prj: UTM 14N NAD83 per its readme (EPSG:26914); Water/Unknown/NeedToFix dropped.
  ca_gsc_of8651  OF 8651 (2019) Cartographie du Quaternaire, region du gisement Amaruq, Nunavut,
                 regional map (carte_regionale.gdb, depot_surface, field new_code), 1:60 000.
usage: ingest_gsc_symbols.py [src ...]
"""
import os
import re
import sys

import pandas as pd
import pyogrio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

U = '/albedo/scratch/user/hlantuit/arctic_surficial/unz/canada'
GEN = {'GF': 'GF', 'GL': 'GL', 'GM': 'GM', 'T': 'T', 'R': 'R', 'A': 'F', 'M': 'M', 'G': 'GF', 'L': 'L',
       'O': 'O', 'E': 'E', 'C': 'C', 'W': 'M'}
TEX = {'T': 'diamicton', 'R': 'unknown', 'F': 'mixed', 'M': 'fines', 'GF': 'gravel', 'GL': 'fines',
       'GM': 'fines', 'L': 'fines', 'O': 'organic', 'E': 'sand', 'C': 'bouldery'}
DROP = {'water', 'unknown', 'needtofix', '', 'nan', 'none'}


def comp(s):
    """'GLv' -> ('GL', 'v', ''); 'AM' -> ('A', '', 'M'); 'Tr' -> ('T', 'r', '')."""
    m = re.match(r'^[a-z]*([A-Z]+)([a-z]*)', s)
    if not m:
        return None, '', ''
    caps, q = m.group(1), m.group(2)
    if caps[:2] in ('GF', 'GL', 'GM'):
        return GEN[caps[:2]], q, (GEN.get(caps[2:3], '') if len(caps) > 2 else '')
    return GEN.get(caps[0]), q, (GEN.get(caps[1:2], '') if len(caps) > 1 else '')


def parse(code):
    c = str(code).strip()
    if c.lower() in DROP:
        return ('DROP', '', 'unknown', 'unknown', f'{c}: not a unit - dropped')
    parts = re.split(r'[./]', c)
    h, q, h2 = comp(parts[0])
    if not h:
        return ('DROP', '', 'unknown', 'unknown', f'{c}: unparsed symbol - dropped')
    if len(parts) > 1 and not h2:
        h2 = comp(parts[1])[0] or ''
    h2 = '' if h2 == h else h2
    cover = 'veneer' if q.startswith('v') else ('blanket' if q.startswith('b') else 'unknown')
    if cover == 'veneer' and not h2:
        h2 = 'R'
    return (h, h2, TEX.get(h, 'unknown'), cover, f'GSC symbol {c}: genetic {h}' + (f', second {h2}' if h2 else '') +
            (f', {cover}' if cover != 'unknown' else ''))


def run(src, g, key, scale, year, tier, title):
    g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
    g['xkey'] = g[key].astype(str).str.strip()
    u, _ = S.standardise(g, src_id=src, code='xkey', desc='xkey', xkey='xkey', scale_den=scale, pub_year=year,
                         conf_tier=tier, licence='Open Government Licence - Canada', redistribution='open')
    u['xkey'] = u['xkey'].fillna('Unknown').astype(str)          # empty Unit fields -> dropped
    u['src_code'] = u['src_code'].fillna('Unknown')
    p, m = S.write_std(u, S.footprint_from_units(u, coarse=250.0), src, dict(title=title))
    xw = [[k, *parse(k)] for k in sorted(u['xkey'].unique())]
    pd.DataFrame([[k, h, h2, t, c, 'unknown', n] for k, (h, h2, t, c, n) in ((x[0], x[1:]) for x in xw)],
                 columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(f'{S.XWALK}/{src}.csv', index=False)
    print(src, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')})
    for x in xw:
        print('  ', x)


def of5153():
    g = pyogrio.read_dataframe(f'{U}/of_5153/Appendix/Surficial-Geology.shp').set_crs(26914, allow_override=True)
    run('ca_gsc_of5153', g, 'Unit', 250_000, 2006, 'Predictive',
        'GSC OF 5153 Predictive mapping of surficial materials, Schultz Lake area (NTS 66A), Radarsat-1 + Landsat 7')


def of8651():
    import glob
    gdb = glob.glob(f'{U}/of_8651/**/carte_regionale.gdb', recursive=True)[0]
    g = pyogrio.read_dataframe(gdb, layer='depot_surface')
    run('ca_gsc_of8651', g, 'new_code', 60_000, 2019, 'Surficial',
        'GSC OF 8651 Cartographie du Quaternaire, region du gisement Amaruq, Nunavut (carte regionale)')


ALL = {'ca_gsc_of5153': of5153, 'ca_gsc_of8651': of8651}
if __name__ == '__main__':
    for s in (sys.argv[1:] or ALL):
        print('==', s, flush=True)
        ALL[s]()
