#!/usr/bin/env python
"""Check an A0 print PDF: page size (mm), embedded fonts (type, embedded), number of text spans, and render the side
panel and two map corners at 100 dpi for a visual check. usage: check_a0_pdf.py PDF OUTPREFIX"""
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import fitz  # noqa: E402

pdf, pre = sys.argv[1], sys.argv[2]
doc = fitz.open(pdf)
pg = doc[0]
w, h = pg.rect.width / 72 * 25.4, pg.rect.height / 72 * 25.4
print(f'page {w:.1f} x {h:.1f} mm, pages {len(doc)}')
for f in pg.get_fonts(full=True):
    print('font', f[3], f[2], 'ext', f[1])
spans = sum(len(l['spans']) for b in pg.get_text('dict')['blocks'] if b.get('type') == 0 for l in b['lines'])
print('text spans', spans)
mm = 72 / 25.4
for name, (x0, y0, x1, y1) in {'panel': (930, 20, 1175, 820), 'map_topleft': (15, 15, 220, 200),
                               'map_bottomright': (700, 640, 930, 820)}.items():
    clip = fitz.Rect(x0 * mm, y0 * mm, x1 * mm, y1 * mm)
    pg.get_pixmap(dpi=100 if name == 'panel' else 150, clip=clip).save(f'{pre}_{name}.png')
    print('wrote', f'{pre}_{name}.png')
