#!/usr/bin/env python
"""
GSC Open File 5116 (St-Onge, Ford & Henderson 2007), Digital geoscience atlas of Baffin Island (south of 70N
and east of 80W), DOI 10.4095/223256; surficial layer AS1536_units_ply = GSC Map 1536A, Surficial materials
and landforms, Cumberland Peninsula, Baffin Island (Dyke, Andrews & Miller 1982), scale 1:500 000, digitised
for the atlas (polygon field MapUnit: 1-8 and Ice). Legend transcribed from the map scan
(raw/canada/ostr_new/123331, gscmap-a_1536a). The atlas's other surficial layers are already merged
(Hodg_* = A2042a/A2043a Hidden Bay and Dredge_* = A2073a Ekalugad Fiord, in ca_gsc_legacy) or are the national
1:5M map (AS1880 = Map 1880A, Fulton 1995 = ca_gsc_5m), so only AS1536 is ingested.
Source -> ca_gsc_of5116. usage: ingest_of5116.py
"""
import os
import sys

import geopandas as gpd
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

SRC = 'ca_gsc_of5116'
SHP = ('/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/ostr_new/223256/x/data/surficial_geology/'
       'AS1536_units_ply.shp')
# MapUnit -> hclass, hclass2, texture, cover, ice_rich, legend text (Map 1536A)
XW = {
    'Ice': ('I', '', 'unknown', 'unknown', 'unknown', 'Glacier ice'),
    '8': ('C', '', 'bouldery', 'unknown', 'yes', 'Colluvium (scree): extensive accumulations of blocks 0.5-1.5 m with '
          'interstitial ice and sandy gravel at the bases of bedrock cliffs; in many places flowed downslope to form rock '
          'glaciers (rock-glacierized scree)'),
    '7': ('GF', 'F', 'gravel', 'unknown', 'unknown', 'Active proglacial alluvium (outwash): sorted and stratified gravels '
          'and sands forming large floodplains, seasonally flooded, shifting braided channels'),
    '6': ('GF', 'F', 'gravel', 'unknown', 'unknown', 'Inactive alluvium: predominantly terraced proglacial outwash gravels '
          'and sands; inactive to intermittently active alluvial fans of boulder gravel'),
    '5': ('GL', 'T', 'mixed', 'unknown', 'unknown', 'Areas inundated by former glacier-dammed lakes: wave-modified till, '
          'beach sand and gravel, deltaic gravel, sand and silt, and bedrock'),
    '4': ('M', '', 'mixed', 'blanket', 'unknown', 'Emerged marine sediment: mainly thick (>10 m) deltaic gravel, sand and '
          'silt, minor beach gravel and wave-modified till'),
    '3': ('T', '', 'diamicton', 'blanket', 'unknown', 'Till (ground moraine): diamicton 1-2 m thick, ice cored near existing '
          'glaciers; 20-50 % gravel, >= 60 % sand, < 10 % clay; numerous small ice-moulded bedrock outcrops; locally '
          'rock-glacierized till'),
    '2': ('W', 'R', 'bouldery', 'veneer', 'unknown', 'Residuum: predominantly felsenmeer (blockfields) with interstitial grus, '
          'about 1 m thick over bedrock on broad summits; glacial erratics and till mixed in by cryoturbation'),
    '1': ('R', 'T', 'unknown', 'unknown', 'unknown', 'Bedrock: ice-moulded, hilly to gently rolling plateau surfaces with '
          'lakes and ponds, overlain in many places by small thin patches of till and erratic boulders; steep in deeply '
          'dissected areas'),
}

g = gpd.read_file(SHP)
g['xkey'] = g['MapUnit'].astype('string').str.strip()
n0 = len(g)
g = g[g['xkey'].isin(list(XW))].copy()                      # 2 polygons without MapUnit (GEO_SYM 0) dropped
print(f'{n0} polygons, {n0 - len(g)} without a map unit dropped')
g['desc'] = g['xkey'].map(lambda k: XW[k][5])
g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
u, _ = S.standardise(g, src_id=SRC, code='xkey', desc='desc', xkey='xkey', scale_den=500_000, pub_year=1982,
                     conf_tier='Surficial', licence='Open Government Licence - Canada', redistribution='open')
p, m = S.write_std(u, S.footprint_from_units(u, coarse=250.0), SRC,
                   dict(title='GSC Map 1536A Cumberland Peninsula (Dyke, Andrews & Miller 1982), 1:500 000, '
                              'digitised in GSC Open File 5116 (2007)'))
pd.DataFrame([[k, *v[:5], f'Map 1536A unit {k}: {v[5]}'] for k, v in XW.items()],
             columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(
    f'{S.XWALK}/{SRC}.csv', index=False)
print(SRC, {k: m[k] for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes') if k in m})
a = u.assign(km2=u.area / 1e6).groupby('xkey').km2.sum().round()
print(a.to_dict())
