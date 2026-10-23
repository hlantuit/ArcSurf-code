#!/usr/bin/env python
"""Seam pass over all VSEGEI sheets extracted from vector PDFs (work/pdfvec/<sheet>.gpkg).

1. band_snap every sheet onto its exact Pulkovo-1942 frame (nomen.frame), band 200 m.
2. find every pair of sheets sharing a frame side (meridian or parallel segment);
3. match_seam on each shared edge, pairing boundary crossings by BROAD group
   (the project rule: match geometry on broader groups, keep real
   disagreements) - tangential warp only, so the edge stays on the edge and no
   gap or overlap can open;
4. writes work/pdfvec_seamed/<sheet>.gpkg (same layers as the input, geometry
   warped) + work/ru_seams.gpkg: layer 'seams' (one line per shared edge with stats)
   and 'conflicts' (edge intervals where the two sheets disagree, with both classes).

Classes come straight from sources/legend_<sheet>.csv (hclass), so this runs before
ingest_russia.py pdfvec, which then reads the seamed copies.

usage: seam_russia.py [--tol 1000] [--band 3000]
"""
import argparse
import itertools
import json
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402  (FIRST: it points PROJ at a /tmp copy of proj.db)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import pyproj  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString  # noqa: E402
from shapely.ops import substring  # noqa: E402
import seam  # noqa: E402
import nomen  # noqa: E402
from ingest_russia import PDF_SHEETS, PDFVEC as _P, JPGVEC  # noqa: E402

PDFVEC = f'{S.WORK}/pdfvec'
OUTDIR = f'{S.WORK}/pdfvec_seamed'
SRCDIR = os.path.join(os.path.dirname(S.WORK), 'sources')
FRAMES = {'R-52': (126, 68, 132, 72)}
# broad groups for pairing crossings: sheets of different teams split glacial,
# slope and fluvial/lacustrine families differently; the fine class is kept.
BROAD = {'T': 'G', 'GF': 'G', 'GL': 'G', 'GM': 'M', 'M': 'M', 'W': 'S', 'C': 'S',
         'F': 'FL', 'L': 'FL', 'Y': 'Y', 'O': 'O', 'H': 'H', 'R': 'R', 'X': 'X', 'E': 'E', 'K': 'K', 'V': 'V'}


def frame(sheet):
    return FRAMES.get(sheet) or nomen.frame(sheet)


def src_path(sheet):
    """raw extraction (vector PDF or raster scan) - never the seamed copy"""
    return next((f'{d}/{sheet}.gpkg' for d in (_P, JPGVEC) if os.path.exists(f'{d}/{sheet}.gpkg')), None)


def load(sheet):
    u = gpd.read_file(src_path(sheet), layer='units').to_crs(S.CRS)
    leg = pd.read_csv(f'{SRCDIR}/legend_{sheet}.csv', dtype=str, keep_default_na=False)
    h = dict(zip(leg['index'], leg['hclass']))
    u['hclass'] = u['index'].map(lambda s: 'H' if s == 'WATER' else h.get(s.split('|')[0], 'Q'))
    u['broad'] = u['hclass'].map(BROAD).fillna(u['hclass'])
    return u


def edge_line(lon0, lat0, lon1, lat1, step=0.005):
    t = pyproj.Transformer.from_crs(4284, S.CRS, always_xy=True)
    n = int(round(max(abs(lon1 - lon0), abs(lat1 - lat0)) / step)) + 1
    return LineString(np.c_[t.transform(np.linspace(lon0, lon1, n), np.linspace(lat0, lat1, n))])


def shared_edges(frames):
    """(A, B, lonlat segment) for every pair sharing a side; A = west/south sheet."""
    out = []
    for a, b in itertools.permutations(frames, 2):
        (w0, s0, e0, n0), (w1, s1, e1, n1) = frames[a], frames[b]
        if abs(e0 - w1) < 1e-6:                          # a west of b: meridian e0
            lo, hi = max(s0, s1), min(n0, n1)
            if hi - lo > 1e-6:
                out.append((a, b, (e0, lo, e0, hi)))
        if abs(n0 - s1) < 1e-6:                          # a south of b: parallel n0
            lo, hi = max(w0, w1), min(e0, e1)
            if hi - lo > 1e-6:
                out.append((a, b, (lo, n0, hi, n0)))
    return out


