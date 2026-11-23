#!/usr/bin/env python3
"""Check config/pce_leaf_map.csv against BEA's own source list, Table 2.4.4U-D "Price Indexes for PCE: Source Data"
(XLSX linked from https://www.bea.gov/help/faq/521). For every leaf: is the line in BEA's table; for single-CPI-source leaves,
does the BLS item name of the mapped series equal the item BEA names, and is BEA's seasonal status (SA / NSA / SA by BEA)
consistent with the series' seasonal flag. Writes data/crosswalk_bea_check.csv. Needs the XLSX path (download once).
Usage: python scripts/02c_check_bea_source_table.py [--xlsx data/raw/<date>_bea_FAQ521_table244UD.xlsx]"""
import argparse
import re
from pathlib import Path

import openpyxl
import pandas as pd

from lib_common import DATA, RAW, ROOT, connect

PAPER_LEAVES, PAPER_NAME_MATCH, PAPER_SA_OK, PAPER_N_SINGLE = 220, 152, 167, 169     # values reported in docs/crosswalk_validation.md


def norm(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--xlsx', default=str(sorted(RAW.glob('*_bea_FAQ521_table244UD.xlsx'))[-1]))
    a = ap.parse_args()
    rows = list(openpyxl.load_workbook(a.xlsx, read_only=True).worksheets[0].iter_rows(values_only=True))
    b = pd.DataFrame([r[:5] for r in rows[4:]], columns=['item', 'component', 'code', 'source', 'sa'])
    b = b[b.item.astype(str).str.fullmatch(r'\d+')].copy()
    b['line'] = b.item.astype(int).astype(str)
    b['source'] = b.source.fillna('').astype(str).str.strip()
    b['sa'] = b.sa.fillna('').astype(str).str.strip()
    m = pd.read_csv(ROOT / 'config' / 'pce_leaf_map.csv', dtype=str)
    names = connect().execute('select series_id, item_name, seasonal from cpi_series').df().set_index('series_id')

    out = []
    for _, r in m.merge(b, on='line', how='left', suffixes=('', '_bea')).iterrows():
        parts = [] if pd.isna(r.series) else r.series.split(';')
        if len(parts) != 1 or not parts[0].startswith('CU'):
            continue
        sid = parts[0].split(':')[0]
        series_sa = 'SA' if names.loc[sid, 'seasonal'] == 'S' else 'NSA'
        out.append(dict(line=r.line, label=r.label[:40], bea_source=r.source[:60], mapped_item=names.loc[sid, 'item_name'][:60],
                        name_ok=norm(re.sub(r'^CPI\s+', '', r.source)) == norm(names.loc[sid, 'item_name']),
                        bea_sa=r.sa, series_sa=series_sa, sa_ok=r.sa == series_sa or r.sa == 'SA by BEA'))
    d = pd.DataFrame(out)
    d.to_csv(DATA / 'crosswalk_bea_check.csv', index=False)
    missing = sorted(set(m.line) - set(b.line), key=int)
    for name, got, want in [('map lines in BEA table', len(m) - len(missing), PAPER_LEAVES), ('single-CPI-source leaves', len(d), PAPER_N_SINGLE),
                            ('exact item-name matches', int(d.name_ok.sum()), PAPER_NAME_MATCH), ('seasonal status consistent', int(d.sa_ok.sum()), PAPER_SA_OK)]:
        print(f'{"OK      " if got == want else "MISMATCH"} {name}: {got} (documented {want})')
    print('\nSeasonal mismatches:'); print(d[~d.sa_ok][['line', 'label', 'bea_sa', 'series_sa']].to_string(index=False))


if __name__ == '__main__':
    main()
