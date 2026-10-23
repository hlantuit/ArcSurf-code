#!/usr/bin/env python
"""Write the reference list of the manuscript (the <ol class="refs"> block of 08_figs.html) from plain-text reference
files, one Copernicus-style entry per line: duplicates (same DOI or same text) dropped, sorted as Copernicus asks:
by first author; for the same first author single-author works first, then two-author works by second author, then
works with three or more authors, each chronologically.
usage: build_refs.py PARTS_DIR REFS.txt [REFS2.txt ...]"""
import html
import os
import re
import sys
import unicodedata

PARTS, files = sys.argv[1], sys.argv[2:]
entries, seen = [], set()
for f in files:
    for line in open(f, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        doi = re.search(r'https://doi\.org/(\S+?),', line)
        key = doi.group(1).lower() if doi else re.sub(r'\W+', '', line.lower())[:120]
        if key in seen:
            continue
        seen.add(key)
        entries.append(line)


def plain(t):
    return ''.join(c for c in unicodedata.normalize('NFKD', t) if not unicodedata.combining(c))


def sort_key(e):
    block = plain(e.split(': ', 1)[0])
    first = re.split(r',', block)[0].strip().lower()
    first = re.sub(r"['’]", '', first)
    if ' and ' not in block:
        n, second = 1, ''
    else:
        before = re.split(r',? and ', block)[0]
        groups = re.findall(r'[^,]+, (?:[A-Z]\.\s?)+(?:-[A-Z]\.)?', before)
        n = 2 if len(groups) <= 1 else 3
        second = re.split(r',? and ', block)[1].split(',')[0].strip().lower() if n == 2 else ''
    y = re.search(r'(\d{4})[a-z]?\.?(?:\s*\(in [A-Za-z]+\))?\.?\s*$', e)
    return (first, n, second, y.group(1) if y else '0', e.lower())


entries.sort(key=sort_key)
fn = os.path.join(PARTS, '08_figs.html')
s = open(fn, encoding='utf-8').read()
m = re.search(r'(<ol class="refs">\n)(.*?)(\s*</ol>)', s, re.S)
if not m:
    sys.exit('no <ol class="refs"> block')
body = ''.join(f'    <li>{html.escape(e, quote=False)}</li>\n' for e in entries)
s = s[:m.start(2)] + body + s[m.end(2):].lstrip('\n').rjust(0)
s = s.replace('</li>\n  </ol>', '</li>\n  </ol>')
open(fn, 'w', encoding='utf-8', newline='').write(s)
print(f'{len(entries)} references written')
