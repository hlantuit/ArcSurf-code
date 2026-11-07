#!/usr/bin/env python
"""Tag an RGB print PDF as sRGB: one embedded ICC profile for every colour, plus an sRGB output intent.

matplotlib writes all colour as DeviceRGB. Those RGB numbers carry no definition, so a print shop's RIP has to guess
(some assume Adobe RGB and oversaturate). This script embeds the sRGB profile once and then:
- points every RGB image, and the base of every indexed image, at it;
- adds it as DefaultRGB to every resource dictionary, which remaps the vector colours (rg / RG) of the content streams;
- makes it the blending space of each page (a page transparency group: halos and some keys are semi-transparent);
- declares an sRGB output intent in the catalog.

Nothing else changes: streams are copied as they are and text stays text. The profile is LittleCMS's built-in sRGB
(ICC v4, "No copyright, use freely"), stored next to this script as sRGB_lcms2_builtin.icc. The file version becomes 1.7,
the first PDF version that names an ICC v4 profile.

Needs pypdf. usage: pdf_srgb.py IN.pdf [OUT.pdf]   (no OUT: in place)"""
import os
import sys

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject

try:                                      # the map image is one ~76 MB stream, over pypdf's 75 MB guard against bombs
    from pypdf import overwrite_configuration
    overwrite_configuration(maximum_declared_stream_length=10 ** 10)
except ImportError:                       # older pypdf: a module constant (or no guard)
    import pypdf.filters
    pypdf.filters.MAX_DECLARED_STREAM_LENGTH = 10 ** 10

ICC =os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sRGB_lcms2_builtin.icc')
SRGB = 'sRGB IEC61966-2.1'                # the ICC registry's name for the characterisation
N = NameObject


def tag(src, dst):
    w = PdfWriter(clone_from=PdfReader(src))
    s = DecodedStreamObject()
    s.set_data(open(ICC, 'rb').read())
    s.update({N('/N'): NumberObject(3), N('/Alternate'): N('/DeviceRGB')})
    icc = w._add_object(s.flate_encode())
    cs = w._add_object(ArrayObject([N('/ICCBased'), icc]))
    n = {'images': 0, 'indexed': 0, 'named': 0, 'resources': 0, 'groups': 0}

    def fix(d, key):                      # d[key] is a colour space: DeviceRGB -> the ICC space, also as an Indexed base
        o = d[key]                        # (pypdf resolves indirect objects on access)
        if o == '/DeviceRGB':
            d[N(key)] = cs
            return 1
        if isinstance(o, ArrayObject) and len(o) == 4 and o[0] == '/Indexed' and o[1].get_object() == '/DeviceRGB':
            o[1] = cs
            n['indexed'] += 1
        return 0

    def group(x):                         # a transparency group's blending space
        g = x.get('/Group')
        if g is not None and '/CS' in g.get_object():
            n['groups'] += fix(g.get_object(), '/CS')

    def sub(d, key):                      # a resolved sub-dictionary, empty if absent (dict.get would not resolve)
        return d[key] if key in d else DictionaryObject()

    done = set()

    def resources(d):
        if id(d) in done:
            return
        done.add(id(d))
        n['resources'] += 1
        if '/ColorSpace' not in d:
            d[N('/ColorSpace')] = DictionaryObject()
        csd = d['/ColorSpace']
        for k in list(csd):
            n['named'] += fix(csd, k)
        csd[N('/DefaultRGB')] = cs
        xo = sub(d, '/XObject')
        for k in list(xo):
            x = xo[k]
            if x.get('/Subtype') == '/Image' and '/ColorSpace' in x:
                n['images'] += fix(x, '/ColorSpace')
            elif x.get('/Subtype') == '/Form':
                group(x)
                if '/Resources' in x:
                    resources(x['/Resources'])
        pat = sub(d, '/Pattern')
        for k in list(pat):
            p = pat[k]
            if '/Resources' in p:
                resources(p['/Resources'])
            if '/Shading' in p and '/ColorSpace' in p['/Shading']:
                fix(p['/Shading'], '/ColorSpace')
        sh = sub(d, '/Shading')
        for k in list(sh):
            if '/ColorSpace' in sh[k]:
                fix(sh[k], '/ColorSpace')
        gs = sub(d, '/ExtGState')
        for k in list(gs):
            sm = gs[k]['/SMask'] if '/SMask' in gs[k] else None
            if isinstance(sm, DictionaryObject) and '/G' in sm:
                f = sm['/G']                      # soft-mask groups keep their own space (DeviceGray luminosity)
                if '/Resources' in f:
                    resources(f['/Resources'])
        fo = sub(d, '/Font')
        for k in list(fo):
            f = fo[k]
            if f.get('/Subtype') == '/Type3' and '/Resources' in f:
                resources(f['/Resources'])

    for page in w.pages:
        resources(page['/Resources'])
        if '/Group' in page:
            group(page)
        else:
            page[N('/Group')] = DictionaryObject({N('/Type'): N('/Group'), N('/S'): N('/Transparency'), N('/CS'): cs})
            n['groups'] += 1
    w.root_object[N('/OutputIntents')] = ArrayObject([w._add_object(DictionaryObject({
        N('/Type'): N('/OutputIntent'), N('/S'): N('/GTS_PDFA1'), N('/OutputConditionIdentifier'): TextStringObject(SRGB),
        N('/RegistryName'): TextStringObject('http://www.color.org'), N('/Info'): TextStringObject(SRGB),
        N('/DestOutputProfile'): icc}))])
    w.pdf_header = '%PDF-1.7'
    tmp = dst + '.tmp'
    with open(tmp, 'wb') as f:
        w.write(f)
    os.replace(tmp, dst)
    print(f'{dst}: sRGB profile on {n["images"]} RGB images, {n["indexed"]} indexed palettes, {n["named"]} named '
          f'colour spaces and {n["groups"]} transparency groups; DefaultRGB in {n["resources"]} resource dictionaries; '
          f'output intent {SRGB}', flush=True)


if __name__ == '__main__':
    tag(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
