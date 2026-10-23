#!/usr/bin/env python
"""
Russian (VSEGEI / Gosgeolkarta) stratigraphic-genetic index parser.

A unit index is  <genesis letters><age>[<horizon>]  e.g.  gIII[os]  mnH^{2+3}<slv>
aH  plH  lgIII[os]^s  am_dH^3  mvfH^{2-3}.  The leading lowercase Latin letters are
the genetic type, by national convention; the first uppercase / roman / H/N/E
letter starts the age. This module maps the genetic letters to hclass and reads
texture from the Russian lithology text (first material named = dominant).

Unknown prefixes return None, so the crosswalk check fails loudly rather than
defaulting.
"""
import re

# longest-first matching of the genetic prefix
GEN = [
    ('lbl', 'K', 'O', 'lacustrine-boggy (alas)'), ('lb', 'K', 'O', 'lacustrine-boggy (alas / drained basin)'),
    ('gm', 'GM', '', 'glaciomarine'), ('lg', 'GL', '', 'glaciolacustrine'), ('fg', 'GF', '', 'fluvioglacial'),
    ('gf', 'GF', '', 'glaciofluvial'), ('am', 'F', 'M', 'alluvial-marine'), ('ma', 'M', 'F', 'marine-alluvial'),
    ('la', 'F', 'L', 'limnoalluvial'), ('al', 'F', 'L', 'alluvial-lacustrine'),
    ('mvf', 'M', 'F', 'marine wave-fluvial (undaflyuvial)'), ('mv', 'M', '', 'marine wave (undalyuvial)'),
    ('mn', 'M', '', 'marine nepheloid (offshore muds)'), ('mb', 'M', '', 'marine biogenic'),
    ('mf', 'M', 'F', 'marine fluvial'), ('ml', 'M', 'L', 'marine-lacustrine'),
    ('pl', 'O', '', 'paludal (bog)'), ('pal', 'O', '', 'paludal'), ('b', 'O', '', 'biogenic'),
    ('ed', 'W', 'C', 'eluvial-deluvial'), ('dp', 'C', 'F', 'deluvial-proluvial'), ('ds', 'C', '', 'deluvial-solifluction'),
    ('cd', 'C', '', 'colluvial-deluvial'), ('ld', 'L', 'C', 'lacustrine-deluvial'),
    ('g', 'T', '', 'glacial (moraine)'), ('f', 'GF', '', 'fluvioglacial'), ('m', 'M', '', 'marine'),
    ('a', 'F', '', 'alluvial'), ('p', 'F', '', 'proluvial (fans)'), ('l', 'L', '', 'lacustrine'),
    ('v', 'E', '', 'eolian'), ('d', 'C', '', 'deluvial (slope wash)'), ('c', 'C', '', 'colluvial'),
    ('s', 'C', '', 'solifluction'), ('e', 'W', '', 'eluvial'), ('h', 'X', '', 'technogenic'),
    ('t', 'X', '', 'technogenic'),
]
TEX = [('торф', 'organic'), ('валун', 'bouldery'), ('глыб', 'bouldery'), ('щебен', 'gravel'),
       ('галечник', 'gravel'), ('гравий', 'gravel'), ('галька', 'gravel'), ('пес', 'sand'),
       ('супес', 'fines'), ('суглин', 'fines'), ('алеврит', 'fines'), ('глин', 'fines'), ('ил', 'fines')]


def genetic_prefix(index):
    """'gmIII<kn>' -> 'gm';  'am_dH^3' -> 'am';  returns '' if none."""
    s = (index or '').strip()
    m = re.match(r'([a-z]+)', s)
    return m.group(1) if m else ''


def classify_index(index):
    p = genetic_prefix(index)
    for k, h, h2, note in GEN:          # longest prefix first (list order)
        if p == k:
            return h, h2, note
    for k, h, h2, note in sorted(GEN, key=lambda x: -len(x[0])):
        if p.startswith(k):
            return h, h2, note + f' (prefix {p!r} matched {k!r})'
    return None


def texture_ru(text):
    """Dominant texture = the first material named in the lithology text."""
    t = (text or '').lower()
    best = None
    for key, tex in TEX:
        i = t.find(key)
        if i >= 0 and (best is None or i < best[0]):
            best = (i, tex)
    return best[1] if best else 'unknown'
