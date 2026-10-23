"""Zoom windows around N points of a scan (4x, 10 px grid, red cross = the given point) for reading exact
graticule crossings / corners. usage: zoom_points.py <img> <out.png> "x,y;x,y;..." [half=60] [labels a;b;...]"""
import sys

from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
img, out, ps = sys.argv[1:4]
half = int(sys.argv[4]) if len(sys.argv) > 4 else 60
labs = sys.argv[5].split(';') if len(sys.argv) > 5 else None
im = Image.open(img).convert('RGB')
pts = [tuple(int(float(v)) for v in p.split(',')) for p in ps.split(';')]
sc = 4; w = 2 * half * sc
ncol = min(4, len(pts)); nrow = (len(pts) + ncol - 1) // ncol
canvas = Image.new('RGB', (ncol * (w + 6), nrow * (w + 6)), 'white')
for k, (x, y) in enumerate(pts):
    t = im.crop((x - half, y - half, x + half, y + half)).resize((w, w), Image.NEAREST)
    d = ImageDraw.Draw(t)
    for g in range(0, 2 * half + 1, 10):
        d.line([(g * sc, 0), (g * sc, w)], fill=(0, 170, 255)); d.line([(0, g * sc), (w, g * sc)], fill=(0, 170, 255))
    d.line([(half * sc - 12, half * sc), (half * sc + 12, half * sc)], fill=(255, 0, 0), width=2)
    d.line([(half * sc, half * sc - 12), (half * sc, half * sc + 12)], fill=(255, 0, 0), width=2)
    d.text((4, 4), f'{labs[k] if labs else k}: origin {x - half},{y - half}', fill=(255, 0, 0))
    canvas.paste(t, ((k % ncol) * (w + 6), (k // ncol) * (w + 6)))
canvas.save(out)
