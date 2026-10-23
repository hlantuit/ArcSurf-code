#!/usr/bin/env python
"""Apply exact text replacements to manuscript parts; each old string must occur exactly once.
usage: replace_once.py EDITS.json   (a list of [file, old, new])"""
import json
import sys

edits = json.load(open(sys.argv[1], encoding='utf-8'))
for fn, old, new in edits:
    s = open(fn, encoding='utf-8').read()
    n = s.count(old)
    if n != 1:
        sys.exit(f'{fn}: {n} occurrences of {old[:80]!r}')
    open(fn, 'w', encoding='utf-8', newline='').write(s.replace(old, new))
    print(f'ok {fn}: {old[:60]!r}')
