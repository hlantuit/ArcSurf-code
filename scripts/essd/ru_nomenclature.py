#!/usr/bin/env python
"""Frames of Russian (Soviet) map sheets from their nomenclature, for figures.

  1:1,000,000  'N-49'      row letter A..V (4 degrees of latitude from the equator), column 1..60 (6 degrees of
               longitude from 180 W); combined sheets 'N-49-50', 'R-35-37' (columns 49 to 50, 35 to 37)
  1:200,000    'P-39-X'    sheet I..XXXVI of the 1:1M sheet, row-major from the north-west, 40' x 1 degree;
               combined 'Q-39-XXXIII,XXXIV'
Suffixes such as _g2, _g3, _g2pv, _pq are ignored; ids joined by '_' (e.g. 'P-58-XXXIV_O-58-IV') are unions.
frame(sheet) -> shapely Polygon/MultiPolygon in lon/lat (EPSG:4326), densified along the parallels"""
import re

import numpy as np
import shapely

ROWS = 'ABCDEFGHIJKLMNOPQRSTUV'
ROMAN = {'I': 1, 'V': 5, 'X': 10, 'L': 50}


def roman(s):
    v, prev = 0, 0
    for ch in reversed(s):
        n = ROMAN[ch]
        v += -n if n < prev else n
        prev = max(prev, n)
    return v


def box(lon0, lat0, lon1, lat1, n=24):
    lons = np.linspace(lon0, lon1, n)
    ring = ([(x, lat0) for x in lons] + [(lon1, lat1)] + [(x, lat1) for x in lons[::-1]] + [(lon0, lat0)])
    return shapely.Polygon(ring)


TOKEN = re.compile(r'^\(?([A-V])\)?-\(?(\d{1,2})\)?(?:-\(?(\d{1,2})\)?)?(?:-([IVXL,]+))?$')


def frame_token(tok):
    m = TOKEN.match(tok)
    if not m:
        return None
    row, c0, c1, sub = m.group(1), int(m.group(2)), m.group(3), m.group(4)
    lat0 = 4 * ROWS.index(row)
    if sub:
        parts = []
        for r in sub.split(','):
            k = roman(r) - 1
            rr, cc = divmod(k, 6)
            lon0 = -180 + 6 * (c0 - 1) + cc
            top = lat0 + 4 - rr * (2 / 3)
            parts.append(box(lon0, top - 2 / 3, lon0 + 1, top))
        return shapely.union_all(parts)
    c1 = int(c1) if c1 else c0
    return box(-180 + 6 * (c0 - 1), lat0, -180 + 6 * c1, lat0 + 4)


def frame(sheet):
    toks = [t for t in re.split(r'_', sheet) if t and not re.fullmatch(r'g\d\w*|pq|pv', t)]
    parts = [f for f in (frame_token(t) for t in toks) if f is not None]
    return shapely.union_all(parts) if parts else None


if __name__ == '__main__':
    for s in ('N-49-50_g2', 'R-35-37_g2', 'P-39-X', 'Q-39-XXXIII,XXXIV', 'P-58-XXXIV_O-58-IV', 'T-48-50_g2pv',
              'Q-2_g2', 'Q-39_g3', 'S-44-46_g2', 'T-47-XXXI,XXXII,XXXIII'):
        f = frame(s)
        print(s, None if f is None else [round(v, 3) for v in f.bounds])
