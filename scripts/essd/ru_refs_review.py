#!/usr/bin/env python
"""Second check of the geokniga records found by ru_sheet_refs.py: a record must be the edition we used, not only the
right sheet. Edition of the record from its title ('третье поколение' = 3rd generation, 'новая серия' / 'Издание
второе' = new series / 2nd edition, 'Геологическая карта СССР' without either = 1st edition or old series); edition of
our sheet from its name (_g3, _g2) or, at 1:200,000, from the legend note (GGK-200/1, GGK-200/2, '1st edition').
Flagged (reference withheld, sheet listed for review): edition differs, or the release year and the record year differ
by more than 15 years. Placeholder release years (2010, 2013, 1980, 1985, 1995, 1965) give way to the record year.
usage: ru_refs_review.py [work_local/refs]   -> ru_sheet_refs_reviewed.csv, ru_refs_to_review.csv"""
import os
import re
import sys

import pandas as pd

D = sys.argv[1] if len(sys.argv) > 1 else 'work_local/refs'
R = pd.read_csv(f'{D}/ru_sheet_refs.csv', dtype=str, keep_default_na=False)


def rec_gen(t):
    t = t.lower()
    if 'трет' in t and 'поколен' in t:
        return 3
    if re.search(r'нов(ая|ой) сери|издание второе', t):
        return 2
    if 'геологическая карта ссср' in t:
        return 1
    return None


def our_gen(sheet):
    if re.search(r'_g3', sheet):
        return 3
    if re.search(r'_g2', sheet):
        return 2
    f = f'sources/legend_{sheet}.csv'
    if os.path.exists(f):
        n = ' '.join(pd.read_csv(f, dtype=str, keep_default_na=False).get('note', pd.Series(dtype=str)))[:400]
        if re.search(r'GGK-200/2|2nd edition|издание второе', n, flags=re.I):
            return 2
        if re.search(r'GGK-200/1|1st edition|GGK-200 ', n, flags=re.I):
            return 1
    return None


def placeholder(sheet, year):
    """the placeholder years of ingest_russia.py only: 1:1,000,000 sheets without a year (2013), preview placeholders
    (1980, 1985, 1995), N-44-V (1965) and M-45-III (2010); every other year is an imprint or record year"""
    if sheet == 'M-45-III':
        return year == '2010'
    if sheet == 'N-44-V':
        return year == '1965'
    if re.search(r'_g\dpv', sheet):
        return year in {'1980', '1985', '1995'}
    return not re.search(r'-[IVXL]+', sheet) and year == '2013'
rows = []
for x in R.to_dict('records'):
    why = []
    if x['record_ok'] == 'True':
        a, b = rec_gen(x['title']), our_gen(x['src_sheet'])
        if a and b and a != b:
            why.append(f'edition: record {a}, ours {b}')
        if x['year'] and x['page_year'] and abs(int(x['year']) - int(x['page_year'])) > 15:
            why.append(f"years {x['year']} vs record {x['page_year']}")
        if placeholder(x['src_sheet'], x['year']) and x['page_year'] and x['page_year'] != x['year'] and not why:
            x['reference'] = x['reference'].replace(f", {x['year']} (in Russian).", f", {x['page_year']} (in Russian).")
            x['year_fixed_from'] = x['year']
            x['year'] = x['page_year']
    else:
        why.append('no record found')
    x['review'] = '; '.join(why)
    if why:
        x['reference'] = ''
    rows.append(x)
O = pd.DataFrame(rows)
O.to_csv(f'{D}/ru_sheet_refs_reviewed.csv', index=False)
O.loc[O['review'] != '', ['src_sheet', 'year', 'page_year', 'review', 'node', 'title']].to_csv(f'{D}/ru_refs_to_review.csv', index=False)
print(f'{len(O)} sheets: reference kept {(O.reference != "").sum()}, for review {(O.review != "").sum()} '
      f'({O.review.str.contains("edition").sum()} edition, {O.review.str.contains("years").sum()} years, '
      f'{O.review.str.contains("no record").sum()} no record); placeholder years replaced: {O.get("year_fixed_from", pd.Series(dtype=str)).notna().sum()}')
