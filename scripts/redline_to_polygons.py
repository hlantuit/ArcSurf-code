"""Red-overlay map scan -> unit regions (pixel space) for maps whose units are drawn and labelled in RED over a grey
topographic base (GSC Paper 81-9 maps 1-1981 / 2-1981, Hodgson 1982: red 'lithogenetic' overview units 1-14; the
black 'morphogenetic' detail is ignored). Output feeds line_georef_ingest.py like line_to_polygons.py.

  red   = r - max(g, b) > --red-t and r > 110 (lines and labels)
  sea   = flat grey screen tint (--sea-hex, tolerance --sea-tol on a 7 x 7 median), large components only
  lines = red components whose bbox is longer than --line-len px (labels are shorter glyph groups); with
          --line-close N the red ink is first closed with N-px line elements in 12 directions, so the DASHED
          contacts (approximate / assumed boundaries) join into lines, and an elongated red component lying on
          such a line (a dash, PCA axis ratio >= 3) is not taken as a label glyph
  walls = lines (closed by --close px) + the sea edge; regions = components of (face & ~sea & ~walls), grown back
          over the walls (not into the sea), regions < --min-px merged into their longest-border neighbour
  labels = red glyph components (8..90 px tall) clustered within 16 px; the region under the cluster centre gets it
Writes <out>_regions.npy, <out>_regions.json (as line_to_polygons.py), <out>_walls.npy (packed bits) and <out>_qa.png.
usage: redline_to_polygons.py <img> <out_prefix> --face "x,y;x,y;x,y;x,y" [--red-t 35] [--sea-hex #b4b4b4]
       [--sea-tol 22] [--line-len 110] [--close 3] [--min-px 3000] [--line-close 0]"""
import argparse
import json
import sys

import numpy as np
import rasterio.features as rf
import shapely
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
from line_to_polygons import merge_small  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser()
ap.add_argument('image'); ap.add_argument('out'); ap.add_argument('--face', required=True)
ap.add_argument('--red-t', type=int, default=35); ap.add_argument('--sea-hex', default='#b4b4b4')
ap.add_argument('--sea-tol', type=int, default=22); ap.add_argument('--line-len', type=int, default=110)
ap.add_argument('--close', type=int, default=3); ap.add_argument('--min-px', type=int, default=3000)
ap.add_argument('--line-close', type=int, default=0)
a = ap.parse_args()
face = shapely.Polygon([tuple(map(float, p.split(','))) for p in a.face.split(';')])
x0, y0, x1, y1 = [int(v) for v in face.bounds]
im = np.asarray(Image.open(a.image).convert('RGB').crop((x0, y0, x1, y1))).astype(np.int16)
inside = rf.rasterize([(shapely.affinity.translate(face, -x0, -y0), 1)], out_shape=im.shape[:2], dtype=np.uint8) == 1
r, g, b = im[..., 0], im[..., 1], im[..., 2]
red = (r - np.maximum(g, b) > a.red_t) & (r > 110) & inside
# sea: flat grey screen; median-smoothed so the halftone dots read as one tone
med = ndi.median_filter(im.astype(np.uint8), size=(7, 7, 1)).astype(np.int16)
sc = np.array([int(a.sea_hex[i:i + 2], 16) for i in (1, 3, 5)])
sea = (np.abs(med - sc).max(-1) < a.sea_tol) & (np.ptp(med, axis=-1) < 14)
sea = ndi.binary_opening(sea, iterations=3)
lab_s, n_s = ndi.label(sea)
if n_s:
    sz = ndi.sum(sea, lab_s, range(1, n_s + 1))
    sea = np.isin(lab_s, np.nonzero(sz >= 20000)[0] + 1)
sea &= inside                                           # islands inside the sea stay land (no hole filling)
del med, lab_s
# red components: long ones are lines, short ones glyphs
cl, n = ndi.label(red, structure=np.ones((3, 3)))
objs = ndi.find_objects(cl)
kind = np.zeros(n + 1, np.uint8)               # 1 line, 2 dash candidate (short, elongated), 3 glyph
for k, s_ in enumerate(objs, 1):
    h, w = s_[0].stop - s_[0].start, s_[1].stop - s_[1].start
    if max(h, w) >= a.line_len:
        kind[k] = 1
    elif 8 <= max(h, w) < 90:
        kind[k] = 3
        if a.line_close:
            yy, xx = np.nonzero(cl[s_] == k)
            if len(yy) > 5:
                ev = np.linalg.eigvalsh(np.cov(np.c_[yy, xx].T))
                if np.sqrt(max(ev[1], 1e-6) / max(ev[0], 1e-6)) >= 3:
                    kind[k] = 2
