"""Write sources/legend_<sheet>.csv from a compact spec (one line per swatch, ';'-separated:
fill;index;hclass;hclass2;texture;ice_rich;description). First line = note for the sheet.
usage: mk_legend.py <sheet> <spec.txt>"""
import csv
import sys

sheet, spec = sys.argv[1], sys.argv[2]
L = [l.rstrip('\n') for l in open(spec, encoding='utf-8') if l.strip()]
note = L[0]
with open(f'sources/legend_{sheet}.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['k', 'fill', 'index', 'description_ru', 'hclass', 'hclass2', 'texture', 'ice_rich', 'note'])
    for k, l in enumerate(L[1:]):
        fill, idx, h, h2, tex, ice, desc = (l.split(';') + [''] * 7)[:7]
        w.writerow([k, fill.strip(), idx.strip(), desc.strip() or idx.strip(), h.strip(), h2.strip(), tex.strip(), ice.strip(), note if k == 0 else ''])
print(sheet, len(L) - 1, 'rows')
