"""Render the four frame-corner windows of a scanned sheet as one 2x2 mosaic, for reading
the corner coordinate labels and placing approximate corner pixels.
usage: scan_corners.py <image> <out.png> x_tl,y_tl x_tr,y_tr x_br,y_br x_bl,y_bl [half_window_px]
Each tile is labelled with its full-resolution pixel window so positions can be read back."""
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
import jpg_to_polygons as J  # noqa: E402

img, out = sys.argv[1], sys.argv[2]
cs = [tuple(map(int, c.split(','))) for c in sys.argv[3:7]]
hw = int(sys.argv[7]) if len(sys.argv) > 7 else 700
a = J.load_rgb(img)
H, W = a.shape[:2]
tiles = []
for n, (x, y) in zip(('TL', 'TR', 'BR', 'BL'), cs):
    x0, y0 = max(x - hw, 0), max(y - hw, 0)
    x1, y1 = min(x + hw, W), min(y + hw, H)
    t = Image.fromarray(np.ascontiguousarray(a[y0:y1, x0:x1]))
    s = 600 / max(t.size)
    t = t.resize((int(t.size[0] * s), int(t.size[1] * s)))
    d = ImageDraw.Draw(t)
    # grid every 200 full-res px, labelled, to read positions back
    for gx in range((x0 // 200 + 1) * 200, x1, 200):
        d.line([((gx - x0) * s, 0), ((gx - x0) * s, t.size[1])], fill=(255, 0, 0) if gx % 1000 == 0 else (255, 170, 170), width=1)
        if gx % 1000 == 0:
            d.text(((gx - x0) * s + 2, 2), str(gx), fill=(200, 0, 0))
    for gy in range((y0 // 200 + 1) * 200, y1, 200):
        d.line([(0, (gy - y0) * s), (t.size[0], (gy - y0) * s)], fill=(0, 0, 255) if gy % 1000 == 0 else (170, 170, 255), width=1)
        if gy % 1000 == 0:
            d.text((2, (gy - y0) * s + 2), str(gy), fill=(0, 0, 200))
    d.text((5, t.size[1] - 14), f'{n} x{x0}-{x1} y{y0}-{y1}', fill=(0, 0, 0))
    tiles.append(t)
m = Image.new('RGB', (1210, 1210), 'white')
for i, t in enumerate(tiles):
    m.paste(t, ((i % 2) * 610, (i // 2) * 610))
m.save(out)
print('image', W, H, 'saved', out)
