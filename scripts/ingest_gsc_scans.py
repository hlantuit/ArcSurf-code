"""Ingest legacy GSC sheets extracted from raster scans (work/gscvec/<label>.gpkg, by
run_gsc_scans.py) as source 'ca_gsc_scans'. Only sheets with qc == PASS in
work/gscvec/summary.csv. Crosswalk key '<label>|<index>' from sources/legend_gsc_<label>.csv
(hclass etc. assigned when transcribing). Scale / year from the GSC catalogue.
Footprint = the sheet's exact frame MINUS paper (the units' union): white = not mapped
by this sheet, so a coarser source fills it."""
import json
import sys

sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/scripts')
import surflib as S  # noqa: E402
import pandas as pd  # noqa: E402
import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
SRC = 'ca_gsc_scans'
OGL = 'Open Government Licence - Canada'
EDGE_PX = 20            # outer strip of every scanned sheet dropped, in PIXELS (printed frame band ~15-20 px reads as a unit)
cfg = pd.read_csv(f'{ROOT}/sources/gsc_scan_sheets.csv', dtype=str, keep_default_na=False).set_index('label')
qc = pd.read_csv(f'{S.WORK}/gscvec/summary.csv')
# QC gate recomputed here (rows written before the gate existed have no qc column):
# corner rms <= 300 m and coast median <= 1.2 mm at map scale (0.8 mm until 2026-10-02; Hugues relaxed it:
# lake/coast shorelines of 1:100k-1:125k sheets vs OSM differ by generalisation, ~130-140 m)
med = qc['coast'].astype(str).str.extract(r'median (\d+) m')[0].astype(float)
lim = 0.0012 * qc['label'].map(lambda l: float(cfg.loc[l, 'scale']) if l in cfg.index and cfg.loc[l, 'scale'] else 250000.0)
rms_lim = (0.00045 * qc['label'].map(lambda l: float(cfg.loc[l, 'scale']) if l in cfg.index and cfg.loc[l, 'scale'] else 250000.0)).clip(lower=300.0)
qc['qc'] = ((qc['ok']) & (qc['corner_rms_m'] <= rms_lim) & (med.isna() | (med <= lim))).map({True: 'PASS', False: 'FAIL'})
# manual override from the sheet config (qc_override=FAIL + qc_note): known defects that neither the corner fit nor
# the coast median sees (A1621a: east third ~750 m off; after the 2026-10-02 domain-edge fix its coast median fell
# to 510 m < 600 m, p90 still 3.7 km, so the automatic gate would have let it in)
if 'qc_override' in cfg:
    ov = qc['label'].map(lambda l: cfg.loc[l, 'qc_override'] if l in cfg.index else '')
    qc.loc[ov.eq('FAIL'), 'qc'] = 'FAIL (override)'
