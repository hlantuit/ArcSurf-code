#!/usr/bin/env python
"""Manuscript figures cut from the final A0 PDF: the whole sheet (Fig. 1) and a print-scale detail of the Mackenzie
Delta (true 1:10 000 000, 150 x 95 mm of the sheet). DPI5 (default 300): resolution of the detail; 400 dpi gives
353 dpi at the 170 mm width of the journal page.
usage: render_a0_figs.py PDF OUTDIR [DPI5]"""
import os
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402

pdf, out = sys.argv[1], sys.argv[2]
dpi5 = int(sys.argv[3]) if len(sys.argv) > 3 else 300
os.makedirs(out, exist_ok=True)
pg = pymupdf.open(pdf)[0]
mm = 72 / 25.4
pg.get_pixmap(dpi=60).save(f'{out}/fig1_a0_sheet.png')
# Mackenzie Delta: x = -1680 km, y = +1680 km in EPSG:6931 -> 302 mm from the left, 298 mm from the top of the sheet
clip = pymupdf.Rect(227 * mm, 250 * mm, 377 * mm, 345 * mm)
pg.get_pixmap(dpi=dpi5, clip=clip).save(f'{out}/fig5_detail_mackenzie.png')
print('ok')
