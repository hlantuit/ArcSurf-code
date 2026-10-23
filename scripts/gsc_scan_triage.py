"""Triage every legacy GSC scan file (jp2, pdf, and pdfs inside the zips) for the raster
pipeline: is it a COLOUR-FILLED unit map (usable), or a line/label map, landform map, table
or legend sheet (not usable by colour classification)?
Per file, on a ~1500 px preview: fraction of strongly coloured pixels (chroma > 18),
number of distinct colour clusters, and fraction of very pale paper. Writes
work/gscvec/triage.csv (+ gain from work/gsc_scans_survey.csv) and contact sheets of the
candidates to work/gscvec/triage_*.png."""
import glob
import io
import os
import sys
import zipfile

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from multiprocessing import Pool  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
# usage: gsc_scan_triage.py [scans_dir out_dir]   (default: the 315 legacy GSC scans)
SCANS = sys.argv[1] if len(sys.argv) > 2 else f'{ROOT}/raw/canada/gsc_scans'
OUT = sys.argv[2] if len(sys.argv) > 2 else f'{ROOT}/work/gscvec'


def to_lab(rgb):
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883], np.float32)
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def previews(label):
    """(name, PIL image ~1500 px) for every map image of a sheet"""
    out = []
    for f in sorted(glob.glob(f'{SCANS}/{label}/*')):
        ext = f.rsplit('.', 1)[-1].lower()
        try:
            if ext == 'jp2':
                im = Image.open(f); W, H = im.size
                im.draft('RGB', (W // 8, H // 8)); im = im.convert('RGB'); im.thumbnail((1500, 1500))
                out.append((os.path.basename(f), im))
            elif ext in ('pdf', 'zip'):
                import pymupdf
                srcs = []
                if ext == 'pdf':
                    srcs.append((os.path.basename(f), open(f, 'rb').read()))
                else:
                    z = zipfile.ZipFile(f)
                    srcs += [(n, z.read(n)) for n in z.namelist() if n.lower().endswith('.pdf')]
                for n, data in srcs:
                    d = pymupdf.open(stream=data, filetype='pdf')
                    for i, pg in enumerate(d):
                        z_ = 1500 / max(pg.rect.width, pg.rect.height)
                        pix = pg.get_pixmap(matrix=pymupdf.Matrix(z_, z_), alpha=False)
                        out.append((f'{n}#p{i}', Image.frombytes('RGB', (pix.width, pix.height), pix.samples)))
        except Exception as e:
            out.append((os.path.basename(f) + ' ERR ' + str(e)[:60], None))
    return out


def one(label):
    rows = []
    for name, im in previews(label):
        if im is None:
            rows.append(dict(label=label, file=name, usable=False, why='unreadable')); continue
        a = np.asarray(im)
        lab = to_lab(a)
        ch = np.hypot(lab[..., 1], lab[..., 2])
        coloured = (ch > 18) & (lab[..., 0] > 30)
        pale = (lab[..., 0] > 92) & (ch < 10)
        q = (a[coloured] // 32).astype(np.int32)
        ncl = len(np.unique(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2])) if len(q) else 0
        cf = float(coloured.mean())
        usable = cf > 0.12 and ncl >= 6
        why = 'colour-filled units' if usable else ('few colours (line/label or landform map)' if cf <= 0.12 else 'low colour variety')
        rows.append(dict(label=label, file=name, colour_frac=round(cf, 3), pale_frac=round(float(pale.mean()), 3),
                         n_colour_bins=ncl, usable=usable, why=why))
        im.thumbnail((360, 360)); im.save(f'{OUT}/triage_thumbs/{label}__{name.replace("/", "_").replace("#", "_")}.png')
    return rows


if __name__ == '__main__':
    os.makedirs(f'{OUT}/triage_thumbs', exist_ok=True)
    labels = sorted(os.listdir(SCANS))
    with Pool(16) as p:
        res = [r for rr in p.map(one, labels) for r in rr]
    t = pd.DataFrame(res)
    if len(sys.argv) > 2:      # OSTR census items: metadata from the census table, gain unknown yet
        sv = pd.read_csv(f'{ROOT}/sources/canada_ostr_new_in_domain.csv', dtype={'geoscan': str})
        sv = sv.rename(columns={'geoscan': 'label'})[['label', 'scale', 'year', 'title', 'tuk_delta']]
        sv['gain_km2'] = 0
        t['label'] = t['label'].astype(str)
    else:
        sv = pd.read_csv(f'{ROOT}/work/gsc_scans_survey.csv')[['label', 'scale', 'year', 'gain_km2', 'title']]
    t = t.merge(sv, on='label', how='left').sort_values(['usable', 'gain_km2'], ascending=[False, False])
    t.to_csv(f'{OUT}/triage.csv', index=False)
    s = t.groupby('label').agg(usable=('usable', 'any'), gain=('gain_km2', 'first'), scale=('scale', 'first'))
    print('files', len(t), '| sheets', len(s), '| sheets with a usable colour map:', int(s.usable.sum()),
          '| their gain km2 (overlaps double-count):', int(s[s.usable].gain.sum()))
    print(t.why.value_counts().to_dict())
    pd.set_option('display.width', 220)
    print(s[s.usable].sort_values('gain', ascending=False).head(40).to_string())
