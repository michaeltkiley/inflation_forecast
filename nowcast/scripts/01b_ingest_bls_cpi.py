#!/usr/bin/env python3
"""Ingest BLS CPI-U detail (U.S. city average, monthly, SA and NSA) from BLS flat files into DuckDB tables
`cpi_series` (metadata with item names) and `cpi_data` (series_id, date, value, vintage).
Reads the cu directory listing and downloads cu.series, cu.item and the national data files cu.data.1, .2, .11-.18, .20
(regional / city-size files 3-10 and 19 are skipped). Requires BLS_CONTACT in .env or the environment.
Skips if today's vintage exists; --force re-pulls.  Usage: python scripts/01b_ingest_bls_cpi.py [--force]
"""
import argparse
import re
from datetime import date

import pandas as pd
import requests

from lib_common import connect, fetch, user_agent, vintage_done, drop_other_vintages

BASE = 'https://download.bls.gov/pub/time.series/cu/'
KEEP_FILES = {1, 2, 11, 12, 13, 14, 15, 16, 17, 18, 20}


def read_tsv(path):
    df = pd.read_csv(path, sep='\t', dtype=str, skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    return df.apply(lambda s: s.str.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    vintage = f'{date.today():%Y-%m-%d}'
    con = connect()
    if vintage_done(con, 'cpi_data', vintage) and not a.force:
        print(f'cpi_data vintage {vintage} already ingested (use --force)')
        return
    ua = user_agent(contact_required=True)
    listing = requests.get(BASE, headers={'User-Agent': ua}, timeout=60)
    listing.raise_for_status()
    files = sorted(set(re.findall(r'cu\.data\.(\d+)\.(\w+)', listing.text)))
    files = [f'cu.data.{n}.{nm}' for n, nm in files if int(n) in KEEP_FILES]

    series = read_tsv(fetch(BASE + 'cu.series', 'bls_cu.series', ua, a.force))
    items = read_tsv(fetch(BASE + 'cu.item', 'bls_cu.item', ua, a.force))
    series = series[(series.area_code == '0000') & (series.periodicity_code == 'R')]
    meta = series.merge(items[['item_code', 'item_name']], on='item_code')[
        ['series_id', 'item_code', 'item_name', 'seasonal', 'base_period', 'begin_year', 'end_year']]
    wanted = set(meta.series_id)

    parts = []
    for f in files:
        d = read_tsv(fetch(BASE + f, f'bls_{f}', ua, a.force))
        d = d[d.series_id.isin(wanted) & d.period.str.match(r'M(0[1-9]|1[0-2])$')]
        d = d.assign(date=pd.to_datetime(d.year + '-' + d.period.str[1:] + '-01'),
                     value=pd.to_numeric(d.value, errors='coerce')).dropna(subset=['value'])
        parts.append(d[['series_id', 'date', 'value']])
    data = pd.concat(parts).drop_duplicates(['series_id', 'date'])
    data['vintage'] = vintage

    con.execute('CREATE OR REPLACE TABLE cpi_series AS SELECT * FROM meta')
    con.execute('CREATE TABLE IF NOT EXISTS cpi_data AS SELECT * FROM data LIMIT 0')
    con.execute('DELETE FROM cpi_data WHERE vintage=?', [vintage])
    con.execute('INSERT INTO cpi_data SELECT series_id, date, value, vintage FROM data')
    drop_other_vintages(con, 'cpi_data', vintage)
    print(f'{len(files)} files, {data.series_id.nunique()} series, {data.date.min():%Y-%m} to {data.date.max():%Y-%m}')
    print(meta.groupby('seasonal').size().to_string())


if __name__ == '__main__':
    main()
