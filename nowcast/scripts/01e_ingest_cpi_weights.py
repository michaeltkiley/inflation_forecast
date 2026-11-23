#!/usr/bin/env python3
"""Ingest BLS CPI-U relative importance (percent of all items, December of each year, U.S. city average, expenditure-category hierarchy)
from https://www.bls.gov/cpi/tables/relative-importance/<year>.xlsx into DuckDB table `cpi_weights` (year, seq, lvl, item_name, ri). `seq` keeps the
table order so the hierarchy can be rebuilt from `lvl`. Only the expenditure-category block (up to the second 'All items' row, where special
aggregates start) is stored.  Requires BLS_CONTACT.  Skips years already stored; --force refetches.
Usage: python scripts/01e_ingest_cpi_weights.py [--years 2021 2022 2023 2024 2025]"""
import argparse

import openpyxl
import pandas as pd

from lib_common import connect, fetch, user_agent

URL = 'https://www.bls.gov/cpi/tables/relative-importance/{y}.xlsx'


def parse(path):
    rows = list(openpyxl.load_workbook(path, read_only=True)['Table 1'].iter_rows(values_only=True))
    out, seen_all = [], 0
    for r in rows:
        if r[0] is None or not str(r[0]).isdigit() or r[2] in (None, ''):
            continue
        name = str(r[1]).strip()
        if name == 'All items':
            seen_all += 1
            if seen_all == 2:
                break
        out.append((len(out), int(r[0]), name, float(r[2])))
    return pd.DataFrame(out, columns=['seq', 'lvl', 'item_name', 'ri'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', nargs='+', type=int, default=[2021, 2022, 2023, 2024, 2025])
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    con = connect()
    con.execute('CREATE TABLE IF NOT EXISTS cpi_weights (year INTEGER, seq INTEGER, lvl INTEGER, item_name VARCHAR, ri DOUBLE)')
    ua = user_agent(contact_required=True)
    for y in a.years:
        if not a.force and con.execute('select count(*) from cpi_weights where year=?', [y]).fetchone()[0]:
            continue
        d = parse(fetch(URL.format(y=y), f'bls_cpi_relative_importance_{y}.xlsx', ua, a.force)).assign(year=y)
        con.execute('DELETE FROM cpi_weights WHERE year=?', [y])
        con.execute('INSERT INTO cpi_weights SELECT year, seq, lvl, item_name, ri FROM d')
    print(con.execute("select year, count(*) items, round(sum(ri) filter (where lvl=1),2) sum_lvl1 from cpi_weights group by 1 order by 1").df().to_string(index=False))


if __name__ == '__main__':
    main()