print(qc[['label', 'corner_rms_m', 'coast', 'qc']].to_string(index=False))
ok = qc[qc.qc.eq('PASS')].label.tolist()
cat = {x['label']: x for x in json.load(open(f'{ROOT}/sources/canada_gsc_sheets.json', encoding='utf-8'))['sheets']}
parts, fps, xw = [], [], []
for lab in ok:
    g = gpd.read_file(f'{S.WORK}/gscvec/{lab}.gpkg', layer='units').to_crs(S.CRS)
    # the printed neatline (grey / purple double line) classifies as whatever unit shares its
    # colour: 16-31 km2 false 'O' strips on the 1:125k Slave sheets, 71 km2 'LW' on A1620a
    # (2026-10-01; the strip is ~15-20 px wide at any scale: O to 200 m at 10.6 m/px, LW to 600 m at
    # 42 m/px). Drop the outer EDGE_PX pixels of every sheet; the footprint stays the full frame,
    # so merge_tiles fills that thin strip from this sheet's own neighbouring units.
    nl = gpd.read_file(f'{S.WORK}/gscvec/{lab}.gpkg', layer='neatline').to_crs(S.CRS)
    mpp = float(json.load(open(f'{S.WORK}/gscvec/{lab}.json')).get('m_per_px') or 10.0)
    inner = shapely.buffer(shapely.make_valid(nl.union_all()), -EDGE_PX * mpp)   # 1:125k 10.6 m/px -> 212 m; 1:500k 42 m/px -> 850 m
    g['geometry'] = shapely.intersection(shapely.make_valid(g.geometry.values), inner)
    g = S.in_amap(S.polygons_only(g))
    # grid overprint (A1693a organic deposits over the indicated mineral unit): split the
    # units; the overprinted part becomes index 'O/<base>' -> hclass O, hclass2 = base class
    # OF4662: organic_minor / fen_minor / peat_minor = organic 10-50 % of the unit -> index
    # 'o/<base>' keeps the base class, hclass2 O
    import fiona
    lays = fiona.listlayers(f'{S.WORK}/gscvec/{lab}.gpkg')
    for lay, pre, what in [('overprint_organic', 'O/', 'Organic deposits over: '),
                           ('overprint_organic_minor', 'o/', 'with peat/fen 10-50 %: '),
                           ('overprint_fen_minor', 'o/', 'with fen 10-50 %: '),
                           ('overprint_peat_minor', 'o/', 'with peat 10-50 %: ')]:
        if lay not in lays:
            continue
        ov = gpd.read_file(f'{S.WORK}/gscvec/{lab}.gpkg', layer=lay).to_crs(S.CRS)
        if not len(ov):
            continue
        ou = shapely.make_valid(ov.union_all())
        base = ~g['index'].str.contains('/')            # never overprint twice
        gb = g[base]
        inn, out = gb.copy(), gb.copy()
        inn['geometry'] = shapely.intersection(shapely.make_valid(gb.geometry.values), ou)
        out['geometry'] = shapely.difference(shapely.make_valid(gb.geometry.values), ou)
        inn['index'] = pre + inn['index']
        inn['description_ru'] = what + inn['description_ru']
        g = S.polygons_only(gpd.GeoDataFrame(pd.concat([g[~base], out, inn], ignore_index=True), crs=S.CRS))
    if cfg.loc[lab].get('clip_5m', '') if 'clip_5m' in cfg.columns else '':
        # 'idx=CLS,CLS;...': units allowed only where the GSC 1:5M map has one of the listed classes. Map 24-1987's
        # 'UND' ('generally till; includes marine deposits near the coasts, minor organic, fluvial, lacustrine') would
        # otherwise replace the 1:5M glaciomarine / glaciolacustrine / organic polygons (14k + 6.5k km2 of its gap cells)
        # with till; the removed parts are holes in this sheet, so the 1:5M class stays there
        g5 = gpd.read_file(f'{S.WORK}/xw/ca_gsc_5m.gpkg', layer='units', bbox=tuple(g.total_bounds))
        for spec in cfg.loc[lab, 'clip_5m'].split(';'):
            idx, cls = spec.split('=')
            keep = shapely.union_all(shapely.make_valid(g5.loc[g5['hclass'].isin(cls.split(','))].geometry.values))
            m = g['index'] == idx
            a0 = g.loc[m].area.sum()
            g.loc[m, 'geometry'] = shapely.intersection(shapely.make_valid(g.loc[m].geometry.values), keep)
            print(f'  {lab}: {idx} clipped to 1:5M {cls}: {a0 / 1e6:.0f} -> {g.loc[m].area.sum() / 1e6:.0f} km2', flush=True)
        g = S.polygons_only(g)
    if g.empty:
        continue
    g['xkey'] = lab + '|' + g['index']
    c = cat.get(lab.split('_')[0], {})             # multi-panel sheets: OF3634_1, OF3634_2
    yr = int(str(c.get('release') or c.get('year') or '0')[:4]) or None
    tier = (c.get('tier_from_title') or '').capitalize()
    u, _ = S.standardise(g, src_id=SRC, code='index', desc='description_ru', xkey='xkey',
                         sheet=pd.Series(lab, index=g.index), scale_den=int(cfg.loc[lab, 'scale']), pub_year=yr,
                         conf_tier=tier, extra=('fill',), licence=OGL + ' (GSC map scan; vectorised by colour classification)',
                         redistribution='open')
    parts.append(u)
    f = S.in_amap(gpd.GeoDataFrame({'src_id': [SRC], 'overlay': [0]}, geometry=[nl.union_all()], crs=S.CRS))
    if f.empty:
        f = S.footprint_from_units(u, simplify=100.0)
    f['src_sheet'] = lab
    fps.append(f)
    leg = pd.read_csv(f'{ROOT}/sources/{cfg.loc[lab, "legend"]}', dtype=str, keep_default_na=False)
    for key in sorted(u['xkey'].unique()):
        idx = key.split('|', 1)[1]
        org = idx.startswith('O/')
        minor = idx.startswith('o/')
        base = idx[2:] if (org or minor) else idx
        r = leg[leg['index'].isin(base.split('|'))]
        if not len(r):
            xw.append([key, 'Q', '', '', '', '', f'{lab}: index {idx} not in legend']); continue
        x = r.iloc[0]
        if minor:
            cov, ice = (x['ice_rich'], '') if x['ice_rich'] in S.COVER else ('', x['ice_rich'])
            xw.append([key, x['hclass'], 'O', x['texture'], cov, ice, f'{lab} {idx}: {base} with organic (peat/fen) 10-50 % (line-pattern overprint)'])
        elif org:
            xw.append([key, 'O', x['hclass'], 'organic', '', '', f'{lab} {idx}: organic grid overprint over {base}'])
        else:
            # legends transcribed 'veneer' in the ice_rich column: cover words go to cover
            cov, ice = (x['ice_rich'], '') if x['ice_rich'] in S.COVER else ('', x['ice_rich'])
            xw.append([key, x['hclass'], x['hclass2'], x['texture'], cov, ice, f'{lab} {idx}: {x["note"]}'])
    print(lab, len(u), 'polys', round(u.area.sum() / 1e6), 'km2', flush=True)
u = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=S.CRS)
fp = gpd.GeoDataFrame(pd.concat(fps, ignore_index=True), crs=S.CRS)
pd.DataFrame(xw, columns=['xkey', 'hclass', 'hclass2', 'texture', 'cover', 'ice_rich', 'xwalk_note']).to_csv(f'{S.XWALK}/{SRC}.csv', index=False)
S.write_std(u, fp, SRC, dict(title='GSC legacy surficial map scans, vectorised (this work)', sheets=ok))
print('sheets', len(ok), 'polys', len(u), 'km2', round(u.area.sum() / 1e6))
