"""Ingest line-map sheets (work/linevec/<key>.gpkg by line_georef_ingest.py, rows of
sources/line_sheets.csv) as source 'ca_gsc_lines'. Crosswalk key '<key>|<label>', built here
from the Rampton label grammar (line_georef_ingest.parse); hatch-only regions -> O.
QC note: Tuk 1:25k coast check median 51 m vs OSM is NOT a fit error alone - that coast
retreats ~1-2 m/yr, i.e. 50-100 m since the 1970s air photos (corner residual 28 m).
Sheets with a 'legend' column in line_sheets.csv take their crosswalk from that legend file (label, hclass,
hclass2, texture, description; optional cover) instead of the Rampton grammar."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import surflib as S  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
from line_georef_ingest import parse  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SRC = 'ca_gsc_lines'
OGL = 'Open Government Licence - Canada'
cfg = pd.read_csv(f'{ROOT}/sources/line_sheets.csv', dtype=str, keep_default_na=False)
# processed but NOT merged (decision 2026-10-03): OF189 1:1M (695 labels, 107 ties) reaches only 248 km2 of gap and was
# never reviewed for merging (catalogue flag no_gap_units)
NOT_MERGED = {'of189_c', 'of189_s'}
# sheets that YIELD to a coarser map where both map (decision H. Lantuit 2026-10-06): OF48 97C (Klassen 1971, 1:250k
# reconnaissance: till) vs Rampton's A1647a (Tuktoyaktuk Coastlands 1:500k, 1987: organic / thermokarst) in the NW corner
# (126.5-128W, 69.5-70N, ~443 km2, 0 % agreement): A1647a kept. Mask = union of A1647a's extracted units (work/gscvec, not
# the ca_gsc_scans std file, which its own ingest rewrites in parallel), closed by +-50 m
YIELD_TO = {'of48_097c': f'{S.WORK}/gscvec/A1647a.gpkg'}


def _mask(path):
    m = gpd.read_file(path, layer='units').to_crs(S.CRS)
    return shapely.buffer(shapely.buffer(shapely.union_all(shapely.make_valid(m.geometry.values)), 50), -50)
parts, fps, xw = [], [], []
for _, c in cfg.iterrows():
    if c.key in NOT_MERGED:
        print('not merged (decision):', c.key); continue
    f = f'{S.WORK}/linevec/{c.key}.gpkg'
    if not os.path.exists(f):
        print('missing', c.key); continue
    g = gpd.read_file(f, layer='units').to_crs(S.CRS)
    g = g[g['label'] != 'UNLABELLED']
    ymask = _mask(YIELD_TO[c.key]) if c.key in YIELD_TO else None
    if ymask is not None:
        a0 = g.area.sum()
        g = g.set_geometry(gpd.GeoSeries(shapely.difference(shapely.make_valid(g.geometry.values), ymask),
                                         index=g.index, crs=g.crs))
        g = g[~g.geometry.is_empty & (g.area > 0)]
        print(f'{c.key}: yields {(a0 - g.area.sum()) / 1e6:.1f} km2 to {os.path.basename(YIELD_TO[c.key])}')
    g['xkey'] = c.key + '|' + g['label']
    u, _ = S.standardise(g, src_id=SRC, code='label', desc='label', xkey='xkey', sheet=pd.Series(c.key, index=g.index),
                         scale_den=int(c.scale), pub_year=int(c.year), conf_tier='Surficial', extra=('gapfill',),
                         licence=OGL + ' (GSC line-map scan; polygons from linework, labels transcribed)', redistribution='open')
    parts.append(u)
    fp = gpd.read_file(f, layer='neatline').to_crs(S.CRS)
    if ymask is not None:                      # the footprint must not claim the yielded corner either
        fp = fp.set_geometry(gpd.GeoSeries(shapely.difference(shapely.make_valid(fp.geometry.values), ymask),
                                           index=fp.index, crs=fp.crs))
    fp['src_id'], fp['overlay'], fp['src_sheet'] = SRC, 0, c.key
    fps.append(fp[['src_id', 'overlay', 'src_sheet', 'geometry']])
    leg = None
    if c.get('legend'):                          # sheets not in Rampton's notation: crosswalk from the sheet legend
        leg = pd.read_csv(f"{ROOT}/sources/{c['legend']}", dtype=str, keep_default_na=False).set_index('label')
    for lbl in sorted(g['label'].unique()):
        if leg is not None:
            assert lbl in leg.index, f'{c.key}: label {lbl!r} not in {c["legend"]}'
            r = leg.loc[lbl]
            xw.append([f'{c.key}|{lbl}', r.hclass, r.hclass2, r.texture, r.get('cover', ''), '', f"{c.key} {lbl}: {r.description}"])
        elif lbl == 'O_hatch':
            xw.append([f'{c.key}|{lbl}', 'O', '', 'organic', '', '', 'cross-hatch overprint: organic deposits 2-15 ft thick'])
        else:
            p = parse(lbl)
            xw.append([f'{c.key}|{lbl}', p['hclass'], p['hclass2'], p['texture'], '', '', f"{c.key} {p['note']}"])
    print(c.key, len(u), 'polys', round(u.area.sum() / 1e6, 1), 'km2')
u = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
pd.DataFrame(xw, columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(f'{S.XWALK}/{SRC}.csv', index=False)
S.write_std(u, fp, SRC, dict(title='GSC line/label map scans, vectorised from linework (this work)', sheets=list(cfg.key)))
