"""Region labels from a per-cluster transcription of a redline_to_polygons.py run (redlabel_sheet.py tiles).
transcription CSV: region,k,label  (label '-' or empty = the cluster is not a unit label: line fragment, symbol).
A region whose labelled clusters all agree takes that label. A region holding DIFFERENT labels is a set of units
merged through an open or broken contact (units open at a clipped mapping limit, gaps in dashed lines). It is
split only where the linework itself makes COMPARTMENTS: the region's non-wall pixels (<prefix>_walls.npy) eroded
by GAP px (closing wall gaps up to 2 x GAP), 8-connected. Each compartment takes one label: the largest sum of
vote() over its clusters there (lettering height, doubled for an areal unit against a small or linear one; map
labels are sized to their polygons and repeated on large ones); a label losing in a shared compartment is dropped
and its small unit lost. Walls, margins and unlabelled compartments take the nearest
labelled compartment. (Flooding from every label, geodesic or not, drew straight Voronoi-like edges through open
ground and gave small coastal or valley units tens of km2 of the plateau around them.) Each part gets its own
region id. Writes <prefix>_regions.npy/.json in place (originals kept as *_orig.*) and the id,label CSV read by
line_georef_ingest.py.
usage: redlabel_assign.py <prefix> <transcription.csv> <out_labels.csv> <image> [red | black:T] [snap_max_px]"""
import json
import os
import re
import shutil
import sys

import numpy as np
import pandas as pd
from PIL import Image
from scipy import ndimage as ndi

pre, tr_csv, out_csv, image = sys.argv[1:5]
INK = sys.argv[5] if len(sys.argv) > 5 else 'red'          # 'red' or 'black:T' (gray < T)
# a label whose centre is farther than SNAP_MAX px from every compartment core sat in a loop too small to survive
# the erosion (a sub-minimum organic patch merged into its neighbour): it must not vote for the compartment it is
# snapped to. 0 = no limit (Maps 1/2-1981 were assigned without it)
SNAP_MAX = float(sys.argv[6]) if len(sys.argv) > 6 else 0.0
Image.MAX_IMAGE_PIXELS = None
IMG = Image.open(image).convert('RGB')


def char_height(b):
    """tallest character-like red glyph in a label box (8-100 px, PCA axis ratio < 3, so leader and contact
    fragments are excluded): the lettering size"""
    c = np.asarray(IMG.crop(tuple(b))).astype(np.int16)
    if INK == 'red':
        red = (c[..., 0] - np.maximum(c[..., 1], c[..., 2]) > 35) & (c[..., 0] > 110)
    else:
        red = c.mean(-1) < int(INK.split(':')[1])
    cl, n = ndi.label(red, structure=np.ones((3, 3)))
    hs = []
    for k, s_ in enumerate(ndi.find_objects(cl), 1):
        h, w = s_[0].stop - s_[0].start, s_[1].stop - s_[1].start
        if not (8 <= h <= 100 and w <= 100):
            continue
        yy, xx = np.nonzero(cl[s_] == k)
        if len(yy) > 5:
            ev = np.linalg.eigvalsh(np.cov(np.c_[yy, xx].T))
            if np.sqrt(max(ev[1], 1e-6) / max(ev[0], 1e-6)) >= 3:
                continue
        hs.append(h)
    return max(hs) if hs else 0


AREAL = re.compile(r'^(2|3|5|6|8|9|10)(\D|$)')   # Hodgson 1982: rock/residual, marine-reworked rock, diamicton, marine


# optional patch weighting, env RLA_PATCH='<regex>:<weight>': labels of units mapped as PATCHES inside a matrix (the
# organic units of the 1970s Mackenzie terrain maps: each peat patch carries its own label, the till matrix only a few)
# vote with this weight, so in a shared compartment the matrix wins over the sum of its patches' labels
_P = os.environ.get('RLA_PATCH', '')
PATCH = (re.compile(_P.rsplit(':', 1)[0]), float(_P.rsplit(':', 1)[1])) if _P else None


# optional class-level vote, env RLA_GROUP=1: labels are grouped by their first unit's genetic letter (terrain maps:
# 's$Ap' and '$Ap' are both A) or unit number (Hodgson: '2p', '2q' are 2) and a compartment goes to the group with
# the largest summed vote, then to that group's best label
GROUP = os.environ.get('RLA_GROUP', '') == '1'


def group_of(label):
    m_ = re.match(r'^[a-z$]*(GL|[A-Z]|\d+)', label)
    return m_.group(1) if m_ else label


def vote(label, box):
    """lettering height (labels are sized to their polygons), doubled for an areal unit against a small or linear
    one (dyke 4, diapir 1, ridges 7b, plateau gravel 7a, colluvium 11, deltaic 12, fluvial 13-14); summed over a
    label's clusters in the compartment, since a large unit carries its label repeatedly"""
    w = PATCH[1] if PATCH and PATCH[0].match(label) else 1.0
    return w * (2 if AREAL.match(label) else 1) * char_height(box)


for ext in ('_regions.npy', '_regions.json'):
    if not os.path.exists(pre + ext.replace('.', '_orig.')):
        shutil.copy(pre + ext, pre + ext.replace('.', '_orig.'))
