"""Contact sheet of GSC scan candidates (triage: colour units vs line/label vs symbol maps).
usage: scan_thumbs.py <out.png> [n=24] [skip,labels]   reads work/scan_rank.csv (jp2 rows, by gain)."""
import glob
import sys

import pandas as pd
from PIL import Image, ImageDraw

Image.MAX_IMAGE_PIXELS = None
W0 = '/albedo/work/user/hlantuit/arctic_surficial'
out = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
skip = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else set()
r = pd.read_csv(f'{W0}/work/scan_rank.csv')
r = r[r.types.str.contains('jp2') & ~r.label.isin(skip)].head(n)
tiles = []
for _, row in r.iterrows():
    fs = sorted(glob.glob(f'{W0}/../../../../scratch/user/hlantuit/arctic_surficial/raw/canada/gsc_scans/{row.label}/*.jp2')) or \
        sorted(glob.glob(f'/albedo/scratch/user/hlantuit/arctic_surficial/raw/canada/gsc_scans/{row.label}/*.jp2'))
    fs = [f for f in fs if 'mn' in f] or fs
    if not fs:
        continue
    im = Image.open(fs[0]); im.draft('RGB', (im.width // 16, im.height // 16)); im = im.convert('RGB'); im.thumbnail((400, 400))
    c = Image.new('RGB', (400, 420), 'white'); c.paste(im, (0, 20))
    ImageDraw.Draw(c).text((3, 3), f'{row.label} {int(row.gain_km2)} km2 1:{int(row.scale)}', fill=(255, 0, 0))
    tiles.append(c)
cols = 6
sheet = Image.new('RGB', (cols * 400, ((len(tiles) + cols - 1) // cols) * 420), 'white')
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % cols) * 400, (i // cols) * 420))
sheet.save(out)
print(len(tiles), 'thumbs:', ' '.join(r.label))
