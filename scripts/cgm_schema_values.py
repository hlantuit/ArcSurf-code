"""Value samples of the unit fields in each old CGM schema."""
import glob
import sys

import pyogrio

GSC = '/albedo/work/user/hlantuit/arctic_surficial/raw/canada/gsc'
CASES = [('CGM112', 'Data/SHP/Surficial/GEO_POLYS.shp', None),
         ('CGM143', 'Data/SHP/Surficial/GEO_POLYS.shp', None),
         ('CGM141', 'Data/SHP/Surficial/GEO_POLYS.shp', None),
         ('CGM136', 'Data/SHP/Surficial/GEO_POLYS.shp', None),
         ('CGM21', 'Data/SHP/Surficial/GeologyPolygons.shp', None),
         ('CGM60', 'Data/SHP/Surficial/GeoUnits0060.shp', None),
         ('CGM45', 'Data/PMF/data/cw10/CGM0045.gdb', 'GEO_POLYS_CGM45'),
         ('CGM15', 'Apps/data/cw10/CGM_0015_p1.gdb', 'Geo_Ply'),
         ('CGM58', 'Apps/data/cw10/CGM0058.gdb', None),
         ('CGM64', None, None), ('CGM65', None, None), ('CGM140', None, None), ('CGM139', None, None)]
for s, rel, layer in CASES:
    d = f'{GSC}/{s}'
    if rel is None:        # list every polygon layer to find the unit one
        for g in glob.glob(f'{d}/**/*.gdb', recursive=True) + glob.glob(f'{d}/**/Surficial/*.shp', recursive=True):
            try:
                print('  ', s, g.replace(d + '/', ''), [(n, t) for n, t in pyogrio.list_layers(g) if t and 'Polygon' in str(t)][:8])
            except Exception as e:
                print('  ', s, g, 'ERR', e)
        continue
    p = f'{d}/{rel}'
    if layer is None and p.endswith('.gdb'):
        print('  ', s, [(n, t) for n, t in pyogrio.list_layers(p) if t and 'Polygon' in str(t)])
        continue
    df = pyogrio.read_dataframe(p, layer=layer, read_geometry=False)
    print(f'## {s} {rel} {layer or ""} n={len(df)}')
    for c in df.columns:
        v = df[c].astype(str).value_counts()
        if 1 < len(v) < 400 and not c.lower().startswith(('shape', 'area', 'perim', 'objectid', 'fid')):
            print(f'     {c:12s} {len(v):4d} {dict(list(v.head(7).items()))}')
