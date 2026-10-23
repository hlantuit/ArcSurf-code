"""Black-and-white LINE / LABEL map scan -> unit polygons (pixel space), for maps whose units
are outlined and labelled rather than colour-filled (GSC 1970s-80s Open Files: Herschel OF191,
Tuktoyaktuk 1:25k, Mackenzie Delta 1:250k ...). Step 1 of the line-map pipeline:

  1. ink   = gray < ink_t (lines, labels, symbols); sea/grey tones are NOT ink
  2. hatch = periodic line overprint (jpg_to_polygons.grid_mask on the ink, pitch given):
             removed from the ink (recorded as overprint layer), so hatched units are not
             shattered into strips
  3. walls = ink dilated by `close` px (closes dashed boundaries)
  4. regions = connected components of NOT walls, then grown back over the walls
             (watershed by distance), so polygons tile the face
  5. tiny regions (< min_px: text counters, dots, symbol holes) merged into the neighbour
             sharing the longest border
  6. label candidates per region: ink components of text size inside the region, grouped;
             the bbox of the largest group is the label crop (read by a person or a multimodal language model via a
             contact sheet, or tesseract when typeset)
Writes <out>_regions.npy (int32 label raster, window), <out>_regions.json (region stats +
label crop boxes: the largest, and all_label_boxes = every label cluster in the region), <out>_walls.npy
(packed bits) and a QA overlay PNG.
Bold-line maps drawn over a black topographic base (GSC OF 21, 1970: contacts and unit labels bold, contours,
grid, lakes and names thin): --thick R keeps only strokes that survive an opening with a disk of radius R
(walls AND label glyphs), --gap-close G bridges dashed contacts (closing, disk radius G), --single-min-h H
accepts one-glyph labels (A, H) at least H px tall.
usage: line_to_polygons.py <image> <out_prefix> [--window x0,y0,x1,y1] [--ink-t 150]
       [--close 3] [--min-px 4000] [--hatch pitch_px] [--hatch-hex #303030]
       [--thick 2] [--gap-close 8] [--single-min-h 30]"""
import argparse
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

Image.MAX_IMAGE_PIXELS = None


def disk(r):
    y, x = np.mgrid[-r:r + 1, -r:r + 1]
    return (x * x + y * y) <= r * r


