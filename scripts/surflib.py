"""
Shared helpers for the pan-Arctic surficial geology build.

Pipeline
--------
1. per source:  raw archive -> `work/std/<src_id>.gpkg`
       layer `units`      : polygons, EPSG:6931, native fields kept verbatim in
                            src_code / src_desc (+ src_extra JSON), provenance cols
       layer `footprint`  : what the source CLAIMS to have mapped (sheet extents
                            where known, else the dissolved polygon union)
2. per source:  `xwalk/<src_id>.csv`  native code -> hclass, hclass2, texture,
                cover, ice_rich, xwalk_note   (see LEGEND.md)
3. merge_tiles.py : precedence merge per 100 km EASE tile, clip to AMAP land,
                coastal sliver repair, write the final GeoPackage.

Every function here is deterministic and keeps the native unit, so a crosswalk
decision can be changed and the merge re-run without touching raw data.
"""
import json
import os
import shutil
import tempfile

# PROJ's sqlite db on GPFS fails intermittently ("proj_create_from_database:
# Open of .../share/proj failed"); a node-local copy avoids the lock contention.
_env = os.path.dirname(os.path.dirname(os.path.realpath(__import__('sys').executable)))
_src_proj = os.path.join(_env, 'share', 'proj')
_loc_proj = os.path.join(tempfile.gettempdir(), f'proj_{os.getuid()}')
if os.path.isdir(_src_proj) and not os.path.exists(os.path.join(_loc_proj, 'proj.db')):
    shutil.copytree(_src_proj, _loc_proj, dirs_exist_ok=True)
if os.path.exists(os.path.join(_loc_proj, 'proj.db')):
    os.environ['PROJ_DATA'] = os.environ['PROJ_LIB'] = _loc_proj
    # the env var is read once, at pyproj import: scripts importing geopandas BEFORE
    # surflib (ingest_nordic) got NaN transforms -> 'LinearRing not closed'. Set it live too.
    import pyproj.datadir
    pyproj.datadir.set_data_dir(_loc_proj)

import numpy as np            # noqa: E402
import pandas as pd           # noqa: E402
import geopandas as gpd       # noqa: E402
import shapely                # noqa: E402
from shapely import make_valid  # noqa: E402

ROOT = '/albedo/work/user/hlantuit/arctic_surficial'
RAW, WORK, OUT = f'{ROOT}/raw', f'{ROOT}/work', f'{ROOT}/out'
STD = f'{WORK}/std'
XWALK = f'{ROOT}/xwalk'
CRS = 6931  # WGS 84 / NSIDC EASE-Grid 2.0 North (LAEA, equal area)

HCLASS = {
    'R': 'Bedrock', 'T': 'Till / morainal', 'GF': 'Glaciofluvial',
    'GL': 'Glaciolacustrine', 'GM': 'Glaciomarine', 'M': 'Marine and littoral',
    'F': 'Fluvial / alluvial / deltaic', 'L': 'Lacustrine', 'K': 'Thermokarst / alas',
    'Y': 'Ice complex / Yedoma', 'E': 'Eolian', 'C': 'Colluvial / mass-wasting',
    'W': 'Residual / weathered regolith', 'O': 'Organic', 'V': 'Quaternary volcanic',
    'X': 'Anthropogenic', 'I': 'Glacier / perennial ice',
    'Q': 'Quaternary undivided', 'H': 'Water body (as mapped by the source)',
    'U': 'Unmapped / no data',
}
TEXTURE = {'gravel', 'sand', 'fines', 'diamicton', 'mixed', 'organic', 'bouldery', 'unknown'}
COVER = {'blanket', 'veneer', 'discontinuous', 'unknown'}
ICE = {'yes', 'no', 'unknown'}

PROV_COLS = ['src_id', 'src_sheet', 'src_code', 'src_desc', 'src_extra', 'scale_den',
             'pub_year', 'survey_years', 'conf_tier', 'licence', 'redistribution']


def polygons_only(gdf):
    """make_valid, drop empties, explode to single Polygons (GPKG layer type)."""
    g = gdf.copy()
    g['geometry'] = make_valid(g.geometry.values)
    g = g[g.geometry.notna() & ~g.geometry.is_empty]
    # make_valid can return GeometryCollections of MultiPolygons + lines; one explode
    # leaves MultiPolygons (Veremeeva lost ALL polygons this way), so repeat until flat
    for _ in range(4):
        g = g.explode(index_parts=False)
        if not g.geom_type.isin(['MultiPolygon', 'GeometryCollection']).any():
            break
    g = g[g.geom_type == 'Polygon']
    g = g[g.area > 0]
    return g.reset_index(drop=True)


