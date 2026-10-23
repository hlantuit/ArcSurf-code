#!/usr/bin/env python
"""Unit polygons from a RASTER scan (geokniga JPG) of a 1:200k Quaternary sheet.

Two subcommands:

  legend <img> <x0,y0,x1,y1> <out_prefix>
      Find legend swatches (uniform rectangles of one common size) inside the box
      (full-res px), sample each one's colour (median of non-dark interior pixels, so
      the printed index and hatching are ignored), write <out_prefix>_legend.json and
      crops for reading the labels. Transcribe into sources/legend_<sheet>.csv with
      `fill` = the sampled colour.

  extract <img> <sheet> <legend.csv> <out.gpkg> [--dE 14] [--mmu 120] [--map-box x0,y0,x1,y1]
      1. neatline = outline of the largest coloured blob (the map face; legend and
         insets are separated from it by white paper), corners by the x+-y extremes,
         ring split IN ORDER at the corners (as pdf_to_polygons.py);
      2. control points on the parallels (lon by arc fraction) + meridian pins, affine
         fit into eqdc/lcc (Krassowsky), thin-plate-spline snap onto the EXACT frame;
      3. classify: 5x5 median filter (halftone), CIELAB nearest legend colour within
         dE; dark (L<38) and unmatched pixels = unassigned; majority filter; unassigned
         filled from the nearest assigned pixel; sieve below --mmu pixels;
      4. polygonise, transform, clip to the exact frame, dissolve by unit.
      Datum: EPSG:4284 (Pulkovo-1942) assumed, as for every VSEGEI sheet.

Colours are a classification, not a reading of vector fills: report per unit the
fraction of pixels that matched directly (vs. filled), and the pairs of legend
colours closer than dE 8 (confusable).
"""
import argparse
import json
import shlex
import math
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402  (first: PROJ fix)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyproj  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Polygon, shape  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402
from PIL import Image  # noqa: E402
import rasterio.features as rf  # noqa: E402
from affine import Affine  # noqa: E402
import nomen  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def load_rgb(path):
    im = Image.open(path)
    if im.mode == 'CMYK':
        # through the embedded profile: the naive PIL conversion gives saturated, shifted
        # colours (R-53-IX) that crowd the classes together
        icc = im.info.get('icc_profile')
        if icc:
            import io
            from PIL import ImageCms
            im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                           ImageCms.createProfile('sRGB'), outputMode='RGB')
        else:
            im = im.convert('RGB')
    return np.asarray(im.convert('RGB'))


def to_lab(rgb):
    """sRGB uint8 (..., 3) -> CIELAB float32 (D65)."""
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def hex2rgb(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.uint8)


# ------------------------------------------------------------------ legend
def cmd_legend(a):
    rgb = load_rgb(a.img)
    x0, y0, x1, y1 = map(int, a.box.split(','))
    sub = rgb[y0:y1, x0:x1]
    lab = to_lab(sub)
    ink = (lab[..., 0] < 92) | (np.hypot(lab[..., 1], lab[..., 2]) > 12)      # non-paper
    ink = ndi.binary_opening(ink, iterations=2)
    lbl, n = ndi.label(ink)
    objs = ndi.find_objects(lbl)
    cand = []
    for i, sl in enumerate(objs, 1):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if not (60 < w < 400 and 30 < h < 200):
            continue
        fill = (lbl[sl] == i).mean()
        if fill < 0.85:
            continue
        cand.append((w, h, sl, i))
    if not cand:
        sys.exit('no swatch candidates')
    ws = np.median([c[0] for c in cand]); hs = np.median([c[1] for c in cand])
    sw = [c for c in cand if abs(c[0] - ws) < 0.12 * ws and abs(c[1] - hs) < 0.2 * hs]
    out = []
    for w, h, sl, i in sorted(sw, key=lambda c: (round(c[2][1].start / 50), c[2][0].start)):
        ys, xs = sl
        dy, dx = int(h * 0.15), int(w * 0.15)
        core = sub[ys.start + dy:ys.stop - dy, xs.start + dx:xs.stop - dx].reshape(-1, 3)
        L = to_lab(core)[:, 0]
        keep = core[L > np.percentile(L, 35)]            # drop the index text and hatching
        if len(keep) == 0:                                # uniform swatch: percentile == all
            keep = core
        med = np.median(keep, axis=0).astype(int)
        out.append(dict(k=len(out), fill='#%02x%02x%02x' % tuple(med),
                        bbox=[xs.start + x0, ys.start + y0, xs.stop + x0, ys.stop + y0]))
    print(f'swatch size ~{ws:.0f}x{hs:.0f} px; {len(out)} swatches')
    for s in out:
        print(s['k'], s['fill'], s['bbox'])
    json.dump(dict(img=a.img, box=a.box, swatches=out), open(f'{a.out}_legend.json', 'w'), indent=1)
    # crops of ~16 swatches each, label text to the right
    for j in range(0, len(out), 16):
        ch = out[j:j + 16]
        cx0 = min(s['bbox'][0] for s in ch) - 10
        cy0 = min(s['bbox'][1] for s in ch) - 10
        cy1 = max(s['bbox'][3] for s in ch) + 10
        crop = Image.fromarray(rgb[cy0:cy1, cx0:min(cx0 + int(ws * 9), rgb.shape[1])])
        crop.thumbnail((1000, 1600))
        crop.save(f'{a.out}_legend_{j // 16}.png')
        print('saved', f'{a.out}_legend_{j // 16}.png')


