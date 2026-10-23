"""Contact sheet of catalogue maps (largest image per label: jp2/tif/jpg on disk, or the largest image embedded in
a PDF, also inside zips) to sort the backlog into colour / line / text. usage: backlog_thumbs.py <out.png> LABEL ..."""
import glob
import io
import os
import sys
import zipfile

from PIL import Image, ImageDraw  # PIL before fitz (GLIBCXX on Albedo)
import fitz

Image.MAX_IMAGE_PIXELS = None
ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SCR = '/albedo/scratch/user/hlantuit/arctic_surficial'


def biggest_pdf_image(data):
    d = fitz.open(stream=data, filetype='pdf')
    best = None
    for pno in range(min(len(d), 3)):
        for im in d[pno].get_images(full=True):
            w, h = im[2], im[3]
            if best is None or w * h > best[0]:
                best = (w * h, im[0])
    if best is None:
        return None
    x = d.extract_image(best[1])
    return Image.open(io.BytesIO(x['image']))


def thumb(lab):
    files = []
    for d in (f'{ROOT}/raw/canada/gsc_scans/{lab}', f'{SCR}/raw/canada/gsc_scans/{lab}'):
        files += glob.glob(d + '/*')
    imgs = [f for f in files if f.lower().endswith(('.jp2', '.tif', '.jpg', '.png'))]
    if imgs:
        return Image.open(max(imgs, key=os.path.getsize)), os.path.basename(max(imgs, key=os.path.getsize))
    zips = [f for f in files if f.endswith('.zip')]
    for z in zips:
        zf = zipfile.ZipFile(z)
        mem = [m for m in zf.infolist() if m.filename.lower().endswith(('.jp2', '.tif', '.jpg', '.png', '.pdf'))]
        mem = [m for m in mem if 'legend' not in m.filename.lower()]
        mem.sort(key=lambda m: -m.file_size)
        for m in mem[:3]:
            data = zf.read(m)
            im = biggest_pdf_image(data) if m.filename.lower().endswith('.pdf') else Image.open(io.BytesIO(data))
            if im is not None and im.width * im.height > 4e6:
                return im, f'{os.path.basename(z)}:{m.filename} (+{len(mem) - 1})'
    pdfs = [f for f in files if f.endswith('.pdf')]
    for p in pdfs:
        im = biggest_pdf_image(open(p, 'rb').read())
        if im is not None:
            return im, os.path.basename(p)
    return None, 'no image'


out = sys.argv[1]
tiles = []
for lab in sys.argv[2:]:
    try:
        im, name = thumb(lab)
    except Exception as e:
        im, name = None, f'ERR {e}'[:60]
    t = Image.new('RGB', (420, 440), 'white')
    if im is not None:
        sz = im.size
        im = im.convert('RGB'); im.thumbnail((420, 420)); t.paste(im, (0, 20))
        name = f'{sz[0]}x{sz[1]} ' + name
    ImageDraw.Draw(t).text((3, 3), f'{lab}: {name}'[:70], fill=(255, 0, 0))
    tiles.append(t)
    print(lab, name, flush=True)
n = len(tiles); cols = 4; rows = (n + cols - 1) // cols
sheet = Image.new('RGB', (cols * 424, rows * 444), 'white')
for k, t in enumerate(tiles):
    sheet.paste(t, ((k % cols) * 424, (k // cols) * 444))
sheet.save(out)