lab = np.load(pre + '_regions_orig.npy')
R = json.load(open(pre + '_regions_orig.json'))
walls = np.unpackbits(np.load(pre + '_walls.npy'))[:lab.size].reshape(lab.shape).astype(bool)
wx0, wy0 = R['window'][:2]
regs = {r['id']: r for r in R['regions']}
T = pd.read_csv(tr_csv, dtype={'region': int, 'k': int, 'label': str}, keep_default_na=False)
T['label'] = T['label'].str.strip()
T = T[(T['label'] != '') & (T['label'] != '-')]
next_id = int(lab.max()) + 1
labels, split_log = {}, []
n_minor = 0
GAP = 10            # px: wall gaps up to 2 x GAP are closed when finding compartments
for rid, grp in T.groupby('region'):
    names = grp['label'].unique()
    if len(names) == 1:
        labels[rid] = names[0]
        continue
    if os.environ.get('RLA_VOTED', '') == 'drop':
        # different labels in one region: leave it unlabelled (dropped downstream). For black line maps whose contacts
        # do not close (OF 294 Mahony Lake: voted regions agreed 20 % with the hand digitisation in OF 7289,
        # unanimous ones 68 %); the red-overlay maps keep their votes (Map 1-1981 vs CGM: 82 % voted, 80 % unanimous)
        n_minor += len(names)
        continue
    s_ = ndi.find_objects((lab == rid).astype(np.int8))[0]
    m = lab[s_] == rid
    passable = m & ~walls[s_]
    # compartments: the region's non-wall pixels eroded by GAP (wall gaps up to 2 x GAP closed), 8-connected
    core = ndi.distance_transform_edt(passable) > GAP
    comp, ncomp = ndi.label(core, structure=np.ones((3, 3)))
    dcore, (py, px_) = ndi.distance_transform_edt(~core, return_indices=True)
    ids, votes, cl_ = {}, {}, []
    for _, c in grp.iterrows():
        b = regs[rid]['all_label_boxes'][c['k']]
        cy = max(0, min(m.shape[0] - 1, (b[1] + b[3]) // 2 - wy0 - s_[0].start))
        cx = max(0, min(m.shape[1] - 1, (b[0] + b[2]) // 2 - wx0 - s_[1].start))
        if c['label'] not in ids:
            ids[c['label']] = len(ids) + 1
        k_ = int(comp[py[cy, cx], px_[cy, cx]]) if ncomp else 0
        cl_.append((k_, ids[c['label']], vote(c['label'], b), float(dcore[cy, cx])))
    keep = [x for x in cl_ if not SNAP_MAX or x[3] <= SNAP_MAX] or cl_     # all skipped -> use them all
    for k_, j, v_, _ in keep:
        votes.setdefault(k_, {})
        votes[k_][j] = votes[k_].get(j, 0) + v_
    part = np.zeros(m.shape, np.int32)
    inv = {j: n for n, j in ids.items()}
    for k_, v in votes.items():
        if GROUP:                             # class first (summed over spellings), then the best label of that class
            gs = {}
            for j, a_ in v.items():
                gs[group_of(inv[j])] = gs.get(group_of(inv[j]), 0) + a_
            g_ = max(gs, key=gs.get)
            win = max((j for j in v if group_of(inv[j]) == g_), key=v.get)
        else:
            win = max(v, key=v.get)
        n_minor += len(v) - 1
        if k_:
            part[comp == k_] = win
    if not part.any():                        # no compartment (thin region): the largest lettering takes it all
        tot = {}
        for v in votes.values():
            for j, a_ in v.items():
                tot[j] = tot.get(j, 0) + a_
        part[m] = max(tot, key=tot.get)
    _, (iy, ix) = ndi.distance_transform_edt(part == 0, return_indices=True)
    part = part[iy, ix]                       # walls, eroded margins, unseeded compartments: nearest labelled one
    ids = {n: j for n, j in ids.items() if (part[m] == j).any()}
    sub = lab[s_]
    areas = {}
    first = True
    for name, j in ids.items():
        pm = m & (part == j)
        nid = rid if first else next_id
        if not first:
            next_id += 1
            R['regions'].append(dict(regs[rid], id=nid, label_box=None, all_label_boxes=[], n_glyphs=0, split_from=rid))
        first = False
        sub[pm] = nid
        labels[nid] = name
        areas[name] = int(pm.sum())
    lab[s_] = sub
    split_log.append((rid, areas))
for r in R['regions']:
    r['px'] = int((lab == r['id']).sum()) if r.get('split_from') or r['id'] in dict(split_log) else r['px']
R['n_regions'] = int(lab.max())
np.save(pre + '_regions.npy', lab)
json.dump(R, open(pre + '_regions.json', 'w'))
pd.DataFrame(sorted(labels.items()), columns=['id', 'label']).to_csv(out_csv, index=False)
print(len(labels), 'labelled regions;', n_minor, 'labels dropped (smaller lettering in a shared compartment);', len(split_log), 'regions split:')
for rid, a in split_log:
    print(' ', rid, a)
