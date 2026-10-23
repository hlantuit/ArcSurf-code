"""Line-map regions (line_to_polygons.py) + transcribed labels -> georeferenced unit polygons
and the std source 'ca_gsc_lines' (one sheet per config row, appended).

Labels follow Rampton's GSC notation: texture prefix (f clay/silt/fine sand, s sand, a sand
or gravel, g gravel, d diamicton, w driftwood/organic debris) + genetic capital (L lacustrine,
M marine [bold] or morainal [with d], G glaciofluvial, C colluvial, F fluvial, O organic,
E eolian) + age superscript (A active, M recently exposed / drained) + morphology suffix
(p plain, t terrace, b beach, k kettled/thermokarst, m rolling, h hummocky, r ...).
Unlabelled regions: hatch_frac > 0.5 -> organic deposits (hatch overprint, 'organic deposits
2-15 ft thick'); water_frac > 0.5 -> water (dropped); otherwise the label of the labelled
neighbour sharing the longest border (flagged gapfill 'label_neighbour').
Georeference: frame corners (px) refined to the neatline, lon/lat from the sheet's corner
and tick labels, affine px -> UTM (datum given), clipped to the frame. frame_px is either
'xl,xr,yt,yb' (axis-aligned scan, lines refined) or four measured corners 'x,y;x,y;x,y;x,y' (TL;TR;BR;BL;
skewed scans, used as given).
Optional config columns: 'legend' = sources/<csv> with label,hclass,hclass2,texture,description (sheets not in
Rampton's notation: the crosswalk comes from it); 'background' = label given to every unlabelled region
(reconnaissance maps whose legend says that areas without a unit symbol are one background class, e.g.
OF 21 Fulton 1968: 'largely rock, near surface rock or till plains'), instead of the neighbour fill.
Optional 'fit' = corner_fit (projection + spline from the four corners, for curved graticules), 'clip_lonlat' =
lon0,lat0,lon1,lat1 mapping limit inside the frame (corner_fit branch), and 'unlabelled' = drop
(regions without a label are no-data, for partly mapped sheets) instead of the neighbour fill.
usage: line_georef_ingest.py <sheet_key>   (row in sources/line_sheets.csv)"""
import json
import os
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyproj  # noqa: E402
import rasterio.features as rf  # noqa: E402
import shapely  # noqa: E402
from affine import Affine  # noqa: E402
from shapely.geometry import shape  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
GEN = {'L': 'L', 'G': 'GF', 'C': 'C', 'F': 'F', 'O': 'O', 'E': 'E', 'A': 'F'}
TEX = {'f': 'fines', 's': 'sand', 'a': 'mixed', 'g': 'gravel', 'd': 'diamicton', 'w': 'organic', 'c': 'fines', 'r': 'bouldery'}


def parse(lbl):
    m = re.match(r'^([a-z]?)([A-Z])([AM]?)([a-z]*)$', lbl)
    if not m:
        return dict(hclass='Q', hclass2='', texture='unknown', note=f'unparsed {lbl}')
    tx, g, age, morph = m.groups()
    if g == 'M':
        h = 'T' if tx == 'd' else 'M'
    else:
        h = GEN.get(g, 'Q')
    if g == 'L' and age == 'M':
        h2 = 'K'                        # recently drained lake basin (thaw-lake cycle)
    else:
        h2 = ''
    return dict(hclass=h, hclass2=h2, texture=TEX.get(tx, 'unknown'), note=f'{lbl}: tex {tx or "-"} gen {g} age {age or "-"} morph {morph or "-"}')


def neighbours_longest(lab, r):
    m = lab == r
    edge = shapely_free_edge(m)
    vals = lab[edge]
    vals = vals[vals != r]
    if not len(vals):
        return None
    u, c = np.unique(vals, return_counts=True)
    return [int(x) for x in u[np.argsort(-c)]]


def shapely_free_edge(m):
    from scipy import ndimage as ndi
    return ndi.binary_dilation(m, iterations=2) & ~m


def refine_line(gray, approx, axis, lo, hi, win=40):
    """position of the darkest straight line near approx (column if axis=0, row if axis=1)"""
    if axis == 0:
        prof = gray[lo:hi, max(approx - win, 0):approx + win].mean(0)
    else:
        prof = gray[max(approx - win, 0):approx + win, lo:hi].mean(1)
    return max(approx - win, 0) + int(np.argmin(prof))