def standardise(gdf, *, src_id, code, desc=None, sheet=None, extra=(), scale_den,
                pub_year=None, survey_years=None, conf_tier=None, licence,
                redistribution, drop_codes=(), xkey=None, carry=()):
    """Native layer -> standard `units` frame.

    `code`, `desc`, `sheet`, `conf_tier` may be a column name or a callable(row-frame)
    returning a Series; `scale_den`/`pub_year` may be a constant or column name.
    Rows whose code is in `drop_codes` (e.g. water) are removed and COUNTED.
    """
    def col(spec, default=None):
        if spec is None:
            return pd.Series(default, index=gdf.index)
        if callable(spec):
            return spec(gdf)
        if isinstance(spec, str) and spec in gdf.columns:
            return gdf[spec]
        return pd.Series(spec, index=gdf.index)

    out = gpd.GeoDataFrame({
        'src_id': src_id,
        'src_sheet': col(sheet).astype('string'),
        'src_code': col(code).astype('string').str.strip(),
        'src_desc': col(desc).astype('string'),
        'src_extra': gdf[list(extra)].astype(str).apply(
            lambda r: json.dumps(r.to_dict(), ensure_ascii=False), axis=1) if extra else None,
        'scale_den': pd.to_numeric(col(scale_den), errors='coerce').astype('Int64'),
        'pub_year': pd.to_numeric(col(pub_year), errors='coerce').astype('Int64'),
        'survey_years': col(survey_years).astype('string'),
        'conf_tier': col(conf_tier).astype('string'),
        'licence': licence, 'redistribution': redistribution,
    }, geometry=gdf.geometry.values, crs=gdf.crs)
    # xkey = what the crosswalk is keyed on. Defaults to the native code; sources
    # with hundreds of age-qualified symbols key on their genetic type instead.
    out['xkey'] = col(xkey).astype('string').str.strip() if xkey is not None else out['src_code']
    # carry = columns derived from the source's OWN attributes (e.g. texture from a
    # clast-size field) that should override the crosswalk defaults at merge time.
    for c in carry:
        out[c] = gdf[c].values
    n0 = len(out)
    if drop_codes:
        out = out[~out['src_code'].isin(drop_codes)]
    dropped = n0 - len(out)
    out = polygons_only(out.to_crs(CRS))
    return out, dropped


def write_std(units, footprint, src_id, meta):
    """Write the per-source standard GeoPackage + a sidecar json of counts."""
    os.makedirs(STD, exist_ok=True)
    p = f'{STD}/{src_id}.gpkg'
    if os.path.exists(p):
        os.remove(p)
    units.to_file(p, layer='units', driver='GPKG')
    footprint.to_file(p, layer='footprint', driver='GPKG')
    meta = dict(meta)
    meta.update(src_id=src_id, n_polygons=int(len(units)),
                area_km2=float(units.area.sum() / 1e6),
                footprint_km2=float(footprint.area.sum() / 1e6),
                n_codes=int(units['src_code'].nunique()))
    with open(f'{STD}/{src_id}.json', 'w') as f:
        json.dump(meta, f, indent=1, default=str)
    return p, meta


_AMAP = None


_AMAP_ONLY = None


def amap_only_geom():
    """The AMAP polygon itself (the coast-phase domain)."""
    global _AMAP_ONLY
    if _AMAP_ONLY is None:
        a = gpd.read_file(f'{RAW}/amap/amaplim_lam_poly.shp').to_crs(CRS)
        _AMAP_ONLY = shapely.make_valid(a.geometry.union_all())
        shapely.prepare(_AMAP_ONLY)
    return _AMAP_ONLY


def amap_geom():
    """The BUILD domain. SURF_DOMAIN=domain (set for the permafrost-region build, from
    2026-09-30): AMAP UNION Obu 2019 permafrost minus the Caucasus (work/domain_obu_amap.gpkg,
    layer 'domain', by obu_domain.py). Otherwise the AMAP polygon (coast phase)."""
    global _AMAP
    if _AMAP is None:
        if os.environ.get('SURF_DOMAIN') == 'domain':
            d = gpd.read_file(f'{WORK}/domain_obu_amap.gpkg', layer='domain').to_crs(CRS)
            _AMAP = shapely.make_valid(d.geometry.union_all())
            shapely.prepare(_AMAP)
        else:
            _AMAP = amap_only_geom()
    return _AMAP


def in_amap(gdf):
    """Keep features (already in CRS 6931) that touch the AMAP area."""
    return gdf[shapely.intersects(amap_geom(), gdf.geometry.values)]


def resolve_overlaps(units, prio_col):
    """Within-source overlaps double-count area in the merge. Features with a LOWER
    prio_col value win; later ones are differenced by the union of earlier ones.
    Returns (units, overlap_km2_removed)."""
    # Difference each feature only against the higher-priority pieces that actually
    # intersect it (STRtree); differencing against one global union was quadratic
    # (Svalbard G250: 17k polygons vs a 35,000 km2 glacier multipolygon).
    out, prev, removed = [], [], 0.0
    for p in sorted(units[prio_col].unique()):
        part = units[units[prio_col] == p].copy()
        geoms = part.geometry.values.copy()
        if prev:
            tree = shapely.STRtree(prev)
            ia, ib = tree.query(geoms, predicate='intersects')
            if len(ia):
                hits = pd.Series(ib).groupby(ia).apply(list)
                prev_arr = np.array(prev, dtype=object)
                for i, js in hits.items():
                    g0 = geoms[i]
                    cut = shapely.union_all(prev_arr[js])
                    geoms[i] = shapely.difference(g0, cut)
                    removed += (shapely.area(g0) - shapely.area(geoms[i])) / 1e6
        part['geometry'] = geoms
        out.append(part)
        prev.extend([g for g in geoms if g is not None and not g.is_empty])
    res = polygons_only(gpd.GeoDataFrame(pd.concat(out, ignore_index=True), crs=units.crs))
    return res, float(removed)


