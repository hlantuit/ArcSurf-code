import sys, glob, re, collections
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
import numpy  # noqa: F401  (before pymupdf: GLIBCXX)
import pymupdf
G = '/albedo/scratch/user/hlantuit/arctic_surficial/raw/russia_geokniga'
for f in sorted(glob.glob(f'{G}/*/*.pdf')):
    t = pymupdf.open(f)[0].get_text()
    ys = collections.Counter(re.findall(r'(?<!\d)(19[5-9]\d|20[0-2]\d)(?!\d)', t))
    city = re.findall(r'(Санкт-Петербург|Москва|Ленинград)[^\n]{0,20}', t)
    print(f.split('/')[-2], len(t), ys.most_common(4), city[:2])
