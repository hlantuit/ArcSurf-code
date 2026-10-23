#!/usr/bin/env python
"""Debug 2: run merge_tiles_test.do_tile on one tile (into a scratch MERGE_TDIR) with the later steps wrapped, printing
after each how much geometry lies OUTSIDE the tile. usage: debug_tile_outside2.py TILE_ID"""
import importlib.util
import json
import os
import sys
import tempfile

os.environ['MERGE_TDIR'] = tempfile.mkdtemp(prefix='dbg_', dir='/albedo/work/user/hlantuit/arctic_surficial/work')
sys.path.insert(0, '/albedo/work/user/hlantuit/arctic_surficial/pylib')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shapely  # noqa: E402
import pyogrio  # noqa: E402

spec = importlib.util.spec_from_file_location('mt', os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                                 'merge_tiles_test.py'))
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)
tid = sys.argv[1]
mt._init(json.load(open(f'{mt.S.WORK}/merge_sources.json')))
TG = pyogrio.read_dataframe(mt.LAND, layer='tiles', where=f"tile_id = '{tid}'").geometry.values[0]


def outside(df, label):
    o = shapely.area(shapely.difference(df.geometry.values, TG)) / 1e6
    m = o > 0.001
    extra = ''
    if m.any():
        x = df[m]
        extra = f" <- {list(zip(x['src_id'].astype(str)[:3], x['hclass'].astype(str)[:3]))}"
    print(f'{label:28s} n={len(df):7d} outside_km2={o.sum():10.3f}{extra}', flush=True)


def wrap(name):
    f = getattr(mt, name)

    def g(*a, **k):
        r = f(*a, **k)
        outside(r if not isinstance(r, tuple) else r[0], f'after {name}')
        return r
    setattr(mt, name, g)


orig_plan = mt._planarize


def plan(take, prio):
    r = orig_plan(take, prio)
    if len(take) > 50:                       # the whole-tile pass (per-sheet takes are usually small)
        outside(take, 'before _planarize(tile)')
        outside(r, 'after _planarize(tile)')
    return r


mt._planarize = plan
for n in ('split_by_zone', 'split_by_yedoma'):
    wrap(n)
ia_apply = mt.IA.apply_ice


def ice(out, tgeom, ice_):
    outside(out, 'before apply_ice')
    r = ia_apply(out, tgeom, ice_)
    outside(r[0], 'after apply_ice')
    return r


mt.IA.apply_ice = ice

_si = mt._sinter


def sinter_chk(a, b, *k, **kw):
    r = _si(a, b, *k, **kw)
    try:
        arr = list(a) if not isinstance(a, shapely.Geometry) else None
        if arr is not None and isinstance(b, shapely.Geometry):
            res = list(r)
            for i, (x, y) in enumerate(zip(arr, res)):
                if y is None or x is None:
                    continue
                o = shapely.area(shapely.difference(y, b))
                if o > 1e4:
                    print(f'  INTERSECTION LEAK: input {i} valid={shapely.is_valid(x)} area={x.area/1e6:.1f} km2, '
                          f'clip valid={b.is_valid} type={b.geom_type}, result area={y.area/1e6:.1f}, outside clip={o/1e6:.1f} km2', flush=True)
                    import pickle
                    pickle.dump((shapely.to_wkb(x), shapely.to_wkb(b)), open(f'/albedo/work/user/hlantuit/arctic_surficial/work/leak_{tid}_{i}.pkl', 'wb'))
    except Exception as e:
        print('chk error', e)
    return r


mt._sinter = sinter_chk

import traceback as _tb
_seen = set()


def chk_any(name, fn):
    def w(*a, **kw):
        r = fn(*a, **kw)
        try:
            geoms = [r] if isinstance(r, shapely.Geometry) else list(r)
            o = sum(shapely.area(shapely.difference(g, TG)) for g in geoms if g is not None and not g.is_empty)
            if o > 1e8:
                st = _tb.extract_stack(limit=3)[0]
                key = (name, round(o / 1e6, 1), tuple(type(x).__name__ for x in a))
                if key not in _seen:
                    _seen.add(key)
                    ins = [type(x).__name__ for x in a]
                    print(f'  OUTSIDE after {name} inputs={ins} outside={o/1e6:.1f} km2 | stack: ' + ' <- '.join(f'{f.name}:{f.lineno}' for f in _tb.extract_stack(limit=6)[:-1]), flush=True)
                    if name == '_sinter' and not isinstance(a[0], shapely.Geometry):
                        import pickle
                        arr = list(a[0]); res = list(r)
                        for i_, (x_, y_) in enumerate(zip(arr, res)):
                            if y_ is not None and shapely.area(shapely.difference(y_, TG)) > 1e8:
                                pickle.dump(dict(x=shapely.to_wkb(x_), clip=shapely.to_wkb(a[1]), y=shapely.to_wkb(y_)),
                                            open('/albedo/work/user/hlantuit/arctic_surficial/work/leak_case.pkl', 'wb'))
                                print(f'     saved element {i_}: x valid={shapely.is_valid(x_)} {x_.geom_type} area={x_.area/1e6:.1f}', flush=True)
                    for j, x in enumerate(a):
                        if isinstance(x, shapely.Geometry):
                            print(f'     arg{j}: {x.geom_type} valid={x.is_valid} area={x.area/1e6:.1f} outside_tile={shapely.area(shapely.difference(x, TG))/1e6:.1f}', flush=True)
        except Exception as e:
            print('chk err', name, e)
        return r
    return w


mt._sinter = chk_any('_sinter', mt._sinter)
mt._sdiff = chk_any('_sdiff', mt._sdiff)
mt._sunion = chk_any('_sunion', mt._sunion)
print(mt.do_tile((tid, TG)))