lines = kind[cl] == 1
n_dash = 0
if a.line_close:
    # dashed contacts (approximate / assumed boundaries): only line pieces and elongated dashes are closed, with
    # N-px line elements in 12 directions, so gaps ALONG a dash are bridged while compact label glyphs are left
    # out (closing the whole red layer fused glyphs and contacts into blobs)
    ink0 = (kind[cl] == 1) | (kind[cl] == 2)
    ink = np.zeros_like(red)
    n_ = a.line_close
    for k in range(12):
        th = np.pi * k / 12
        se = np.zeros((n_, n_), bool)
        t = np.linspace(-(n_ - 1) / 2, (n_ - 1) / 2, 2 * n_)
        se[np.clip(np.round((n_ - 1) / 2 + t * np.sin(th)).astype(int), 0, n_ - 1),
           np.clip(np.round((n_ - 1) / 2 + t * np.cos(th)).astype(int), 0, n_ - 1)] = True
        ink |= ndi.binary_closing(ink0, structure=se)
    # keep only bridging pixels near a dash: a gap of <= N px between dashes lies within N/2 of one of them, while
    # closing a label glued to a contact by its leader fills the space between glyph strokes far from any dash
    near = ndi.binary_dilation(kind[cl] == 2, iterations=(n_ + 1) // 2)
    ink = ink0 | (ink & near)
    ink &= inside
    clc, nc = ndi.label(ink, structure=np.ones((3, 3)))
    long_ = np.zeros(nc + 1, bool)
    for k, s_ in enumerate(ndi.find_objects(clc), 1):
        if max(s_[0].stop - s_[0].start, s_[1].stop - s_[1].start) >= a.line_len:
            long_[k] = True
    lines = long_[clc]
    del clc, ink, ink0
glyphs = []
for k, s_ in enumerate(objs, 1):
    if kind[k] == 3 or (kind[k] == 2 and not lines[s_][cl[s_] == k].mean() > 0.5):
        glyphs.append([s_[1].start, s_[0].start, s_[1].stop, s_[0].stop])
    elif kind[k] == 2:
        n_dash += 1
print('glyph components', len(glyphs), '| dashes taken as contact', n_dash, flush=True)
walls = ndi.binary_closing(lines, structure=np.ones((3, 3)), iterations=a.close)
walls = ndi.binary_dilation(walls, iterations=1)
coast = sea ^ ndi.binary_erosion(sea, iterations=1)
walls |= ndi.binary_dilation(coast, iterations=1)
np.save(a.out + '_walls.npy', np.packbits(walls))          # for redlabel_assign.py (geodesic split of merged units)
land = inside & ~sea
lab, nreg = ndi.label(land & ~walls)
_, (iy, ix) = ndi.distance_transform_edt(lab == 0, return_indices=True)
lab = lab[iy, ix].astype(np.int32)
lab[~land] = 0
lab = merge_small(lab, a.min_px)          # 1-based again; sea/outside became a region too: reset below
lab[~land] = 0
u, inv = np.unique(lab, return_inverse=True)
lab = inv.reshape(lab.shape).astype(np.int32)  # 0 stays 0 (smallest)
nreg = int(lab.max())
# label clusters
gl = np.array(glyphs) if glyphs else np.zeros((0, 4), int)
par = list(range(len(gl)))


def find(i):
    while par[i] != i:
        par[i] = par[par[i]]; i = par[i]
    return i


if len(gl):
    gap = 16
    boxes = shapely.box(gl[:, 0] - gap, gl[:, 1] - gap, gl[:, 2] + gap, gl[:, 3] + gap)
    tree = shapely.STRtree(boxes)
    ii, jj = tree.query(boxes, predicate='intersects')
    for i_, j_ in zip(ii, jj):
        if i_ != j_:
            par[find(i_)] = find(j_)
clusters = {}
for k in range(len(gl)):
    clusters.setdefault(find(k), []).append(k)
cand = {}
for ks in clusters.values():
    bb = gl[ks]
    if len(ks) > 8:
        continue
    bx = [int(bb[:, 0].min()), int(bb[:, 1].min()), int(bb[:, 2].max()), int(bb[:, 3].max())]
    if bx[2] - bx[0] > 300 or bx[3] - bx[1] > 220:
        continue
    cy, cx = (bx[1] + bx[3]) // 2, (bx[0] + bx[2]) // 2
    r_ = int(lab[cy, cx])
    if r_ == 0:
        continue
    cand.setdefault(r_, []).append([bx[0] + x0, bx[1] + y0, bx[2] + x0, bx[3] + y0])
areas = np.bincount(lab.ravel(), minlength=nreg + 1)
regs = []
for rid in range(1, nreg + 1):
    lb = cand.get(rid, [])
    big = max(lb, key=lambda q: (q[2] - q[0]) * (q[3] - q[1])) if lb else None
    regs.append(dict(id=rid, px=int(areas[rid]), label_box=big, all_label_boxes=lb, n_glyphs=len(lb), water_frac=0.0, hatch_frac=0.0))
np.save(a.out + '_regions.npy', lab)
json.dump(dict(window=[x0, y0, x1, y1], n_regions=nreg, hatch_frac=0.0, regions=regs), open(a.out + '_regions.json', 'w'))
rng = np.random.default_rng(1)
pal = rng.integers(60, 255, (nreg + 1, 3)).astype(np.uint8)
gray = im.mean(-1).astype(np.uint8)
ov = (0.5 * pal[lab] + 0.5 * np.repeat(gray[..., None], 3, -1)).astype(np.uint8)
ov[sea] = (200, 220, 240)
ov[lines] = (200, 0, 0)
ov[~inside] = 255
Image.fromarray(ov).save(a.out + '_qa.png')
print('regions', nreg, '| with label clusters', sum(1 for x in regs if x['label_box']), '| red px', int(red.sum()),
      '| line px', int(lines.sum()), '| sea frac', round(float(sea[inside].mean()), 3))