def merge_small(lab, min_px):
    """Merge regions smaller than min_px into the neighbour with the longest shared border."""
    for _ in range(6):
        areas = np.bincount(lab.ravel())
        small = np.nonzero((areas > 0) & (areas < min_px))[0]
        small = small[small > 0]
        if not len(small):
            break
        # border pairs from horizontal and vertical neighbours
        a = np.concatenate([lab[:, :-1].ravel(), lab[:-1, :].ravel()])
        b = np.concatenate([lab[:, 1:].ravel(), lab[1:, :].ravel()])
        m = a != b
        a, b = a[m], b[m]
        pairs = np.stack([np.minimum(a, b), np.maximum(a, b)], 1)
        u, c = np.unique(pairs, axis=0, return_counts=True)
        best = {}
        for (x, y), n in zip(u, c):
            for s, o in ((x, y), (y, x)):
                if areas[s] < min_px and o > 0 and (s not in best or n > best[s][1] or
                                                     (n == best[s][1] and areas[o] > areas[best[s][0]])):
                    best[s] = (o, n)
        remap = np.arange(len(areas))
        for s, (o, _) in best.items():
            remap[s] = o
        for _ in range(10):                     # resolve chains s -> o -> o2
            remap = remap[remap]
        lab = remap[lab]
    shape = lab.shape
    _, inv = np.unique(lab, return_inverse=True)
    return (inv.reshape(shape) + 1).astype(np.int32)          # 1-based: 0 means 'no region'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image'); ap.add_argument('out')
    ap.add_argument('--window'); ap.add_argument('--ink-t', type=int, default=150)
    ap.add_argument('--close', type=int, default=3); ap.add_argument('--min-px', type=int, default=4000)
    ap.add_argument('--water-hex'); ap.add_argument('--water-tol', type=int, default=60)
    ap.add_argument('--osm-land', help='coast_walls.py output (.npy): OSM land mask for the window (sea = water, coast = wall)')
    ap.add_argument('--water-smooth', type=int, default=0, help='halftone water: match the tone on the N-px local mean (tol in grey levels)')
    ap.add_argument('--water-sd', type=float, default=25.0, help='--water-smooth: minimum local sd of the screen')
    ap.add_argument('--hatch', type=float); ap.add_argument('--hatch-hex', default='#303030')
    ap.add_argument('--thick', type=int, default=0); ap.add_argument('--gap-close', type=int, default=0)
    ap.add_argument('--single-min-h', type=int, default=0)
    ap.add_argument('--line-close', type=int, default=0, help='length (px) of 12-direction line closings for dashed contacts')
    ap.add_argument('--dash-only', action='store_true', help='with --line-close: only line pieces and elongated dashes are walls (dots, glyphs, symbols are not)')
    ap.add_argument('--line-len', type=int, default=150, help='--dash-only: components at least this long are line pieces')
    ap.add_argument('--regrow', type=int, default=0, help='after --thick: regrow the bold strokes N px inside the raw ink (rejoins broken hand-drafted lines)')
    ap.add_argument('--dash-wmax', type=float, default=0.0, help='--dash-only: a dash has at most this many px per unit length (0 = no limit)')
    ap.add_argument('--ring-min', type=int, default=0, help='--dash-only: compact components enclosing a hole of at least this many px are walls (closed unit outlines)')
    ap.add_argument('--drop-grid', type=float, default=0.0, help='remove straight grid lines whose ink covers > this share of the window (e.g. 0.35)')
    a = ap.parse_args()
    im_rgb = Image.open(a.image).convert('RGB')
    im = im_rgb.convert('L')
    x0, y0, x1, y1 = map(int, a.window.split(',')) if a.window else (0, 0, *im.size)
    g = np.asarray(im.crop((x0, y0, x1, y1)))
    ink = g < a.ink_t
    water = None
    if a.osm_land:
        # land mask from OSM through the sheet's corner fit (coast_walls.py): the sea is water, the coast a wall
        meta = json.load(open(a.osm_land.replace('.npy', '.json')))
        assert meta['window'] == [x0, y0, x1, y1], f"osm-land window {meta['window']} != {[x0, y0, x1, y1]}"
        h_, w_ = meta['shape']
        water = ~np.unpackbits(np.load(a.osm_land))[:h_ * w_].reshape(h_, w_).astype(bool)
        ink &= ~ndi.binary_erosion(water, iterations=8)        # sea names, screen dots and ticks in the sea
    elif a.water_hex:
        rgbw = np.asarray(im_rgb.crop((x0, y0, x1, y1))).astype(np.int16)
        wc = np.array([int(a.water_hex[i:i + 2], 16) for i in (1, 3, 5)])
        if a.water_smooth:
            # grey HALFTONE water (OF 48, 1971: sea and lakes are a dot screen, mean ~145, local sd ~50): a pixel is a dot
            # or paper, never the tone, so the tone is matched on the local mean, and the screen is told from flat grey
            # by its local sd; tolerance in grey levels
            gf = g.astype(np.float32)
            gs = ndi.uniform_filter(gf, a.water_smooth)
            sd = np.sqrt(np.clip(ndi.uniform_filter(gf * gf, a.water_smooth) - gs * gs, 0, None))
            water = (np.abs(gs - float(wc.mean())) < a.water_tol) & (sd > a.water_sd)
            del gf, gs, sd
        else:
            water = np.abs(rgbw - wc).sum(-1) < a.water_tol
        # halftone screen: close the dots, then drop specks and fill holes (< 2000 px)
        water = ndi.binary_closing(water, iterations=4)
        water = ndi.binary_opening(water, iterations=3)
        wl, wn = ndi.label(water)
        if wn:
            ws = ndi.sum(water, wl, range(1, wn + 1))
            water = np.isin(wl, np.nonzero(ws >= 2000)[0] + 1)
        hl, hn = ndi.label(~water)
        if hn:
            hs = ndi.sum(~water, hl, range(1, hn + 1))
            water |= np.isin(hl, np.nonzero(hs < 2000)[0] + 1)
        ink &= ~ndi.binary_erosion(water, iterations=2)       # labels/lines inside water ignored
    hatch = np.zeros_like(ink)
    if a.hatch:
        # periodic hatch (Tuk 1:25k: diagonal cross-hatch, period 26 px along both axes)
        # = closed patches of their own unit: clear their ink, use their EDGE as a wall
        import jpg_to_polygons as J
        rgb = np.repeat(np.where(ink, 40, 245).astype(np.uint8)[..., None], 3, -1)
        hatch, _ = J.grid_mask(rgb, '#282828', a.hatch, 200)
        ink = ink & ~ndi.binary_erosion(hatch, iterations=3)
    bold = ndi.binary_opening(ink, structure=disk(a.thick)) if a.thick else ink
    if a.regrow:
        # hand-drafted lines (OF 1275, 1986) narrow below the opening's width every few px, so the opening breaks solid
        # contacts and closed outlines into pieces; regrowing the surviving strokes inside the ORIGINAL ink rejoins
        # them, while thin contours touching a contact gain only `regrow` px
        for _ in range(a.regrow):
            bold = ndi.binary_dilation(bold, structure=np.ones((3, 3), bool)) & ink
    if a.drop_grid:
        # map grid (UTM km grid, graticule) drawn as long straight lines: angle from the projection profile of
        # the full ink (the angle that makes column / row sums peakiest), lines = profile peaks longer than
        # drop_grid x the window size; their pixels (+-3 px) are removed from the bold ink, otherwise the line
        # closing below turns the grid's dotted remnants into walls (OF 21 096F: rectangles)
        yy, xx = np.nonzero(ink)
        gmask = np.zeros_like(ink)
        for axis in (0, 1):                  # 0: near-vertical lines, 1: near-horizontal lines
            best = None
            for ang in np.arange(-4.0, 4.01, 0.1):
                t = np.deg2rad(ang)
                u = (xx * np.cos(t) + yy * np.sin(t)) if axis == 0 else (yy * np.cos(t) - xx * np.sin(t))
                h = np.bincount(np.round(u - u.min()).astype(int))
                sc = float((h.astype(np.float64) ** 2).sum())
                if best is None or sc > best[0]:
                    best = (sc, ang, h, u.min())
            _, ang, h, umin = best
            span = ink.shape[0] if axis == 0 else ink.shape[1]
            hs = np.convolve(h, np.ones(3), 'same')
            peaks = np.nonzero((hs > a.drop_grid * span) & (hs >= np.roll(hs, 1)) & (hs >= np.roll(hs, -1)))[0]
            t = np.deg2rad(ang)
            Y, X = np.mgrid[0:ink.shape[0], 0:ink.shape[1]]
            U = (X * np.cos(t) + Y * np.sin(t)) if axis == 0 else (Y * np.cos(t) - X * np.sin(t))
            U = U - umin
            for pk in peaks:
                gmask |= np.abs(U - pk) <= 3
            print(f'grid {"vertical" if axis == 0 else "horizontal"}: angle {ang:+.1f} deg, {len(peaks)} lines', flush=True)
            del Y, X, U
        bold &= ~gmask
    wall_ink = ndi.binary_closing(bold, structure=disk(a.gap_close)) if a.gap_close else bold
    if a.line_close and a.dash_only:
        # OF 189 (1:1M, 1973): closing ALL bold ink chained the organic stipple dots, fluting symbols and label glyphs
        # into walls and shattered the sheet (2,440 regions). As in redline_to_polygons.py: components are lines
        # (>= line_len px), dashes (shorter, PCA axis ratio >= 3) or compact (dots, glyphs, symbols); only lines and
        # dashes are walls, closed along 12 directions, and bridging pixels are kept only near a dash
        cl, ncl = ndi.label(wall_ink, structure=np.ones((3, 3), bool))
        kind = np.zeros(ncl + 1, np.uint8)               # 0 compact (not a wall), 1 line, 2 dash
        for k, s_ in enumerate(ndi.find_objects(cl), 1):
            h, w = s_[0].stop - s_[0].start, s_[1].stop - s_[1].start
            if max(h, w) >= a.line_len:
                kind[k] = 1
            elif max(h, w) >= 8:
                ck = cl[s_] == k
                yy, xx = np.nonzero(ck)
                if len(yy) > 5:
                    ev = np.linalg.eigvalsh(np.cov(np.c_[yy, xx].T))
                    if np.sqrt(max(ev[1], 1e-6) / max(ev[0], 1e-6)) >= 3 and                             (not a.dash_wmax or len(yy) / max(h, w) <= a.dash_wmax):     # a word is elongated but thick
                        kind[k] = 2
                if kind[k] == 0 and a.ring_min and h * w >= a.ring_min:
                    # small closed outline (OF 1275: '1a' till patches, 60-150 px rings): compact like a glyph,
                    # but it encloses far more than a letter counter ('a', 'R', '4': < ~400 px)
                    if int(ndi.binary_fill_holes(ck).sum()) - len(yy) >= a.ring_min:
                        kind[k] = 1
        ink0 = kind[cl] > 0
        lc = np.zeros_like(ink0)
        n = a.line_close
        for k in range(12):
            th = np.pi * k / 12
            se = np.zeros((n, n), bool)
            t = np.linspace(-(n - 1) / 2, (n - 1) / 2, 2 * n)
            se[np.clip(np.round((n - 1) / 2 + t * np.sin(th)).astype(int), 0, n - 1),
               np.clip(np.round((n - 1) / 2 + t * np.cos(th)).astype(int), 0, n - 1)] = True
            lc |= ndi.binary_closing(ink0, structure=se)
        near = ndi.binary_dilation(kind[cl] == 2, iterations=(n + 1) // 2)
        wall_ink = ink0 | (lc & near)
        print(f'dash-only walls: {int((kind == 1).sum())} line pieces, {int((kind == 2).sum())} dashes, '
              f'{int((kind == 0).sum()) - 1} compact components left out', flush=True)
        del cl, kind, ink0, lc, near
    elif a.line_close:
        # dashed contacts (OF 21: bold dashes, 25-40 px gaps): closings with line elements in 12 directions
        # bridge gaps ALONG a dash without fusing neighbouring outlines the way a large disk does
        lc = np.zeros_like(wall_ink)
        for k in range(12):
            th = np.pi * k / 12
            n = a.line_close
            se = np.zeros((n, n), bool)
            t = np.linspace(-(n - 1) / 2, (n - 1) / 2, 2 * n)
            se[np.clip(np.round((n - 1) / 2 + t * np.sin(th)).astype(int), 0, n - 1),
               np.clip(np.round((n - 1) / 2 + t * np.cos(th)).astype(int), 0, n - 1)] = True
            lc |= ndi.binary_closing(wall_ink, structure=se)
        wall_ink = lc
    walls = ndi.binary_dilation(wall_ink, iterations=a.close)
    if water is not None:
        walls |= ndi.binary_dilation(water ^ ndi.binary_erosion(water, iterations=1), iterations=a.close)
    if a.hatch:
        walls |= ndi.binary_dilation(hatch ^ ndi.binary_erosion(hatch, iterations=1), iterations=a.close)
    np.save(a.out + '_walls.npy', np.packbits(walls))      # for redlabel_assign.py (compartment split)
    lab, n = ndi.label(~walls)
    # grow regions back over the walls
    _, (iy, ix) = ndi.distance_transform_edt(lab == 0, return_indices=True)
    lab = lab[iy, ix].astype(np.int32)                 # wall pixels take the nearest region
    lab = merge_small(lab, a.min_px)
    nreg = int(lab.max())
    # label candidates: glyph-sized ink components (not in hatch / water), CLUSTERED into
    # labels (glyphs whose boxes lie within `gap` px of each other, incl. sub/superscripts),
    # each label assigned to the region under its centre; a region keeps its largest label
    tl, tn = ndi.label(bold if a.thick else (g < a.ink_t), structure=np.ones((3, 3)))
    gl = []
    for s_ in ndi.find_objects(tl):
        h, w = s_[0].stop - s_[0].start, s_[1].stop - s_[1].start
        if not (10 <= h <= 90 and 3 <= w <= 110) or w * h > 6000:
            continue
        cy, cx = (s_[0].start + s_[0].stop) // 2, (s_[1].start + s_[1].stop) // 2
        if hatch[cy, cx] or (water is not None and water[cy, cx]):
            continue
        gl.append([s_[1].start, s_[0].start, s_[1].stop, s_[0].stop])
    gl = np.array(gl) if gl else np.zeros((0, 4), int)
    gap = 14
    par = list(range(len(gl)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    if len(gl):
        import shapely
        boxes = shapely.box(gl[:, 0] - gap, gl[:, 1] - gap, gl[:, 2] + gap, gl[:, 3] + gap)
        tree = shapely.STRtree(boxes)
        ii, jj = tree.query(boxes, predicate='intersects')
        for i_, j_ in zip(ii, jj):
            if i_ != j_:
                par[find(i_)] = find(j_)
    clusters = {}
    for k in range(len(gl)):
        clusters.setdefault(find(k), []).append(k)
    cand, allc = {}, {}
    for ks in clusters.values():
        b = gl[ks]
        if len(ks) > 8 or (len(ks) < 2 and not (a.single_min_h and b[0, 3] - b[0, 1] >= a.single_min_h)):
            continue                              # labels are 2-8 glyphs (one if --single-min-h); names longer
        bx = [int(b[:, 0].min()), int(b[:, 1].min()), int(b[:, 2].max()), int(b[:, 3].max())]
        if bx[2] - bx[0] > 260 or bx[3] - bx[1] > 120:
            continue
        r = int(lab[(bx[1] + bx[3]) // 2, (bx[0] + bx[2]) // 2])
        area_ = (bx[2] - bx[0]) * (bx[3] - bx[1])
        allc.setdefault(r, []).append(([bx[0] + x0, bx[1] + y0, bx[2] + x0, bx[3] + y0], area_))
        if r not in cand or area_ > cand[r][1]:
            cand[r] = ([bx[0] + x0, bx[1] + y0, bx[2] + x0, bx[3] + y0], area_, len(ks))
    regs = []
    areas = np.bincount(lab.ravel())
    for r in range(1, nreg + 1):
        box, _, ng = cand.get(r, (None, 0, 0))
        m = lab == r
        wf = float(water[m].mean()) if water is not None else 0.0
        hf = float(hatch[m].mean()) if a.hatch else 0.0
        regs.append(dict(id=r, px=int(areas[r]), label_box=box, n_glyphs=ng, water_frac=round(wf, 3), hatch_frac=round(hf, 3),
                         all_label_boxes=[c[0] for c in sorted(allc.get(r, []), key=lambda c: -c[1])]))
    np.save(a.out + '_regions.npy', lab)
    json.dump(dict(window=[x0, y0, x1, y1], n_regions=nreg, hatch_frac=float(hatch.mean()), regions=regs),
              open(a.out + '_regions.json', 'w'))
    # QA overlay: random colour per region over the scan
    rng = np.random.default_rng(1)
    pal = rng.integers(60, 255, (nreg + 1, 3)).astype(np.uint8)
    ov = (0.55 * pal[lab] + 0.45 * np.repeat(g[..., None], 3, -1)).astype(np.uint8)
    ov[ink] = 0
    Image.fromarray(ov).save(a.out + '_qa.png')
    print('regions', nreg, '| with label candidates', sum(1 for x in regs if x['label_box']),
          '| hatch frac', round(float(hatch.mean()), 3))


if __name__ == '__main__':
    main()
