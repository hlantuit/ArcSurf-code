#!/usr/bin/env python
"""Soviet/Russian map sheet nomenclature -> geographic frame (lon0, lat0, lon1, lat1).

1:1,000,000  'R-52'            4 deg lat x 6 deg lon; row letter A=0-4N ... ; column n
                               spans (n-31)*6 .. (n-30)*6 E.  Combined sheets 'R-53,54'.
1:200,000    'R-35-XXIX,XXX'   36 cells per 1:1M sheet (6 x 6), each 40' lat x 1 deg lon,
                               numbered I..XXXVI row-wise from the NW corner. North of 60N
                               they are published doubled/tripled ('XXIX,XXX' = 2 deg wide).
The frame of a combined sheet is the union of its cells (must be a rectangle).
"""
import re

ROMAN = {'I': 1, 'V': 5, 'X': 10, 'L': 50}


def roman(s):
    s = s.strip().upper()
    v = 0
    for i, ch in enumerate(s):
        x = ROMAN[ch]
        v += -x if i + 1 < len(s) and ROMAN[s[i + 1]] > x else x
    return v


def m1(letter, col):
    lat0 = (ord(letter.upper()) - ord('A')) * 4
    lon0 = (int(col) - 31) * 6
    return lon0, lat0, lon0 + 6, lat0 + 4


def frame(code):
    code = code.replace('_', '').replace(' ', '')
    m = re.match(r'^([A-V])-(\d{1,2})(?:[-,](\d{1,2}))?$', code)
    if m and not re.search(r'[IVXL]', code):              # 1:1M, possibly combined
        c0 = int(m.group(2)); c1 = int(m.group(3) or c0)
        a = m1(m.group(1), c0); b = m1(m.group(1), c1)
        return a[0], a[1], b[2], a[3]
    m = re.match(r'^([A-V])-(\d{1,2})-([IVXL,]+)$', code)
    if not m:
        raise ValueError(f'unrecognised nomenclature {code!r}')
    lon0, lat0, lon1, lat1 = m1(m.group(1), m.group(2))
    cells = [roman(x) for x in m.group(3).split(',') if x]
    boxes = []
    for k in cells:
        r, c = (k - 1) // 6, (k - 1) % 6
        top = lat1 - r * 40 / 60
        boxes.append((lon0 + c, top - 40 / 60, lon0 + c + 1, top))
    b = (min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes))
    area = sum((x[2] - x[0]) * (x[3] - x[1]) for x in boxes)
    assert abs(area - (b[2] - b[0]) * (b[3] - b[1])) < 1e-9, f'{code}: cells do not form a rectangle'
    return tuple(round(v, 6) for v in b)


if __name__ == '__main__':
    for c in ['R-52', 'R-35-XXIX,XXX', 'S-44-XXI,XXII', 'Q-37-XXV,XXVI', 'T-47-XXXI,XXXII,XXXIII', 'S-48-I,II']:
        print(c, frame(c))
