#!/usr/bin/env python
"""Fill the number tokens of the manuscript parts: <span class="todo">@TOKEN@</span> -> the value from a JSON made by
numbers_release.py. Tokens without a value stay as they are and are listed.
usage: fill_tokens.py NUMBERS.json PART.html [PART.html ...]"""
import json
import re
import sys

vals = json.load(open(sys.argv[1], encoding='utf-8'))
TOK = re.compile(r'<span class="todo">@([A-Z0-9_]+)@</span>')
left = set()
for fn in sys.argv[2:]:
    s = open(fn, encoding='utf-8').read()
    n = len(TOK.findall(s))
    s2 = TOK.sub(lambda m: vals[m.group(1)] if m.group(1) in vals else m.group(0), s)
    rest = TOK.findall(s2)
    left.update(rest)
    if s2 != s:
        open(fn, 'w', encoding='utf-8', newline='').write(s2)
    print(f'{fn}: {n - len(rest)} of {n} tokens filled')
if left:
    print('NOT FILLED:', ', '.join(sorted(left)))
    sys.exit(1)