def footprint_from_units(units, simplify=50.0, overlay=False, coarse=None):
    """Dissolved union of the units, used when no sheet index is available.

    overlay=True marks a partial layer (its footprint is only its own polygons);
    it is not simplified, since simplification would move its claim off its units.
    coarse=m: outline only, from units simplified + buffered by m, unioned on an m/4 grid
    and shrunk back (the exact union of 172k Québec-Nord polygons ran > 9.7 h). A slightly
    generous footprint is harmless: merge_tiles fills only THIN slivers from the source's
    units; thicker footprint-minus-units gaps fall to coarser sources.
    """
    if coarse:
        c = shapely.buffer(shapely.simplify(units.geometry.values, coarse / 2), coarse)
        geom = shapely.buffer(shapely.union_all(c, grid_size=coarse / 4), -coarse)
        return gpd.GeoDataFrame({'src_id': [units['src_id'].iat[0]], 'overlay': [0]},
                                geometry=[shapely.simplify(geom, coarse / 2)], crs=CRS)
    geom = shapely.union_all(shapely.buffer(units.geometry.values, 0))
    if not overlay:
        geom = shapely.simplify(geom, simplify, preserve_topology=True)
    return gpd.GeoDataFrame({'src_id': [units['src_id'].iat[0]], 'overlay': [int(overlay)]},
                            geometry=[geom], crs=CRS)


def code_table(units):
    """Distinct native units with area -> seed for the crosswalk CSV."""
    t = (units.assign(a=units.area / 1e6)
         .groupby(['xkey'], dropna=False)
         .agg(n=('a', 'size'), area_km2=('a', 'sum'),
              example_code=('src_code', 'first'), example_desc=('src_desc', 'first'))
         .reset_index().sort_values('area_km2', ascending=False))
    return t


def load_xwalk(src_id):
    x = pd.read_csv(f'{XWALK}/{src_id}.csv', dtype=str, keep_default_na=False)
    bad = set(x['hclass']) - set(HCLASS) - {'DROP'}
    assert not bad, f'{src_id}: unknown hclass {bad}'
    for c, allowed in (('texture', TEXTURE), ('cover', COVER), ('ice_rich', ICE)):
        if c in x:
            x[c] = x[c].replace('', 'unknown')
            bad = set(x[c]) - allowed
            assert not bad, f'{src_id}: unknown {c} {bad}'
    return x


def apply_xwalk(units, src_id, key=('xkey',)):
    """Left-join the crosswalk; UNMATCHED codes raise, never default silently.

    hclass 'DROP' rows (water) are removed; returns (frame, n_dropped, km2_dropped).
    A carried `hclass_src` (a class the SOURCE asserts, e.g. Bryant's Yedoma flag)
    overrides hclass, and the crosswalk class moves to hclass2.
    """
    x = load_xwalk(src_id)
    key = list(key)
    x = x.drop_duplicates(key)
    m = units.merge(x[key + [c for c in ('hclass', 'hclass2', 'texture', 'cover',
                                         'ice_rich', 'xwalk_note') if c in x]],
                    on=key, how='left')
    miss = m['hclass'].isna()
    if miss.any():
        codes = m.loc[miss, key].drop_duplicates().head(20).to_dict('records')
        raise ValueError(f'{src_id}: {int(miss.sum())} polygons with no crosswalk entry, e.g. {codes}')
    for c in ('hclass2', 'xwalk_note'):
        if c not in m:
            m[c] = ''
    for c in ('texture', 'cover', 'ice_rich'):
        if c not in m:
            m[c] = 'unknown'
        # a value measured by the source (carried as <c>_src) beats the crosswalk
        if f'{c}_src' in m:
            s = m[f'{c}_src'].fillna('unknown')
            m[c] = s.where(s != 'unknown', m[c])
    if 'hclass2_src' in m:
        # second component measured by the source (e.g. GSC UTYPE2): beats the xwalk's
        o2 = m['hclass2_src'].fillna('').astype(str)
        m.loc[o2 != '', 'hclass2'] = o2[o2 != '']
    if 'hclass_src' in m:
        o = m['hclass_src'].fillna('').astype(str)
        hit = (o != '') & (o != m['hclass'])
        m.loc[hit, 'hclass2'] = m.loc[hit, 'hclass']
        m.loc[hit, 'hclass'] = o[hit]
        m.loc[hit, 'xwalk_note'] = (m.loc[hit, 'xwalk_note'].astype(str)
                                    + ' [hclass from source flag]').str.strip()
    drop = m['hclass'] == 'DROP'
    n_drop, a_drop = int(drop.sum()), float(m.loc[drop].area.sum() / 1e6) if drop.any() else 0.0
    m = m[~drop]
    return gpd.GeoDataFrame(m, geometry='geometry', crs=units.crs), n_drop, a_drop