def main():
    key = sys.argv[1]
    cfg = pd.read_csv(f'{ROOT}/sources/line_sheets.csv', dtype=str, keep_default_na=False).set_index('key').loc[key]
    pre = f'{S.WORK}/linevec/{cfg.prefix}'
    lab = np.load(pre + '_regions.npy')
    R = json.load(open(pre + '_regions.json'))
    wx0, wy0 = R['window'][:2]
    regs = {r['id']: r for r in R['regions']}
    L = pd.read_csv(f'{ROOT}/sources/{cfg.labels}', dtype={'id': int, 'label': str}).set_index('id')['label'].to_dict()
    # classes per region
    cls = {}
    for rid, r in regs.items():
        if rid in L:
            cls[rid] = (L[rid], '')
        elif r.get('water_frac', 0) > 0.5:
            cls[rid] = ('WATER', '')
        elif r.get('hatch_frac', 0) > 0.5:
            cls[rid] = ('O_hatch', '')
    bg = cfg.get('background', '')
    for rid in regs:
        if rid in cls:
            continue
        if bg:
            cls[rid] = (bg, 'background'); continue
        if cfg.get('unlabelled', '') == 'drop':
            cls[rid] = ('DROP', 'unlabelled'); continue
        for n in (neighbours_longest(lab, rid) or []):
            if n in cls and cls[n][0] not in ('WATER',) and not cls[n][1]:
                cls[rid] = (cls[n][0], 'label_neighbour'); break
        else:
            cls[rid] = ('UNLABELLED', 'unlabelled')
    # frame + transform
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    gray = np.asarray(Image.open(cfg.image).convert('L'), dtype=np.float32)
    if ';' in cfg.frame_px:                      # four measured corners TL;TR;BR;BL (skewed scan)
        px = np.array([[float(v) for v in c.split(',')] for c in cfg.frame_px.split(';')])
        xl2, xr2, yt2, yb2 = px[:, 0].min(), px[:, 0].max(), px[:, 1].min(), px[:, 1].max()
    else:
        xl, xr, yt, yb = map(int, cfg.frame_px.split(','))
        xl2 = refine_line(gray, xl, 0, yt + 200, yb - 200); xr2 = refine_line(gray, xr, 0, yt + 200, yb - 200)
        yt2 = refine_line(gray, yt, 1, xl + 200, xr - 200); yb2 = refine_line(gray, yb, 1, xl + 200, xr - 200)
        px = np.array([[xl2, yt2], [xr2, yt2], [xr2, yb2], [xl2, yb2]], float)
    lon0, lat0, lon1, lat1 = map(float, cfg.frame_lonlat.split(','))
    # 'fit_lonlat': the graticule box whose four corners frame_px gives, when it differs from the clip frame (stepped
    # sheets, OF 189: the frame's own corners are not all printed, so the fit uses an interior 1-degree box + ties)
    f0, f1, f2, f3 = map(float, (cfg.get('fit_lonlat', '') or cfg.frame_lonlat).split(','))
    if cfg.get('fit', '') == 'corner_fit':
        # projection + thin-plate spline from the four corners (jpg_to_polygons.corner_fit): parallels are curves on
        # wide high-latitude frames (Map 2-1981, 7 deg x 2 deg at 78 N: 2.6 km sag), which an affine cannot follow
        import jpg_to_polygons as J
        # optional interior graticule crossings 'lon,lat,x,y;...' (stepped 1:1M frames, OF 189: the lon/lat box corners
        # are measured crossings, the other crossings tie the interior); residuals then cover corners + ties
        ties = [tuple(float(v) for v in t.split(',')) for t in str(cfg.get('ties', '') or '').split(';') if t.strip()]
        tfc, fit = J.corner_fit([tuple(p) for p in px], f0, f1, f2, f3, str(int(cfg.datum)), ties or None)
        res = np.array(fit['corner_residuals_m'])
        print('corner_fit', fit['projection'], '| corner (+tie) residual m', np.round(res, 1))
        rows = []
        for g, v in rf.shapes(lab.astype(np.int32), transform=Affine.translation(wx0, wy0)):
            v = int(v)
            if v == 0 or cls[v][0] in ('WATER', 'DROP'):
                continue
            geom = shape(g).simplify(1.0)
            rows.append(dict(rid=v, label=cls[v][0], gapfill=cls[v][1], geometry=shapely.transform(geom, tfc)))
        g = gpd.GeoDataFrame(rows, crs=S.CRS)
        to6931 = pyproj.Transformer.from_crs(int(cfg.datum), S.CRS, always_xy=True)
        fr = shapely.segmentize(shapely.box(lon0, lat0, lon1, lat1), 0.01)
        frame = shapely.Polygon(np.c_[to6931.transform(*np.array(fr.exterior.coords).T)])
        if cfg.get('clip_lonlat', ''):
            # mapping limit inside the frame (Map 2-1981: units only south of 78 30 N): units and neatline end there
            c0, c1, c2, c3 = map(float, cfg.clip_lonlat.split(','))
            cb = shapely.segmentize(shapely.box(c0, c1, c2, c3), 0.01)
            frame = frame.intersection(shapely.Polygon(np.c_[to6931.transform(*np.array(cb.exterior.coords).T)]))
        g['geometry'] = shapely.intersection(shapely.make_valid(g.geometry.values), frame)
        g = S.polygons_only(g).dissolve(by=['rid', 'label', 'gapfill'], as_index=False)
        g = S.polygons_only(g)
        g['sheet'] = key
        out = f'{S.WORK}/linevec/{key}.gpkg'
        g.to_file(out, layer='units', driver='GPKG')
        gpd.GeoDataFrame(dict(sheet=[key]), geometry=[frame], crs=S.CRS).to_file(out, layer='neatline', driver='GPKG')
        a = g.assign(km2=g.area / 1e6).groupby('label').km2.sum().sort_values(ascending=False)
        print('units', len(g), 'km2', round(g.area.sum() / 1e6, 1), '| unlabelled km2', round(float(a.get('UNLABELLED', 0)), 2))
        print(a.round(2).head(25).to_dict())
        json.dump(dict(sheet=key, corner_residual_m=res.tolist(), projection=fit['projection'], frame_px=px.tolist(),
                       n_ties=len(ties), rms_m=fit['rms_m'], max_res_m=fit['max_res_m'], m_per_px=fit['m_per_px']),
                  open(out.replace('.gpkg', '.json'), 'w'))
        return
    crs = pyproj.CRS.from_user_input(cfg.utm_epsg)
    tr = pyproj.Transformer.from_crs(int(cfg.datum), crs, always_xy=True)
    ll = [(lon0, lat1), (lon1, lat1), (lon1, lat0), (lon0, lat0)]
    xy = np.array([tr.transform(*p) for p in ll])
    A = np.c_[px, np.ones(4)]
    cx, *_ = np.linalg.lstsq(A, xy[:, 0], rcond=None)
    cy, *_ = np.linalg.lstsq(A, xy[:, 1], rcond=None)
    res = np.hypot(A @ cx - xy[:, 0], A @ cy - xy[:, 1])
    aff = Affine(cx[0], cx[1], cx[2], cy[0], cy[1], cy[2]) * Affine.translation(wx0, wy0)
    print('frame px', (xl2, xr2, yt2, yb2), '| corner residual m', np.round(res, 1))
    # polygons
    rows = []
    for g, v in rf.shapes(lab.astype(np.int32), transform=aff):
        v = int(v)
        if v == 0 or cls[v][0] == 'WATER':
            continue
        rows.append(dict(rid=v, label=cls[v][0], gapfill=cls[v][1], geometry=shape(g).simplify(2.0)))
    g = gpd.GeoDataFrame(rows, crs=crs)
    fr = shapely.segmentize(shapely.box(lon0, lat0, lon1, lat1), 0.002)
    frame = gpd.GeoSeries([fr], crs=int(cfg.datum)).to_crs(crs).iloc[0]
    g['geometry'] = shapely.intersection(shapely.make_valid(g.geometry.values), frame)
    g = S.polygons_only(g).dissolve(by=['rid', 'label', 'gapfill'], as_index=False)
    g = S.polygons_only(g.to_crs(S.CRS))
    g['sheet'] = key
    out = f'{S.WORK}/linevec/{key}.gpkg'
    g.to_file(out, layer='units', driver='GPKG')
    gpd.GeoDataFrame(dict(sheet=[key]), geometry=[frame], crs=crs).to_crs(S.CRS).to_file(out, layer='neatline', driver='GPKG')
    a = g.assign(km2=g.area / 1e6).groupby('label').km2.sum().sort_values(ascending=False)
    print('units', len(g), 'km2', round(g.area.sum() / 1e6, 1), '| unlabelled km2', round(float(a.get('UNLABELLED', 0)), 2),
          '| neighbour-filled km2', round(float(g[g.gapfill == 'label_neighbour'].area.sum() / 1e6), 2))
    print(a.round(2).head(20).to_dict())
    json.dump(dict(sheet=key, corner_residual_m=res.tolist(), frame_px=px.tolist()), open(out.replace('.gpkg', '.json'), 'w'))


if __name__ == '__main__':
    main()
