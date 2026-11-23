#!/usr/bin/env python3
"""Audit config/pce_leaf_map.csv against the ingested data: every BEA price/nominal code in bea_pce (U20404/U20405) and
every BLS source series in cpi_data / ppi_data, plus the latest month each release supplies. Prints OK or MISSING.
Usage: python scripts/02a_audit_crosswalk.py"""
import pandas as pd

from lib_common import ROOT, connect

PAPER_LEAVES = 220            # econvitals: 220 components whose signed spending sums to total PCE


def main():
    m = pd.read_csv(ROOT / 'config' / 'pce_leaf_map.csv', dtype=str)
    con = connect()
    q = lambda s: con.execute(s).df()
    bea = set(q("select distinct series_code from bea_pce where table_id in ('U20404','U20405')").series_code)
    src = {p.split(':')[0].strip() for s in m.series.dropna() for p in s.split(';')}
    have = set(q('select distinct series_id from cpi_data').series_id) | set(q('select distinct series_id from ppi_data').series_id)
    checks = {'leaf count': (len(m) == PAPER_LEAVES, f'{len(m)} vs {PAPER_LEAVES}'),
              'BEA price codes': (set(m.bea_price_code.dropna()) <= bea, sorted(set(m.bea_price_code.dropna()) - bea)),
              'BEA nominal codes': (set(m.bea_nominal_code.dropna()) <= bea, sorted(set(m.bea_nominal_code.dropna()) - bea)),
              'BLS source series': (src <= have, sorted(src - have))}
    for k, (ok, detail) in checks.items():
        print(f'{"OK     " if ok else "MISSING"} {k}' + ('' if ok else f': {detail}'))
    last = q("""select 'BEA U20404' src, max(date) d from bea_pce where table_id='U20404'
                union all select 'CPI', max(date) from cpi_data union all select 'PPI/import', max(date) from ppi_data""")
    print(last.to_string(index=False))
    print('seasonal rule of sources:', pd.Series([p.split(':')[1] for s in m.series.dropna() for p in s.split(';')]).value_counts().to_dict())


if __name__ == '__main__':
    main()
