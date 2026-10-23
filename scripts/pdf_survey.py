#!/usr/bin/env python
"""Survey a vector map PDF: page size, drawings, fill-colour histogram (by area),
text spans (graticule / legend candidates), largest filled paths.

usage: pdf_survey.py <file.pdf> [...]
"""
import collections
import re
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import pymupdf  # noqa: E402


def hexc(c):
    return '#%02x%02x%02x' % tuple(int(round(v * 255)) for v in c) if c else None


for f in sys.argv[1:]:
    doc = pymupdf.open(f)
    print(f'### {f}: {doc.page_count} page(s), producer={doc.metadata.get("producer")!r} creator={doc.metadata.get("creator")!r}')
    for pno, page in enumerate(doc):
        r = page.rect
        print(f'  page {pno}: {r.width:.0f} x {r.height:.0f} pt ({r.width/72*25.4:.0f} x {r.height/72*25.4:.0f} mm), images={len(page.get_images())}')
        dr = page.get_drawings()
        fills = [d for d in dr if d.get('fill') is not None]
        print(f'  drawings {len(dr)}, filled {len(fills)}, stroked-only {sum(1 for d in dr if d.get("fill") is None)}')
        area = collections.Counter()
        cnt = collections.Counter()
        for d in fills:
            c = hexc(d['fill'])
            area[c] += d['rect'].width * d['rect'].height
            cnt[c] += 1
        print(f'  distinct fill colours: {len(area)}; top 25 by bbox-area:')
        for c, a in area.most_common(25):
            print(f'     {c}  n={cnt[c]:5d}  bbox-area={a/1e4:9.1f} (x1e4 pt2)')
        big = sorted(fills, key=lambda d: -d['rect'].width * d['rect'].height)[:5]
        for d in big:
            print('   biggest fill', hexc(d['fill']), [round(v) for v in d['rect']], 'items', len(d['items']))
        words = page.get_text('words')
        print(f'  words: {len(words)}')
        deg = [w for w in words if re.search(r'\d+\s*°|°', w[4])]
        print('  degree-like text:', [(w[4], round(w[0]), round(w[1])) for w in deg[:40]])
        # legend candidates: short index-like tokens (a, gIII, mH ...)
        idx = [w[4] for w in words if re.match(r'^[a-z]{1,4}[A-ZIVXLH\d]', w[4])]
        print('  index-like tokens (first 60):', idx[:60])
        sample = [w[4] for w in words[:80]]
        print('  first words:', sample)