# ------------------------------------------------------------------ extract
def neatline(rgb, map_box=None, f=2, mode='colour'):
    """Neatline sides (full-res px) as robust OUTER envelopes of the largest coloured blob.
    White label boxes and text bite INTO the face along its edge, so the first coloured
    pixel per column/row is fitted with iterative rejection: top/bottom = quadratics
    (parallels are arcs on the conic), left/right = straight lines (meridians).
    Returns (edges dict of 60-point polylines, blob, f, fit report)."""
    small = rgb[::f, ::f]
    lab = to_lab(small)
    if mode == 'dark':
        # GSC legacy sheets: only part of the frame is coloured (white = not mapped here),
        # so the neatline is the thin BLACK frame line; first dark pixel inward from the box
        blob = (lab[..., 0] < 45) & (np.hypot(lab[..., 1], lab[..., 2]) < 25)
        if map_box:
            x0, y0, x1, y1 = [v // f for v in map_box]
            m = np.zeros_like(blob); m[y0:y1, x0:x1] = True; blob &= m
        return _envelope(blob, f)
    # strictly COLOURED paper: the minute bar of the frame is black/white and must not
    # join the face (a closing bridged it and put the neatline on the OUTER frame)
    col = (np.hypot(lab[..., 1], lab[..., 2]) > 9) & (lab[..., 0] > 30) & (lab[..., 0] < 96)
    if map_box:
        x0, y0, x1, y1 = [v // f for v in map_box]
        m = np.zeros_like(col); m[y0:y1, x0:x1] = True; col &= m
    col = ndi.binary_opening(col, iterations=1)
    lbl, n = ndi.label(col)
    size = np.bincount(lbl.ravel()); size[0] = 0
    # a wide pale river (S-47 Upper Taimyra) splits the face: keep every large piece,
    # then close river-width gaps (the mask holds no dark pixels, so the closing can
    # no longer reach the black/white minute bar of the frame)
    blob = np.isin(lbl, np.nonzero(size > 0.02 * size.max())[0])
    # padded: the closing's erosion treats outside the image as background and shaved a face
    # lying within 60 px of the image edge (P-48,49 preview: bottom arc cut flat, 3.7 km rms)
    it = max(1, 60 // f)
    blob = ndi.binary_closing(np.pad(blob, it + 2), structure=np.ones((3, 3), bool), iterations=it)[it + 2:-(it + 2), it + 2:-(it + 2)]
    blob = ndi.binary_fill_holes(blob)
    Image.fromarray((blob[::4, ::4] * 255).astype(np.uint8)).save('/tmp/jpg_blob.png')   # QC of the face mask
    return _envelope(blob, f)


def _envelope(blob, f):
    H, W = blob.shape
    ca, ra = blob.any(0), blob.any(1)
    xs, ys = np.nonzero(ca)[0], np.nonzero(ra)[0]
    first_r = np.argmax(blob, 0).astype(float); last_r = (H - 1 - np.argmax(blob[::-1], 0)).astype(float)
    first_c = np.argmax(blob, 1).astype(float); last_c = (W - 1 - np.argmax(blob[:, ::-1], 1)).astype(float)
    rep = {}

    def robust(t, v, deg, inward_sign, name, tol=2.0, n_iter=400):
        """RANSAC: the polynomial with most points within tol px (at 1/f), refit on them.
        Bites (pale units, label boxes) go inward and attachments (frame lines) outward;
        both are outliers, whatever their share, as long as the true edge is the mode."""
        rng = np.random.default_rng(0)
        best_in = None
        for _ in range(n_iter):
            pick = rng.choice(len(t), deg + 1, replace=False)
            if len(np.unique(t[pick])) < deg + 1:
                continue
            c = np.polyfit(t[pick], v[pick], deg)
            inl = np.abs(v - np.polyval(c, t)) < tol
            if best_in is None or inl.sum() > best_in.sum():
                best_in = inl
        c = np.polyfit(t[best_in], v[best_in], deg)
        r = v - np.polyval(c, t)
        rep[name] = dict(kept=round(float(best_in.mean()), 3), rms_px=round(float(np.sqrt((r[best_in] ** 2).mean()) * f), 2))
        return c
    trim = lambda a: a[int(len(a) * .04):int(len(a) * .96)]   # noqa: E731  (corners excluded)
    tx, ly = trim(xs), trim(ys)
    T = robust(tx, first_r[tx], 2, +1, 'top')       # inward = larger row
    B = robust(tx, last_r[tx], 2, -1, 'bottom')
    Lc = robust(ly, first_c[ly], 1, +1, 'left')     # inward = larger column
    Rc = robust(ly, last_c[ly], 1, -1, 'right')

    def meet(hor, ver, y0):
        y = y0
        for _ in range(50):
            x = np.polyval(ver, y); y = np.polyval(hor, x)
        return x, y
    tl = meet(T, Lc, ys[0]); tr = meet(T, Rc, ys[0]); bl = meet(B, Lc, ys[-1]); br = meet(B, Rc, ys[-1])
    q = np.linspace(0, 1, 60)
    hx = lambda a, b: a[0] + q * (b[0] - a[0])   # noqa: E731
    vy = lambda a, b: a[1] + q * (b[1] - a[1])   # noqa: E731
    edges = {'top': np.c_[hx(tl, tr), np.polyval(T, hx(tl, tr))],
             'bottom': np.c_[hx(bl, br), np.polyval(B, hx(bl, br))],
             'left': np.c_[np.polyval(Lc, vy(tl, bl)), vy(tl, bl)],
             'right': np.c_[np.polyval(Rc, vy(tr, br)), vy(tr, br)]}
    edges = {k: v * f + f / 2 for k, v in edges.items()}
    print('neatline envelope fit:', rep)
    return edges, blob, f, rep


def frame_fit(edges, lon0, lat0, lon1, lat1, datum=4284, proj=None):
    """Page->EPSG:6931 transform from the neatline sides (px), as pdf_to_polygons.py."""
    from scipy.interpolate import RBFInterpolator

    def along(pts):
        s = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
        return s / s[-1]
    cps = [(p[0], p[1], lon0 + t * (lon1 - lon0), lat) for name, lat in (('top', lat1), ('bottom', lat0))
           for p, t in zip(edges[name], along(edges[name]))]
    for name, lon in (('left', lon0), ('right', lon1)):
        e = edges[name]
        if e[0][1] > e[-1][1]:
            e = e[::-1]
        cps += [(p[0], p[1], lon, lat1 + t * (lat0 - lat1)) for p, t in zip(e[1:-1], along(e)[1:-1])]
    cps = np.array(cps)
    dl = (lat1 - lat0) / 6
    best = None
    ell = pyproj.CRS.from_epsg(datum).ellipsoid
    ellps = f'+a={ell.semi_major_metre} +rf={ell.inverse_flattening}'
    for kind in (('given',) if proj else ('eqdc', 'lcc', 'tmerc')):
        if kind == 'given':        # explicit projection (T-48-50: Soviet equidistant conic 47/62 N, not a sheet cone)
            crs = pyproj.CRS.from_proj4(f'{proj} {ellps} +units=m +no_defs')
        elif kind == 'tmerc':      # Canadian legacy sheets: Transverse Mercator on the sheet's central meridian
            crs = pyproj.CRS.from_proj4(f'+proj=tmerc +lat_0=0 +lon_0={(lon0 + lon1) / 2} +k=0.9996 {ellps} +units=m +no_defs')
        else:
            crs = pyproj.CRS.from_proj4(f'+proj={kind} +lat_1={lat0 + dl} +lat_2={lat1 - dl} +lat_0={(lat0 + lat1) / 2} '
                                        f'+lon_0={(lon0 + lon1) / 2} {ellps} +units=m +no_defs')
        fwd = pyproj.Transformer.from_crs(datum, crs, always_xy=True)
        E, N = fwd.transform(cps[:, 2], cps[:, 3])
        A = np.c_[cps[:, 0], cps[:, 1], np.ones(len(cps))]
        cx, *_ = np.linalg.lstsq(A, E, rcond=None); cy, *_ = np.linalg.lstsq(A, N, rcond=None)
        res = np.hypot(A @ cx - E, A @ cy - N)
        print(f'{kind}: n={len(cps)} rms={np.sqrt((res ** 2).mean()):.1f} m max={res.max():.1f} m')
        if best is None or res.max() < best[0]:
            best = (res.max(), kind, crs, cx, cy, float(np.sqrt((res ** 2).mean())), fwd, E, N, A)
    maxres, kind, crs, cx, cy, rms, fwd, E, N, A = best
    mpp = math.hypot(cx[0], cy[0])
    print(f'chosen {kind}: rms {rms:.1f} m max {maxres:.1f} m; {mpp:.2f} m/px -> {mpp / 0.0254 * 300 / 1000:,.0f} (x1000) '
          f'at 300 dpi = 1:{mpp / (0.0254 / 300):,.0f}')
    Ef, Nf = A @ cx, A @ cy
    _, u = np.unique(np.round(np.c_[Ef, Nf], 1), axis=0, return_index=True)
    corr = RBFInterpolator(np.c_[Ef, Nf][u], np.c_[E - Ef, N - Nf][u], kernel='thin_plate_spline', smoothing=0.0)
    inv = pyproj.Transformer.from_crs(crs, datum, always_xy=True)
    to6931 = pyproj.Transformer.from_crs(datum, S.CRS, always_xy=True)

    def tf(xy):
        x, y = xy[:, 0], xy[:, 1]
        e = cx[0] * x + cx[1] * y + cx[2]; n = cy[0] * x + cy[1] * y + cy[2]
        d = corr(np.c_[e, n])
        lo, la = inv.transform(e + d[:, 0], n + d[:, 1])
        return np.c_[to6931.transform(lo, la)]
    return tf, dict(projection=kind, rms_m=rms, max_res_m=float(maxres), m_per_px=mpp)


def refine_corner(rgb, x, y, sx, sy, win=70):
    """Snap an approximate inner-frame corner to the innermost dark lines around it.
    (sx, sy) point INTO the map (TL = (+1, +1)). GSC frames have three lines (thick border,
    thin line, minute bar); the neatline is the inner edge of the minute bar, i.e. the
    innermost row/column that is dark along the frame direction."""
    y0, x0 = max(int(y) - win, 0), max(int(x) - win, 0)
    sub = rgb[y0:int(y) + win, x0:int(x) + win]
    L = to_lab(sub)[..., 0]
    dark = L < 50
    cx, cy = int(x) - x0, int(y) - y0
    # horizontal line rows: darkness along the frame on the interior side of the corner
    xs = slice(cx + 8, cx + win) if sx > 0 else slice(max(cx - win, 0), cx - 8)
    ys = slice(cy + 8, cy + win) if sy > 0 else slice(max(cy - win, 0), cy - 8)
    rowfrac = dark[:, xs].mean(1)
    colfrac = dark[ys, :].mean(0)
    rows = np.nonzero(rowfrac > 0.6)[0]
    cols = np.nonzero(colfrac > 0.6)[0]
    if len(rows) == 0 or len(cols) == 0:
        return float(x), float(y), False
    r = rows.max() if sy > 0 else rows.min()      # innermost
    c = cols.max() if sx > 0 else cols.min()
    return float(x0 + c + 0.5 * sx), float(y0 + r + 0.5 * sy), True


def corner_fit(pts, lon0, lat0, lon1, lat1, datum, ties=None, proj=None):
    """Page->EPSG:6931 from the four frame corners (TL, TR, BR, BL) of a graticule-bounded
    sheet. The projection (eqdc / lcc / tmerc on the sheet's central meridian) supplies the
    curvature of the sides; its choice = lowest corner residual after an affine fit; a
    thin-plate spline pinned at the corners makes the corners exact.
    ties = [(lon, lat, x, y), ...]: interior graticule crossings read on the scan, added as
    control points (folded / photographed 1:1M sheets: 4 corners leave ~600 m mid-sheet
    error on N-52,(53)); residuals are then reported over corners + ties."""
    from scipy.interpolate import RBFInterpolator
    ll = np.array([(lon0, lat1), (lon1, lat1), (lon1, lat0), (lon0, lat0)])
    P = np.array(pts, float)
    if ties:
        ll = np.r_[ll, np.array([t[:2] for t in ties], float)]
        P = np.r_[P, np.array([t[2:] for t in ties], float)]
    ell = pyproj.CRS.from_epsg(datum).ellipsoid
    ellps = f'+a={ell.semi_major_metre} +rf={ell.inverse_flattening}'
    dl = (lat1 - lat0) / 6
    best = None
    cm_utm = -183 + 6 * (int(((lon0 + lon1) / 2 + 180) // 6) + 1)
    for kind in (('given',) if proj else ('eqdc', 'lcc', 'tmerc', 'tmerc_utm')):
        if kind == 'given':
            crs = pyproj.CRS.from_proj4(f'{proj} {ellps} +units=m +no_defs')
        elif kind == 'tmerc':
            crs = pyproj.CRS.from_proj4(f'+proj=tmerc +lat_0=0 +lon_0={(lon0 + lon1) / 2} +k=0.9996 {ellps} +units=m +no_defs')
        elif kind == 'tmerc_utm':      # A1583a: TM on the UTM zone meridian fits best (128 m vs 134 m)
            crs = pyproj.CRS.from_proj4(f'+proj=tmerc +lat_0=0 +lon_0={cm_utm} +k=0.9996 {ellps} +units=m +no_defs')
        else:
            crs = pyproj.CRS.from_proj4(f'+proj={kind} +lat_1={lat0 + dl} +lat_2={lat1 - dl} +lat_0={(lat0 + lat1) / 2} '
                                        f'+lon_0={(lon0 + lon1) / 2} {ellps} +units=m +no_defs')
        E, N = pyproj.Transformer.from_crs(datum, crs, always_xy=True).transform(ll[:, 0], ll[:, 1])
        A = np.c_[P, np.ones(len(P))]
        cx, *_ = np.linalg.lstsq(A, E, rcond=None); cy, *_ = np.linalg.lstsq(A, N, rcond=None)
        res = np.hypot(A @ cx - E, A @ cy - N)
        print(f'{kind}: corner residual rms {np.sqrt((res ** 2).mean()):.1f} m max {res.max():.1f} m')
        if best is None or res.max() < best[0]:
            best = (res.max(), kind, crs, cx, cy, float(np.sqrt((res ** 2).mean())), E, N, A)
    maxres, kind, crs, cx, cy, rms, E, N, A = best
    mpp = math.hypot(cx[0], cy[0])
    print(f'chosen {kind}: corner rms {rms:.1f} m; {mpp:.2f} m/px')
    Ef, Nf = A @ cx, A @ cy
    corr = RBFInterpolator(np.c_[Ef, Nf], np.c_[E - Ef, N - Nf], kernel='thin_plate_spline', smoothing=0.0)
    inv = pyproj.Transformer.from_crs(crs, datum, always_xy=True)
    to6931 = pyproj.Transformer.from_crs(datum, S.CRS, always_xy=True)

    def tf(xy):
        x, y = xy[:, 0], xy[:, 1]
        e = cx[0] * x + cx[1] * y + cx[2]; n = cy[0] * x + cy[1] * y + cy[2]
        d = corr(np.c_[e, n])
        lo, la = inv.transform(e + d[:, 0], n + d[:, 1])
        return np.c_[to6931.transform(lo, la)]

    fwd = pyproj.Transformer.from_crs(datum, crs, always_xy=True)
    M = np.array([[cx[0], cx[1]], [cy[0], cy[1]]])

    def tf_inv(lonlat):
        """(lon, lat) in the datum -> scan pixels: affine inverse, iterated through the spline correction"""
        Et, Nt = fwd.transform(lonlat[:, 0], lonlat[:, 1])
        xy = np.linalg.solve(M, np.vstack([Et - cx[2], Nt - cy[2]])).T
        for _ in range(6):
            e = cx[0] * xy[:, 0] + cx[1] * xy[:, 1] + cx[2]; n = cy[0] * xy[:, 0] + cy[1] * xy[:, 1] + cy[2]
            d = corr(np.c_[e, n])
            xy = np.linalg.solve(M, np.vstack([Et - d[:, 0] - cx[2], Nt - d[:, 1] - cy[2]])).T
        return xy
    tf.inv = tf_inv
    return tf, dict(projection=kind, rms_m=rms, max_res_m=float(maxres), m_per_px=mpp, corner_residuals_m=[round(float(v), 1) for v in np.hypot(A @ cx - E, A @ cy - N)])


def pattern_mask(rgb, hexcol, win, mmu):
    """pixels inside a two-colour line pattern (hexcol on white): in a win x win window the
    pattern colour covers 15-70 % and white > 20 %; a solid unit of a similar colour (> 70 %)
    and its border band with paper are removed by an opening of win/2"""
    raw = to_lab(rgb)                                   # unfiltered: a median smears the lines
    pc = to_lab(hex2rgb(hexcol)[None, None])[0, 0]
    sq = np.sqrt(((raw - pc) ** 2).sum(-1)) < 25
    wh = (raw[..., 0] > 95) & (np.hypot(raw[..., 1], raw[..., 2]) < 8)
    fs = ndi.uniform_filter(sq.astype(np.float32), win)
    fw = ndi.uniform_filter(wh.astype(np.float32), win)
    # contour lines drawn over the pattern lower both fractions: white > 8 % only, then a
    # closing bridges the contour gaps; a coastline (1-2 px line on white) stays < 18 %
    m = (fs > 0.18) & (fs < 0.7) & (fw > 0.08)
    st = np.ones((3, 3), bool)
    m = ndi.binary_closing(m, structure=st, iterations=win // 6)
    m = ndi.binary_opening(m, structure=st, iterations=max(win // 4, 1))
    return rf.sieve(m.astype(np.uint8), size=max(mmu * 4, 6000)) == 1   # 6000 px: drops cyan place names


def grid_mask(rgb, hexcol, pitch, mmu, mode='hv'):
    """(region, line pixels) of a square-grid overprint (A1693a 'organic deposits': dark red
    lines at a 24.6 px pitch over the colour of the underlying unit). The print screening
    breaks the lines, so the test is PERIODICITY, not line runs: on g = closeness to the line
    colour, the local autocorrelation at lag = pitch minus that at lag = pitch/2 (normalised by
    the local variance) is high in BOTH x and y only inside the grid. Unit edges, contours and
    the fine screen of the unit fills (4-6 px) do not have that period in both directions."""
    raw = to_lab(rgb)
    pc = to_lab(hex2rgb(hexcol)[None, None])[0, 0]
    g = np.exp(-np.sqrt(((raw - pc) ** 2).sum(-1)) / 20.0).astype(np.float32)
    p = int(round(pitch)); win = 3 * p + 1
    gc = g - ndi.uniform_filter(g, win)
    var = ndi.uniform_filter(gc * gc, win) + 1e-6
    score = []
    for ax in (1, 0):
        c1 = ndi.uniform_filter(gc * np.roll(gc, p, axis=ax), win)
        c2 = ndi.uniform_filter(gc * np.roll(gc, p // 2, axis=ax), win)
        score.append((c1 - c2) / var)
    # score[0]: period along x (vertical lines), score[1]: along y (horizontal lines).
    # OF4662 also has one-direction patterns (fen = horizontal, peat = vertical lines)
    if mode == 'hv':
        reg = (score[0] > 0.25) & (score[1] > 0.25)
    elif mode == 'h':
        reg = (score[1] > 0.25) & (score[0] < 0.1)
    else:
        reg = (score[0] > 0.25) & (score[1] < 0.1)
    st = np.ones((3, 3), bool)
    reg = ndi.binary_closing(reg, structure=st, iterations=p)
    reg = ndi.binary_opening(reg, structure=st, iterations=p // 2)
    reg = rf.sieve(reg.astype(np.uint8), size=max(mmu * 4, 6000)) == 1
    # 4 px: the 5x5 median blends a 3-4 px line into its neighbours (olive/brown pixels that
    # A1693a read as slump Ch: 3.9 M px, direct 35 %); cells of 24.6 px keep half their pixels
    near = np.sqrt(((raw - pc) ** 2).sum(-1)) < 30
    lines = ndi.binary_dilation(near, structure=st, iterations=4) & reg
    return reg, lines


def majority(lbl, ncls, size):
    best = np.zeros(lbl.shape, np.float32); arg = np.zeros(lbl.shape, np.int16)
    for c in range(1, ncls + 1):
        cnt = ndi.uniform_filter((lbl == c).astype(np.float32), size)
        m = cnt > best
        best[m], arg[m] = cnt[m], c
    arg[best == 0] = 0
    return arg


def cmd_extract(a):
    rgb = load_rgb(a.img)
    leg = pd.read_csv(a.legend, dtype=str, keep_default_na=False)
    fills = list(dict.fromkeys(leg['fill'].str.lower()))           # unique, ordered; class id = pos+1
    idx_of = {f: '|'.join(leg.loc[leg['fill'].str.lower() == f, 'index']) for f in fills}
    lon0, lat0, lon1, lat1 = map(float, a.lonlat.split(',')) if a.lonlat else nomen.frame(a.sheet)
    mb = list(map(int, a.map_box.split(','))) if a.map_box else None
    if a.corners:
        # approximate inner corners TL;TR;BR;BL (px), snapped to the neatline
        approx = [tuple(map(float, c.split(','))) for c in a.corners.split(';')]
        dirs = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
        pts, snaps = [], []
        for (x, y), (sx, sy) in zip(approx, dirs):
            # --no-snap: corners measured on grey-level profiles (frame_profiles.py); refine_corner's L<50
            # rule misses a faint inner neatline and snaps ~7 px outward onto the minute bar (A1672a TL)
            px, py, ok = (x, y, 'measured') if a.no_snap else refine_corner(rgb, x, y, sx, sy)
            if ok is True and np.hypot(px - x, py - y) > 15:
                # a snap that moves the corner far has found another line (A1647a BL moved
                # 70 px = 3 km onto a graticule line): keep the read position
                px, py, ok = x, y, 'rejected (moved > 15 px)'
            pts.append((px, py)); snaps.append(dict(approx=(x, y), snapped=(round(px, 1), round(py, 1)), ok=ok))
        print('corners:', snaps)
        ties = [tuple(float(v) for v in t.split(',')) for t in a.ties.split(';')] if a.ties else None
        tf, fit = corner_fit(pts, lon0, lat0, lon1, lat1, a.datum, ties, a.proj)
        if ties:
            fit['n_ties'] = len(ties)
        fit['corners'] = snaps
        face = Polygon(pts)
        # The 4-corner polygon has STRAIGHT edges, but a conic sheet's parallels are arcs that sag below the chord
        # between their corners: the strip between the bottom chord and the southern parallel was never classified
        # (up to ~17 km on the 15-degree-wide R-35-37 at 68N; 2026-10-06: the R-35-37 / R-39-40 / R-40-42 gaps along
        # 68N, ~2-3 km on every 6-degree 1:1M sheet). Face = the exact frame mapped back to pixels, unioned with the
        # 4-corner polygon (what lies outside the frame is clipped in map space anyway).
        fl = np.r_[np.c_[np.linspace(lon0, lon1, 200), np.full(200, lat1)], np.c_[np.full(100, lon1), np.linspace(lat1, lat0, 100)],
                   np.c_[np.linspace(lon1, lon0, 200), np.full(200, lat0)], np.c_[np.full(100, lon0), np.linspace(lat0, lat1, 100)]]
        fpx = Polygon(tf.inv(fl))
        if fpx.is_valid and fpx.area > 0.5 * face.area:
            sag = float(np.max(shapely.distance(shapely.points(tf.inv(fl)), face)))
            fit['frame_sag_px'] = round(sag, 1)
            face = shapely.union(face, fpx)
            face = max(shapely.get_parts(face), key=lambda q: q.area) if face.geom_type != 'Polygon' else face
            # stay on the image (a negative slice start would wrap around)
            face = shapely.intersection(face, shapely.box(0, 0, rgb.shape[1] - 1, rgb.shape[0] - 1))
        if a.face_px:          # classify this pixel polygon instead of the 4-corner face (map parts outside the
            # fitted frame: the O-55 block hanging below P-54,55 on the Oymyakon sheet)
            face = Polygon([tuple(map(float, q.split(','))) for q in a.face_px.split(';')])
    else:
        edges, blob, f, env = neatline(rgb, mb, mode=a.frame_mode)
        tf, fit = frame_fit(edges, lon0, lat0, lon1, lat1, datum=a.datum, proj=a.proj)
        fit['envelope'] = env
        # classify inside the neatline
        face = Polygon(np.r_[edges['top'], edges['right'][1:], edges['bottom'][::-1][1:], edges['left'][::-1][1:-1]])
    x0, y0, x1, y1 = [int(v) for v in face.bounds]
    sub = ndi.median_filter(rgb[y0:y1, x0:x1], size=(a.median, a.median, 1))
    lab = to_lab(sub)
    cl = to_lab(np.array([hex2rgb(h) for h in fills])[None])[0]
    # --restrict: units allowed only inside a pixel polygon (P-48,49 preview: the Samarovo glacial
    # units and their II-IV cover; outside the glaciated NW, brown line/orange mixtures read as till)
    allow = {}
    for spec in (a.restrict.split('|') if a.restrict else []):
        nms, poly = spec.split('@', 1)
        pg = Polygon([tuple(map(float, q.split(','))) for q in poly.split(';')])
        m = rf.rasterize([(shapely.affinity.translate(pg, -x0, -y0), 1)], out_shape=lab.shape[:2], dtype=np.uint8) == 1
        for nm in nms.split(';'):
            allow[nm] = m
    dmin = np.full(lab.shape[:2], np.inf, np.float32); cls = np.zeros(lab.shape[:2], np.int16)
    for i, c in enumerate(cl, 1):
        d = np.sqrt(((lab - c) ** 2).sum(-1))
        for nm in idx_of[fills[i - 1]].split('|'):
            if nm in allow:
                d = np.where(allow[nm], d, np.inf)
        m = d < dmin
        dmin[m], cls[m] = d[m], i
    cls[(dmin > a.dE) | (lab[..., 0] < a.min_L)] = 0      # dark = linework (A1849a units 2/6 are L ~30: --min-L 22)
    for spec in (a.class_dE.split('|') if a.class_dE else []):     # tighter match for line-mixture look-alikes
        nm, v = spec.rsplit('=', 1)
        for i, f in enumerate(fills, 1):
            if nm in idx_of[f].split('|'):
                cls[(cls == i) & (dmin > float(v))] = 0
    patt = None
    if a.pattern:
        # line-pattern fill on white (OF3634 'permanent snow and ice': cyan squiggles, pitch
        # ~12 px) has no single colour and reads as marine 5a/5b + paper: detect it as a
        # MIXTURE of the squiggle colour and white in a window, then force that class
        pfill, phex, win = a.pattern.split(':'); win = int(win)
        patt = pattern_mask(rgb[y0:y1, x0:x1], phex, win, a.mmu)
        cls[patt] = fills.index(pfill.lower()) + 1
    grids = []
    for spec in (a.grid.split(';') if a.grid else []):
        # grid overprint: blank its lines so the underlying unit fills them (majority +
        # nearest fill below); the grid region is written as layer overprint_<name>
        gname, ghex, gwin, *gm = spec.split(':')
        greg, glines = grid_mask(rgb[y0:y1, x0:x1], ghex, float(gwin), a.mmu, gm[0] if gm else 'hv')
        cls[glines] = 0
        # specs in priority order: a grid's fringe scores as one-direction lines (OF4662),
        # so later specs exclude earlier regions grown by two pitches
        for _, prev in grids:
            greg &= ~ndi.binary_dilation(prev, iterations=int(2 * float(gwin)))
        greg = rf.sieve(greg.astype(np.uint8), size=max(a.mmu * 4, 6000)) == 1
        grids.append((gname, greg))
    inside = rf.rasterize([(shapely.affinity.translate(face, -x0, -y0), 1)], out_shape=cls.shape, dtype=np.uint8) == 1
    if a.exclude:              # legend panels / insets inside the frame
        for bx in a.exclude.split(';'):
            ex0, ey0, ex1, ey1 = map(int, bx.split(','))
            inside[max(ey0 - y0, 0):max(ey1 - y0, 0), max(ex0 - x0, 0):max(ex1 - x0, 0)] = False
    if a.paper_nodata:         # white paper inside the frame = not mapped by this sheet: stays no-data
        # paper measured on A1583a: L >= 99, chroma <= 2; the palest unit (weathered-bedrock A) is L 96, chroma 5.4
        if a.paper_rgb:        # tinted paper (A1319a cream #fffceb, chroma 8.6): distance to the sampled paper colour
            pc = to_lab(hex2rgb(a.paper_rgb)[None, None])[0, 0]
            paper = ndi.binary_opening(np.sqrt(((lab - pc) ** 2).sum(-1)) < 4.0, iterations=3)
        else:
            paper = ndi.binary_opening((lab[..., 0] > 97.5) & (np.hypot(lab[..., 1], lab[..., 2]) < 3), iterations=3)
        if a.paper_close:
            # unmapped parts printed as white paper crossed by thin base-map lines (GSC Map 24-1987: hydrography and
            # contours west of the Shield; pale lines fall within dE of the pale 'undifferentiated' fill and seeded
            # false polygons): close the paper mask over lines up to ~2N px wide, so they become no-data too
            paper = ndi.binary_closing(paper, structure=np.ones((3, 3), bool), iterations=a.paper_close)
        paper = rf.sieve(paper.astype(np.uint8), size=a.mmu * 4) == 1
        if patt is not None:
            paper &= ~patt
        inside &= ~paper
    # legend rows with index PAPER: off-white tones that mean 'not mapped here' (A1395a's
    # uncoloured bedrock/ice reads L 88-95, not paper-white): no-data like the paper
    pap = [i for i, f in enumerate(fills, 1) if idx_of[f] == 'PAPER']
    if pap:
        pm = rf.sieve(np.isin(cls, pap).astype(np.uint8), size=a.mmu * 4) == 1
        inside &= ~pm
        cls[np.isin(cls, pap)] = 0
    cls[~inside] = 0
    if a.main_region:
        # keep only the MAIN mapped body (GSC Map 24-1987: base-map line fragments in the unmapped plains survive the
        # paper closing as scattered isolated specks): close the assigned-pixel mask with a disk of radius R, fill holes,
        # keep components >= 5 % of the largest; everything else is no-data (not filled from far-away units)
        yy_, xx_ = np.mgrid[-a.main_region:a.main_region + 1, -a.main_region:a.main_region + 1]
        dk = xx_ * xx_ + yy_ * yy_ <= a.main_region * a.main_region
        body = ndi.binary_fill_holes(ndi.binary_closing(cls > 0, structure=dk))
        bl, bn = ndi.label(body)
        if bn:
            sz = np.bincount(bl.ravel()); sz[0] = 0
            body = np.isin(bl, np.nonzero(sz >= 0.05 * sz.max())[0])
            print(f'main region: kept {int((sz >= 0.05 * sz.max()).sum())} of {bn} components, {body.mean():.3f} of the window', flush=True)
        inside &= body
        cls[~inside] = 0
    if a.thin_units:
        # units whose tint matches the linework (A1693a slump Ch #8b7662 = brown streams,
        # contours, boundaries: 3.4 M px of lines): their pixels must survive an opening,
        # thinner features are blanked and filled from the neighbours
        names, it = a.thin_units.rsplit(':', 1)
        # ';' separates names that contain commas ('c;c,d:2' on O-46-XXVIII: red fault lines read as colluvium)
        for nm in names.split(';' if ';' in names else ','):
            # EVERY fill of the unit (2026-10-06: map-calibrated preview legends carry several tints per unit; the
            # first version thinned only the first one, work/pv_ne used a patched copy)
            cs = [i for i, f in enumerate(fills, 1) if nm in idx_of[f].split('|')]
            if not cs:
                sys.exit(f'--thin-units: no legend fill has index {nm!r}')
            for c in cs:
                m = cls == c
                cls[m & ~ndi.binary_opening(m, structure=np.ones((3, 3), bool), iterations=int(it))] = 0
    direct = cls.copy()
    cls = majority(cls, len(fills), 5)
    miss = (cls == 0) & inside
    if miss.any():
        _, (iy, ix) = ndi.distance_transform_edt(cls == 0, return_indices=True)
        cls[miss] = cls[iy[miss], ix[miss]]
    cls = rf.sieve(cls.astype(np.int16), size=a.mmu, mask=inside)
    cls[~inside] = 0
    # polygonise in page px (offset), simplify 0.8 px, transform
    rows = []
    for g, v in rf.shapes(cls, mask=cls > 0, transform=Affine.translation(x0, y0)):
        p = shape(g).simplify(0.8)
        rows.append(dict(cid=int(v), geometry=shapely.transform(p, tf)))
    g = gpd.GeoDataFrame(rows, crs=S.CRS)
    to6931 = pyproj.Transformer.from_crs(a.datum, S.CRS, always_xy=True)
    cb = tuple(map(float, a.clip_lonlat.split(','))) if a.clip_lonlat else (lon0, lat0, lon1, lat1)
    fr = shapely.segmentize(shapely.box(*cb), 0.01)
    exact = Polygon(np.c_[to6931.transform(*np.array(fr.exterior.coords).T)])
    clip = exact
    if a.exclude_lonlat:       # unmapped graticule blocks of a partly mapped sheet (A1603a: NTS sheets left blank);
        for bx in a.exclude_lonlat.split(';'):          # parallels are arcs on the page, so cut them in lon/lat
            fb = shapely.segmentize(shapely.box(*map(float, bx.split(','))), 0.01)
            clip = clip.difference(Polygon(np.c_[to6931.transform(*np.array(fb.exterior.coords).T)]))
    g['geometry'] = shapely.intersection(shapely.make_valid(g.geometry.values), clip)
    g = S.polygons_only(g)
    g['fill'] = [fills[c - 1] for c in g['cid']]
    g['index'] = g['fill'].map(idx_of)
    lut = leg.drop_duplicates('fill').set_index(leg.drop_duplicates('fill')['fill'].str.lower())
    g['description_ru'] = g['fill'].map(lut['description_ru'])
    g['sheet'] = a.sheet
    g['k'] = g['fill'].map(lambda h: '|'.join(leg.loc[leg['fill'].str.lower() == h, 'k']))
    g['draw_order'] = g['cid']
    out = g.dissolve(by=['index', 'fill'], as_index=False, aggfunc='first')
    out = S.polygons_only(out)[['index', 'fill', 'k', 'description_ru', 'sheet', 'draw_order', 'geometry']]
    out.to_file(a.out, layer='units', driver='GPKG')
    gpd.GeoDataFrame(dict(sheet=[a.sheet]), geometry=[exact], crs=S.CRS).to_file(a.out, layer='neatline', driver='GPKG')
    # excluded area (px boxes through the fit + lon/lat blocks) as its own layer: coast_check.py skips OSM
    # shore points near it (on partly mapped sheets the mapping limit is a unit edge, not a shore)
    exs = []
    for bx in (a.exclude.split(';') if a.exclude else []):
        rb = shapely.segmentize(shapely.box(*map(float, bx.split(','))), 50.0)
        exs.append(Polygon(tf(np.array(rb.exterior.coords))))
    for bx in (a.exclude_lonlat.split(';') if a.exclude_lonlat else []):
        fb = shapely.segmentize(shapely.box(*map(float, bx.split(','))), 0.01)
        exs.append(Polygon(np.c_[to6931.transform(*np.array(fb.exterior.coords).T)]))
    if exs:
        exu = shapely.intersection(shapely.union_all(shapely.make_valid(np.array(exs, dtype=object))), exact)
        gpd.GeoDataFrame(dict(sheet=[a.sheet]), geometry=[exu], crs=S.CRS).to_file(a.out, layer='excluded', driver='GPKG')
    ov_rep = None
    for gname, greg in grids:
        reg = greg & inside
        geoms = [shapely.intersection(shapely.make_valid(shapely.transform(shape(gg).simplify(1.0), tf)), exact)
                 for gg, v in rf.shapes(reg.astype(np.uint8), mask=reg, transform=Affine.translation(x0, y0))]
        ov = S.polygons_only(gpd.GeoDataFrame(dict(overprint=[gname] * len(geoms)), geometry=geoms, crs=S.CRS))
        if len(ov):
            ov.to_file(a.out, layer=f'overprint_{gname}', driver='GPKG')
        ov_rep = (ov_rep or []) + [dict(name=gname, kind='grid', regions=len(ov), km2=round(float(ov.area.sum() / 1e6), 1),
                                        frac_of_face=round(float(reg.sum() / max(inside.sum(), 1)), 3))]
        print('grid overprint', ov_rep[-1])
    if a.overprint:
        # dot overprint (e.g. R-53 'породы повышенной льдистости', blue dots): dot-sized
        # components of the dot colour, each dot buffered by 0.75 x the pattern pitch,
        # unioned; regions with < 5 dots are dropped (stray symbols, not a pattern)
        name, hexcol, pitch = a.overprint.split(':')
        pitch = float(pitch)
        c = to_lab(hex2rgb(hexcol)[None, None])[0, 0]
        raw = to_lab(rgb[y0:y1, x0:x1])
        m = (np.abs(raw[..., 0] - c[0]) < 14) & (np.abs(raw[..., 1] - c[1]) < 16) & (np.abs(raw[..., 2] - c[2]) < 16)
        m &= inside
        lb, n = ndi.label(m)
        if n:
            s = ndi.sum(m, lb, range(1, n + 1))
            ext = np.array([max(q[0].stop - q[0].start, q[1].stop - q[1].start) for q in ndi.find_objects(lb)])
            med = np.median(s[s > 3]) if (s > 3).any() else 0
            dot = (s >= 0.4 * med) & (s <= 3 * med) & (ext < pitch * 0.5)
            cen = np.array(ndi.center_of_mass(m, lb, np.nonzero(dot)[0] + 1))[:, ::-1] + [x0, y0]
            regs = shapely.get_parts(shapely.union_all(shapely.buffer(shapely.points(cen), 0.75 * pitch)))
            pts = shapely.points(cen)
            keep = [r for r in regs if shapely.contains(r, pts).sum() >= 5]
            geoms = [shapely.intersection(shapely.make_valid(shapely.transform(r.simplify(1.0), tf)), exact) for r in keep]
            ov = S.polygons_only(gpd.GeoDataFrame(dict(overprint=[name] * len(geoms)), geometry=geoms, crs=S.CRS))
            ov.to_file(a.out, layer=f'overprint_{name}', driver='GPKG')
            ov_rep = dict(name=name, dots=int(dot.sum()), components=int(n), regions=len(ov),
                          km2=round(float(ov.area.sum() / 1e6), 1))
            print('overprint', ov_rep)
    # QA
    tot = inside.sum()
    per = {fills[c - 1]: dict(index=idx_of[fills[c - 1]], px=int((cls == c).sum()),
                              direct_frac=round(float(((direct == c) & (cls == c)).sum() / max((cls == c).sum(), 1)), 3))
           for c in range(1, len(fills) + 1) if (cls == c).any()}
    dd = np.sqrt(((cl[:, None] - cl[None]) ** 2).sum(-1))
    close = [(idx_of[fills[i]], idx_of[fills[j]], round(float(dd[i, j]), 1))
             for i in range(len(fills)) for j in range(i + 1, len(fills)) if dd[i, j] < 8]
    area = float(out.area.sum() / 1e6); fa = exact.area / 1e6
    # the exact command line (2026-10-06: re-running sheets for the curved-face fix meant searching four kinds of
    # run records; from now on every output carries its own)
    fit['argv'] = ' '.join(shlex.quote(x) for x in sys.argv)
    rep = dict(sheet=a.sheet, source='raster scan', **fit, unassigned_before_fill=round(float(1 - (direct > 0)[inside].mean()), 3),
               area_km2=area, neatline_km2=fa, cover_frac=area / fa, n_polygons=len(out), units=per,
               confusable_pairs=close, overprint=ov_rep, datum=f'EPSG:{a.datum}', dE=a.dE, mmu_px=a.mmu)
    json.dump(rep, open(a.out.replace('.gpkg', '.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps({k: v for k, v in rep.items() if k != 'units'}, ensure_ascii=False))
    print('units (index: km2-share, direct):', {v['index']: (round(v['px'] / tot, 3), v['direct_frac']) for v in per.values()})
    # QC render: classified sheet at 1/6
    pal = np.array([[255, 255, 255]] + [hex2rgb(h) for h in fills], np.uint8)
    Image.fromarray(pal[cls[::6, ::6]]).save(a.out.replace('.gpkg', '_class.png'))


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    l = sp.add_parser('legend'); l.add_argument('img'); l.add_argument('box'); l.add_argument('out')
    e = sp.add_parser('extract'); e.add_argument('img'); e.add_argument('sheet'); e.add_argument('legend'); e.add_argument('out')
    e.add_argument('--dE', type=float, default=14.0); e.add_argument('--mmu', type=int, default=120)
    e.add_argument('--map-box')
    e.add_argument('--lonlat', help='frame lon0,lat0,lon1,lat1 (default: from the Russian nomenclature)')
    e.add_argument('--datum', type=int, default=4284, help='EPSG of the geographic datum (4284 Pulkovo; 4267 NAD27)')
    e.add_argument('--frame-mode', default='colour', choices=('colour', 'dark'))
    e.add_argument('--corners', help='approximate inner frame corners TL;TR;BR;BL as x,y px (graticule sheets)')
    e.add_argument('--ties', help='interior graticule crossings lon,lat,x,y;... (extra control points with --corners)')
    e.add_argument('--paper-nodata', action='store_true')
    e.add_argument('--paper-rgb', help='paper colour #rrggbb for tinted paper (default: near-white rule)')
    e.add_argument('--main-region', type=int, default=0, help='keep only the main mapped body: closing radius px; components < 5 %% of the largest -> no-data')
    e.add_argument('--paper-close', type=int, default=0, help='with --paper-nodata: close the paper mask N iterations (thin base-map lines in unmapped areas -> no-data)')
    e.add_argument('--exclude', help='x0,y0,x1,y1;... px boxes inside the frame to ignore (legend, insets)')
    e.add_argument('--no-snap', action='store_true', help='use --corners as given (measured), no neatline snap')
    e.add_argument('--face-px', help='x,y;x,y;... pixel polygon to classify instead of the 4-corner face')
    e.add_argument('--clip-lonlat', help='lon0,lat0,lon1,lat1 output clip box (and neatline) instead of the fitted frame')
    e.add_argument('--exclude-lonlat', help='lon0,lat0,lon1,lat1;... graticule blocks (frame datum) to drop: unmapped parts')
    e.add_argument('--pattern', help='fill:#hex:win_px, e.g. #c0fdff:#79ffff:31 (line-pattern unit on white -> legend fill)')
    e.add_argument('--thin-units', help='idx[,idx]:iters, e.g. Ch:2, or idx;idx:iters when names contain commas (units that must survive an opening: linework look-alikes)')
    e.add_argument('--min-L', type=float, default=38.0, help='pixels darker than this are linework (default 38)')
    e.add_argument('--grid', help='name:#hex:pitch_px[:hv|h|v][;...], e.g. organic:#8d5a50:24.6 (grid / line-pattern overprint -> layer overprint_<name>)')
    e.add_argument('--overprint', help='name:#hex:pitch_px, e.g. ice:#0669b1:33 (dot-pattern overprint -> layer overprint_<name>)')
    e.add_argument('--restrict', help='idx;idx@x,y;x,y;...[|...]: units allowed only inside this pixel polygon')
    e.add_argument('--class-dE', help='idx=dE[|idx=dE]: per-unit colour threshold tighter than --dE')
    e.add_argument('--median', type=int, default=5, help='median filter size (px) before classification')
    e.add_argument('--proj', help="explicit PROJ string for the frame fit, ellipsoid added from --datum (e.g. '+proj=eqdc +lat_1=47 +lat_2=62 +lon_0=111')")
    a = ap.parse_args()
    (cmd_legend if a.cmd == 'legend' else cmd_extract)(a)


if __name__ == '__main__':
    main()
