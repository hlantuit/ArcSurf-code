#!/usr/bin/env python
"""
BC Terrain Resource Information Management (TRIM-based terrain mapping), northern BC
(downloaded 2026-10-01 from openmaps.gov.bc.ca WFS, bbox 56-60.1N, EPSG:3005) ->
work/std/ca_bc_ter.gpkg + xwalk/ca_bc_ter.csv (written here from the BC Terrain
Classification System material codes, Howes & Kenk 1997).

Three layers, one source; src_sheet = PROJECT_NAME so each project's own scale sets its
precedence in the merge (1:20k TSM/TBT beat 1:50k TIM beat the 1:250k Stikine-Iskut TIM):
  STE_TER_INVENTORY_POLYS_SVW  (TIM)    STE_TER_BIOTERRAIN_POLYS_SVW (TBT, TEM, TEMWHR)
  STE_TER_STABILITY_POLYS_SVW  (TSM, TSMDET)
POLYGON_TEXTURE_CLASS / _THICKNESS_CLASS are null everywhere, so texture and cover are
parsed from the FIRST component label (texture letters + MATERIAL + expression letters)
and carried as texture_src / cover_src. xkey = first|second component material code.
Not Classified (N) and unparseable labels are dropped (they must not claim area).
Not served as polygons: PEMTBT projects (Fort Nelson TSA 98.6k km2, Muskwa-Kechika 11.9k km2).
Licence: Open Government Licence - British Columbia.
"""
import os
import re
import sys

import geopandas as gpd
import pandas as pd
import pyogrio
import shapely

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402

R = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/bc_ter'
LAYERS = ['inventory', 'bioterrain', 'stability']
SRC = 'ca_bc_ter'
# BC TCS material -> (hclass, default texture)
MAT = {'A': ('X', 'mixed'), 'C': ('C', 'bouldery'), 'D': ('W', 'bouldery'), 'E': ('E', 'sand'),
       'F': ('F', 'gravel'), 'FG': ('GF', 'gravel'), 'I': ('I', 'unknown'), 'L': ('L', 'fines'),
       'LG': ('GL', 'fines'), 'M': ('T', 'diamicton'), 'O': ('O', 'organic'), 'R': ('R', 'unknown'),
       'U': ('Q', 'unknown'), 'V': ('V', 'unknown'), 'W': ('M', 'fines'), 'WG': ('GM', 'fines'),
       'N': ('DROP', 'unknown'), '?': ('DROP', 'unknown')}
TEX = {**dict.fromkeys('abkxr', 'bouldery'), **dict.fromkeys('pg', 'gravel'), 's': 'sand',
       **dict.fromkeys('zcm', 'fines'), 'd': 'diamicton', 'y': 'mixed', **dict.fromkeys('euh', 'organic')}
LBL = re.compile(r'^([a-z]*)([A-Z])(G?)([AI]?)([a-z]*)')


def parse(lbl):
    """'zsFGv' -> ('FG', 'fines', 'veneer'); first letter of the texture string dominates."""
    m = LBL.match(str(lbl or '').strip())
    if not m:
        return '?', 'unknown', 'unknown'
    tex, mat, g, _, exp = m.groups()
    mat = mat + g
    if mat not in MAT:
        mat = mat[0] if mat[0] in MAT else '?'
    t = TEX.get(tex[:1], 'unknown') if tex else 'unknown'
    c = 'veneer' if exp[:1] in ('v', 'x') else ('blanket' if exp[:1] == 'b' else 'unknown')
    return mat, t, c


