#!/usr/bin/env python
"""Check of flagged raster sheets against their scans (Sect. 6.3): per sheet one image with the scan (the map image
run_rast.sh picks: the largest JPG that is not a legend, imprint or section file), the classified map face
(work/jpgvec/<sheet>_class.png) and the legend as extracted (swatch, index, class, share of the sheet, share of its
pixels matched directly, description), so that a reader can see whether each tint of the map was read as the right
unit.
usage: qa_sheet_composite.py OUTDIR SHEET [SHEET ...]"""
import ast
import glob
import os
import re
import sys

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga'
EXTRA = re.compile(r'(q|p)(inf|l|r|s[0-9]+)(_[0-9]+)?\.jpg$|q_(inf|l|r|s[0-9]+)\.jpg$', re.I)
Image.MAX_IMAGE_PIXELS = None


def font(size):
    import matplotlib
    return ImageFont.truetype(os.path.join(os.path.dirname(matplotlib.__file__), 'mpl-data/fonts/ttf/DejaVuSans.ttf'),
                              size)


def shares(sheet):
    """{index: (share of the sheet, share matched directly)} from the extraction log"""
    for line in open(f'{ROOT}/work/jpgvec/{sheet}.log', encoding='utf-8', errors='replace'):
        if line.startswith('units (index'):
            txt = re.sub(r'np\.float64\(([^)]*)\)', r'\1', line[line.index('{'):].strip())
            return ast.literal_eval(txt)
    return {}


def composite(sheet, out):
    jpgs = [j for j in glob.glob(f'{RAW}/{sheet}/*.jpg') if not EXTRA.search(os.path.basename(j))]
    scan = Image.open(max(jpgs, key=os.path.getsize)).convert('RGB')
    cls = Image.open(f'{ROOT}/work/jpgvec/{sheet}_class.png').convert('RGB')
    w = 1100
    scan = scan.resize((w, round(scan.height * w / scan.width)), Image.LANCZOS)
    cls = cls.resize((w, round(cls.height * w / cls.width)), Image.LANCZOS)
    leg = pd.read_csv(f'{ROOT}/sources/legend_{sheet}.csv')
    sh = shares(sheet)
    leg['share'] = [sh.get(str(i), (0.0, 0.0))[0] for i in leg['index']]
    leg['direct'] = [sh.get(str(i), (0.0, 0.0))[1] for i in leg['index']]
    leg = leg.sort_values('share', ascending=False)
    row, f, fb = 24, font(16), font(20)
    H = max(scan.height, cls.height) + 40 + row * (len(leg) + 1) + 20
    img = Image.new('RGB', (2 * w + 30, H), 'white')
    d = ImageDraw.Draw(img)
    d.text((10, 8), f'{sheet}: scan (left) and the classes as extracted (right)', fill='black', font=fb)
    img.paste(scan, (0, 40))
    img.paste(cls, (w + 30, 40))
    y = 40 + max(scan.height, cls.height) + 10
    d.text((10, y), 'swatch  index  class  share of sheet  matched directly  description', fill='black', font=f)
    for _, r in leg.iterrows():
        y += row
        d.rectangle((10, y + 2, 60, y + 20), fill=str(r['fill']), outline='black')
        desc = str(r.get('description_ru', ''))[:120]
        d.text((70, y), f"{r['index']}   {r['hclass']}{'/' + str(r['hclass2']) if pd.notna(r.get('hclass2')) else ''}"
                        f"   {r['share']:.3f}   {r['direct']:.2f}   {desc}", fill='black', font=f)
    p = f'{out}/qa_{sheet}.png'
    img.save(p)
    print(sheet, p, img.size, flush=True)


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for s in sys.argv[2:]:
        try:
            composite(s, out)
        except Exception as e:
            print(s, 'FAILED', repr(e)[:200], flush=True)


if __name__ == '__main__':
    main()
