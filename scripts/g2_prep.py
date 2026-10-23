"""Crops for registering a scanned 1:1M sheet (geokniga GGK-1000/2 JPG) by eye.
usage:
  g2_prep.py preview <jpg> <out.png>                       1/8 preview (read approximate corners x8)
  g2_prep.py corners <jpg> <out.png> "x,y;x,y;x,y;x,y"     TL;TR;BR;BL: 600 px windows, 100 px grid
  g2_prep.py zoom    <jpg> <out.png> "x,y;x,y;x,y;x,y"     120 px windows at 4x, 10 px grid (red = given point)
  g2_prep.py crops   <jpg> <prefix> x0,x1 y0,y1 [step]     full-res strips (legend columns), 1350 px tall
Window labels give each window's origin in full-res px: point = origin + px in the window."""
import sys

from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
cmd, jpg, out = sys.argv[1:4]
im = Image.open(jpg).convert('RGB')


def pts(s):
    return [tuple(int(v) for v in p.split(',')) for p in s.split(';')]


def tiles(points, half, scale, grid, labels=('TL', 'TR', 'BR', 'BL')):
    w = 2 * half * scale
    canvas = Image.new('RGB', (2 * w + 10, 2 * w + 10), 'white')
    for i, (lab, (x, y)) in enumerate(zip(labels, points)):
        x0, y0 = x - half, y - half
        t = im.crop((x0, y0, x0 + 2 * half, y0 + 2 * half)).resize((w, w), Image.NEAREST)
        d = ImageDraw.Draw(t)
        for g in range(0, 2 * half + 1, grid):
            c = (255, 0, 0) if g == half else (0, 160, 255)
            d.line([(g * scale, 0), (g * scale, w)], fill=c); d.line([(0, g * scale), (w, g * scale)], fill=c)
        d.text((5, 5), f'{lab} origin {x0},{y0} ({grid}px grid)', fill=(0, 0, 255))
        canvas.paste(t, ((i % 2) * (w + 10), (i // 2) * (w + 10)))
    canvas.save(out)


if cmd == 'preview':
    print(im.size)
    im.resize((im.width // 8, im.height // 8)).save(out)
elif cmd == 'corners':
    tiles(pts(sys.argv[4]), 300, 1, 100)
elif cmd == 'zoom':
    tiles(pts(sys.argv[4]), 60, 4, 10)
elif cmd == 'crops':
    x0, x1 = (int(v) for v in sys.argv[4].split(','))
    y0, y1 = (int(v) for v in sys.argv[5].split(','))
    step = int(sys.argv[6]) if len(sys.argv) > 6 else 1300
    k = 0
    for y in range(y0, y1, step):
        im.crop((x0, y, x1, min(y + step + 50, y1))).save(f'{out}{k}.png'); k += 1
    print(k, 'crops')
