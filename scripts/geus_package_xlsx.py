#!/usr/bin/env python
"""GEUS_unit_translation.xlsx for the GEUS package: sheet "Units" (units.csv from export_geus_package.py), sheet
"Rules" (the GEUS crosswalk rules xwalk/gl_geus_*.csv) and sheet "ArcSurf classes" (integration/deposit_genesis.csv).
usage: geus_package_xlsx.py PACKAGE_DIR"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    pk = sys.argv[1]
    units = pd.read_csv(f'{pk}/units.csv', keep_default_na=False)
    rules = []
    for src, name in (('gl_geus_g500_v3', 'GEUS 1:500 000 v3.0'), ('gl_geus_g100_karrat', 'GEUS 1:100 000 Karrat')):
        r = pd.read_csv(f'{ROOT}/xwalk/{src}.csv', keep_default_na=False)
        r.insert(0, 'geus_dataset', name)
        rules.append(r)
    rules = pd.concat(rules, ignore_index=True).rename(columns={'xkey': 'geus_unit_label_or_rule'})
    cls = pd.read_csv(f'{ROOT}/integration/deposit_genesis.csv', keep_default_na=False)[['code', 'label', 'definition']]
    out = f'{pk}/GEUS_unit_translation.xlsx'
    with pd.ExcelWriter(out, engine='openpyxl') as xw:
        units.to_excel(xw, sheet_name='Units', index=False)
        rules.to_excel(xw, sheet_name='Rules', index=False)
        cls.to_excel(xw, sheet_name='ArcSurf classes', index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = 'A2'
            for col in ws.columns:
                width = max(len(str(c.value or '')) for c in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 70)
    print(out, len(units), 'units,', len(rules), 'rules')


if __name__ == '__main__':
    main()
