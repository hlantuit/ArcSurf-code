"""Survey of the downloaded legacy GSC scans (raw/canada/gsc_scans/<label>/): per sheet the
file type, raster size / dpi (JPEG2000 via GDAL, PDF pages via PyMuPDF), zip contents,
the catalogue extent and scale, and the GAIN: share of the sheet's land footprint whose
best current source is coarser than 1:500k (the GSC 1:5M backdrop) or nothing.
Writes work/gsc_scans_survey.csv sorted by gain km2."""
import glob
import json
import os
import sys
import zipfile

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402
import pyogrio  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SCANS = f'{ROOT}/raw/canada/gsc_scans'
inv = {x['label']: x for x in json.load(open(f'{ROOT}/sources/canada_legacy_scans.json', encoding='utf-8')) if 'files' in x}

# finer-than-1:500k coverage already in hand (footprints of the built sources)
fine = []
for f in glob.glob(f'{S.WORK}/xw/ca_*.gpkg') + glob.glob(f'{S.WORK}/xw/us_*.gpkg'):
    fp = gpd.read_file(f, layer='footprint')
    if 'scale_den' in fp:
        fp = fp[fp['scale_den'] <= 500_000]
    if len(fp):
        fine.append(shapely.union_all(fp.to_crs(S.CRS).geometry.values))
fine = shapely.union_all(fine)
shapely.prepare(fine)
land = pyogrio.read_dataframe(f'{S.WORK}/land_amap.gpkg', layer=pyogrio.list_layers(f'{S.WORK}/land_amap.gpkg')[0][0])
land_sindex = land.sindex
print('fine coverage and land loaded', flush=True)


def raster_info(p):
    ext = p.rsplit('.', 1)[-1].lower()
    try:
        if ext == 'jp2':
            # this GDAL build has no OpenJPEG driver; Pillow reads JPEG2000 (header only here)
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = None
            im = Image.open(p)
            return dict(w=im.size[0], h=im.size[1], mode=im.mode, dpi=str(im.info.get('dpi', '')))
        if ext == 'pdf':
            import numpy  # noqa: F401
            import pymupdf
            d = pymupdf.open(p)
            pg = d[0]
            imgs = pg.get_images(full=True)
            big = max(((i[2], i[3]) for i in imgs), default=(0, 0), key=lambda t: t[0] * t[1])
            return dict(w=big[0], h=big[1], pages=len(d), page_in=(round(pg.rect.width / 72, 1), round(pg.rect.height / 72, 1)),
                        n_draw=len(pg.get_drawings()) if len(imgs) == 0 else None)
        if ext == 'zip':
            z = zipfile.ZipFile(p)
            names = [n for n in z.namelist() if not n.endswith('/')]
            kinds = pd.Series([n.rsplit('.', 1)[-1].lower() for n in names]).value_counts().head(6).to_dict()
            return dict(zip_kinds=kinds, zip_n=len(names))
    except Exception as e:
        return dict(err=str(e)[:80])
    return {}


rows = []
for lab, x in sorted(inv.items()):
    d = f'{SCANS}/{lab}'
    files = sorted(glob.glob(f'{d}/*'))
    b = x.get('bbox') or [np.nan] * 4
    r = dict(label=lab, title=x['title'][:80], scale=x['scale'], year=str(x.get('release') or '')[:4],
             lon0=b[0], lat0=b[1], lon1=b[2], lat1=b[3], files=len(files),
             types=','.join(sorted({f.rsplit('.', 1)[-1].lower() for f in files})))
    if files:
        r.update(raster_info(max(files, key=os.path.getsize)))
    # gain: sheet land area not yet covered finer than 1:500k
    try:
        box = gpd.GeoSeries([shapely.box(*b)], crs=4326).to_crs(S.CRS).geometry.values[0]
        li = land.geometry.values[land_sindex.query(box)]
        bl = shapely.intersection(shapely.union_all(li), box) if len(li) else shapely.Polygon()
        gain = shapely.difference(bl, fine)
        r['land_km2'] = round(bl.area / 1e6)
        r['gain_km2'] = round(gain.area / 1e6)
    except Exception as e:
        r['land_km2'] = r['gain_km2'] = None
        r['err_gain'] = str(e)[:60]
    rows.append(r)
t = pd.DataFrame(rows).sort_values('gain_km2', ascending=False)
t.to_csv(f'{S.WORK}/gsc_scans_survey.csv', index=False)
pd.set_option('display.width', 250)
print(t[['label', 'scale', 'year', 'types', 'w', 'h', 'land_km2', 'gain_km2', 'title']].head(40).to_string(index=False))
print('sheets', len(t), '| with gain > 1000 km2:', int((t.gain_km2 > 1000).sum()), '| total gain km2', int(t.gain_km2.sum()),
      '(overlapping sheets double-count)')
print('types', t.types.value_counts().to_dict())