def main():
    b = pyogrio.read_dataframe(f'{R}/ter_project_boundaries_n56_bbox.geojson', read_geometry=False)
    yr = (b.assign(y=pd.to_numeric(b['PROJECT_COMPLETION_DATE'].astype(str).str.extract(r'((?:19|20)\d\d)')[0],
                                   errors='coerce'))
          .groupby('PROJECT_NAME')['y'].max())
    parts = []
    for lay in LAYERS:
        g = pyogrio.read_dataframe(f'{R}/bc_ste_ter_{lay}_polys_svw_n56_epsg3005.gpkg',
                                   columns=['PROJECT_TYPE', 'PROJECT_NAME', 'PROJECT_MAP_SCALE',
                                            'TERRAIN_POLYGON_LBL', 'FIRST_TERRAIN_LBL', 'SCND_TERRAIN_LBL',
                                            'TERRAIN_CPNT_1_DECILE', 'DOMINANT_SURFICIAL_MATERIAL'])
        g['layer'] = lay
        parts.append(g)
        print(lay, len(g), flush=True)
    g = pd.concat(parts, ignore_index=True)
    g = gpd.GeoDataFrame(g, geometry='geometry', crs=parts[0].crs)
    p1 = g['FIRST_TERRAIN_LBL'].map(parse)
    g['m1'] = [p[0] for p in p1]
    g['texture_src'] = [p[1] for p in p1]
    g['cover_src'] = [p[2] for p in p1]
    g['m2'] = g['SCND_TERRAIN_LBL'].map(lambda s: parse(s)[0] if isinstance(s, str) and s.strip() else '')
    g['xkey'] = g['m1'] + '|' + g['m2']
    # N (not classified) / unparseable: removed BEFORE the footprint so they claim nothing
    g = g[g['m1'].map(lambda k: MAT.get(k, ('DROP',))[0]) != 'DROP']
    # 1:250k projects whose polygon carries no scale fall back to 50k only where TBT left it blank (Sikanni)
    g['scale'] = pd.to_numeric(g['PROJECT_MAP_SCALE'], errors='coerce').fillna(50_000).astype(int)
    g['year'] = g['PROJECT_NAME'].map(yr)
    g = S.in_amap(S.polygons_only(g.to_crs(S.CRS)))
    xw = []
    for k in sorted(g['xkey'].unique()):
        a, b2 = k.split('|')
        h, t = MAT.get(a, ('DROP', 'unknown'))
        h2 = MAT.get(b2, ('', ''))[0] if b2 else ''
        h2 = '' if h2 in ('DROP', h) else h2
        xw.append([k, h, h2, t, 'unknown', 'unknown', f'BC TCS material {a} (2nd component {b2 or "-"})'])
    u, _ = S.standardise(g, src_id=SRC, code='TERRAIN_POLYGON_LBL', desc='DOMINANT_SURFICIAL_MATERIAL',
                         sheet='PROJECT_NAME', xkey='xkey', scale_den='scale', pub_year='year',
                         extra=('PROJECT_TYPE', 'layer', 'TERRAIN_CPNT_1_DECILE'),
                         carry=('texture_src', 'cover_src'),
                         licence='Open Government Licence - British Columbia', redistribution='open')
    u['src_sheet'] = u['src_sheet'].fillna('')
    # one coarse footprint per project (precedence is per sheet)
    fps = []
    for name, grp in u.groupby('src_sheet'):
        f = S.footprint_from_units(grp, coarse=250.0)
        f['src_sheet'] = name
        fps.append(f)
    fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), geometry='geometry', crs=S.CRS)
    fp['geometry'] = shapely.make_valid(fp.geometry.values)
    p, m = S.write_std(u, fp, SRC, dict(title='BC Terrain mapping (TIM/TBT/TSM), northern BC',
                                        scale_note='per project: 1:20k TSM/TBT, 1:50k TIM, 1:250k Stikine-Iskut TIM'))
    pd.DataFrame(xw, columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']) \
        .drop_duplicates('xkey').to_csv(f'{S.XWALK}/{SRC}.csv', index=False)
    print(SRC, {k: m.get(k) for k in ('n_polygons', 'area_km2', 'footprint_km2', 'n_codes')}, flush=True)
    print(u.assign(a=u.area / 1e6).groupby('scale_den')['a'].sum().round(0).to_dict())


if __name__ == '__main__':
    main()