def conflict_lines(edge, conf, a, b, step=25.0):
    """Merge consecutive 25 m disagreement samples into edge intervals."""
    if conf.empty:
        return []
    rows, pos = [], conf['pos'].values
    brk = np.r_[0, np.nonzero(np.diff(pos) > step * 1.5)[0] + 1, len(pos)]
    for i, j in zip(brk[:-1], brk[1:]):
        seg = conf.iloc[i:j]
        top = seg.groupby(['a', 'b']).size().idxmax()
        rows.append(dict(sheet_a=a, sheet_b=b, class_a=top[0], class_b=top[1],
                         length_m=float(pos[j - 1] - pos[i] + step),
                         geometry=substring(edge, max(pos[i] - step / 2, 0), min(pos[j - 1] + step / 2, edge.length))))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tol', type=float, default=1000.0)
    ap.add_argument('--band', type=float, default=3000.0)
    a = ap.parse_args()
    sheets = [s for s in PDF_SHEETS if src_path(s)]
    frames = {s: frame(s) for s in sheets}
    U, snap = {}, {}
    for s in sheets:
        U[s], snap[s] = seam.band_snap(load(s), frames[s], datum=4284, band=200.0, exact=True)
        print('snap', s, {k: v for k, v in snap[s].items() if k.endswith('_after_m')}, flush=True)
    edges = shared_edges(frames)
    print(f'{len(sheets)} sheets, {len(edges)} shared edges', flush=True)
    seams, conflicts = [], []
    for A, B, (lo0, la0, lo1, la1) in edges:
        edge = edge_line(lo0, la0, lo1, la1)
        near = lambda g: g[shapely.dwithin(g.geometry.values, edge, a.band)]   # noqa: E731
        nA, nB = near(U[A]), near(U[B])
        if nA.empty or nB.empty:
            print('skip (no units at edge)', A, B)
            continue
        A2, B2, pairs, conf, st = seam.match_seam(nA, nB, edge, tol=a.tol, band=a.band, cls='broad')
        # put the warped near-edge polygons back (their indices survive polygons_only? no: explode
        # renumbers) - replace the near-edge subset wholesale
        U[A] = pd.concat([U[A].drop(nA.index), A2], ignore_index=True)
        U[B] = pd.concat([U[B].drop(nB.index), B2], ignore_index=True)
        # fine-class agreement on the warped edge, for the report
        _, fa = seam.crossings(A2, edge, 'hclass')
        _, fb = seam.crossings(B2, edge, 'hclass')
        n = min(len(fa), len(fb))
        st['agree_fine'] = float((fa['cls'].values[:n] == fb['cls'].values[:n]).mean()) if n else None
        st.update(sheet_a=A, sheet_b=B, side=f'{lo0},{la0},{lo1},{la1}')
        print('seam', A, '|', B, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in st.items()}, flush=True)
        seams.append(dict(st, geometry=edge))
        conflicts += conflict_lines(edge, conf, A, B)
    os.makedirs(OUTDIR, exist_ok=True)
    for s in sheets:
        g = U[s].drop(columns=['broad', 'hclass'])
        # the warp can split a polygon at the band edge: re-dissolve by unit
        g = g.dissolve(by=['index', 'fill'], as_index=False, aggfunc='first')
        g = S.polygons_only(g)
        o = f'{OUTDIR}/{s}.gpkg'
        if os.path.exists(o):
            os.remove(o)
        g.to_file(o, layer='units', driver='GPKG')
        gpd.read_file(src_path(s), layer='neatline').to_file(o, layer='neatline', driver='GPKG')
    out = f'{S.WORK}/ru_seams.gpkg'
    if os.path.exists(out):
        os.remove(out)
    if seams:
        gpd.GeoDataFrame(seams, crs=S.CRS).to_file(out, layer='seams', driver='GPKG')
    if conflicts:
        gpd.GeoDataFrame(conflicts, crs=S.CRS).to_file(out, layer='conflicts', driver='GPKG')
    summ = dict(sheets=sheets, n_edges=len(seams), band_snap=snap,
                seams=[{k: v for k, v in r.items() if k != 'geometry'} for r in seams])
    json.dump(summ, open(f'{S.WORK}/ru_seams.json', 'w'), indent=1, default=str)
    print('wrote', out, OUTDIR)


if __name__ == '__main__':
    main()
